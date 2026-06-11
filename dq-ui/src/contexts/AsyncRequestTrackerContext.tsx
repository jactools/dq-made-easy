import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { SettingsContext } from './SettingsContext'
import { NotificationContext } from './NotificationContext'
import { RuleContext } from './RuleContext'
import { AuthContext, getAuthToken } from './AuthContext'
import { usePerformanceMonitoringContext } from './PerformanceMonitoringContext'
import { normalizeApiBaseUrl, toApiGroupV1Base } from '../config/api'

type TrackedAsyncRequestKind = 'test-data-generation' | 'rule-test' | 'profiling' | 'natural-language-draft'
type TrackedAsyncRequestStatus = 'pending' | 'running' | 'completed' | 'failed' | 'timed_out'

type RuleTestSelectedAttribute = {
  id: string
  name: string
  versionId?: string | null
  dataObjectName?: string
}

type RuleTestSemanticMatching = {
  enabled: boolean
  fieldAliasMappings?: Record<string, string>
  activeSynonyms?: string[]
  inactiveSynonyms?: string[]
}

export interface TrackedAsyncRequest {
  id: string
  kind: TrackedAsyncRequestKind
  requestId: string
  status: TrackedAsyncRequestStatus
  title: string
  relatedId?: string
  actionUrl?: string
  sourceId?: string
  sourceName?: string
  message?: string
  errorMessage?: string
  startedAt: string
  updatedAt: string
  completedAt?: string
  result?: any
  metadata?: Record<string, any>
}

interface StartTestDataGenerationInput {
  versionId: string
  sampleCount: number
  versionName?: string | number | null
  dataObjectId?: string | null
}

interface StartRuleTestInput {
  ruleId: string
  ruleName: string
  versionId: string
  sampleCount: number
  selectedAttributes: RuleTestSelectedAttribute[]
  semanticMatching?: RuleTestSemanticMatching
}

interface TrackProfilingRequestInput {
  requestId: string
  eventsUrl: string
  dataSourceId: string
  dataSourceName: string
  mode: 'profiling' | 'mock-preview'
}

interface TrackNaturalLanguageDraftRequestInput {
  requestId: string
  workspaceId: string
  workspaceName: string
  analysisProvider: 'rapidfuzz' | 'llm'
  analysisType?: 'preview' | 'draft' | 'steward'
}

interface AsyncRequestTrackerContextType {
  requests: Record<string, TrackedAsyncRequest>
  naturalLanguageAnalysisRequests: TrackedAsyncRequest[]
  naturalLanguageAnalysisRequestsError: string | null
  startTestDataGeneration: (input: StartTestDataGenerationInput) => Promise<string>
  startRuleTest: (input: StartRuleTestInput) => Promise<string>
  trackProfilingRequest: (input: TrackProfilingRequestInput) => string
  trackNaturalLanguageDraftRequest: (input: TrackNaturalLanguageDraftRequestInput) => string
  refreshNaturalLanguageAnalysisRequests: () => Promise<void>
  clearRequest: (id: string) => void
  registerWatcher: (id: string) => void
  unregisterWatcher: (id: string) => void
}

export const AsyncRequestTrackerContext = createContext<AsyncRequestTrackerContextType | null>(null)

const PROFILING_POLL_INTERVAL_MS = 5000
const PROFILING_MAX_POLLS = 120

const currentTimestamp = (): string => new Date().toISOString()

const sleep = (ms: number): Promise<void> => new Promise((resolve) => window.setTimeout(resolve, ms))

const buildTrackerId = (prefix: string): string => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

const normalizeTrackedStatus = (status: unknown): TrackedAsyncRequestStatus => {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'completed') return 'completed'
  if (normalized === 'failed') return 'failed'
  if (normalized === 'timed_out' || normalized === 'timeout') return 'timed_out'
  if (normalized === 'started' || normalized === 'running') return 'running'
  return 'pending'
}

const readJsonSafely = async (response: Response): Promise<any> => {
  const raw = await response.text()
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

const parseApiResponse = async (response: Response): Promise<any> => {
  const payload = await readJsonSafely(response)

  if (!response.ok || payload?.success === false || payload?.error) {
    const message = payload?.message || payload?.error || `Request failed: ${response.status} ${response.statusText}`
    throw new Error(message)
  }

  return payload || {}
}

const normalizeErrorMessage = (error: unknown, fallback: string, apiBaseUrl: string): string => {
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

const buildErrorMessage = async (response: Response, fallbackPrefix: string): Promise<string> => {
  const payload = await readJsonSafely(response)

  if (typeof payload === 'string' && payload.trim()) {
    return `${fallbackPrefix}: ${payload.trim()}`
  }

  if (typeof payload?.detail === 'string' && payload.detail.trim()) {
    return `${fallbackPrefix}: ${payload.detail.trim()}`
  }

  if (typeof payload?.detail?.message === 'string' && payload.detail.message.trim()) {
    return `${fallbackPrefix}: ${payload.detail.message.trim()}`
  }

  if (typeof payload?.detail?.error === 'string' && payload.detail.error.trim()) {
    return `${fallbackPrefix}: ${payload.detail.error.trim()}`
  }

  if (Array.isArray(payload?.detail)) {
    const detail = payload.detail
      .map((item: any) => {
        const loc = Array.isArray(item?.loc) ? item.loc.join('.') : ''
        const msg = typeof item?.msg === 'string' ? item.msg : ''
        return [loc, msg].filter(Boolean).join(': ')
      })
      .filter(Boolean)
      .join('; ')
    if (detail) {
      return `${fallbackPrefix}: ${detail}`
    }
  }

  if (typeof payload?.error === 'string' && payload.error.trim()) {
    return `${fallbackPrefix}: ${payload.error.trim()}`
  }

  if (typeof payload?.message === 'string' && payload.message.trim()) {
    return `${fallbackPrefix}: ${payload.message.trim()}`
  }

  return `${fallbackPrefix}: ${response.status} ${response.statusText}`
}

interface AsyncStatusEventPayload {
  requestId?: string
  request_id?: string
  status?: string
  errorMessage?: string
  error_message?: string
  request?: any
}

const resolveAsyncEventsUrl = (apiBase: string, eventsUrl: string): string => {
  const trimmedEventsUrl = String(eventsUrl || '').trim()
  if (!trimmedEventsUrl) {
    throw new Error('Async request did not return events_url.')
  }
  if (/^https?:\/\//i.test(trimmedEventsUrl)) {
    return trimmedEventsUrl
  }
  if (trimmedEventsUrl.startsWith('/')) {
    const apiRoot = apiBase.replace(/\/(rulebuilder|data-catalog)\/v1\/?$/i, '')
    return `${apiRoot}${trimmedEventsUrl}`
  }
  return `${apiBase.replace(/\/$/, '')}/${trimmedEventsUrl.replace(/^\//, '')}`
}

const parseAsyncStatusEventFrame = (frame: string): AsyncStatusEventPayload | null => {
  const dataLines = frame
    .split(/\r?\n/)
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice('data:'.length).trim())
  if (!dataLines.length) return null
  return JSON.parse(dataLines.join('\n')) as AsyncStatusEventPayload
}

export const AsyncRequestTrackerProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const settings = useContext(SettingsContext) as any
  const auth = useContext(AuthContext) as any
  const notifications = useContext(NotificationContext) as { addNotification?: (notification: any) => string } | null
  const rules = useContext(RuleContext) as {
    updateRuleStatus?: (ruleId: string, status: string) => Promise<void>
    logTestAction?: (ruleId: string, testData: any) => Promise<void>
    applyRuleTestResult?: (ruleId: string, testResult: any) => void
    applyStoredTestProof?: (ruleId: string, storedProof: any) => void
  } | null
  const { startTimer, endTimer } = usePerformanceMonitoringContext()
  const apiBaseUrl = useMemo(
    () => normalizeApiBaseUrl(settings?.applicationSettings?.apiBaseUrl),
    [settings?.applicationSettings?.apiBaseUrl],
  )
  const rulebuilderApiBase = useMemo(
    () => toApiGroupV1Base('rulebuilder', settings?.applicationSettings?.apiBaseUrl),
    [settings?.applicationSettings?.apiBaseUrl],
  )
  const dataCatalogApiBase = useMemo(
    () => toApiGroupV1Base('data-catalog', settings?.applicationSettings?.apiBaseUrl),
    [settings?.applicationSettings?.apiBaseUrl],
  )
  const [requests, setRequests] = useState<Record<string, TrackedAsyncRequest>>({})
  const [naturalLanguageAnalysisRequests, setNaturalLanguageAnalysisRequests] = useState<TrackedAsyncRequest[]>([])
  const [naturalLanguageAnalysisRequestsError, setNaturalLanguageAnalysisRequestsError] = useState<string | null>(null)
  const [isSuggestionsApiUnavailable, setIsSuggestionsApiUnavailable] = useState(false)
  const watcherCountsRef = useRef<Record<string, number>>({})
  const suggestionsApiBase = `${dataCatalogApiBase}/suggestions`

  const buildAuthHeaders = useCallback((includeJson = false): HeadersInit => {
    const token = getAuthToken()
    return {
      ...(includeJson ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
  }, [])

  const updateRequest = useCallback((id: string, updater: (current: TrackedAsyncRequest) => TrackedAsyncRequest) => {
    setRequests((prev) => {
      const current = prev[id]
      if (!current) return prev
      return {
        ...prev,
        [id]: updater(current),
      }
    })
  }, [])

  const clearRequest = useCallback((id: string) => {
    setRequests((prev) => {
      if (!prev[id]) return prev
      const next = { ...prev }
      delete next[id]
      return next
    })
    delete watcherCountsRef.current[id]
  }, [])

  const registerWatcher = useCallback((id: string) => {
    watcherCountsRef.current[id] = (watcherCountsRef.current[id] || 0) + 1
  }, [])

  const unregisterWatcher = useCallback((id: string) => {
    const current = watcherCountsRef.current[id] || 0
    if (current <= 1) {
      delete watcherCountsRef.current[id]
      return
    }
    watcherCountsRef.current[id] = current - 1
  }, [])

  const shouldNotifyCompletion = useCallback((id: string): boolean => {
    const watcherCount = watcherCountsRef.current[id] || 0
    const pageHidden = typeof document !== 'undefined' ? document.hidden : false
    return pageHidden || watcherCount === 0
  }, [])

  const addBackgroundNotification = useCallback((payload: {
    id: string
    type: 'success' | 'error' | 'info'
    title: string
    message: string
    relatedId?: string
    actionUrl?: string
  }) => {
    if (!notifications?.addNotification) {
      return
    }

    notifications.addNotification({
      id: payload.id,
      type: payload.type,
      title: payload.title,
      message: payload.message,
      relatedId: payload.relatedId,
      actionUrl: payload.actionUrl,
    })
  }, [notifications])

  const createRequestRecord = useCallback((request: TrackedAsyncRequest) => {
    setRequests((prev) => ({
      ...prev,
      [request.id]: request,
    }))
  }, [])

  const finalizeRequest = useCallback((id: string, updates: Partial<TrackedAsyncRequest>) => {
    updateRequest(id, (current) => ({
      ...current,
      ...updates,
      updatedAt: currentTimestamp(),
      completedAt: updates.completedAt || currentTimestamp(),
    }))
  }, [updateRequest])

  const readAsyncStatusEvents = useCallback(async (
    apiBase: string,
    eventsUrl: string,
    handlePayload: (payload: AsyncStatusEventPayload) => Promise<boolean> | boolean,
  ) => {
    const response = await fetch(resolveAsyncEventsUrl(apiBase, eventsUrl), {
      headers: {
        ...buildAuthHeaders(),
        Accept: 'text/event-stream',
      },
    })
    if (!response.ok) {
      throw new Error(await buildErrorMessage(response, 'Failed to subscribe to async request events'))
    }
    if (!response.body) {
      throw new Error('Async request event stream did not return a response body.')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split(/\r?\n\r?\n/)
        buffer = frames.pop() || ''

        for (const frame of frames) {
          const eventPayload = parseAsyncStatusEventFrame(frame)
          if (!eventPayload) continue
          const stop = await handlePayload(eventPayload)
          if (stop) {
            await reader.cancel()
            return
          }
        }
      }

      const finalFrame = buffer.trim()
      if (finalFrame) {
        const eventPayload = parseAsyncStatusEventFrame(finalFrame)
        if (eventPayload) {
          await handlePayload(eventPayload)
        }
      }
    } finally {
      reader.releaseLock()
    }
  }, [buildAuthHeaders])

  const fetchNaturalLanguageDraftRequestStatus = useCallback(async (requestId: string) => {
    const response = await fetch(`${dataCatalogApiBase}/suggestions/natural-language-rule-previews/requests/${encodeURIComponent(requestId)}/status`, {
      headers: buildAuthHeaders(),
    })
    if (!response.ok) {
      throw new Error(await buildErrorMessage(response, 'Failed to fetch natural-language draft request status'))
    }
    return readJsonSafely(response)
  }, [dataCatalogApiBase, buildAuthHeaders])

  const normalizeNaturalLanguageRequest = useCallback((request: any): TrackedAsyncRequest => {
    const requestId = String(request?.requestId || request?.request_id || '').trim()
    const normalizedAnalysisType = String(request?.analysisType || request?.analysis_type || 'preview').trim().toLowerCase()
    const analysisType = normalizedAnalysisType === 'draft' || normalizedAnalysisType === 'steward' ? normalizedAnalysisType : 'preview'
    const status = normalizeTrackedStatus(request?.status)
    const title = analysisType === 'preview'
      ? 'Natural-language preview'
      : analysisType === 'draft'
        ? 'Natural-language draft'
        : 'Metadata steward'
    const startedAt = String(request?.startedAt || request?.started_at || request?.requestedAt || request?.requested_at || currentTimestamp())
    const completedAtValue = String(request?.completedAt || request?.completed_at || '').trim()
    const completedAt = completedAtValue || undefined
    const updatedAt = completedAtValue || String(request?.startedAt || request?.started_at || request?.requestedAt || request?.requested_at || currentTimestamp())
    const errorMessage = request?.errorMessage || request?.error_message || undefined

    return {
      id: requestId || buildTrackerId('nlreq'),
      kind: 'natural-language-draft',
      requestId,
      status,
      title,
      relatedId: requestId,
      sourceId: String(request?.currentWorkspaceId || request?.current_workspace_id || '').trim() || undefined,
      sourceName: String(request?.currentWorkspaceId || request?.current_workspace_id || '').trim() || undefined,
      message: status === 'completed'
        ? `${title} completed.`
        : status === 'failed'
          ? String(errorMessage || `${title} failed.`)
          : `${title} is running...`,
      errorMessage: status === 'failed' ? String(errorMessage || `${title} failed.`) : undefined,
      startedAt,
      updatedAt,
      completedAt,
      result: request?.result ?? request?.result_json ?? null,
      metadata: {
        analysisProvider: String(request?.analysisProvider || request?.analysis_provider || 'llm').trim().toLowerCase() || 'llm',
        analysisType,
      },
    }
  }, [])

  const refreshNaturalLanguageAnalysisRequests = useCallback(async () => {
    if (!auth.isAuthenticated || !auth.currentWorkspaceId || isSuggestionsApiUnavailable) {
      setNaturalLanguageAnalysisRequests([])
      setNaturalLanguageAnalysisRequestsError(null)
      return
    }

    const timer = startTimer()
    setNaturalLanguageAnalysisRequestsError(null)

    try {
      const queryParams = new URLSearchParams({ limit: '20', workspace_id: auth.currentWorkspaceId })
      const response = await fetch(`${suggestionsApiBase}/natural-language-rule-previews/requests?${queryParams.toString()}`, {
        headers: buildAuthHeaders(),
      })
      const data = await parseApiResponse(response)
      const rawRequests = Array.isArray(data?.requests) ? data.requests : []
      setNaturalLanguageAnalysisRequests(
        rawRequests.map(normalizeNaturalLanguageRequest).sort((left: TrackedAsyncRequest, right: TrackedAsyncRequest) => right.updatedAt.localeCompare(left.updatedAt)),
      )
      endTimer('natural-language.requests.fetch', timer, true, {
        count: rawRequests.length,
      })
    } catch (err) {
      if (isNotFoundError(err)) {
        setIsSuggestionsApiUnavailable(true)
        setNaturalLanguageAnalysisRequestsError(suggestionsApiUnavailableMessage)
        setNaturalLanguageAnalysisRequests([])
        endTimer('natural-language.requests.fetch', timer, false, {
          error: err instanceof Error ? err.message : String(err),
          unavailable: true,
        })
        return
      }

      setNaturalLanguageAnalysisRequests([])
      setNaturalLanguageAnalysisRequestsError(normalizeErrorMessage(err, 'Failed to fetch natural-language analysis requests', apiBaseUrl))
      endTimer('natural-language.requests.fetch', timer, false, {
        error: err instanceof Error ? err.message : String(err),
      })
    }
  }, [
    apiBaseUrl,
    auth.currentWorkspaceId,
    auth.isAuthenticated,
    buildAuthHeaders,
    endTimer,
    isSuggestionsApiUnavailable,
    normalizeNaturalLanguageRequest,
    startTimer,
    suggestionsApiBase,
  ])

  const runTestDataEventStream = useCallback(async (taskId: string, options: {
    requestId: string
    eventsUrl: string
    successTitle: string
    successMessage: string
    failureTitle: string
    failureFallbackMessage: string
    actionUrl?: string
    relatedId?: string
    completeRequestOnSuccess?: boolean
    notifyOnSuccess?: boolean
  }) => {
    await readAsyncStatusEvents(rulebuilderApiBase, options.eventsUrl, async (eventPayload) => {
      const payload = eventPayload.request || eventPayload
      const status = normalizeTrackedStatus(payload?.status)

      updateRequest(taskId, (current) => ({
        ...current,
        requestId: String(payload?.request_id || current.requestId),
        status: status === 'completed' && options.completeRequestOnSuccess === false ? 'running' : status,
        message: status === 'completed'
          ? options.successMessage
          : status === 'failed'
            ? String(payload?.error_message || options.failureFallbackMessage)
            : 'Waiting for generated samples...',
        errorMessage: status === 'failed' ? String(payload?.error_message || options.failureFallbackMessage) : undefined,
        updatedAt: currentTimestamp(),
        completedAt: payload?.completed_at || current.completedAt,
        result: status === 'completed' ? payload?.result || null : current.result,
        metadata: {
          ...(current.metadata || {}),
          requestPayload: payload,
        },
      }))

      if (status === 'completed') {
        if (options.completeRequestOnSuccess !== false) {
          finalizeRequest(taskId, {
            status: 'completed',
            result: payload?.result || null,
            completedAt: payload?.completed_at || currentTimestamp(),
            message: options.successMessage,
            metadata: {
              requestPayload: payload,
            },
          })
          if (options.notifyOnSuccess !== false && shouldNotifyCompletion(taskId)) {
            addBackgroundNotification({
              id: `${taskId}-completed`,
              type: 'success',
              title: options.successTitle,
              message: options.successMessage,
              relatedId: options.relatedId,
              actionUrl: options.actionUrl,
            })
          }
        }
        return true
      }

      if (status === 'failed') {
        const failureMessage = String(payload?.error_message || options.failureFallbackMessage)
        finalizeRequest(taskId, {
          status: 'failed',
          errorMessage: failureMessage,
          completedAt: payload?.completed_at || currentTimestamp(),
          message: failureMessage,
          metadata: {
            requestPayload: payload,
          },
        })
        if (shouldNotifyCompletion(taskId)) {
          addBackgroundNotification({
            id: `${taskId}-failed`,
            type: 'error',
            title: options.failureTitle,
            message: failureMessage,
            relatedId: options.relatedId,
            actionUrl: options.actionUrl,
          })
        }
        return true
      }

      return false
    })
  }, [addBackgroundNotification, finalizeRequest, readAsyncStatusEvents, rulebuilderApiBase, shouldNotifyCompletion, updateRequest])

  const startTestDataGeneration = useCallback(async (input: StartTestDataGenerationInput): Promise<string> => {
    const taskId = buildTrackerId('req')
    createRequestRecord({
      id: taskId,
      kind: 'test-data-generation',
      requestId: '',
      status: 'pending',
      title: 'Test data generation',
      relatedId: input.versionId,
      message: 'Submitting test data generation request...',
      startedAt: currentTimestamp(),
      updatedAt: currentTimestamp(),
      metadata: {
        versionId: input.versionId,
        versionName: input.versionName,
        dataObjectId: input.dataObjectId,
      },
    })

    try {
      const response = await fetch(`${rulebuilderApiBase}/test-data/requests`, {
        method: 'POST',
        headers: buildAuthHeaders(true),
        body: JSON.stringify({
          target_type: 'data_object_version',
          target_id: input.versionId,
          sample_count: input.sampleCount,
          version_name: input.versionName,
          data_object_id: input.dataObjectId,
        }),
      })

      if (!response.ok) {
        throw new Error(await buildErrorMessage(response, 'Failed to create test data request'))
      }

      const payload = await readJsonSafely(response)
      const requestId = String(payload?.request_id || '').trim()
      if (!requestId) {
        throw new Error('Failed to create test data request: missing request_id')
      }
      const eventsUrl = String(payload?.events_url || '').trim()
      if (!eventsUrl) {
        throw new Error('Failed to create test data request: missing events_url')
      }

      updateRequest(taskId, (current) => ({
        ...current,
        requestId,
        status: 'running',
        message: 'Waiting for generated samples...',
        updatedAt: currentTimestamp(),
      }))

      void runTestDataEventStream(taskId, {
        requestId,
        eventsUrl,
        successTitle: 'Test Data Ready',
        successMessage: 'Generated test data is ready to review.',
        failureTitle: 'Test Data Generation Failed',
        failureFallbackMessage: 'Failed to generate test data.',
        relatedId: input.versionId,
      })

      return taskId
    } catch (error) {
      clearRequest(taskId)
      throw error
    }
  }, [rulebuilderApiBase, buildAuthHeaders, clearRequest, createRequestRecord, runTestDataEventStream, updateRequest])

  const startRuleTest = useCallback(async (input: StartRuleTestInput): Promise<string> => {
    const taskId = buildTrackerId('req')
    const startedAt = currentTimestamp()
    createRequestRecord({
      id: taskId,
      kind: 'rule-test',
      requestId: '',
      status: 'pending',
      title: `Rule test: ${input.ruleName}`,
      relatedId: input.ruleId,
      actionUrl: '/rules',
      sourceId: input.versionId,
      message: 'Submitting rule test request...',
      startedAt,
      updatedAt: startedAt,
      metadata: {
        ruleId: input.ruleId,
        ruleName: input.ruleName,
        versionId: input.versionId,
        sampleCount: input.sampleCount,
        selectedAttributes: input.selectedAttributes,
        semanticMatching: input.semanticMatching,
      },
    })

    let proofId = ''
    try {
      const startResponse = await fetch(`${rulebuilderApiBase}/rules/${encodeURIComponent(input.ruleId)}/test-runs/start`, {
        method: 'POST',
        headers: buildAuthHeaders(true),
        body: JSON.stringify({
          version_id: input.versionId,
          sample_count: input.sampleCount,
          semantic_matching: input.semanticMatching || null,
        }),
      })

      if (!startResponse.ok) {
        throw new Error(await buildErrorMessage(startResponse, 'Failed to start rule test'))
      }

      const startedProof = await readJsonSafely(startResponse)
      proofId = String(startedProof?.id || startedProof?.proof_id || '').trim()
      if (!proofId) {
        throw new Error('Rule test start did not return a persisted proof id.')
      }

      if (rules?.applyStoredTestProof) {
        rules.applyStoredTestProof(input.ruleId, startedProof)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to start rule test'
      finalizeRequest(taskId, {
        status: 'failed',
        errorMessage: message,
        message,
      })
      if (shouldNotifyCompletion(taskId)) {
        addBackgroundNotification({
          id: `${taskId}-failed-start`,
          type: 'error',
          title: 'Rule Test Failed',
          message,
          relatedId: input.ruleId,
          actionUrl: '/rules',
        })
      }
      throw error
    }

    updateRequest(taskId, (current) => ({
      ...current,
      requestId: proofId,
      status: 'running',
      message: 'Generating test data and executing rule...',
      updatedAt: currentTimestamp(),
      metadata: {
        ...(current.metadata || {}),
        proofId,
      },
    }))

    void (async () => {
      let storedProofApplied = false

      try {
        const executionResponse = await fetch(`${rulebuilderApiBase}/rules/${encodeURIComponent(input.ruleId)}/test-with-generated-data`, {
          method: 'POST',
          headers: buildAuthHeaders(true),
          body: JSON.stringify({
            version_id: input.versionId,
            sample_count: input.sampleCount,
            semantic_matching: input.semanticMatching || null,
            proof_id: proofId,
          }),
        })

        if (!executionResponse.ok) {
          const errorPayload = await readJsonSafely(executionResponse)
          const storedProof = errorPayload?.detail?.stored_proof
          if (storedProof && rules?.applyStoredTestProof) {
            storedProofApplied = true
            rules.applyStoredTestProof(input.ruleId, storedProof)
          }

          const detailMessage =
            typeof errorPayload === 'string'
              ? errorPayload.trim()
              : typeof errorPayload?.detail === 'string'
                ? errorPayload.detail.trim()
                : typeof errorPayload?.detail?.message === 'string'
                  ? errorPayload.detail.message.trim()
                  : typeof errorPayload?.message === 'string'
                    ? errorPayload.message.trim()
                    : `${executionResponse.status} ${executionResponse.statusText}`

          throw new Error(`Test failed: ${detailMessage}`)
        }

        const result = await readJsonSafely(executionResponse)
        const storedProof = result?.stored_proof ?? result?.storedProof
        if (!storedProof || !rules?.applyStoredTestProof) {
          throw new Error('Rule test completed without a persisted proof result.')
        }
        storedProofApplied = true
        rules.applyStoredTestProof(input.ruleId, storedProof)

        const testedCount = Number(result?.totalTests ?? result?.recordsTestedCount ?? input.sampleCount)
        const failedCount = Number(result?.failedCount ?? result?.failuresFound ?? 0)
        const passedCount = Number(result?.passedCount ?? result?.passed ?? Math.max(0, testedCount - failedCount))
        const coverage = Number(result?.coverage ?? result?.successRate ?? (testedCount > 0 ? (passedCount / testedCount) * 100 : 0))

        if (testedCount <= 0) {
          throw new Error('No test records were executed. The selected data-object version may be missing or has no attributes.')
        }

        const testPassed = typeof result?.rulePassed === 'boolean' ? result.rulePassed : failedCount === 0

        if (testPassed && rules.updateRuleStatus) {
          await rules.updateRuleStatus(input.ruleId, 'tested')
        }

        const executionSummary = {
          passed: passedCount,
          failed: failedCount,
          coverage,
          rulePassed: testPassed,
          requiredSuccessRate: result?.requiredSuccessRate,
          recordsTestedCount: testedCount,
          joinEvaluated: result?.joinEvaluated,
          joinMatchedContexts: result?.joinMatchedContexts,
          joinDefinitions: result?.joinDefinitions,
          proofId: storedProof?.id || storedProof?.proof_id || result?.proofId,
          selectedAttributes: input.selectedAttributes,
          semanticMatching: result?.executionContext?.semanticMatching,
        }

        finalizeRequest(taskId, {
          status: 'completed',
          message: testPassed
            ? `Rule test passed for ${input.ruleName}.`
            : `Rule test completed with ${failedCount} failures for ${input.ruleName}.`,
          result: executionSummary,
        })

        if (shouldNotifyCompletion(taskId)) {
          addBackgroundNotification({
            id: `${taskId}-completed`,
            type: testPassed ? 'success' : 'error',
            title: 'Rule Test Completed',
            message: testPassed
              ? `${input.ruleName} passed across ${testedCount} generated records.`
              : `${input.ruleName} completed with ${failedCount} failures out of ${testedCount} generated records.`,
            relatedId: input.ruleId,
            actionUrl: '/rules',
          })
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Rule test failed'

        finalizeRequest(taskId, {
          status: 'failed',
          errorMessage: message,
          message,
        })

        if (shouldNotifyCompletion(taskId)) {
          addBackgroundNotification({
            id: `${taskId}-failed`,
            type: 'error',
            title: 'Rule Test Failed',
            message,
            relatedId: input.ruleId,
            actionUrl: '/rules',
          })
        }
      }
    })()

    return taskId
  }, [rulebuilderApiBase, buildAuthHeaders, createRequestRecord, finalizeRequest, rules, shouldNotifyCompletion, addBackgroundNotification, updateRequest])

  const trackProfilingRequest = useCallback((input: TrackProfilingRequestInput): string => {
    const taskId = buildTrackerId('req')
    const title = input.mode === 'mock-preview' ? 'Mock data generation' : 'Data profiling'

    createRequestRecord({
      id: taskId,
      kind: 'profiling',
      requestId: input.requestId,
      status: 'running',
      title,
      relatedId: input.requestId,
      sourceId: input.dataSourceId,
      sourceName: input.dataSourceName,
      message: input.mode === 'mock-preview' ? 'Generating preview data...' : 'Profiling is running...',
      startedAt: currentTimestamp(),
      updatedAt: currentTimestamp(),
      metadata: {
        mode: input.mode,
        eventsUrl: input.eventsUrl,
      },
    })

    void (async () => {
      try {
        await readAsyncStatusEvents(
          input.mode === 'mock-preview' ? rulebuilderApiBase : dataCatalogApiBase,
          input.eventsUrl,
          async (payload) => {
          const requestPayload = payload.request || payload
          const status = normalizeTrackedStatus(requestPayload?.status)
          const errorMessage = requestPayload?.error_message || requestPayload?.errorMessage

          updateRequest(taskId, (current) => ({
            ...current,
            status,
            message: status === 'completed'
              ? input.mode === 'mock-preview'
                ? 'Mock data generation completed.'
                : 'Profiling completed.'
              : status === 'failed'
                ? String(errorMessage || 'Profiling failed.')
                : input.mode === 'mock-preview'
                  ? 'Generating preview data...'
                  : 'Profiling is running...',
            errorMessage: status === 'failed' ? String(errorMessage || 'Profiling failed.') : undefined,
            updatedAt: currentTimestamp(),
            completedAt: requestPayload?.completed_at || requestPayload?.completedAt || current.completedAt,
            result: requestPayload || payload,
            metadata: {
              ...(current.metadata || {}),
              mode: input.mode,
              response: payload,
            },
          }))

          if (status === 'completed') {
            finalizeRequest(taskId, {
              status: 'completed',
              message: input.mode === 'mock-preview'
                ? 'Mock data generation completed.'
                : 'Profiling completed.',
              result: requestPayload || payload,
              completedAt: requestPayload?.completed_at || requestPayload?.completedAt || currentTimestamp(),
              metadata: {
                mode: input.mode,
                response: payload,
              },
            })

            if (shouldNotifyCompletion(taskId)) {
              addBackgroundNotification({
                id: `${taskId}-completed`,
                type: 'success',
                title: input.mode === 'mock-preview' ? 'Mock Data Ready' : 'Profiling Completed',
                message: input.mode === 'mock-preview'
                  ? `${input.dataSourceName} preview data is ready.`
                  : `${input.dataSourceName} finished profiling. Suggestions are ready to review.`,
                relatedId: input.requestId,
              })
            }
            return true
          }

          if (status === 'failed') {
            const failureMessage = String(errorMessage || 'Profiling failed.')
            finalizeRequest(taskId, {
              status: 'failed',
              errorMessage: failureMessage,
              message: failureMessage,
              completedAt: requestPayload?.completed_at || requestPayload?.completedAt || currentTimestamp(),
              metadata: {
                mode: input.mode,
                response: payload,
              },
            })
            if (shouldNotifyCompletion(taskId)) {
              addBackgroundNotification({
                id: `${taskId}-failed`,
                type: 'error',
                title: input.mode === 'mock-preview' ? 'Mock Data Generation Failed' : 'Profiling Failed',
                message: failureMessage,
                relatedId: input.requestId,
              })
            }
            return true
          }

          return false
        })
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to subscribe to request events'
        finalizeRequest(taskId, {
          status: 'failed',
          errorMessage: message,
          message,
          metadata: {
            mode: input.mode,
          },
        })
        if (shouldNotifyCompletion(taskId)) {
          addBackgroundNotification({
            id: `${taskId}-failed`,
            type: 'error',
            title: input.mode === 'mock-preview' ? 'Mock Data Generation Failed' : 'Profiling Failed',
            message,
            relatedId: input.requestId,
          })
        }
      }
    })()

    return taskId
  }, [addBackgroundNotification, createRequestRecord, dataCatalogApiBase, finalizeRequest, readAsyncStatusEvents, rulebuilderApiBase, shouldNotifyCompletion, updateRequest])

  const trackNaturalLanguageDraftRequest = useCallback((input: TrackNaturalLanguageDraftRequestInput): string => {
    const taskId = buildTrackerId('req')
    const analysisType = input.analysisType || 'draft'
    const requestTitle = analysisType === 'preview' ? 'Natural-language preview' : 'Natural-language draft'
    const runningMessage = analysisType === 'preview'
      ? 'Preview request is running...'
      : 'Draft suggestion request is running...'
    const completedMessage = analysisType === 'preview'
      ? 'Preview request completed.'
      : 'Draft suggestion request completed.'
    const fallbackFailureMessage = analysisType === 'preview'
      ? 'Preview request failed.'
      : 'Draft suggestion request failed.'
    const successNotificationTitle = analysisType === 'preview' ? 'Preview Ready' : 'Draft Suggestion Ready'
    const failureNotificationTitle = analysisType === 'preview' ? 'Preview Failed' : 'Draft Suggestion Failed'

    createRequestRecord({
      id: taskId,
      kind: 'natural-language-draft',
      requestId: input.requestId,
      status: 'running',
      title: requestTitle,
      relatedId: input.requestId,
      sourceId: input.workspaceId,
      sourceName: input.workspaceName,
      message: runningMessage,
      startedAt: currentTimestamp(),
      updatedAt: currentTimestamp(),
      metadata: {
        analysisProvider: input.analysisProvider,
        analysisType,
      },
    })

    void (async () => {
      for (let pollCount = 0; pollCount < PROFILING_MAX_POLLS; pollCount += 1) {
        try {
          const payload = await fetchNaturalLanguageDraftRequestStatus(input.requestId)
          const requestPayload = payload?.request
          const status = normalizeTrackedStatus(requestPayload?.status)
          const errorMessage = requestPayload?.error_message || requestPayload?.errorMessage

          updateRequest(taskId, (current) => ({
            ...current,
            status,
            message: status === 'completed'
              ? completedMessage
              : status === 'failed'
                ? String(errorMessage || fallbackFailureMessage)
                : runningMessage,
            errorMessage: status === 'failed' ? String(errorMessage || fallbackFailureMessage) : undefined,
            updatedAt: currentTimestamp(),
            completedAt: requestPayload?.completed_at || requestPayload?.completedAt || current.completedAt,
            result: requestPayload || payload,
            metadata: {
              ...(current.metadata || {}),
              response: payload,
            },
          }))

          if (status === 'completed') {
            finalizeRequest(taskId, {
              status: 'completed',
              message: completedMessage,
              result: requestPayload || payload,
              completedAt: requestPayload?.completed_at || requestPayload?.completedAt || currentTimestamp(),
              metadata: {
                analysisProvider: input.analysisProvider,
                analysisType,
                response: payload,
              },
            })

            if (shouldNotifyCompletion(taskId)) {
              addBackgroundNotification({
                id: `${taskId}-completed`,
                type: 'success',
                title: successNotificationTitle,
                message: analysisType === 'preview'
                  ? `${input.workspaceName} preview is ready to review.`
                  : `${input.workspaceName} draft suggestion is ready to review.`,
                relatedId: input.requestId,
              })
            }
            return
          }

          if (status === 'failed') {
            const failureText = String(errorMessage || fallbackFailureMessage)
            finalizeRequest(taskId, {
              status: 'failed',
              errorMessage: failureText,
              message: failureText,
              completedAt: requestPayload?.completed_at || requestPayload?.completedAt || currentTimestamp(),
              metadata: {
                analysisProvider: input.analysisProvider,
                analysisType,
                response: payload,
              },
            })
            if (shouldNotifyCompletion(taskId)) {
              addBackgroundNotification({
                id: `${taskId}-failed`,
                type: 'error',
                title: failureNotificationTitle,
                message: failureText,
                relatedId: input.requestId,
              })
            }
            return
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to poll draft suggestion request status'
          finalizeRequest(taskId, {
            status: 'failed',
            errorMessage: message,
            message,
            metadata: {
              analysisProvider: input.analysisProvider,
              analysisType,
            },
          })
          if (shouldNotifyCompletion(taskId)) {
            addBackgroundNotification({
              id: `${taskId}-failed`,
              type: 'error',
              title: failureNotificationTitle,
              message,
              relatedId: input.requestId,
            })
          }
          return
        }

        await sleep(PROFILING_POLL_INTERVAL_MS)
      }

      const timeoutMessage = analysisType === 'preview'
        ? 'Preview request is still running. Check Notifications for completion updates.'
        : 'Draft suggestion request is still running. Check Notifications for completion updates.'
      finalizeRequest(taskId, {
        status: 'timed_out',
        errorMessage: timeoutMessage,
        message: timeoutMessage,
      })
      if (shouldNotifyCompletion(taskId)) {
        addBackgroundNotification({
          id: `${taskId}-timed-out`,
          type: 'info',
          title: analysisType === 'preview' ? 'Preview Pending' : 'Draft Suggestion Pending',
          message: timeoutMessage,
          relatedId: input.requestId,
        })
      }
    })()

    return taskId
  }, [addBackgroundNotification, createRequestRecord, fetchNaturalLanguageDraftRequestStatus, finalizeRequest, shouldNotifyCompletion, updateRequest])

  useEffect(() => {
    void refreshNaturalLanguageAnalysisRequests()
  }, [refreshNaturalLanguageAnalysisRequests])

  const value = useMemo<AsyncRequestTrackerContextType>(() => ({
    requests,
    naturalLanguageAnalysisRequests,
    naturalLanguageAnalysisRequestsError,
    startTestDataGeneration,
    startRuleTest,
    trackProfilingRequest,
    trackNaturalLanguageDraftRequest,
    refreshNaturalLanguageAnalysisRequests,
    clearRequest,
    registerWatcher,
    unregisterWatcher,
  }), [clearRequest, naturalLanguageAnalysisRequests, naturalLanguageAnalysisRequestsError, refreshNaturalLanguageAnalysisRequests, registerWatcher, requests, startRuleTest, startTestDataGeneration, trackNaturalLanguageDraftRequest, trackProfilingRequest, unregisterWatcher])

  return <AsyncRequestTrackerContext.Provider value={value}>{children}</AsyncRequestTrackerContext.Provider>
}

export const useAsyncRequestTrackerContext = (): AsyncRequestTrackerContextType => {
  const context = useContext(AsyncRequestTrackerContext)
  if (!context) {
    throw new Error('useAsyncRequestTrackerContext must be used within AsyncRequestTrackerProvider')
  }
  return context
}