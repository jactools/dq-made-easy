import React, { useState, useMemo, useEffect, useCallback } from 'react'
import { useRules, useAuth, useSettings } from '../hooks/useContexts'
import { DataQualityMetrics } from './DataQualityMetrics'
import { ExecutionResultExplorer } from './ExecutionResultExplorer'
import { HealthScorecards } from './HealthScorecards'
import { Button } from './Button'
import { RuleDetailsModal } from './RuleDetailsModal'
import { ReconciliationWorkbench } from './ReconciliationWorkbench'
import { DiscussionPanel, normalizeDiscussionEntries } from './discussion/DiscussionPanel'
import { AppBanner, AppIcon, AppPageHeader, AppPageShell, AppTabs } from './app-primitives'
import { getUiTelemetryConnectionState, subscribeUiTelemetryConnectionState } from '../telemetry'
import type { Rule, RuleTestResult } from '../types/rules'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { snakeToCamel } from '../utils/caseConverters'
import './Reports.css'

interface ReportsProps {
  initialTab?: 'metrics' | 'agent-access' | 'data-definition' | 'result-explorer' | 'test-results' | 'incidents' | 'reconciliation'
  onNavigate?: (destination: string) => void
}

interface GroupedTestResults {
  rule: Rule
  results: RuleTestResult[]
}

interface SelectedAttributeLike {
  id?: string
  name?: string
  versionId?: string | number
  version_id?: string | number
  dataObjectId?: string
  data_object_id?: string
  dataObjectName?: string
  data_object_name?: string
  dataObjectVersion?: string | number
  data_object_version?: string | number
  datasetName?: string
  dataset_name?: string
  dataProductName?: string
  data_product_name?: string
}

interface TestResultPresentation {
  failureRate: string
  testDateLabel: string
  isPassed: boolean
  isPending: boolean
  selectedAttributes: SelectedAttributeLike[]
  selectedAttributeLabel: string
  selectedAttributeTitle: string
  targetObjectLabel: string
  targetVersionLabel: string
  targetSummaryLabel: string
  statusLabel: string
  coverageValue: number
  summaryLabel: string | null
}

interface IncidentListItem {
  id: string
  incidentKind: string
  status: string
  title: string
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
  assignedTo?: string | null
  resolvedAt?: string | null
  itsmTicketId?: string | null
  itsmTicketNumber?: string | null
  createdAt?: string | null
  updatedAt?: string | null
  comments?: Array<Record<string, unknown>>
  resolutionHistory?: Array<Record<string, unknown>>
}

interface IncidentsPagePayload {
  incidents: IncidentListItem[]
  count: number
  offset: number
  limit: number
}

interface RootCauseEvidenceItem {
  label: string
  value: string
}

interface IncidentRootCauseSuggestionItem {
  id: string
  workspaceId?: string | null
  incidentIds: string[]
  incidentCount: number
  suggestedRootCause: {
    kind: string
    title: string
    summary: string
    confidenceScore?: number | null
    recommendedAction?: string | null
    evidence?: RootCauseEvidenceItem[] | null
    signals?: Record<string, string> | null
  }
  status: string
  events?: Array<Record<string, unknown>>
  createdBy?: string | null
  createdAt?: string | null
  updatedBy?: string | null
  updatedAt?: string | null
  acceptedAt?: string | null
  rejectedAt?: string | null
  assistanceRequestedAt?: string | null
  assistanceRequestReferenceId?: string | null
  assistanceRequestTicketId?: string | null
  assistanceRequestTicketNumber?: string | null
  assistanceRequestTicketUrl?: string | null
  assistanceRequestTicketSystem?: string | null
  assistanceRequestDeliveryModes?: string[]
  assistanceRequestPayload?: Record<string, unknown> | null
}

interface RootCauseSuggestionsPagePayload {
  rootCauseSuggestions: IncidentRootCauseSuggestionItem[]
  count: number
  offset: number
  limit: number
}

interface DataDefinitionRequestRow {
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

interface DataDefinitionTaskStatusResponsePayload {
  success: boolean
  request: DataDefinitionRequestRow
}

interface AgentAuditEventRow {
  id: string
  requestId: string
  timestamp: string
  action: string
  endpoint: string
  method: string
  actorId: string | null
  correlationId: string | null
  agentType: string | null
  agentSource: string | null
  agentInstanceId: string | null
  requestOrigin: string | null
  userAgent: string | null
  responseType: string
  statusCode: number
  success: boolean
  details: Record<string, unknown>
  governanceContextRef?: Record<string, unknown>
}

interface AgentAuditEventListPayload {
  events: AgentAuditEventRow[]
  governanceMetadata: Record<string, unknown>
}

interface AgentAccessSummaryRow {
  key: string
  agentLabel: string
  targetLabel: string
  count: number
  firstSeenAt: string | null
  lastSeenAt: string | null
  latestStatusLabel: string
  latestStatusTone: string
  latestRequestOrigin: string
  latestActorLabel: string
}

const uniqueValues = (values: Array<string | null | undefined>): string[] => {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value))))
}

const formatAttributeLabel = (attribute: SelectedAttributeLike): string => {
  return String(
    attribute?.name ||
      attribute?.data_object_name ||
      attribute?.dataObjectName ||
      attribute?.dataset_name ||
      attribute?.datasetName ||
      attribute?.data_product_name ||
      attribute?.dataProductName ||
      attribute?.id ||
      attribute?.version_id ||
      attribute?.versionId ||
      attribute?.data_object_version ||
      'unknown',
  )
}

const humanizeLabel = (value: string): string => {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

const formatIncidentKindLabel = (value: string): string => {
  switch (value) {
    case 'technical_run_error':
      return 'Technical Run Error'
    case 'functional_violation':
      return 'Functional Violation'
    default:
      return humanizeLabel(value)
  }
}

const formatIncidentStatusLabel = (value: string): string => {
  switch (value) {
    case 'in_progress':
      return 'In Progress'
    case 'resolved':
      return 'Resolved'
    case 'closed':
      return 'Closed'
    case 'open':
      return 'Open'
    default:
      return humanizeLabel(value)
  }
}

const formatIncidentDate = (value?: string | null): string => {
  if (!value) {
    return 'Unknown'
  }

  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

const formatDataDefinitionDate = (value?: string | null): string => {
  if (!value) {
    return '—'
  }

  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

const formatAgentAccessDate = (value?: string | null): string => formatDataDefinitionDate(value)

const getAgentAccessAgentLabel = (event: AgentAuditEventRow): string => {
  return String(
    event.agentType ||
      event.agentSource ||
      event.agentInstanceId ||
      event.actorId ||
      'Unknown agent',
  )
}

const formatAgentAccessTargetLabel = (event: AgentAuditEventRow): string => {
  const actionLabel = humanizeLabel(String(event.action || 'access'))
  const endpointLabel = String(event.endpoint || '').trim() || 'Unknown endpoint'
  return `${actionLabel} · ${endpointLabel}`
}

const formatAgentAccessStatusLabel = (success: boolean): string => (success ? 'Success' : 'Failed')

const getAgentAccessStatusTone = (success: boolean): string => (success ? 'status-completed' : 'status-failed')

const formatAgentAccessRequestOrigin = (event: AgentAuditEventRow): string => {
  const parts: string[] = []

  if (event.requestOrigin) {
    parts.push(`Origin ${humanizeLabel(event.requestOrigin)}`)
  }
  if (event.agentSource && event.agentSource !== event.agentType) {
    parts.push(`Source ${event.agentSource}`)
  }
  if (event.agentInstanceId) {
    parts.push(`Instance ${event.agentInstanceId}`)
  }
  if (event.responseType) {
    parts.push(`Response ${event.responseType}`)
  }

  return parts.length > 0 ? parts.join(' · ') : 'No additional details'
}

const formatDataDefinitionStatusLabel = (value: string): string => {
  switch (value) {
    case 'pending':
      return 'Pending'
    case 'started':
      return 'Started'
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Failed'
    default:
      return humanizeLabel(value)
  }
}

const getDataDefinitionStatusTone = (value: string): string => {
  switch (value) {
    case 'started':
      return 'status-started'
    case 'completed':
      return 'status-completed'
    case 'failed':
      return 'status-failed'
    case 'pending':
    default:
      return 'status-pending'
  }
}

const getDataDefinitionStatusChangedAt = (request: DataDefinitionRequestRow): string | null => {
  switch (request.status) {
    case 'completed':
    case 'failed':
      return request.completedAt || request.startedAt || request.requestedAt
    case 'started':
      return request.startedAt || request.requestedAt
    case 'pending':
    default:
      return request.requestedAt
  }
}

const getIncidentSeverityTone = (severity?: string | null): string => {
  switch (String(severity || '').trim()) {
    case 'critical':
      return 'critical'
    case 'high':
      return 'high'
    case 'medium':
      return 'medium'
    case 'low':
      return 'low'
    default:
      return 'neutral'
  }
}

const formatIncidentSummary = (incident: IncidentListItem): string => {
  const parts: string[] = []

  if (incident.scopeKind && incident.scopeId) {
    parts.push(`${humanizeLabel(incident.scopeKind)} / ${incident.scopeId}`)
  }
  if (incident.runId) {
    parts.push(`Run ${incident.runId}`)
  }
  if (incident.runPlanId) {
    parts.push(`Run plan ${incident.runPlanId}`)
  }
  if (incident.assignedTo) {
    parts.push(`Assigned to ${incident.assignedTo}`)
  }
  if (incident.itsmTicketNumber) {
    parts.push(`Ticket ${incident.itsmTicketNumber}`)
  }

  return parts.length > 0 ? parts.join(' · ') : 'Workspace scoped'
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

const formatRootCauseConfidence = (value?: number | null): string => {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return 'Confidence unavailable'
  }

  return `${Math.round(Number(value) * 100)}% confidence`
}

const formatRootCauseEvidence = (evidence?: RootCauseEvidenceItem[] | null): string => {
  if (!Array.isArray(evidence) || evidence.length === 0) {
    return 'No evidence captured'
  }

  return evidence.map((item) => `${humanizeLabel(item.label)} ${item.value}`).join(' · ')
}

const sortIncidents = (left: IncidentListItem, right: IncidentListItem): number => {
  const leftTime = new Date(left.updatedAt || left.createdAt || 0).getTime()
  const rightTime = new Date(right.updatedAt || right.createdAt || 0).getTime()
  return rightTime - leftTime
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

const toRecord = (value: unknown): Record<string, any> => {
  return value && typeof value === 'object' ? value as Record<string, any> : {}
}

const getProofData = (testResult: RuleTestResult): Record<string, any> => {
  return toRecord((testResult as any)?.proof_data ?? (testResult as any)?.proofData)
}

const getProofValue = (proofData: Record<string, any>, ...fieldNames: string[]): unknown => {
  for (const fieldName of fieldNames) {
    const value = proofData[fieldName]
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      return value
    }
  }

  return undefined
}

const normalizeSearchValue = (value: unknown): string => String(value ?? '').trim().toLowerCase()

const tokenizeSearchQuery = (value: unknown): string[] => {
  return normalizeSearchValue(value)
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean)
}

const matchesSearchQuery = (searchableValues: Array<unknown>, query: string): boolean => {
  const queryTokens = tokenizeSearchQuery(query)

  if (queryTokens.length === 0) {
    return true
  }

  return searchableValues.some((value) => {
    const normalizedValue = normalizeSearchValue(value)
    return queryTokens.some((token) => normalizedValue.includes(token))
  })
}

const getTestTargetLabels = (proofData: Record<string, any>): {
  targetObjectLabel: string
  targetVersionLabel: string
  targetSummaryLabel: string
} => {
  const targetObjectLabel = String(
    getProofValue(
      proofData,
      'data_object_name',
      'dataObjectName',
      'source_name',
      'sourceName',
    ) || 'Data object',
  )
  const versionValue = getProofValue(
    proofData,
    'version_name',
    'versionName',
    'data_object_version',
    'dataObjectVersion',
  )
  const targetVersionLabel = versionValue === undefined || versionValue === null || String(versionValue).trim() === ''
    ? 'Version unavailable'
    : `Version ${String(versionValue)}`

  return {
    targetObjectLabel,
    targetVersionLabel,
    targetSummaryLabel: `${targetObjectLabel} · ${targetVersionLabel}`,
  }
}

const getFailureClassLabel = (failureClass: string): string => {
  switch (failureClass) {
    case 'value_mismatch':
      return 'Value Mismatch'
    case 'actuality_date_drift':
      return 'Actuality-Date Drift'
    case 'null_or_missing_join_key':
      return 'Null/Missing Join Key'
    default:
      return 'Other'
  }
}

const getTestResultPresentation = (testResult: RuleTestResult): TestResultPresentation => {
  const failureRate = testResult.recordsTestedCount > 0
    ? ((testResult.failuresFound / testResult.recordsTestedCount) * 100).toFixed(2)
    : '0.00'
  const testDateLabel = new Date(testResult.testDate).toLocaleString()
  const isPassed = testResult.status === 'passed'
  const isPending = testResult.status === 'pending'
  const metrics = testResult.metrics
  const diagnostics = Array.isArray(testResult.diagnostics) ? testResult.diagnostics : []
  const totalDiagnosticCount = diagnostics.reduce((sum, item) => sum + Number(item.count || 0), 0)
  const topDiagnostic = diagnostics
    .slice()
    .sort((a, b) => Number(b.count || 0) - Number(a.count || 0))[0]
  const proofData = getProofData(testResult)

  const summaryParts: string[] = []
  if (isPending) {
    summaryParts.push(String(getProofValue(proofData, 'request_message', 'requestMessage') || 'Execution in progress'))
  }
  if (metrics) {
    summaryParts.push(`Match ${metrics.matchRate.toFixed(2)}%`)
  }
  if (topDiagnostic) {
    summaryParts.push(`${getFailureClassLabel(topDiagnostic.failureClass)} ${topDiagnostic.count}`)
  }
  if (totalDiagnosticCount > 0) {
    summaryParts.push(`${totalDiagnosticCount} diagnostic failure${totalDiagnosticCount === 1 ? '' : 's'}`)
  }

  const selectedAttributes = Array.isArray(proofData.selected_attributes)
    ? proofData.selected_attributes
    : Array.isArray(proofData.selectedAttributes)
      ? proofData.selectedAttributes
    : []
  const targetLabels = getTestTargetLabels(proofData)
  const selectedAttributeLabel = selectedAttributes.length === 0
    ? 'N/A'
    : selectedAttributes.length <= 2
      ? selectedAttributes.map((attribute) => formatAttributeLabel(attribute)).join(', ')
      : `${selectedAttributes.slice(0, 2).map((attribute) => formatAttributeLabel(attribute)).join(', ')} +${selectedAttributes.length - 2}`
  const selectedAttributeTitle = selectedAttributes.length === 0
    ? 'No selected attributes recorded'
    : selectedAttributes.map((attribute) => formatAttributeLabel(attribute)).join(', ')
  const statusLabel = isPending
    ? 'Running'
    : isPassed
      ? '✓ Passed'
      : '✗ Failed'
  const coverageValue = Number.isFinite(Number(testResult.coverage)) ? Number(testResult.coverage) : 0

  return {
    failureRate,
    testDateLabel,
    isPassed,
    isPending,
    selectedAttributes,
    selectedAttributeLabel,
    selectedAttributeTitle,
    targetObjectLabel: targetLabels.targetObjectLabel,
    targetVersionLabel: targetLabels.targetVersionLabel,
    targetSummaryLabel: targetLabels.targetSummaryLabel,
    statusLabel,
    coverageValue,
    summaryLabel: summaryParts.length > 0 ? summaryParts.join(' · ') : null,
  }
}

export const Reports: React.FC<ReportsProps> = ({ initialTab = 'metrics', onNavigate }) => {
  const { rules } = useRules()
  const auth = useAuth()
  const settings = useSettings()
  const [activeTab, setActiveTab] = useState<'metrics' | 'agent-access' | 'data-definition' | 'result-explorer' | 'test-results' | 'incidents' | 'reconciliation'>(initialTab)
  const [telemetryConnectionState, setTelemetryConnectionState] = useState(getUiTelemetryConnectionState())
  const [expandedTestGroups, setExpandedTestGroups] = useState<Record<string, boolean>>({})
  const [ruleSearchInput, setRuleSearchInput] = useState('')
  const [detailsModalOpen, setDetailsModalOpen] = useState(false)
  const [detailsModalRule, setDetailsModalRule] = useState<any | null>(null)
  const [incidentRows, setIncidentRows] = useState<IncidentListItem[]>([])
  const [incidentLoading, setIncidentLoading] = useState(false)
  const [incidentError, setIncidentError] = useState<string | null>(null)
  const [incidentRootCauseSuggestions, setIncidentRootCauseSuggestions] = useState<IncidentRootCauseSuggestionItem[]>([])
  const [incidentRootCauseLoading, setIncidentRootCauseLoading] = useState(false)
  const [incidentRootCauseError, setIncidentRootCauseError] = useState<string | null>(null)
  const [selectedIncidentIds, setSelectedIncidentIds] = useState<string[]>([])
  const [rootCauseActionLoadingId, setRootCauseActionLoadingId] = useState<string | null>(null)
  const [rootCauseActionError, setRootCauseActionError] = useState<string | null>(null)
  const [refreshNonce, setRefreshNonce] = useState(0)
  const [agentAccessEvents, setAgentAccessEvents] = useState<AgentAuditEventRow[]>([])
  const [agentAccessLoading, setAgentAccessLoading] = useState(false)
  const [agentAccessError, setAgentAccessError] = useState<string | null>(null)
  const [dataDefinitionRequests, setDataDefinitionRequests] = useState<DataDefinitionRequestRow[]>([])
  const [dataDefinitionRequestsLoading, setDataDefinitionRequestsLoading] = useState(false)
  const [dataDefinitionRequestsError, setDataDefinitionRequestsError] = useState<string | null>(null)

  // Update activeTab when initialTab prop changes
  useEffect(() => {
    setActiveTab(initialTab)
  }, [initialTab])

  useEffect(() => subscribeUiTelemetryConnectionState(setTelemetryConnectionState), [])

  const currentWorkspaceId = String(auth.currentWorkspaceId || '').trim()

  const refreshAll = () => {
    setRefreshNonce((current) => current + 1)
  }

  const loadIncidents = useCallback(async () => {
    if (!currentWorkspaceId) {
      setIncidentRows([])
      setIncidentError('Select an active workspace to view workspace incidents.')
      setIncidentLoading(false)
      return
    }

    setIncidentLoading(true)
    setIncidentError(null)

    try {
      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const token = getAuthToken()
      const response = await fetch(
        `${apiBase}/incidents?workspace_id=${encodeURIComponent(currentWorkspaceId)}&limit=200&offset=0`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      )

      if (!response.ok) {
        throw new Error(`Unable to load workspace incidents (${response.status}).`)
      }

      const payload = snakeToCamel<IncidentsPagePayload>(await response.json())
      const incidents = Array.isArray(payload.incidents) ? payload.incidents.slice().sort(sortIncidents) : []
      setIncidentRows(incidents)
    } catch (loadError) {
      setIncidentRows([])
      setIncidentError(loadError instanceof Error ? loadError.message : 'Unable to load workspace incidents.')
    } finally {
      setIncidentLoading(false)
    }
  }, [currentWorkspaceId, settings.applicationSettings?.apiBaseUrl])

  const loadRootCauseSuggestions = useCallback(async () => {
    if (!currentWorkspaceId) {
      setIncidentRootCauseSuggestions([])
      setIncidentRootCauseError('Select an active workspace to view workspace incidents.')
      setIncidentRootCauseLoading(false)
      return
    }

    setIncidentRootCauseLoading(true)
    setIncidentRootCauseError(null)

    try {
      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const token = getAuthToken()
      const response = await fetch(
        `${apiBase}/incidents/root-cause-suggestions?workspace_id=${encodeURIComponent(currentWorkspaceId)}&limit=50&offset=0`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      )

      if (!response.ok) {
        throw new Error(`Unable to load workspace root cause suggestions (${response.status}).`)
      }

      const payload = snakeToCamel<RootCauseSuggestionsPagePayload>(await response.json())
      const suggestions = Array.isArray(payload.rootCauseSuggestions) ? payload.rootCauseSuggestions.slice() : []
      setIncidentRootCauseSuggestions(suggestions)
    } catch (loadError) {
      setIncidentRootCauseSuggestions([])
      setIncidentRootCauseError(loadError instanceof Error ? loadError.message : 'Unable to load workspace root cause suggestions.')
    } finally {
      setIncidentRootCauseLoading(false)
    }
  }, [currentWorkspaceId, settings.applicationSettings?.apiBaseUrl])

  const loadDataDefinitionRequests = useCallback(async () => {
    if (!currentWorkspaceId) {
      setDataDefinitionRequests([])
      setDataDefinitionRequestsError('Select an active workspace to view data-definition insights.')
      setDataDefinitionRequestsLoading(false)
      return
    }

    setDataDefinitionRequestsLoading(true)
    setDataDefinitionRequestsError(null)

    try {
      const apiBase = toApiGroupV1Base('data-catalog', settings.applicationSettings?.apiBaseUrl)
      const payload = await fetchJson<{ requests: DataDefinitionRequestRow[]; count: number }>(
        `${apiBase}/data-definition-tasks/requests?workspace_id=${encodeURIComponent(currentWorkspaceId)}&limit=50`,
        'Unable to load data-definition insights.',
      )

      const initialRequests = Array.isArray(payload.requests) ? payload.requests : []
      const nextRequests = await Promise.all(
        initialRequests.map(async (request) => {
          if (request.status !== 'started') {
            return request
          }

          try {
            const statusPayload = await fetchJson<DataDefinitionTaskStatusResponsePayload>(
              `${apiBase}/data-definition-tasks/requests/${encodeURIComponent(request.requestId)}/status`,
              `Unable to refresh data-definition request ${request.requestId}.`,
            )
            return statusPayload.request || request
          } catch {
            return request
          }
        }),
      )

      setDataDefinitionRequests(nextRequests)
    } catch (loadError) {
      setDataDefinitionRequests([])
      setDataDefinitionRequestsError(loadError instanceof Error ? loadError.message : 'Unable to load data-definition insights.')
    } finally {
      setDataDefinitionRequestsLoading(false)
    }
  }, [currentWorkspaceId, settings.applicationSettings?.apiBaseUrl])

  const loadAgentAccessEvents = useCallback(async () => {
    setAgentAccessLoading(true)
    setAgentAccessError(null)

    try {
      const apiBase = toApiGroupV1Base('agent', settings.applicationSettings?.apiBaseUrl)
      const payload = await fetchJson<AgentAuditEventListPayload>(
        `${apiBase}/audit/events?limit=200&offset=0`,
        'Unable to load agent access insights.',
      )

      setAgentAccessEvents(Array.isArray(payload.events) ? payload.events : [])
    } catch (loadError) {
      setAgentAccessEvents([])
      setAgentAccessError(loadError instanceof Error ? loadError.message : 'Unable to load agent access insights.')
    } finally {
      setAgentAccessLoading(false)
    }
  }, [settings.applicationSettings?.apiBaseUrl])

  useEffect(() => {
    if (activeTab !== 'incidents') {
      return
    }

    void loadIncidents()
    void loadRootCauseSuggestions()
  }, [activeTab, loadIncidents, loadRootCauseSuggestions])

  useEffect(() => {
    if (activeTab !== 'data-definition') {
      return
    }

    void loadDataDefinitionRequests()
  }, [activeTab, loadDataDefinitionRequests, refreshNonce])

  useEffect(() => {
    if (activeTab !== 'agent-access') {
      return
    }

    void loadAgentAccessEvents()
  }, [activeTab, loadAgentAccessEvents, refreshNonce])

  useEffect(() => {
    setSelectedIncidentIds([])
  }, [currentWorkspaceId])

  const currentWorkspaceRules = useMemo(() => {
    if (!auth.currentWorkspaceId) {
      return []
    }

    return rules.filter((rule) => rule.workspace === auth.currentWorkspaceId)
  }, [rules, auth.currentWorkspaceId])

  const dataDefinitionRequestsSorted = useMemo(
    () => [...dataDefinitionRequests].sort((left, right) => {
      const leftTime = new Date(left.requestedAt || left.startedAt || left.completedAt || 0).getTime()
      const rightTime = new Date(right.requestedAt || right.startedAt || right.completedAt || 0).getTime()
      return rightTime - leftTime
    }),
    [dataDefinitionRequests],
  )

  const dataDefinitionCounts = useMemo(() => ({
    total: dataDefinitionRequestsSorted.length,
    pending: dataDefinitionRequestsSorted.filter((request) => request.status === 'pending').length,
    started: dataDefinitionRequestsSorted.filter((request) => request.status === 'started').length,
    completed: dataDefinitionRequestsSorted.filter((request) => request.status === 'completed').length,
    failed: dataDefinitionRequestsSorted.filter((request) => request.status === 'failed').length,
  }), [dataDefinitionRequestsSorted])

  const agentAccessEventsSorted = useMemo(
    () => [...agentAccessEvents].sort((left, right) => {
      const leftTime = new Date(left.timestamp || 0).getTime()
      const rightTime = new Date(right.timestamp || 0).getTime()
      return rightTime - leftTime
    }),
    [agentAccessEvents],
  )

  const agentAccessSummaries = useMemo(() => {
    const summaryMap = new Map<string, AgentAccessSummaryRow & { lastSeenEpoch: number }>()

    for (const event of agentAccessEventsSorted) {
      const agentLabel = getAgentAccessAgentLabel(event)
      const targetLabel = formatAgentAccessTargetLabel(event)
      const key = `${agentLabel}|||${targetLabel}`
      const eventTime = new Date(event.timestamp || 0).getTime()
      const current = summaryMap.get(key)

      if (!current) {
        summaryMap.set(key, {
          key,
          agentLabel,
          targetLabel,
          count: 1,
          firstSeenAt: event.timestamp || null,
          lastSeenAt: event.timestamp || null,
          latestStatusLabel: formatAgentAccessStatusLabel(event.success),
          latestStatusTone: getAgentAccessStatusTone(event.success),
          latestRequestOrigin: formatAgentAccessRequestOrigin(event),
          latestActorLabel: event.actorId || 'Unknown actor',
          lastSeenEpoch: Number.isNaN(eventTime) ? 0 : eventTime,
        })
        continue
      }

      current.count += 1
      if ((current.firstSeenAt === null || eventTime < new Date(current.firstSeenAt).getTime()) && event.timestamp) {
        current.firstSeenAt = event.timestamp
      }
      if ((current.lastSeenAt === null || eventTime > new Date(current.lastSeenAt).getTime()) && event.timestamp) {
        current.lastSeenAt = event.timestamp
        current.latestStatusLabel = formatAgentAccessStatusLabel(event.success)
        current.latestStatusTone = getAgentAccessStatusTone(event.success)
        current.latestRequestOrigin = formatAgentAccessRequestOrigin(event)
        current.latestActorLabel = event.actorId || 'Unknown actor'
        current.lastSeenEpoch = Number.isNaN(eventTime) ? current.lastSeenEpoch : eventTime
      }
    }

    return Array.from(summaryMap.values())
      .sort((left, right) => right.lastSeenEpoch - left.lastSeenEpoch)
      .map(({ lastSeenEpoch: _lastSeenEpoch, ...summary }) => summary)
  }, [agentAccessEventsSorted])

  const agentAccessCounts = useMemo(() => ({
    total: agentAccessEventsSorted.length,
    agents: uniqueValues(agentAccessEventsSorted.map((event) => getAgentAccessAgentLabel(event))).length,
    targets: uniqueValues(agentAccessEventsSorted.map((event) => formatAgentAccessTargetLabel(event))).length,
    failed: agentAccessEventsSorted.filter((event) => !event.success).length,
    successful: agentAccessEventsSorted.filter((event) => event.success).length,
  }), [agentAccessEventsSorted])

  const searchQuery = normalizeSearchValue(ruleSearchInput)
  const activeSearchQuery = searchQuery.length >= 3 ? searchQuery : ''

  const testGroups = useMemo(() => {
    return currentWorkspaceRules
      .map((rule) => {
        const history = Array.isArray(rule.testResultsHistory) && rule.testResultsHistory.length > 0
          ? rule.testResultsHistory
          : rule.testResults
            ? [rule.testResults]
            : []

        const filteredHistory = history
          .filter((testResult) => {
            if (!activeSearchQuery) {
              return true
            }

            const presentation = getTestResultPresentation(testResult)
            const searchableValues = [
              rule.name,
              rule.description,
              rule.dimension,
              testResult.id,
              testResult.status,
              testResult.testDate,
              presentation.targetObjectLabel,
              presentation.targetVersionLabel,
              presentation.targetSummaryLabel,
              presentation.selectedAttributeLabel,
              presentation.summaryLabel,
              presentation.selectedAttributeTitle,
              getProofValue(getProofData(testResult), 'request_message', 'requestMessage'),
            ]

            return matchesSearchQuery(searchableValues, activeSearchQuery)
          })
          .slice()
          .sort((left, right) => new Date(right.testDate || 0).getTime() - new Date(left.testDate || 0).getTime())

        if (filteredHistory.length === 0) {
          return null
        }

        return {
          rule,
          results: filteredHistory,
        }
      })
    .filter((group): group is GroupedTestResults => group !== null)
    .sort((left, right) => {
      const leftTime = new Date(left.results[0]?.testDate || 0).getTime()
      const rightTime = new Date(right.results[0]?.testDate || 0).getTime()
      return rightTime - leftTime
    })
  }, [currentWorkspaceRules, activeSearchQuery])

  const mostRecentTest = (() => {
    const latestGroup = testGroups[0]
    const latestResult = latestGroup?.results[0]

    if (!latestGroup || !latestResult) {
      return null
    }

    return {
      rule: latestGroup.rule,
      result: latestResult,
      presentation: getTestResultPresentation(latestResult),
    }
  })()

  const testResultCount = testGroups.reduce((sum, group) => sum + group.results.length, 0)
  const incidentCounts = useMemo(() => ({
    total: incidentRows.length,
    open: incidentRows.filter((incident) => incident.status === 'open').length,
    active: incidentRows.filter((incident) => incident.status === 'in_progress').length,
    resolved: incidentRows.filter((incident) => incident.status === 'resolved' || incident.status === 'closed').length,
  }), [incidentRows])

  const sortRootCauseSuggestions = useCallback((left: IncidentRootCauseSuggestionItem, right: IncidentRootCauseSuggestionItem) => {
    const leftTime = new Date(left.updatedAt || left.createdAt || 0).getTime()
    const rightTime = new Date(right.updatedAt || right.createdAt || 0).getTime()
    return rightTime - leftTime
  }, [])

  const upsertRootCauseSuggestion = useCallback((nextSuggestion: IncidentRootCauseSuggestionItem) => {
    setIncidentRootCauseSuggestions((previous) => {
      const nextSuggestions = [
        nextSuggestion,
        ...previous.filter((suggestion) => suggestion.id !== nextSuggestion.id),
      ]

      return nextSuggestions.slice().sort(sortRootCauseSuggestions)
    })
  }, [sortRootCauseSuggestions])

  const toggleIncidentSelection = useCallback((incidentId: string) => {
    setSelectedIncidentIds((previous) => (
      previous.includes(incidentId)
        ? previous.filter((selectedIncidentId) => selectedIncidentId !== incidentId)
        : [...previous, incidentId]
    ))
  }, [])

  const clearIncidentSelection = useCallback(() => {
    setSelectedIncidentIds([])
  }, [])

  const handleRootCauseSuggestionAction = useCallback(async (
    action: 'create' | 'accept' | 'reject' | 'assistance-request',
    suggestionId?: string,
  ) => {
    if (action === 'create' && selectedIncidentIds.length === 0) {
      return
    }

    const targetId = suggestionId || 'create'
    setRootCauseActionLoadingId(targetId)
    setRootCauseActionError(null)

    try {
      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const token = getAuthToken()
      const path = action === 'create'
        ? `${apiBase}/incidents/root-cause-suggestions`
        : `${apiBase}/incidents/root-cause-suggestions/${encodeURIComponent(String(suggestionId || ''))}/${action}`
      const response = await fetch(path, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: action === 'create' ? JSON.stringify({ incident_ids: selectedIncidentIds }) : undefined,
      })

      const payload = await response.json().catch(() => null)
      if (!response.ok) {
        const detailMessage = typeof payload?.detail?.message === 'string'
          ? payload.detail.message
          : typeof payload?.message === 'string'
            ? payload.message
            : `Unable to ${action === 'create' ? 'create' : action.replace('-', ' ')} root cause suggestion (${response.status}).`
        throw new Error(detailMessage)
      }

      const normalized = snakeToCamel<{ rootCauseSuggestion: IncidentRootCauseSuggestionItem }>(payload)
      if (normalized.rootCauseSuggestion) {
        upsertRootCauseSuggestion(normalized.rootCauseSuggestion)
      }
      if (action === 'create') {
        clearIncidentSelection()
      }
    } catch (actionError) {
      setRootCauseActionError(actionError instanceof Error ? actionError.message : 'Unable to update the root cause suggestion.')
    } finally {
      setRootCauseActionLoadingId(null)
    }
  }, [clearIncidentSelection, selectedIncidentIds, settings.applicationSettings?.apiBaseUrl, upsertRootCauseSuggestion])

  const handleRuleClick = (ruleId: string) => {
    const clickedRule = rules.find((rule) => rule.id === ruleId) || { id: ruleId, name: ruleId } as any
    setDetailsModalRule(clickedRule)
    setDetailsModalOpen(true)
  }

  const closeDetailsModal = () => {
    setDetailsModalOpen(false)
    setDetailsModalRule(null)
  }

  const toggleTestGroup = (ruleId: string) => {
    setExpandedTestGroups((previous) => ({
      ...previous,
      [ruleId]: !previous[ruleId],
    }))
  }

  const handleTestGroupHeaderKeyDown = (
    event: React.KeyboardEvent<HTMLButtonElement>,
    ruleId: string,
    canExpand: boolean,
  ) => {
    if (!canExpand) {
      return
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggleTestGroup(ruleId)
    }
  }

  return (
    <AppPageShell className="reports-container">
      <AppPageHeader className="reports-header" title="Operations" description="Monitor validation health, result exploration, incidents, and reconciliation in one place.">
        <div className="reports-tabs-scroll">
          <AppTabs
            ariaLabel="Operations views"
            value={activeTab}
            onChange={setActiveTab}
            className="reports-tabs-control"
            tabs={[
              { value: 'metrics', label: 'Health Dashboard', title: 'Show Health Dashboard', iconName: 'line-chart' },
              { value: 'agent-access', label: 'Agent Access', title: 'Show Agent Access', iconName: 'shield-check' },
              { value: 'data-definition', label: 'Data-Definition Insights', title: 'Show Data-Definition Insights', iconName: 'document' },
              { value: 'result-explorer', label: 'Result Explorer', title: 'Show Result Explorer', iconName: 'search' },
              { value: 'test-results', label: 'Validation Test Results', title: 'Show Validation Test Results', iconName: 'list' },
              { value: 'incidents', label: 'Incidents', title: 'Show Incidents', iconName: 'exclamation-circle' },
              { value: 'reconciliation', label: 'Reconciliation', title: 'Show Reconciliation', iconName: 'table' },
            ]}
          />
        </div>
      </AppPageHeader>

      {telemetryConnectionState === 'unavailable' ? (
        <AppBanner variant="warning" className="reports-telemetry-banner">
          Observability is temporarily unavailable. Operations pages will retry automatically and resume telemetry when the connection returns.
        </AppBanner>
      ) : null}

      {activeTab === 'metrics' && (
        <div className="reports-content">
          <HealthScorecards
            workspaceId={auth.currentWorkspaceId}
            apiBaseUrl={settings.applicationSettings?.apiBaseUrl || ''}
            onRuleSelect={handleRuleClick}
            onNavigate={onNavigate}
          />
          <DataQualityMetrics
            rules={currentWorkspaceRules}
            onRuleClick={handleRuleClick}
          />
        </div>
      )}

      {activeTab === 'agent-access' && (
        <div className="reports-content">
          <div className="latest-test-summary">
            <div className="latest-test-summary-header">
              <div>
                <p className="latest-test-summary-kicker">Agent access audit</p>
                <h3>AI agent access insights</h3>
                <p className="incident-workspace-label">
                  Monitor which agent accessed which endpoint, how often, and when.
                </p>
                <p className="incident-workspace-label">
                  Showing the latest agent audit events available to the app.
                </p>
              </div>
              <Button onClick={refreshAll}>Refresh</Button>
            </div>

            <div className="latest-test-summary-grid incident-summary-grid">
              <div className="latest-test-summary-metric">
                <span>Total events</span>
                <strong>{agentAccessCounts.total}</strong>
                <p>Recent agent audit records</p>
              </div>
              <div className="latest-test-summary-metric">
                <span>Agents observed</span>
                <strong>{agentAccessCounts.agents}</strong>
                <p>Distinct agent identities</p>
              </div>
              <div className="latest-test-summary-metric">
                <span>Unique targets</span>
                <strong>{agentAccessCounts.targets}</strong>
                <p>Different actions and endpoints</p>
              </div>
              <div className="latest-test-summary-metric">
                <span>Successful / failed</span>
                <strong>{agentAccessCounts.successful} / {agentAccessCounts.failed}</strong>
                <p>Latest result window</p>
              </div>
            </div>
          </div>

          {agentAccessLoading ? (
            <div className="empty-results">
              <p>Loading agent access events…</p>
            </div>
          ) : agentAccessError ? (
            <div className="empty-results">
              <p>{agentAccessError}</p>
            </div>
          ) : agentAccessSummaries.length === 0 ? (
            <div className="empty-results">
              <p>No agent access audit events found.</p>
            </div>
          ) : (
            <div className="results-table">
              <div
                className="table-header"
                style={{ gridTemplateColumns: '1.2fr 1.8fr 0.6fr 1fr 1fr 0.9fr 1.2fr' }}
              >
                <div className="column rule-group">Agent</div>
                <div className="column target">Accessed what</div>
                <div className="column status">Count</div>
                <div className="column test-date">First seen</div>
                <div className="column test-date">Last seen</div>
                <div className="column status">Latest status</div>
                <div className="column target">Latest details</div>
              </div>

              {agentAccessSummaries.map((summary) => (
                <div
                  key={summary.key}
                  className="table-row agent-access-table-row"
                  style={{ gridTemplateColumns: '1.2fr 1.8fr 0.6fr 1fr 1fr 0.9fr 1.2fr' }}
                >
                  <div className="column rule-group">
                    <div className="rule-group-text no-toggle">
                      <strong>{summary.agentLabel}</strong>
                      <span>{summary.latestActorLabel}</span>
                    </div>
                  </div>
                  <div className="column target agent-access-target-column">
                    <div className="target-stack agent-access-target-stack">
                      <strong>{summary.targetLabel}</strong>
                      <span>{summary.latestRequestOrigin}</span>
                    </div>
                  </div>
                  <div className="column status">
                    <span className="status-badge status-started agent-access-count-badge">
                      {summary.count}
                    </span>
                  </div>
                  <div className="column test-date">{formatAgentAccessDate(summary.firstSeenAt)}</div>
                  <div className="column test-date">{formatAgentAccessDate(summary.lastSeenAt)}</div>
                  <div className="column status">
                    <span className={`status-badge ${summary.latestStatusTone}`}>
                      {summary.latestStatusLabel}
                    </span>
                  </div>
                  <div className="column target agent-access-details-column">
                    <span className="agent-access-details">{summary.latestRequestOrigin}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'data-definition' && (
        <div className="reports-content">
          <div className="latest-test-summary">
            <div className="latest-test-summary-header">
              <div>
                <p className="latest-test-summary-kicker">Data-definition requests</p>
                <h3>Workspace request insights</h3>
                <p className="incident-workspace-label">
                  {currentWorkspaceId ? `Current workspace: ${currentWorkspaceId}` : 'No workspace selected'}
                </p>
                <p className="incident-workspace-label">
                  Request counts, runtime timestamps, and any recorded error messages for generated business-term tasks.
                </p>
              </div>
              <Button onClick={refreshAll}>Refresh</Button>
            </div>

            <div className="latest-test-summary-grid incident-summary-grid">
              <div className="latest-test-summary-metric">
                <span>Total</span>
                <strong>{dataDefinitionCounts.total}</strong>
                <p>Requests in the selected workspace</p>
              </div>
              <div className="latest-test-summary-metric">
                <span>Pending</span>
                <strong>{dataDefinitionCounts.pending}</strong>
                <p>Waiting to start</p>
              </div>
              <div className="latest-test-summary-metric">
                <span>Started</span>
                <strong>{dataDefinitionCounts.started}</strong>
                <p>Currently running</p>
              </div>
              <div className="latest-test-summary-metric">
                <span>Completed / Failed</span>
                <strong>{dataDefinitionCounts.completed} / {dataDefinitionCounts.failed}</strong>
                <p>Terminal requests</p>
              </div>
            </div>
          </div>

          {dataDefinitionRequestsLoading ? (
            <div className="empty-results">
              <p>Loading data-definition requests…</p>
            </div>
          ) : dataDefinitionRequestsError ? (
            <div className="empty-results">
              <p>{dataDefinitionRequestsError}</p>
            </div>
          ) : dataDefinitionRequestsSorted.length === 0 ? (
            <div className="empty-results">
              <p>No data-definition requests found for the selected workspace.</p>
            </div>
          ) : (
            <div className="results-table">
              <div
                className="table-header"
                style={{ gridTemplateColumns: '2.3fr 0.9fr 1.2fr 1.2fr 1.2fr 1.2fr 1.6fr' }}
              >
                <div className="column rule-group">Request</div>
                <div className="column status">Status</div>
                <div className="column test-date">Requested</div>
                <div className="column test-date">Started</div>
                <div className="column test-date">Ended</div>
                <div className="column test-date">Status changed</div>
                <div className="column target">Error message</div>
              </div>

              {dataDefinitionRequestsSorted.map((request) => {
                const statusChangedAt = getDataDefinitionStatusChangedAt(request)

                return (
                  <div
                    key={request.requestId}
                    className="table-row data-definition-table-row"
                    style={{ gridTemplateColumns: '2.3fr 0.9fr 1.2fr 1.2fr 1.2fr 1.2fr 1.6fr' }}
                  >
                    <div className="column rule-group">
                      <div className="rule-group-text no-toggle">
                        <strong>{request.prompt}</strong>
                        <span>{request.requestId}</span>
                      </div>
                    </div>
                    <div className="column status">
                      <span className={`status-badge ${getDataDefinitionStatusTone(request.status)}`}>
                        {formatDataDefinitionStatusLabel(request.status)}
                      </span>
                    </div>
                    <div className="column test-date">{formatDataDefinitionDate(request.requestedAt)}</div>
                    <div className="column test-date">{formatDataDefinitionDate(request.startedAt)}</div>
                    <div className="column test-date">{formatDataDefinitionDate(request.completedAt)}</div>
                    <div className="column test-date">{formatDataDefinitionDate(statusChangedAt)}</div>
                    <div className="column target data-definition-error-column">
                      <span
                        className="execution-inline-summary data-definition-error-message"
                        title={request.errorMessage || 'No error message recorded'}
                      >
                        {request.errorMessage || 'No error message'}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {activeTab === 'result-explorer' && (
                  <ExecutionResultExplorer onNavigate={onNavigate} />
      )}

      {activeTab === 'test-results' && (
        <div className="reports-content">
          <div className="test-results-section">
            <div className="reports-search-panel">
              <span>Search</span>
              <div className="reports-search-row">
                <input
                  id="rule-search"
                  type="search"
                  aria-label="Search"
                  value={ruleSearchInput}
                  onChange={(event) => setRuleSearchInput(event.target.value)}
                  onInput={(event) => setRuleSearchInput((event.target as HTMLInputElement).value)}
                  placeholder="Type 3+ characters to search..."
                />
                <AppIcon name="search" className="reports-search-icon" />
              </div>
            </div>

            {mostRecentTest && (
              <div className="latest-test-summary">
                <div className="latest-test-summary-header">
                  <div>
                    <p className="latest-test-summary-kicker">Most recent test</p>
                    <h3>{mostRecentTest.rule.name}</h3>
                  </div>
                  <Button onClick={() => handleRuleClick(mostRecentTest.rule.id)}>
                    Open details
                  </Button>
                </div>

                <div className="latest-test-summary-grid">
                  <div className="latest-test-summary-metric">
                    <span>Target</span>
                    <strong>{mostRecentTest.presentation.targetSummaryLabel}</strong>
                    <p>{mostRecentTest.presentation.selectedAttributeLabel}</p>
                  </div>
                  <div className="latest-test-summary-metric">
                    <span>Status</span>
                    <strong>{mostRecentTest.presentation.statusLabel}</strong>
                    <p>{mostRecentTest.presentation.testDateLabel}</p>
                  </div>
                  <div className="latest-test-summary-metric">
                    <span>DQ Score</span>
                    <strong>{mostRecentTest.presentation.isPending ? 'Pending' : `${mostRecentTest.presentation.coverageValue}%`}</strong>
                    <p>{mostRecentTest.presentation.summaryLabel || 'No execution summary recorded'}</p>
                  </div>
                  <div className="latest-test-summary-metric">
                    <span>Dimension</span>
                    <strong>{mostRecentTest.rule.dimension || '—'}</strong>
                    <p>{mostRecentTest.result.id}</p>
                  </div>
                </div>
              </div>
            )}

            <div className="test-results-content">
              {testResultCount === 0 ? (
                <div className="empty-results">
                  <p>{activeSearchQuery ? 'No test results found matching your search' : 'No test results found'}</p>
                </div>
              ) : (
                <div className="results-table">
                  <div className="table-header">
                    <div className="column rule-group">Rule</div>
                    <div className="column target">Target Version</div>
                    <div className="column status">Status</div>
                    <div className="column test-date">Test Date</div>
                    <div className="column coverage">DQ Score</div>
                    <div className="column failures">Failures</div>
                    <div className="column dimension">DAMA Dimension</div>
                  </div>

                  {testGroups.map(({ rule, results }) => {
                    const latestResult = results[0]
                    const previousResults = results.slice(1)
                    const canExpand = previousResults.length > 0
                    const isExpanded = Boolean(expandedTestGroups[rule.id])
                    const latestPresentation = getTestResultPresentation(latestResult)
                    const visibleHistoryResults = isExpanded ? previousResults : []
                    const historySummaryLabel = canExpand
                      ? `${results.length} test runs · ${previousResults.length} previous hidden`
                      : `${results.length} test run${results.length === 1 ? '' : 's'}`

                    return (
                      <div key={rule.id} className="table-group">
                        <div
                          className="table-row table-row-group table-row-latest"
                          onClick={() => handleRuleClick(rule.id)}
                        >
                          <div className="column rule-group">
                            {canExpand ? (
                              <button
                                type="button"
                                className="rule-group-toggle"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  toggleTestGroup(rule.id)
                                }}
                                onKeyDown={(event) => handleTestGroupHeaderKeyDown(event, rule.id, canExpand)}
                                aria-expanded={isExpanded}
                                aria-label={`${isExpanded ? 'Collapse' : 'Expand'} test history for ${rule.name}`}
                              >
                                <span
                                  className={`rule-group-chevron ${isExpanded ? 'expanded' : ''}`}
                                  aria-hidden="true"
                                />
                                <span className="rule-group-text">
                                  <strong>{rule.name}</strong>
                                  <span>{historySummaryLabel}</span>
                                </span>
                              </button>
                            ) : (
                              <div className="rule-group-text no-toggle">
                                <strong>{rule.name}</strong>
                                <span>{historySummaryLabel}</span>
                              </div>
                            )}
                          </div>
                          <div className="column target">
                            <div className="target-stack">
                              <div className="target-version-row">
                                <strong>{latestPresentation.targetVersionLabel}</strong>
                              </div>
                              <span className="target-object-label">{latestPresentation.targetObjectLabel}</span>
                              <span
                                className="execution-inline-summary"
                                title={latestPresentation.selectedAttributeTitle}
                              >
                                {latestPresentation.selectedAttributeLabel}
                              </span>
                              {latestPresentation.summaryLabel && (
                                <span
                                  className="execution-inline-summary"
                                  title={latestPresentation.summaryLabel}
                                >
                                  {latestPresentation.summaryLabel}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="column status">
                            <span className={`status-badge dq-status-badge status-${latestResult.status}`}>
                              {latestPresentation.statusLabel}
                            </span>
                          </div>
                          <div className="column test-date">{latestPresentation.testDateLabel}</div>
                          <div className="column coverage">
                            <div className="coverage-bar">
                              <div
                                className="coverage-fill"
                                style={{ width: `${latestPresentation.isPending ? 0 : latestPresentation.coverageValue}%` }}
                              />
                            </div>
                            <span className="coverage-text">
                              {latestPresentation.isPending ? 'Pending' : `${latestPresentation.coverageValue}%`}
                            </span>
                          </div>
                          <div className="column failures">
                            <span className={latestPresentation.isPending ? 'failures-pending' : latestPresentation.isPassed ? 'failures-pass' : 'failures-fail'}>
                              {latestPresentation.isPending
                                ? 'In progress'
                                : `${latestResult.failuresFound.toLocaleString()} (${latestPresentation.failureRate}%)`}
                            </span>
                          </div>
                          <div className="column dimension">
                            {rule.dimension || '—'}
                          </div>
                        </div>

                        {visibleHistoryResults.map((testResult) => {
                          const presentation = getTestResultPresentation(testResult)

                          return (
                            <div
                              key={`${rule.id}-${testResult.id}`}
                              className="table-row table-row-history"
                              onClick={() => handleRuleClick(rule.id)}
                            >
                              <div className="column rule-group">
                                <div className="history-rule-label">
                                  <span className="history-branch" aria-hidden="true" />
                                  <span>Previous run</span>
                                </div>
                              </div>
                              <div className="column target">
                                <div className="target-stack">
                                  <div className="target-version-row">
                                    <strong>{presentation.targetVersionLabel}</strong>
                                  </div>
                                  <span className="target-object-label">{presentation.targetObjectLabel}</span>
                                  <span
                                    className="execution-inline-summary"
                                    title={presentation.selectedAttributeTitle}
                                  >
                                    {presentation.selectedAttributeLabel}
                                  </span>
                                  {presentation.summaryLabel && (
                                    <span
                                      className="execution-inline-summary"
                                      title={presentation.summaryLabel}
                                    >
                                      {presentation.summaryLabel}
                                    </span>
                                  )}
                                </div>
                              </div>
                              <div className="column status">
                                <span className={`status-badge dq-status-badge status-${testResult.status}`}>
                                  {presentation.statusLabel}
                                </span>
                              </div>
                              <div className="column test-date">{presentation.testDateLabel}</div>
                              <div className="column coverage">
                                <div className="coverage-bar">
                                  <div
                                    className="coverage-fill"
                                    style={{ width: `${presentation.isPending ? 0 : presentation.coverageValue}%` }}
                                  />
                                </div>
                                <span className="coverage-text">
                                  {presentation.isPending ? 'Pending' : `${presentation.coverageValue}%`}
                                </span>
                              </div>
                              <div className="column failures">
                                <span className={presentation.isPending ? 'failures-pending' : presentation.isPassed ? 'failures-pass' : 'failures-fail'}>
                                  {presentation.isPending
                                    ? 'In progress'
                                    : `${testResult.failuresFound.toLocaleString()} (${presentation.failureRate}%)`}
                                </span>
                              </div>
                              <div className="column dimension">
                                {rule.dimension || '—'}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )
                  })}
                </div>
              )}

              <div className="results-summary">
                <p>Showing {testResultCount} test result{testResultCount !== 1 ? 's' : ''} across {testGroups.length} rule{testGroups.length === 1 ? '' : 's'}</p>
                {activeSearchQuery && (
                  <p className="filter-info">filtered by search: "{activeSearchQuery}"</p>
                )}
              </div>
            </div>
        </div>
      </div>
      )}

      {activeTab === 'incidents' && (
        <div className="reports-content">
          <div className="incident-list-section">
            <div className="latest-test-summary">
              <div className="latest-test-summary-header">
                <div>
                  <p className="latest-test-summary-kicker">Workspace incidents</p>
                  <h3>Workspace incidents</h3>
                  <p className="incident-workspace-label">
                    {currentWorkspaceId ? `Current workspace: ${currentWorkspaceId}` : 'No workspace selected'}
                  </p>
                  <p className="incident-workspace-label">
                    Metadata-only triage view. Source records, row values, and failure payloads are not shown here.
                  </p>
                </div>
              </div>

              <div className="latest-test-summary-grid incident-summary-grid">
                <div className="latest-test-summary-metric">
                  <span>Total</span>
                  <strong>{incidentCounts.total}</strong>
                  <p>Workspace related incidents</p>
                </div>
                <div className="latest-test-summary-metric">
                  <span>Open</span>
                  <strong>{incidentCounts.open}</strong>
                  <p>Waiting for triage</p>
                </div>
                <div className="latest-test-summary-metric">
                  <span>In Progress</span>
                  <strong>{incidentCounts.active}</strong>
                  <p>Being worked on</p>
                </div>
                <div className="latest-test-summary-metric">
                  <span>Resolved</span>
                  <strong>{incidentCounts.resolved}</strong>
                  <p>Closed or resolved</p>
                </div>
              </div>
            </div>

            <div className="incident-root-cause-toolbar">
              <div className="incident-root-cause-toolbar-copy">
                <p className="incident-root-cause-toolbar-kicker">Root cause suggestions</p>
                <strong>
                  {selectedIncidentIds.length > 0
                    ? `${selectedIncidentIds.length} incident${selectedIncidentIds.length === 1 ? '' : 's'} selected`
                    : 'Select one or more incidents to generate a persisted root cause suggestion'}
                </strong>
                <p>
                  Suggestions are stored in Postgres and can be accepted, rejected, or sent to assistance with the evidence attached.
                </p>
              </div>
              <div className="incident-root-cause-toolbar-actions">
                <Button
                  variant="secondary"
                  disabled={selectedIncidentIds.length === 0 || rootCauseActionLoadingId === 'create'}
                  onClick={() => void handleRootCauseSuggestionAction('create')}
                >
                  {rootCauseActionLoadingId === 'create' ? 'Creating…' : 'Suggest root cause'}
                </Button>
                <Button
                  variant="tertiary"
                  disabled={selectedIncidentIds.length === 0}
                  onClick={clearIncidentSelection}
                >
                  Clear selection
                </Button>
              </div>
            </div>

            {rootCauseActionError && (
              <div className="empty-results">
                <p>{rootCauseActionError}</p>
              </div>
            )}

            {incidentRootCauseLoading && (
              <div className="empty-results">
                <p>Loading persisted root cause suggestions…</p>
              </div>
            )}

            {incidentRootCauseError && (
              <div className="empty-results">
                <p>{incidentRootCauseError}</p>
              </div>
            )}

            {incidentRootCauseSuggestions.length > 0 && (
              <section className="incident-root-cause-panel">
                <div className="incident-root-cause-panel-header">
                  <div>
                    <p className="incident-root-cause-toolbar-kicker">Persisted suggestions</p>
                    <h4>Recent root cause suggestions</h4>
                  </div>
                  <p>{incidentRootCauseSuggestions.length} suggestion{incidentRootCauseSuggestions.length === 1 ? '' : 's'} stored for this workspace</p>
                </div>
                <div className="incident-root-cause-list">
                  {incidentRootCauseSuggestions.map((suggestion) => {
                    const confidenceLabel = formatRootCauseConfidence(suggestion.suggestedRootCause.confidenceScore)
                    const evidenceLabel = formatRootCauseEvidence(suggestion.suggestedRootCause.evidence)
                    const suggestionActionDisabled = rootCauseActionLoadingId === suggestion.id

                    return (
                      <article key={suggestion.id} className="incident-root-cause-card">
                        <div className="incident-card-header">
                          <div className="incident-card-title-group">
                            <p className="incident-card-kicker">{humanizeLabel(suggestion.suggestedRootCause.kind)}</p>
                            <h4>{suggestion.suggestedRootCause.title}</h4>
                            <p className="incident-card-id">Suggestion ID: {suggestion.id}</p>
                          </div>
                          <div className="incident-chip-row">
                            <span className={`incident-chip incident-chip-status incident-status-${suggestion.status}`}>
                              {formatIncidentStatusLabel(suggestion.status)}
                            </span>
                            <span className="incident-chip incident-chip-neutral">{confidenceLabel}</span>
                          </div>
                        </div>

                        <div className="incident-detail-grid">
                          <div className="incident-detail">
                            <span>Summary</span>
                            <strong>{suggestion.suggestedRootCause.summary}</strong>
                          </div>
                          <div className="incident-detail">
                            <span>Incidents</span>
                            <strong>{suggestion.incidentCount}</strong>
                          </div>
                          <div className="incident-detail">
                            <span>Updated</span>
                            <strong>{formatIncidentDate(suggestion.updatedAt || suggestion.createdAt)}</strong>
                          </div>
                          <div className="incident-detail">
                            <span>Assistance</span>
                            <strong>{suggestion.assistanceRequestTicketNumber || suggestion.assistanceRequestReferenceId || 'Not requested'}</strong>
                          </div>
                        </div>

                        <div className="incident-supporting-copy">
                          <p><strong>Recommended action:</strong> {suggestion.suggestedRootCause.recommendedAction || 'Review the incident cluster.'}</p>
                          <p><strong>Evidence:</strong> {evidenceLabel}</p>
                          {suggestion.assistanceRequestedAt && (
                            <p>
                              <strong>Assistance request:</strong> {suggestion.assistanceRequestTicketSystem || 'support'}
                              {suggestion.assistanceRequestTicketNumber ? ` ticket ${suggestion.assistanceRequestTicketNumber}` : ''}
                            </p>
                          )}
                        </div>

                        <div className="incident-suggestion-actions">
                          <Button
                            variant="secondary"
                            disabled={suggestionActionDisabled}
                            onClick={() => void handleRootCauseSuggestionAction('accept', suggestion.id)}
                          >
                            Accept
                          </Button>
                          <Button
                            variant="secondary"
                            destructive
                            disabled={suggestionActionDisabled}
                            onClick={() => void handleRootCauseSuggestionAction('reject', suggestion.id)}
                          >
                            Reject
                          </Button>
                          <Button
                            disabled={suggestionActionDisabled || Boolean(suggestion.assistanceRequestedAt)}
                            onClick={() => void handleRootCauseSuggestionAction('assistance-request', suggestion.id)}
                          >
                            {suggestion.assistanceRequestedAt ? 'Assistance requested' : 'Request assistance'}
                          </Button>
                        </div>
                      </article>
                    )
                  })}
                </div>
              </section>
            )}

            {incidentLoading ? (
              <div className="empty-results">
                <p>Loading workspace incidents…</p>
              </div>
            ) : incidentError ? (
              <div className="empty-results">
                <p>{incidentError}</p>
              </div>
            ) : !currentWorkspaceId ? (
              <div className="empty-results">
                <p>Select an active workspace to view workspace incidents.</p>
              </div>
            ) : incidentRows.length === 0 ? (
              <div className="empty-results">
                <p>No incidents recorded for this workspace.</p>
              </div>
            ) : (
              <div className="incident-list">
                {incidentRows.map((incident) => (
                  <article className="incident-card" key={incident.id}>
                    <div className="incident-card-header">
                      <div className="incident-card-title-group">
                        <p className="incident-card-kicker">{formatIncidentKindLabel(incident.incidentKind)}</p>
                        <h4>{incident.title}</h4>
                        <p className="incident-card-id">Incident ID: {incident.id}</p>
                        <label className="incident-select-control">
                          <input
                            type="checkbox"
                            checked={selectedIncidentIds.includes(incident.id)}
                            onChange={() => toggleIncidentSelection(incident.id)}
                          />
                          <span>
                            {selectedIncidentIds.includes(incident.id) ? 'Selected for suggestion' : 'Add to suggestion set'}
                          </span>
                        </label>
                      </div>
                      <div className="incident-chip-row">
                        <span className={`incident-chip incident-chip-${getIncidentSeverityTone(incident.severity)}`}>
                          {incident.severity ? formatIncidentStatusLabel(incident.severity) : 'Unspecified severity'}
                        </span>
                        <span className={`incident-chip incident-chip-status incident-status-${incident.status}`}>
                          {formatIncidentStatusLabel(incident.status)}
                        </span>
                      </div>
                    </div>

                    <div className="incident-detail-grid">
                      <div className="incident-detail">
                        <span>Summary</span>
                        <strong>{formatIncidentSummary(incident)}</strong>
                      </div>
                      <div className="incident-detail">
                        <span>Workspace</span>
                        <strong>{incident.workspaceId || currentWorkspaceId}</strong>
                      </div>
                      <div className="incident-detail">
                        <span>Scope</span>
                        <strong>{incident.scopeKind && incident.scopeId ? `${humanizeLabel(incident.scopeKind)} / ${incident.scopeId}` : 'Workspace'}</strong>
                      </div>
                      <div className="incident-detail">
                        <span>Assignment</span>
                        <strong>{incident.assignedTo || 'Unassigned'}</strong>
                      </div>
                      <div className="incident-detail">
                        <span>Tracking</span>
                        <strong>{incident.itsmTicketNumber || incident.itsmTicketId || 'No ticket yet'}</strong>
                      </div>
                      <div className="incident-detail">
                        <span>Correlation</span>
                        <strong>{formatIncidentCorrelationSummary(incident)}</strong>
                      </div>
                      <div className="incident-detail">
                        <span>Updated</span>
                        <strong>{formatIncidentDate(incident.updatedAt || incident.createdAt)}</strong>
                      </div>
                    </div>

                    {(incident.failureCode || incident.resolutionHistory || incident.comments) && (
                      <div className="incident-supporting-copy">
                        {incident.failureCode && <p><strong>Failure code:</strong> {incident.failureCode}</p>}
                        {(incident.sourceCorrelationId || incident.sourceParentCorrelationId || incident.sourceTraceId || incident.sourceRequestId || incident.sourceQueueMessageId || incident.sourceSystem) && (
                          <p>
                            <strong>Correlation inputs:</strong>{' '}
                            {[
                              incident.sourceCorrelationId && `correlation ${incident.sourceCorrelationId}`,
                              incident.sourceParentCorrelationId && `parent ${incident.sourceParentCorrelationId}`,
                              incident.sourceTraceId && `trace ${incident.sourceTraceId}`,
                              incident.sourceRequestId && `request ${incident.sourceRequestId}`,
                              incident.sourceQueueMessageId && `queue ${incident.sourceQueueMessageId}`,
                              incident.sourceSystem && `source ${incident.sourceSystem}`,
                            ].filter(Boolean).join(' · ')}
                          </p>
                        )}
                        <p>
                          <strong>Comments:</strong> {incident.comments?.length || 0} · <strong>History events:</strong> {incident.resolutionHistory?.length || 0}
                        </p>
                      </div>
                    )}

                    {Array.isArray(incident.comments) && incident.comments.length > 0 && (
                      <DiscussionPanel
                        title="Discussion"
                        subtitle="Workspace-scoped incident comments and updates."
                        entries={normalizeDiscussionEntries(incident.comments, 'Incident')}
                        emptyState="No incident comments recorded yet."
                      />
                    )}
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'reconciliation' && (
        <div className="reports-content">
          <ReconciliationWorkbench />
        </div>
      )}

      <RuleDetailsModal
        isOpen={detailsModalOpen}
        onClose={closeDetailsModal}
        ruleId={detailsModalRule?.id || null}
        ruleName={detailsModalRule?.name || null}
        statusText={detailsModalRule?.status || null}
        approvalText={detailsModalRule?.last_approval_status || null}
        versionHint={detailsModalRule?.currentVersionNumber || null}
      />
    </AppPageShell>
  )
}
