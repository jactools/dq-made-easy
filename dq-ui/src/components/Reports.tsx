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
  initialTab?: 'metrics' | 'result-explorer' | 'test-results' | 'incidents' | 'reconciliation'
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
  const [activeTab, setActiveTab] = useState<'metrics' | 'result-explorer' | 'test-results' | 'incidents' | 'reconciliation'>(initialTab)
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

  // Update activeTab when initialTab prop changes
  useEffect(() => {
    setActiveTab(initialTab)
  }, [initialTab])

  useEffect(() => subscribeUiTelemetryConnectionState(setTelemetryConnectionState), [])

  const currentWorkspaceId = String(auth.currentWorkspaceId || '').trim()

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

  useEffect(() => {
    if (activeTab !== 'incidents') {
      return
    }

    void loadIncidents()
    void loadRootCauseSuggestions()
  }, [activeTab, loadIncidents, loadRootCauseSuggestions])

  useEffect(() => {
    setSelectedIncidentIds([])
  }, [currentWorkspaceId])

  const currentWorkspaceRules = useMemo(() => {
    if (!auth.currentWorkspaceId) {
      return []
    }

    return rules.filter((rule) => rule.workspace === auth.currentWorkspaceId)
  }, [rules, auth.currentWorkspaceId])

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
