import React, { useEffect, useMemo, useState } from 'react'

import { getAuthToken } from '../contexts/AuthContext'
import { useAuth, useRules, useSettings } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import { snakeToCamel } from '../utils/caseConverters'
import { AuditCompilerVersions } from './AuditCompilerVersions'
import { Button } from './Button'
import { AppIcon, AppSelect, AppTabs, type AppIconName } from './app-primitives'
import './AuditTrail.css'

type AuditSectionTab = 'overview' | 'rules' | 'data-definition' | 'validation' | 'approvals' | 'versions'
type AuditSectionTabInput = AuditSectionTab | 'all' | 'changes'

interface AuditTrailProps {
  ruleId?: string
  initialTab?: AuditSectionTabInput
}

interface RuleStatusHistoryRow {
  id?: string
  ruleId: string
  action: string
  fromStatus: string | null
  toStatus: string
  changedBy: string | null
  changedAt: string
  reason: string | null
  details: Record<string, unknown> | null
}

interface DataDefinitionTaskSummaryRow {
  requestId: string
  currentWorkspaceId: string
  prompt: string
  requestedByUserId: string | null
  requestedByEmail: string | null
  requestedAt: string | null
  startedAt: string | null
  completedAt: string | null
  status: 'pending' | 'started' | 'completed' | 'failed'
  errorMessage: string | null
  analysisType: string
  analysisProvider: string
}

interface DataDefinitionTaskAuditRow {
  id: string
  requestId: string
  action: string
  fromStatus: string | null
  toStatus: string | null
  actorId: string | null
  changedAt: string
  details: Record<string, unknown>
}

interface ValidationRunRow {
  id: string
  workspace: string | null
  triggeredBy: string | null
  runAt: string
  total: number
  validCount: number
  invalidCount: number
  status: string
}

interface ValidationRunHistoryRow {
  id: string
  runId: string
  fromStatus: string | null
  toStatus: string
  changedBy: string | null
  changedAt: string
  reason: string | null
  details: Record<string, unknown> | null
}

interface ApprovalAuditRow {
  id: string
  approvalId: string
  action: string
  actorId: string | null
  timestamp: string
  details: Record<string, unknown>
}

interface TimelineEntry {
  id: string
  kindLabel: string
  title: string
  reference: string
  actorLabel: string
  timestamp: string
  summary: string
  fromStatus: string | null
  toStatus: string | null
  accent: string
  icon: AppIconName
}

interface TimelineSectionProps {
  sectionKey: Exclude<AuditSectionTab, 'overview' | 'versions'>
  title: string
  description: string
  countLabel: string
  latestLabel: string
  loading: boolean
  error: string | null
  entries: TimelineEntry[]
  emptyMessage: string
  selector?: React.ReactNode
  onRefresh: () => void
}

interface OverviewCardProps {
  sectionKey: Exclude<AuditSectionTab, 'overview' | 'versions'>
  title: string
  description: string
  countLabel: string
  latestLabel: string
  onOpen: () => void
}

const TAB_LABELS: Record<AuditSectionTab, string> = {
  overview: 'Overview',
  rules: 'Rule History',
  'data-definition': 'Data-Definition History',
  validation: 'Validation History',
  approvals: 'Approval History',
  versions: 'Rule & Compiler Versions',
}

const SECTION_META: Record<Exclude<AuditSectionTab, 'overview' | 'versions'>, { accent: string; icon: AppIconName }> = {
  rules: { accent: 'var(--app-brand-primary)', icon: 'arrow-curve-right' },
  'data-definition': { accent: 'var(--app-status-success-border)', icon: 'document' },
  validation: { accent: 'var(--app-status-info-border)', icon: 'play' },
  approvals: { accent: 'var(--app-status-warning-border)', icon: 'check-circle' },
}

const ACTION_META: Record<string, { label: string; icon: AppIconName; accent: string }> = {
  created: { label: 'Created', icon: 'document', accent: 'var(--app-status-success-border)' },
  modified: { label: 'Modified', icon: 'pencil', accent: 'var(--app-brand-primary)' },
  updated: { label: 'Updated', icon: 'pencil', accent: 'var(--app-brand-primary)' },
  approved: { label: 'Approved', icon: 'check-circle', accent: 'var(--app-status-success-border)' },
  rejected: { label: 'Rejected', icon: 'close-circle', accent: 'var(--app-status-error-border)' },
  commented: { label: 'Commented', icon: 'document', accent: 'var(--app-status-info-border)' },
  activated: { label: 'Activated', icon: 'play', accent: 'var(--app-status-info-border)' },
  deactivated: { label: 'Deactivated', icon: 'minus', accent: 'var(--app-status-error-border)' },
  submitted: { label: 'Submitted', icon: 'arrow-right', accent: 'var(--app-brand-primary)' },
  started: { label: 'Started', icon: 'play', accent: 'var(--app-status-info-border)' },
  completed: { label: 'Completed', icon: 'check-circle', accent: 'var(--app-status-success-border)' },
  failed: { label: 'Failed', icon: 'close-circle', accent: 'var(--app-status-error-border)' },
  pending: { label: 'Pending', icon: 'list', accent: 'var(--app-status-warning-border)' },
}

const DEFAULT_ACTION_META = { label: 'Event', icon: 'receipt' as AppIconName, accent: 'var(--app-text-secondary)' }

const humanize = (value: string): string => {
  const trimmed = String(value || '').trim()
  if (!trimmed) {
    return 'Event'
  }
  return trimmed
    .replace(/[-_]+/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ')
}

const asString = (value: unknown): string => (typeof value === 'string' ? value.trim() : '')

const asRecord = (value: unknown): Record<string, unknown> => (value && typeof value === 'object' ? (value as Record<string, unknown>) : {})

const formatDate = (value: string | null): string => {
  if (!value) {
    return 'Not available'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatRelativeCount = (count: number, noun: string): string => `${count} ${noun}${count === 1 ? '' : 's'}`

const summarizeDetails = (details: Record<string, unknown> | null | undefined): string => {
  if (!details) {
    return ''
  }

  const candidates = [
    details.summary,
    details.reason,
    details.message,
    details.comment,
    details.comments,
    details.note,
    details.description,
    details.state,
  ]

  for (const candidate of candidates) {
    const text = asString(candidate)
    if (text) {
      return text
    }
  }

  return ''
}

const describeTransition = (fromStatus: string | null, toStatus: string | null): string => {
  const fromValue = asString(fromStatus)
  const toValue = asString(toStatus)
  if (fromValue && toValue) {
    return `${fromValue} -> ${toValue}`
  }
  if (toValue) {
    return toValue
  }
  if (fromValue) {
    return fromValue
  }
  return ''
}

const getActionMeta = (action: string): { label: string; icon: AppIconName; accent: string } => {
  const normalized = String(action || '').trim().toLowerCase().replace(/\s+/g, '_')
  return ACTION_META[normalized] || DEFAULT_ACTION_META
}

const createTimelineId = (...parts: Array<string | null | undefined>): string =>
  parts
    .map((part) => asString(part))
    .filter(Boolean)
    .join('::') || `audit-${Math.random().toString(36).slice(2)}`

const normalizeTab = (tab?: AuditSectionTabInput): AuditSectionTab => {
  switch (tab) {
    case 'changes':
      return 'rules'
    case 'all':
      return 'overview'
    case 'rules':
    case 'data-definition':
    case 'validation':
    case 'approvals':
    case 'versions':
      return tab
    default:
      return 'overview'
  }
}

const buildHeaders = (): HeadersInit => {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const readErrorMessage = async (response: Response, fallback: string): Promise<string> => {
  const bodyText = await response.text().catch(() => '')
  if (!bodyText.trim()) {
    return fallback
  }

  try {
    const parsed = JSON.parse(bodyText) as Record<string, unknown>
    const detail = parsed.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail.trim()
    }
    if (detail && typeof detail === 'object') {
      const nested = detail as Record<string, unknown>
      const nestedMessage = asString(nested.message) || asString(nested.error)
      if (nestedMessage) {
        return nestedMessage
      }
    }
    const parsedMessage = asString(parsed.message) || asString(parsed.error)
    if (parsedMessage) {
      return parsedMessage
    }
  } catch {
    return bodyText.trim()
  }

  return bodyText.trim() || fallback
}

const fetchJson = async <T,>(url: string, fallbackMessage: string): Promise<T> => {
  const response = await fetch(url, {
    headers: buildHeaders(),
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, fallbackMessage))
  }

  return snakeToCamel<T>(await response.json())
}

const ruleSectionMeta = SECTION_META.rules
const dataDefinitionSectionMeta = SECTION_META['data-definition']
const validationSectionMeta = SECTION_META.validation
const approvalsSectionMeta = SECTION_META.approvals

const buildTimelineEntry = (params: {
  id: string
  kindLabel: string
  title: string
  reference: string
  actorLabel: string
  timestamp: string
  summary: string
  fromStatus?: string | null
  toStatus?: string | null
  icon?: AppIconName
  accent?: string
}): TimelineEntry => ({
  id: params.id,
  kindLabel: params.kindLabel,
  title: params.title,
  reference: params.reference,
  actorLabel: params.actorLabel,
  timestamp: params.timestamp,
  summary: params.summary,
  fromStatus: params.fromStatus ?? null,
  toStatus: params.toStatus ?? null,
  accent: params.accent || 'var(--app-text-secondary)',
  icon: params.icon || 'receipt',
})

const HistoryTimeline: React.FC<{ entries: TimelineEntry[] }> = ({ entries }) => {
  return (
    <div className="audit-timeline" role="list" aria-label="Audit event timeline">
      {entries.map((entry, index) => (
        <article key={entry.id} className="audit-timeline-item" role="listitem">
          <div className="audit-timeline-marker" style={{ borderColor: entry.accent }}>
            <AppIcon name={entry.icon} className="audit-timeline-icon" />
          </div>

          <div className="audit-timeline-content">
            <div className="audit-timeline-head">
              <div className="audit-timeline-title-block">
                <span className="audit-timeline-kind" style={{ color: entry.accent }}>
                  {entry.kindLabel}
                </span>
                <h4 className="audit-timeline-title">{entry.title}</h4>
                <p className="audit-timeline-reference">{entry.reference}</p>
              </div>
              <span className="audit-timeline-time">{formatDate(entry.timestamp)}</span>
            </div>

            <div className="audit-timeline-meta">
              <span className="audit-timeline-actor">By {entry.actorLabel || 'system'}</span>
              {entry.summary && <span className="audit-timeline-summary">{entry.summary}</span>}
            </div>

            {(entry.fromStatus || entry.toStatus) && (
              <div className="audit-timeline-transition">
                {entry.fromStatus ? <span className="audit-status-pill muted">{entry.fromStatus}</span> : <span className="audit-status-pill muted">-</span>}
                <span className="audit-transition-arrow">{'->'}</span>
                {entry.toStatus ? <span className="audit-status-pill">{entry.toStatus}</span> : <span className="audit-status-pill muted">-</span>}
              </div>
            )}
          </div>

          {index !== entries.length - 1 && <div className="audit-timeline-rail" />}
        </article>
      ))}
    </div>
  )
}

const AuditTimelineSection: React.FC<TimelineSectionProps> = ({
  sectionKey,
  title,
  description,
  countLabel,
  latestLabel,
  loading,
  error,
  entries,
  emptyMessage,
  selector,
  onRefresh,
}) => {
  const sectionMeta = SECTION_META[sectionKey]

  return (
    <section className="audit-section-card">
      <div className="audit-section-head">
        <div className="audit-section-copy">
          <span className="audit-section-kicker" style={{ color: sectionMeta.accent }}>
            {title}
          </span>
          <p className="audit-section-description">{description}</p>
        </div>

        <div className="audit-section-actions">
          <span className="audit-section-stat">{countLabel}</span>
          <span className="audit-section-stat muted">{latestLabel}</span>
          <Button onClick={onRefresh}>Refresh</Button>
        </div>
      </div>

      {selector && <div className="audit-section-toolbar">{selector}</div>}

      {error && <div className="audit-section-error">{error}</div>}

      {loading ? (
        <div className="audit-section-state">Loading audit history...</div>
      ) : entries.length === 0 ? (
        <div className="audit-section-state">{emptyMessage}</div>
      ) : (
        <HistoryTimeline entries={entries} />
      )}
    </section>
  )
}

const OverviewCard: React.FC<OverviewCardProps> = ({ sectionKey, title, description, countLabel, latestLabel, onOpen }) => {
  const sectionMeta = SECTION_META[sectionKey]

  return (
    <article className="audit-overview-card" style={{ borderTopColor: sectionMeta.accent }}>
      <div className="audit-overview-card-head">
        <span className="audit-overview-card-icon" style={{ color: sectionMeta.accent }}>
          <AppIcon name={sectionMeta.icon} />
        </span>
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
      </div>

      <div className="audit-overview-card-meta">
        <span>{countLabel}</span>
        <span>{latestLabel}</span>
      </div>

      <Button onClick={onOpen}>Open {title}</Button>
    </article>
  )
}

export const AuditTrail: React.FC<AuditTrailProps> = ({ ruleId, initialTab = 'all' }) => {
  const auth = useAuth()
  const rulesContext = useRules()
  const settings = useSettings()
  const compactMode = settings.displaySettings?.compactMode ?? false
  const currentWorkspaceId = String(auth.currentWorkspaceId || '').trim()
  const apiBase = useMemo(() => toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl), [settings.applicationSettings?.apiBaseUrl])
  const dataCatalogApiBase = useMemo(() => toApiGroupV1Base('data-catalog', settings.applicationSettings?.apiBaseUrl), [settings.applicationSettings?.apiBaseUrl])

  const [activeTab, setActiveTab] = useState<AuditSectionTab>(normalizeTab(initialTab))
  const [refreshNonce, setRefreshNonce] = useState(0)
  const [selectedRuleId, setSelectedRuleId] = useState<string>(String(ruleId || '').trim())
  const [ruleHistoryLoading, setRuleHistoryLoading] = useState(false)
  const [ruleHistoryError, setRuleHistoryError] = useState<string | null>(null)
  const [ruleHistoryEntries, setRuleHistoryEntries] = useState<TimelineEntry[]>([])

  const [dataDefinitionRequestsLoading, setDataDefinitionRequestsLoading] = useState(false)
  const [dataDefinitionRequestsError, setDataDefinitionRequestsError] = useState<string | null>(null)
  const [dataDefinitionRequests, setDataDefinitionRequests] = useState<DataDefinitionTaskSummaryRow[]>([])
  const [selectedDataDefinitionRequestId, setSelectedDataDefinitionRequestId] = useState('')
  const [dataDefinitionHistoryLoading, setDataDefinitionHistoryLoading] = useState(false)
  const [dataDefinitionHistoryError, setDataDefinitionHistoryError] = useState<string | null>(null)
  const [dataDefinitionHistoryEntries, setDataDefinitionHistoryEntries] = useState<TimelineEntry[]>([])

  const [validationRunsLoading, setValidationRunsLoading] = useState(false)
  const [validationRunsError, setValidationRunsError] = useState<string | null>(null)
  const [validationRuns, setValidationRuns] = useState<ValidationRunRow[]>([])
  const [selectedValidationRunId, setSelectedValidationRunId] = useState('')
  const [validationHistoryLoading, setValidationHistoryLoading] = useState(false)
  const [validationHistoryError, setValidationHistoryError] = useState<string | null>(null)
  const [validationHistoryEntries, setValidationHistoryEntries] = useState<TimelineEntry[]>([])

  const [approvalHistoryLoading, setApprovalHistoryLoading] = useState(false)
  const [approvalHistoryError, setApprovalHistoryError] = useState<string | null>(null)
  const [approvalHistoryEntries, setApprovalHistoryEntries] = useState<TimelineEntry[]>([])

  useEffect(() => {
    setActiveTab(normalizeTab(initialTab))
  }, [initialTab])

  const workspaceRules = useMemo(() => {
    if (!currentWorkspaceId) {
      return rulesContext.rules
    }
    return rulesContext.rules.filter((rule) => String(rule.workspace || '').trim() === currentWorkspaceId)
  }, [currentWorkspaceId, rulesContext.rules])

  const ruleOptions = useMemo(
    () => workspaceRules.map((rule) => ({ value: rule.id, label: rule.name })),
    [workspaceRules],
  )

  const dataDefinitionRequestOptions = useMemo(
    () => dataDefinitionRequests.map((request) => ({
      value: request.requestId,
      label: `${request.prompt.slice(0, 72)}${request.prompt.length > 72 ? '...' : ''}${request.status ? ` (${request.status})` : ''}`,
    })),
    [dataDefinitionRequests],
  )

  const validationRunOptions = useMemo(
    () => validationRuns.map((run) => ({
      value: run.id,
      label: `${run.id}${run.status ? ` (${run.status})` : ''}${run.total ? ` - ${run.validCount}/${run.total} valid` : ''}`,
    })),
    [validationRuns],
  )

  const selectedRule = useMemo(
    () => workspaceRules.find((rule) => rule.id === selectedRuleId) || workspaceRules[0] || null,
    [selectedRuleId, workspaceRules],
  )

  const selectedDataDefinitionRequest = useMemo(
    () => dataDefinitionRequests.find((request) => request.requestId === selectedDataDefinitionRequestId) || dataDefinitionRequests[0] || null,
    [dataDefinitionRequests, selectedDataDefinitionRequestId],
  )

  const selectedValidationRun = useMemo(
    () => validationRuns.find((run) => run.id === selectedValidationRunId) || validationRuns[0] || null,
    [selectedValidationRunId, validationRuns],
  )

  useEffect(() => {
    if (ruleId && ruleId !== selectedRuleId) {
      setSelectedRuleId(ruleId)
      return
    }

    if (selectedRuleId && workspaceRules.some((rule) => rule.id === selectedRuleId)) {
      return
    }

    const nextRuleId = workspaceRules[0]?.id || ''
    if (nextRuleId !== selectedRuleId) {
      setSelectedRuleId(nextRuleId)
    }
  }, [ruleId, selectedRuleId, workspaceRules])

  useEffect(() => {
    if (selectedDataDefinitionRequestId && dataDefinitionRequests.some((request) => request.requestId === selectedDataDefinitionRequestId)) {
      return
    }
    setSelectedDataDefinitionRequestId(dataDefinitionRequests[0]?.requestId || '')
  }, [dataDefinitionRequests, selectedDataDefinitionRequestId])

  useEffect(() => {
    if (selectedValidationRunId && validationRuns.some((run) => run.id === selectedValidationRunId)) {
      return
    }
    setSelectedValidationRunId(validationRuns[0]?.id || '')
  }, [selectedValidationRunId, validationRuns])

  const refreshAll = () => {
    setRefreshNonce((current) => current + 1)
  }

  useEffect(() => {
    let cancelled = false

    const loadRuleHistory = async () => {
      if (!selectedRuleId) {
        setRuleHistoryEntries([])
        setRuleHistoryError(null)
        setRuleHistoryLoading(false)
        return
      }

      setRuleHistoryLoading(true)
      setRuleHistoryError(null)

      try {
        const payload = await fetchJson<RuleStatusHistoryRow[]>(
          `${apiBase}/rules/${encodeURIComponent(selectedRuleId)}/status-history?limit=100&offset=0`,
          `Unable to load rule history for ${selectedRuleId}.`,
        )
        if (cancelled) {
          return
        }

        const rows = Array.isArray(payload) ? payload : []
        const entries = rows
          .map((row) => buildTimelineEntry({
            id: row.id || createTimelineId(row.ruleId, row.changedAt, row.action),
            kindLabel: 'Rule history',
            title: humanize(row.action),
            reference: selectedRule ? `${selectedRule.name} (${selectedRule.id})` : row.ruleId,
            actorLabel: row.changedBy || 'system',
            timestamp: row.changedAt,
            summary: summarizeDetails(row.details) || describeTransition(row.fromStatus, row.toStatus) || 'Rule status updated',
            fromStatus: row.fromStatus,
            toStatus: row.toStatus,
            accent: ruleSectionMeta.accent,
            icon: getActionMeta(row.action).icon,
          }))
          .sort((left, right) => Date.parse(String(right.timestamp || '')) - Date.parse(String(left.timestamp || '')))

        setRuleHistoryEntries(entries)
      } catch (error) {
        if (cancelled) {
          return
        }
        setRuleHistoryEntries([])
        setRuleHistoryError(error instanceof Error ? error.message : `Unable to load rule history for ${selectedRuleId}.`)
      } finally {
        if (!cancelled) {
          setRuleHistoryLoading(false)
        }
      }
    }

    void loadRuleHistory()

    return () => {
      cancelled = true
    }
  }, [apiBase, refreshNonce, selectedRule, selectedRuleId])

  useEffect(() => {
    let cancelled = false

    const loadDataDefinitionRequests = async () => {
      if (!currentWorkspaceId) {
        setDataDefinitionRequests([])
        setDataDefinitionRequestsError('Select a workspace to view data-definition history.')
        setDataDefinitionRequestsLoading(false)
        return
      }

      setDataDefinitionRequestsLoading(true)
      setDataDefinitionRequestsError(null)

      try {
        const payload = await fetchJson<{ requests: DataDefinitionTaskSummaryRow[]; count: number }>(
          `${dataCatalogApiBase}/data-definition-tasks/requests?workspace_id=${encodeURIComponent(currentWorkspaceId)}&limit=20`,
          'Unable to load data-definition requests.',
        )
        if (cancelled) {
          return
        }

        const rows = Array.isArray(payload.requests) ? payload.requests : []
        const sortedRows = [...rows].sort((left, right) => Date.parse(String(right.requestedAt || '')) - Date.parse(String(left.requestedAt || '')))
        setDataDefinitionRequests(sortedRows)
      } catch (error) {
        if (cancelled) {
          return
        }
        setDataDefinitionRequests([])
        setDataDefinitionRequestsError(error instanceof Error ? error.message : 'Unable to load data-definition requests.')
      } finally {
        if (!cancelled) {
          setDataDefinitionRequestsLoading(false)
        }
      }
    }

    void loadDataDefinitionRequests()

    return () => {
      cancelled = true
    }
  }, [currentWorkspaceId, dataCatalogApiBase, refreshNonce])

  useEffect(() => {
    let cancelled = false

    const loadDataDefinitionHistory = async () => {
      if (!selectedDataDefinitionRequestId) {
        setDataDefinitionHistoryEntries([])
        setDataDefinitionHistoryError(null)
        setDataDefinitionHistoryLoading(false)
        return
      }

      setDataDefinitionHistoryLoading(true)
      setDataDefinitionHistoryError(null)

      try {
        const payload = await fetchJson<{ requestId: string; events: DataDefinitionTaskAuditRow[]; count: number }>(
          `${dataCatalogApiBase}/data-definition-tasks/requests/${encodeURIComponent(selectedDataDefinitionRequestId)}/history?limit=50&offset=0`,
          `Unable to load data-definition history for ${selectedDataDefinitionRequestId}.`,
        )
        if (cancelled) {
          return
        }

        const rows = Array.isArray(payload.events) ? payload.events : []
        const requestLabel = selectedDataDefinitionRequest?.prompt || selectedDataDefinitionRequestId
        const entries = rows
          .map((row) => buildTimelineEntry({
            id: row.id || createTimelineId(row.requestId, row.changedAt, row.action),
            kindLabel: 'Data-definition history',
            title: humanize(row.action),
            reference: `${requestLabel} (${row.requestId})`,
            actorLabel: row.actorId || selectedDataDefinitionRequest?.requestedByEmail || selectedDataDefinitionRequest?.requestedByUserId || 'system',
            timestamp: row.changedAt,
            summary: summarizeDetails(row.details) || describeTransition(row.fromStatus, row.toStatus) || 'Data-definition request updated',
            fromStatus: row.fromStatus,
            toStatus: row.toStatus,
            accent: dataDefinitionSectionMeta.accent,
            icon: getActionMeta(row.action).icon,
          }))
          .sort((left, right) => Date.parse(String(right.timestamp || '')) - Date.parse(String(left.timestamp || '')))

        setDataDefinitionHistoryEntries(entries)
      } catch (error) {
        if (cancelled) {
          return
        }
        setDataDefinitionHistoryEntries([])
        setDataDefinitionHistoryError(error instanceof Error ? error.message : `Unable to load data-definition history for ${selectedDataDefinitionRequestId}.`)
      } finally {
        if (!cancelled) {
          setDataDefinitionHistoryLoading(false)
        }
      }
    }

    void loadDataDefinitionHistory()

    return () => {
      cancelled = true
    }
  }, [currentWorkspaceId, dataCatalogApiBase, refreshNonce, selectedDataDefinitionRequest, selectedDataDefinitionRequestId])

  useEffect(() => {
    let cancelled = false

    const loadValidationRuns = async () => {
      if (!currentWorkspaceId) {
        setValidationRuns([])
        setValidationRunsError('Select a workspace to view validation history.')
        setValidationRunsLoading(false)
        return
      }

      setValidationRunsLoading(true)
      setValidationRunsError(null)

      try {
        const payload = await fetchJson<{ data: ValidationRunRow[]; pagination: Record<string, unknown> }>(
          `${apiBase}/rules/validation-runs?workspace=${encodeURIComponent(currentWorkspaceId)}&limit=20`,
          'Unable to load validation runs.',
        )
        if (cancelled) {
          return
        }

        const rows = Array.isArray(payload.data) ? payload.data : []
        const sortedRows = [...rows].sort((left, right) => Date.parse(String(right.runAt || '')) - Date.parse(String(left.runAt || '')))
        setValidationRuns(sortedRows)
      } catch (error) {
        if (cancelled) {
          return
        }
        setValidationRuns([])
        setValidationRunsError(error instanceof Error ? error.message : 'Unable to load validation runs.')
      } finally {
        if (!cancelled) {
          setValidationRunsLoading(false)
        }
      }
    }

    void loadValidationRuns()

    return () => {
      cancelled = true
    }
  }, [apiBase, currentWorkspaceId, refreshNonce])

  useEffect(() => {
    let cancelled = false

    const loadValidationHistory = async () => {
      if (!selectedValidationRunId) {
        setValidationHistoryEntries([])
        setValidationHistoryError(null)
        setValidationHistoryLoading(false)
        return
      }

      setValidationHistoryLoading(true)
      setValidationHistoryError(null)

      try {
        const payload = await fetchJson<ValidationRunHistoryRow[]>(
          `${apiBase}/gx/runs/${encodeURIComponent(selectedValidationRunId)}/status-history`,
          `Unable to load validation history for ${selectedValidationRunId}.`,
        )
        if (cancelled) {
          return
        }

        const rows = Array.isArray(payload) ? payload : []
        const selectedLabel = selectedValidationRun ? `${selectedValidationRun.id} (${selectedValidationRun.status})` : selectedValidationRunId
        const entries = rows
          .map((row) => buildTimelineEntry({
            id: row.id || createTimelineId(row.runId, row.changedAt, row.toStatus),
            kindLabel: 'Validation history',
            title: humanize(row.toStatus),
            reference: selectedLabel,
            actorLabel: row.changedBy || selectedValidationRun?.triggeredBy || 'system',
            timestamp: row.changedAt,
            summary: summarizeDetails(row.details) || row.reason || 'Validation run status updated',
            fromStatus: row.fromStatus,
            toStatus: row.toStatus,
            accent: validationSectionMeta.accent,
            icon: getActionMeta(row.toStatus).icon,
          }))
          .sort((left, right) => Date.parse(String(right.timestamp || '')) - Date.parse(String(left.timestamp || '')))

        setValidationHistoryEntries(entries)
      } catch (error) {
        if (cancelled) {
          return
        }
        setValidationHistoryEntries([])
        setValidationHistoryError(error instanceof Error ? error.message : `Unable to load validation history for ${selectedValidationRunId}.`)
      } finally {
        if (!cancelled) {
          setValidationHistoryLoading(false)
        }
      }
    }

    void loadValidationHistory()

    return () => {
      cancelled = true
    }
  }, [apiBase, refreshNonce, selectedValidationRun, selectedValidationRunId])

  useEffect(() => {
    let cancelled = false

    const loadApprovalHistory = async () => {
      setApprovalHistoryLoading(true)
      setApprovalHistoryError(null)

      try {
        const payload = await fetchJson<ApprovalAuditRow[]>(
          `${apiBase}/approvals/audit`,
          'Unable to load approval history.',
        )
        if (cancelled) {
          return
        }

        const rows = Array.isArray(payload) ? payload : []
        const entries = rows
          .map((row) => buildTimelineEntry({
            id: row.id || createTimelineId(row.approvalId, row.timestamp, row.action),
            kindLabel: 'Approval history',
            title: humanize(row.action),
            reference: `Approval ${row.approvalId}`,
            actorLabel: row.actorId || 'system',
            timestamp: row.timestamp,
            summary: summarizeDetails(row.details) || 'Approval audit event recorded',
            accent: approvalsSectionMeta.accent,
            icon: getActionMeta(row.action).icon,
          }))
          .sort((left, right) => Date.parse(String(right.timestamp || '')) - Date.parse(String(left.timestamp || '')))

        setApprovalHistoryEntries(entries)
      } catch (error) {
        if (cancelled) {
          return
        }
        setApprovalHistoryEntries([])
        setApprovalHistoryError(error instanceof Error ? error.message : 'Unable to load approval history.')
      } finally {
        if (!cancelled) {
          setApprovalHistoryLoading(false)
        }
      }
    }

    void loadApprovalHistory()

    return () => {
      cancelled = true
    }
  }, [apiBase, refreshNonce])

  const overviewCards = [
    {
      sectionKey: 'rules' as const,
      title: 'Rule history',
      description: 'Status changes, approvals, and lifecycle transitions for governed rules.',
      countLabel: formatRelativeCount(ruleHistoryEntries.length, 'event'),
      latestLabel: `Latest: ${formatDate(ruleHistoryEntries[0]?.timestamp || null)}`,
      onOpen: () => setActiveTab('rules'),
    },
    {
      sectionKey: 'data-definition' as const,
      title: 'Data-definition history',
      description: 'Draft requests and audit events for generated business term definitions.',
      countLabel: formatRelativeCount(dataDefinitionHistoryEntries.length, 'event'),
      latestLabel: `Latest: ${formatDate(dataDefinitionHistoryEntries[0]?.timestamp || null)}`,
      onOpen: () => setActiveTab('data-definition'),
    },
    {
      sectionKey: 'validation' as const,
      title: 'Validation history',
      description: 'Validation run state transitions for compliance and execution traceability.',
      countLabel: formatRelativeCount(validationHistoryEntries.length, 'event'),
      latestLabel: `Latest: ${formatDate(validationHistoryEntries[0]?.timestamp || null)}`,
      onOpen: () => setActiveTab('validation'),
    },
    {
      sectionKey: 'approvals' as const,
      title: 'Approval history',
      description: 'Audit events for approval actions, comments, and review transitions.',
      countLabel: formatRelativeCount(approvalHistoryEntries.length, 'event'),
      latestLabel: `Latest: ${formatDate(approvalHistoryEntries[0]?.timestamp || null)}`,
      onOpen: () => setActiveTab('approvals'),
    },
  ]

  const tabValue = activeTab

  return (
    <div className={`audit-report-shell${compactMode ? ' compact' : ''}`}>
      <header className="audit-report-hero">
        <div className="audit-report-hero-copy">
          <p className="audit-report-kicker">WS8-A02 compliance reporting</p>
          <h2>Audit Trail</h2>
          <p className="trail-description">
            Rule, data-definition, validation, and approval history are surfaced from the canonical backend audit seams.
            The compliance page stays focused on compliance workflows, not audit reporting.
          </p>
        </div>

        <div className="audit-report-hero-actions">
          <div className="audit-report-workspace">
            <span className="audit-report-workspace-label">Workspace</span>
            <strong>{currentWorkspaceId || 'No active workspace'}</strong>
          </div>
          <Button onClick={refreshAll}>Refresh all history</Button>
        </div>
      </header>

      <div className="audit-report-overview-grid">
        {overviewCards.map((card) => (
          <OverviewCard
            key={card.title}
            sectionKey={card.sectionKey}
            title={card.title}
            description={card.description}
            countLabel={card.countLabel}
            latestLabel={card.latestLabel}
            onOpen={card.onOpen}
          />
        ))}
      </div>

      <div className="audit-header-tabs" aria-label="Audit report sections">
        <div className="audit-header-tabs-scroll">
          <AppTabs
            ariaLabel="Audit report sections"
            value={tabValue}
            onChange={(value) => setActiveTab(value as AuditSectionTab)}
            className="audit-header-tabs-control"
            tabs={[
              { value: 'overview', label: TAB_LABELS.overview, title: 'Open overview' },
              { value: 'rules', label: TAB_LABELS.rules, title: 'Open rule history' },
              { value: 'data-definition', label: TAB_LABELS['data-definition'], title: 'Open data-definition history' },
              { value: 'validation', label: TAB_LABELS.validation, title: 'Open validation history' },
              { value: 'approvals', label: TAB_LABELS.approvals, title: 'Open approval history' },
              { value: 'versions', label: TAB_LABELS.versions, title: 'Open rule and compiler versions' },
            ]}
          />
        </div>
      </div>

      {activeTab === 'overview' && (
        <div className="audit-overview-panel">
          <div className="audit-overview-panel-copy">
            <h3>Reporting views</h3>
            <p>
              Use the section tabs to drill into the owned audit seam for each workflow. Each section is backed by the
              relevant API contract and can be inspected independently.
            </p>
          </div>

          <div className="audit-overview-panel-grid">
            <div className="audit-overview-stat">
              <span className="audit-overview-stat-label">Rule events</span>
              <strong>{formatRelativeCount(ruleHistoryEntries.length, 'event')}</strong>
              <span>{formatDate(ruleHistoryEntries[0]?.timestamp || null)}</span>
            </div>
            <div className="audit-overview-stat">
              <span className="audit-overview-stat-label">Data-definition events</span>
              <strong>{formatRelativeCount(dataDefinitionHistoryEntries.length, 'event')}</strong>
              <span>{formatDate(dataDefinitionHistoryEntries[0]?.timestamp || null)}</span>
            </div>
            <div className="audit-overview-stat">
              <span className="audit-overview-stat-label">Validation events</span>
              <strong>{formatRelativeCount(validationHistoryEntries.length, 'event')}</strong>
              <span>{formatDate(validationHistoryEntries[0]?.timestamp || null)}</span>
            </div>
            <div className="audit-overview-stat">
              <span className="audit-overview-stat-label">Approval events</span>
              <strong>{formatRelativeCount(approvalHistoryEntries.length, 'event')}</strong>
              <span>{formatDate(approvalHistoryEntries[0]?.timestamp || null)}</span>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'rules' && (
        <AuditTimelineSection
          sectionKey="rules"
          title="Rule history"
          description="Immutable rule lifecycle changes and approval-linked state transitions."
          countLabel={formatRelativeCount(ruleHistoryEntries.length, 'event')}
          latestLabel={`Latest: ${formatDate(ruleHistoryEntries[0]?.timestamp || null)}`}
          loading={ruleHistoryLoading}
          error={ruleHistoryError}
          entries={ruleHistoryEntries}
          emptyMessage={selectedRuleId ? `No rule history found for ${selectedRule?.name || selectedRuleId}.` : 'Choose a rule to view its history.'}
          selector={
            <AppSelect
              id="audit-rule-selector"
              label="Rule"
              value={selectedRuleId}
              placeholderLabel="Select a rule"
              options={ruleOptions}
              onChange={(value) => setSelectedRuleId(value)}
            />
          }
          onRefresh={refreshAll}
        />
      )}

      {activeTab === 'data-definition' && (
        <AuditTimelineSection
          sectionKey="data-definition"
          title="Data-definition history"
          description="Immutable request and audit events for generated data-definition tasks."
          countLabel={formatRelativeCount(dataDefinitionHistoryEntries.length, 'event')}
          latestLabel={`Latest: ${formatDate(dataDefinitionHistoryEntries[0]?.timestamp || null)}`}
          loading={dataDefinitionRequestsLoading || dataDefinitionHistoryLoading}
          error={dataDefinitionRequestsError || dataDefinitionHistoryError}
          entries={dataDefinitionHistoryEntries}
          emptyMessage={selectedDataDefinitionRequestId ? `No data-definition history found for ${selectedDataDefinitionRequest?.requestId || selectedDataDefinitionRequestId}.` : 'Choose a data-definition request to view its history.'}
          selector={
            <div className="audit-section-selectors">
              <AppSelect
                id="audit-definition-request-selector"
                label="Request"
                value={selectedDataDefinitionRequestId}
                placeholderLabel="Select a request"
                options={dataDefinitionRequestOptions}
                onChange={(value) => setSelectedDataDefinitionRequestId(value)}
              />
            </div>
          }
          onRefresh={refreshAll}
        />
      )}

      {activeTab === 'validation' && (
        <AuditTimelineSection
          sectionKey="validation"
          title="Validation history"
          description="Run state changes for validation work that proves controls, not just outcome summaries."
          countLabel={formatRelativeCount(validationHistoryEntries.length, 'event')}
          latestLabel={`Latest: ${formatDate(validationHistoryEntries[0]?.timestamp || null)}`}
          loading={validationRunsLoading || validationHistoryLoading}
          error={validationRunsError || validationHistoryError}
          entries={validationHistoryEntries}
          emptyMessage={selectedValidationRunId ? `No validation history found for ${selectedValidationRun?.id || selectedValidationRunId}.` : 'Choose a validation run to view its history.'}
          selector={
            <AppSelect
              id="audit-validation-run-selector"
              label="Validation run"
              value={selectedValidationRunId}
              placeholderLabel="Select a validation run"
              options={validationRunOptions}
              onChange={(value) => setSelectedValidationRunId(value)}
            />
          }
          onRefresh={refreshAll}
        />
      )}

      {activeTab === 'approvals' && (
        <AuditTimelineSection
          sectionKey="approvals"
          title="Approval history"
          description="Audit events for approval actions, comments, and review transitions."
          countLabel={formatRelativeCount(approvalHistoryEntries.length, 'event')}
          latestLabel={`Latest: ${formatDate(approvalHistoryEntries[0]?.timestamp || null)}`}
          loading={approvalHistoryLoading}
          error={approvalHistoryError}
          entries={approvalHistoryEntries}
          emptyMessage="No approval audit events found yet."
          onRefresh={refreshAll}
        />
      )}

      {activeTab === 'versions' && <AuditCompilerVersions showHeader={false} />}
    </div>
  )
}

export default AuditTrail
