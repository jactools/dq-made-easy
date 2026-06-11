import React from 'react'
import { getAuthToken } from '../contexts/AuthContext'
import { useAuth, useSettings } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import { RuleDetailsModal } from './RuleDetailsModal'
import { Button } from './Button'

type UiRuleStatus = 'draft' | 'testing' | 'tested' | 'pending-approval' | 'approved' | 'activated' | 'deactivated' | 'rejected'

interface RuleSearchRow {
  id: string
  name: string
  active?: boolean
  last_approval_status?: string | null
  total_versions?: number | null
}

const formatDateTime = (value: string | null): string => {
  if (!value) return 'N/A'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'N/A'
  return parsed.toLocaleString()
}

const statusLabel = (status: UiRuleStatus): string => {
  switch (status) {
    case 'draft':
      return 'Draft'
    case 'testing':
      return 'Testing'
    case 'tested':
      return 'Tested'
    case 'pending-approval':
      return 'Pending approval'
    case 'approved':
      return 'Approved'
    case 'activated':
      return 'Activated'
    case 'deactivated':
      return 'Deactivated'
    case 'rejected':
      return 'Rejected'
    default:
      return String(status)
  }
}

interface RuleSuggestion {
  rule: RuleSearchRow
  conciseOverview: string
  detailedOverview: string
  proofOverview: string
  testsOverview: string
  approvalOverview: string
  testTimestamp: string | null
  status: UiRuleStatus
}

export const Toolbar: React.FC = () => {
  const auth = useAuth()
  const settings = useSettings()
  const [query, setQuery] = React.useState('')
  const [isOpen, setIsOpen] = React.useState(false)
  const [expandedSuggestionId, setExpandedSuggestionId] = React.useState<string | null>(null)
  const [suggestions, setSuggestions] = React.useState<RuleSuggestion[]>([])
  const [searchLoading, setSearchLoading] = React.useState(false)
  const [searchError, setSearchError] = React.useState<string | null>(null)
  const [detailsModalOpen, setDetailsModalOpen] = React.useState(false)
  const [detailsModalTarget, setDetailsModalTarget] = React.useState<RuleSuggestion | null>(null)
  const searchContainerRef = React.useRef<HTMLDivElement | null>(null)
  const debounceTimerRef = React.useRef<number | null>(null)

  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!searchContainerRef.current) return
      if (!searchContainerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const apiBase = React.useMemo(
    () => toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl),
    [settings.applicationSettings?.apiBaseUrl]
  )
  const debounceMs = settings.applicationSettings?.debounceMs ?? 300

  React.useEffect(() => {
    const trimmedQuery = query.trim()

    if (debounceTimerRef.current) {
      window.clearTimeout(debounceTimerRef.current)
      debounceTimerRef.current = null
    }

    if (!isOpen) {
      return
    }

    if (trimmedQuery.length < 3) {
      setSuggestions([])
      setSearchLoading(false)
      setSearchError(null)
      return
    }

    debounceTimerRef.current = window.setTimeout(() => {
      const runSearch = async () => {
        const token = getAuthToken()
        if (!token) {
          setSuggestions([])
          setSearchError('Sign in to search rules.')
          return
        }

        const headers: HeadersInit = { Authorization: `Bearer ${token}` }
        const workspace = String(auth.currentWorkspaceId || '').trim()
        const params = new URLSearchParams({ page: '1', limit: '5', q: trimmedQuery })
        if (workspace) {
          params.set('workspace', workspace)
        }

        setSearchLoading(true)
        setSearchError(null)

        try {
          const listResponse = await fetch(`${apiBase}/rules?${params.toString()}`, { headers })
          if (!listResponse.ok) {
            throw new Error('Failed to search rules')
          }

          const body = await listResponse.json()
          const rows = Array.isArray(body?.data) ? body.data : []

          const proofPairs = await Promise.all(
            rows.map(async (row: RuleSearchRow) => {
              try {
                const proofResponse = await fetch(`${apiBase}/test-proofs/${encodeURIComponent(String(row.id || ''))}`, { headers })
                if (!proofResponse.ok) {
                  return [String(row.id), []] as const
                }
                const proofRows = await proofResponse.json()
                return [String(row.id), Array.isArray(proofRows) ? proofRows : []] as const
              } catch {
                return [String(row.id), []] as const
              }
            })
          )

          const proofsByRuleId = Object.fromEntries(proofPairs) as Record<string, any[]>

          const mapped = rows.map((row: RuleSearchRow): RuleSuggestion => {
            const versionNumber = Number(row.total_versions || 0) || 1
            const approvalStatus = String(row.last_approval_status || '').toLowerCase()

            const status: UiRuleStatus = row.active
              ? 'activated'
              : approvalStatus === 'deactivated'
              ? 'deactivated'
              : approvalStatus === 'approved'
              ? 'approved'
              : approvalStatus === 'pending'
              ? 'pending-approval'
              : approvalStatus === 'rejected'
              ? 'rejected'
              : 'draft'

            const approvalOverview =
              approvalStatus === 'approved'
                ? `Approved for V${versionNumber}`
                : approvalStatus === 'pending'
                ? `Pending approval for V${versionNumber}`
                : approvalStatus === 'rejected'
                ? `Rejected for V${versionNumber}`
                : `No approval submitted for V${versionNumber}`

            const latestProof = (proofsByRuleId[String(row.id)] || [])[0]
            const proofId = String(latestProof?.id || latestProof?.proofId || '').trim() || 'N/A'
            const coverage = Number(latestProof?.coverage || 0)
            const failuresFound = Number(latestProof?.failuresFound || 0)
            const recordsTestedCount = Number(latestProof?.recordsTestedCount || 0)
            const testStatus = String(latestProof?.status || '').trim()

            const testsOverview = latestProof
              ? `${testStatus.toUpperCase()} | DQ Score ${coverage}% | ${failuresFound} failures / ${recordsTestedCount} records`
              : 'No test execution recorded yet'

            const proofOverview = latestProof
              ? `Proof available (${proofId})`
              : 'No proof recorded yet'

            const conciseOverview = `${statusLabel(status)} | ${testsOverview} | ${approvalOverview}`
            const detailedOverview = `Version V${versionNumber} | ${approvalOverview} | ${proofOverview}`

            return {
              rule: row,
              status,
              conciseOverview,
              detailedOverview,
              proofOverview,
              testsOverview,
              approvalOverview,
              testTimestamp: latestProof?.testDate || null,
            }
          })

          setSuggestions(mapped)
        } catch {
          setSuggestions([])
          setSearchError('Search failed. Please try again.')
        } finally {
          setSearchLoading(false)
        }
      }

      void runSearch()
    }, debounceMs)

    return () => {
      if (debounceTimerRef.current) {
        window.clearTimeout(debounceTimerRef.current)
        debounceTimerRef.current = null
      }
    }
  }, [query, isOpen, apiBase, auth.currentWorkspaceId, debounceMs])

  const hasQuery = query.trim().length > 0
  const hasMinChars = query.trim().length >= 3

  const closeDetailsModal = () => {
    setDetailsModalOpen(false)
    setDetailsModalTarget(null)
  }

  const handleNewRuleClick = () => {
    if (typeof window === 'undefined') return
    window.dispatchEvent(new CustomEvent('dq-open-new-rule'))
  }

  const openDetailsModal = (suggestion: RuleSuggestion) => {
    setDetailsModalOpen(true)
    setDetailsModalTarget(suggestion)
  }

  return (
    <div className="toolbar">
      <div className="toolbar-content">
        <div className="toolbar-search-container" ref={searchContainerRef}>
          <input
            type="text"
            placeholder="Search rules by name, id, expression, description..."
            className="toolbar-search"
            aria-label="Search rules"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setIsOpen(true)
            }}
            onFocus={() => setIsOpen(true)}
          />

          {isOpen && hasQuery && (
            <div className="toolbar-search-suggestions" role="listbox" aria-label="Rule search suggestions">
              {!hasMinChars && (
                <div className="toolbar-search-empty">Type at least 3 characters to start searching.</div>
              )}

              {hasMinChars && searchLoading && (
                <div className="toolbar-search-empty">Searching rules...</div>
              )}

              {hasMinChars && searchError && (
                <div className="toolbar-search-empty toolbar-search-error">{searchError}</div>
              )}

              {hasMinChars && !searchLoading && !searchError && suggestions.length === 0 && (
                <div className="toolbar-search-empty">No matching rules found in the active workspace.</div>
              )}

              {hasMinChars && !searchLoading && !searchError && suggestions.map((suggestion) => {
                const isExpanded = expandedSuggestionId === suggestion.rule.id
                return (
                  <div key={suggestion.rule.id} className="toolbar-suggestion-card" role="option" aria-selected={isExpanded}>
                    <div className="toolbar-suggestion-top">
                      <div className="toolbar-suggestion-title-group">
                        <span className="toolbar-suggestion-title">{suggestion.rule.name}</span>
                        <span className="toolbar-suggestion-id">#{suggestion.rule.id}</span>
                      </div>
                      <button
                        type="button"
                        className="toolbar-suggestion-toggle"
                        onClick={() => setExpandedSuggestionId(isExpanded ? null : suggestion.rule.id)}
                      >
                        {isExpanded ? 'Hide details' : 'Show details'}
                      </button>
                    </div>

                    <div className="toolbar-suggestion-concise">{suggestion.conciseOverview}</div>

                    {isExpanded && (
                      <div className="toolbar-suggestion-detailed">
                        <div><strong>Status:</strong> {statusLabel(suggestion.status)}</div>
                        <div><strong>Tests:</strong> {suggestion.testsOverview}</div>
                        <div><strong>Proof:</strong> {suggestion.proofOverview}</div>
                        <div><strong>Approval:</strong> {suggestion.approvalOverview}</div>
                        <div><strong>Detailed overview:</strong> {suggestion.detailedOverview}</div>
                        <div><strong>Last tested:</strong> {formatDateTime(suggestion.testTimestamp)}</div>
                        <button
                          type="button"
                          className="toolbar-suggestion-full-link"
                          onClick={() => openDetailsModal(suggestion)}
                        >
                          View full details
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="toolbar-actions">
          <Button variant="primary" onClick={handleNewRuleClick}>
            New Rule
          </Button>
          <Button variant="tertiary">
            Export
          </Button>
        </div>
      </div>

      <RuleDetailsModal
        isOpen={detailsModalOpen}
        onClose={closeDetailsModal}
        ruleId={detailsModalTarget?.rule.id || null}
        ruleName={detailsModalTarget?.rule.name || null}
        statusText={detailsModalTarget ? statusLabel(detailsModalTarget.status) : null}
        approvalText={detailsModalTarget?.approvalOverview || null}
        versionHint={detailsModalTarget?.rule.total_versions || null}
      />
    </div>
  )
}
