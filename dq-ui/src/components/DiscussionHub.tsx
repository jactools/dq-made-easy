import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth, useRules, useSettings } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { snakeToCamel } from '../utils/caseConverters'
import { AppSelect } from './app-primitives'
import { AppIcon, AppTabs, type AppIconName } from './app-primitives'
import { DiscussionPanel, normalizeDiscussionEntries, type DiscussionCommentType, type DiscussionEntry } from './discussion/DiscussionPanel'
import './DiscussionHub.css'

type DiscussionTopicKey = 'approvals' | 'incidents' | 'contract-reviews'
type DiscussionTopicFilter = 'all' | DiscussionTopicKey
type DiscussionCommentFilter = 'all' | DiscussionCommentType

interface DiscussionTopicOption {
  key: DiscussionTopicFilter
  label: string
  icon: AppIconName
}

interface DiscussionThreadCard {
  id: string
  topicKey: DiscussionTopicKey
  topicLabel: string
  title: string
  subtitle: string
  details: string[]
  entries: DiscussionEntry[]
  updatedAt: string
  searchText: string
  commentTypes: Set<DiscussionCommentType>
}

interface IncidentListItem {
  id: string
  incidentKind: string
  status: string
  title: string
  description?: string | null
  severity?: string | null
  runId?: string | null
  runPlanId?: string | null
  workspaceId?: string | null
  scopeKind?: string | null
  scopeId?: string | null
  sourceCorrelationId?: string | null
  sourceParentCorrelationId?: string | null
  sourceRequestId?: string | null
  sourceQueueMessageId?: string | null
  sourceTraceId?: string | null
  sourceSystem?: string | null
  failureCode?: string | null
  failureMessage?: string | null
  assignedTo?: string | null
  resolvedAt?: string | null
  itsmTicketId?: string | null
  itsmTicketNumber?: string | null
  createdAt?: string | null
  updatedAt?: string | null
  comments?: Array<Record<string, unknown>>
  resolutionHistory?: Array<Record<string, unknown>>
}

interface IncidentPagePayload {
  incidents: IncidentListItem[]
  count: number
  offset: number
  limit: number
}

interface DataAssetSummary {
  id: string
  name: string
  description?: string | null
  workspaceId: string
  status?: string | null
  createdAt?: string | null
  currentVersionId?: string | null
  dataContractDownloadUrl?: string | null
}

interface DataAssetContractAnalysis {
  success: boolean
  dataAssetId: string
  contract: {
    version: string
    name: string
    status: string
  }
  latestContractVersion: {
    reviewStatus?: string | null
    reviewedBy?: string | null
    reviewedAt?: string | null
    reviewComments?: string | null
  } | null
}

const TOPIC_OPTIONS: DiscussionTopicOption[] = [
  { key: 'all', label: 'All topics', icon: 'chat' },
  { key: 'approvals', label: 'Approvals', icon: 'shield-check' },
  { key: 'incidents', label: 'Incidents', icon: 'exclamation-circle' },
  { key: 'contract-reviews', label: 'Contract reviews', icon: 'document' },
]

const COMMENT_FILTER_OPTIONS: Array<{ value: DiscussionCommentFilter; label: string }> = [
  { value: 'all', label: 'All comment types' },
  { value: 'general', label: 'General' },
  { value: 'note', label: 'Note' },
  { value: 'concern', label: 'Concern' },
  { value: 'question', label: 'Question' },
]

const sameId = (left: unknown, right: unknown): boolean => String(left) === String(right)

const normalizeText = (value: unknown): string => String(value ?? '').trim().toLowerCase()

const splitTokens = (value: unknown): string[] => normalizeText(value).split(/\s+/).filter(Boolean)

const matchesSearch = (searchableValues: Array<unknown>, query: string): boolean => {
  const queryTokens = splitTokens(query)
  if (queryTokens.length === 0) return true
  return searchableValues.some((value) => {
    const normalized = normalizeText(value)
    return queryTokens.every((token) => normalized.includes(token))
  })
}

const requestJson = async <T,>(url: string, init: RequestInit = {}): Promise<T> => {
  const response = await fetch(url, init)
  if (!response.ok) {
    throw new Error(await response.text() || `Request failed (${response.status})`)
  }
  return await response.json() as T
}

const buildHeaders = (token: string | null): Record<string, string> => {
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

const formatSeverity = (severity?: string | null): string => {
  switch (String(severity || '').trim()) {
    case 'critical': return 'Critical'
    case 'high': return 'High'
    case 'medium': return 'Medium'
    case 'low': return 'Low'
    default: return 'Unknown'
  }
}

const formatIncidentStatus = (status: string): string => {
  switch (status) {
    case 'in_progress': return 'In Progress'
    case 'resolved': return 'Resolved'
    case 'closed': return 'Closed'
    case 'open': return 'Open'
    default: return status.replace(/[_-]+/g, ' ').replace(/\b\w/g, (match) => match.toUpperCase())
  }
}

const formatIncidentKind = (kind: string): string => {
  switch (kind) {
    case 'technical_run_error': return 'Technical Run Error'
    case 'functional_violation': return 'Functional Violation'
    default: return kind.replace(/[_-]+/g, ' ').replace(/\b\w/g, (match) => match.toUpperCase())
  }
}

const formatIncidentCorrelationSummary = (incident: IncidentListItem): string => {
  const parts: string[] = []

  if (incident.sourceCorrelationId) {
    parts.push(`Correlation ${incident.sourceCorrelationId}`)
  }
  if (incident.sourceParentCorrelationId) {
    parts.push(`Parent ${incident.sourceParentCorrelationId}`)
  }
  if (incident.sourceTraceId) {
    parts.push(`Trace ${incident.sourceTraceId}`)
  }
  if (incident.sourceRequestId) {
    parts.push(`Request ${incident.sourceRequestId}`)
  }
  if (incident.sourceQueueMessageId) {
    parts.push(`Queue ${incident.sourceQueueMessageId}`)
  }
  if (incident.sourceSystem) {
    parts.push(`Source ${incident.sourceSystem}`)
  }

  return parts.length > 0 ? parts.join(' · ') : 'No source correlation inputs'
}

const formatDateTime = (value?: string | null): string => {
  if (!value) return 'Unknown'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

const getApprovalWorkspaceId = (approval: { workspaceId?: string | null; ruleId: string }, rules: { id: string; workspace?: string }[]): string | null => {
  if (String(approval.workspaceId || '').trim()) {
    return String(approval.workspaceId).trim()
  }
  const matchingRule = rules.find((rule) => sameId(rule.id, approval.ruleId))
  return matchingRule?.workspace ? String(matchingRule.workspace).trim() : null
}

const buildThreadSearchText = (...values: Array<string | null | undefined>): string => {
  return values.filter(Boolean).map((value) => normalizeText(value)).join(' ')
}

const getThreadCommentTypes = (entries: DiscussionEntry[]): Set<DiscussionCommentType> => {
  return new Set(entries.map((entry) => entry.type))
}

const threadMatchesCommentFilter = (thread: DiscussionThreadCard, filter: DiscussionCommentFilter): boolean => {
  if (filter === 'all') return true
  return thread.commentTypes.has(filter)
}

const DiscussionThreadCardView: React.FC<{ thread: DiscussionThreadCard }> = ({ thread }) => {
  return (
    <article className="discussion-hub-thread-card">
      <div className="discussion-hub-thread-header">
        <div>
          <p className="discussion-hub-thread-topic">{thread.topicLabel}</p>
          <h3>{thread.title}</h3>
          <p className="discussion-hub-thread-subtitle">{thread.subtitle}</p>
        </div>
        <span className="discussion-hub-thread-count">{thread.entries.length} comment{thread.entries.length === 1 ? '' : 's'}</span>
      </div>

      {thread.details.length > 0 && (
        <div className="discussion-hub-thread-details">
          {thread.details.map((detail) => (
            <span key={detail} className="discussion-hub-thread-detail">{detail}</span>
          ))}
        </div>
      )}

      <DiscussionPanel
        title="Thread"
        subtitle="Discussion activity for this topic"
        entries={thread.entries}
        emptyState="No discussion comments recorded yet."
      />
    </article>
  )
}

export const DiscussionHub: React.FC = () => {
  const auth = useAuth()
  const rules = useRules()
  const settings = useSettings()
  const currentWorkspaceId = String(auth.currentWorkspaceId || '').trim()
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken())
  const [searchQuery, setSearchQuery] = useState('')
  const [topicFilter, setTopicFilter] = useState<DiscussionTopicFilter>('all')
  const [commentFilter, setCommentFilter] = useState<DiscussionCommentFilter>('all')
  const [incidentThreads, setIncidentThreads] = useState<DiscussionThreadCard[]>([])
  const [incidentLoading, setIncidentLoading] = useState(false)
  const [incidentError, setIncidentError] = useState<string | null>(null)
  const [contractThreads, setContractThreads] = useState<DiscussionThreadCard[]>([])
  const [contractLoading, setContractLoading] = useState(false)
  const [contractError, setContractError] = useState<string | null>(null)

  useEffect(() => {
    const syncToken = () => {
      setAuthToken(getAuthToken())
    }

    syncToken()
    window.addEventListener('storage', syncToken)
    window.addEventListener('dq-auth-token-changed', syncToken)

    return () => {
      window.removeEventListener('storage', syncToken)
      window.removeEventListener('dq-auth-token-changed', syncToken)
    }
  }, [])

  const approvalThreads = useMemo(() => {
    if (!currentWorkspaceId) {
      return []
    }

    const approvals = (rules.approvals || []).filter((approval) => {
      const workspaceId = getApprovalWorkspaceId(approval, rules.rules)
      return workspaceId === currentWorkspaceId
    })

    return approvals
      .map<DiscussionThreadCard | null>((approval) => {
        const entries = normalizeDiscussionEntries(approval.commentThread || [], auth.user?.name || 'Reviewer')
        if (entries.length === 0) {
          return null
        }

        const rule = rules.rules.find((candidate) => sameId(candidate.id, approval.ruleId))
        const title = rule?.name || approval.ruleId || approval.id
        const requestTypeLabel = approval.requestType === 'deactivation'
          ? 'Deactivation request'
          : approval.requestType === 'gx_suite_repair'
            ? 'Suite repair request'
            : 'Approval request'

        return {
          id: `approval-${approval.id}`,
          topicKey: 'approvals',
          topicLabel: 'Approvals',
          title,
          subtitle: `${requestTypeLabel} · ${approval.status === 'pending' ? 'Pending review' : formatDateTime(approval.reviewedAt || approval.requestedAt)}`,
          details: [
            `Workspace ${approval.workspaceId || currentWorkspaceId}`,
            approval.requesterName || approval.requesterDisplayName || approval.requesterId,
          ].filter(Boolean) as string[],
          entries,
          updatedAt: approval.reviewedAt || approval.requestedAt || new Date().toISOString(),
          searchText: buildThreadSearchText(
            'approval',
            approval.id,
            approval.ruleId,
            approval.requesterName,
            approval.requesterDisplayName,
            approval.requesterId,
            approval.status,
            approval.requestType,
            rule?.name,
            entries.map((entry) => `${entry.authorName} ${entry.content}`).join(' '),
          ),
          commentTypes: getThreadCommentTypes(entries),
        }
      })
      .filter((thread): thread is DiscussionThreadCard => thread !== null)
  }, [auth.user?.name, currentWorkspaceId, rules.approvals, rules.rules])

  const loadIncidentThreads = useCallback(async () => {
    if (!currentWorkspaceId) {
      setIncidentThreads([])
      setIncidentError('Select an active workspace to view discussion threads.')
      setIncidentLoading(false)
      return
    }

    setIncidentLoading(true)
    setIncidentError(null)

    try {
      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const response = await fetch(
        `${apiBase}/incidents?workspace_id=${encodeURIComponent(currentWorkspaceId)}&limit=200&offset=0`,
        {
          headers: buildHeaders(authToken),
        },
      )

      if (!response.ok) {
        throw new Error(`Unable to load workspace incidents (${response.status}).`)
      }

      const payload = snakeToCamel<IncidentPagePayload>(await response.json())
      const threads = (Array.isArray(payload.incidents) ? payload.incidents : [])
        .map<DiscussionThreadCard | null>((incident) => {
          const entries = normalizeDiscussionEntries(incident.comments || [], 'Incident')
          if (entries.length === 0) {
            return null
          }

          const title = incident.title || incident.id
          const subtitle = `${formatIncidentKind(incident.incidentKind)} · ${formatIncidentStatus(incident.status)}`
          const correlationSummary = formatIncidentCorrelationSummary(incident)
          const correlationDetail = correlationSummary !== 'No source correlation inputs' ? correlationSummary : null
          const details = [
            incident.severity ? `Severity ${formatSeverity(incident.severity)}` : null,
            incident.runId ? `Run ${incident.runId}` : null,
            incident.runPlanId ? `Run plan ${incident.runPlanId}` : null,
            correlationDetail,
            incident.assignedTo ? `Assigned to ${incident.assignedTo}` : null,
            incident.itsmTicketNumber ? `Ticket ${incident.itsmTicketNumber}` : null,
          ].filter((detail): detail is string => Boolean(detail))

          return {
            id: `incident-${incident.id}`,
            topicKey: 'incidents',
            topicLabel: 'Incidents',
            title,
            subtitle,
            details,
            entries,
            updatedAt: incident.updatedAt || incident.createdAt || new Date().toISOString(),
            searchText: buildThreadSearchText(
              'incident',
              incident.id,
              incident.title,
              incident.description,
              incident.incidentKind,
              incident.status,
              incident.severity,
              incident.failureCode,
              incident.failureMessage,
              incident.runId,
              incident.runPlanId,
              correlationDetail,
              incident.assignedTo,
              incident.itsmTicketNumber,
              entries.map((entry) => `${entry.authorName} ${entry.content}`).join(' '),
            ),
            commentTypes: getThreadCommentTypes(entries),
          }
        })
        .filter((thread): thread is DiscussionThreadCard => thread !== null)
        .sort((left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime())

      setIncidentThreads(threads)
    } catch (loadError) {
      setIncidentThreads([])
      setIncidentError(loadError instanceof Error ? loadError.message : 'Unable to load workspace incidents.')
    } finally {
      setIncidentLoading(false)
    }
  }, [authToken, currentWorkspaceId, settings.applicationSettings?.apiBaseUrl])

  const loadContractThreads = useCallback(async () => {
    if (!currentWorkspaceId) {
      setContractThreads([])
      setContractError('Select an active workspace to view contract review discussions.')
      setContractLoading(false)
      return
    }

    setContractLoading(true)
    setContractError(null)

    try {
      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const assetsPayload = await requestJson<unknown[]>(`${apiBase}/data-assets`, {
        headers: buildHeaders(authToken),
      })
      const assets = snakeToCamel<DataAssetSummary[]>(assetsPayload)
      const workspaceAssets = assets.filter((asset) => String(asset.workspaceId || '').trim() === currentWorkspaceId)

      const threads = await Promise.all(
        workspaceAssets.map(async (asset) => {
          const analysisPayload = await requestJson<unknown>(`${apiBase}/data-assets/${encodeURIComponent(asset.id)}/contract/analysis`, {
            headers: buildHeaders(authToken),
          })
          const analysis = snakeToCamel<DataAssetContractAnalysis>(analysisPayload)
          const reviewComments = String(analysis.latestContractVersion?.reviewComments || '').trim()
          if (!reviewComments) {
            return null
          }

          const reviewedBy = String(analysis.latestContractVersion?.reviewedBy || '').trim()
          const reviewedAt = String(analysis.latestContractVersion?.reviewedAt || '').trim()
          const entries = normalizeDiscussionEntries([
            {
              id: `contract-review-${asset.id}`,
              authorName: reviewedBy || 'Contract reviewer',
              content: reviewComments,
              type: 'note',
              createdAt: reviewedAt || new Date().toISOString(),
            },
          ], reviewedBy || 'Contract reviewer')

          return {
            id: `contract-${asset.id}`,
            topicKey: 'contract-reviews' as const,
            topicLabel: 'Contract reviews',
            title: asset.name || asset.id,
            subtitle: analysis.contract?.version ? `Contract version ${analysis.contract.version}` : 'Latest contract review',
            details: [
              `Workspace ${asset.workspaceId}`,
              analysis.latestContractVersion?.reviewStatus ? `Review ${analysis.latestContractVersion.reviewStatus}` : 'Review note available',
            ],
            entries,
            updatedAt: reviewedAt || asset.createdAt || new Date().toISOString(),
            searchText: buildThreadSearchText(
              'contract review',
              asset.id,
              asset.name,
              asset.description,
              asset.workspaceId,
              analysis.contract?.version,
              analysis.latestContractVersion?.reviewStatus,
              reviewedBy,
              reviewComments,
            ),
            commentTypes: getThreadCommentTypes(entries),
          } as DiscussionThreadCard
        }),
      )

      setContractThreads(threads.filter((thread): thread is DiscussionThreadCard => thread !== null))
    } catch (loadError) {
      setContractThreads([])
      setContractError(loadError instanceof Error ? loadError.message : 'Unable to load contract review discussions.')
    } finally {
      setContractLoading(false)
    }
  }, [authToken, currentWorkspaceId, settings.applicationSettings?.apiBaseUrl])

  useEffect(() => {
    void loadIncidentThreads()
  }, [loadIncidentThreads])

  useEffect(() => {
    void loadContractThreads()
  }, [loadContractThreads])

  const allThreads = useMemo(() => {
    return [...approvalThreads, ...incidentThreads, ...contractThreads].sort(
      (left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime(),
    )
  }, [approvalThreads, incidentThreads, contractThreads])

  const filteredThreads = useMemo(() => {
    return allThreads.filter((thread) => {
      if (topicFilter !== 'all' && thread.topicKey !== topicFilter) {
        return false
      }

      if (!threadMatchesCommentFilter(thread, commentFilter)) {
        return false
      }

      return matchesSearch([thread.searchText], searchQuery)
    })
  }, [allThreads, commentFilter, searchQuery, topicFilter])

  const commentCount = useMemo(() => {
    return filteredThreads.reduce((total, thread) => total + thread.entries.length, 0)
  }, [filteredThreads])

  const topicCount = useMemo(() => {
    return new Set(filteredThreads.map((thread) => thread.topicKey)).size
  }, [filteredThreads])

  const topicCounts = useMemo(() => {
    const counts: Record<DiscussionTopicFilter, number> = {
      all: allThreads.length,
      approvals: allThreads.filter((thread) => thread.topicKey === 'approvals').length,
      incidents: allThreads.filter((thread) => thread.topicKey === 'incidents').length,
      'contract-reviews': allThreads.filter((thread) => thread.topicKey === 'contract-reviews').length,
    }
    return counts
  }, [allThreads])

  return (
    <section className="discussion-hub-page">
      <div className="discussion-hub-header">
        <div>
          <h1>Discussions</h1>
          <p className="page-subtitle">Search threaded discussions across approvals, incidents, and contract review notes.</p>
        </div>
        {currentWorkspaceId && <span className="discussion-hub-workspace">Workspace {currentWorkspaceId}</span>}
      </div>

      <div className="discussion-hub-toolbar">
        <div className="discussion-hub-search-group">
          <label htmlFor="discussion-search-input">Search</label>
          <div className="discussion-hub-search">
            <AppIcon name="chat" />
            <input
              id="discussion-search-input"
              type="search"
              placeholder="Search discussions, comments, authors, or topic text"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              aria-label="Search discussions"
            />
            {searchQuery && (
              <button type="button" className="discussion-hub-clear-search" onClick={() => setSearchQuery('')} aria-label="Clear discussion search">
                <AppIcon name="times" />
              </button>
            )}
          </div>
        </div>

        <div className="discussion-hub-comment-filter">
          <AppSelect
            id="discussion-comment-filter"
            label="Comment type"
            value={commentFilter}
            onChange={(value) => setCommentFilter(value as DiscussionCommentFilter)}
            className="discussion-hub-comment-filter-select"
            placeholderLabel="All comment types"
            options={COMMENT_FILTER_OPTIONS}
          />
        </div>
      </div>

      <div className="discussion-hub-topic-tabs">
        <div className="discussion-hub-topic-tabs-scroll">
          <AppTabs
            ariaLabel="Discussion topics"
            value={topicFilter}
            onChange={setTopicFilter}
            className="discussion-hub-topic-tabs-control"
            tabs={TOPIC_OPTIONS.map((option) => ({
              value: option.key,
              label: `${option.label} (${topicCounts[option.key]})`,
              title: `Show ${option.label}`,
            }))}
          />
        </div>
      </div>

      <div className="discussion-hub-summary">
        <div className="discussion-hub-stat"><strong>{filteredThreads.length}</strong><span>Threads</span></div>
        <div className="discussion-hub-stat"><strong>{commentCount}</strong><span>Comments</span></div>
        <div className="discussion-hub-stat"><strong>{topicCount}</strong><span>Topics</span></div>
      </div>

      {!currentWorkspaceId ? (
        <div className="discussion-hub-empty-state">Select an active workspace to view discussion threads.</div>
      ) : filteredThreads.length === 0 ? (
        <div className="discussion-hub-empty-state">
          <p>No discussion threads match your search and topic filters.</p>
        </div>
      ) : (
        <div className="discussion-hub-thread-list">
          {filteredThreads.map((thread) => (
            <DiscussionThreadCardView key={thread.id} thread={thread} />
          ))}
        </div>
      )}

      {(incidentLoading || contractLoading || incidentError || contractError) && (
        <div className="discussion-hub-source-status-list">
          {incidentLoading && <p>Loading incident discussions…</p>}
          {contractLoading && <p>Loading contract review discussions…</p>}
          {incidentError && <p className="discussion-hub-source-error">Incidents: {incidentError}</p>}
          {contractError && <p className="discussion-hub-source-error">Contract reviews: {contractError}</p>}
        </div>
      )}
    </section>
  )
}