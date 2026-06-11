import { diag, DiagConsoleLogger, DiagLogLevel, metrics, SpanStatusCode, trace, type Counter, type ObservableGauge, type Span } from '@opentelemetry/api'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http'
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch'
import { XMLHttpRequestInstrumentation } from '@opentelemetry/instrumentation-xml-http-request'
import { resourceFromAttributes } from '@opentelemetry/resources'
import { BatchSpanProcessor, ParentBasedSampler, TraceIdRatioBasedSampler } from '@opentelemetry/sdk-trace-base'
import { MeterProvider, PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics'
import { StackContextManager, WebTracerProvider } from '@opentelemetry/sdk-trace-web'

const SESSION_CORRELATION_KEY = 'dq.correlation_id'
const MANUAL_UI_TRACER_NAME = 'dq-ui.manual'
const DQ_FETCH_PATCH_MARKER = '__dqFetchPatched'
const UI_METER_NAME = 'dq-ui'
const UI_PAGE_VIEW_COUNTER_NAME = 'dq_ui_page_views_total'
const UI_ACTIVE_SESSIONS_GAUGE_NAME = 'dq_ui_active_sessions'
const UI_METRIC_EXPORT_INTERVAL_MS = 15000
const UI_METRIC_EXPORT_TIMEOUT_MS = 10000
const UI_TELEMETRY_RETRY_INTERVAL_MS = 30000
const UI_TELEMETRY_IGNORED_PATH = '/api/admin/v1/me'
const UI_TELEMETRY_STATUS_EVENT = 'dq-ui-telemetry-status'
let telemetryBootstrapStarted = false
let telemetryRuntimeStarted = false
let telemetryRetryTimer: number | null = null
let uiPageViewCounter: Counter | null = null
let uiActiveSessionGauge: ObservableGauge | null = null
let uiSessionActive = false
type UiTelemetryConnectionState = 'disabled' | 'checking' | 'available' | 'unavailable'
interface UiTelemetryStatusEventDetail {
  state: UiTelemetryConnectionState
}
let uiTelemetryConnectionState: UiTelemetryConnectionState = 'disabled'

type SpanAttributeValue = string | number | boolean

const setSpanAttributes = (span: Span, attributes?: Record<string, SpanAttributeValue>): void => {
  if (!attributes) {
    return
  }

  Object.entries(attributes).forEach(([key, value]) => {
    span.setAttribute(key, value)
  })
}

const toErrorMessage = (error: unknown): string => {
  if (error instanceof Error) {
    return error.message
  }

  return String(error)
}

const sanitizeSampleRatio = (value: string | undefined): number => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return 0.1
  }

  if (parsed < 0) return 0
  if (parsed > 1) return 1
  return parsed
}

const readServiceName = (): string => (import.meta.env.OTEL_SERVICE_NAME || 'dq-ui').trim() || 'dq-ui'
const readServiceVersion = (): string =>
  (import.meta.env.VITE_SERVICE_VERSION || import.meta.env.OTEL_SERVICE_VERSION || 'dev').trim() || 'dev'
const readEnvironment = (): string => (import.meta.env.VITE_ENVIRONMENT || 'dev').trim() || 'dev'

const readOtlpHttpEndpoint = (signalType: 'traces' | 'metrics'): string | null => {
  const configured = (import.meta.env.VITE_OTEL_ENDPOINT || '').trim()
  const suffix = signalType === 'metrics' ? '/v1/metrics' : '/v1/traces'
  if (configured) {
    if (window.isSecureContext && configured.startsWith('http://')) {
      return null
    }
    return configured.replace(/\/$/, '') + suffix
  }

  const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:'
  return `${protocol}//${window.location.hostname}:4318${suffix}`
}

export const normalizeUiPageName = (navId: string): string => {
  const normalized = navId.trim().toLowerCase()

  if (!normalized) {
    return 'unknown'
  }

  if (normalized.startsWith('rules')) return 'rules'
  if (normalized.startsWith('rule-quality')) return 'rule_quality'
  if (normalized.startsWith('approvals')) return 'governance'
  if (normalized.startsWith('data-browser')) return 'data_browser'
  if (normalized.startsWith('reports')) return 'operations'
  if (normalized.startsWith('templates')) return 'templates'
  if (normalized.startsWith('audit')) return 'audit'
  if (normalized.startsWith('administration')) return 'administration'

  return normalized.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'unknown'
}

export const isUiTelemetrySuppressedUrl = (rawUrl: string): boolean => {
  try {
    const url = new URL(rawUrl, window.location.origin)
    const path = url.pathname.replace(/\/+$/, '')
    return path === UI_TELEMETRY_IGNORED_PATH
  } catch {
    return false
  }
}

export const setUiSessionActive = (isActive: boolean): void => {
  uiSessionActive = isActive
}

export const recordUiPageView = (navId: string): void => {
  if (!uiPageViewCounter) {
    return
  }

  uiPageViewCounter.add(1, {
    page_name: normalizeUiPageName(navId),
  })
}

const setUiTelemetryConnectionState = (nextState: UiTelemetryConnectionState): void => {
  if (uiTelemetryConnectionState === nextState) {
    return
  }

  uiTelemetryConnectionState = nextState
  window.dispatchEvent(new CustomEvent<UiTelemetryStatusEventDetail>(UI_TELEMETRY_STATUS_EVENT, {
    detail: { state: nextState },
  }))
}

export const getUiTelemetryConnectionState = (): UiTelemetryConnectionState => uiTelemetryConnectionState

export const subscribeUiTelemetryConnectionState = (
  listener: (state: UiTelemetryConnectionState) => void,
): (() => void) => {
  const handleStatusChange = (event: Event): void => {
    const detail = (event as CustomEvent<UiTelemetryStatusEventDetail>).detail
    listener(detail.state)
  }

  window.addEventListener(UI_TELEMETRY_STATUS_EVENT, handleStatusChange)
  return () => window.removeEventListener(UI_TELEMETRY_STATUS_EVENT, handleStatusChange)
}

const createCorrelationId = (): string => {
  const webCrypto = globalThis.crypto

  if (typeof webCrypto?.randomUUID === 'function') {
    return webCrypto.randomUUID()
  }

  if (typeof webCrypto?.getRandomValues === 'function') {
    const bytes = new Uint8Array(16)
    webCrypto.getRandomValues(bytes)
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80

    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }

  const fallback = `${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 14)}`
  return `fallback-${fallback}`
}

const getOrCreateCorrelationId = (): string => {
  const existing = window.sessionStorage.getItem(SESSION_CORRELATION_KEY)
  if (existing) {
    return existing
  }

  const value = createCorrelationId()
  window.sessionStorage.setItem(SESSION_CORRELATION_KEY, value)
  return value
}

const endpointCategoryFromUrl = (rawUrl: string): string => {
  try {
    const url = new URL(rawUrl, window.location.origin)
    const tokens = url.pathname.split('/').filter(Boolean)
    if (tokens.length === 0) {
      return 'root'
    }

    const isVersionToken = (value: string | undefined): boolean => /^v\d+$/i.test(String(value || ''))

    // Internal API: /api/<group>/v1/...
    if (tokens[0] === 'api' && isVersionToken(tokens[2])) {
      return tokens[1] || 'unknown'
    }

    // Gateway/public API: /<group>/v1/...
    if (isVersionToken(tokens[1])) {
      return tokens[0] || 'unknown'
    }

    return tokens[0] || 'unknown'
  } catch {
    return 'unknown'
  }
}

import { camelToSnake, snakeToCamel } from './utils/caseConverters'

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  Object.prototype.toString.call(value) === '[object Object]'

const isApiRequestUrl = (rawUrl: string): boolean => {
  try {
    const parsed = new URL(rawUrl, window.location.origin)
    const path = parsed.pathname || ''
    if (path === '/api' || path.startsWith('/api/')) {
      return true
    }
    return /^\/[a-z][a-z0-9-]*\/v\d+(?:\/|$)/i.test(path)
  } catch {
    return false
  }
}

const hasJsonContentType = (headers: Headers): boolean =>
  (headers.get('Content-Type') || headers.get('content-type') || '').toLowerCase().includes('application/json')

const clearTelemetryRetryTimer = (): void => {
  if (telemetryRetryTimer !== null) {
    window.clearInterval(telemetryRetryTimer)
    telemetryRetryTimer = null
  }
}

const isTelemetryEndpointReachable = async (endpoint: string): Promise<boolean> => {
  try {
    const response = await fetch(endpoint, {
      method: 'OPTIONS',
      mode: 'cors',
      cache: 'no-store',
      credentials: 'omit',
    })
    return response.ok || response.status === 405
  } catch {
    return false
  }
}

const startTelemetryRuntime = (resource: ReturnType<typeof resourceFromAttributes>, otlpHttpEndpoint: string): void => {
  if (telemetryRuntimeStarted) {
    return
  }

  telemetryRuntimeStarted = true
  clearTelemetryRetryTimer()

  if (import.meta.env.DEV) {
    diag.setLogger(new DiagConsoleLogger(), DiagLogLevel.ERROR)
  }

  const metricProvider = new MeterProvider({
    resource,
    readers: [
      new PeriodicExportingMetricReader({
        exporter: new OTLPMetricExporter({
          url: readOtlpHttpEndpoint('metrics') || undefined,
        }),
        exportIntervalMillis: UI_METRIC_EXPORT_INTERVAL_MS,
        exportTimeoutMillis: UI_METRIC_EXPORT_TIMEOUT_MS,
      }),
    ],
  })

  metrics.setGlobalMeterProvider(metricProvider)

  const uiMeter = metrics.getMeter(UI_METER_NAME, readServiceVersion())
  uiPageViewCounter = uiMeter.createCounter(UI_PAGE_VIEW_COUNTER_NAME, {
    description: 'Total UI page views by page family',
  })
  uiActiveSessionGauge = uiMeter.createObservableGauge(UI_ACTIVE_SESSIONS_GAUGE_NAME, {
    description: 'Active authenticated UI sessions observed in this browser',
  })
  uiActiveSessionGauge.addCallback((observableResult) => {
    observableResult.observe(uiSessionActive ? 1 : 0)
  })

  const provider = new WebTracerProvider({
    resource,
    sampler: new ParentBasedSampler({
      root: new TraceIdRatioBasedSampler(sanitizeSampleRatio(import.meta.env.VITE_OTEL_SAMPLE_RATIO)),
    }),
    spanProcessors: [
      new BatchSpanProcessor(
        new OTLPTraceExporter({
          url: otlpHttpEndpoint,
        })
      ),
    ],
  })

  provider.register({
    contextManager: new StackContextManager(),
  })

  const traceHeaderPropagationUrls = [
    /\/api\//i,
    /\/[a-z][a-z0-9-]*\/v\d+(?:\/|$)/i,
  ]

  new FetchInstrumentation({
    ignoreUrls: [UI_TELEMETRY_IGNORED_PATH],
    // Only propagate trace headers to our app/gateway API paths.
    // Do not send traceparent to external auth providers like Keycloak,
    // which can reject custom CORS headers on token exchange requests.
    propagateTraceHeaderCorsUrls: traceHeaderPropagationUrls,
    applyCustomAttributesOnSpan(span, request, result) {
      const url = toStringUrl(request)
      span.setAttribute('dq.endpoint_category', endpointCategoryFromUrl(url))

      const status = (result as { status?: unknown }).status
      if (typeof status === 'number') {
        span.setAttribute('http.response.status_code', status)
        if (status >= 400) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: `HTTP ${status}` })
        }
      }
    },
  }).setTracerProvider(provider)

  new XMLHttpRequestInstrumentation({
    ignoreUrls: [UI_TELEMETRY_IGNORED_PATH],
    propagateTraceHeaderCorsUrls: traceHeaderPropagationUrls,
    applyCustomAttributesOnSpan(span, xhr) {
      span.setAttribute('dq.endpoint_category', endpointCategoryFromUrl(xhr.responseURL || ''))

      if (typeof xhr.status === 'number' && xhr.status > 0) {
        span.setAttribute('http.response.status_code', xhr.status)
        if (xhr.status >= 400) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: `HTTP ${xhr.status}` })
        }
      }
    },
  }).setTracerProvider(provider)

  // IMPORTANT: Apply our fetch wrapper after OTEL instrumentation.
  // OTEL's fetch instrumentation may return a proxied Response, which can bypass
  // per-response json() overrides if we patch fetch earlier.
  patchFetchForCorrelationHeader()

  setUiTelemetryConnectionState('available')
}

const retryTelemetryRuntimeBootstrap = async (resource: ReturnType<typeof resourceFromAttributes>, otlpHttpEndpoint: string): Promise<void> => {
  if (telemetryRuntimeStarted) {
    setUiTelemetryConnectionState('available')
    clearTelemetryRetryTimer()
    return
  }

  setUiTelemetryConnectionState('checking')
  const reachable = await isTelemetryEndpointReachable(otlpHttpEndpoint)

  if (reachable) {
    startTelemetryRuntime(resource, otlpHttpEndpoint)
    return
  }

  setUiTelemetryConnectionState('unavailable')

  if (telemetryRetryTimer === null) {
    telemetryRetryTimer = window.setInterval(() => {
      void retryTelemetryRuntimeBootstrap(resource, otlpHttpEndpoint)
    }, UI_TELEMETRY_RETRY_INTERVAL_MS)
  }
}

export const patchFetchForCorrelationHeader = (): void => {
  const existing = window.fetch as any
  if (existing && existing[DQ_FETCH_PATCH_MARKER]) {
    return
  }

  const originalFetch = window.fetch.bind(window)

  const patchedFetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null
    const rawUrl = request ? request.url : String(input)
    if (isUiTelemetrySuppressedUrl(rawUrl)) {
      return originalFetch(input, init)
    }
    const isApiRequest = isApiRequestUrl(rawUrl)
    const headers = new Headers(init?.headers || request?.headers || {})
    const credentials: RequestCredentials | undefined = init?.credentials ?? (isApiRequest ? 'include' : undefined)

    if (isApiRequest && !headers.has('X-Correlation-ID')) {
      headers.set('X-Correlation-ID', getOrCreateCorrelationId())
    }

    let nextBody = init?.body
    if (isApiRequest && hasJsonContentType(headers) && typeof nextBody === 'string') {
      try {
        const parsed = JSON.parse(nextBody)
        nextBody = JSON.stringify(camelToSnake(parsed))
      } catch {
        nextBody = init?.body
      }
    }

    const normalizeApiJsonResponse = (response: Response): Response => {
      const responseType = (response.headers.get('content-type') || '').toLowerCase()
      if (!isApiRequest || !responseType.includes('application/json')) {
        return response
      }

      const originalJson = response.json.bind(response)
      response.json = async () => {
        const payload = await originalJson()
        return snakeToCamel(payload)
      }
      return response
    }

    if (request) {
      const overridden = new Request(request, { ...(init ?? {}), headers, body: nextBody, credentials })
      const response = await originalFetch(overridden)
      return normalizeApiJsonResponse(response)
    }

    const response = await originalFetch(input, { ...init, headers, body: nextBody, credentials })
    return normalizeApiJsonResponse(response)
  }) as typeof window.fetch

  ;(patchedFetch as any)[DQ_FETCH_PATCH_MARKER] = true
  window.fetch = patchedFetch
}

const toStringUrl = (request: Request | RequestInit | string | URL): string => {
  if (typeof request === 'string') {
    return request
  }

  if (request instanceof URL) {
    return request.toString()
  }

  if (request instanceof Request) {
    return request.url
  }

  const maybeUrl = (request as { url?: unknown }).url
  return typeof maybeUrl === 'string' ? maybeUrl : ''
}

export const startUiSpan = (name: string, attributes?: Record<string, SpanAttributeValue>): Span => {
  const span = trace.getTracer(MANUAL_UI_TRACER_NAME).startSpan(name)
  setSpanAttributes(span, attributes)
  return span
}

export const withUiSpan = async <T>(
  name: string,
  attributes: Record<string, SpanAttributeValue> | undefined,
  operation: (span: Span) => Promise<T>
): Promise<T> => {
  const span = startUiSpan(name, attributes)

  try {
    const result = await operation(span)
    span.setStatus({ code: SpanStatusCode.OK })
    return result
  } catch (error) {
    span.setStatus({ code: SpanStatusCode.ERROR, message: toErrorMessage(error) })
    throw error
  } finally {
    span.end()
  }
}

export const initTelemetry = (): void => {
  if (telemetryBootstrapStarted || typeof window === 'undefined') {
    return
  }

  telemetryBootstrapStarted = true

  // Even when OTEL is disabled, we still want correlation IDs and payload casing conversion.
  patchFetchForCorrelationHeader()

  // IMPORTANT: OTLP export from the browser should be opt-in.
  // Defaulting to enabled causes noisy CORS/network errors unless an OTLP HTTP
  // collector endpoint is explicitly exposed with the right CORS settings.
  const enabledOverride = (import.meta.env.VITE_OTEL_ENABLED || '').trim().toLowerCase()
  const hasConfiguredEndpoint = (import.meta.env.VITE_OTEL_ENDPOINT || '').trim().length > 0
  const enabled =
    enabledOverride === 'true' ? true : enabledOverride === 'false' ? false : hasConfiguredEndpoint
  const otlpHttpEndpoint = readOtlpHttpEndpoint('traces')
  if (!enabled || !otlpHttpEndpoint) {
    setUiTelemetryConnectionState('disabled')
    return
  }

  const resource = resourceFromAttributes({
    'service.name': readServiceName(),
    'service.version': readServiceVersion(),
    environment: readEnvironment(),
  })
  setUiTelemetryConnectionState('checking')
  void retryTelemetryRuntimeBootstrap(resource, otlpHttpEndpoint)

}