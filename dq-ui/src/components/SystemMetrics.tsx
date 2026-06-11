import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { usePerformanceMonitoringContext } from '../contexts/PerformanceMonitoringContext'
import { useAuth, useSettings } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { AdminPageHeader } from './AdminPageHeader'
import { AppIcon, AppTabs } from './app-primitives'
import { Button } from './Button'
import './SystemMetrics.css'

interface BackendMetricsOperation {
  operation: string
  count: number
  successCount: number
  failureCount: number
  successRate: number
  avgDurationMs: number
  minDurationMs: number
  maxDurationMs: number
  lastSeenAt: number
}

interface BackendMetricsSummary {
  total: number
  successful: number
  failed: number
  successRate: number
  operations: BackendMetricsOperation[]
}

interface PreviewFunnelStep {
  key: string
  label: string
  description: string
  tone: 'default' | 'success' | 'warning' | 'error'
  count: number
}

interface ApiMetricsEndpoint {
  endpoint: string
  count: number
  errorCount: number
  errorRate: number
  avgDurationMs: number
  minDurationMs: number
  maxDurationMs: number
  lastSeenMs: number
}

interface ApiMetricsRecentError {
  method: string
  path: string
  statusCode: number
  durationMs: number
  timestampMs: number
  errorDetail: string | null
}

interface ApiMetricsPoint {
  bucketStartMs: number
  requestCount: number
  errorCount: number
  avgDurationMs: number
}

interface ApiMetricsSummary {
  total: number
  errors: number
  errorRate: number
  avgDurationMs: number
  p95DurationMs: number
  retentionDays: number
  logLevel: string
  trendWindowMinutes: number
  requestSeries: ApiMetricsPoint[]
  endpoints: ApiMetricsEndpoint[]
  recentErrors: ApiMetricsRecentError[]
}

interface AuthLoginRoleCount {
  role: string
  label: string
  count: number
}

interface AuthLoginTrendBucket {
  bucketStartMs: number
  roleCounts: Record<string, number>
}

interface AuthLoginMetricsSummary {
  total: number
  retentionDays: number
  trendWindowHours: number
  bucketMinutes: number
  roleCounts: AuthLoginRoleCount[]
  trendSeries: AuthLoginTrendBucket[]
}

const PREVIEW_OPERATION_METADATA: Record<string, {
  label: string
  category: 'Discovery' | 'Selection' | 'Drafting' | 'Outcome' | 'Error'
}> = {
  'suggestions.natural_language.preview_clicked': {
    label: 'Preview clicked',
    category: 'Discovery',
  },
  'suggestions.natural_language.attributes_selected': {
    label: 'Attributes selected',
    category: 'Selection',
  },
  'suggestions.natural_language.draft_created': {
    label: 'Draft suggestion created',
    category: 'Drafting',
  },
  'suggestions.natural_language.suggestion_accepted': {
    label: 'Suggestion accepted',
    category: 'Outcome',
  },
  'suggestions.natural_language.suggestion_rejected': {
    label: 'Suggestion rejected',
    category: 'Outcome',
  },
  'suggestions.natural_language.suggestion_applied': {
    label: 'Suggestion applied to create rule',
    category: 'Outcome',
  },
  'suggestions.natural_language.preview_cancelled': {
    label: 'Preview cancelled',
    category: 'Outcome',
  },
  'suggestions.natural_language.preview_error': {
    label: 'Preview error',
    category: 'Error',
  },
}

const PREVIEW_FUNNEL_ORDER: Array<Omit<PreviewFunnelStep, 'count'>> = [
  {
    key: 'suggestions.natural_language.preview_clicked',
    label: 'Preview Clicked',
    description: 'How often the steward asked for a draft preview.',
    tone: 'default',
  },
  {
    key: 'suggestions.natural_language.attributes_selected',
    label: 'Attributes Selected',
    description: 'A steward picked one or more candidate attributes.',
    tone: 'default',
  },
  {
    key: 'suggestions.natural_language.draft_created',
    label: 'Draft Created',
    description: 'The preview produced a persisted suggestion draft.',
    tone: 'success',
  },
  {
    key: 'suggestions.natural_language.suggestion_accepted',
    label: 'Accepted',
    description: 'The resulting suggestion was accepted.',
    tone: 'success',
  },
  {
    key: 'suggestions.natural_language.suggestion_rejected',
    label: 'Rejected',
    description: 'The resulting suggestion was rejected.',
    tone: 'warning',
  },
  {
    key: 'suggestions.natural_language.preview_cancelled',
    label: 'Cancelled',
    description: 'The steward reset or abandoned the preview flow.',
    tone: 'warning',
  },
  {
    key: 'suggestions.natural_language.preview_error',
    label: 'Errors',
    description: 'Preview requests that failed validation or support checks.',
    tone: 'error',
  },
]

const formatBackendOperationLabel = (operation: string) => {
  const previewMetadata = PREVIEW_OPERATION_METADATA[operation]
  if (previewMetadata) {
    return previewMetadata.label
  }

  const normalized = String(operation || '').trim()
  if (!normalized) {
    return 'Unknown operation'
  }

  return normalized
    .split('.')
    .map(segment => segment.replace(/_/g, ' '))
    .map(segment => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' / ')
}

export const SystemMetrics: React.FC = () => {
  const settings = useSettings()
  const auth = useAuth()
  const {
    aggregated,
    cacheStats,
    getSlowOperations,
    getFailedOperations,
    getOverallStats,
    clearMetrics,
  } = usePerformanceMonitoringContext()

  // Section refs for navigation
  const overallStatsRef = useRef<HTMLDivElement>(null)
  const suggestionsRef = useRef<HTMLDivElement>(null)
  const authMetricsRef = useRef<HTMLDivElement>(null)
  const apiMetricsRef = useRef<HTMLDivElement>(null)
  const operationPerfRef = useRef<HTMLDivElement>(null)
  const cacheRef = useRef<HTMLDivElement>(null)
  const slowOpsRef = useRef<HTMLDivElement>(null)
  const failedOpsRef = useRef<HTMLDivElement>(null)
  const anchorNavRef = useRef<HTMLDivElement>(null)

  // Filter states
  const [operationFilter, setOperationFilter] = useState('')
  const [cacheFilter, setCacheFilter] = useState('')
  const [slowOpFilter, setSlowOpFilter] = useState('')
  const [slowOpThreshold, setSlowOpThreshold] = useState(1000)
  const [failedOpFilter, setFailedOpFilter] = useState('')
  const [apiEndpointFilter, setApiEndpointFilter] = useState('')
  const [apiMethodFilter, setApiMethodFilter] = useState('all')
  const [apiSortBy, setApiSortBy] = useState<'requests' | 'errors' | 'latency'>('requests')
  const [apiMinRequests, setApiMinRequests] = useState(0)
  const [recentErrorStatusFilter, setRecentErrorStatusFilter] = useState<'all' | '4xx' | '5xx'>('all')
  const [recentErrorPathFilter, setRecentErrorPathFilter] = useState('')

  const [showAdminApiDetails, setShowAdminApiDetails] = useState(false)
  const [isRefreshingApiMetrics, setIsRefreshingApiMetrics] = useState(false)
  const [lastApiMetricsRefreshAt, setLastApiMetricsRefreshAt] = useState<number | null>(null)
  const [lastAuthMetricsRefreshAt, setLastAuthMetricsRefreshAt] = useState<number | null>(null)
  const [backendMetrics, setBackendMetrics] = useState<BackendMetricsSummary | null>(null)
  const [backendMetricsError, setBackendMetricsError] = useState<string | null>(null)
  const [authLoginMetrics, setAuthLoginMetrics] = useState<AuthLoginMetricsSummary | null>(null)
  const [authLoginMetricsError, setAuthLoginMetricsError] = useState<string | null>(null)
  const [apiMetrics, setApiMetrics] = useState<ApiMetricsSummary | null>(null)
  const [apiMetricsError, setApiMetricsError] = useState<string | null>(null)
  const [activeSection, setActiveSection] = useState('overall')
  const isAdmin = auth.getCurrentUserRole() === 'admin'

  const apiBaseUrl = useMemo(() => {
    return toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)
  }, [settings.applicationSettings?.apiBaseUrl])

  const parseApiMetricsSummary = (data: any): ApiMetricsSummary => ({
    total: Number(data.total || 0),
    errors: Number(data.errors || 0),
    errorRate: Number(data.errorRate || 0),
    avgDurationMs: Number(data.avgDurationMs || 0),
    p95DurationMs: Number(data.p95DurationMs || 0),
    retentionDays: Number(data.retentionDays || 90),
    logLevel: String(data.logLevel || 'info'),
    trendWindowMinutes: Number(data.trendWindowMinutes || 60),
    requestSeries: Array.isArray(data.requestSeries) ? data.requestSeries : [],
    endpoints: Array.isArray(data.endpoints) ? data.endpoints : [],
    recentErrors: Array.isArray(data.recentErrors) ? data.recentErrors : [],
  })

  const parseAuthLoginMetricsSummary = (data: any): AuthLoginMetricsSummary => {
    const normalizeRoleCounts = (roleCounts: any): Record<string, number> => {
      if (!roleCounts || typeof roleCounts !== 'object') {
        return {}
      }

      return Object.entries(roleCounts).reduce<Record<string, number>>((accumulator, [key, value]) => {
        accumulator[key] = Number(value || 0)
        return accumulator
      }, {})
    }

    return {
      total: Number(data.total || 0),
      retentionDays: Number(data.retention_days || 90),
      trendWindowHours: Number(data.trend_window_hours || 24),
      bucketMinutes: Number(data.bucket_minutes || 60),
      roleCounts: Array.isArray(data.role_counts)
        ? data.role_counts.map((entry: any) => ({
            role: String(entry.role || 'other'),
            label: String(entry.label || entry.role || 'Other'),
            count: Number(entry.count || 0),
          }))
        : [],
      trendSeries: Array.isArray(data.trend_series)
        ? data.trend_series.map((entry: any) => ({
            bucketStartMs: Number(entry.bucket_start_ms || 0),
            roleCounts: normalizeRoleCounts(entry.role_counts),
          }))
        : [],
    }
  }

  const refreshApiMetrics = useCallback(async (showSpinner = false): Promise<void> => {
    if (showSpinner) {
      setIsRefreshingApiMetrics(true)
    }

    try {
      const token = getAuthToken()
      const params = new URLSearchParams()
      if (apiEndpointFilter.trim()) {
        params.set('apiEndpointFilter', apiEndpointFilter.trim())
      }
      if (apiMethodFilter !== 'all') {
        params.set('apiMethodFilter', apiMethodFilter)
      }
      if (apiMinRequests > 0) {
        params.set('apiMinRequests', String(apiMinRequests))
      }
      if (recentErrorStatusFilter !== 'all') {
        params.set('recentErrorStatusFilter', recentErrorStatusFilter)
      }
      if (recentErrorPathFilter.trim()) {
        params.set('recentErrorPathFilter', recentErrorPathFilter.trim())
      }
      params.set('excludeHealthEndpoints', 'true')

      const query = params.toString()
      const response = await fetch(`${apiBaseUrl}/api-metrics${query ? `?${query}` : ''}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const data = await response.json()
      if (!response.ok || data?.success === false) {
        throw new Error(data?.error || 'Failed to load API metrics')
      }

      setApiMetrics(parseApiMetricsSummary(data))
      setApiMetricsError(null)
      setLastApiMetricsRefreshAt(Date.now())
    } catch (error) {
      setApiMetricsError(error instanceof Error ? error.message : 'Failed to load API metrics')
    } finally {
      if (showSpinner) {
        setIsRefreshingApiMetrics(false)
      }
    }
  }, [
    apiBaseUrl,
    apiEndpointFilter,
    apiMethodFilter,
    apiMinRequests,
    recentErrorStatusFilter,
    recentErrorPathFilter,
  ])

  const refreshAuthLoginMetrics = useCallback(async (): Promise<void> => {
    try {
      const token = getAuthToken()
      const response = await fetch(`${apiBaseUrl}/auth-login-metrics`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const data = await response.json()
      if (!response.ok || data?.success === false) {
        throw new Error(data?.error || 'Failed to load auth login metrics')
      }

      setAuthLoginMetrics(parseAuthLoginMetricsSummary(data))
      setAuthLoginMetricsError(null)
      setLastAuthMetricsRefreshAt(Date.now())
    } catch (error) {
      setAuthLoginMetricsError(error instanceof Error ? error.message : 'Failed to load auth login metrics')
    }
  }, [apiBaseUrl])

  useEffect(() => {
    let cancelled = false

    const loadBackendMetrics = async () => {
      try {
        const token = getAuthToken()
        const response = await fetch(`${apiBaseUrl}/suggestions/metrics`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        const data = await response.json()
        if (!response.ok || data?.success === false) {
          throw new Error(data?.error || 'Failed to load backend metrics')
        }

        if (!cancelled) {
          setBackendMetrics({
            total: Number(data.total || 0),
            successful: Number(data.successful || 0),
            failed: Number(data.failed || 0),
            successRate: Number(data.successRate || 0),
            operations: Array.isArray(data.operations) ? data.operations : [],
          })
          setBackendMetricsError(null)
        }
      } catch (error) {
        if (!cancelled) {
          setBackendMetricsError(error instanceof Error ? error.message : 'Failed to load backend metrics')
        }
      }
    }

    loadBackendMetrics()
    const timer = window.setInterval(loadBackendMetrics, 15000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [apiBaseUrl])

  useEffect(() => {
    let cancelled = false

    const loadAuthLoginMetrics = async () => {
      if (cancelled) {
        return
      }

      await refreshAuthLoginMetrics()
    }

    loadAuthLoginMetrics()
    const timer = window.setInterval(loadAuthLoginMetrics, 30000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [refreshAuthLoginMetrics])

  useEffect(() => {
    let cancelled = false

    const loadApiMetrics = async () => {
      if (cancelled) {
        return
      }

      await refreshApiMetrics(false)
    }

    loadApiMetrics()
    const timer = window.setInterval(loadApiMetrics, 15000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [refreshApiMetrics])

  const slowOps = getSlowOperations()
  const failedOps = getFailedOperations()

  const scrollToSection = (ref: React.RefObject<HTMLDivElement | null>) => {
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const handleSectionLinkClick = (
    e: React.MouseEvent<HTMLElement>,
    sectionId: string,
    ref: React.RefObject<HTMLDivElement | null>
  ) => {
    e.preventDefault()
    setActiveSection(sectionId)
    scrollToSection(ref)
  }

  const handleSectionTabChange = (sectionId: string) => {
    const sectionRefs: Record<string, React.RefObject<HTMLDivElement | null>> = {
      overall: overallStatsRef,
      suggestions: suggestionsRef,
      'auth-login-metrics': authMetricsRef,
      'api-metrics': apiMetricsRef,
      operations: operationPerfRef,
      cache: cacheRef,
      slow: slowOpsRef,
      failed: failedOpsRef,
    }

    const targetRef = sectionRefs[sectionId]
    if (targetRef) {
      setActiveSection(sectionId)
      scrollToSection(targetRef)
    }
  }

  // Track which section is visible
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const id = entry.target.id
            setActiveSection(id)
          }
        })
      },
      { threshold: 0.5 }
    )

    if (overallStatsRef.current) observer.observe(overallStatsRef.current)
    if (suggestionsRef.current) observer.observe(suggestionsRef.current)
    if (authMetricsRef.current) observer.observe(authMetricsRef.current)
    if (apiMetricsRef.current) observer.observe(apiMetricsRef.current)
    if (operationPerfRef.current) observer.observe(operationPerfRef.current)
    if (cacheRef.current) observer.observe(cacheRef.current)
    if (slowOpsRef.current) observer.observe(slowOpsRef.current)
    if (failedOpsRef.current) observer.observe(failedOpsRef.current)

    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!window.matchMedia('(max-width: 768px)').matches) {
      return
    }

    const activeOption = anchorNavRef.current?.querySelector<HTMLElement>(
      `.metrics-anchor-option[data-section="${activeSection}"]`
    )

    activeOption?.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
      inline: 'center',
    })
  }, [activeSection])

  const overallStats = getOverallStats()

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${Math.round(ms)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  const formatUptime = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)
    
    if (hours > 0) return `${hours}h ${minutes % 60}m`
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`
    return `${seconds}s`
  }

  const formatPercentage = (value: number) => {
    return `${(value * 100).toFixed(1)}%`
  }

  const formatTimestamp = (value: number) => {
    if (!Number.isFinite(value) || value <= 0) {
      return 'Not recorded'
    }

    return new Date(value).toLocaleString()
  }

  const sortedOperations = useMemo(() => {
    return Object.values(aggregated)
      .filter(op => op.operation.toLowerCase().includes(operationFilter.toLowerCase()))
      .sort((a, b) => b.count - a.count)
  }, [aggregated, operationFilter])

  const filteredCacheStats = useMemo(() => {
    return Object.entries(cacheStats)
      .filter(([operation]) => operation.toLowerCase().includes(cacheFilter.toLowerCase()))
  }, [cacheStats, cacheFilter])

  const filteredSlowOps = useMemo(() => {
    return slowOps
      .filter(op => op.duration >= slowOpThreshold)
      .filter(op => op.operation.toLowerCase().includes(slowOpFilter.toLowerCase()))
  }, [slowOps, slowOpThreshold, slowOpFilter])

  const filteredFailedOps = useMemo(() => {
    return failedOps
      .filter(op => op.operation.toLowerCase().includes(failedOpFilter.toLowerCase()))
  }, [failedOps, failedOpFilter])

  const filteredApiEndpoints = useMemo(() => {
    const base = apiMetrics?.endpoints ?? []

    return [...base].sort((a, b) => {
      if (apiSortBy === 'errors') {
        if (b.errorCount !== a.errorCount) return b.errorCount - a.errorCount
        return b.errorRate - a.errorRate
      }
      if (apiSortBy === 'latency') {
        return b.avgDurationMs - a.avgDurationMs
      }
      return b.count - a.count
    })
  }, [apiMetrics, apiSortBy])

  const filteredRecentApiErrors = useMemo(() => {
    return apiMetrics?.recentErrors ?? []
  }, [apiMetrics])

  const compactTopEndpoints = useMemo(() => {
    const top = filteredApiEndpoints.slice(0, 6)
    const maxRequests = top.reduce((highest, ep) => Math.max(highest, ep.count), 0)
    const maxLatency = top.reduce((highest, ep) => Math.max(highest, ep.maxDurationMs), 0)
    return top.map(ep => ({
      ...ep,
      requestWidth: maxRequests > 0 ? (ep.count / maxRequests) * 100 : 0,
      latencyWidth: maxLatency > 0 ? (ep.maxDurationMs / maxLatency) * 100 : 0,
    }))
  }, [filteredApiEndpoints])

  const lastApiMetricsRefreshLabel = useMemo(() => {
    if (!lastApiMetricsRefreshAt) return 'Waiting for first refresh'
    return new Date(lastApiMetricsRefreshAt).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }, [lastApiMetricsRefreshAt])

  const lastAuthMetricsRefreshLabel = useMemo(() => {
    if (!lastAuthMetricsRefreshAt) return 'Waiting for first refresh'
    return new Date(lastAuthMetricsRefreshAt).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }, [lastAuthMetricsRefreshAt])

  const previewOperationRows = useMemo(() => {
    return (backendMetrics?.operations ?? []).filter((operation) =>
      operation.operation.startsWith('suggestions.natural_language.')
    )
  }, [backendMetrics])

  const previewFunnelSteps = useMemo<PreviewFunnelStep[]>(() => {
    const countsByOperation = new Map(
      previewOperationRows.map((operation) => [operation.operation, operation.count])
    )

    return PREVIEW_FUNNEL_ORDER.map((step) => ({
      ...step,
      count: Number(countsByOperation.get(step.key) ?? 0),
    }))
  }, [previewOperationRows])

  const otherBackendOperationRows = useMemo(() => {
    return (backendMetrics?.operations ?? []).filter(
      (operation) => !operation.operation.startsWith('suggestions.natural_language.')
    )
  }, [backendMetrics])

  return (
    <div className="system-metrics">
      <AdminPageHeader
        title="System Performance Metrics"
        actions={
          <Button variant="tertiary" onClick={clearMetrics}>
            <AppIcon slot="start" name="trash" />
            Clear Metrics
          </Button>
        }
      />

      <div className="metrics-header-tabs" aria-label="Section navigation">
        <div className="metrics-header-tabs-scroll" ref={anchorNavRef}>
          <AppTabs
            ariaLabel="Section navigation"
            value={activeSection as any}
            onChange={handleSectionTabChange}
            className="metrics-header-tabs-control"
            tabs={[
              { value: 'overall', label: 'Overall', title: 'Go to Overall statistics' },
              { value: 'suggestions', label: 'Backend Metrics', title: 'Go to Backend metrics' },
              { value: 'auth-login-metrics', label: 'Role Logins', title: 'Go to auth login metrics' },
              { value: 'api-metrics', label: 'API Metrics', title: 'Go to API request metrics' },
              { value: 'operations', label: 'Operations', title: 'Go to Operations performance' },
              { value: 'cache', label: 'Cache', title: 'Go to Cache performance' },
              ...(slowOps.length > 0 ? [{ value: 'slow', label: 'Slow Ops', title: 'Go to Slow operations' }] : []),
              ...(failedOps.length > 0 ? [{ value: 'failed', label: 'Failed Ops', title: 'Go to Failed operations' }] : []),
            ]}
          />
        </div>
      </div>

      {/* Overall Statistics */}
      <div className="metrics-section" ref={overallStatsRef} id="overall">
        <h2>Overall Statistics</h2>
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Total Operations</div>
            <div className="stat-value">{overallStats.totalOperations}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Success Rate</div>
            <div className="stat-value success">{formatPercentage(overallStats.successRate)}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Avg Duration</div>
            <div className="stat-value">{formatDuration(overallStats.avgDuration)}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Uptime</div>
            <div className="stat-value">{formatUptime(overallStats.uptime)}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Failed Operations</div>
            <div className="stat-value error">{overallStats.failedOperations}</div>
          </div>
        </div>
      </div>

      {/* Suggestions, Preview Usage & Profiling (Backend) */}
      <div className="metrics-section" ref={suggestionsRef} id="suggestions">
        <h2>Suggestions, Preview Usage & Profiling (Backend)</h2>
        <p className="section-description">
          Includes persisted natural-language preview funnel events for the in-app analytics view. Use Grafana for time-series trend analysis.
        </p>
        {backendMetricsError && <p className="error">{backendMetricsError}</p>}

        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Total Operations</div>
            <div className="stat-value">{backendMetrics?.total ?? 0}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Success Rate</div>
            <div className="stat-value success">{formatPercentage(backendMetrics?.successRate ?? 0)}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Failed Operations</div>
            <div className="stat-value error">{backendMetrics?.failed ?? 0}</div>
          </div>
        </div>

        <div className="metrics-subsection-card metrics-preview-funnel-card">
          <h3>NL Preview Funnel</h3>
          <p className="metrics-subsection-description">
            Product-facing counts for the preview journey from click through steward outcome.
          </p>
          <div className="metrics-preview-funnel-grid">
            {previewFunnelSteps.map((step) => (
              <div key={step.key} className={`stat-card metrics-preview-step metrics-preview-step-${step.tone}`}>
                <div className="stat-label">{step.label}</div>
                <div className={`stat-value${step.tone === 'success' ? ' success' : step.tone === 'warning' ? ' warning' : step.tone === 'error' ? ' error' : ''}`}>
                  {step.count}
                </div>
                <p className="metrics-preview-step-description">{step.description}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="metrics-subsection-card">
          <h3>NL Preview Event Detail</h3>
          <div className="table-container">
            <table className="metrics-table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Category</th>
                  <th>Count</th>
                  <th>Success Rate</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {previewOperationRows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="no-data">No NL preview events recorded yet</td>
                  </tr>
                ) : (
                  previewOperationRows.map(op => (
                    <tr key={op.operation} className={op.failureCount > 0 ? 'failed-row' : ''}>
                      <td className="operation-name operation-name-friendly">{formatBackendOperationLabel(op.operation)}</td>
                      <td>{PREVIEW_OPERATION_METADATA[op.operation]?.category ?? 'Preview'}</td>
                      <td>{op.count}</td>
                      <td className={op.successRate < 0.9 ? 'error' : 'success'}>{formatPercentage(op.successRate)}</td>
                      <td>{op.lastSeenAt > 0 ? new Date(op.lastSeenAt).toLocaleTimeString() : 'n/a'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="metrics-subsection-card">
          <h3>Other Backend Suggestion Operations</h3>
          <div className="table-container">
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Operation</th>
                <th>Count</th>
                <th>Avg Duration</th>
                <th>Success Rate</th>
                <th>Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {!backendMetrics || otherBackendOperationRows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="no-data">No other backend suggestion operations recorded yet</td>
                </tr>
              ) : (
                otherBackendOperationRows.map(op => (
                  <tr key={op.operation} className={op.failureCount > 0 ? 'failed-row' : ''}>
                    <td className="operation-name operation-name-friendly">{formatBackendOperationLabel(op.operation)}</td>
                    <td>{op.count}</td>
                    <td>{formatDuration(op.avgDurationMs)}</td>
                    <td className={op.successRate < 0.9 ? 'error' : 'success'}>{formatPercentage(op.successRate)}</td>
                    <td>{op.lastSeenAt > 0 ? new Date(op.lastSeenAt).toLocaleTimeString() : 'n/a'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        </div>
      </div>

      {/* Auth Login Metrics */}
      <div className="metrics-section" ref={authMetricsRef} id="auth-login-metrics">
        <h2>Role Login Metrics</h2>
        {authLoginMetricsError && <p className="error">{authLoginMetricsError}</p>}

        {authLoginMetrics && (
          <p className="metrics-retention-note">
            Showing role logins over the last <strong>{authLoginMetrics.trendWindowHours} hours</strong> · retained for <strong>{authLoginMetrics.retentionDays} days</strong>
          </p>
        )}

        <div className="metrics-toolbar-inline">
          <div className="metrics-toolbar-status">
            <span className="metrics-live-indicator" aria-hidden="true">
              <span className="metrics-live-indicator-dot"></span>
            </span>
            <span className="metrics-toolbar-meta">Live · Last updated: <strong>{lastAuthMetricsRefreshLabel}</strong></span>
          </div>
        </div>

        <div className="metrics-role-badges">
          {(authLoginMetrics?.roleCounts ?? [])
            .filter(roleCount => ['admin', 'auditor', 'regulator'].includes(roleCount.role))
            .map(roleCount => (
              <div key={roleCount.role} className={`metrics-role-badge metrics-role-badge-${roleCount.role}`}>
                <span className="metrics-role-badge-label">{roleCount.label}</span>
                <strong className="metrics-role-badge-value">{roleCount.count}</strong>
                <span className="metrics-role-badge-caption">successful logins</span>
              </div>
            ))}
        </div>

        <div className="table-container">
          <table className="metrics-table metrics-table-role-logins">
            <thead>
              <tr>
                <th>Time</th>
                <th>Admin</th>
                <th>Auditor</th>
                <th>Regulator</th>
              </tr>
            </thead>
            <tbody>
              {(authLoginMetrics?.trendSeries ?? []).length === 0 ? (
                <tr>
                  <td colSpan={4} className="no-data">
                    No role login activity recorded yet
                  </td>
                </tr>
              ) : (
                (authLoginMetrics?.trendSeries ?? []).map(bucket => (
                  <tr key={bucket.bucketStartMs}>
                    <td className="operation-name-friendly">{new Date(bucket.bucketStartMs).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
                    <td>{bucket.roleCounts.admin ?? 0}</td>
                    <td>{bucket.roleCounts.auditor ?? 0}</td>
                    <td>{bucket.roleCounts.regulator ?? 0}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* API Request Metrics */}
      <div className="metrics-section" ref={apiMetricsRef} id="api-metrics">
        <h2>API Request Metrics</h2>
        {apiMetricsError && <p className="error">{apiMetricsError}</p>}

        {apiMetrics && (
          <p className="metrics-retention-note">
            Showing data from the last <strong>{apiMetrics.retentionDays} days</strong> · log level: <strong>{apiMetrics.logLevel}</strong>
          </p>
        )}

        <div className="metrics-toolbar-inline">
          <div className="metrics-toolbar-status">
            <span className={`metrics-live-indicator ${isRefreshingApiMetrics ? 'is-refreshing' : ''}`} aria-hidden="true">
              <span className="metrics-live-indicator-dot"></span>
            </span>
            <span className="metrics-toolbar-meta">Live · Last updated: <strong>{lastApiMetricsRefreshLabel}</strong></span>
          </div>
          <Button variant="secondary" onClick={() => refreshApiMetrics(true)} disabled={isRefreshingApiMetrics ? 'true' : 'false'}>
            <AppIcon slot="start" name="arrow-circle-repeat" />
            {isRefreshingApiMetrics ? 'Refreshing...' : 'Refresh Now'}
          </Button>
        </div>

        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Total Requests</div>
            <div className="stat-value">{apiMetrics?.total ?? 0}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Errors</div>
            <div className={`stat-value ${(apiMetrics?.errors ?? 0) > 0 ? 'error' : ''}`}>{apiMetrics?.errors ?? 0}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Error Rate</div>
            <div className={`stat-value ${(apiMetrics?.errorRate ?? 0) > 0.05 ? 'error' : 'success'}`}>
              {formatPercentage(apiMetrics?.errorRate ?? 0)}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Avg Duration</div>
            <div className="stat-value">{formatDuration(apiMetrics?.avgDurationMs ?? 0)}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">p95 Duration</div>
            <div className="stat-value">{formatDuration(apiMetrics?.p95DurationMs ?? 0)}</div>
          </div>
        </div>

        <div className="section-header" style={{ marginTop: '16px' }}>
          <h3>Top Endpoints</h3>
          {isAdmin && (
            <Button variant="tertiary" onClick={() => setShowAdminApiDetails(value => !value)}>
              <AppIcon slot="start" name={showAdminApiDetails ? 'minus' : 'plus'} />
              {showAdminApiDetails ? 'Hide Details' : 'Show All Details'}
            </Button>
          )}
        </div>
        <div className="table-container">
          <table className="metrics-table metrics-table-compact-endpoints">
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Load</th>
                <th>Reliability</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody>
              {compactTopEndpoints.length === 0 ? (
                <tr>
                  <td colSpan={4} className="no-data">
                    {apiEndpointFilter ? 'No endpoints match filter' : 'No API requests recorded yet'}
                  </td>
                </tr>
              ) : (
                compactTopEndpoints.map(ep => (
                  <tr key={ep.endpoint}>
                    <td className="operation-name">{ep.endpoint}</td>
                    <td>
                      <div className="inline-metric-cell">
                        <div className="inline-meter">
                          <div className="inline-meter-fill inline-meter-fill-primary" style={{ width: `${ep.requestWidth}%` }} />
                        </div>
                        <span className="inline-metric-text">{ep.count} req</span>
                      </div>
                    </td>
                    <td>
                      <span className={`inline-status-pill ${ep.errorRate > 0.05 ? 'is-error' : ep.errorRate > 0.01 ? 'is-warning' : 'is-good'}`}>
                        {formatPercentage(ep.errorRate)}
                      </span>
                    </td>
                    <td>
                      <div className="inline-metric-cell">
                        <div className="inline-meter">
                          <div className="inline-meter-fill inline-meter-fill-warning" style={{ width: `${ep.latencyWidth}%` }} />
                        </div>
                        <span className="inline-metric-text">{formatDuration(ep.avgDurationMs)} avg</span>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {isAdmin && showAdminApiDetails && (
          <>
            <div className="section-header" style={{ marginTop: '16px' }}>
              <h3>Per Endpoint Details</h3>
              <div className="filter-controls">
                <input
                  type="text"
                  className="filter-input"
                  placeholder="Filter endpoints..."
                  value={apiEndpointFilter}
                  onChange={(e) => setApiEndpointFilter(e.target.value)}
                />
                <select
                  className="filter-input filter-select"
                  value={apiMethodFilter}
                  onChange={(e) => setApiMethodFilter(e.target.value)}
                >
                  <option value="all">All methods</option>
                  <option value="GET">GET</option>
                  <option value="POST">POST</option>
                  <option value="PUT">PUT</option>
                  <option value="PATCH">PATCH</option>
                  <option value="DELETE">DELETE</option>
                </select>
                <select
                  className="filter-input filter-select"
                  value={apiSortBy}
                  onChange={(e) => setApiSortBy(e.target.value as 'requests' | 'errors' | 'latency')}
                >
                  <option value="requests">Sort: Most requests</option>
                  <option value="errors">Sort: Most errors</option>
                  <option value="latency">Sort: Highest latency</option>
                </select>
                <div className="threshold-control">
                  <label htmlFor="apiMinRequests">Min requests:</label>
                  <input
                    id="apiMinRequests"
                    type="number"
                    className="threshold-input"
                    min="0"
                    step="1"
                    value={apiMinRequests}
                    onChange={(e) => setApiMinRequests(Number(e.target.value) || 0)}
                  />
                </div>
                {apiEndpointFilter && (
                  <Button
                    variant="tertiary"
                    onClick={() => setApiEndpointFilter('')}
                    title="Clear filter"
                  >
                    <AppIcon name="times" />
                  </Button>
                )}
              </div>
            </div>
            <div className="table-container">
              <table className="metrics-table">
                <thead>
                  <tr>
                    <th>Endpoint</th>
                    <th>Requests</th>
                    <th>Errors</th>
                    <th>Error Rate</th>
                    <th>Avg</th>
                    <th>Max</th>
                    <th>Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredApiEndpoints.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="no-data">
                        {apiEndpointFilter ? 'No endpoints match filter' : 'No API requests recorded yet'}
                      </td>
                    </tr>
                  ) : (
                    filteredApiEndpoints.map(ep => (
                      <tr key={`details-${ep.endpoint}`}>
                        <td className="operation-name">{ep.endpoint}</td>
                        <td>{ep.count}</td>
                        <td className={ep.errorCount > 0 ? 'error' : ''}>{ep.errorCount}</td>
                        <td className={ep.errorRate > 0.05 ? 'error' : 'success'}>{formatPercentage(ep.errorRate)}</td>
                        <td>{formatDuration(ep.avgDurationMs)}</td>
                        <td>{formatDuration(ep.maxDurationMs)}</td>
                        <td>{new Date(ep.lastSeenMs).toLocaleTimeString()}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Recent errors */}
        {(apiMetrics?.recentErrors?.length ?? 0) > 0 && isAdmin && showAdminApiDetails && (
          <>
            <div className="section-header" style={{ marginTop: '20px' }}>
              <h3>Recent Errors</h3>
              <div className="filter-controls">
                <select
                  className="filter-input filter-select"
                  value={recentErrorStatusFilter}
                  onChange={(e) => setRecentErrorStatusFilter(e.target.value as 'all' | '4xx' | '5xx')}
                >
                  <option value="all">All statuses</option>
                  <option value="4xx">Only 4xx</option>
                  <option value="5xx">Only 5xx</option>
                </select>
                <input
                  type="text"
                  className="filter-input"
                  placeholder="Filter method/path..."
                  value={recentErrorPathFilter}
                  onChange={(e) => setRecentErrorPathFilter(e.target.value)}
                />
              </div>
            </div>
            <div className="table-container">
              <table className="metrics-table">
                <thead>
                  <tr>
                    <th>Method</th>
                    <th>Path</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRecentApiErrors.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="no-data">No recent errors match filter</td>
                    </tr>
                  ) : (
                    filteredRecentApiErrors.map((err, idx) => (
                      <tr key={idx} className="failed-row">
                        <td><span className="method-badge">{err.method}</span></td>
                        <td className="operation-name">{err.path}</td>
                        <td className="error">{err.statusCode}</td>
                        <td>{formatDuration(err.durationMs)}</td>
                        <td>{new Date(err.timestampMs).toLocaleTimeString()}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {/* Operation Statistics */}
      <div className="metrics-section" ref={operationPerfRef} id="operations">
        <div className="section-header">
          <h2>Operation Performance</h2>
          <div className="filter-controls">
            <input
              type="text"
              className="filter-input"
              placeholder="Filter operations..."
              value={operationFilter}
              onChange={(e) => setOperationFilter(e.target.value)}
            />
            {operationFilter && (
              <Button
                variant="tertiary"
                onClick={() => setOperationFilter('')}
                title="Clear filter"
              >
                <AppIcon name="times" />
              </Button>
            )}
          </div>
        </div>
        <div className="table-container">
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Operation</th>
                <th>Count</th>
                <th>Avg Duration</th>
                <th>Min</th>
                <th>Max</th>
                <th>Success Rate</th>
              </tr>
            </thead>
            <tbody>
              {sortedOperations.length === 0 ? (
                <tr>
                  <td colSpan={6} className="no-data">
                    {operationFilter ? 'No operations match filter' : 'No operations recorded yet'}
                  </td>
                </tr>
              ) : (
                sortedOperations.map(op => (
                  <tr key={op.operation}>
                    <td className="operation-name">{op.operation}</td>
                    <td>{op.count}</td>
                    <td>{formatDuration(op.avgDuration)}</td>
                    <td className="duration-min">{formatDuration(op.minDuration)}</td>
                    <td className="duration-max">{formatDuration(op.maxDuration)}</td>
                    <td className={op.successRate < 0.9 ? 'error' : 'success'}>
                      {formatPercentage(op.successRate)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cache Statistics */}
      <div className="metrics-section" ref={cacheRef} id="cache">
        <div className="section-header">
          <h2>Cache Performance</h2>
          <div className="filter-controls">
            <input
              type="text"
              className="filter-input"
              placeholder="Filter cache types..."
              value={cacheFilter}
              onChange={(e) => setCacheFilter(e.target.value)}
            />
            {cacheFilter && (
              <Button
                variant="tertiary"
                onClick={() => setCacheFilter('')}
                title="Clear filter"
              >
                <AppIcon name="times" />
              </Button>
            )}
          </div>
        </div>
        <div className="table-container">
          <table className="metrics-table">
            <thead>
              <tr>
                <th>Cache Type</th>
                <th>Hits</th>
                <th>Misses</th>
                <th>Hit Rate</th>
              </tr>
            </thead>
            <tbody>
              {filteredCacheStats.length === 0 ? (
                <tr>
                  <td colSpan={4} className="no-data">
                    {cacheFilter ? 'No cache types match filter' : 'No cache activity yet'}
                  </td>
                </tr>
              ) : (
                filteredCacheStats.map(([operation, stats]) => (
                  <tr key={operation}>
                    <td className="operation-name">{operation}</td>
                    <td className="cache-hits">{stats.hits}</td>
                    <td className="cache-misses">{stats.misses}</td>
                    <td className={stats.hitRate > 0.7 ? 'success' : stats.hitRate > 0.4 ? 'warning' : 'error'}>
                      {formatPercentage(stats.hitRate)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Slow Operations */}
      {slowOps.length > 0 && (
        <div className="metrics-section" ref={slowOpsRef} id="slow">
          <div className="section-header">
            <h2>Slow Operations</h2>
            <div className="filter-controls">
              <div className="threshold-control">
                <label htmlFor="slowOpThreshold">Min duration:</label>
                <input
                  id="slowOpThreshold"
                  type="number"
                  className="threshold-input"
                  min="100"
                  step="100"
                  value={slowOpThreshold}
                  onChange={(e) => setSlowOpThreshold(Number(e.target.value))}
                />
                <span className="threshold-label">ms</span>
              </div>
              <input
                type="text"
                className="filter-input"
                placeholder="Filter operations..."
                value={slowOpFilter}
                onChange={(e) => setSlowOpFilter(e.target.value)}
              />
              {slowOpFilter && (
                <Button
                  variant="tertiary"
                  onClick={() => setSlowOpFilter('')}
                  title="Clear filter"
                >
                  <AppIcon name="times" />
                </Button>
              )}
            </div>
          </div>
          <div className="table-container">
            <table className="metrics-table">
              <thead>
                <tr>
                  <th>Operation</th>
                  <th>Duration</th>
                  <th>Time</th>
                  <th>Metadata</th>
                </tr>
              </thead>
              <tbody>
                {filteredSlowOps.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="no-data">No slow operations match filters</td>
                  </tr>
                ) : (
                  filteredSlowOps.map((op, idx) => (
                    <tr key={idx}>
                      <td className="operation-name">{op.operation}</td>
                      <td className="duration-slow">{formatDuration(op.duration)}</td>
                      <td>{new Date(op.endTime).toLocaleTimeString()}</td>
                      <td className="metadata">{op.metadata ? JSON.stringify(op.metadata) : '-'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Failed Operations */}
      {failedOps.length > 0 && (
        <div className="metrics-section" ref={failedOpsRef} id="failed">
          <div className="section-header">
            <h2>Failed Operations</h2>
            <div className="filter-controls">
              <input
                type="text"
                className="filter-input"
                placeholder="Filter operations..."
                value={failedOpFilter}
                onChange={(e) => setFailedOpFilter(e.target.value)}
              />
              {failedOpFilter && (
                <Button
                  variant="tertiary"
                  onClick={() => setFailedOpFilter('')}
                  title="Clear filter"
                >
                  <AppIcon name="times" />
                </Button>
              )}
            </div>
          </div>
          <div className="table-container">
            <table className="metrics-table">
              <thead>
                <tr>
                  <th>Operation</th>
                  <th>Duration</th>
                  <th>Time</th>
                  <th>Metadata</th>
                </tr>
              </thead>
              <tbody>
                {filteredFailedOps.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="no-data">No failed operations match filter</td>
                  </tr>
                ) : (
                  filteredFailedOps.map((op, idx) => (
                    <tr key={idx} className="failed-row">
                      <td className="operation-name">{op.operation}</td>
                      <td>{formatDuration(op.duration)}</td>
                      <td>{new Date(op.endTime).toLocaleTimeString()}</td>
                      <td className="metadata">{op.metadata ? JSON.stringify(op.metadata) : '-'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="metrics-info">
        <p>
          <AppIcon name="info-circle" />
          Metrics track the last 1000 operations. Clear metrics to reset and start fresh.
        </p>
      </div>
    </div>
  )
}
