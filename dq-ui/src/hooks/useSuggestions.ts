import { useState, useEffect, useCallback, useRef } from 'react'
import { Rule, Suggestion } from '../types/rules'
import { useAuth } from './useKeycloak'
import { useSettings } from './useContexts'
import { usePerformanceMonitoringContext } from '../contexts/PerformanceMonitoringContext'
import { normalizeApiBaseUrl, toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { buildRuleDslPayload } from '../utils/ruleDsl'

export interface SuggestionDataSource {
  dataSourceId: string
  name: string
  sourceType: string
  recordCount?: number
  lastProfiledAt?: string
}

export interface ProfilingRequestResult {
  success: boolean
  message: string
  profilingRequestId?: string
  eventsUrl?: string
}

export interface ProfilingRequestSummary {
  id: string
  dataSourceId: string
  requestedByUserId: string
  requestedAt?: string
  startedAt?: string
  completedAt?: string
  status?: string
  errorMessage?: string
  resultMetadataId?: string
  jobId?: string
}

export interface NaturalLanguageRequestHistoryItem {
  requestId: string
  currentWorkspaceId: string
  searchScope: NaturalLanguageSearchScope
  analysisProvider: NaturalLanguageAnalysisProvider
  analysisType: 'preview' | 'draft' | 'steward'
  prompt: string
  selectedAttributeIds: string[]
  accessibleWorkspaceIds: string[]
  requestedByUserId?: string | null
  requestedAt?: string | null
  startedAt?: string | null
  completedAt?: string | null
  status: 'pending' | 'started' | 'completed' | 'failed'
  errorMessage?: string | null
  suggestionId?: string | null
  jobId?: string | null
  result?: Record<string, unknown> | null
}

export interface ProfilingRequestStatusResult {
  success: boolean
  status?: string
  message?: string
  request?: ProfilingRequestSummary
}

export type NaturalLanguageSearchScope = 'current' | 'all' | 'all_across_workspaces'
export type NaturalLanguageAnalysisProvider = 'rapidfuzz' | 'llm'

export interface NaturalLanguagePreviewCandidate {
  attributeId: string
  attributeName: string
  versionId: string
  dataObjectId: string
  dataObjectName: string
  dataSetId: string
  dataSetName: string
  dataProductId: string
  dataProductName: string
  workspaceId: string
  parentPath: string[]
  confidenceScore: number
  matchReasons: string[]
  currentContext: boolean
  matchRoles: string[]
}

export interface NaturalLanguageParsedCondition {
  attributeTerm: string
  operator: string
  value: string
  sameVersionRequired: boolean
}

export interface NaturalLanguageDraftRulePreview {
  name: string
  workspaceId: string
  dimension: string
  summary: string
  dsl: NaturalLanguageRuleDslDocument
}

export interface NaturalLanguageRuleDslDocument {
  schemaVersion: '2.0.0'
  rule: NaturalLanguageRuleDslRule
}

export interface NaturalLanguageRuleDslRule {
  kind: string
  scope: NaturalLanguageRuleDslScope
  measure: NaturalLanguageRuleDslMeasure
  expectation: NaturalLanguageRuleDslExpectation
  evidence: NaturalLanguageRuleDslEvidence
  operations: NaturalLanguageRuleDslOperations
  reusableJoinId?: string | null
  reusableFilterIds?: string[]
}

export interface NaturalLanguageRuleDslScope {
  dataset: {
    dataObjectId?: string
    dataObjectVersionId?: string
    datasetId?: string
    dataProductId?: string
  }
  rowFilter?: {
    kind: string
    language: string
    expression: string
  }
  join?: Record<string, unknown>
  grouping?: Record<string, unknown>
  timeWindow?: Record<string, unknown>
  comparison?: Record<string, unknown>
}

export interface NaturalLanguageRuleDslMeasure {
  type: string
  metric?: string
  subject?: {
    column?: string
    columns?: string[]
  }
  predicate?: {
    kind: string
    language: string
    expression: string
  }
  schemaAssertion?: string
  queryLanguage?: string
  query?: string
  comparisonDataSourceName?: string | null
  comparisonQuery?: string | null
}

export interface NaturalLanguageRuleDslExpectation {
  type: string
  operator?: string
  value?: string | number | null
  minValue?: string | number | null
  maxValue?: string | number | null
  unit?: string | null
}

export interface NaturalLanguageRuleDslEvidence {
  failedRows: {
    mode: string
    limit?: number | null
    includeRowIdentifier: boolean
    includePrimaryKey: boolean
  }
  emitCompiledArtifact: boolean
  emitGeneratedSql: boolean
}

export interface NaturalLanguageRuleDslOperations {
  severity: string
  preferredEngines: string[]
  failIfNotNative: boolean
}

export interface NaturalLanguageRulePreview {
  targetTerms: string[]
  searchScope: NaturalLanguageSearchScope
  candidateAttributes: NaturalLanguagePreviewCandidate[]
  parsedCondition?: NaturalLanguageParsedCondition
  requiresStewardConfirmation: boolean
  draftRulePreview: NaturalLanguageDraftRulePreview
}

export interface NaturalLanguageRulePreviewRequest {
  prompt: string
  searchScope: NaturalLanguageSearchScope
  currentWorkspaceId: string
  analysisProvider: NaturalLanguageAnalysisProvider
}

export interface NaturalLanguageDraftSuggestionRequest extends NaturalLanguageRulePreviewRequest {
  selectedAttributeIds: string[]
}

export type NaturalLanguagePreviewTelemetryAction = 'attributes_selected' | 'preview_cancelled'

export interface NaturalLanguagePreviewTelemetryRequest {
  action: NaturalLanguagePreviewTelemetryAction
  currentWorkspaceId: string
  selectedAttributeCount?: number
}

export interface NaturalLanguagePreviewResult {
  success: boolean
  message: string
  preview?: NaturalLanguageRulePreview
  queued?: boolean
  requestId?: string
}

export interface NaturalLanguageDraftSuggestionResult {
  success: boolean
  message: string
  suggestion?: Suggestion
  queued?: boolean
  requestId?: string
}

export interface UseSuggestionsResult {
  suggestions: Suggestion[]
  dataSources: SuggestionDataSource[]
  profilingRequests: ProfilingRequestSummary[]
  naturalLanguageRequests: NaturalLanguageRequestHistoryItem[]
  hasProfilingPermission: boolean
  loading: boolean
  loadingDataSources: boolean
  loadingProfilingRequests: boolean
  error: string | null
  profilingRequestsError: string | null
  refetch: () => Promise<void>
  refreshProfilingRequests: () => Promise<void>
  acceptSuggestion: (suggestionId: string) => Promise<boolean>
  dismissSuggestion: (suggestionId: string) => Promise<boolean>
  applySuggestion: (suggestionId: string, ruleId?: string) => Promise<boolean>
  generateNaturalLanguagePreview: (request: NaturalLanguageRulePreviewRequest) => Promise<NaturalLanguagePreviewResult>
  createNaturalLanguageDraftSuggestion: (request: NaturalLanguageDraftSuggestionRequest) => Promise<NaturalLanguageDraftSuggestionResult>
  recordNaturalLanguagePreviewTelemetry: (request: NaturalLanguagePreviewTelemetryRequest) => Promise<boolean>
  requestProfiling: (dataSourceId: string) => Promise<ProfilingRequestResult>
  getProfilingRequestStatus: (profilingRequestId: string) => Promise<ProfilingRequestStatusResult>
  // For client-side mock preview flows: raw sample data (before profiling) and injected suggestions (after profiling)
  previewSample: any[]
  previewSuggestions: Suggestion[]
}

const parseApiResponse = async (response: Response) => {
  const payload = await response.text()
  let data: any = null

  if (payload) {
    try {
      data = JSON.parse(payload)
    } catch {
      data = null
    }
  }

  if (!response.ok || data?.success === false || data?.error) {
    const message = data?.message || data?.error || `Request failed: ${response.status} ${response.statusText}`
    throw new Error(message)
  }

  return data || {}
}

const normalizeErrorMessage = (error: unknown, fallback: string, apiBaseUrl: string) => {
  const message = error instanceof Error ? error.message : fallback

  if (message.includes('The string did not match the expected pattern')) {
    return `Unable to call the API endpoint. Check API Base URL in Settings (currently: ${apiBaseUrl}).`
  }

  if (message.includes('Failed to fetch')) {
    return `Unable to reach the API at ${apiBaseUrl}.`
  }

  return message || fallback
}

const isNotFoundError = (error: unknown): boolean => {
  const message = error instanceof Error ? error.message : String(error || '')
  return /404\s+Not\s+Found/i.test(message)
}

const suggestionsApiUnavailableMessage =
  'Rule Suggestions API endpoints are not available on this backend deployment. Please enable or deploy Suggestions endpoints in the API service.'

const normalizeSuggestion = (suggestion: any): Suggestion => ({
  id: suggestion?.id ?? '',
  userId: suggestion?.user_id ?? '',
  dataSourceId: suggestion?.data_source_id ?? '',
  suggestedRule: {
    name: suggestion?.suggested_rule?.name ?? '',
    description: suggestion?.suggested_rule?.description ?? '',
    expression: suggestion?.suggested_rule?.expression,
    dimension: suggestion?.suggested_rule?.dimension,
    ruleType: suggestion?.suggested_rule?.rule_type ?? suggestion?.rule_type ?? 'NOT_NULL',
    checkType: suggestion?.suggested_rule?.check_type,
    checkTypeParams: suggestion?.suggested_rule?.check_type_params,
    workspaceId: suggestion?.suggested_rule?.workspace_id,
    targetTerms: Array.isArray(suggestion?.suggested_rule?.target_terms) ? suggestion.suggested_rule.target_terms : [],
    searchScope: suggestion?.suggested_rule?.search_scope,
    selectedAttributeIds: Array.isArray(suggestion?.suggested_rule?.selected_attribute_ids) ? suggestion.suggested_rule.selected_attribute_ids : [],
    selectedAttributes: Array.isArray(suggestion?.suggested_rule?.selected_attributes)
      ? snakeToCamel(suggestion.suggested_rule.selected_attributes)
      : [],
    draftSummary: suggestion?.suggested_rule?.draft_summary,
    parsedCondition: suggestion?.suggested_rule?.parsed_condition ? snakeToCamel(suggestion.suggested_rule.parsed_condition) : undefined,
    dsl: suggestion?.suggested_rule?.dsl ? snakeToCamel(suggestion.suggested_rule.dsl) : undefined,
    prompt: suggestion?.suggested_rule?.prompt,
    originalPromptText: suggestion?.suggested_rule?.original_prompt_text,
  },
  confidenceScore: suggestion?.confidence_score ?? 0,
  reason: suggestion?.reason ?? '',
  ruleType: suggestion?.rule_type ?? suggestion?.suggested_rule?.rule_type ?? 'NOT_NULL',
  createdFromProfilingRequestId: suggestion?.created_from_profiling_request_id ?? undefined,
  status: suggestion?.status ?? 'pending',
  createdAt: suggestion?.created_at ?? '',
  expiresAt: suggestion?.expires_at ?? undefined,
})

const normalizeProfilingRequest = (request: any): ProfilingRequestSummary => ({
  id: request?.id ?? '',
  dataSourceId: request?.data_source_id ?? '',
  requestedByUserId: request?.requested_by_user_id ?? '',
  requestedAt: request?.requested_at,
  startedAt: request?.started_at,
  completedAt: request?.completed_at,
  status: request?.status,
  errorMessage: request?.error_message,
  resultMetadataId: request?.result_metadata_id,
  jobId: request?.job_id,
})

const normalizeNaturalLanguageRequest = (request: any): NaturalLanguageRequestHistoryItem => ({
  requestId: request?.request_id ?? '',
  currentWorkspaceId: request?.current_workspace_id ?? '',
  searchScope: request?.search_scope ?? 'current',
  analysisProvider: request?.analysis_provider ?? 'llm',
  analysisType: request?.analysis_type ?? 'preview',
  prompt: request?.prompt ?? '',
  selectedAttributeIds: Array.isArray(request?.selected_attribute_ids) ? request.selected_attribute_ids : [],
  accessibleWorkspaceIds: Array.isArray(request?.accessible_workspace_ids) ? request.accessible_workspace_ids : [],
  requestedByUserId: request?.requested_by_user_id ?? null,
  requestedAt: request?.requested_at ?? null,
  startedAt: request?.started_at ?? null,
  completedAt: request?.completed_at ?? null,
  status: request?.status ?? 'pending',
  errorMessage: request?.error_message ?? null,
  suggestionId: request?.suggestion_id ?? null,
  jobId: request?.job_id ?? null,
  result: request?.result_json ? snakeToCamel(request.result_json) : null,
})

const buildMockPreviewSuggestions = (sourceId: string, createdAt: string): Suggestion[] => ([
  {
    id: `mock-sugg-${sourceId}-1-${Date.now()}`,
    dataSourceId: sourceId,
    ruleType: 'NOT_NULL',
    confidenceScore: 0.92,
    status: 'pending',
    reason: 'High percentage of missing values detected in sample profiling.',
    suggestedRule: {
      name: 'column_x is not null',
      description: 'Ensure column_x is always populated.',
      expression: 'column_x IS NOT NULL',
      dimension: 'Completeness',
    },
    createdAt,
  } as unknown as Suggestion,
  {
    id: `mock-sugg-${sourceId}-2-${Date.now()}`,
    dataSourceId: sourceId,
    ruleType: 'UNIQUE',
    confidenceScore: 0.78,
    status: 'pending',
    reason: 'Duplicate values detected in profiling sample.',
    suggestedRule: {
      name: 'column_id is unique',
      description: 'Ensure column_id values are unique across rows.',
      expression: 'COUNT(DISTINCT column_id) = COUNT(column_id)',
      dimension: 'Uniqueness',
    },
    createdAt,
  } as unknown as Suggestion,
])

const profilingRequestSortValue = (request: ProfilingRequestSummary) => {
  const value = request.requestedAt ?? request.startedAt ?? request.completedAt
  const timestamp = value ? Date.parse(value) : Number.NaN
  return Number.isNaN(timestamp) ? 0 : timestamp
}

const sortProfilingRequests = (requests: ProfilingRequestSummary[]) => (
  [...requests].sort((left, right) => profilingRequestSortValue(right) - profilingRequestSortValue(left))
)

const naturalLanguageRequestSortValue = (request: NaturalLanguageRequestHistoryItem) => {
  const value = request.requestedAt ?? request.startedAt ?? request.completedAt
  const timestamp = value ? Date.parse(value) : Number.NaN
  return Number.isNaN(timestamp) ? 0 : timestamp
}

const sortNaturalLanguageRequests = (requests: NaturalLanguageRequestHistoryItem[]) => (
  [...requests].sort((left, right) => naturalLanguageRequestSortValue(right) - naturalLanguageRequestSortValue(left))
)

export const useSuggestions = (dataSourceId?: string): UseSuggestionsResult => {
  const auth = useAuth()
  const settings = useSettings()
  const { startTimer, endTimer } = usePerformanceMonitoringContext()
  const apiBaseUrl = normalizeApiBaseUrl(settings.applicationSettings?.apiBaseUrl)
  const dataCatalogApiBase = toApiGroupV1Base('data-catalog', settings.applicationSettings?.apiBaseUrl)
  const rulebuilderApiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  const suggestionsApiBase = `${dataCatalogApiBase}/suggestions`
  const profilingApiBase = `${dataCatalogApiBase}/profiling`
  const naturalLanguagePreviewApiBase = `${suggestionsApiBase}/natural-language-rule-previews`
  const testDataRequestsApiBase = `${rulebuilderApiBase}/test-data/requests`
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [dataSources, setDataSources] = useState<SuggestionDataSource[]>([])
  const [hasProfilingPermission, setHasProfilingPermission] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadingDataSources, setLoadingDataSources] = useState(false)
  const [loadingProfilingRequests, setLoadingProfilingRequests] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [profilingRequestsError, setProfilingRequestsError] = useState<string | null>(null)
  const [naturalLanguageRequests, setNaturalLanguageRequests] = useState<NaturalLanguageRequestHistoryItem[]>([])
  const [isSuggestionsApiUnavailable, setIsSuggestionsApiUnavailable] = useState(false)
  const [lastMockProfiledSource, setLastMockProfiledSource] = useState<string | null>(null)
  const [injectedMockSuggestions, setInjectedMockSuggestions] = useState(false)
  const preservedMockSuggestionsRef = useRef<Suggestion[] | null>(null)
  const preservedMockSourceRef = useRef<string | null>(null)
  const [previewSample, setPreviewSample] = useState<any[]>([])
  const [previewSuggestions, setPreviewSuggestions] = useState<Suggestion[]>([])
  const [backendProfilingRequests, setBackendProfilingRequests] = useState<ProfilingRequestSummary[]>([])
  const [localProfilingRequests, setLocalProfilingRequests] = useState<ProfilingRequestSummary[]>([])

  const buildAuthHeaders = useCallback((includeJsonContentType = false): HeadersInit => {
    const token = getAuthToken()
    if (!token) {
      return includeJsonContentType
        ? { 'Content-Type': 'application/json' }
        : {}
    }

    return includeJsonContentType
      ? {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        }
      : {
          'Authorization': `Bearer ${token}`,
        }
  }, [])

  const fetchSuggestions = useCallback(async () => {
    // debug: trace preconditions for fetching suggestions
    try {
      console.debug('[useSuggestions] fetchSuggestions called', JSON.stringify({
        isAuthenticated: !!auth.isAuthenticated,
        currentWorkspaceId: auth.currentWorkspaceId,
        isSuggestionsApiUnavailable,
        lastMockProfiledSource,
        injectedMockSuggestions,
      }))
    } catch {
      // ignore stringify errors
    }

    if (!auth.isAuthenticated || !auth.currentWorkspaceId || isSuggestionsApiUnavailable) return

    // If a local mock data source was just profiled, inject client-side mock suggestions
    if (lastMockProfiledSource) {
      try {
        console.debug('[useSuggestions] Injecting mock suggestions for', JSON.stringify({ lastMockProfiledSource }))
      } catch {}
      const now = new Date().toISOString()
      const mockSuggestions = buildMockPreviewSuggestions(lastMockProfiledSource, now)

      try { console.debug('[useSuggestions] Setting mock suggestions', JSON.stringify({ count: mockSuggestions.length })) } catch {}
      setSuggestions(mockSuggestions)
      preservedMockSuggestionsRef.current = mockSuggestions
      preservedMockSourceRef.current = lastMockProfiledSource
      setPreviewSuggestions(mockSuggestions)
      setLastMockProfiledSource(null)
      setInjectedMockSuggestions(true)
      return
    }

    const timer = startTimer()
    setLoading(true)
    setError(null)

    // If we've injected mock suggestions (held in ref), avoid overwriting them with empty API responses
    // Preserve injected mock suggestions only when the current fetch is for
    // the same data source that produced the mock suggestions. This prevents
    // mocks from blocking real suggestions for other data sources or global
    // workspace fetches.
    const shouldPreserveForThisRequest = Boolean(
      preservedMockSuggestionsRef.current &&
      preservedMockSuggestionsRef.current.length > 0 &&
      dataSourceId &&
      preservedMockSourceRef.current === dataSourceId
    )

    if (shouldPreserveForThisRequest) {
      try { console.debug('[useSuggestions] Preserving injected mock suggestions (from ref)', JSON.stringify({ preservedCount: preservedMockSuggestionsRef.current!.length })) } catch {}
      setLoading(false)
      return
    }

    try {
      const queryParams = new URLSearchParams()
      queryParams.append('status', 'pending')
      if (dataSourceId) {
        queryParams.append('data_source_id', dataSourceId)
      }

      const response = await fetch(`${suggestionsApiBase}?${queryParams.toString()}`, {
        headers: buildAuthHeaders(),
      })
      const data = await parseApiResponse(response)
      const rawSuggestions = Array.isArray(data?.suggestions) ? data.suggestions : []
      const apiSuggestions = rawSuggestions.map((suggestion: any) => normalizeSuggestion(suggestion))
      try { console.debug('[useSuggestions] API response received', JSON.stringify({ apiCount: Array.isArray(apiSuggestions) ? apiSuggestions.length : 0, injectedMockSuggestions })) } catch {}

      // If we've injected mock suggestions while this request was in-flight,
      // avoid overwriting them with an empty API response.
      const shouldPreserveAfterResponse = Boolean(
        preservedMockSuggestionsRef.current &&
        preservedMockSuggestionsRef.current.length > 0 &&
        dataSourceId &&
        preservedMockSourceRef.current === dataSourceId
      )

      if (shouldPreserveAfterResponse) {
        try { console.debug('[useSuggestions] Skipping API overwrite; preserved mock suggestions present (from ref)') } catch {}
        endTimer('suggestions.fetch', timer, true, {
          count: rawSuggestions.length,
          preservedInjectedMocks: true,
        })
        return
      }

      try { console.debug('[useSuggestions] Applying API suggestions', JSON.stringify({ apiCount: Array.isArray(apiSuggestions) ? apiSuggestions.length : 0, injectedMockSuggestions })) } catch {}
      setSuggestions(apiSuggestions)
      // If API returned any real suggestions, clear preserved mocks so live data takes over
      if (apiSuggestions.length > 0) {
        preservedMockSuggestionsRef.current = null
        preservedMockSourceRef.current = null
        if (injectedMockSuggestions) setInjectedMockSuggestions(false)
      }
      endTimer('suggestions.fetch', timer, true, {
        count: rawSuggestions.length,
      })
    } catch (err) {
      if (isNotFoundError(err)) {
        setIsSuggestionsApiUnavailable(true)
        setError(suggestionsApiUnavailableMessage)
        endTimer('suggestions.fetch', timer, false, {
          error: err instanceof Error ? err.message : String(err),
          unavailable: true,
        })
        return
      }

      const message = normalizeErrorMessage(err, 'Failed to fetch suggestions', apiBaseUrl)
      setError(message)
      console.error('Error fetching suggestions:', err)
      endTimer('suggestions.fetch', timer, false, {
        error: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setLoading(false)
    }
  }, [auth.currentWorkspaceId, dataSourceId, suggestionsApiBase, apiBaseUrl, startTimer, endTimer, buildAuthHeaders, isSuggestionsApiUnavailable, lastMockProfiledSource, injectedMockSuggestions])

  useEffect(() => {
    fetchSuggestions()
  }, [fetchSuggestions])

  const normalizeDataSourcesPayload = (data: any): SuggestionDataSource[] => {
    const rawDataSources = Array.isArray(data?.data_sources) ? data.data_sources : []

    return rawDataSources.map((source: any) => ({
      dataSourceId: source?.data_source_id ?? '',
      name: source?.name ?? '',
      sourceType: source?.source_type ?? '',
      recordCount: source?.record_count,
      lastProfiledAt: source?.last_profiled_at,
    }))
  }

  const fetchDataSources = useCallback(async () => {
    if (!auth.isAuthenticated || isSuggestionsApiUnavailable) {
      setDataSources([])
      setHasProfilingPermission(false)
      return
    }
    const timer = startTimer()
    setLoadingDataSources(true)

    try {
      const response = await fetch(`${suggestionsApiBase}/data-sources`, {
        headers: buildAuthHeaders(),
      })
      const data = await parseApiResponse(response)
      const normalizedDataSources = normalizeDataSourcesPayload(data)
      const canRequestProfiling = data?.can_request_profiling
      // Expose a local mock data source for all users so they can try the preview profiling flow locally.
      const augmentedDataSources = [...normalizedDataSources]
      const hasMock = augmentedDataSources.some(ds => ds.dataSourceId === 'mock-preview-source')
      if (!hasMock) {
        augmentedDataSources.push({
          dataSourceId: 'mock-preview-source',
          name: 'Mock Data Source (Preview)',
          sourceType: 'mock',
          recordCount: 1234,
          lastProfiledAt: new Date().toISOString(),
        })
      }

      setDataSources(augmentedDataSources)
      // keep permission as indicated by API; mock preview is available regardless
      setHasProfilingPermission(Boolean(canRequestProfiling))
      endTimer('profiling.dataSources.fetch', timer, true, {
        count: normalizedDataSources.length,
        hasProfilingPermission: Boolean(canRequestProfiling),
      })
    } catch (err) {
      if (isNotFoundError(err)) {
        setIsSuggestionsApiUnavailable(true)
        setError(suggestionsApiUnavailableMessage)
        setDataSources([])
        setHasProfilingPermission(false)
        endTimer('profiling.dataSources.fetch', timer, false, {
          error: err instanceof Error ? err.message : String(err),
          unavailable: true,
        })
        return
      }

      console.error('Error fetching suggestion data sources:', err)
      setDataSources([])
      setHasProfilingPermission(false)
      endTimer('profiling.dataSources.fetch', timer, false, {
        error: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setLoadingDataSources(false)
    }
  }, [
    suggestionsApiBase,
    startTimer,
    endTimer,
    buildAuthHeaders,
    auth.isAuthenticated,
    isSuggestionsApiUnavailable,
  ])

  useEffect(() => {
    fetchDataSources()
  }, [fetchDataSources])

  const fetchProfilingRequests = useCallback(async () => {
    if (!auth.isAuthenticated || !auth.currentWorkspaceId || isSuggestionsApiUnavailable) {
      setBackendProfilingRequests([])
      setProfilingRequestsError(null)
      return
    }

    const timer = startTimer()
    setLoadingProfilingRequests(true)
    setProfilingRequestsError(null)

    try {
      const queryParams = new URLSearchParams({ limit: '20' })
      if (dataSourceId) {
        queryParams.set('data_source_id', dataSourceId)
      }

      const response = await fetch(`${profilingApiBase}/requests?${queryParams.toString()}`, {
        headers: buildAuthHeaders(),
      })
      const data = await parseApiResponse(response)
      const rawProfilingRequests = Array.isArray(data?.profiling_requests)
        ? data.profiling_requests
        : []

      setBackendProfilingRequests(sortProfilingRequests(rawProfilingRequests.map(normalizeProfilingRequest)))
      endTimer('profiling.requests.fetch', timer, true, {
        count: rawProfilingRequests.length,
      })
    } catch (err) {
      if (isNotFoundError(err)) {
        setIsSuggestionsApiUnavailable(true)
        setError(suggestionsApiUnavailableMessage)
        setBackendProfilingRequests([])
        endTimer('profiling.requests.fetch', timer, false, {
          error: err instanceof Error ? err.message : String(err),
          unavailable: true,
        })
        return
      }

      console.error('Error fetching profiling requests:', err)
      setBackendProfilingRequests([])
      setProfilingRequestsError(normalizeErrorMessage(err, 'Failed to fetch profiling requests', apiBaseUrl))
      endTimer('profiling.requests.fetch', timer, false, {
        error: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setLoadingProfilingRequests(false)
    }
  }, [
    apiBaseUrl,
    auth.currentWorkspaceId,
    auth.isAuthenticated,
    buildAuthHeaders,
    endTimer,
    isSuggestionsApiUnavailable,
    startTimer,
    profilingApiBase,
    dataSourceId,
  ])

  useEffect(() => {
    fetchProfilingRequests()
  }, [fetchProfilingRequests])

  const fetchNaturalLanguageRequests = useCallback(async () => {
    if (!auth.isAuthenticated || !auth.currentWorkspaceId || isSuggestionsApiUnavailable) {
      setNaturalLanguageRequests([])
      return
    }

    try {
      const queryParams = new URLSearchParams()
      queryParams.append('workspace_id', auth.currentWorkspaceId)
      queryParams.append('limit', '20')

      const response = await fetch(`${naturalLanguagePreviewApiBase}/requests?${queryParams.toString()}`, {
        headers: buildAuthHeaders(),
      })
      const data = await parseApiResponse(response)
      const rawRequests = Array.isArray(data?.requests) ? data.requests : []
      setNaturalLanguageRequests(sortNaturalLanguageRequests(rawRequests.map(normalizeNaturalLanguageRequest)))
    } catch (err) {
      if (isNotFoundError(err)) {
        setIsSuggestionsApiUnavailable(true)
        setError(suggestionsApiUnavailableMessage)
        setNaturalLanguageRequests([])
        return
      }

      console.error('Error fetching natural-language requests:', err)
      setNaturalLanguageRequests([])
    }
  }, [auth.currentWorkspaceId, auth.isAuthenticated, buildAuthHeaders, isSuggestionsApiUnavailable, naturalLanguagePreviewApiBase])

  useEffect(() => {
    fetchNaturalLanguageRequests()
  }, [fetchNaturalLanguageRequests])

  const createRuleFromSuggestion = useCallback(async (suggestionId: string) => {
    const suggestion = suggestions.find(s => s.id === suggestionId)
    if (!suggestion) {
      throw new Error('Suggestion not found')
    }

    const suggestionRule = {
      name: suggestion.suggestedRule.name,
      description: suggestion.suggestedRule.description,
      expression: suggestion.suggestedRule.expression,
      dimension: suggestion.suggestedRule.dimension,
      workspace: suggestion.suggestedRule.workspaceId || auth.currentWorkspaceId,
      checkType: suggestion.suggestedRule.checkType,
      checkTypeParams: suggestion.suggestedRule.checkTypeParams,
      joinConditions: [],
      reusableFilterIds: [],
      aliasMappings: {},
      generated: false,
    } as Partial<Rule> as Rule

    const createRuleResponse = await fetch(`${rulebuilderApiBase}/rules`, {
      method: 'POST',
      headers: buildAuthHeaders(true),
      body: JSON.stringify(camelToSnake({
        name: suggestionRule.name,
        description: suggestionRule.description,
        dimension: suggestionRule.dimension,
        workspace: suggestionRule.workspace,
        suggestionId: suggestionId,
        generated: suggestionRule.generated,
        dsl: buildRuleDslPayload(suggestionRule),
      })),
    })

    const ruleData = await parseApiResponse(createRuleResponse)
    return ruleData.id as string
  }, [auth.currentWorkspaceId, buildAuthHeaders, rulebuilderApiBase, suggestions])

  const acceptSuggestion = useCallback(async (suggestionId: string) => {
    if (isSuggestionsApiUnavailable) {
      setError(suggestionsApiUnavailableMessage)
      return false
    }
    const workspaceId = String(auth.currentWorkspaceId || '').trim()
    if (!workspaceId) {
      setError('A current workspace is required to accept a suggestion.')
      return false
    }
    const timer = startTimer()
    try {
      const ruleId = await createRuleFromSuggestion(suggestionId)
      const response = await fetch(`${suggestionsApiBase}/${suggestionId}/accept`, {
        method: 'POST',
        headers: buildAuthHeaders(true),
        body: JSON.stringify(camelToSnake({ ruleId, workspaceId })),
      })

      await parseApiResponse(response)
      setSuggestions(prev => prev.filter(s => s.id !== suggestionId))
      endTimer('suggestions.accept', timer, true, {
        suggestionId,
        createdRuleId: ruleId,
      })

      return true
    } catch (err) {
      console.error('Error accepting suggestion:', err)
      endTimer('suggestions.accept', timer, false, {
        suggestionId,
        error: err instanceof Error ? err.message : String(err),
      })
      return false
    }
  }, [auth.currentWorkspaceId, createRuleFromSuggestion, suggestionsApiBase, startTimer, endTimer, buildAuthHeaders, isSuggestionsApiUnavailable])

  const dismissSuggestion = useCallback(async (suggestionId: string) => {
    if (isSuggestionsApiUnavailable) {
      setError(suggestionsApiUnavailableMessage)
      return false
    }
    const workspaceId = String(auth.currentWorkspaceId || '').trim()
    if (!workspaceId) {
      setError('A current workspace is required to dismiss a suggestion.')
      return false
    }
    const timer = startTimer()
    try {
      const response = await fetch(`${suggestionsApiBase}/${suggestionId}/dismiss`, {
        method: 'POST',
        headers: buildAuthHeaders(true),
        body: JSON.stringify(camelToSnake({ workspaceId })),
      })

      await parseApiResponse(response)
      setSuggestions(prev => prev.filter(s => s.id !== suggestionId))
      endTimer('suggestions.dismiss', timer, true, { suggestionId })

      return true
    } catch (err) {
      console.error('Error dismissing suggestion:', err)
      endTimer('suggestions.dismiss', timer, false, {
        suggestionId,
        error: err instanceof Error ? err.message : String(err),
      })
      return false
    }
  }, [auth.currentWorkspaceId, suggestionsApiBase, startTimer, endTimer, buildAuthHeaders, isSuggestionsApiUnavailable])

  const applySuggestion = useCallback(async (suggestionId: string, ruleId?: string) => {
    if (isSuggestionsApiUnavailable) {
      setError(suggestionsApiUnavailableMessage)
      return false
    }
    const workspaceId = String(auth.currentWorkspaceId || '').trim()
    if (!workspaceId) {
      setError('A current workspace is required to apply a suggestion.')
      return false
    }
    const timer = startTimer()
    try {
      if (!ruleId) {
        ruleId = await createRuleFromSuggestion(suggestionId)
      }

      // Now mark the suggestion as applied
      const response = await fetch(`${suggestionsApiBase}/${suggestionId}/apply`, {
        method: 'POST',
        headers: buildAuthHeaders(true),
        body: JSON.stringify(camelToSnake({ ruleId, workspaceId })),
      })

      await parseApiResponse(response)
      setSuggestions(prev => prev.filter(s => s.id !== suggestionId))
      endTimer('suggestions.apply', timer, true, {
        suggestionId,
        createdRuleId: ruleId,
      })

      return true
    } catch (err) {
      console.error('Error applying suggestion:', err)
      endTimer('suggestions.apply', timer, false, {
        suggestionId,
        error: err instanceof Error ? err.message : String(err),
      })
      return false
    }
  }, [auth.currentWorkspaceId, createRuleFromSuggestion, suggestionsApiBase, startTimer, endTimer, buildAuthHeaders, isSuggestionsApiUnavailable])

  const generateNaturalLanguagePreview = useCallback(async (
    request: NaturalLanguageRulePreviewRequest,
  ): Promise<NaturalLanguagePreviewResult> => {
    const timer = startTimer()
    try {
      const response = await fetch(naturalLanguagePreviewApiBase, {
        method: 'POST',
        headers: buildAuthHeaders(true),
        body: JSON.stringify(camelToSnake(request)),
      })
      const data = await parseApiResponse(response)

      if (data?.queued || data?.request_id || data?.requestId) {
        const requestId = String(data?.request_id || data?.requestId || '').trim()
        void fetchNaturalLanguageRequests()

        endTimer('suggestions.naturalLanguage.preview', timer, true, {
          queued: true,
          requestId,
          analysisProvider: request.analysisProvider,
        })

        return {
          success: true,
          message: data?.message || 'LLM preview request started.',
          queued: true,
          requestId,
        }
      }

      const normalizedPreview = snakeToCamel<NaturalLanguageRulePreview>(data)

      endTimer('suggestions.naturalLanguage.preview', timer, true, {
        ruleKind: normalizedPreview?.draftRulePreview?.dsl?.rule?.kind,
        candidateCount: normalizedPreview?.candidateAttributes?.length ?? 0,
      })

      void fetchNaturalLanguageRequests()

      return {
        success: true,
        message: 'Preview generated.',
        preview: normalizedPreview,
      }
    } catch (err) {
      endTimer('suggestions.naturalLanguage.preview', timer, false, {
        error: err instanceof Error ? err.message : String(err),
      })
      return {
        success: false,
        message: normalizeErrorMessage(err, 'Failed to generate a natural-language preview', apiBaseUrl),
      }
    }
  }, [apiBaseUrl, buildAuthHeaders, endTimer, fetchNaturalLanguageRequests, naturalLanguagePreviewApiBase, startTimer])

  const createNaturalLanguageDraftSuggestion = useCallback(async (
    request: NaturalLanguageDraftSuggestionRequest,
  ): Promise<NaturalLanguageDraftSuggestionResult> => {
    const timer = startTimer()
    try {
      const response = await fetch(`${naturalLanguagePreviewApiBase}/create-suggestion`, {
        method: 'POST',
        headers: buildAuthHeaders(true),
        body: JSON.stringify(camelToSnake(request)),
      })
      const data = await parseApiResponse(response)

      if (data?.queued || data?.request_id || data?.requestId) {
        const requestId = String(data?.request_id || data?.requestId || '').trim()
        void fetchNaturalLanguageRequests()
        endTimer('suggestions.naturalLanguage.createSuggestion', timer, true, {
          queued: true,
          requestId,
        })

        return {
          success: true,
          message: data?.message || 'Draft suggestion request started.',
          queued: true,
          requestId,
        }
      }

      const createdSuggestion = data?.suggestion ? normalizeSuggestion(data.suggestion) : undefined

      if (!createdSuggestion) {
        throw new Error('Draft suggestion was not returned by the API.')
      }

      setSuggestions((previousSuggestions) => [
        createdSuggestion,
        ...previousSuggestions.filter((existingSuggestion) => existingSuggestion.id !== createdSuggestion.id),
      ])
      void fetchNaturalLanguageRequests()

      endTimer('suggestions.naturalLanguage.createSuggestion', timer, true, {
        suggestionId: createdSuggestion.id,
        ruleKind: createdSuggestion.suggestedRule.dsl?.rule?.kind,
      })

      return {
        success: true,
        message: data?.message || 'Draft suggestion created.',
        suggestion: createdSuggestion,
      }
    } catch (err) {
      endTimer('suggestions.naturalLanguage.createSuggestion', timer, false, {
        error: err instanceof Error ? err.message : String(err),
      })
      return {
        success: false,
        message: normalizeErrorMessage(err, 'Failed to create a natural-language draft suggestion', apiBaseUrl),
      }
    }
  }, [apiBaseUrl, buildAuthHeaders, endTimer, fetchNaturalLanguageRequests, naturalLanguagePreviewApiBase, startTimer])

  const recordNaturalLanguagePreviewTelemetry = useCallback(async (
    request: NaturalLanguagePreviewTelemetryRequest,
  ): Promise<boolean> => {
    const timer = startTimer()
    try {
      const response = await fetch(`${naturalLanguagePreviewApiBase}/telemetry`, {
        method: 'POST',
        headers: buildAuthHeaders(true),
        body: JSON.stringify(camelToSnake(request)),
      })
      await parseApiResponse(response)

      endTimer('suggestions.naturalLanguage.telemetry', timer, true, {
        action: request.action,
        selectedAttributeCount: request.selectedAttributeCount ?? 0,
      })
      return true
    } catch (err) {
      console.error('Error recording natural-language preview telemetry:', err)
      endTimer('suggestions.naturalLanguage.telemetry', timer, false, {
        action: request.action,
        error: err instanceof Error ? err.message : String(err),
      })
      return false
    }
  }, [buildAuthHeaders, endTimer, naturalLanguagePreviewApiBase, startTimer])

  const requestProfiling = useCallback(async (sourceId: string): Promise<ProfilingRequestResult> => {
    if (isSuggestionsApiUnavailable) {
      return {
        success: false,
        message: suggestionsApiUnavailableMessage,
      }
    }

    const workspaceId = String(auth.currentWorkspaceId || '').trim()
    if (!workspaceId) {
      return {
        success: false,
        message: 'Select a workspace before requesting profiling.',
      }
    }

    const timer = startTimer()
    // Mock preview sources use the shared queued test-data generator instead of local simulation.
    const isMockSource = dataSources.some(ds => ds.dataSourceId === sourceId && ds.sourceType === 'mock') || sourceId.startsWith('mock-')
    if (isMockSource) {
      try {
        const response = await fetch(testDataRequestsApiBase, {
          method: 'POST',
          headers: buildAuthHeaders(true),
          body: JSON.stringify(camelToSnake({
            targetType: 'mock_data_source',
            targetId: sourceId,
            sampleCount: 10,
            sourceName: dataSources.find(ds => ds.dataSourceId === sourceId)?.name || sourceId,
          })),
        })
        const data = await parseApiResponse(response)
        const profilingRequestId = data?.request_id
        const eventsUrl = String(data?.events_url || '').trim()
        if (!eventsUrl) {
          throw new Error('Mock data generation request did not return events_url.')
        }
        const requestedAt = data?.requested_at || new Date().toISOString()

        setDataSources(prev => prev.map(ds => ds.dataSourceId === sourceId ? { ...ds, lastProfiledAt: requestedAt } : ds))
        setPreviewSample([])
        setPreviewSuggestions([])
        setLocalProfilingRequests(prev => sortProfilingRequests([
          {
            id: profilingRequestId,
            dataSourceId: sourceId,
            requestedByUserId: 'mock-preview-user',
            requestedAt,
            status: data?.status || 'pending',
            jobId: data?.job_id,
          },
          ...prev.filter(request => request.id !== profilingRequestId),
        ]))

        endTimer('profiling.request', timer, true, {
          dataSourceId: sourceId,
          profilingRequestId,
          mock: true,
        })

        return {
          success: true,
          message: 'Mock data generation started.',
          profilingRequestId,
          eventsUrl,
        }
      } catch (err) {
        endTimer('profiling.request', timer, false, {
          dataSourceId: sourceId,
          error: err instanceof Error ? err.message : String(err),
          mock: true,
        })
        return {
          success: false,
          message: normalizeErrorMessage(err, 'Failed to request mock data generation', apiBaseUrl),
        }
      }
    }
    try {
      const queryParams = new URLSearchParams({
        data_source_id: sourceId,
        workspace_id: workspaceId,
      })
      const response = await fetch(`${profilingApiBase}/requests?${queryParams.toString()}`, {
        method: 'POST',
        headers: buildAuthHeaders(),
      })

      const payload = await response.text()
      let data: any = null

      if (payload) {
        try {
          data = JSON.parse(payload)
        } catch {
          data = null
        }
      }

      if (!response.ok || data?.success === false || data?.error) {
        if (response.status === 429 || data?.status === 429) {
          const minutesRemaining = Number(data?.minutes_remaining)
          const retryIn = Number.isFinite(minutesRemaining) && minutesRemaining > 0
            ? `${minutesRemaining} minute${minutesRemaining === 1 ? '' : 's'}`
            : 'a short while'

          const lastRequestedAt = data?.last_requested_at
          let lastRequestedLabel = ''

          if (lastRequestedAt) {
            const lastRequestedDate = new Date(lastRequestedAt)
            if (!Number.isNaN(lastRequestedDate.getTime())) {
              lastRequestedLabel = ` Last requested at ${lastRequestedDate.toLocaleString()}.`
            }
          }

          return {
            success: false,
            message: `Data profiling was requested recently for this data source.${lastRequestedLabel} Please try again in ${retryIn}.`,
          }
        }

        throw new Error(data?.error || data?.message || `Request failed: ${response.status} ${response.statusText}`)
      }

      const profilingRequestId = data?.profiling_request_id
      const eventsUrl = String(data?.events_url || '').trim()
      if (!eventsUrl) {
        throw new Error('Profiling request did not return events_url.')
      }

      void fetchProfilingRequests()

      endTimer('profiling.request', timer, true, {
        dataSourceId: sourceId,
        workspaceId,
        profilingRequestId,
      })

      return {
        success: true,
        message: data.message || 'Data profiling started.',
        profilingRequestId,
        eventsUrl,
      }
    } catch (err) {
      endTimer('profiling.request', timer, false, {
        dataSourceId: sourceId,
        workspaceId,
        error: err instanceof Error ? err.message : String(err),
      })
      const message = normalizeErrorMessage(err, 'Failed to request data profiling', apiBaseUrl)
      return {
        success: false,
        message,
      }
    }
  }, [
    apiBaseUrl,
    auth.currentWorkspaceId,
    buildAuthHeaders,
    dataSources,
    endTimer,
    fetchProfilingRequests,
    isSuggestionsApiUnavailable,
    startTimer,
    profilingApiBase,
  ])

  const getProfilingRequestStatus = useCallback(async (profilingRequestId: string): Promise<ProfilingRequestStatusResult> => {
    if (isSuggestionsApiUnavailable) {
      return {
        success: false,
        message: suggestionsApiUnavailableMessage,
      }
    }

    const timer = startTimer()
    const localMockRequest = localProfilingRequests.find(request => request.id === profilingRequestId)
    const isQueuedMockRequest = Boolean(localMockRequest && dataSources.some(ds => ds.dataSourceId === localMockRequest.dataSourceId && ds.sourceType === 'mock'))
    if (isQueuedMockRequest || (profilingRequestId && profilingRequestId.startsWith('tdr-'))) {
      try {
        const response = await fetch(`${testDataRequestsApiBase}/${encodeURIComponent(profilingRequestId)}`, {
          headers: buildAuthHeaders(),
        })
        const data = await parseApiResponse(response)
        const requestDataSourceId = localMockRequest?.dataSourceId || data?.target_id || ''
        const normalizedRequest = normalizeProfilingRequest({
          id: data?.request_id,
          data_source_id: requestDataSourceId,
          requested_by_user_id: localMockRequest?.requestedByUserId || 'mock-preview-user',
          requested_at: data?.requested_at,
          started_at: data?.started_at,
          completed_at: data?.completed_at,
          status: data?.status,
          error_message: data?.error_message,
          job_id: data?.job_id,
        })

        setLocalProfilingRequests(prev => sortProfilingRequests(prev.map(request => (
          request.id === profilingRequestId
            ? normalizedRequest
            : request
        ))))

        if ((normalizedRequest.status || '').toLowerCase() === 'completed') {
          const samples = Array.isArray(data?.result?.samples) ? data.result.samples : []
          setPreviewSample(samples)
          if (requestDataSourceId) {
            setLastMockProfiledSource(requestDataSourceId)
          }
        }

        if ((normalizedRequest.status || '').toLowerCase() === 'completed' && requestDataSourceId) {
          const mockSuggestions = buildMockPreviewSuggestions(requestDataSourceId, data?.completed_at || new Date().toISOString())
          setPreviewSuggestions(mockSuggestions)
        }

        endTimer('profiling.status.poll', timer, true, {
          profilingRequestId,
          status: normalizedRequest.status,
          mock: true,
        })

        return {
          success: true,
          status: normalizedRequest.status,
          request: normalizedRequest,
        }
      } catch (err) {
        endTimer('profiling.status.poll', timer, false, {
          profilingRequestId,
          error: err instanceof Error ? err.message : String(err),
          mock: true,
        })
        return {
          success: false,
          message: normalizeErrorMessage(err, 'Failed to fetch mock profiling status', apiBaseUrl),
        }
      }
    }
    try {
      const response = await fetch(
        `${profilingApiBase}/requests/${encodeURIComponent(profilingRequestId)}/status`,
        {
          headers: buildAuthHeaders(),
        }
      )
      const data = await parseApiResponse(response)
      const normalizedRequest = data?.request ? normalizeProfilingRequest(data.request) : undefined
      void fetchProfilingRequests()
      endTimer('profiling.status.poll', timer, true, {
        profilingRequestId,
        status: normalizedRequest?.status,
      })

      return {
        success: true,
        status: normalizedRequest?.status,
        request: normalizedRequest,
      }
    } catch (err) {
      endTimer('profiling.status.poll', timer, false, {
        profilingRequestId,
        error: err instanceof Error ? err.message : String(err),
      })
      const message = normalizeErrorMessage(err, 'Failed to fetch profiling status', apiBaseUrl)
      return {
        success: false,
        message,
      }
    }
  }, [
    apiBaseUrl,
    buildAuthHeaders,
    endTimer,
    fetchProfilingRequests,
    isSuggestionsApiUnavailable,
    dataSources,
    localProfilingRequests,
    startTimer,
    profilingApiBase,
    testDataRequestsApiBase,
  ])

  const profilingRequests = sortProfilingRequests([
    ...localProfilingRequests,
    ...backendProfilingRequests,
  ])

  return {
    suggestions,
    dataSources,
    profilingRequests,
    hasProfilingPermission,
    loading,
    loadingDataSources,
    loadingProfilingRequests,
    error,
    profilingRequestsError,
    refetch: fetchSuggestions,
    refreshProfilingRequests: fetchProfilingRequests,
    acceptSuggestion,
    dismissSuggestion,
    applySuggestion,
    generateNaturalLanguagePreview,
    createNaturalLanguageDraftSuggestion,
    recordNaturalLanguagePreviewTelemetry,
    requestProfiling,
    getProfilingRequestStatus,
    previewSample,
    previewSuggestions,
    naturalLanguageRequests,
  }
}
