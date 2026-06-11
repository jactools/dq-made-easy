import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth, useSettings } from '../../hooks/useContexts'
import { getAuthToken } from '../../contexts/AuthContext'
import { toApiGroupV1Base } from '../../config/api'
import { camelToSnake, snakeToCamel } from '../../utils/caseConverters'
import {
  consumeDashboardNavigationSelection,
  isDashboardBrowseStatus,
} from '../../utils/dashboardNavigation'
import { normalizeValidationUiText } from '../../utils/validationTerminology'
import { AppIcon, AppPageHeader, AppPageShell, AppSelect } from '../app-primitives'
import { GxSuiteScopePickerModal, type GxSuiteScopeSelection } from '../GxSuiteScopePickerModal'
import './features.css'
import './RuleExecutionMonitoring.css'

type GxExecutionStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled'
type GxExecutionShape = 'single_object' | 'join_pair' | 'grouped_scope'
type GxBrowseStatusFilter = GxExecutionStatus | 'all'
type GxSuiteStatus = 'active' | 'deprecated' | 'disabled'

interface GxSuiteEnvelope {
  suiteId: string
  suiteVersion: number
  artifactVersion: string
  assignmentScope: {
    dataObjectId: string | null
    datasetId: string | null
    dataProductId: string | null
  }
  resolvedExecutionScope: {
    dataObjectVersionIds: string[]
  }
  compiledFrom: {
    ruleIds: string[]
    compilerVersion: string
    generatedAt: string
  }
  executionContract?: {
    engineTarget: string
    executionShape: string
    traceability: {
      ruleId: string
      ruleVersionId: string
      gxSuiteId: string
      gxSuiteVersion: number
      dataObjectVersionId?: string | null
      sourceRuleExpression?: string | null
      compiledExpression?: string | null
      artifactKey?: string | null
    }
  } | null
}

interface GxScheduledDispatchHandoffView {
  runId: string
  suiteId: string
  suiteVersion: number
  correlationId: string
  requestedBy: string | null
  engineTarget: 'pyspark'
  executionShape: 'single_object' | 'join_pair'
  handoffStatus: 'accepted'
  handoffReady: boolean
  submittedAt: string
  dispatchMode: 'queued'
  executorTarget: 'dq-engine'
  queueKey: string
  queueMessageId: string
  scheduledAt: string
}

interface GxExecutionRunStatusHistoryView {
  id: string
  runId: string
  fromStatus: GxExecutionStatus | null
  toStatus: GxExecutionStatus
  changedBy: string | null
  changedAt: string
  reason: string | null
  details: Record<string, unknown> | null
}

interface GxExecutionContractTraceabilityView {
  ruleId: string
  ruleVersionId: string
  gxSuiteId: string
  gxSuiteVersion: number
  dataObjectVersionId: string | null
  sourceRuleExpression?: string | null
  compiledExpression?: string | null
  artifactKey?: string | null
}

interface GxArtifactSourceTargetView {
  dataObjectId: string
  dataObjectVersionId: string
  datasetId: string | null
  dataProductId: string | null
}

interface GxArtifactLandingZoneMaterializationView {
  landingZoneArtifactId: string
  landingZoneVersionId: string
  outputLocation: string
  joinType: 'inner' | 'left' | 'right' | 'full'
  joinKeys: string[]
  leftSource: GxArtifactSourceTargetView
  rightSource: GxArtifactSourceTargetView
}

interface MaterializationDeliverySummaryView {
  targetCount?: number | null
  dataDeliveryCount?: number | null
  totalRowCount?: number | null
  reusedExisting?: boolean | null
  dataDeliveryIds?: string[] | null
  deliveryLocations?: string[] | null
  outputFormats?: string[] | null
}

interface MaterializationTargetResultView {
  dataObjectVersionId?: string | null
  rowCount?: number | null
  outputUri?: string | null
  outputFormat?: string | null
  reusedExisting?: boolean | null
  dataDeliveryId?: string | null
  deliveryNote?: {
    deliveryLocation?: string | null
  } | null
}

interface SourceOverrideView {
  uri?: string | null
  format?: string | null
  options?: {
    materializationRequestId?: string | null
    deliverySummary?: MaterializationDeliverySummaryView | null
    targetResults?: MaterializationTargetResultView[] | null
  } | null
}

interface RuleExecutionMonitoringProps {
  onNavigate?: (navId: string) => void
}

interface GxArtifactExecutionContractView {
  engineTarget: 'pyspark'
  executionShape: GxExecutionShape
  traceability: GxExecutionContractTraceabilityView
  sourceMaterialization: GxArtifactLandingZoneMaterializationView | null
}

interface GxExecutionRunView {
  id: string
  suiteId: string | null
  suiteVersion: number | null
  ruleId: string | null
  ruleVersionId: string | null
  runPlanId?: string | null
  correlationId: string
  requestedBy: string | null
  engineTarget: 'pyspark'
  executionShape: GxExecutionShape
  status: GxExecutionStatus
  submittedAt: string
  startedAt: string | null
  completedAt: string | null
  createdAt: string
  updatedAt: string
  executionContract: Record<string, unknown> | null
  handoffPayload: Record<string, unknown> | null
  resolvedDataDeliveryId?: string | null
  executionProgress: GxExecutionProgressView | null
  resultSummary: Record<string, unknown>
  performanceSummary: GxExecutionPerformanceSummaryView | null
  diagnostics: Array<Record<string, unknown>>
  failureCode: string | null
  failureMessage: string | null
  comments: string | null
  statusHistory: GxExecutionRunStatusHistoryView[]
}

interface GxExecutionProgressView {
  percent: number
  label: string | null
  completedSteps: number | null
  totalSteps: number | null
  source: string | null
  updatedAt: string | null
}
interface GxExecutionPerformanceSummaryView {
  executionPath: string
  plannerChoice: string
  runtimeMs: number
  suiteCount: number
  batchCount: number
  selectedTargetCount: number
  dataScannedRows: number | null
  dataScannedBytes: number | null
}

interface GxExecutionRunSummaryView {
  id: string
  suiteId: string | null
  suiteVersion: number | null
  ruleId: string | null
  ruleName: string | null
  runPlanId?: string | null
  dataObjectVersionId: string | null
  dataObjectNames: string[]
  resolvedDataDeliveryId?: string | null
  correlationId: string
  requestedBy: string | null
  engineTarget: 'pyspark'
  executionShape: GxExecutionShape
  status: GxExecutionStatus
  failedRecordCount: number
  submittedAt: string
  startedAt: string | null
  completedAt: string | null
  createdAt: string
  updatedAt: string
}

interface GxExecutionRunCountView {
  name: string
  count: number
}

interface GxExecutionRunStatisticsView {
  lookbackAmount: number
  lookbackUnit: 'hours' | 'days'
  recentLimit: number
  totalRuns: number
  pendingRuns: number
  runningRuns: number
  succeededRuns: number
  failedRuns: number
  cancelledRuns: number
  statusBreakdown: GxExecutionRunCountView[]
  engineTargetBreakdown: GxExecutionRunCountView[]
  executionShapeBreakdown: GxExecutionRunCountView[]
  recentRuns: GxExecutionRunSummaryView[]
}

type GxExceptionTrendBucketView = {
  bucketStart: string
  total: number
}

type GxExceptionRuleHotspotView = {
  ruleId: string
  ruleName: string
  total: number
}

type GxExceptionDataObjectHotspotView = {
  dataObjectVersionId: string
  dataObjectName: string
  total: number
}

interface GxExecutionExceptionAnalyticsView {
  totalFailedRecords: number
  runsWithFailures: number
  trendBuckets: GxExceptionTrendBucketView[]
  topRules: GxExceptionRuleHotspotView[]
  topDataObjects: GxExceptionDataObjectHotspotView[]
}

type GxSuiteRefView = {
  suiteId: string
  suiteVersion: number
}

type GxGroupedBatchSummaryView = {
  targetDataObjectVersionId?: string | null
  suiteCount?: number | null
  executionShape?: string | null
}

interface GxExecutionQueueStatusView {
  runId: string
  queueKey: string
  queueMessageId: string
  queueLength: number
  inspectedDepth: number
  found: boolean
  indexFromHead: number | null
  indexFromTail: number | null
}

const DEFAULT_LOOKBACK_AMOUNT = 24
const DEFAULT_LOOKBACK_UNIT: 'hours' | 'days' = 'hours'
const DEFAULT_SUMMARY_LIMIT = 25

const LOOKBACK_UNIT_OPTIONS = [
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
]

const BROWSE_STATUS_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
]

const buildSuiteSelectionKey = (suiteId: string, suiteVersion: number): string => `${suiteId}:${suiteVersion}`

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

const readOptionalNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

const pluralize = (count: number, noun: string): string => {
  if (count === 1) return `${count} ${noun}`
  if (noun === 'delivery') return `${count} deliveries`
  return `${count} ${noun}s`
}

const normalizeStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []
  return Array.from(new Set(value.map((item) => String(item || '').trim()).filter(Boolean)))
}

const getSourceOverrides = (value: unknown): Array<{ targetId: string; override: SourceOverrideView }> => {
  if (!isRecord(value)) return []
  return Object.entries(value).flatMap(([targetId, override]) => {
    const normalizedTargetId = String(targetId || '').trim()
    if (!normalizedTargetId || !isRecord(override)) return []
    return [{ targetId: normalizedTargetId, override: override as unknown as SourceOverrideView }]
  })
}

const getOverrideTargetResults = (overrides: Array<{ targetId: string; override: SourceOverrideView }>): MaterializationTargetResultView[] => {
  const firstWithResults = overrides.find((entry) => Array.isArray(entry.override.options?.targetResults))
  return Array.isArray(firstWithResults?.override.options?.targetResults)
    ? firstWithResults.override.options.targetResults
    : []
}

const getOverrideDeliverySummary = (overrides: Array<{ targetId: string; override: SourceOverrideView }>): MaterializationDeliverySummaryView | null => {
  const firstWithSummary = overrides.find((entry) => isRecord(entry.override.options?.deliverySummary))
  return isRecord(firstWithSummary?.override.options?.deliverySummary)
    ? firstWithSummary.override.options.deliverySummary
    : null
}

const formatTrendBucketLabel = (value: number, lookbackUnit: 'hours' | 'days'): string => {
  const date = new Date(value)
  if (lookbackUnit === 'hours') {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

const formatSuiteIdentity = (suiteId?: string | null, suiteVersion?: number | null): string => {
  if (suiteId && suiteVersion !== null && suiteVersion !== undefined) {
    return `Suite ${suiteId} v${suiteVersion}`
  }
  return 'Grouped scope'
}

const isGroupedScopeShape = (executionShape?: string | null): boolean => executionShape === 'grouped_scope'

const getGroupedSuiteRefs = (value: unknown): GxSuiteRefView[] => {
  if (!Array.isArray(value)) {
    return []
  }

  return value.flatMap((entry) => {
    if (!isRecord(entry)) {
      return []
    }

    const suiteId = typeof entry.suiteId === 'string' ? entry.suiteId.trim() : ''
    const suiteVersion = readOptionalNumber(entry.suiteVersion)
    if (!suiteId || suiteVersion === null) {
      return []
    }

    return [{ suiteId, suiteVersion }]
  })
}

const getGroupedBatchResults = (value: unknown): GxGroupedBatchSummaryView[] => {
  if (!Array.isArray(value)) {
    return []
  }

  return value.flatMap((entry) => {
    if (!isRecord(entry)) {
      return []
    }

    return [{
      targetDataObjectVersionId: typeof entry.targetDataObjectVersionId === 'string' ? entry.targetDataObjectVersionId : null,
      suiteCount: readOptionalNumber(entry.suiteCount),
      executionShape: typeof entry.executionShape === 'string' ? entry.executionShape : null,
    }]
  })
}

const summarizeGroupedScopeCounts = (suiteCount: number | null, batchCount: number | null): string => {
  const parts: string[] = ['Grouped scope']
  if (suiteCount !== null) {
    parts.push(pluralize(suiteCount, 'suite'))
  }
  if (batchCount !== null) {
    parts.push(pluralize(batchCount, 'batch'))
  }
  return parts.join(' | ')
}
const formatDurationMs = (value: number | null | undefined): string => {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'Not recorded'
  }
  if (value < 1000) {
    return `${Math.round(value)}ms`
  }
  return `${(value / 1000).toFixed(2)}s`
}

const formatMetricCount = (value: number | null | undefined): string => {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'Not recorded'
  }
  return value.toLocaleString()
}

const formatBytes = (value: number | null | undefined): string => {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'Not recorded'
  }

  const absoluteValue = Math.abs(value)
  const units = [
    { unit: 'B', threshold: 1 },
    { unit: 'KB', threshold: 1024 },
    { unit: 'MB', threshold: 1024 ** 2 },
    { unit: 'GB', threshold: 1024 ** 3 },
    { unit: 'TB', threshold: 1024 ** 4 },
  ]

  const selectedUnit = [...units].reverse().find((entry) => absoluteValue >= entry.threshold) || units[0]
  const normalizedValue = selectedUnit.unit === 'B' ? value : value / selectedUnit.threshold
  return `${normalizedValue.toFixed(selectedUnit.unit === 'B' ? 0 : 2)} ${selectedUnit.unit}`
}

const buildDefaultScheduledAtInput = (): string => {
  const date = new Date(Date.now() + 60 * 60 * 1000)
  date.setSeconds(0, 0)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day}T${hours}:${minutes}`
}

const formatAssignmentScope = (scope: GxSuiteEnvelope['assignmentScope'] | undefined): string => {
  if (!scope) return 'n/a'

  const parts = [
    scope.dataProductId ? `dataProductId=${scope.dataProductId}` : null,
    scope.datasetId ? `datasetId=${scope.datasetId}` : null,
    scope.dataObjectId ? `dataObjectId=${scope.dataObjectId}` : null,
  ].filter(Boolean)

  return parts.length > 0 ? parts.join(', ') : 'n/a'
}

const describeSelectedScope = (selection: GxSuiteScopeSelection | null): string => {
  if (!selection) return 'No scope selected.'

  if (selection.kind === 'attribute') {
    const objectLabel = selection.dataObjectName || selection.dataObjectId || 'unknown object'
    return `Attribute ${selection.attributeName} (${objectLabel}, version ${selection.dataObjectVersionId})`
  }

  if (selection.kind === 'data_object_version') {
    const objectLabel = selection.dataObjectName || selection.dataObjectId || 'unknown object'
    return `Data object version (${objectLabel}, version ${selection.dataObjectVersionId})`
  }

  if (selection.kind === 'data_object') {
    return `Data object ${selection.dataObjectName} (${selection.dataObjectId})`
  }

  if (selection.kind === 'dataset') {
    return `Dataset ${selection.datasetName} (${selection.datasetId})`
  }

  return `Data product ${selection.dataProductName} (${selection.dataProductId})`
}

const buildSuiteQueryFromSelection = (selection: GxSuiteScopeSelection): { key: string; value: string } => {
  if (selection.kind === 'data_product') {
    return { key: 'dataProductId', value: selection.dataProductId }
  }
  if (selection.kind === 'dataset') {
    return { key: 'datasetId', value: selection.datasetId }
  }
  if (selection.kind === 'data_object') {
    return { key: 'dataObjectId', value: selection.dataObjectId }
  }
  if (selection.kind === 'data_object_version') {
    return { key: 'dataObjectVersionId', value: selection.dataObjectVersionId }
  }
  return { key: 'dataObjectVersionId', value: selection.dataObjectVersionId }
}

const toScheduledAtIso = (value: string): string => {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    throw new Error('Enter a valid scheduled time.')
  }
  return parsed.toISOString()
}

/**
 * RuleExecutionMonitoring Component
 *
 * Browse recent validation execution runs, inspect lifecycle transitions, and open
 * a specific run for the detailed queue handoff view.
 */
export const RuleExecutionMonitoring: React.FC<RuleExecutionMonitoringProps> = ({ onNavigate }) => {
  const [initialDashboardPreset] = useState(() => consumeDashboardNavigationSelection('reports-rule-monitoring'))
  const auth = useAuth()
  const settings = useSettings()
  const apiV1 = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  const currentWorkspaceId = auth.currentWorkspaceId?.trim() || ''
  const [lookbackAmount, setLookbackAmount] = useState(DEFAULT_LOOKBACK_AMOUNT)
  const [lookbackUnit, setLookbackUnit] = useState<'hours' | 'days'>(DEFAULT_LOOKBACK_UNIT)
  const [browseStatus, setBrowseStatus] = useState<GxBrowseStatusFilter>(() => {
    const presetStatus = initialDashboardPreset?.browse_status
    return isDashboardBrowseStatus(presetStatus) ? presetStatus : 'all'
  })
  const [ruleNameFilter, setRuleNameFilter] = useState('')
  const [dataObjectNameFilter, setDataObjectNameFilter] = useState('')
  const [deliveryIdFilter, setDeliveryIdFilter] = useState('')
  const [searchFilter, setSearchFilter] = useState('')
  const [recentRuns, setRecentRuns] = useState<GxExecutionRunSummaryView[]>([])
  const [recentRunsLoading, setRecentRunsLoading] = useState(false)
  const [recentRunsError, setRecentRunsError] = useState<string | null>(null)
  const [recentRunsLastLoadedAt, setRecentRunsLastLoadedAt] = useState<string | null>(null)
  const [exceptionAnalytics, setExceptionAnalytics] = useState<GxExecutionExceptionAnalyticsView | null>(null)
  const [exceptionAnalyticsLoading, setExceptionAnalyticsLoading] = useState(false)
  const [exceptionAnalyticsError, setExceptionAnalyticsError] = useState<string | null>(null)
  const [runIdInput, setRunIdInput] = useState('')
  const [trackedRunId, setTrackedRunId] = useState('')
  const [run, setRun] = useState<GxExecutionRunView | null>(null)
  const [runCommentsDraft, setRunCommentsDraft] = useState('')
  const [runCommentsSaving, setRunCommentsSaving] = useState(false)
  const [runCommentsError, setRunCommentsError] = useState<string | null>(null)
  const [statusHistory, setStatusHistory] = useState<GxExecutionRunStatusHistoryView[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null)
  const [queueStatus, setQueueStatus] = useState<GxExecutionQueueStatusView | null>(null)
  const [queueStatusLoading, setQueueStatusLoading] = useState(false)
  const [queueStatusError, setQueueStatusError] = useState<string | null>(null)
  const [isScopePickerOpen, setIsScopePickerOpen] = useState(false)
  const [scheduleScopeSelection, setScheduleScopeSelection] = useState<GxSuiteScopeSelection | null>(null)
  const [scheduleSuites, setScheduleSuites] = useState<GxSuiteEnvelope[]>([])
  const [scheduleSuitesLoading, setScheduleSuitesLoading] = useState(false)
  const [scheduleSuitesError, setScheduleSuitesError] = useState<string | null>(null)
  const [selectedSuiteKey, setSelectedSuiteKey] = useState('')
  const [scheduleAtInput, setScheduleAtInput] = useState(buildDefaultScheduledAtInput)
  const [scheduleSubmitting, setScheduleSubmitting] = useState(false)
  const [scheduleSubmitError, setScheduleSubmitError] = useState<string | null>(null)
  const [scheduledDispatch, setScheduledDispatch] = useState<GxScheduledDispatchHandoffView | null>(null)

  const terminalStatuses = useMemo(() => new Set<GxExecutionStatus>(['succeeded', 'failed', 'cancelled']), [])

  const authHeaders = useCallback((): Record<string, string> => {
    const token = getAuthToken()
    return token ? { Authorization: `Bearer ${token}` } : {}
  }, [])

  const formatDateTime = useCallback((value?: string | null): string => {
    if (!value) return 'Not recorded'
    try {
      return new Date(value).toLocaleString()
    } catch {
      return value
    }
  }, [])

  const formatJson = useCallback((value: unknown): string => {
    if (!value || (typeof value === 'object' && Object.keys(value as Record<string, unknown>).length === 0)) {
      return 'No data'
    }
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }, [])

  const isTerminalStatus = useCallback((value?: string | null) => {
    return terminalStatuses.has((value || '').toLowerCase() as GxExecutionStatus)
  }, [terminalStatuses])

  const extractErrorMessage = useCallback(async (response: Response, fallback: string): Promise<string> => {
    const body = await response.json().catch(() => null)
    if (typeof body === 'string' && body.trim()) {
      return normalizeValidationUiText(body.trim())
    }

    if (body && typeof body === 'object') {
      const detail = (body as Record<string, unknown>).detail ?? (body as Record<string, unknown>).message ?? (body as Record<string, unknown>).error
      if (typeof detail === 'string' && detail.trim()) {
        return normalizeValidationUiText(detail.trim())
      }
      if (detail && typeof detail === 'object') {
        try {
          return normalizeValidationUiText(JSON.stringify(detail))
        } catch {
          return fallback
        }
      }
    }

    return normalizeValidationUiText(fallback)
  }, [])

  const buildMonitoringQuery = useCallback((
    overrides?: Partial<{
      lookbackAmount: number
      lookbackUnit: 'hours' | 'days'
      browseStatus: GxBrowseStatusFilter
      ruleNameFilter: string
      dataObjectNameFilter: string
      deliveryIdFilter: string
      searchFilter: string
    }>,
    options?: { includeLimit?: boolean }
  ) => {
    const includeLimit = options?.includeLimit ?? true
    const params = new URLSearchParams()
    const nextLookbackAmount = overrides?.lookbackAmount ?? lookbackAmount
    const nextLookbackUnit = overrides?.lookbackUnit ?? lookbackUnit
    const nextBrowseStatus = overrides?.browseStatus ?? browseStatus
    const nextRuleNameFilter = (overrides?.ruleNameFilter ?? ruleNameFilter).trim()
    const nextDataObjectNameFilter = (overrides?.dataObjectNameFilter ?? dataObjectNameFilter).trim()
    const nextDeliveryIdFilter = (overrides?.deliveryIdFilter ?? deliveryIdFilter).trim()
    const nextSearchFilter = (overrides?.searchFilter ?? searchFilter).trim()

    params.set('lookbackAmount', String(nextLookbackAmount))
    params.set('lookbackUnit', nextLookbackUnit)
    if (includeLimit) {
      params.set('recentLimit', String(DEFAULT_SUMMARY_LIMIT))
    }
    if (currentWorkspaceId) {
      params.set('workspaceId', currentWorkspaceId)
    }

    if (nextBrowseStatus !== 'all') {
      params.set('status', nextBrowseStatus)
    }
    if (nextRuleNameFilter) {
      params.set('ruleName', nextRuleNameFilter)
    }
    if (nextDataObjectNameFilter) {
      params.set('dataObjectName', nextDataObjectNameFilter)
    }
    if (nextDeliveryIdFilter) {
      params.set('deliveryId', nextDeliveryIdFilter)
    } else if (scheduleScopeSelection) {
      const scopeQuery = buildSuiteQueryFromSelection(scheduleScopeSelection)
      params.set(scopeQuery.key, scopeQuery.value)
    }
    if (nextSearchFilter) {
      params.set('search', nextSearchFilter)
    }

    return params.toString()
  }, [browseStatus, currentWorkspaceId, dataObjectNameFilter, deliveryIdFilter, lookbackAmount, lookbackUnit, ruleNameFilter, scheduleScopeSelection, searchFilter])

  const loadRecentRuns = useCallback(async (overrides?: Partial<{
    lookbackAmount: number
    lookbackUnit: 'hours' | 'days'
    browseStatus: GxBrowseStatusFilter
    ruleNameFilter: string
    dataObjectNameFilter: string
    deliveryIdFilter: string
    searchFilter: string
  }>) => {
    setRecentRunsLoading(true)
    setRecentRunsError(null)
    try {
      const query = buildMonitoringQuery(overrides, { includeLimit: true })
      const response = await fetch(`${apiV1}/gx/runs/stats?${query}`, {
        headers: authHeaders(),
      })

      if (!response.ok) {
        const message = await extractErrorMessage(response, 'Unable to load recent validation runs.')
        setRecentRuns([])
        setRecentRunsError(message)
        return
      }

      const payload = snakeToCamel<GxExecutionRunStatisticsView>(await response.json())
      setRecentRuns(payload.recentRuns)
      setRecentRunsLastLoadedAt(new Date().toISOString())
    } catch (error) {
      setRecentRuns([])
      setRecentRunsError(error instanceof Error ? normalizeValidationUiText(error.message) : 'Unable to load recent validation runs.')
    } finally {
      setRecentRunsLoading(false)
    }
  }, [apiV1, authHeaders, buildMonitoringQuery, extractErrorMessage])

  const loadExceptionAnalytics = useCallback(async (overrides?: Partial<{
    lookbackAmount: number
    lookbackUnit: 'hours' | 'days'
    browseStatus: GxBrowseStatusFilter
    ruleNameFilter: string
    dataObjectNameFilter: string
    deliveryIdFilter: string
    searchFilter: string
  }>) => {
    setExceptionAnalyticsLoading(true)
    setExceptionAnalyticsError(null)
    try {
      const query = buildMonitoringQuery(overrides, { includeLimit: false })
      const response = await fetch(`${apiV1}/gx/exception-analytics?${query}`, {
        headers: authHeaders(),
      })

      if (!response.ok) {
        const message = await extractErrorMessage(response, 'Unable to load validation exception analytics.')
        setExceptionAnalytics(null)
        setExceptionAnalyticsError(message)
        return
      }

      const payload = snakeToCamel<GxExecutionExceptionAnalyticsView>(await response.json())
      setExceptionAnalytics(payload)
    } catch (error) {
      setExceptionAnalytics(null)
      setExceptionAnalyticsError(error instanceof Error ? normalizeValidationUiText(error.message) : 'Unable to load validation exception analytics.')
    } finally {
      setExceptionAnalyticsLoading(false)
    }
  }, [apiV1, authHeaders, buildMonitoringQuery, extractErrorMessage])

  const loadScheduleSuites = useCallback(async (selectionOverride?: GxSuiteScopeSelection | null) => {
    const selection = selectionOverride ?? scheduleScopeSelection
    if (!selection) {
      setScheduleSuites([])
      setSelectedSuiteKey('')
      setScheduleSuitesError('Select a catalog scope first.')
      return
    }

    setScheduleSuitesLoading(true)
    setScheduleSuitesError(null)

    try {
      const params = new URLSearchParams()
      const query = buildSuiteQueryFromSelection(selection)
      params.set(query.key, query.value)
      params.set('status', 'active' satisfies GxSuiteStatus)
      params.set('latestOnly', 'true')

      const response = await fetch(`${apiV1}/gx/suites?${params.toString()}`, {
        headers: authHeaders(),
      })

      if (!response.ok) {
        const message = await extractErrorMessage(response, 'Unable to load validation suites for scheduling.')
        setScheduleSuites([])
        setSelectedSuiteKey('')
        setScheduleSuitesError(message)
        return
      }

      const payload = snakeToCamel<GxSuiteEnvelope[]>(await response.json())
      const nextSuites = Array.isArray(payload) ? payload : []
      setScheduleSuites(nextSuites)
      setSelectedSuiteKey((current) => {
        if (current && nextSuites.some((suite) => buildSuiteSelectionKey(suite.suiteId, suite.suiteVersion) === current)) {
          return current
        }
        const firstSuite = nextSuites[0]
        return firstSuite ? buildSuiteSelectionKey(firstSuite.suiteId, firstSuite.suiteVersion) : ''
      })
    } catch (error) {
      setScheduleSuites([])
      setSelectedSuiteKey('')
      setScheduleSuitesError(error instanceof Error ? normalizeValidationUiText(error.message) : 'Unable to load validation suites for scheduling.')
    } finally {
      setScheduleSuitesLoading(false)
    }
  }, [apiV1, authHeaders, extractErrorMessage, scheduleScopeSelection])

  const loadRun = useCallback(async (nextRunId: string) => {
    const normalizedRunId = nextRunId.trim()
    if (!normalizedRunId) {
      setRunError('Enter a validation run id to load.')
      setRun(null)
      setRunCommentsDraft('')
      setRunCommentsError(null)
      setRunCommentsSaving(false)
      setStatusHistory([])
      setTrackedRunId('')
      return
    }

    setIsLoading(true)
    setRunError(null)
    setHistoryError(null)
    setQueueStatus(null)
    setQueueStatusError(null)
    setQueueStatusLoading(false)
    setRunCommentsError(null)
    setRunCommentsSaving(false)

    const [runResult, historyResult] = await Promise.allSettled([
      fetch(`${apiV1}/gx/runs/${encodeURIComponent(normalizedRunId)}`, {
        headers: authHeaders(),
      }),
      fetch(`${apiV1}/gx/runs/${encodeURIComponent(normalizedRunId)}/status-history`, {
        headers: authHeaders(),
      }),
    ])

    let nextRun: GxExecutionRunView | null = null
    let nextRunError: string | null = null
    let nextHistory: GxExecutionRunStatusHistoryView[] = []
    let nextHistoryError: string | null = null

    if (runResult.status === 'fulfilled') {
      if (runResult.value.ok) {
        nextRun = snakeToCamel<GxExecutionRunView>(await runResult.value.json())
      } else {
        nextRunError = await extractErrorMessage(
          runResult.value,
          `Unable to load validation run '${normalizedRunId}'.`
        )
      }
    } else {
      nextRunError = runResult.reason instanceof Error
        ? normalizeValidationUiText(runResult.reason.message)
        : `Unable to load validation run '${normalizedRunId}'.`
    }

    if (historyResult.status === 'fulfilled') {
      if (historyResult.value.ok) {
        nextHistory = snakeToCamel<GxExecutionRunStatusHistoryView[]>(await historyResult.value.json())
      } else {
        nextHistoryError = await extractErrorMessage(
          historyResult.value,
          `Unable to load validation run status history for '${normalizedRunId}'.`
        )
      }
    } else {
      nextHistoryError = historyResult.reason instanceof Error
        ? normalizeValidationUiText(historyResult.reason.message)
        : `Unable to load validation run status history for '${normalizedRunId}'.`
    }

    setRun(nextRun)
    setRunCommentsDraft(String(nextRun?.comments || ''))
    setStatusHistory(nextHistory)
    setRunError(nextRunError)
    setHistoryError(nextHistoryError)
    setTrackedRunId(nextRun ? normalizedRunId : '')
    setLastLoadedAt(new Date().toISOString())
    setIsLoading(false)

    if (nextRun && nextRun.handoffPayload && typeof nextRun.handoffPayload === 'object') {
      const dispatchMode = String((nextRun.handoffPayload as any).dispatchMode || '').toLowerCase()
      const queueKey = String((nextRun.handoffPayload as any).queueKey || '').trim()
      const queueMessageId = String((nextRun.handoffPayload as any).queueMessageId || '').trim()
      const isQueued = dispatchMode === 'queued' && nextRun.status === 'pending'

      if (isQueued && queueKey && queueMessageId) {
        setQueueStatusLoading(true)
        fetch(`${apiV1}/gx/runs/${encodeURIComponent(normalizedRunId)}/queue-status?scanLimit=500`, {
          headers: authHeaders(),
        })
          .then(async (response) => {
            if (!response.ok) {
              const message = await extractErrorMessage(response, 'Unable to load validation queue status.')
              setQueueStatus(null)
              setQueueStatusError(message)
              return
            }
            const payload = snakeToCamel<GxExecutionQueueStatusView>(await response.json())
            setQueueStatus(payload)
            setQueueStatusError(null)
          })
          .catch((error) => {
            setQueueStatus(null)
            setQueueStatusError(error instanceof Error ? normalizeValidationUiText(error.message) : 'Unable to load validation queue status.')
          })
          .finally(() => {
            setQueueStatusLoading(false)
          })
      }
    }

    if (nextRun) {
      setRunIdInput(normalizedRunId)
      try {
        localStorage.setItem('dq-last-gx-run-id', normalizedRunId)
      } catch {
        // ignore storage errors
      }
    }
  }, [apiV1, authHeaders, extractErrorMessage])

  const saveRunComments = useCallback(async () => {
    if (!run) {
      setRunCommentsError('Load a validation run before saving comments.')
      return
    }

    const normalizedComments = runCommentsDraft.trim()
    const currentComments = String(run.comments || '').trim()
    if (normalizedComments === currentComments) {
      setRunCommentsError(null)
      return
    }

    setRunCommentsSaving(true)
    setRunCommentsError(null)

    try {
      const response = await fetch(`${apiV1}/gx/runs/${encodeURIComponent(run.id)}/comments`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
        },
        body: JSON.stringify(camelToSnake({ comments: normalizedComments || null })),
      })

      if (!response.ok) {
        const message = await extractErrorMessage(response, `Unable to update comments for validation run '${run.id}'.`)
        setRunCommentsError(message)
        return
      }

      const updatedRun = snakeToCamel<GxExecutionRunView>(await response.json())
      setRun(updatedRun)
      setRunCommentsDraft(String(updatedRun.comments || ''))
      setStatusHistory(updatedRun.statusHistory || [])
    } catch (error) {
      setRunCommentsError(error instanceof Error ? normalizeValidationUiText(error.message) : `Unable to update comments for validation run '${run.id}'.`)
    } finally {
      setRunCommentsSaving(false)
    }
  }, [apiV1, authHeaders, extractErrorMessage, normalizeValidationUiText, run, runCommentsDraft])

  const scheduleSelectedSuiteRun = useCallback(async () => {
    const selectedSuite = scheduleSuites.find((suite) => buildSuiteSelectionKey(suite.suiteId, suite.suiteVersion) === selectedSuiteKey)
    if (!selectedSuite) {
      setScheduleSubmitError('Select a validation suite to schedule.')
      return
    }

    setScheduleSubmitError(null)
    setScheduledDispatch(null)
    setScheduleSubmitting(true)

    try {
      const scheduledAt = toScheduledAtIso(scheduleAtInput)
      const response = await fetch(
        `${apiV1}/gx/suites/${encodeURIComponent(selectedSuite.suiteId)}/runs/schedule?suiteVersion=${selectedSuite.suiteVersion}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...authHeaders(),
          },
          body: JSON.stringify(camelToSnake({ scheduledAt })),
        },
      )

      if (!response.ok) {
        const message = await extractErrorMessage(response, 'Unable to schedule validation run.')
        setScheduleSubmitError(message)
        return
      }

      const handoff = snakeToCamel<GxScheduledDispatchHandoffView>(await response.json())
      setScheduledDispatch(handoff)
      setRunIdInput(handoff.runId)
      await Promise.all([
        loadRecentRuns(),
        loadExceptionAnalytics(),
        loadRun(handoff.runId),
      ])
    } catch (error) {
      setScheduleSubmitError(error instanceof Error ? normalizeValidationUiText(error.message) : 'Unable to schedule validation run.')
    } finally {
      setScheduleSubmitting(false)
    }
  }, [apiV1, authHeaders, extractErrorMessage, loadExceptionAnalytics, loadRecentRuns, loadRun, scheduleAtInput, scheduleSuites, selectedSuiteKey])

  const handleRecentRunsSubmit = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await Promise.all([
      loadRecentRuns(),
      loadExceptionAnalytics(),
    ])
  }, [loadExceptionAnalytics, loadRecentRuns])

  const handleRunSubmit = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await loadRun(runIdInput)
  }, [loadRun, runIdInput])

  useEffect(() => {
    if (!currentWorkspaceId) {
      setRecentRuns([])
      setExceptionAnalytics(null)
      return
    }
    const initialFilters = {
      lookbackAmount: DEFAULT_LOOKBACK_AMOUNT,
      lookbackUnit: DEFAULT_LOOKBACK_UNIT,
      browseStatus: isDashboardBrowseStatus(initialDashboardPreset?.browse_status)
        ? initialDashboardPreset.browse_status
        : 'all' as const,
      ruleNameFilter: '',
      dataObjectNameFilter: '',
      searchFilter: '',
    }
    void Promise.all([
      loadRecentRuns(initialFilters),
      loadExceptionAnalytics(initialFilters),
    ])
  }, [currentWorkspaceId, initialDashboardPreset, loadExceptionAnalytics, loadRecentRuns])

  useEffect(() => {
    if (!trackedRunId || !run || isTerminalStatus(run.status)) {
      return
    }

    const interval = window.setInterval(() => {
      void loadRun(trackedRunId)
    }, 15000)

    return () => {
      window.clearInterval(interval)
    }
  }, [isTerminalStatus, loadRun, run, trackedRunId])

  const queueDetails = run?.handoffPayload && typeof run.handoffPayload === 'object'
    ? run.handoffPayload
    : null
  const sourceOverrides = getSourceOverrides(queueDetails?.sourceOverridesByDataObjectVersionId)
  const sourceOverrideDeliverySummary = getOverrideDeliverySummary(sourceOverrides)
  const sourceOverrideTargetResults = getOverrideTargetResults(sourceOverrides)
  const sourceOverrideTargetCount = readOptionalNumber(sourceOverrideDeliverySummary?.targetCount)
    ?? (sourceOverrideTargetResults.length > 0 ? sourceOverrideTargetResults.length : sourceOverrides.length)
  const sourceOverrideDeliveryCount = readOptionalNumber(sourceOverrideDeliverySummary?.dataDeliveryCount)
    ?? sourceOverrideTargetResults.filter((target) => String(target.dataDeliveryId || '').trim()).length
  const sourceOverrideTotalRows = readOptionalNumber(sourceOverrideDeliverySummary?.totalRowCount)
  const sourceOverrideFormats = normalizeStringList(sourceOverrideDeliverySummary?.outputFormats)
  const sourceOverrideDeliveryIds = normalizeStringList([
    ...(sourceOverrideDeliverySummary?.dataDeliveryIds || []),
    ...sourceOverrideTargetResults.map((target) => target.dataDeliveryId),
  ])
  const sourceOverrideDeliveryLocations = normalizeStringList([
    ...(sourceOverrideDeliverySummary?.deliveryLocations || []),
    ...sourceOverrideTargetResults.map((target) => target.deliveryNote?.deliveryLocation || target.outputUri),
  ])

  const queuePositionLabel = useMemo(() => {
    if (!queueStatus) return null
    if (!queueStatus.found) return 'Not found in scan window'
    if (queueStatus.indexFromTail === 0) return 'Next'
    if (typeof queueStatus.indexFromTail === 'number') return `${queueStatus.indexFromTail} ahead`
    return null
  }, [queueStatus])

  const executionContract = run?.executionContract ?? null
  const executionProgress = isRecord(run?.executionProgress)
    ? run?.executionProgress as GxExecutionProgressView
    : null
  const traceability = isRecord(executionContract) && isRecord(executionContract.traceability)
    ? executionContract.traceability as unknown as GxExecutionContractTraceabilityView
    : null
  const sourceMaterialization = isRecord(executionContract) && isRecord(executionContract.sourceMaterialization)
    ? executionContract.sourceMaterialization as unknown as GxArtifactLandingZoneMaterializationView
    : null
  const groupedExecutionContract = run?.executionShape === 'grouped_scope' && isRecord(executionContract)
    ? executionContract
    : null
  const groupedExecutionPlan = isRecord(queueDetails) && isRecord(queueDetails.groupedExecutionPlan)
    ? queueDetails.groupedExecutionPlan
    : null
  const groupedResultSummary = isRecord(run?.resultSummary) ? run.resultSummary : null
  const executionPerformanceSummary = isRecord(run?.performanceSummary)
    ? run.performanceSummary as GxExecutionPerformanceSummaryView
    : isRecord(groupedResultSummary?.performanceSummary)
      ? groupedResultSummary.performanceSummary as GxExecutionPerformanceSummaryView
      : null
  const groupedSuiteRefs = getGroupedSuiteRefs(groupedExecutionContract?.suiteRefs ?? queueDetails?.suiteRefs)
  const groupedSuiteCount = readOptionalNumber(
    groupedExecutionContract?.suiteCount
      ?? groupedExecutionPlan?.suiteCount
      ?? groupedResultSummary?.suiteCount
      ?? (groupedSuiteRefs.length > 0 ? groupedSuiteRefs.length : null)
  )
  const groupedBatchCount = readOptionalNumber(
    groupedExecutionContract?.batchCount
      ?? groupedExecutionPlan?.batchCount
      ?? groupedResultSummary?.batchCount
  )
  const groupedScopeLabel = run?.executionShape === 'grouped_scope'
    ? summarizeGroupedScopeCounts(groupedSuiteCount, groupedBatchCount)
    : formatSuiteIdentity(run?.suiteId, run?.suiteVersion)
  const groupedBatchResults = getGroupedBatchResults(groupedResultSummary?.results)
  const historyRows = statusHistory.length > 0 ? statusHistory : run?.statusHistory || []
  const executionProgressPercent = executionProgress ? Math.max(0, Math.min(100, readOptionalNumber(executionProgress.percent) ?? 0)) : null
  const executionProgressLabel = typeof executionProgress?.label === 'string' && executionProgress.label.trim()
    ? executionProgress.label.trim()
    : null
  const executionProgressStepLabel = executionProgress?.completedSteps !== null && executionProgress?.completedSteps !== undefined && executionProgress?.totalSteps !== null && executionProgress?.totalSteps !== undefined
    ? `${executionProgress.completedSteps} of ${executionProgress.totalSteps} steps`
    : null
  const exceptionTrendBuckets = exceptionAnalytics?.trendBuckets ?? []
  const totalFailedRecords = exceptionAnalytics?.totalFailedRecords ?? 0
  const runsWithFailures = exceptionAnalytics?.runsWithFailures ?? 0
  const maxExceptionBucketTotal = useMemo(
    () => exceptionTrendBuckets.reduce((max, entry) => Math.max(max, entry.total), 0),
    [exceptionTrendBuckets]
  )

  return (
    <AppPageShell className="rule-feature-container">
      <AppPageHeader
        className="feature-header"
        title="Execution Monitoring"
        titleAs="h2"
        description="Browse recent validation runs, schedule operations, and inspect runtime status history"
      />

      <div className="feature-content gx-monitor-layout">
        <section className="gx-monitor-panel gx-monitor-panel-scheduler">
          <div className="gx-monitor-panel-header">
            <div>
              <h3>Schedule a validation run</h3>
              <p className="gx-monitor-helper">
                Pick a catalog scope, choose an active validation suite, and enqueue a scheduled run without calling the API directly.
              </p>
            </div>
            <div className="gx-monitor-panel-meta">
              <span className="gx-monitor-badge gx-monitor-badge-neutral">API-7.8 dispatch</span>
              <span className="gx-monitor-badge gx-monitor-badge-info">API7-OI-06 UI flow</span>
            </div>
          </div>

          <div className="gx-scheduler-toolbar">
            <div className="gx-scheduler-scope-copy">
              <span className="gx-monitor-label">Selected scope</span>
              <p className="gx-monitor-helper">{describeSelectedScope(scheduleScopeSelection)}</p>
            </div>
            <div className="gx-scheduler-toolbar-actions">
              <button className="feature-button" type="button" onClick={() => setIsScopePickerOpen(true)}>
                Browse data catalog
              </button>
              <button
                className="gx-secondary-button"
                type="button"
                onClick={() => void loadScheduleSuites()}
                disabled={scheduleSuitesLoading || !scheduleScopeSelection}
              >
                {scheduleSuitesLoading ? 'Loading suites…' : 'Refresh suites'}
              </button>
            </div>
          </div>

          {scheduleSuitesError && (
            <div className="gx-monitor-error" role="alert">
              <AppIcon name="close-circle" />
              <span>{scheduleSuitesError}</span>
            </div>
          )}

          {scheduleSubmitError && (
            <div className="gx-monitor-error" role="alert">
              <AppIcon name="close-circle" />
              <span>{scheduleSubmitError}</span>
            </div>
          )}

          {!scheduleSuitesLoading && scheduleScopeSelection && scheduleSuites.length === 0 && !scheduleSuitesError && (
            <div className="feature-placeholder gx-scheduler-placeholder">
              <AppIcon name="calendar" />
              <p>No active validation suites were found for the selected scope.</p>
              <p className="placeholder-subtitle">Pick a different catalog scope or refresh the suite list.</p>
            </div>
          )}

          {scheduleSuites.length > 0 && (
            <>
              <div className="gx-scheduler-field-grid">
                <label className="gx-monitor-filter-field" htmlFor="gx-scheduled-at">
                  <span className="gx-monitor-label">Scheduled time</span>
                  <input
                    id="gx-scheduled-at"
                    className="gx-monitor-input"
                    type="datetime-local"
                    aria-label="Scheduled time"
                    value={scheduleAtInput}
                    onChange={(event) => setScheduleAtInput(event.target.value)}
                  />
                  <span className="gx-monitor-helper">Uses your local timezone for input, then converts to a UTC timestamp for the API. Scheduling itself is UTC-based.</span>
                </label>
              </div>

              <div className="gx-monitor-table-shell gx-scheduler-suite-shell">
                <table className="gx-monitor-table gx-scheduler-suite-table">
                  <thead>
                    <tr>
                      <th>Pick</th>
                      <th>Suite</th>
                      <th>Assignment</th>
                      <th>Compiled from</th>
                      <th>Execution</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scheduleSuites.map((suite) => {
                      const suiteKey = buildSuiteSelectionKey(suite.suiteId, suite.suiteVersion)
                      return (
                        <tr key={suiteKey} className={selectedSuiteKey === suiteKey ? 'is-active' : ''}>
                          <td>
                            <label className="gx-scheduler-radio">
                              <input
                                type="radio"
                                name="scheduled-suite"
                                value={suiteKey}
                                checked={selectedSuiteKey === suiteKey}
                                onChange={() => setSelectedSuiteKey(suiteKey)}
                              />
                              <span>Select</span>
                            </label>
                          </td>
                          <td>
                            <div>Suite {suite.suiteId} v{suite.suiteVersion}</div>
                            <div className="gx-monitor-table-subtext">Artifact {suite.artifactVersion}</div>
                          </td>
                          <td>
                            <div>{formatAssignmentScope(suite.assignmentScope)}</div>
                            <div className="gx-monitor-table-subtext gx-monitor-mono">
                              {suite.resolvedExecutionScope?.dataObjectVersionIds?.join(', ') || 'n/a'}
                            </div>
                          </td>
                          <td>
                            <div>{suite.compiledFrom?.ruleIds?.join(', ') || 'n/a'}</div>
                            <div className="gx-monitor-table-subtext">
                              Compiler {suite.compiledFrom?.compilerVersion || 'unknown'}
                            </div>
                          </td>
                          <td>
                            <div>{suite.executionContract?.executionShape || 'unknown'}</div>
                            <div className="gx-monitor-table-subtext">{suite.executionContract?.engineTarget || 'unknown'}</div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <div className="gx-scheduler-actions">
                <button className="feature-button" type="button" onClick={() => void scheduleSelectedSuiteRun()} disabled={scheduleSubmitting}>
                  {scheduleSubmitting ? 'Scheduling…' : 'Schedule selected validation run'}
                </button>
              </div>
            </>
          )}

          {scheduledDispatch && (
            <div className="gx-scheduler-success">
              <div className="gx-scheduler-success-copy">
                <h4>Scheduled run accepted</h4>
                <p className="gx-monitor-helper">
                  Run <span className="gx-monitor-mono">{scheduledDispatch.runId}</span> was queued for suite {scheduledDispatch.suiteId} v{scheduledDispatch.suiteVersion}.
                </p>
              </div>
              <dl className="gx-monitor-dl gx-monitor-dl-compact">
                <div>
                  <dt>Scheduled at</dt>
                  <dd>{formatDateTime(scheduledDispatch.scheduledAt)}</dd>
                </div>
                <div>
                  <dt>Queue key</dt>
                  <dd className="gx-monitor-mono">{scheduledDispatch.queueKey}</dd>
                </div>
                <div>
                  <dt>Queue message</dt>
                  <dd className="gx-monitor-mono">{scheduledDispatch.queueMessageId}</dd>
                </div>
              </dl>
              <div className="gx-scheduler-toolbar-actions">
                <button className="gx-secondary-button" type="button" onClick={() => void loadRun(scheduledDispatch.runId)}>
                  Open scheduled run
                </button>
              </div>
            </div>
          )}
        </section>

        <section className="gx-monitor-panel gx-monitor-panel-browse">
          <div className="gx-monitor-panel-header">
            <div>
              <h3>Recent validation runs</h3>
              <p className="gx-monitor-helper">
                Browse runs from the last {lookbackAmount} {lookbackUnit} and filter by rule or data object name before opening a detail view.
              </p>
              <p className="gx-monitor-helper">
                Active scope: {deliveryIdFilter ? `Delivery ${deliveryIdFilter}` : describeSelectedScope(scheduleScopeSelection)}
              </p>
            </div>
            <div className="gx-monitor-panel-meta">
              <span className="gx-monitor-badge gx-monitor-badge-neutral">API-7.9 browse</span>
              <span className="gx-monitor-badge gx-monitor-badge-info">{recentRuns.length} shown</span>
              {recentRunsLastLoadedAt && <span className="gx-monitor-badge">Updated {formatDateTime(recentRunsLastLoadedAt)}</span>}
            </div>
          </div>

          <form className="gx-monitor-form gx-monitor-browse-form" onSubmit={handleRecentRunsSubmit}>
            <div className="gx-monitor-filter-grid">
              <label className="gx-monitor-filter-field" htmlFor="gx-lookback-amount">
                <span className="gx-monitor-label">Lookback</span>
                <input
                  id="gx-lookback-amount"
                  className="gx-monitor-input"
                  type="number"
                  min={1}
                  max={720}
                  value={lookbackAmount}
                  onChange={(event) => setLookbackAmount(Number(event.target.value) || DEFAULT_LOOKBACK_AMOUNT)}
                />
              </label>
              <div className="gx-monitor-filter-field gx-monitor-select-field">
                <AppSelect
                  id="gx-lookback-unit"
                  label="Window"
                  value={lookbackUnit}
                  onChange={(value) => setLookbackUnit(value as 'hours' | 'days')}
                  options={LOOKBACK_UNIT_OPTIONS}
                  fieldClassName="gx-monitor-select"
                />
              </div>
              <div className="gx-monitor-filter-field gx-monitor-select-field">
                <AppSelect
                  id="gx-status-filter"
                  label="Status"
                  value={browseStatus}
                  onChange={(value) => setBrowseStatus(value as GxBrowseStatusFilter)}
                  options={BROWSE_STATUS_OPTIONS}
                  fieldClassName="gx-monitor-select"
                />
              </div>
              <label className="gx-monitor-filter-field gx-monitor-filter-wide" htmlFor="gx-rule-name-filter">
                <span className="gx-monitor-label">Rule name</span>
                <input
                  id="gx-rule-name-filter"
                  className="gx-monitor-input"
                  type="text"
                  value={ruleNameFilter}
                  onChange={(event) => setRuleNameFilter(event.target.value)}
                  placeholder="contains..."
                  autoComplete="off"
                />
              </label>
              <label className="gx-monitor-filter-field gx-monitor-filter-wide" htmlFor="gx-data-object-name-filter">
                <span className="gx-monitor-label">Data object name</span>
                <input
                  id="gx-data-object-name-filter"
                  className="gx-monitor-input"
                  type="text"
                  value={dataObjectNameFilter}
                  onChange={(event) => setDataObjectNameFilter(event.target.value)}
                  placeholder="contains..."
                  autoComplete="off"
                />
              </label>
              <label className="gx-monitor-filter-field gx-monitor-filter-wide" htmlFor="gx-delivery-id-filter">
                <span className="gx-monitor-label">Delivery id</span>
                <input
                  id="gx-delivery-id-filter"
                  className="gx-monitor-input"
                  type="text"
                  value={deliveryIdFilter}
                  onChange={(event) => setDeliveryIdFilter(event.target.value)}
                  placeholder="delivery-123"
                  autoComplete="off"
                />
              </label>
              <label className="gx-monitor-filter-field gx-monitor-filter-wide" htmlFor="gx-search-filter">
                <span className="gx-monitor-label">Search</span>
                <input
                  id="gx-search-filter"
                  className="gx-monitor-input"
                  type="text"
                  value={searchFilter}
                  onChange={(event) => setSearchFilter(event.target.value)}
                  placeholder="run id, correlation id, suite id, requested by..."
                  autoComplete="off"
                />
              </label>
            </div>

            <div className="gx-monitor-input-row gx-monitor-actions-row">
              <button className="feature-button" type="submit" disabled={recentRunsLoading}>
                {recentRunsLoading ? 'Loading…' : 'Refresh recent runs'}
              </button>
              <button
                className="gx-secondary-button"
                type="button"
                disabled={recentRunsLoading || exceptionAnalyticsLoading}
                onClick={() => {
                  setLookbackAmount(DEFAULT_LOOKBACK_AMOUNT)
                  setLookbackUnit(DEFAULT_LOOKBACK_UNIT)
                  setBrowseStatus('all')
                  setRuleNameFilter('')
                  setDataObjectNameFilter('')
                  setDeliveryIdFilter('')
                  setSearchFilter('')
                  void loadRecentRuns({
                    lookbackAmount: DEFAULT_LOOKBACK_AMOUNT,
                    lookbackUnit: DEFAULT_LOOKBACK_UNIT,
                    browseStatus: 'all',
                    ruleNameFilter: '',
                    dataObjectNameFilter: '',
                    deliveryIdFilter: '',
                    searchFilter: '',
                  })
                  void loadExceptionAnalytics({
                    lookbackAmount: DEFAULT_LOOKBACK_AMOUNT,
                    lookbackUnit: DEFAULT_LOOKBACK_UNIT,
                    browseStatus: 'all',
                    ruleNameFilter: '',
                    dataObjectNameFilter: '',
                    deliveryIdFilter: '',
                    searchFilter: '',
                  })
                }}
              >
                Reset filters
              </button>
            </div>
          </form>

          {recentRunsError && (
            <div className="gx-monitor-error" role="alert">
              <AppIcon name="close-circle" />
              <span>{recentRunsError}</span>
            </div>
          )}

          {!recentRunsError && exceptionAnalyticsError && (
            <div className="gx-monitor-error" role="alert">
              <AppIcon name="close-circle" />
              <span>{exceptionAnalyticsError}</span>
            </div>
          )}

          {!recentRunsError && !exceptionAnalyticsError && exceptionAnalyticsLoading && recentRuns.length > 0 && (
            <div className="feature-placeholder">
              <AppIcon name="search" />
              <p>Loading validation exception analytics…</p>
            </div>
          )}

          {!recentRunsError && !exceptionAnalyticsError && !exceptionAnalyticsLoading && exceptionAnalytics && recentRuns.length > 0 && (
            <div className="gx-monitor-insight-grid">
              <section className="gx-monitor-insight-card" aria-labelledby="gx-exception-volume-title">
                <div className="gx-monitor-insight-header">
                  <h4 id="gx-exception-volume-title">Exception volume</h4>
                  <span className="gx-monitor-badge gx-monitor-badge-info">MN-01d</span>
                </div>
                <p className="gx-monitor-insight-total">{pluralize(totalFailedRecords, 'failed record')}</p>
                <p className="gx-monitor-helper">
                  {runsWithFailures > 0
                    ? `${pluralize(runsWithFailures, 'run')} with failed records in the current monitoring window.`
                    : 'No failed records were reported in the current monitoring window.'}
                </p>
                <div className="gx-monitor-trend-bars" aria-label="Exception volume trend">
                  {exceptionTrendBuckets.map((bucket) => {
                    const heightPercent = maxExceptionBucketTotal > 0 ? Math.max((bucket.total / maxExceptionBucketTotal) * 100, bucket.total > 0 ? 12 : 0) : 0
                    const label = formatTrendBucketLabel(new Date(bucket.bucketStart).getTime(), lookbackUnit)
                    return (
                      <div key={`exception-trend-${bucket.bucketStart}`} className="gx-monitor-trend-bar-group">
                        <span className="gx-monitor-trend-value">{bucket.total}</span>
                        <div
                          className="gx-monitor-trend-bar"
                          title={`${label}: ${pluralize(bucket.total, 'failed record')}`}
                          style={{ height: `${heightPercent}%` }}
                        />
                        <span className="gx-monitor-trend-label">{label}</span>
                      </div>
                    )
                  })}
                </div>
              </section>

              <section className="gx-monitor-insight-card" aria-labelledby="gx-top-rules-title">
                <div className="gx-monitor-insight-header">
                  <h4 id="gx-top-rules-title">Top rules</h4>
                  <span className="gx-monitor-badge gx-monitor-badge-neutral">Failure hotspots</span>
                </div>
                {exceptionAnalytics.topRules.length === 0 ? (
                  <p className="gx-monitor-empty">No rule-level failed records in the current monitoring window.</p>
                ) : (
                  <ol className="gx-monitor-hotspot-list" aria-label="Top rules by failed records">
                    {exceptionAnalytics.topRules.map((entry) => (
                      <li key={`rule-hotspot-${entry.ruleId}`} className="gx-monitor-hotspot-row">
                        <div>
                          <strong>{entry.ruleName}</strong>
                          <div className="gx-monitor-table-subtext gx-monitor-mono">{entry.ruleId}</div>
                        </div>
                        <span className="gx-monitor-hotspot-total">{pluralize(entry.total, 'failed record')}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              <section className="gx-monitor-insight-card" aria-labelledby="gx-top-data-objects-title">
                <div className="gx-monitor-insight-header">
                  <h4 id="gx-top-data-objects-title">Top data objects</h4>
                  <span className="gx-monitor-badge gx-monitor-badge-neutral">Exception store summary</span>
                </div>
                {exceptionAnalytics.topDataObjects.length === 0 ? (
                  <p className="gx-monitor-empty">No data-object hotspots in the current monitoring window.</p>
                ) : (
                  <ol className="gx-monitor-hotspot-list" aria-label="Top data objects by failed records">
                    {exceptionAnalytics.topDataObjects.map((entry) => (
                      <li key={`object-hotspot-${entry.dataObjectVersionId}`} className="gx-monitor-hotspot-row">
                        <div>
                          <strong>{entry.dataObjectName}</strong>
                          <div className="gx-monitor-table-subtext gx-monitor-mono">{entry.dataObjectVersionId}</div>
                        </div>
                        <span className="gx-monitor-hotspot-total">{pluralize(entry.total, 'failed record')}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </div>
          )}

          {!recentRunsError && recentRuns.length === 0 && !recentRunsLoading ? (
            <div className="feature-placeholder">
              <AppIcon name="search" />
              <p>No validation runs matched the current browse filters.</p>
              <p className="placeholder-subtitle">Widen the time window or clear the rule and data object filters.</p>
            </div>
          ) : null}

          {recentRuns.length > 0 && (
            <div className="gx-monitor-table-shell">
              <table className="gx-monitor-table">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Status</th>
                    <th>Rule</th>
                    <th>Data objects</th>
                    <th>Submitted</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.map((item) => (
                    <tr key={item.id} className={trackedRunId === item.id ? 'is-active' : ''}>
                      <td>
                        <button
                          type="button"
                          className="gx-link-button"
                          onClick={() => void loadRun(item.id)}
                        >
                          {item.id}
                        </button>
                        <div className="gx-monitor-table-subtext">
                          {isGroupedScopeShape(item.executionShape)
                            ? 'Grouped scope run'
                            : formatSuiteIdentity(item.suiteId, item.suiteVersion)}
                        </div>
                        {item.runPlanId && <div className="gx-monitor-table-subtext gx-monitor-mono">Run plan {item.runPlanId}</div>}
                      </td>
                      <td><span className={`gx-monitor-badge gx-monitor-badge-status gx-status-${item.status}`}>{item.status}</span></td>
                      <td>
                        <div>{item.ruleName || item.ruleId || 'Grouped scope run'}</div>
                        <div className="gx-monitor-table-subtext gx-monitor-mono">{item.ruleId || item.executionShape}</div>
                      </td>
                      <td>
                        {item.dataObjectNames.length > 0 ? item.dataObjectNames.join(', ') : 'Not recorded'}
                        <div className="gx-monitor-table-subtext gx-monitor-mono">{item.dataObjectVersionId || 'n/a'}</div>
                      </td>
                      <td>
                        <div>{formatDateTime(item.submittedAt)}</div>
                        <div className="gx-monitor-table-subtext">{item.executionShape}</div>
                        {item.resolvedDataDeliveryId && (
                          <div className="gx-monitor-table-subtext gx-monitor-mono">Delivery {item.resolvedDataDeliveryId}</div>
                        )}
                      </td>
                      <td>
                        <button className="gx-secondary-button gx-monitor-row-button" type="button" onClick={() => void loadRun(item.id)}>
                          Open run
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="gx-monitor-panel">
          <div className="gx-monitor-panel-header">
            <div>
              <h3>Load a validation run</h3>
              <p className="gx-monitor-helper">
                Enter a run id returned by the validation start or schedule endpoints to inspect the persisted lifecycle.
              </p>
            </div>
            <div className="gx-monitor-panel-meta">
              <span className="gx-monitor-badge gx-monitor-badge-neutral">Direct lookup</span>
              {trackedRunId && <span className="gx-monitor-badge gx-monitor-badge-info">Tracking {trackedRunId}</span>}
            </div>
          </div>

          <form className="gx-monitor-form" onSubmit={handleRunSubmit}>
            <label className="gx-monitor-label" htmlFor="gx-run-id">
              Validation run id
            </label>
            <div className="gx-monitor-input-row">
              <input
                id="gx-run-id"
                className="gx-monitor-input"
                type="text"
                value={runIdInput}
                onChange={(event) => setRunIdInput(event.target.value)}
                placeholder="run-123abc456def"
                autoComplete="off"
              />
              <button className="feature-button" type="submit" disabled={isLoading}>
                {isLoading ? 'Loading…' : 'Load run'}
              </button>
              <button
                className="gx-secondary-button"
                type="button"
                disabled={isLoading || !trackedRunId}
                onClick={() => void loadRun(trackedRunId || runIdInput)}
              >
                Refresh
              </button>
            </div>
          </form>

          {runError && (
            <div className="gx-monitor-error" role="alert">
              <AppIcon name="close-circle" />
              <span>{runError}</span>
            </div>
          )}

          {!run && !runError && (
            <div className="feature-placeholder">
              <AppIcon name="play-circle" />
              <p>Load a validation run to inspect its persisted lifecycle.</p>
              <p className="placeholder-subtitle">The monitor shows run status, queue handoff metadata, and transition history.</p>
            </div>
          )}
        </section>

        {run && (
          <>
            <section className="gx-monitor-panel">
              <div className="gx-monitor-panel-header">
                <div>
                  <h3>Run summary</h3>
                  <p className="gx-monitor-helper">Last refreshed at {lastLoadedAt ? formatDateTime(lastLoadedAt) : 'Not loaded yet'}</p>
                </div>
                <div className="gx-monitor-badges">
                  <span className={`gx-monitor-badge gx-monitor-badge-status gx-status-${run.status}`}>{run.status}</span>
                  <span className="gx-monitor-badge">{run.executionShape}</span>
                  <span className="gx-monitor-badge">{run.engineTarget}</span>
                </div>
              </div>

              <div className="gx-monitor-summary-grid">
                <div className="gx-monitor-summary-card">
                  <span className="gx-monitor-summary-label">Run</span>
                  <strong className="gx-monitor-mono">{run.id}</strong>
                  <span className="gx-monitor-summary-muted">{groupedScopeLabel}</span>
                </div>
                <div className="gx-monitor-summary-card">
                  <span className="gx-monitor-summary-label">Execution engine</span>
                  <strong className="gx-monitor-mono">{run.engineTarget}</strong>
                  <span className="gx-monitor-summary-muted">
                    {executionPerformanceSummary?.executionPath
                      ? `${executionPerformanceSummary.executionPath} / ${executionPerformanceSummary.plannerChoice}`
                      : `Shape ${run.executionShape}`}
                  </span>
                </div>
                <div className="gx-monitor-summary-card">
                  <span className="gx-monitor-summary-label">Correlation</span>
                  <strong className="gx-monitor-mono">{run.correlationId}</strong>
                  <span className="gx-monitor-summary-muted">Requested by {run.requestedBy || 'system'}</span>
                </div>
                <div className="gx-monitor-summary-card">
                  <span className="gx-monitor-summary-label">Run plan</span>
                  <strong className="gx-monitor-mono">{run.runPlanId || 'Not recorded'}</strong>
                  <span className="gx-monitor-summary-muted">{run.suiteId ? `Suite ${run.suiteId}` : 'No suite recorded'}</span>
                </div>
                <div className="gx-monitor-summary-card">
                  <span className="gx-monitor-summary-label">Status</span>
                  <strong>{run.status}</strong>
                  <span className="gx-monitor-summary-muted">Submitted {formatDateTime(run.submittedAt)}</span>
                </div>
                <div className="gx-monitor-summary-card">
                  <span className="gx-monitor-summary-label">Delivery</span>
                  <strong className="gx-monitor-mono">{run.resolvedDataDeliveryId || 'Not recorded'}</strong>
                  <span className="gx-monitor-summary-muted">{run.suiteVersion ? `Suite v${run.suiteVersion}` : 'No suite version recorded'}</span>
                </div>
                <div className="gx-monitor-summary-card">
                  <span className="gx-monitor-summary-label">Lifecycle</span>
                  <strong>{run.startedAt ? 'Started' : 'Queued'}</strong>
                  <span className="gx-monitor-summary-muted">
                    {run.completedAt ? `Completed ${formatDateTime(run.completedAt)}` : `Updated ${formatDateTime(run.updatedAt)}`}
                  </span>
                </div>
                <div className="gx-monitor-summary-card gx-monitor-progress-card">
                  <span className="gx-monitor-summary-label">Executor progress</span>
                  <strong>{executionProgressPercent !== null ? `${executionProgressPercent}%` : 'Not recorded'}</strong>
                  <span className="gx-monitor-summary-muted">
                    {executionProgressLabel || 'Waiting for worker progress updates'}
                  </span>
                  <div
                    className="gx-monitor-progress-track"
                    role="progressbar"
                    aria-label="Executor progress"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={executionProgressPercent ?? 0}
                    aria-valuetext={executionProgressPercent !== null ? `${executionProgressPercent}%` : 'Progress not recorded'}
                  >
                    <div
                      className="gx-monitor-progress-fill"
                      style={{ width: `${executionProgressPercent ?? 0}%` }}
                    />
                  </div>
                  <span className="gx-monitor-summary-muted">
                    {executionProgressStepLabel || (executionProgress?.updatedAt ? `Updated ${formatDateTime(executionProgress.updatedAt)}` : 'No progress details recorded')}
                  </span>
                </div>
                <div className="gx-monitor-summary-card">
                  <span className="gx-monitor-summary-label">Performance snapshot</span>
                  <strong>{executionPerformanceSummary ? formatDurationMs(executionPerformanceSummary.runtimeMs) : 'Not recorded'}</strong>
                  <span className="gx-monitor-summary-muted">
                    {executionPerformanceSummary
                      ? `${formatMetricCount(executionPerformanceSummary.batchCount)} batches, ${formatMetricCount(executionPerformanceSummary.suiteCount)} suites`
                      : 'Worker performance summary not recorded yet'}
                  </span>
                </div>
              </div>

              <div className="gx-monitor-detail-grid">
                <div className="gx-monitor-detail-card">
                  <h4>Execution contract</h4>
                  {run.executionShape === 'grouped_scope' ? (
                    <>
                      <dl className="gx-monitor-dl">
                        <div>
                          <dt>Selection mode</dt>
                          <dd className="gx-monitor-mono">grouped_scope</dd>
                        </div>
                        <div>
                          <dt>Planned suites</dt>
                          <dd>{groupedSuiteCount !== null ? pluralize(groupedSuiteCount, 'suite') : 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Planned batches</dt>
                          <dd>{groupedBatchCount !== null ? pluralize(groupedBatchCount, 'batch') : 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Scope selector</dt>
                          <dd><pre className="gx-monitor-json">{formatJson(groupedExecutionContract?.scopeSelector ?? queueDetails?.scopeSelector ?? null)}</pre></dd>
                        </div>
                        <div>
                          <dt>Suite refs</dt>
                          <dd>
                            {groupedSuiteRefs.length > 0
                              ? groupedSuiteRefs.map((entry) => `${entry.suiteId} v${entry.suiteVersion}`).join(', ')
                              : 'Not recorded'}
                          </dd>
                        </div>
                      </dl>

                      {groupedBatchResults.length > 0 && (
                        <div className="gx-monitor-materialization">
                          <h5>Grouped batches</h5>
                          <dl className="gx-monitor-dl gx-monitor-dl-compact">
                            {groupedBatchResults.map((entry, index) => (
                              <div key={`${run.id}-grouped-batch-${index}`}>
                                <dt>{entry.targetDataObjectVersionId || `Batch ${index + 1}`}</dt>
                                <dd>
                                  {(entry.suiteCount !== null && entry.suiteCount !== undefined)
                                    ? pluralize(entry.suiteCount, 'suite')
                                    : 'suite count n/a'}
                                  {entry.executionShape ? ` | ${entry.executionShape}` : ''}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <dl className="gx-monitor-dl">
                        <div>
                          <dt>Rule</dt>
                          <dd className="gx-monitor-mono">{traceability?.ruleId || run.ruleId || 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Rule version</dt>
                          <dd className="gx-monitor-mono">{traceability?.ruleVersionId || run.ruleVersionId || 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Validation suite</dt>
                          <dd className="gx-monitor-mono">{traceability?.gxSuiteId || run.suiteId || 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Validation suite version</dt>
                          <dd>{traceability?.gxSuiteVersion ?? run.suiteVersion ?? 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Data object version</dt>
                          <dd className="gx-monitor-mono">{traceability?.dataObjectVersionId || 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Rule build</dt>
                          <dd className="gx-monitor-mono">{traceability?.artifactKey || 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Source rule expression</dt>
                          <dd className="gx-monitor-mono">{traceability?.sourceRuleExpression || 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Compiled expression</dt>
                          <dd className="gx-monitor-mono">{traceability?.compiledExpression || 'Not recorded'}</dd>
                        </div>
                      </dl>

                      {sourceMaterialization && (
                    <div className="gx-monitor-materialization">
                      <h5>Landing-zone materialization</h5>
                      <dl className="gx-monitor-dl gx-monitor-dl-compact">
                        <div>
                          <dt>Artifact</dt>
                          <dd className="gx-monitor-mono">{sourceMaterialization.landingZoneArtifactId}</dd>
                        </div>
                        <div>
                          <dt>Version</dt>
                          <dd className="gx-monitor-mono">{sourceMaterialization.landingZoneVersionId}</dd>
                        </div>
                        <div>
                          <dt>Output</dt>
                          <dd className="gx-monitor-mono">{sourceMaterialization.outputLocation}</dd>
                        </div>
                        <div>
                          <dt>Join</dt>
                          <dd>{sourceMaterialization.joinType} on {sourceMaterialization.joinKeys.join(', ') || 'n/a'}</dd>
                        </div>
                      </dl>
                    </div>
                      )}
                    </>
                  )}
                </div>

                <div className="gx-monitor-detail-card">
                  <h4>Queue handoff</h4>
                  <dl className="gx-monitor-dl">
                    <div>
                      <dt>Dispatch mode</dt>
                      <dd>{(queueDetails?.dispatchMode as string) || 'accepted'}</dd>
                    </div>
                    <div>
                      <dt>Executor target</dt>
                      <dd>{(queueDetails?.executorTarget as string) || 'dq-engine'}</dd>
                    </div>
                    <div>
                      <dt>Queue key</dt>
                      <dd className="gx-monitor-mono">{(queueDetails?.queueKey as string) || 'Not recorded'}</dd>
                    </div>
                    <div>
                      <dt>Queue message</dt>
                      <dd className="gx-monitor-mono">{(queueDetails?.queueMessageId as string) || 'Not recorded'}</dd>
                    </div>
                    <div>
                      <dt>Queue length</dt>
                      <dd>
                        {queueStatusLoading && 'Loading…'}
                        {!queueStatusLoading && queueStatus && String(queueStatus.queueLength)}
                        {!queueStatusLoading && !queueStatus && 'Not recorded'}
                      </dd>
                    </div>
                    <div>
                      <dt>Queue position</dt>
                      <dd>
                        {queueStatusLoading && 'Loading…'}
                        {!queueStatusLoading && queuePositionLabel}
                        {!queueStatusLoading && !queuePositionLabel && 'Not recorded'}
                      </dd>
                    </div>
                    <div>
                      <dt>Scheduled at</dt>
                      <dd>{formatDateTime((queueDetails?.scheduledAt as string) || null)}</dd>
                    </div>
                    <div>
                      <dt>Handoff ready</dt>
                      <dd>{String((queueDetails?.handoffReady as boolean) ?? false)}</dd>
                    </div>
                  </dl>

                  {queueStatusError && (
                    <div className="gx-monitor-error" role="alert">
                      <AppIcon name="close-circle" />
                      <span>{queueStatusError}</span>
                    </div>
                  )}

                  {sourceOverrides.length > 0 && (
                    <div className="gx-monitor-materialization gx-monitor-source-summary">
                      <div className="gx-monitor-section-heading-row">
                        <h5>Ad-hoc source delivery summary</h5>
                        {onNavigate && sourceOverrideDeliveryIds.length > 0 && (
                          <button className="gx-secondary-button" type="button" onClick={() => onNavigate('delivery-inventory')}>
                            Open Delivery Inventory
                          </button>
                        )}
                      </div>
                      <dl className="gx-monitor-dl gx-monitor-dl-compact">
                        <div>
                          <dt>Materialized targets</dt>
                          <dd>{pluralize(sourceOverrideTargetCount, 'target')}</dd>
                        </div>
                        <div>
                          <dt>Data deliveries</dt>
                          <dd>{pluralize(sourceOverrideDeliveryCount, 'delivery')}</dd>
                        </div>
                        <div>
                          <dt>Total rows</dt>
                          <dd>{sourceOverrideTotalRows !== null ? sourceOverrideTotalRows : 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Output formats</dt>
                          <dd>{sourceOverrideFormats.length > 0 ? sourceOverrideFormats.join(', ') : 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Delivery IDs</dt>
                          <dd className="gx-monitor-mono">{sourceOverrideDeliveryIds.length > 0 ? sourceOverrideDeliveryIds.join(', ') : 'Not recorded'}</dd>
                        </div>
                        <div>
                          <dt>Delivery locations</dt>
                          <dd className="gx-monitor-mono">{sourceOverrideDeliveryLocations.length > 0 ? sourceOverrideDeliveryLocations.join(', ') : 'Not recorded'}</dd>
                        </div>
                      </dl>

                      {sourceOverrideTargetResults.length > 0 && (
                        <div className="gx-monitor-target-results" aria-label="Materialized target delivery outcomes">
                          {sourceOverrideTargetResults.map((target, index) => {
                            const targetId = String(target.dataObjectVersionId || '').trim() || `target-${index + 1}`
                            const deliveryId = String(target.dataDeliveryId || '').trim()
                            const location = String(target.deliveryNote?.deliveryLocation || target.outputUri || '').trim()
                            const format = String(target.outputFormat || '').trim()
                            return (
                              <div className="gx-monitor-target-result" key={`${targetId}-${index}`}>
                                <strong className="gx-monitor-mono">{targetId}</strong>
                                <span>{pluralize(readOptionalNumber(target.rowCount) ?? 0, 'row')}</span>
                                {deliveryId && <span className="gx-monitor-mono">Delivery {deliveryId}</span>}
                                {format && <span>{format}</span>}
                                {location && <span className="gx-monitor-mono">{location}</span>}
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="gx-monitor-detail-card">
                  <h4>Execution performance</h4>
                  {executionPerformanceSummary ? (
                    <dl className="gx-monitor-dl">
                      <div>
                        <dt>Execution path</dt>
                        <dd className="gx-monitor-mono">{executionPerformanceSummary.executionPath}</dd>
                      </div>
                      <div>
                        <dt>Planner choice</dt>
                        <dd className="gx-monitor-mono">{executionPerformanceSummary.plannerChoice}</dd>
                      </div>
                      <div>
                        <dt>Runtime</dt>
                        <dd>{formatDurationMs(executionPerformanceSummary.runtimeMs)}</dd>
                      </div>
                      <div>
                        <dt>Suite count</dt>
                        <dd>{formatMetricCount(executionPerformanceSummary.suiteCount)}</dd>
                      </div>
                      <div>
                        <dt>Batch count</dt>
                        <dd>{formatMetricCount(executionPerformanceSummary.batchCount)}</dd>
                      </div>
                      <div>
                        <dt>Selected targets</dt>
                        <dd>{formatMetricCount(executionPerformanceSummary.selectedTargetCount)}</dd>
                      </div>
                      <div>
                        <dt>Data scanned rows</dt>
                        <dd>{formatMetricCount(executionPerformanceSummary.dataScannedRows)}</dd>
                      </div>
                      <div>
                        <dt>Data scanned bytes</dt>
                        <dd>{formatBytes(executionPerformanceSummary.dataScannedBytes)}</dd>
                      </div>
                    </dl>
                  ) : (
                    <p className="gx-monitor-empty">No execution performance summary has been recorded for this run yet.</p>
                  )}
                </div>

                <div className="gx-monitor-detail-card">
                  <h4>Outcome</h4>
                  <dl className="gx-monitor-dl gx-monitor-dl-compact">
                    <div>
                      <dt>Failure code</dt>
                      <dd className="gx-monitor-mono">{run.failureCode || 'None'}</dd>
                    </div>
                    <div>
                      <dt>Failure message</dt>
                      <dd>{run.failureMessage || 'None'}</dd>
                    </div>
                    <div>
                      <dt>Result summary</dt>
                      <dd><pre className="gx-monitor-json">{formatJson(run.resultSummary)}</pre></dd>
                    </div>
                  </dl>
                </div>

                <div className="gx-monitor-detail-card">
                  <h4>Run comments</h4>
                  <p className="gx-monitor-helper" style={{ marginTop: 0 }}>
                    Notes saved here stay with this validation run and are visible on the run detail page.
                  </p>
                  <label htmlFor="gx-run-comments" style={{ display: 'grid', gap: '8px' }}>
                    <span>Comments</span>
                    <textarea
                      id="gx-run-comments"
                      value={runCommentsDraft}
                      onChange={(event) => setRunCommentsDraft(event.target.value)}
                      placeholder="Optional comments for this run"
                      rows={5}
                    />
                  </label>
                  <div style={{ marginTop: '12px' }}>
                    <button
                      className="feature-button"
                      type="button"
                      onClick={() => void saveRunComments()}
                      disabled={runCommentsSaving || runCommentsDraft.trim() === String(run.comments || '').trim()}
                    >
                      {runCommentsSaving ? 'Saving…' : 'Save comments'}
                    </button>
                  </div>
                  {runCommentsError && (
                    <div className="gx-monitor-error" role="alert" style={{ marginTop: '12px' }}>
                      <AppIcon name="close-circle" />
                      <span>{runCommentsError}</span>
                    </div>
                  )}
                </div>

                <div className="gx-monitor-detail-card">
                  <h4>Diagnostics</h4>
                  {run.diagnostics.length === 0 ? (
                    <p className="gx-monitor-empty">No diagnostics recorded.</p>
                  ) : (
                    <ul className="gx-monitor-list">
                      {run.diagnostics.map((item, index) => (
                        <li key={`${run.id}-diagnostic-${index}`}>
                          <pre className="gx-monitor-json">{formatJson(item)}</pre>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </section>

            <section className="gx-monitor-panel">
              <div className="gx-monitor-panel-header">
                <div>
                  <h3>Status history</h3>
                  <p className="gx-monitor-helper">Lifecycle transitions are read from the dedicated GX history endpoint.</p>
                </div>
              </div>

              {historyError && (
                <div className="gx-monitor-error" role="alert">
                  <AppIcon name="close-circle" />
                  <span>{historyError}</span>
                </div>
              )}

              {!historyError && historyRows.length === 0 ? (
                <p className="gx-monitor-empty">No status history has been recorded yet.</p>
              ) : (
                <div className="gx-monitor-history-table">
                  <div className="gx-monitor-history-head">
                    <span>Changed at</span>
                    <span>From</span>
                    <span>To</span>
                    <span>Changed by</span>
                    <span>Reason</span>
                  </div>
                  {historyRows.map((entry) => (
                    <div key={entry.id} className="gx-monitor-history-row">
                      <span>{formatDateTime(entry.changedAt)}</span>
                      <span>{entry.fromStatus || 'n/a'}</span>
                      <span className={`gx-monitor-badge gx-monitor-badge-status gx-status-${entry.toStatus}`}>{entry.toStatus}</span>
                      <span>{entry.changedBy || 'system'}</span>
                      <span>{entry.reason ? normalizeValidationUiText(entry.reason) : 'No reason recorded'}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>

      <GxSuiteScopePickerModal
        isOpen={isScopePickerOpen}
        onClose={() => setIsScopePickerOpen(false)}
        onSelect={(selection) => {
          setIsScopePickerOpen(false)
          setScheduleScopeSelection(selection)
          setScheduleSuites([])
          setSelectedSuiteKey('')
          setScheduleSuitesError(null)
          setScheduleSubmitError(null)
          setScheduledDispatch(null)
          void loadScheduleSuites(selection)
        }}
      />
    </AppPageShell>
  )
}
