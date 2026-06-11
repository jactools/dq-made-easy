import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { AppCard, AppCardContent, AppInput } from '../app-primitives'
import { useAuth, useSettings } from '../../hooks/useContexts'
import { getAuthToken } from '../../contexts/AuthContext'
import { toApiGroupV1Base } from '../../config/api'
import { snakeToCamel } from '../../utils/caseConverters'
import { PrimaryButton, SecondaryButton } from '../Button'
import { AppSelect } from '../app-primitives'
import { StatusBanner } from '../StatusBanner'
import './ExceptionRecordHandling.css'

type ExceptionExecutionScopeView = {
  deliveryId?: string | null
  executionPlanId?: string | null
  executionPlanVersionId?: string | null
  executionRunId: string
  dataObjectVersionId: string
  datasetId?: string | null
  dataProductId?: string | null
}

type ExceptionRuleScopeView = {
  ruleId: string
  ruleVersionId: string
}

type ExceptionRecordReferenceView = {
  identifierType: string
  identifierValue: string
  identifierFields: string[]
  identifierHash?: string | null
}

type ExceptionFailureView = {
  reasonCode: string
  reasonText: string
  failureClass?: string | null
  detectedAt: string
}

type ExceptionFactView = {
  exceptionFactId: string
  exceptionFactContractVersion?: string | null
  engineType?: string | null
  executionScope: ExceptionExecutionScopeView
  ruleScope: ExceptionRuleScopeView
  recordReference: ExceptionRecordReferenceView
  failure: ExceptionFailureView
  correlationId?: string | null
  engineMetadata?: Record<string, unknown> | null
  opsMetadata?: Record<string, unknown> | null
}

type ExceptionAnalyticsView = {
  totalFailedRecords: number
  runsWithFailures: number
  trendBuckets: Array<{ bucketStart: string; total: number }>
  topRules: Array<{ ruleId: string; ruleName: string; total: number }>
  topDataObjects: Array<{ dataObjectVersionId: string; dataObjectName: string; total: number }>
  topReasons: Array<{ reasonCode: string; reasonText: string; total: number }>
}

type SemanticExceptionSummaryView = {
  analytics: ExceptionAnalyticsView
}

type ExceptionAnalysisSliceSuggestionView = {
  reasonCodes: string[]
  failureClass?: string | null
  recordIdentifierType?: string | null
  recordIdentifierValueContains?: string | null
  search?: string | null
  remainingCount: number
  partitionStrategy: string[]
  rationale: string
}

type ExceptionAnalysisSliceSummaryView = {
  analysisSessionId: string
  analysisSliceId: string
  sliceIndex: number
  dataObjectVersionId: string
  executionRunId: string
  ruleId: string
  sliceLimit: number
  anchorTotalCount: number
  totalMatchingCount: number
  returnedCount: number
  truncated: boolean
  analysisPackUri: string
  analysisPackSha256: string
  filters: Record<string, unknown>
  nextSliceSuggestion?: ExceptionAnalysisSliceSuggestionView | null
  createdAt: string
  updatedAt: string
}

type ExceptionAnalysisSliceDetailView = ExceptionAnalysisSliceSummaryView & {
  records: ExceptionFactView[]
}

type ExceptionAnalysisSessionStatusView = {
  state: string
  reason: string
  progressPercent: number
  remainingCount: number
  estimatedRemainingRecordCount: number
  estimatedRemainingSliceCount: number
  estimatedCostImpact: string
  sliceCount: number
  materializedRecordCount: number
  maxSlices?: number | null
  maxRecords?: number | null
  maxSeconds?: number | null
  budgetHit: boolean
  exhausted: boolean
  stalled: boolean
}

type ExceptionAnalysisSessionView = {
  analysisSessionId: string
  dataObjectVersionId: string
  executionRunId: string
  ruleId: string
  anchorTotalCount: number
  sliceCount: number
  createdAt: string
  updatedAt: string
  analysisStatus?: ExceptionAnalysisSessionStatusView | null
  currentSlice: ExceptionAnalysisSliceDetailView
  slices: ExceptionAnalysisSliceSummaryView[]
}

type AnalysisSessionDraft = {
  ruleId: string
  sliceLimit: string
  summaryOnly: boolean
  runUntilExhausted: boolean
  maxSlices: string
  maxRecords: string
  maxSeconds: string
}

type ScopeKind = 'delivery' | 'execution_plan'

type ExceptionFactsPageView = {
  data: ExceptionFactView[]
  pagination: {
    total: number
    page: number
    limit: number
    totalPages: number
    hasNext: boolean
    hasPrevious: boolean
  }
}

type Filters = {
  scopeKind: ScopeKind
  scopeId: string
  lookbackAmount: number
  limit: number
  offset: number
  dataObjectVersionId?: string
  executionRunId?: string
}

type Props = {
  onNavigate?: (target: string) => void
}

const LOOKBACK_OPTIONS = [24, 72, 168]
const LIMIT_OPTIONS = [10, 25, 50]
const SCOPE_OPTIONS: Array<{ value: ScopeKind; label: string }> = [
  { value: 'delivery', label: 'Delivery' },
  { value: 'execution_plan', label: 'Execution plan' },
]

const INITIAL_FILTERS: Filters = {
  scopeKind: 'delivery',
  scopeId: '',
  lookbackAmount: LOOKBACK_OPTIONS[0],
  limit: LIMIT_OPTIONS[1],
  offset: 0,
}

const INITIAL_ANALYSIS_SESSION_DRAFT: AnalysisSessionDraft = {
  ruleId: '',
  sliceLimit: '200',
  summaryOnly: true,
  runUntilExhausted: false,
  maxSlices: '',
  maxRecords: '',
  maxSeconds: '',
}

function getScopeRouteSegment(scopeKind: ScopeKind): string {
  return scopeKind === 'delivery' ? 'deliveries' : 'execution-plans'
}

function getScopeLabel(scopeKind: ScopeKind): string {
  return scopeKind === 'delivery' ? 'Delivery ID' : 'Execution plan ID'
}

function getScopeName(scopeKind: ScopeKind): string {
  return scopeKind === 'delivery' ? 'delivery' : 'execution plan'
}

function formatUnknown(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  return String(value)
}

function formatDateTime(value: string | undefined | null): string {
  if (!value) {
    return '—'
  }
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function toJsonText(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function getFieldValue(event: any): string {
  return event?.detail?.value ?? event?.target?.value ?? event?.currentTarget?.value ?? ''
}

function getCheckedValue(event: any): boolean {
  return Boolean(event?.detail?.value ?? event?.target?.checked ?? event?.currentTarget?.checked)
}

function parsePositiveInteger(value: string, label: string): number {
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`${label} must be a whole number greater than zero.`)
  }
  return parsed
}

function parseOptionalPositiveInteger(value: string, label: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) {
    return undefined
  }
  return parsePositiveInteger(trimmed, label)
}

function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const searchParams = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }
    searchParams.set(key, String(value))
  })

  const serialized = searchParams.toString()
  return serialized ? `?${serialized}` : ''
}

async function fetchJson<T>(url: string, token: string): Promise<T> {
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(await response.text())
  }

  return snakeToCamel(await response.json()) as T
}

function requireAuthToken(): string {
  const token = getAuthToken()
  if (!token) {
    throw new Error('Authentication token is not available yet.')
  }
  return token
}

export const ExceptionRecordHandling: React.FC<Props> = ({ onNavigate }) => {
  const auth = useAuth()
  const settings = useSettings()
  const apiBaseUrl = settings.applicationSettings?.apiBaseUrl ?? ''

  const canRead = Boolean(auth?.hasAnyScope?.(['dq:exceptions:read']) || auth?.hasAnyScope?.(['dq:exceptions:detail']))
  const canViewRawDetails = Boolean(auth?.hasAnyScope?.(['dq:exceptions:detail']))
  const accessGate = !canRead

  const [draftFilters, setDraftFilters] = useState<Filters>(INITIAL_FILTERS)
  const [appliedFilters, setAppliedFilters] = useState<Filters>(INITIAL_FILTERS)
  const [analytics, setAnalytics] = useState<ExceptionAnalyticsView | null>(null)
  const [factsPage, setFactsPage] = useState<ExceptionFactsPageView | null>(null)
  const [selectedFactId, setSelectedFactId] = useState<string | null>(null)
  const [selectedFactDetail, setSelectedFactDetail] = useState<ExceptionFactView | null>(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(false)
  const [factsLoading, setFactsLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [analysisSessionDraft, setAnalysisSessionDraft] = useState<AnalysisSessionDraft>(INITIAL_ANALYSIS_SESSION_DRAFT)
  const [analysisSession, setAnalysisSession] = useState<ExceptionAnalysisSessionView | null>(null)
  const [analysisSessionLoading, setAnalysisSessionLoading] = useState(false)
  const [analysisSessionError, setAnalysisSessionError] = useState<string | null>(null)
  const [analysisSliceLoading, setAnalysisSliceLoading] = useState(false)
  const [analysisSliceError, setAnalysisSliceError] = useState<string | null>(null)
  const [selectedAnalysisSliceId, setSelectedAnalysisSliceId] = useState<string | null>(null)
  const [selectedAnalysisSlice, setSelectedAnalysisSlice] = useState<ExceptionAnalysisSliceDetailView | null>(null)
  const [analyticsError, setAnalyticsError] = useState<string | null>(null)
  const [factsError, setFactsError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  const accessSummary = canViewRawDetails ? 'Exception detail access' : 'Exception read access'
  const scopeLabel = getScopeLabel(appliedFilters.scopeKind)
  const scopeRouteSegment = getScopeRouteSegment(appliedFilters.scopeKind)
  const selectedFact = useMemo(() => {
    if (!factsPage || !selectedFactId) {
      return null
    }
    return factsPage.data.find((fact) => fact.exceptionFactId === selectedFactId) ?? null
  }, [factsPage, selectedFactId])

  const detailFact = selectedFactDetail ?? selectedFact
  const analyticsTopReasons = analytics?.topReasons ?? []
  const analyticsTopRules = analytics?.topRules ?? []
  const analyticsTopDataObjects = analytics?.topDataObjects ?? []
  const analyticsTrendBuckets = analytics?.trendBuckets ?? []
  const hasAnalyticsContent = analyticsTopReasons.length > 0 || analyticsTopRules.length > 0 || analyticsTopDataObjects.length > 0 || analyticsTrendBuckets.length > 0
  const currentAnalysisScope = analysisSession ?? null
  const analysisStatus = currentAnalysisScope?.analysisStatus ?? null
  const analysisSlices = currentAnalysisScope?.slices ?? []
  const analysisSessionDataObjectVersionId = currentAnalysisScope?.dataObjectVersionId ?? appliedFilters.dataObjectVersionId ?? ''
  const analysisSessionExecutionRunId = currentAnalysisScope?.executionRunId ?? appliedFilters.executionRunId ?? ''
  const analysisSessionRuleId = currentAnalysisScope?.ruleId ?? analysisSessionDraft.ruleId

  useEffect(() => {
    const ruleId = selectedFact?.ruleScope.ruleId
    if (!ruleId) {
      return
    }

    setAnalysisSessionDraft((current) => {
      if (current.ruleId.trim()) {
        return current
      }

      return { ...current, ruleId }
    })
  }, [selectedFact?.ruleScope.ruleId])

  const loadAnalytics = useCallback(async () => {
    if (accessGate) {
      return
    }

    if (!appliedFilters.scopeId.trim()) {
      setAnalytics(null)
      setAnalyticsError(null)
      return
    }

    const token = requireAuthToken()
    const baseUrl = toApiGroupV1Base('exceptions', apiBaseUrl)

    setAnalyticsLoading(true)
    setAnalyticsError(null)

    try {
      const data = await fetchJson<SemanticExceptionSummaryView>(`${baseUrl}/${scopeRouteSegment}/${encodeURIComponent(appliedFilters.scopeId)}/exception-summary${buildQuery({
        lookbackAmount: appliedFilters.lookbackAmount,
        workspace_id: auth.currentWorkspaceId ?? '',
      })}`, token)
      setAnalytics(data.analytics)
    } catch (error) {
      setAnalytics(null)
      setAnalyticsError(error instanceof Error ? error.message : `Unable to load ${getScopeName(appliedFilters.scopeKind)} summary.`)
    } finally {
      setAnalyticsLoading(false)
    }
  }, [accessGate, apiBaseUrl, appliedFilters.lookbackAmount, appliedFilters.scopeId, appliedFilters.scopeKind, auth.currentWorkspaceId, scopeRouteSegment])

  const loadFacts = useCallback(async (filters: Filters) => {
    if (accessGate) {
      return
    }

    if (!filters.scopeId.trim()) {
      setFactsPage(null)
      setSelectedFactId(null)
      setSelectedFactDetail(null)
      setFactsError(null)
      return
    }

    const token = requireAuthToken()
    const baseUrl = toApiGroupV1Base('exceptions', apiBaseUrl)

    setFactsLoading(true)
    setFactsError(null)

    try {
      const data = await fetchJson<ExceptionFactsPageView>(
        `${baseUrl}/${getScopeRouteSegment(filters.scopeKind)}/${encodeURIComponent(filters.scopeId)}/exception-summary/records${buildQuery({
          lookbackAmount: filters.lookbackAmount,
          limit: filters.limit,
          offset: filters.offset,
          workspace_id: auth.currentWorkspaceId ?? '',
        })}`,
        token,
      )
      setFactsPage(data)
    } catch (error) {
      setFactsPage(null)
      setSelectedFactId(null)
      setSelectedFactDetail(null)
      setFactsError(error instanceof Error ? error.message : 'Unable to load exception records.')
    } finally {
      setFactsLoading(false)
    }
  }, [accessGate, apiBaseUrl, auth.currentWorkspaceId])

  const loadAnalysisSlice = useCallback(async (sessionId: string, sliceId: string) => {
    if (accessGate) {
      return
    }

    const token = requireAuthToken()
    const baseUrl = toApiGroupV1Base('exceptions', apiBaseUrl)

    setAnalysisSliceLoading(true)
    setAnalysisSliceError(null)

    try {
      const data = await fetchJson<ExceptionAnalysisSliceDetailView>(`${baseUrl}/analysis-sessions/${encodeURIComponent(sessionId)}/slices/${encodeURIComponent(sliceId)}${buildQuery({ workspace_id: auth.currentWorkspaceId ?? '' })}`, token)
      setSelectedAnalysisSliceId(sliceId)
      setSelectedAnalysisSlice(data)
    } catch (error) {
      setSelectedAnalysisSlice(null)
      setAnalysisSliceError(error instanceof Error ? error.message : 'Unable to load the selected analysis slice.')
    } finally {
      setAnalysisSliceLoading(false)
    }
  }, [accessGate, apiBaseUrl, auth.currentWorkspaceId])

  const loadAnalysisSession = useCallback(async (sessionId: string) => {
    if (accessGate) {
      return
    }

    const token = requireAuthToken()
    const baseUrl = toApiGroupV1Base('exceptions', apiBaseUrl)

    setAnalysisSessionLoading(true)
    setAnalysisSessionError(null)

    try {
      const data = await fetchJson<ExceptionAnalysisSessionView>(`${baseUrl}/analysis-sessions/${encodeURIComponent(sessionId)}${buildQuery({ workspace_id: auth.currentWorkspaceId ?? '', summary_only: analysisSessionDraft.summaryOnly ? 'true' : undefined })}`, token)
      setAnalysisSession(data)
      setSelectedAnalysisSliceId(data.currentSlice.analysisSliceId)
      setSelectedAnalysisSlice(data.currentSlice)
    } catch (error) {
      setAnalysisSession(null)
      setSelectedAnalysisSliceId(null)
      setSelectedAnalysisSlice(null)
      setAnalysisSessionError(error instanceof Error ? error.message : 'Unable to load the analysis session.')
    } finally {
      setAnalysisSessionLoading(false)
    }
  }, [accessGate, apiBaseUrl, auth.currentWorkspaceId, analysisSessionDraft.summaryOnly])

  useEffect(() => {
    if (accessGate) {
      return
    }
    void loadAnalytics()
  }, [accessGate, loadAnalytics])

  useEffect(() => {
    if (accessGate) {
      return
    }
    void loadFacts(appliedFilters)
  }, [accessGate, appliedFilters, loadFacts])

  useEffect(() => {
    if (!factsPage || factsPage.data.length === 0) {
      return
    }

    const selectedFactStillVisible = factsPage.data.some((fact) => fact.exceptionFactId === selectedFactId)
    if (!selectedFactId || !selectedFactStillVisible) {
      setSelectedFactId(factsPage.data[0].exceptionFactId)
    }
  }, [factsPage, selectedFactId])

  useEffect(() => {
    if (!canViewRawDetails || !selectedFactId) {
      setSelectedFactDetail(null)
      return
    }

    const token = requireAuthToken()
    const baseUrl = toApiGroupV1Base('exceptions', apiBaseUrl)

    let cancelled = false

    setDetailLoading(true)
    setDetailError(null)

    void (async () => {
      try {
        const data = await fetchJson<ExceptionFactView>(`${baseUrl}/${scopeRouteSegment}/${encodeURIComponent(appliedFilters.scopeId)}/exception-summary/records/${selectedFactId}${buildQuery({ workspace_id: auth.currentWorkspaceId ?? '' })}`, token)
        if (!cancelled) {
          setSelectedFactDetail(data)
        }
      } catch (error) {
        if (!cancelled) {
          setSelectedFactDetail(null)
          setDetailError(error instanceof Error ? error.message : 'Unable to load exception record detail.')
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [apiBaseUrl, appliedFilters.scopeId, auth.currentWorkspaceId, canViewRawDetails, scopeRouteSegment, selectedFactId])

  const handleApplyFilters = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSelectedFactId(null)
    setSelectedFactDetail(null)
    setAppliedFilters({ ...draftFilters, offset: 0 })
  }

  const handleResetFilters = () => {
    setDraftFilters(INITIAL_FILTERS)
    setSelectedFactId(null)
    setSelectedFactDetail(null)
    setAppliedFilters(INITIAL_FILTERS)
  }

  const handleRowSelect = (fact: ExceptionFactView) => {
    setSelectedFactId(fact.exceptionFactId)
    if (!canViewRawDetails) {
      setSelectedFactDetail(fact)
    }
  }

  const handlePageChange = (direction: -1 | 1) => {
    if (!factsPage) {
      return
    }

    setSelectedFactId(null)
    setSelectedFactDetail(null)
    setAppliedFilters((current) => ({
      ...current,
      offset: Math.max(0, current.offset + (direction * current.limit)),
    }))
  }

  const handleSubmitAnalysisSession = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const scopeDataObjectVersionId = analysisSessionDataObjectVersionId.trim()
    const scopeExecutionRunId = analysisSessionExecutionRunId.trim()
    const ruleId = analysisSessionRuleId.trim()

    if (!scopeDataObjectVersionId || !scopeExecutionRunId) {
      setAnalysisSessionError('Load exception records for a data object version and execution run before starting a session.')
      return
    }

    if (!ruleId) {
      setAnalysisSessionError('Enter the rule ID for the analysis session.')
      return
    }

    let sliceLimit: number
    let maxSlices: number | undefined
    let maxRecords: number | undefined
    let maxSeconds: number | undefined

    try {
      sliceLimit = parsePositiveInteger(analysisSessionDraft.sliceLimit, 'Slice limit')
      if (sliceLimit > 200) {
        throw new Error('Slice limit must be between 1 and 200.')
      }
      maxSlices = parseOptionalPositiveInteger(analysisSessionDraft.maxSlices, 'Max slices')
      maxRecords = parseOptionalPositiveInteger(analysisSessionDraft.maxRecords, 'Max records')
      maxSeconds = parseOptionalPositiveInteger(analysisSessionDraft.maxSeconds, 'Max seconds')
    } catch (error) {
      setAnalysisSessionError(error instanceof Error ? error.message : 'Unable to prepare the analysis session request.')
      return
    }

    const token = requireAuthToken()
    const baseUrl = toApiGroupV1Base('exceptions', apiBaseUrl)
    const requestBody = {
      dataObjectVersionId: scopeDataObjectVersionId,
      executionRunId: scopeExecutionRunId,
      ruleId,
      sliceLimit,
      summaryOnly: analysisSessionDraft.summaryOnly,
      runUntilExhausted: analysisSessionDraft.runUntilExhausted,
      maxSlices,
      maxRecords,
      maxSeconds,
    }
    const targetUrl = currentAnalysisScope
      ? `${baseUrl}/analysis-sessions/${encodeURIComponent(currentAnalysisScope.analysisSessionId)}/slices`
      : `${baseUrl}/analysis-sessions`

    setAnalysisSessionLoading(true)
    setAnalysisSessionError(null)
    setAnalysisSliceError(null)

    try {
      const response = await fetch(targetUrl, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      })

      if (!response.ok) {
        throw new Error(await response.text())
      }

      const payload = snakeToCamel<ExceptionAnalysisSessionView>(await response.json())
      setAnalysisSession(payload)
      setSelectedAnalysisSliceId(payload.currentSlice.analysisSliceId)
      setSelectedAnalysisSlice(payload.currentSlice)
      setAnalysisSessionDraft((current) => ({
        ...current,
        ruleId: payload.ruleId,
        sliceLimit: String(payload.currentSlice.sliceLimit || current.sliceLimit),
      }))
    } catch (error) {
      setAnalysisSessionError(error instanceof Error ? error.message : 'Unable to submit the analysis session request.')
    } finally {
      setAnalysisSessionLoading(false)
    }
  }

  const handleClearAnalysisSession = () => {
    setAnalysisSession(null)
    setSelectedAnalysisSliceId(null)
    setSelectedAnalysisSlice(null)
    setAnalysisSessionError(null)
    setAnalysisSliceError(null)
    setAnalysisSessionDraft((current) => ({
      ...INITIAL_ANALYSIS_SESSION_DRAFT,
      ruleId: current.ruleId.trim() || selectedFact?.ruleScope.ruleId || '',
    }))
  }

  if (accessGate) {
    return (
      <div className="exception-records-page">
        <section className="exception-records-hero exception-records-hero--gate">
          <div>
            <p className="exception-records-kicker">Governance</p>
            <h2>Exception Records</h2>
            <p className="exception-records-hero-copy">
              This workspace only exposes exception records while an approved JIT grant is active.
              Request access from Governance and return here after approval is granted.
            </p>
          </div>
          <div className="exception-records-hero-badge">JIT access required</div>
        </section>

        <div className="exception-records-empty">
          <h3>Access is currently unavailable</h3>
          <p>The exception-record page is hidden until your session includes the active exception-record scope.</p>
          <div className="exception-records-actions">
            <PrimaryButton type="button" onClick={() => onNavigate?.('access-requests')}>
              Open Access Requests
            </PrimaryButton>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="exception-records-page">
      <section className="exception-records-hero">
        <div>
          <p className="exception-records-kicker">Governance</p>
          <h2>Exception Records</h2>
          <p className="exception-records-hero-copy">
            Review aggregate exception summaries and page through a bounded set of records while your JIT grant is active.
          </p>
        </div>
        <div className="exception-records-hero-meta">
          <div className="exception-records-hero-badge">{accessSummary}</div>
          <div className="exception-records-hero-note">Active workspace: {formatUnknown(auth.currentWorkspaceId)}</div>
        </div>
      </section>

      {(analysisSessionError || analysisSliceError || analyticsError || factsError || detailError) && (
        <StatusBanner
          variant="error"
          message={analysisSessionError || analysisSliceError || analyticsError || factsError || detailError || 'Unable to load exception records.'}
          onDismiss={() => {
            setAnalysisSessionError(null)
            setAnalysisSliceError(null)
            setAnalyticsError(null)
            setFactsError(null)
            setDetailError(null)
          }}
        />
      )}

      <AppCard className="exception-records-panel exception-records-panel--session">
        <AppCardContent>
          <div className="exception-records-panel-header">
            <div>
              <h3>Analysis session</h3>
              <p>Start or continue a repeatable slice session from the applied data object version, execution run, and rule scope.</p>
            </div>
            <div className="exception-records-session-badge">{analysisStatus?.state ?? 'Not started'}</div>
          </div>

          <div className="exception-records-session-layout">
            <form className="exception-records-session-form" onSubmit={handleSubmitAnalysisSession}>
              <div className="exception-records-session-scope">
                <dl className="exception-records-definition-list">
                  <div>
                    <dt>Data object version</dt>
                    <dd>{formatUnknown(analysisSessionDataObjectVersionId)}</dd>
                  </div>
                  <div>
                    <dt>Execution run</dt>
                    <dd>{formatUnknown(analysisSessionExecutionRunId)}</dd>
                  </div>
                  <div>
                    <dt>Rule</dt>
                    <dd>{formatUnknown(analysisSessionRuleId)}</dd>
                  </div>
                </dl>
              </div>

              <div className="exception-records-session-form-grid">
                <div className="exception-records-field">
                  <AppInput
                    id="exception-records-session-rule-id"
                    className="exception-records-input"
                    label="Rule ID"
                    type="text"
                    value={analysisSessionDraft.ruleId}
                    onChange={(event: any) => setAnalysisSessionDraft((current) => ({ ...current, ruleId: getFieldValue(event) }))}
                    onInput={(event: any) => setAnalysisSessionDraft((current) => ({ ...current, ruleId: getFieldValue(event) }))}
                    placeholder="rule-id"
                    disabled={Boolean(currentAnalysisScope)}
                  />
                </div>
                <div className="exception-records-field">
                  <AppInput
                    id="exception-records-session-slice-limit"
                    className="exception-records-input"
                    label="Slice limit"
                    type="number"
                    min={1}
                    max={200}
                    value={analysisSessionDraft.sliceLimit}
                    onChange={(event: any) => setAnalysisSessionDraft((current) => ({ ...current, sliceLimit: getFieldValue(event) }))}
                    onInput={(event: any) => setAnalysisSessionDraft((current) => ({ ...current, sliceLimit: getFieldValue(event) }))}
                  />
                </div>
                <div className="exception-records-field">
                  <AppInput
                    id="exception-records-session-max-slices"
                    className="exception-records-input"
                    label="Max slices"
                    type="number"
                    min={1}
                    value={analysisSessionDraft.maxSlices}
                    onChange={(event: any) => setAnalysisSessionDraft((current) => ({ ...current, maxSlices: getFieldValue(event) }))}
                    onInput={(event: any) => setAnalysisSessionDraft((current) => ({ ...current, maxSlices: getFieldValue(event) }))}
                    placeholder="Optional"
                  />
                </div>
                <div className="exception-records-field">
                  <AppInput
                    id="exception-records-session-max-records"
                    className="exception-records-input"
                    label="Max records"
                    type="number"
                    min={1}
                    value={analysisSessionDraft.maxRecords}
                    onChange={(event: any) => setAnalysisSessionDraft((current) => ({ ...current, maxRecords: getFieldValue(event) }))}
                    onInput={(event: any) => setAnalysisSessionDraft((current) => ({ ...current, maxRecords: getFieldValue(event) }))}
                    placeholder="Optional"
                  />
                </div>
                <div className="exception-records-field">
                  <AppInput
                    id="exception-records-session-max-seconds"
                    className="exception-records-input"
                    label="Max seconds"
                    type="number"
                    min={1}
                    value={analysisSessionDraft.maxSeconds}
                    onChange={(event: any) => setAnalysisSessionDraft((current) => ({ ...current, maxSeconds: getFieldValue(event) }))}
                    onInput={(event: any) => setAnalysisSessionDraft((current) => ({ ...current, maxSeconds: getFieldValue(event) }))}
                    placeholder="Optional"
                  />
                </div>
                <label className="exception-records-session-toggle" htmlFor="exception-records-session-run-until-exhausted">
                  <input
                    id="exception-records-session-run-until-exhausted"
                    type="checkbox"
                    checked={analysisSessionDraft.runUntilExhausted}
                    onChange={(event) => setAnalysisSessionDraft((current) => ({ ...current, runUntilExhausted: getCheckedValue(event) }))}
                  />
                  <span>Keep enqueueing slices until uncovered exception space is exhausted or a budget is hit.</span>
                </label>
                <label className="exception-records-session-toggle" htmlFor="exception-records-session-summary-only">
                  <input
                    id="exception-records-session-summary-only"
                    type="checkbox"
                    checked={analysisSessionDraft.summaryOnly}
                    onChange={(event) => setAnalysisSessionDraft((current) => ({ ...current, summaryOnly: getCheckedValue(event) }))}
                  />
                  <span>Load the session summary first and materialize slice details only when a slice is selected.</span>
                </label>
              </div>

              <div className="exception-records-actions exception-records-actions--filters">
                <div className="exception-records-session-hint">
                  <span>The session uses the applied filters above as its fixed source scope.</span>
                </div>
                <div className="exception-records-filter-buttons">
                  <PrimaryButton type="submit" disabled={analysisSessionLoading || !analysisSessionDataObjectVersionId.trim() || !analysisSessionExecutionRunId.trim()}>
                    {currentAnalysisScope ? 'Continue session' : 'Start session'}
                  </PrimaryButton>
                  {currentAnalysisScope && (
                    <SecondaryButton type="button" onClick={handleClearAnalysisSession} disabled={analysisSessionLoading}>
                      New session
                    </SecondaryButton>
                  )}
                  {currentAnalysisScope && (
                    <SecondaryButton type="button" onClick={() => void loadAnalysisSession(currentAnalysisScope.analysisSessionId)} disabled={analysisSessionLoading}>
                      Refresh session
                    </SecondaryButton>
                  )}
                </div>
              </div>
            </form>

            <div className="exception-records-session-summary">
              {!currentAnalysisScope ? (
                <div className="exception-records-empty exception-records-empty--compact">
                  <p>Load records first to anchor an analysis session to the current source scope.</p>
                </div>
              ) : (
                <>
                  <dl className="exception-records-definition-list">
                    <div><dt>Session ID</dt><dd>{currentAnalysisScope.analysisSessionId}</dd></div>
                    <div><dt>State</dt><dd>{formatUnknown(analysisStatus?.state)}</dd></div>
                    <div><dt>Reason</dt><dd>{formatUnknown(analysisStatus?.reason)}</dd></div>
                    <div><dt>Progress</dt><dd>{formatUnknown(analysisStatus?.progressPercent === undefined ? undefined : `${analysisStatus.progressPercent.toFixed(1)}%`)}</dd></div>
                    <div><dt>Remaining uncovered</dt><dd>{formatUnknown(analysisStatus?.remainingCount?.toLocaleString?.() ?? analysisStatus?.remainingCount)}</dd></div>
                    <div><dt>Estimated remaining volume</dt><dd>{formatUnknown(analysisStatus?.estimatedRemainingRecordCount?.toLocaleString?.() ?? analysisStatus?.estimatedRemainingRecordCount)}</dd></div>
                    <div><dt>Estimated cost impact</dt><dd>{formatUnknown(analysisStatus?.estimatedCostImpact)}</dd></div>
                    <div><dt>Slice count</dt><dd>{formatUnknown(analysisStatus?.sliceCount?.toLocaleString?.() ?? analysisStatus?.sliceCount)}</dd></div>
                    <div><dt>Materialized records</dt><dd>{formatUnknown(analysisStatus?.materializedRecordCount?.toLocaleString?.() ?? analysisStatus?.materializedRecordCount)}</dd></div>
                  </dl>

                  <div className="exception-records-session-progress">
                    <div className="exception-records-session-progress-track" aria-hidden="true">
                      <div
                        className="exception-records-session-progress-fill"
                        style={{ width: `${Math.max(0, Math.min(100, analysisStatus?.progressPercent ?? 0))}%` }}
                      />
                    </div>
                    <div className="exception-records-session-progress-meta">
                      <span>{formatUnknown(analysisStatus?.progressPercent === undefined ? undefined : `${analysisStatus.progressPercent.toFixed(1)}% complete`)}</span>
                      <span>{formatUnknown(analysisStatus?.estimatedRemainingSliceCount === undefined ? undefined : `${analysisStatus.estimatedRemainingSliceCount} estimated slice(s) left`)}</span>
                    </div>
                  </div>

                  <div className="exception-records-session-badges">
                    {analysisStatus?.budgetHit && <span className="exception-records-session-pill">Budget hit</span>}
                    {analysisStatus?.exhausted && <span className="exception-records-session-pill">Exhausted</span>}
                    {analysisStatus?.stalled && <span className="exception-records-session-pill">Stalled</span>}
                    {!analysisStatus && <span className="exception-records-session-pill">Single-slice session</span>}
                  </div>

                  <div className="exception-records-session-slice-list">
                    <div className="exception-records-panel-header">
                      <div>
                        <h4>Slice history</h4>
                        <p>Each row opens the stored analysis pack for that slice.</p>
                      </div>
                    </div>

                    {analysisSlices.length > 0 ? (
                      <div className="exception-records-table-shell exception-records-session-table-shell">
                        <table className="exception-records-table exception-records-table--facts">
                          <thead>
                            <tr>
                              <th>Slice</th>
                              <th>Returned</th>
                              <th>Matched</th>
                              <th>Status</th>
                              <th>Suggestion</th>
                            </tr>
                          </thead>
                          <tbody>
                            {analysisSlices.map((slice) => (
                              <tr
                                key={slice.analysisSliceId}
                                className={slice.analysisSliceId === selectedAnalysisSliceId ? 'is-selected' : ''}
                                onClick={() => void loadAnalysisSlice(currentAnalysisScope.analysisSessionId, slice.analysisSliceId)}
                              >
                                <td>
                                  <strong>{`Slice ${slice.sliceIndex}`}</strong>
                                  <div className="exception-records-muted">{slice.analysisSliceId}</div>
                                </td>
                                <td>{slice.returnedCount.toLocaleString()}</td>
                                <td>{slice.totalMatchingCount.toLocaleString()}</td>
                                <td>{slice.truncated ? 'Truncated' : 'Complete'}</td>
                                <td>
                                  <strong>{formatUnknown(slice.nextSliceSuggestion?.rationale)}</strong>
                                  {slice.nextSliceSuggestion?.partitionStrategy?.length ? (
                                    <div className="exception-records-muted">{slice.nextSliceSuggestion.partitionStrategy.join(' · ')}</div>
                                  ) : null}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="exception-records-empty exception-records-empty--compact">
                        <p>{analysisSessionLoading ? 'Loading session…' : 'Start a session to capture the first slice and its stored analysis pack.'}</p>
                      </div>
                    )}
                  </div>

                  <div className="exception-records-session-detail">
                    <div className="exception-records-panel-header">
                      <div>
                        <h4>Selected slice pack</h4>
                        <p>{analysisSliceLoading ? 'Loading the stored pack for this slice…' : 'Inspect the selected slice from object storage.'}</p>
                      </div>
                    </div>

                    {!selectedAnalysisSlice ? (
                      <div className="exception-records-empty exception-records-empty--compact">
                        <p>Select a slice to inspect the stored pack and record details.</p>
                      </div>
                    ) : (
                      <>
                        <dl className="exception-records-definition-list">
                          <div><dt>Pack URI</dt><dd>{selectedAnalysisSlice.analysisPackUri}</dd></div>
                          <div><dt>Pack SHA256</dt><dd>{selectedAnalysisSlice.analysisPackSha256}</dd></div>
                          <div><dt>Returned</dt><dd>{selectedAnalysisSlice.returnedCount.toLocaleString()}</dd></div>
                          <div><dt>Matching records</dt><dd>{selectedAnalysisSlice.totalMatchingCount.toLocaleString()}</dd></div>
                          <div><dt>Anchor total</dt><dd>{selectedAnalysisSlice.anchorTotalCount.toLocaleString()}</dd></div>
                          <div><dt>Truncated</dt><dd>{selectedAnalysisSlice.truncated ? 'Yes' : 'No'}</dd></div>
                        </dl>

                        <div className="exception-records-json-block">
                          <strong>Next slice suggestion</strong>
                          <pre>{toJsonText(selectedAnalysisSlice.nextSliceSuggestion)}</pre>
                        </div>

                        <div className="exception-records-table-shell exception-records-session-table-shell">
                          <table className="exception-records-table exception-records-table--facts">
                            <thead>
                              <tr>
                                <th>Record</th>
                                <th>Reason</th>
                                <th>Execution run</th>
                                <th>Data object</th>
                              </tr>
                            </thead>
                            <tbody>
                              {selectedAnalysisSlice.records.map((fact) => (
                                <tr key={fact.exceptionFactId}>
                                  <td>
                                    <strong>{fact.exceptionFactId}</strong>
                                    <div className="exception-records-muted">{formatDateTime(fact.failure.detectedAt)}</div>
                                  </td>
                                  <td>
                                    <strong>{formatUnknown(fact.failure.reasonText)}</strong>
                                    <div className="exception-records-muted">{formatUnknown(fact.failure.reasonCode)}</div>
                                  </td>
                                  <td>{formatUnknown(fact.executionScope.executionRunId)}</td>
                                  <td>{formatUnknown(fact.executionScope.dataObjectVersionId)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </AppCardContent>
      </AppCard>

      <section className="exception-records-metrics">
        <AppCard className="exception-records-metric-card">
          <AppCardContent>
            <span>Failed records</span>
            <strong>{analytics ? analytics.totalFailedRecords.toLocaleString() : analyticsLoading ? 'Loading…' : '—'}</strong>
          </AppCardContent>
        </AppCard>
        <AppCard className="exception-records-metric-card">
          <AppCardContent>
            <span>Runs with failures</span>
            <strong>{analytics ? analytics.runsWithFailures.toLocaleString() : analyticsLoading ? 'Loading…' : '—'}</strong>
          </AppCardContent>
        </AppCard>
        <AppCard className="exception-records-metric-card">
          <AppCardContent>
            <span>Records matched</span>
            <strong>{factsPage ? factsPage.pagination.total.toLocaleString() : factsLoading ? 'Loading…' : '—'}</strong>
          </AppCardContent>
        </AppCard>
      </section>

      <section className="exception-records-controls-panel">
        <form className="exception-records-filters" onSubmit={handleApplyFilters}>
          <div className="exception-records-filters-grid">
            <div className="exception-records-field">
              <AppSelect
                id="exception-records-scope-kind"
                label="Scope type"
                value={draftFilters.scopeKind}
                onChange={(value) => setDraftFilters((current) => ({ ...current, scopeKind: value as ScopeKind }))}
                options={SCOPE_OPTIONS}
                placeholderLabel="Select a scope type"
                className="exception-records-select-wrapper"
              />
            </div>
            <div className="exception-records-field">
              <AppInput
                id="exception-records-scope-id"
                className="exception-records-input"
                label={getScopeLabel(draftFilters.scopeKind)}
                type="text"
                value={draftFilters.scopeId}
                onChange={(event: any) => setDraftFilters((current) => ({ ...current, scopeId: getFieldValue(event) }))}
                onInput={(event: any) => setDraftFilters((current) => ({ ...current, scopeId: getFieldValue(event) }))}
                placeholder={draftFilters.scopeKind === 'delivery' ? 'delivery-id' : 'execution-plan-id'}
              />
            </div>
            <div className="exception-records-field">
              <AppInput
                id="exception-records-data-object-version-id"
                className="exception-records-input"
                label="Data object version ID"
                type="text"
                value={draftFilters.dataObjectVersionId ?? ''}
                onChange={(event: any) => setDraftFilters((current) => ({ ...current, dataObjectVersionId: getFieldValue(event) }))}
                onInput={(event: any) => setDraftFilters((current) => ({ ...current, dataObjectVersionId: getFieldValue(event) }))}
                placeholder="data-object-version-id"
              />
            </div>
            <div className="exception-records-field">
              <AppInput
                id="exception-records-execution-run-id"
                className="exception-records-input"
                label="Run ID"
                type="text"
                value={draftFilters.executionRunId ?? ''}
                onChange={(event: any) => setDraftFilters((current) => ({ ...current, executionRunId: getFieldValue(event) }))}
                onInput={(event: any) => setDraftFilters((current) => ({ ...current, executionRunId: getFieldValue(event) }))}
                placeholder="Optional"
              />
            </div>
            <div className="exception-records-field">
              <AppSelect
                id="exception-records-lookback"
                label="Lookback window"
                value={String(draftFilters.lookbackAmount)}
                onChange={(value) => setDraftFilters((current) => ({ ...current, lookbackAmount: Number(value) }))}
                options={LOOKBACK_OPTIONS.map((option) => ({ value: String(option), label: `Last ${option} hours` }))}
                placeholderLabel="Select a lookback window"
                className="exception-records-select-wrapper"
              />
            </div>
            <div className="exception-records-field">
              <AppSelect
                id="exception-records-limit"
                label="Page size"
                value={String(draftFilters.limit)}
                onChange={(value) => setDraftFilters((current) => ({ ...current, limit: Number(value) }))}
                options={LIMIT_OPTIONS.map((option) => ({ value: String(option), label: `${option} records` }))}
                placeholderLabel="Select a page size"
                className="exception-records-select-wrapper"
              />
            </div>
          </div>
          <div className="exception-records-actions exception-records-actions--filters">
            <div className="exception-records-filter-buttons">
              <PrimaryButton type="submit">Load records</PrimaryButton>
              <SecondaryButton type="button" onClick={handleResetFilters}>Reset</SecondaryButton>
            </div>
          </div>
        </form>
      </section>

      <section className="exception-records-grid">
        <AppCard className="exception-records-panel exception-records-panel--analytics">
          <AppCardContent>
            <div className="exception-records-panel-header">
              <div>
                <h3>Exception summary</h3>
                <p>Aggregated metrics across the current monitoring window.</p>
              </div>
            </div>

            {!hasAnalyticsContent ? (
              <div className="exception-records-empty exception-records-empty--compact exception-records-empty--analytics">
                <p>{analyticsLoading ? 'Loading analytics…' : 'No analytics available for the selected window.'}</p>
              </div>
            ) : (
              <div className="exception-records-subgrid">
                <div>
                  <h4>Top reasons</h4>
                  <table className="exception-records-table exception-records-table--analytics">
                    <thead>
                      <tr>
                        <th>Reason</th>
                        <th>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analyticsTopReasons.map((row) => (
                        <tr key={row.reasonCode}>
                          <td>
                            <strong>{formatUnknown(row.reasonText)}</strong>
                            <div className="exception-records-muted exception-records-muted--analytics">{formatUnknown(row.reasonCode)}</div>
                          </td>
                          <td>{row.total.toLocaleString()}</td>
                        </tr>
                      ))}
                      {!analyticsTopReasons.length && <tr><td colSpan={2}>No analytics available.</td></tr>}
                    </tbody>
                  </table>
                </div>

                <div>
                  <h4>Top rules</h4>
                  <table className="exception-records-table exception-records-table--analytics">
                    <thead>
                      <tr>
                        <th>Rule</th>
                        <th>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analyticsTopRules.map((row) => (
                        <tr key={row.ruleId}>
                          <td>
                            <strong>{formatUnknown(row.ruleName)}</strong>
                            <div className="exception-records-muted exception-records-muted--analytics">{formatUnknown(row.ruleId)}</div>
                          </td>
                          <td>{row.total.toLocaleString()}</td>
                        </tr>
                      ))}
                      {!analyticsTopRules.length && <tr><td colSpan={2}>No analytics available.</td></tr>}
                    </tbody>
                  </table>
                </div>

                <div>
                  <h4>Top data objects</h4>
                  <table className="exception-records-table exception-records-table--analytics">
                    <thead>
                      <tr>
                        <th>Data object version</th>
                        <th>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analyticsTopDataObjects.map((row) => (
                        <tr key={row.dataObjectVersionId}>
                          <td>
                            <strong>{formatUnknown(row.dataObjectName)}</strong>
                            <div className="exception-records-muted exception-records-muted--analytics">{formatUnknown(row.dataObjectVersionId)}</div>
                          </td>
                          <td>{row.total.toLocaleString()}</td>
                        </tr>
                      ))}
                      {!analyticsTopDataObjects.length && <tr><td colSpan={2}>No analytics available.</td></tr>}
                    </tbody>
                  </table>
                </div>

                <div>
                  <h4>Window trend</h4>
                  <table className="exception-records-table exception-records-table--analytics">
                    <thead>
                      <tr>
                        <th>Bucket start</th>
                        <th>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analyticsTrendBuckets.map((row) => (
                        <tr key={row.bucketStart}>
                          <td>{formatDateTime(row.bucketStart)}</td>
                          <td>{row.total.toLocaleString()}</td>
                        </tr>
                      ))}
                      {!analyticsTrendBuckets.length && <tr><td colSpan={2}>No analytics available.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </AppCardContent>
        </AppCard>

        <AppCard className="exception-records-panel exception-records-panel--table">
          <AppCardContent>
            <div className="exception-records-panel-header">
              <div>
                <h3>Exception records</h3>
                <p>Filtered by data object version and optional run ID.</p>
              </div>
              <div className="exception-records-pagination-actions exception-records-pagination-actions--header">
                <div className="exception-records-pagination-summary">
                  {factsPage
                    ? `Page ${factsPage.pagination.page} of ${factsPage.pagination.totalPages} · ${factsPage.pagination.total.toLocaleString()} total · ${factsPage.pagination.limit.toLocaleString()} per page`
                    : 'Load records to begin.'}
                </div>
                {factsPage && (factsPage.pagination.hasPrevious || factsPage.pagination.hasNext) && (
                  <div className="exception-records-pagination-buttons">
                    <SecondaryButton type="button" onClick={() => handlePageChange(-1)} disabled={!factsPage.pagination.hasPrevious || factsLoading}>
                      Previous
                    </SecondaryButton>
                    <SecondaryButton type="button" onClick={() => handlePageChange(1)} disabled={!factsPage.pagination.hasNext || factsLoading}>
                      Next
                    </SecondaryButton>
                  </div>
                )}
              </div>
            </div>

            {factsPage && factsPage.data.length > 0 ? (
              <div className="exception-records-table-shell">
                <table className="exception-records-table exception-records-table--facts">
                  <thead>
                    <tr>
                      <th>Record</th>
                      <th>Reason</th>
                      <th>Execution run</th>
                      <th>Data object</th>
                    </tr>
                  </thead>
                  <tbody>
                    {factsPage.data.map((fact) => (
                      <tr key={fact.exceptionFactId} className={fact.exceptionFactId === selectedFactId ? 'is-selected' : ''} onClick={() => handleRowSelect(fact)}>
                        <td>
                          <strong>{fact.exceptionFactId}</strong>
                          <div className="exception-records-muted">{formatDateTime(fact.failure.detectedAt)}</div>
                        </td>
                        <td>
                          <strong>{formatUnknown(fact.failure.reasonText)}</strong>
                          <div className="exception-records-muted">{formatUnknown(fact.failure.reasonCode)}</div>
                        </td>
                        <td>{formatUnknown(fact.executionScope.executionRunId)}</td>
                        <td>{formatUnknown(fact.executionScope.dataObjectVersionId)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="exception-records-empty exception-records-empty--compact">
                <p>{factsLoading ? 'Loading records…' : 'Enter a data object version ID and load records to see the current page of exception records.'}</p>
              </div>
            )}
          </AppCardContent>
        </AppCard>
      </section>

      <AppCard className="exception-records-panel exception-records-detail-panel">
        <AppCardContent>
          <div className="exception-records-panel-header">
            <div>
              <h3>Record detail</h3>
              <p>Raw detail is only available to investigator access. Readers can still review the selected record summary.</p>
            </div>
          </div>

          {!detailFact ? (
            <div className="exception-records-empty exception-records-empty--compact">
              <p>Select a record row to inspect the record reference, metadata, and execution scope.</p>
            </div>
          ) : (
            <div className="exception-records-detail-grid">
              <div>
                <h4>Summary</h4>
                <dl className="exception-records-definition-list">
                  <div><dt>Record ID</dt><dd>{detailFact.exceptionFactId}</dd></div>
                  <div><dt>Rule</dt><dd>{formatUnknown(detailFact.ruleScope.ruleId)} / {formatUnknown(detailFact.ruleScope.ruleVersionId)}</dd></div>
                  <div><dt>Data object version</dt><dd>{formatUnknown(detailFact.executionScope.dataObjectVersionId)}</dd></div>
                  <div><dt>Execution run</dt><dd>{formatUnknown(detailFact.executionScope.executionRunId)}</dd></div>
                  <div><dt>Detected at</dt><dd>{formatDateTime(detailFact.failure.detectedAt)}</dd></div>
                  <div><dt>Reason</dt><dd>{formatUnknown(detailFact.failure.reasonCode)} / {formatUnknown(detailFact.failure.reasonText)}</dd></div>
                </dl>
              </div>

              <div>
                <h4>Record reference</h4>
                <dl className="exception-records-definition-list">
                  <div><dt>Identifier type</dt><dd>{formatUnknown(detailFact.recordReference.identifierType)}</dd></div>
                  <div><dt>Identifier value</dt><dd>{formatUnknown(detailFact.recordReference.identifierValue)}</dd></div>
                  <div><dt>Identifier fields</dt><dd>{detailFact.recordReference.identifierFields.length > 0 ? detailFact.recordReference.identifierFields.join(', ') : '—'}</dd></div>
                  <div><dt>Identifier hash</dt><dd>{formatUnknown(detailFact.recordReference.identifierHash)}</dd></div>
                </dl>
              </div>

              <div>
                <h4>Execution scope</h4>
                <dl className="exception-records-definition-list">
                  <div><dt>Delivery ID</dt><dd>{formatUnknown(detailFact.executionScope.deliveryId)}</dd></div>
                  <div><dt>Execution plan ID</dt><dd>{formatUnknown(detailFact.executionScope.executionPlanId)}</dd></div>
                  <div><dt>Execution plan version</dt><dd>{formatUnknown(detailFact.executionScope.executionPlanVersionId)}</dd></div>
                  <div><dt>Dataset ID</dt><dd>{formatUnknown(detailFact.executionScope.datasetId)}</dd></div>
                  <div><dt>Data product ID</dt><dd>{formatUnknown(detailFact.executionScope.dataProductId)}</dd></div>
                </dl>
              </div>

              <div>
                <h4>Metadata</h4>
                <div className="exception-records-json-block">
                  <strong>Engine metadata</strong>
                  <pre>{toJsonText(detailFact.engineMetadata)}</pre>
                </div>
                <div className="exception-records-json-block">
                  <strong>Operations metadata</strong>
                  <pre>{toJsonText(detailFact.opsMetadata)}</pre>
                </div>
              </div>
            </div>
          )}

          {canViewRawDetails ? null : (
            <div className="exception-records-empty exception-records-empty--compact">
              <p>Investigator access is required to load the canonical raw detail view for this record.</p>
            </div>
          )}

          {detailLoading ? <div className="exception-records-loading">Loading record detail…</div> : null}
        </AppCardContent>
      </AppCard>
    </div>
  )
}