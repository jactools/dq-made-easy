import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth, useSettings } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { snakeToCamel } from '../utils/caseConverters'
import { AppBanner, AppBadge, AppButton, AppCard, AppCardContent, AppEmptyState, AppInput, AppModal, AppPanel, AppSelect, AppStack, type AppBadgeTone, type AppSelectOption } from './app-primitives'
import { navigateFromDashboardCard } from '../utils/dashboardNavigation'
import './ExecutionResultExplorer.css'

interface ExplorerFilters {
  datasetId: string
  owner: string
  domain: string
  severity: string
  status: string
  search: string
  lookbackAmount: string
  lookbackUnit: 'hours' | 'days'
}

interface ExecutionRunSummaryRow {
  id: string
  ruleName?: string | null
  owner?: string | null
  domain?: string | null
  severity?: string | null
  dataObjectNames?: string[]
  resolvedDataDeliveryId?: string | null
  correlationId?: string | null
  requestedBy?: string | null
  engineTarget?: string | null
  executionShape?: string | null
  status?: string | null
  failedRecordCount?: number | null
  submittedAt?: string | null
  startedAt?: string | null
  completedAt?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

interface ExecutionRunProgressView {
  percent?: number | null
  label?: string | null
  completedSteps?: number | null
  totalSteps?: number | null
  source?: string | null
  updatedAt?: string | null
}

interface ExecutionRunTraceabilityView {
  ruleVersionId?: string | null
  gxSuiteId?: string | null
  gxSuiteVersion?: number | null
  dataObjectVersionId?: string | null
}

interface ExecutionRunContractView {
  engineType?: string | null
  engineTarget?: string | null
  executionShape?: string | null
  traceability?: ExecutionRunTraceabilityView | null
}

interface ExecutionRunStatusHistoryView {
  id?: string | null
  fromStatus?: string | null
  toStatus?: string | null
  changedBy?: string | null
  changedAt?: string | null
  reason?: string | null
}

interface ExecutionRunDetailView {
  id: string
  suiteId?: string | null
  suiteVersion?: number | null
  ruleId?: string | null
  runPlanId?: string | null
  correlationId?: string | null
  requestedBy?: string | null
  engineTarget?: string | null
  executionShape?: string | null
  status?: string | null
  submittedAt?: string | null
  startedAt?: string | null
  completedAt?: string | null
  createdAt?: string | null
  updatedAt?: string | null
  resolvedDataDeliveryId?: string | null
  executionProgress?: ExecutionRunProgressView | null
  executionContract?: ExecutionRunContractView | null
  handoffPayload?: Record<string, unknown> | null
  statusHistory?: ExecutionRunStatusHistoryView[]
}

interface ExecutionResultExplorerProps {
  onNavigate?: (destination: string) => void
}

const DEFAULT_FILTERS: ExplorerFilters = {
  datasetId: '',
  owner: '',
  domain: '',
  severity: '',
  status: '',
  search: '',
  lookbackAmount: '24',
  lookbackUnit: 'hours',
}

const STATUS_OPTIONS: AppSelectOption[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
]

const LOOKBACK_UNIT_OPTIONS: AppSelectOption[] = [
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
]

const SEVERITY_OPTIONS: AppSelectOption[] = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
]

const humanizeLabel = (value: string): string => {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

const formatDateTime = (value?: string | null): string => {
  if (!value) {
    return 'Unknown'
  }

  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

const getStatusTone = (value?: string | null): AppBadgeTone => {
  switch (String(value || '').trim()) {
    case 'succeeded':
      return 'success'
    case 'running':
    case 'pending':
      return 'warning'
    case 'failed':
      return 'error'
    case 'cancelled':
      return 'neutral'
    default:
      return 'info'
  }
}

const getSeverityTone = (value?: string | null): AppBadgeTone => {
  switch (String(value || '').trim()) {
    case 'critical':
      return 'error'
    case 'high':
      return 'warning'
    case 'medium':
      return 'info'
    case 'low':
      return 'success'
    default:
      return 'neutral'
  }
}

const buildRequestHeaders = (): Record<string, string> => {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const appendParam = (params: URLSearchParams, key: string, value: string): void => {
  const normalized = String(value || '').trim()
  if (normalized) {
    params.set(key, normalized)
  }
}

const formatFallback = (value: string | null | undefined, fallback: string): string => {
  const normalized = String(value || '').trim()
  return normalized || fallback
}

const formatOptionalNumber = (value: number | null | undefined): string => {
  return value === null || value === undefined || Number.isNaN(Number(value)) ? 'Unavailable' : String(value)
}

const formatOwnershipLabel = (owner?: string | null, domain?: string | null): string => {
  const parts = [owner, domain].map((value) => String(value || '').trim()).filter(Boolean)
  return parts.length > 0 ? parts.join(' / ') : 'Unspecified'
}

const renderMetadataItem = (label: string, value: React.ReactNode, wide = false): React.ReactNode => (
  <div className={`execution-run-details-item${wide ? ' execution-run-details-item--wide' : ''}`}>
    <dt>{label}</dt>
    <dd>{value}</dd>
  </div>
)

const ExecutionRunDetailsModal: React.FC<{
  isOpen: boolean
  summary: ExecutionRunSummaryRow | null
  run: ExecutionRunDetailView | null
  loading: boolean
  error: string | null
  onClose: () => void
}> = ({ isOpen, summary, run, loading, error, onClose }) => {
  const title = summary ? `Result drilldown: ${summary.ruleName || summary.id}` : 'Result drilldown'
  const executionContract = run?.executionContract
  const traceability = executionContract?.traceability
  const historyRows = Array.isArray(run?.statusHistory) ? run.statusHistory.slice(0, 4) : []

  return (
    <AppModal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      titleAs="h3"
      size="lg"
      bodyClassName="execution-run-details-modal__body"
      footer={<AppButton variant="secondary" onClick={onClose}>Close</AppButton>}
    >
      <AppStack gap="lg">
        <AppBanner variant="info" className="execution-run-details-banner">
          Metadata only. Raw result payloads and data previews are not shown in this drilldown.
        </AppBanner>

        {loading && (
          <AppPanel title="Loading run metadata" titleAs="h4">
            Fetching persisted execution metadata for this run.
          </AppPanel>
        )}

        {!loading && error && (
          <AppBanner variant="warning">
            {error}
          </AppBanner>
        )}

        {!loading && !error && summary && (
          <>
            <AppPanel title="Run overview" titleAs="h4">
              <dl className="execution-run-details-grid">
                {renderMetadataItem('Run ID', summary.id)}
                {renderMetadataItem('Rule', summary.ruleName || 'Unspecified rule')}
                {renderMetadataItem('Ownership', formatOwnershipLabel(summary.owner, summary.domain))}
                {renderMetadataItem('Severity', summary.severity ? humanizeLabel(summary.severity) : 'Unspecified')}
                {renderMetadataItem('Status', summary.status ? humanizeLabel(summary.status) : 'Unknown')}
                {renderMetadataItem('Failed records', formatOptionalNumber(summary.failedRecordCount))}
              </dl>
            </AppPanel>

            <AppPanel title="Execution context" titleAs="h4">
              <dl className="execution-run-details-grid">
                {renderMetadataItem('Dataset', Array.isArray(summary.dataObjectNames) && summary.dataObjectNames.length > 0 ? summary.dataObjectNames.join(', ') : 'Unavailable', true)}
                {renderMetadataItem('Data delivery', formatFallback(summary.resolvedDataDeliveryId, 'Unavailable'))}
                {renderMetadataItem('Run plan', formatFallback(summary.runPlanId, 'Unavailable'))}
                {renderMetadataItem('Correlation', formatFallback(summary.correlationId, 'Unavailable'))}
                {renderMetadataItem('Requested by', formatFallback(summary.requestedBy, 'Unavailable'))}
                {renderMetadataItem('Engine target', formatFallback(summary.engineTarget, 'Unavailable'))}
                {renderMetadataItem('Execution shape', formatFallback(summary.executionShape, 'Unavailable'))}
                {renderMetadataItem('Suite', formatFallback(summary.suiteId, 'Unavailable'))}
              </dl>
            </AppPanel>

            <AppPanel title="Lifecycle" titleAs="h4">
              <dl className="execution-run-details-grid">
                {renderMetadataItem('Submitted at', formatFallback(summary.submittedAt, 'Unavailable'))}
                {renderMetadataItem('Started at', formatFallback(summary.startedAt, 'Unavailable'))}
                {renderMetadataItem('Completed at', formatFallback(summary.completedAt, 'Unavailable'))}
                {renderMetadataItem('Created at', formatFallback(summary.createdAt, 'Unavailable'))}
                {renderMetadataItem('Updated at', formatFallback(summary.updatedAt, 'Unavailable'))}
                {renderMetadataItem('Workspace context', formatFallback(summary.domain, 'Unavailable'))}
              </dl>
            </AppPanel>
          </>
        )}

        {!loading && !error && run && (
          <>
            {run.executionProgress && (
              <AppPanel title="Execution progress" titleAs="h4">
                <dl className="execution-run-details-grid">
                  {renderMetadataItem('Progress', `${formatOptionalNumber(run.executionProgress.percent)}%`)}
                  {renderMetadataItem('Label', formatFallback(run.executionProgress.label, 'Unavailable'))}
                  {renderMetadataItem('Completed steps', formatOptionalNumber(run.executionProgress.completedSteps))}
                  {renderMetadataItem('Total steps', formatOptionalNumber(run.executionProgress.totalSteps))}
                  {renderMetadataItem('Source', formatFallback(run.executionProgress.source, 'Unavailable'))}
                  {renderMetadataItem('Updated at', formatFallback(run.executionProgress.updatedAt, 'Unavailable'))}
                </dl>
              </AppPanel>
            )}

            <AppPanel title="Contract pointers" titleAs="h4">
              <dl className="execution-run-details-grid">
                {renderMetadataItem('Engine type', formatFallback(executionContract?.engineType, 'Unavailable'))}
                {renderMetadataItem('Engine target', formatFallback(executionContract?.engineTarget, 'Unavailable'))}
                {renderMetadataItem('Execution shape', formatFallback(executionContract?.executionShape, 'Unavailable'))}
                {renderMetadataItem('Rule version', formatFallback(traceability?.ruleVersionId, 'Unavailable'))}
                {renderMetadataItem('GX suite', formatFallback(traceability?.gxSuiteId, 'Unavailable'))}
                {renderMetadataItem('GX suite version', formatOptionalNumber(traceability?.gxSuiteVersion))}
                {renderMetadataItem('Data object version', formatFallback(traceability?.dataObjectVersionId, 'Unavailable'))}
              </dl>
            </AppPanel>

            {historyRows.length > 0 && (
              <AppPanel title="Recent lifecycle changes" titleAs="h4">
                <div className="execution-run-details-history">
                  {historyRows.map((item) => (
                    <div key={String(item.id || `${item.toStatus}-${item.changedAt}`)} className="execution-run-details-history-row">
                      <div className="execution-run-details-history-main">
                        <strong>{formatFallback(item.toStatus, 'Unknown status')}</strong>
                        <span>{formatFallback(item.changedAt, 'Unknown time')}</span>
                      </div>
                      <div className="execution-run-details-history-meta">
                        {item.fromStatus ? <span>from {item.fromStatus}</span> : null}
                        {item.changedBy ? <span>by {item.changedBy}</span> : null}
                        {item.reason ? <span>{item.reason}</span> : null}
                      </div>
                    </div>
                  ))}
                </div>
              </AppPanel>
            )}
          </>
        )}
      </AppStack>
    </AppModal>
  )
}

export const ExecutionResultExplorer: React.FC<ExecutionResultExplorerProps> = ({ onNavigate }) => {
  const { currentWorkspaceId } = useAuth()
  const settings = useSettings()
  const [draftFilters, setDraftFilters] = useState<ExplorerFilters>(DEFAULT_FILTERS)
  const [submittedFilters, setSubmittedFilters] = useState<ExplorerFilters>(DEFAULT_FILTERS)
  const [runs, setRuns] = useState<ExecutionRunSummaryRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedRun, setSelectedRun] = useState<ExecutionRunSummaryRow | null>(null)
  const [selectedRunDetail, setSelectedRunDetail] = useState<ExecutionRunDetailView | null>(null)
  const [selectedRunLoading, setSelectedRunLoading] = useState(false)
  const [selectedRunError, setSelectedRunError] = useState<string | null>(null)

  const loadRuns = useCallback(async (filters: ExplorerFilters) => {
    const workspaceId = String(currentWorkspaceId || '').trim()
    if (!workspaceId) {
      setRuns([])
      setError('Select an active workspace to explore execution results.')
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)

    try {
      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const params = new URLSearchParams()
      params.set('workspaceId', workspaceId)
      params.set('lookbackAmount', String(Math.max(1, Number(filters.lookbackAmount) || 24)))
      params.set('lookbackUnit', filters.lookbackUnit)
      params.set('limit', '50')
      appendParam(params, 'datasetId', filters.datasetId)
      appendParam(params, 'owner', filters.owner)
      appendParam(params, 'domain', filters.domain)
      appendParam(params, 'severity', filters.severity)
      appendParam(params, 'status', filters.status)
      appendParam(params, 'search', filters.search)

      const response = await fetch(`${apiBase}/runs?${params.toString()}`, {
        headers: buildRequestHeaders(),
      })

      if (!response.ok) {
        throw new Error(`Unable to load execution results (${response.status}).`)
      }

      const payload = snakeToCamel<ExecutionRunSummaryRow[]>(await response.json())
      const nextRuns = Array.isArray(payload)
        ? payload.slice().sort((left, right) => new Date(String(right.submittedAt || 0)).getTime() - new Date(String(left.submittedAt || 0)).getTime())
        : []
      setRuns(nextRuns)
    } catch (loadError) {
      setRuns([])
      setError(loadError instanceof Error ? loadError.message : 'Unable to load execution results.')
    } finally {
      setLoading(false)
    }
  }, [currentWorkspaceId, settings.applicationSettings?.apiBaseUrl])

  const loadRunDetails = useCallback(async (runId: string) => {
    const workspaceId = String(currentWorkspaceId || '').trim()
    if (!workspaceId) {
      setSelectedRunDetail(null)
      setSelectedRunError('Select an active workspace to drill into run metadata.')
      setSelectedRunLoading(false)
      return
    }

    setSelectedRunLoading(true)
    setSelectedRunError(null)

    try {
      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const response = await fetch(`${apiBase}/runs/${encodeURIComponent(runId)}`, {
        headers: buildRequestHeaders(),
      })

      if (!response.ok) {
        throw new Error(`Unable to load run metadata (${response.status}).`)
      }

      const payload = snakeToCamel<ExecutionRunDetailView>(await response.json())
      setSelectedRunDetail(payload)
    } catch (loadError) {
      setSelectedRunDetail(null)
      setSelectedRunError(loadError instanceof Error ? loadError.message : 'Unable to load run metadata.')
    } finally {
      setSelectedRunLoading(false)
    }
  }, [currentWorkspaceId, settings.applicationSettings?.apiBaseUrl])

  useEffect(() => {
    void loadRuns(submittedFilters)
  }, [loadRuns, submittedFilters, currentWorkspaceId])

  useEffect(() => {
    if (!selectedRun) {
      setSelectedRunDetail(null)
      setSelectedRunError(null)
      setSelectedRunLoading(false)
      return
    }

    void loadRunDetails(selectedRun.id)
  }, [loadRunDetails, selectedRun])

  const statusCounts = useMemo(() => {
    const counts = runs.reduce<Record<string, number>>((accumulator, run) => {
      const status = String(run.status || '').trim() || 'unknown'
      accumulator[status] = (accumulator[status] || 0) + 1
      return accumulator
    }, {})

    return {
      total: runs.length,
      pending: counts.pending || 0,
      running: counts.running || 0,
      succeeded: counts.succeeded || 0,
      failed: counts.failed || 0,
    }
  }, [runs])

  const summaryCards = useMemo(() => {
    const severityCounts = runs.reduce<Record<string, number>>((accumulator, run) => {
      const severity = String(run.severity || '').trim() || 'unspecified'
      accumulator[severity] = (accumulator[severity] || 0) + 1
      return accumulator
    }, {})

    const ownerCounts = runs.reduce<Record<string, number>>((accumulator, run) => {
      const owner = String(run.owner || '').trim() || 'Unspecified'
      accumulator[owner] = (accumulator[owner] || 0) + 1
      return accumulator
    }, {})

    const domainCounts = runs.reduce<Record<string, number>>((accumulator, run) => {
      const domain = String(run.domain || '').trim() || 'Unspecified'
      accumulator[domain] = (accumulator[domain] || 0) + 1
      return accumulator
    }, {})

    const mostImpactedOwner = Object.entries(ownerCounts).sort((left, right) => right[1] - left[1])[0]?.[0] || 'Unspecified'
    const mostImpactedDomain = Object.entries(domainCounts).sort((left, right) => right[1] - left[1])[0]?.[0] || 'Unspecified'
    const highSeverityCount = (severityCounts.high || 0) + (severityCounts.critical || 0)
    const failedRunCount = statusCounts.failed

    return [
      {
        id: 'monitoring',
        eyebrow: 'Next action',
        title: 'Triage failed runs',
        value: failedRunCount,
        description: failedRunCount > 0
          ? 'Open execution monitoring to inspect the failed-run queue for this workspace.'
          : 'No failed runs are currently matched by the active filters.',
        tone: failedRunCount > 0 ? 'error' : 'success',
        actionLabel: 'Open monitoring',
        onAction: (onNavigate?: (destination: string) => void) => {
          navigateFromDashboardCard('failed-validation-runs', onNavigate)
        },
      },
      {
        id: 'rule-quality',
        eyebrow: 'Ownership',
        title: 'Most impacted owner',
        value: mostImpactedOwner,
        description: 'Open the owning rules workflow to review the rules assigned to this owner.',
        tone: 'info',
        actionLabel: 'Open rules',
        onAction: (onNavigate?: (destination: string) => void) => {
          onNavigate?.('rules-all')
        },
      },
      {
        id: 'governance',
        eyebrow: 'Escalation',
        title: 'High-severity results',
        value: highSeverityCount,
        description: 'Open governance review to inspect the results that are most likely to require steward attention.',
        tone: highSeverityCount > 0 ? 'warning' : 'success',
        actionLabel: 'Open governance',
        onAction: (onNavigate?: (destination: string) => void) => {
          onNavigate?.('approvals-governance')
        },
      },
      {
        id: 'domain-focus',
        eyebrow: 'Scope',
        title: 'Most impacted domain',
        value: mostImpactedDomain,
        description: 'Open rule quality follow-up to continue steward-driven investigation from this result set.',
        tone: 'info',
        actionLabel: 'Open follow-up',
        onAction: (onNavigate?: (destination: string) => void) => {
          onNavigate?.('rule-quality-suggestions')
        },
      },
    ]
  }, [runs, statusCounts.failed])

  const currentWorkspaceLabel = String(currentWorkspaceId || '').trim() || 'an active workspace'
  const filteredFilterSummary = useMemo(() => {
    const parts: string[] = []
    if (submittedFilters.datasetId.trim()) parts.push(`dataset ${submittedFilters.datasetId.trim()}`)
    if (submittedFilters.owner.trim()) parts.push(`owner ${submittedFilters.owner.trim()}`)
    if (submittedFilters.domain.trim()) parts.push(`domain ${submittedFilters.domain.trim()}`)
    if (submittedFilters.severity.trim()) parts.push(`severity ${submittedFilters.severity.trim()}`)
    if (submittedFilters.status.trim()) parts.push(`status ${submittedFilters.status.trim()}`)
    if (submittedFilters.search.trim()) parts.push(`search ${submittedFilters.search.trim()}`)
    parts.push(`${submittedFilters.lookbackAmount} ${submittedFilters.lookbackUnit}`)
    return parts.join(' · ')
  }, [submittedFilters])

  const handleApplyFilters = useCallback((event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmittedFilters({ ...draftFilters })
  }, [draftFilters])

  const handleResetFilters = useCallback(() => {
    setDraftFilters({ ...DEFAULT_FILTERS })
    setSubmittedFilters({ ...DEFAULT_FILTERS })
  }, [])

  const openRunDetails = useCallback((run: ExecutionRunSummaryRow) => {
    setSelectedRun(run)
    setSelectedRunDetail(null)
    setSelectedRunError(null)
  }, [])

  const closeRunDetails = useCallback(() => {
    setSelectedRun(null)
    setSelectedRunDetail(null)
    setSelectedRunError(null)
    setSelectedRunLoading(false)
  }, [])

  if (!currentWorkspaceId) {
    return (
      <AppEmptyState
        title="Select a workspace"
        description="Result exploration loads execution runs for the active workspace and pushes dataset, ownership, severity, status, and timeframe filters to the backend."
      />
    )
  }

  return (
    <section className="test-results-section">
      <div className="execution-run-summary-grid" aria-label="Steward summary cards">
        {summaryCards.map((card) => (
          <AppCard key={card.id} className="execution-run-summary-card">
            <AppCardContent className="execution-run-summary-card__content">
              <div className="execution-run-summary-card__body">
                <span className="execution-run-summary-card__eyebrow">{card.eyebrow}</span>
                <h4>{card.title}</h4>
                <strong className={`execution-run-summary-card__value execution-run-summary-card__value--${card.tone}`}>{card.value}</strong>
                <p>{card.description}</p>
              </div>
              <div className="execution-run-summary-card__actions">
                <AppButton
                  type="button"
                  variant="secondary"
                  onClick={() => card.onAction?.(onNavigate)}
                >
                  {card.actionLabel}
                </AppButton>
              </div>
            </AppCardContent>
          </AppCard>
        ))}
      </div>

      <div className="latest-test-summary">
        <div className="latest-test-summary-header">
          <div>
            <p className="latest-test-summary-kicker">Result explorer</p>
            <h3>Filtered execution runs</h3>
            <p>
              Browse the backend-owned execution history for {currentWorkspaceLabel}.
              {' '}
              The server applies dataset, owner, domain, severity, status, and timeframe filters before the UI renders results.
            </p>
          </div>
          <AppButton onClick={() => setSubmittedFilters({ ...draftFilters })} disabled={loading}>
            Refresh
          </AppButton>
        </div>
        <div className="latest-test-summary-grid">
          <div className="latest-test-summary-metric">
            <span>Total runs</span>
            <strong>{statusCounts.total}</strong>
            <p>Runs matching the active browse filters.</p>
          </div>
          <div className="latest-test-summary-metric">
            <span>Pending</span>
            <strong>{statusCounts.pending}</strong>
            <p>Queued runs waiting for execution.</p>
          </div>
          <div className="latest-test-summary-metric">
            <span>Running</span>
            <strong>{statusCounts.running}</strong>
            <p>Runs still in progress.</p>
          </div>
          <div className="latest-test-summary-metric">
            <span>Failed</span>
            <strong>{statusCounts.failed}</strong>
            <p>Runs that need investigation.</p>
          </div>
        </div>
      </div>

      <form className="test-results-filters" onSubmit={handleApplyFilters}>
        <div className="filters-left">
          <AppInput
            id="result-explorer-dataset-id"
            label="Dataset ID"
            value={draftFilters.datasetId}
            onChange={(event) => setDraftFilters((current) => ({ ...current, datasetId: event.target.value }))}
            placeholder="ds_456"
            className="reports-native-field"
            fieldClassName="filter-group"
          />
          <AppInput
            id="result-explorer-owner"
            label="Owner"
            value={draftFilters.owner}
            onChange={(event) => setDraftFilters((current) => ({ ...current, owner: event.target.value }))}
            placeholder="data-platform"
            className="reports-native-field"
            fieldClassName="filter-group"
          />
          <AppInput
            id="result-explorer-domain"
            label="Domain"
            value={draftFilters.domain}
            onChange={(event) => setDraftFilters((current) => ({ ...current, domain: event.target.value }))}
            placeholder="retail-banking"
            className="reports-native-field"
            fieldClassName="filter-group"
          />
        </div>
        <div className="filters-right">
          <AppSelect
            id="result-explorer-severity"
            label="Severity"
            value={draftFilters.severity}
            onChange={(value) => setDraftFilters((current) => ({ ...current, severity: value }))}
            options={SEVERITY_OPTIONS}
            placeholderLabel="Any severity"
            className="reports-native-field"
            fieldClassName="filter-group reports-select-wrapper"
          />
          <AppSelect
            id="result-explorer-status"
            label="Status"
            value={draftFilters.status}
            onChange={(value) => setDraftFilters((current) => ({ ...current, status: value }))}
            options={STATUS_OPTIONS}
            placeholderLabel="Any status"
            className="reports-native-field"
            fieldClassName="filter-group reports-select-wrapper"
          />
          <AppInput
            id="result-explorer-search"
            label="Search"
            value={draftFilters.search}
            onChange={(event) => setDraftFilters((current) => ({ ...current, search: event.target.value }))}
            placeholder="rule or run text"
            className="reports-native-field"
            fieldClassName="filter-group"
          />
          <AppInput
            id="result-explorer-lookback-amount"
            label="Lookback"
            type="number"
            min={1}
            max={720}
            value={draftFilters.lookbackAmount}
            onChange={(event) => setDraftFilters((current) => ({ ...current, lookbackAmount: event.target.value }))}
            className="reports-native-field"
            fieldClassName="filter-group"
          />
          <AppSelect
            id="result-explorer-lookback-unit"
            label="Window"
            value={draftFilters.lookbackUnit}
            onChange={(value) => setDraftFilters((current) => ({ ...current, lookbackUnit: value as ExplorerFilters['lookbackUnit'] }))}
            options={LOOKBACK_UNIT_OPTIONS}
            className="reports-native-field"
            fieldClassName="filter-group reports-select-wrapper"
          />
          <div className="filter-group filter-group-button">
            <label>Actions</label>
            <AppButton type="submit" disabled={loading}>
              Apply filters
            </AppButton>
            <AppButton type="button" variant="secondary" onClick={handleResetFilters} disabled={loading}>
              Reset
            </AppButton>
          </div>
        </div>
      </form>

      {loading && (
        <AppEmptyState
          title="Loading execution results"
          description={`Fetching filtered runs for ${currentWorkspaceLabel} from the backend.`}
        />
      )}

      {!loading && error && (
        <AppEmptyState
          title="Execution results unavailable"
          description={error}
          actions={
            <AppButton onClick={() => setSubmittedFilters({ ...draftFilters })}>
              Retry
            </AppButton>
          }
        />
      )}

      {!loading && !error && runs.length === 0 && (
        <AppEmptyState
          title="No execution runs match these filters"
          description={`Try broadening the search or time window. Active filters: ${filteredFilterSummary}.`}
        />
      )}

      {!loading && !error && runs.length > 0 && (
        <div className="results-table" aria-label="Filtered execution runs">
          <div className="table-header">
            <span>Run</span>
            <span>Rule</span>
            <span>Dataset</span>
            <span>Ownership</span>
            <span>Severity</span>
            <span>Status</span>
            <span>Failed</span>
          </div>
          <div className="table-group">
            {runs.map((run, index) => {
              const datasetLabel = (Array.isArray(run.dataObjectNames) && run.dataObjectNames.length > 0)
                ? run.dataObjectNames.join(', ')
                : 'Unknown dataset'
              const ownershipLabel = [run.owner, run.domain].filter((value): value is string => Boolean(String(value || '').trim())).join(' / ') || 'Unspecified'
              const failedRecordCount = Number(run.failedRecordCount || 0)

              return (
                <div key={run.id} className={`table-row ${index === 0 ? 'table-row-latest' : ''}`}>
                  <div className="column run-name">
                    <div className="target-stack">
                      <strong>{run.id}</strong>
                      <span>{formatDateTime(run.submittedAt)}</span>
                      {run.correlationId ? <span>{run.correlationId}</span> : null}
                      <AppButton
                        type="button"
                        variant="tertiary"
                        className="execution-run-details-action"
                        onClick={() => openRunDetails(run)}
                      >
                        Open details
                      </AppButton>
                    </div>
                  </div>
                  <div className="column rule-name">
                    <div className="target-stack">
                      <strong>{run.ruleName || 'Unspecified rule'}</strong>
                      <span>{run.requestedBy ? `Requested by ${run.requestedBy}` : 'Requester unavailable'}</span>
                    </div>
                  </div>
                  <div className="column target">
                    <div className="target-stack">
                      <strong>{datasetLabel}</strong>
                      <span>{run.resolvedDataDeliveryId || 'Delivery unavailable'}</span>
                    </div>
                  </div>
                  <div className="column">
                    <div className="target-stack">
                      <strong>{ownershipLabel}</strong>
                      <span>{run.engineTarget ? `Engine ${run.engineTarget}` : 'Engine unavailable'}</span>
                    </div>
                  </div>
                  <div className="column">
                    <AppBadge tone={getSeverityTone(run.severity)}>
                      {run.severity ? humanizeLabel(run.severity) : 'Unspecified'}
                    </AppBadge>
                  </div>
                  <div className="column">
                    <AppBadge tone={getStatusTone(run.status)}>
                      {run.status ? humanizeLabel(run.status) : 'Unknown'}
                    </AppBadge>
                  </div>
                  <div className="column">
                    <div className="target-stack">
                      <strong>{failedRecordCount}</strong>
                      <span>{run.executionShape ? humanizeLabel(run.executionShape) : 'Shape unavailable'}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <ExecutionRunDetailsModal
        isOpen={Boolean(selectedRun)}
        summary={selectedRun}
        run={selectedRunDetail}
        loading={selectedRunLoading}
        error={selectedRunError}
        onClose={closeRunDetails}
      />
    </section>
  )
}
