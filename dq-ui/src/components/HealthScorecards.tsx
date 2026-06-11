import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { snakeToCamel } from '../utils/caseConverters'
import { Button } from './Button'
import { AppBadge, AppBanner, AppButton, AppCard, AppCardContent, AppInput, AppTabs } from './app-primitives'
import './HealthScorecards.css'

interface HealthScorecardTopRule {
  rule_id?: string
  rule_name?: string
  dimension?: string | null
  total: number
}

interface HealthScorecardTopReason {
  reason_code?: string
  reason_text?: string
  total: number
}

interface QualityHistoryScope {
  rule_id?: string | null
  dataset_id?: string | null
  domain_id?: string | null
  data_product_id?: string | null
}

interface QualityHistoryDetection {
  detector_type: string
  severity: string
  scope: QualityHistoryScope
  observed_at: string
  baseline_value?: number | string | null
  current_value?: number | string | null
  delta?: number | string | null
  threshold?: number | string | null
  message: string
  evidence: Record<string, unknown>
}

interface QualityHistorySummary {
  lookback_amount: number
  lookback_unit: string
  total_events: number
  scoped_groups: number
  total_detections: number
  detections_by_type: Record<string, number>
  detections_by_severity: Record<string, number>
  latest_observed_at?: string | null
  drifts: QualityHistoryDetection[]
}
interface HealthScorecardTrendBucket {
  bucket_start: string
  total: number
}

interface HealthScorecardReasonTrendBucket {
  bucket_start: string
  reason_code: string
  reason_text: string
  total: number
}

interface HealthScorecardDimensionRollup {
  dimension: string
  rule_count: number
  failed_record_total: number
  failed_run_count: number
  score: number
  status_label: string
}

interface HealthScorecardOwnershipRollup {
  scope_kind: string
  scope_id: string
  scope_name: string
  asset_count: number
  tracked_data_object_version_count: number
  total_runs: number
  pending_runs: number
  running_runs: number
  succeeded_runs: number
  failed_runs: number
  cancelled_runs: number
  total_failed_records: number
  runs_with_failures: number
  overall_score: number
  health_label: string
  summary: string
}

interface HealthScorecardRegression {
  bucket_start: string
  previous_bucket_start: string
  previous_total: number
  current_total: number
  delta: number
}

interface HealthScorecardIncident {
  incident_id: string
  title: string
  status: string
  severity?: string | null
  incident_kind: string
  assigned_to?: string | null
  run_id?: string | null
  run_plan_id?: string | null
}

interface HealthScorecardWorkspaceSummary {
  workspace_id: string
  generated_at: string
  overall_score: number
  health_label: string
  summary: string
  top_regressions: HealthScorecardRegression[]
  top_rules: HealthScorecardTopRule[]
  ownership_rollups: HealthScorecardOwnershipRollup[]
  active_incident_count: number
  active_incidents: HealthScorecardIncident[]
}

interface HealthScorecard {
  scope_type: 'workspace' | 'data_asset' | string
  scope_id: string
  scope_name: string
  workspace_id: string
  data_asset_id?: string | null
  data_asset_name?: string | null
  data_asset_version_id?: string | null
  tracked_data_object_version_ids: string[]
  lookback_amount: number
  lookback_unit: string
  generated_at: string
  overall_score: number
  health_label: string
  summary: string
  total_runs: number
  pending_runs: number
  running_runs: number
  succeeded_runs: number
  failed_runs: number
  cancelled_runs: number
  total_failed_records: number
  runs_with_failures: number
  dimension_rollups: HealthScorecardDimensionRollup[]
  top_rules: HealthScorecardTopRule[]
  top_reasons: HealthScorecardTopReason[]
  trend_buckets: HealthScorecardTrendBucket[]
  reason_trend_buckets: HealthScorecardReasonTrendBucket[]
}

interface HealthScorecardPage {
  workspace_id: string
  data_asset_id?: string | null
  lookback_amount: number
  lookback_unit: string
  generated_at: string
  workspace_summary?: HealthScorecardWorkspaceSummary | null
  scorecards: HealthScorecard[]
}

interface ServiceLevelAdherence {
  currentValue?: number | string | null
  thresholdValue?: number | string | null
  thresholdOperator?: string | null
  complianceRatePct?: number | string | null
  meetsTarget?: boolean | null
  summary?: string | null
}

interface ServiceLevelDefinition {
  id: string
  name: string
  scopeKind: string
  scopeId: string
  metricKind: string
  thresholdValue: number | string
  thresholdOperator: string
  lifecycleStatus: string
  approvalStatus: string
  adherence?: ServiceLevelAdherence | null
}

interface ServiceLevelSummary {
  workspaceId: string | null
  totalDefinitions: number
  activeDefinitions: number
  draftDefinitions: number
  approvedDefinitions: number
  deprecatedDefinitions: number
  compliantDefinitions: number
  atRiskDefinitions: number
  definitions: ServiceLevelDefinition[]
}

interface HealthScorecardsProps {
  workspaceId: string | null
  dataAssetId?: string | null
  apiBaseUrl?: string | null
  onRuleSelect?: (ruleId: string) => void
  onNavigate?: (destination: string) => void
}

const parseNumber = (value: unknown): number => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

const parseScorecard = (entry: any): HealthScorecard => ({
  scope_type: String(entry.scope_type || entry.scopeType || 'workspace'),
  scope_id: String(entry.scope_id || entry.scopeId || ''),
  scope_name: String(entry.scope_name || entry.scopeName || ''),
  workspace_id: String(entry.workspace_id || entry.workspaceId || ''),
  data_asset_id: entry.data_asset_id ?? entry.dataAssetId ?? null,
  data_asset_name: entry.data_asset_name ?? entry.dataAssetName ?? null,
  data_asset_version_id: entry.data_asset_version_id ?? entry.dataAssetVersionId ?? null,
  tracked_data_object_version_ids: Array.isArray(entry.tracked_data_object_version_ids || entry.trackedDataObjectVersionIds)
    ? [...(entry.tracked_data_object_version_ids || entry.trackedDataObjectVersionIds)]
    : [],
  lookback_amount: parseNumber(entry.lookback_amount ?? entry.lookbackAmount),
  lookback_unit: String(entry.lookback_unit || entry.lookbackUnit || 'hours'),
  generated_at: String(entry.generated_at || entry.generatedAt || ''),
  overall_score: parseNumber(entry.overall_score ?? entry.overallScore),
  health_label: String(entry.health_label || entry.healthLabel || 'watch'),
  summary: String(entry.summary || ''),
  total_runs: parseNumber(entry.total_runs ?? entry.totalRuns),
  pending_runs: parseNumber(entry.pending_runs ?? entry.pendingRuns),
  running_runs: parseNumber(entry.running_runs ?? entry.runningRuns),
  succeeded_runs: parseNumber(entry.succeeded_runs ?? entry.succeededRuns),
  failed_runs: parseNumber(entry.failed_runs ?? entry.failedRuns),
  cancelled_runs: parseNumber(entry.cancelled_runs ?? entry.cancelledRuns),
  total_failed_records: parseNumber(entry.total_failed_records ?? entry.totalFailedRecords),
  runs_with_failures: parseNumber(entry.runs_with_failures ?? entry.runsWithFailures),
  dimension_rollups: Array.isArray(entry.dimension_rollups || entry.dimensionRollups)
    ? (entry.dimension_rollups || entry.dimensionRollups).map((dimension: any) => ({
        dimension: String(dimension.dimension || 'Unassigned'),
        rule_count: parseNumber(dimension.rule_count ?? dimension.ruleCount),
        failed_record_total: parseNumber(dimension.failed_record_total ?? dimension.failedRecordTotal),
        failed_run_count: parseNumber(dimension.failed_run_count ?? dimension.failedRunCount),
        score: parseNumber(dimension.score),
        status_label: String(dimension.status_label || dimension.statusLabel || 'watch'),
      }))
    : [],
  top_rules: Array.isArray(entry.top_rules || entry.topRules)
    ? (entry.top_rules || entry.topRules).map((rule: any) => ({
        rule_id: String(rule.rule_id || rule.ruleId || ''),
        rule_name: String(rule.rule_name || rule.ruleName || ''),
        dimension: rule.dimension ?? null,
        total: parseNumber(rule.total),
      }))
    : [],
  top_reasons: Array.isArray(entry.top_reasons || entry.topReasons)
    ? (entry.top_reasons || entry.topReasons).map((reason: any) => ({
        reason_code: String(reason.reason_code || reason.reasonCode || ''),
        reason_text: String(reason.reason_text || reason.reasonText || ''),
        total: parseNumber(reason.total),
      }))
    : [],
  trend_buckets: Array.isArray(entry.trend_buckets || entry.trendBuckets)
    ? (entry.trend_buckets || entry.trendBuckets).map((bucket: any) => ({
        bucket_start: String(bucket.bucket_start || bucket.bucketStart || ''),
        total: parseNumber(bucket.total),
      }))
    : [],
  reason_trend_buckets: Array.isArray(entry.reason_trend_buckets || entry.reasonTrendBuckets)
    ? (entry.reason_trend_buckets || entry.reasonTrendBuckets).map((bucket: any) => ({
        bucket_start: String(bucket.bucket_start || bucket.bucketStart || ''),
        reason_code: String(bucket.reason_code || bucket.reasonCode || ''),
        reason_text: String(bucket.reason_text || bucket.reasonText || ''),
        total: parseNumber(bucket.total),
      }))
    : [],
})

const parseScorecardPage = (data: any): HealthScorecardPage => ({
  workspace_id: String(data.workspace_id || data.workspaceId || ''),
  data_asset_id: data.data_asset_id ?? data.dataAssetId ?? null,
  lookback_amount: parseNumber(data.lookback_amount ?? data.lookbackAmount),
  lookback_unit: String(data.lookback_unit || data.lookbackUnit || 'hours'),
  generated_at: String(data.generated_at || data.generatedAt || ''),
  workspace_summary: data.workspace_summary || data.workspaceSummary
    ? {
        workspace_id: String(data.workspace_summary?.workspace_id || data.workspaceSummary?.workspaceId || data.workspaceSummary?.workspace_id || ''),
        generated_at: String(data.workspace_summary?.generated_at || data.workspaceSummary?.generatedAt || ''),
        overall_score: parseNumber(data.workspace_summary?.overall_score ?? data.workspaceSummary?.overallScore),
        health_label: String(data.workspace_summary?.health_label || data.workspaceSummary?.healthLabel || 'watch'),
        summary: String(data.workspace_summary?.summary || data.workspaceSummary?.summary || ''),
        top_regressions: Array.isArray(data.workspace_summary?.top_regressions || data.workspaceSummary?.topRegressions)
          ? (data.workspace_summary?.top_regressions || data.workspaceSummary?.topRegressions).map((regression: any) => ({
              bucket_start: String(regression.bucket_start || regression.bucketStart || ''),
              previous_bucket_start: String(regression.previous_bucket_start || regression.previousBucketStart || ''),
              previous_total: parseNumber(regression.previous_total ?? regression.previousTotal),
              current_total: parseNumber(regression.current_total ?? regression.currentTotal),
              delta: parseNumber(regression.delta),
            }))
          : [],
        top_rules: Array.isArray(data.workspace_summary?.top_rules || data.workspaceSummary?.topRules)
          ? (data.workspace_summary?.top_rules || data.workspaceSummary?.topRules).map((rule: any) => ({
              rule_id: String(rule.rule_id || rule.ruleId || ''),
              rule_name: String(rule.rule_name || rule.ruleName || ''),
              dimension: rule.dimension ?? null,
              total: parseNumber(rule.total),
            }))
          : [],
        ownership_rollups: Array.isArray(data.workspace_summary?.ownership_rollups || data.workspaceSummary?.ownershipRollups)
          ? (data.workspace_summary?.ownership_rollups || data.workspaceSummary?.ownershipRollups).map((rollup: any) => ({
              scope_kind: String(rollup.scope_kind || rollup.scopeKind || 'domain'),
              scope_id: String(rollup.scope_id || rollup.scopeId || ''),
              scope_name: String(rollup.scope_name || rollup.scopeName || ''),
              asset_count: parseNumber(rollup.asset_count ?? rollup.assetCount),
              tracked_data_object_version_count: parseNumber(rollup.tracked_data_object_version_count ?? rollup.trackedDataObjectVersionCount),
              total_runs: parseNumber(rollup.total_runs ?? rollup.totalRuns),
              pending_runs: parseNumber(rollup.pending_runs ?? rollup.pendingRuns),
              running_runs: parseNumber(rollup.running_runs ?? rollup.runningRuns),
              succeeded_runs: parseNumber(rollup.succeeded_runs ?? rollup.succeededRuns),
              failed_runs: parseNumber(rollup.failed_runs ?? rollup.failedRuns),
              cancelled_runs: parseNumber(rollup.cancelled_runs ?? rollup.cancelledRuns),
              total_failed_records: parseNumber(rollup.total_failed_records ?? rollup.totalFailedRecords),
              runs_with_failures: parseNumber(rollup.runs_with_failures ?? rollup.runsWithFailures),
              overall_score: parseNumber(rollup.overall_score ?? rollup.overallScore),
              health_label: String(rollup.health_label || rollup.healthLabel || 'watch'),
              summary: String(rollup.summary || ''),
            }))
          : [],
        active_incident_count: parseNumber(data.workspace_summary?.active_incident_count ?? data.workspaceSummary?.activeIncidentCount),
        active_incidents: Array.isArray(data.workspace_summary?.active_incidents || data.workspaceSummary?.activeIncidents)
          ? (data.workspace_summary?.active_incidents || data.workspaceSummary?.activeIncidents).map((incident: any) => ({
              incident_id: String(incident.incident_id || incident.incidentId || ''),
              title: String(incident.title || ''),
              status: String(incident.status || ''),
              severity: incident.severity ?? null,
              incident_kind: String(incident.incident_kind || incident.incidentKind || ''),
              assigned_to: incident.assigned_to ?? incident.assignedTo ?? null,
              run_id: incident.run_id ?? incident.runId ?? null,
              run_plan_id: incident.run_plan_id ?? incident.runPlanId ?? null,
            }))
          : [],
      }
    : null,
  scorecards: Array.isArray(data.scorecards) ? data.scorecards.map(parseScorecard) : [],
})

const parseServiceLevelSummary = (data: any): ServiceLevelSummary => ({
  workspaceId: String(data.workspace_id || data.workspaceId || '').trim() || null,
  totalDefinitions: parseNumber(data.total_definitions ?? data.totalDefinitions),
  activeDefinitions: parseNumber(data.active_definitions ?? data.activeDefinitions),
  draftDefinitions: parseNumber(data.draft_definitions ?? data.draftDefinitions),
  approvedDefinitions: parseNumber(data.approved_definitions ?? data.approvedDefinitions),
  deprecatedDefinitions: parseNumber(data.deprecated_definitions ?? data.deprecatedDefinitions),
  compliantDefinitions: parseNumber(data.compliant_definitions ?? data.compliantDefinitions),
  atRiskDefinitions: parseNumber(data.at_risk_definitions ?? data.atRiskDefinitions),
  definitions: Array.isArray(data.definitions)
    ? data.definitions.map((definition: any) => ({
        id: String(definition.id || ''),
        name: String(definition.name || ''),
        scopeKind: String(definition.scope_kind || definition.scopeKind || ''),
        scopeId: String(definition.scope_id || definition.scopeId || ''),
        metricKind: String(definition.metric_kind || definition.metricKind || ''),
        thresholdValue: definition.threshold_value ?? definition.thresholdValue ?? 0,
        thresholdOperator: String(definition.threshold_operator || definition.thresholdOperator || 'gte'),
        lifecycleStatus: String(definition.lifecycle_status || definition.lifecycleStatus || 'draft'),
        approvalStatus: String(definition.approval_status || definition.approvalStatus || 'draft'),
        adherence: definition.adherence
          ? {
              currentValue: definition.adherence.current_value ?? definition.adherence.currentValue ?? null,
              thresholdValue: definition.adherence.threshold_value ?? definition.adherence.thresholdValue ?? null,
              thresholdOperator: String(definition.adherence.threshold_operator || definition.adherence.thresholdOperator || 'gte'),
              complianceRatePct: definition.adherence.compliance_rate_pct ?? definition.adherence.complianceRatePct ?? null,
              meetsTarget: definition.adherence.meets_target ?? definition.adherence.meetsTarget ?? null,
              summary: String(definition.adherence.summary || '').trim() || null,
            }
          : null,
      }))
    : [],
})

const formatHealthLabel = (value: string): string => {
  if (value === 'healthy') {
    return 'Healthy'
  }
  if (value === 'attention') {
    return 'Needs attention'
  }
  return 'Watch'
}

const scoreTone = (score: number): 'green' | 'blue' | 'red' => {
  if (score >= 90) {
    return 'green'
  }
  if (score >= 70) {
    return 'blue'
  }
  return 'red'
}

const scopeLabel = (scopeType: string): string => {
  if (scopeType === 'data_asset') {
    return 'Data Asset'
  }
  return 'Workspace'
}

const historyScopeLabels: Record<'dataset' | 'rule' | 'domain' | 'data_product', string> = {
  dataset: 'Dataset',
  rule: 'Rule',
  domain: 'Domain',
  data_product: 'Data Product',
}

const historyScopeParamNames: Record<'dataset' | 'rule' | 'domain' | 'data_product', 'datasetId' | 'ruleId' | 'domainId' | 'dataProductId'> = {
  dataset: 'datasetId',
  rule: 'ruleId',
  domain: 'domainId',
  data_product: 'dataProductId',
}

const parseHistorySummary = (data: any): QualityHistorySummary => ({
  lookback_amount: parseNumber(data.lookback_amount ?? data.lookbackAmount),
  lookback_unit: String(data.lookback_unit || data.lookbackUnit || 'hours'),
  total_events: parseNumber(data.total_events ?? data.totalEvents),
  scoped_groups: parseNumber(data.scoped_groups ?? data.scopedGroups),
  total_detections: parseNumber(data.total_detections ?? data.totalDetections),
  detections_by_type: typeof data.detections_by_type === 'object' && data.detections_by_type !== null
    ? { ...data.detections_by_type }
    : typeof data.detectionsByType === 'object' && data.detectionsByType !== null
      ? { ...data.detectionsByType }
      : {},
  detections_by_severity: typeof data.detections_by_severity === 'object' && data.detections_by_severity !== null
    ? { ...data.detections_by_severity }
    : typeof data.detectionsBySeverity === 'object' && data.detectionsBySeverity !== null
      ? { ...data.detectionsBySeverity }
      : {},
  latest_observed_at: String(data.latest_observed_at || data.latestObservedAt || '') || null,
  drifts: Array.isArray(data.drifts) ? data.drifts.map((drift: any) => ({
    detector_type: String(drift.detector_type || drift.detectorType || ''),
    severity: String(drift.severity || ''),
    scope: {
      rule_id: drift.scope?.rule_id ?? drift.scope?.ruleId ?? null,
      dataset_id: drift.scope?.dataset_id ?? drift.scope?.datasetId ?? null,
      domain_id: drift.scope?.domain_id ?? drift.scope?.domainId ?? null,
      data_product_id: drift.scope?.data_product_id ?? drift.scope?.dataProductId ?? null,
    },
    observed_at: String(drift.observed_at || drift.observedAt || ''),
    baseline_value: drift.baseline_value ?? drift.baselineValue ?? null,
    current_value: drift.current_value ?? drift.currentValue ?? null,
    delta: drift.delta ?? null,
    threshold: drift.threshold ?? null,
    message: String(drift.message || ''),
    evidence: typeof drift.evidence === 'object' && drift.evidence !== null ? drift.evidence : {},
  })) : [],
})

const buildHistoryBuckets = (drifts: QualityHistoryDetection[]) => {
  const totals = new Map<string, number>()
  drifts.forEach((drift) => {
    const parsed = new Date(drift.observed_at)
    const bucketStart = Number.isNaN(parsed.getTime())
      ? drift.observed_at
      : new Date(Date.UTC(parsed.getUTCFullYear(), parsed.getUTCMonth(), parsed.getUTCDate(), parsed.getUTCHours())).toISOString()
    totals.set(bucketStart, (totals.get(bucketStart) || 0) + 1)
  })
  return Array.from(totals.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([bucket_start, total]) => ({ bucket_start, total }))
}

const formatTrendBucketLabel = (value: string): string => {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const TrendSparkline: React.FC<{ buckets: HealthScorecardTrendBucket[] }> = ({ buckets }) => {
  const points = useMemo(() => {
    if (buckets.length === 0) {
      return ''
    }

    const totals = buckets.map((bucket) => Math.max(0, bucket.total))
    const maxTotal = Math.max(1, ...totals)
    const step = buckets.length > 1 ? 100 / (buckets.length - 1) : 0

    return buckets
      .map((bucket, index) => {
        const x = buckets.length > 1 ? index * step : 50
        const y = 100 - ((Math.max(0, bucket.total) / maxTotal) * 72) - 8
        return `${x},${y}`
      })
      .join(' ')
  }, [buckets])

  if (buckets.length === 0) {
    return <div className="dashboard-content">No historical trend buckets were returned for this window.</div>
  }

  return (
    <div style={{ marginTop: '1rem' }}>
      <h4>Failure trend</h4>
      <div style={{ display: 'grid', gap: '0.5rem' }}>
        <svg viewBox="0 0 100 100" role="img" aria-label="Failure trend over time" style={{ width: '100%', height: '5rem' }}>
          <polyline
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinejoin="round"
            strokeLinecap="round"
            points={points}
          />
        </svg>
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(buckets.length, 6)}, minmax(0, 1fr))`, gap: '0.5rem' }}>
          {buckets.slice(-6).map((bucket) => (
            <div key={bucket.bucket_start} style={{ textAlign: 'center', fontSize: '0.8rem' }}>
              <strong>{bucket.total}</strong>
              <div>{formatTrendBucketLabel(bucket.bucket_start)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export const HealthScorecards: React.FC<HealthScorecardsProps> = ({ workspaceId, dataAssetId, apiBaseUrl, onRuleSelect, onNavigate }) => {
  const [page, setPage] = useState<HealthScorecardPage | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dashboardView, setDashboardView] = useState<'operational' | 'executive'>('operational')
  const [historyScopeType, setHistoryScopeType] = useState<'dataset' | 'rule' | 'domain' | 'data_product'>('dataset')
  const [historyScopeId, setHistoryScopeId] = useState('')
  const [historyLookbackAmount, setHistoryLookbackAmount] = useState(24)
  const [historySummary, setHistorySummary] = useState<QualityHistorySummary | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [serviceLevelSummary, setServiceLevelSummary] = useState<ServiceLevelSummary | null>(null)
  const [serviceLevelLoading, setServiceLevelLoading] = useState(false)
  const [serviceLevelError, setServiceLevelError] = useState<string | null>(null)

  const scorecardApiBase = useMemo(() => toApiGroupV1Base('rulebuilder', apiBaseUrl || undefined), [apiBaseUrl])

  useEffect(() => {
    let cancelled = false

    const loadScorecards = async () => {
      if (!workspaceId) {
        setPage(null)
        setError(null)
        setIsLoading(false)
        return
      }

      setIsLoading(true)
      try {
        const params = new URLSearchParams()
        params.set('workspaceId', workspaceId)
        if (dataAssetId) {
          params.set('dataAssetId', dataAssetId)
        }

        const token = getAuthToken()
        const response = await fetch(`${scorecardApiBase}/observability/health-scorecards?${params.toString()}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        const body = await response.json()
        if (!response.ok || body?.success === false) {
          throw new Error(body?.detail?.message || body?.error || 'Failed to load health scorecards')
        }

        if (!cancelled) {
          setPage(parseScorecardPage(body))
          setError(null)
        }
      } catch (fetchError) {
        if (!cancelled) {
          setPage(null)
          setError(fetchError instanceof Error ? fetchError.message : 'Failed to load health scorecards')
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void loadScorecards()

    return () => {
      cancelled = true
    }
  }, [dataAssetId, scorecardApiBase, workspaceId])

  useEffect(() => {
    let cancelled = false

    const loadServiceLevels = async () => {
      if (!workspaceId) {
        setServiceLevelSummary(null)
        setServiceLevelError(null)
        setServiceLevelLoading(false)
        return
      }

      setServiceLevelLoading(true)
      setServiceLevelError(null)

      try {
        const token = getAuthToken()
        const response = await fetch(
          `${scorecardApiBase}/service-levels?workspace_id=${encodeURIComponent(workspaceId)}`,
          { headers: token ? { Authorization: `Bearer ${token}` } : {} },
        )
        const body = await response.json()
        if (!response.ok || body?.success === false) {
          throw new Error(body?.detail?.message || body?.error || 'Failed to load service levels')
        }

        if (!cancelled) {
          setServiceLevelSummary(parseServiceLevelSummary(snakeToCamel(body)))
          setServiceLevelError(null)
        }
      } catch (fetchError) {
        if (!cancelled) {
          setServiceLevelSummary(null)
          setServiceLevelError(fetchError instanceof Error ? fetchError.message : 'Failed to load service levels')
        }
      } finally {
        if (!cancelled) {
          setServiceLevelLoading(false)
        }
      }
    }

    void loadServiceLevels()

    return () => {
      cancelled = true
    }
  }, [scorecardApiBase, workspaceId])

  const scorecards = useMemo(() => {
    const items = page?.scorecards ? [...page.scorecards] : []
    return items.sort((left, right) => {
      if (left.scope_type === right.scope_type) {
        return left.scope_name.localeCompare(right.scope_name)
      }
      if (left.scope_type === 'workspace') {
        return -1
      }
      if (right.scope_type === 'workspace') {
        return 1
      }
      return left.scope_name.localeCompare(right.scope_name)
    })
  }, [page])

  const workspaceScorecard = useMemo(
    () => scorecards.find((scorecard) => scorecard.scope_type === 'workspace') || null,
    [scorecards],
  )

  const dataAssetScorecards = useMemo(() => {
    return scorecards
      .filter((scorecard) => scorecard.scope_type === 'data_asset')
      .sort((left, right) => {
        if (left.overall_score !== right.overall_score) {
          return left.overall_score - right.overall_score
        }
        return left.scope_name.localeCompare(right.scope_name)
      })
  }, [scorecards])

  const executiveTopRules = useMemo(() => {
    return [...(page?.workspace_summary?.top_rules || [])].slice(0, 5)
  }, [page?.workspace_summary?.top_rules])

  const executiveOwnershipRollups = useMemo(() => {
    return [...(page?.workspace_summary?.ownership_rollups || [])]
  }, [page?.workspace_summary?.ownership_rollups])

  const executiveDomainRollups = useMemo(() => {
    return executiveOwnershipRollups.filter((rollup) => rollup.scope_kind === 'domain')
  }, [executiveOwnershipRollups])

  const executiveDataProductRollups = useMemo(() => {
    return executiveOwnershipRollups.filter((rollup) => rollup.scope_kind === 'data_product')
  }, [executiveOwnershipRollups])

  const executiveTopDegradedDatasets = useMemo(() => dataAssetScorecards.slice(0, 5), [dataAssetScorecards])

  const operationalTopIncidents = useMemo(() => {
    return [...(page?.workspace_summary?.active_incidents || [])].slice(0, 5)
  }, [page?.workspace_summary?.active_incidents])

  const serviceLevelAtRiskDefinitions = useMemo(() => {
    return (serviceLevelSummary?.definitions || [])
      .filter((definition) => definition.lifecycleStatus === 'active' && definition.adherence?.meetsTarget === false)
      .slice(0, 5)
  }, [serviceLevelSummary])

  const serviceLevelStatusTone = useMemo(() => {
    if (!serviceLevelSummary) {
      return 'info' as const
    }
    if (serviceLevelSummary.totalDefinitions <= 0) {
      return 'info' as const
    }
    if (serviceLevelSummary.atRiskDefinitions > 0) {
      return 'warning' as const
    }
    return 'success' as const
  }, [serviceLevelSummary])

  const serviceLevelStatusLabel = useMemo(() => {
    if (!serviceLevelSummary) {
      return serviceLevelLoading ? 'Loading service levels' : 'No service level summary'
    }
    if (serviceLevelSummary.totalDefinitions <= 0) {
      return 'No service levels'
    }
    if (serviceLevelSummary.atRiskDefinitions > 0) {
      return 'At risk'
    }
    return 'On track'
  }, [serviceLevelLoading, serviceLevelSummary])

  const handleOpenServiceLevels = useCallback(() => {
    onNavigate?.('reports-service-levels')
  }, [onNavigate])

  const historyBuckets = useMemo(() => buildHistoryBuckets(historySummary?.drifts || []), [historySummary])

  const handleLoadHistory = async () => {
    const trimmedScopeId = historyScopeId.trim()
    if (!trimmedScopeId) {
      setHistoryError(`Enter a ${historyScopeLabels[historyScopeType].toLowerCase()} ID before loading quality history.`)
      setHistorySummary(null)
      return
    }

    setHistoryLoading(true)
    setHistoryError(null)

    try {
      const params = new URLSearchParams()
      params.set('lookbackAmount', String(historyLookbackAmount))
      params.set('lookbackUnit', 'hours')
      params.set(historyScopeParamNames[historyScopeType], trimmedScopeId)

      const token = getAuthToken()
      const response = await fetch(`${scorecardApiBase}/result-history/drift?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const body = await response.json()
      if (!response.ok || body?.success === false) {
        throw new Error(body?.detail?.message || body?.error || 'Failed to load quality history')
      }

      setHistorySummary(parseHistorySummary(body))
    } catch (fetchError) {
      setHistorySummary(null)
      setHistoryError(fetchError instanceof Error ? fetchError.message : 'Failed to load quality history')
    } finally {
      setHistoryLoading(false)
    }
  }

  if (!workspaceId) {
    return (
      <section className="dashboard">
        <div className="dashboard-content">
          <h3>DQ Health Dashboard</h3>
          <p>Select a workspace to view observability scorecards.</p>
        </div>
      </section>
    )
  }

  return (
    <section className="dashboard">
      <div className="dashboard-content" style={{ marginBottom: '1.25rem' }}>
        <h3>DQ Health Dashboard</h3>
        <p>
          Workspace and data asset rollups for the current monitoring window.
          Dataset, domain, and data product history views are loaded from the backend on demand.
          {page ? ` Updated ${new Date(page.generated_at).toLocaleString()}.` : ''}
        </p>
      </div>

      {page?.workspace_summary && !isLoading && !error && (
        <div className="dashboard-content" style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'grid', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'flex-start' }}>
              <div>
                <p style={{ margin: 0, opacity: 0.8 }}>{dashboardView === 'executive' ? 'Executive dashboard' : 'Operational dashboard'}</p>
                <h3 style={{ marginTop: '0.25rem' }}>{page.workspace_summary.summary || 'Quality summary'}</h3>
                <p style={{ marginBottom: 0 }}>
                  Historical quality score for {page.workspace_summary.workspace_id || workspaceId}. Updated {new Date(page.workspace_summary.generated_at || page.generated_at).toLocaleString()}.
                </p>
                <p style={{ marginBottom: 0, marginTop: '0.5rem', opacity: 0.8 }}>
                  Current failures reflect the latest workspace window. Worsening trends compare adjacent history buckets.
                </p>
              </div>
              <div style={{ textAlign: 'right' }}>
                <strong style={{ display: 'block', fontSize: '2.5rem', lineHeight: 1 }}>
                  {page.workspace_summary.overall_score}
                </strong>
                <span>{formatHealthLabel(page.workspace_summary.health_label)}</span>
              </div>
            </div>

            <AppTabs
              ariaLabel="Dashboard view"
              value={dashboardView}
              onChange={setDashboardView}
              className="health-scorecards-view-control"
              tabs={[
                { value: 'operational', label: 'Operational', title: 'Show operational dashboard' },
                { value: 'executive', label: 'Executive', title: 'Show executive dashboard' },
              ]}
            />

            {dashboardView === 'executive' ? (
              <div className="health-scorecards-dashboard-shell">
                <AppCard className="health-scorecards-dashboard-panel">
                  <AppCardContent>
                    <div className="health-scorecards-dashboard-hero">
                      <div>
                        <p className="health-scorecards-section-label">Executive overview</p>
                        <h4 style={{ marginTop: '0.25rem' }}>Quality score, top failing rules, degraded datasets, and SLA posture</h4>
                        <p style={{ marginBottom: 0 }}>
                          Review the current workspace health at a glance before drilling into the operational details.
                        </p>
                      </div>
                      <div className="health-scorecards-dashboard-score">
                        <strong>{page.workspace_summary.overall_score}</strong>
                        <AppBadge tone={page.workspace_summary.health_label === 'healthy' ? 'success' : page.workspace_summary.health_label === 'attention' ? 'warning' : 'info'}>
                          {formatHealthLabel(page.workspace_summary.health_label)}
                        </AppBadge>
                      </div>
                    </div>
                    <div className="health-scorecards-metric-grid">
                      <div className="health-scorecards-metric-card">
                        <strong>{workspaceScorecard?.failed_runs || 0}</strong>
                        <div>Current failures</div>
                        <div>{workspaceScorecard ? `${workspaceScorecard.total_failed_records} failed records` : 'No failed records in the current window'}</div>
                      </div>
                      <div className="health-scorecards-metric-card">
                        <strong>{page.workspace_summary.top_regressions.length}</strong>
                        <div>Worsening trends</div>
                        <div>Bucket-to-bucket regressions</div>
                      </div>
                      <div className="health-scorecards-metric-card">
                        <strong>{page.workspace_summary.top_rules.length}</strong>
                        <div>Top failing rules</div>
                        <div>Current window</div>
                      </div>
                      <div className="health-scorecards-metric-card">
                        <strong>{serviceLevelSummary?.atRiskDefinitions || 0}</strong>
                        <div>SLA at risk</div>
                        <div>{serviceLevelSummary ? `${serviceLevelSummary.activeDefinitions} active definitions` : 'Loading service levels'}</div>
                      </div>
                    </div>
                  </AppCardContent>
                </AppCard>

                <div style={{ display: 'grid', gap: '1rem', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
                  <AppCard className="health-scorecards-dashboard-panel">
                    <AppCardContent>
                      <h4 style={{ marginTop: 0 }}>Top failing rules</h4>
                      {executiveTopRules.length > 0 ? (
                        <ul className="health-scorecards-list">
                          {executiveTopRules.map((rule) => (
                            <li key={rule.rule_id || rule.rule_name} className="health-scorecards-list-item">
                              {rule.rule_id && onRuleSelect ? (
                                <button
                                  type="button"
                                  onClick={() => onRuleSelect(rule.rule_id || '')}
                                  className="health-scorecards-link-button"
                                >
                                  {rule.rule_name}
                                </button>
                              ) : (
                                <span>{rule.rule_name}</span>
                              )}
                              {' '}· {rule.total}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p style={{ marginBottom: 0 }}>No failing rules were returned for this workspace summary.</p>
                      )}
                    </AppCardContent>
                  </AppCard>

                  <AppCard className="health-scorecards-dashboard-panel">
                    <AppCardContent>
                      <h4 style={{ marginTop: 0 }}>Domain and product rollups</h4>
                      {executiveOwnershipRollups.length > 0 ? (
                        <div style={{ display: 'grid', gap: '1rem' }}>
                          <div>
                            <h5 style={{ marginTop: 0 }}>Domains</h5>
                            {executiveDomainRollups.length > 0 ? (
                              <ul className="health-scorecards-list">
                                {executiveDomainRollups.map((rollup) => (
                                  <li key={`domain-${rollup.scope_id}`} className="health-scorecards-list-item">
                                    <div>
                                      <strong>{rollup.scope_name}</strong>
                                      <div>
                                        {rollup.asset_count} assets · {rollup.tracked_data_object_version_count} tracked source versions
                                      </div>
                                      <div>{rollup.summary}</div>
                                    </div>
                                    <AppBadge tone={rollup.health_label === 'healthy' ? 'success' : rollup.health_label === 'attention' ? 'warning' : 'info'}>
                                      {rollup.overall_score}
                                    </AppBadge>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p style={{ marginBottom: 0 }}>No domain rollups were returned for this workspace summary.</p>
                            )}
                          </div>
                          <div>
                            <h5 style={{ marginTop: 0 }}>Data products</h5>
                            {executiveDataProductRollups.length > 0 ? (
                              <ul className="health-scorecards-list">
                                {executiveDataProductRollups.map((rollup) => (
                                  <li key={`data-product-${rollup.scope_id}`} className="health-scorecards-list-item">
                                    <div>
                                      <strong>{rollup.scope_name}</strong>
                                      <div>
                                        {rollup.asset_count} assets · {rollup.tracked_data_object_version_count} tracked source versions
                                      </div>
                                      <div>{rollup.summary}</div>
                                    </div>
                                    <AppBadge tone={rollup.health_label === 'healthy' ? 'success' : rollup.health_label === 'attention' ? 'warning' : 'info'}>
                                      {rollup.overall_score}
                                    </AppBadge>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p style={{ marginBottom: 0 }}>No data product rollups were returned for this workspace summary.</p>
                            )}
                          </div>
                        </div>
                      ) : (
                        <p style={{ marginBottom: 0 }}>No ownership rollups were returned for this workspace summary.</p>
                      )}
                    </AppCardContent>
                  </AppCard>

                  <AppCard className="health-scorecards-dashboard-panel">
                    <AppCardContent>
                      <h4 style={{ marginTop: 0 }}>Top degraded datasets</h4>
                      {executiveTopDegradedDatasets.length > 0 ? (
                        <ul className="health-scorecards-list">
                          {executiveTopDegradedDatasets.map((scorecard) => (
                            <li key={`${scorecard.scope_type}-${scorecard.scope_id}`} className="health-scorecards-list-item">
                              <strong>{scorecard.scope_name}</strong>
                              <div>
                                Score {scorecard.overall_score} · {scorecard.failed_runs} failed runs · {scorecard.total_failed_records} failed records
                              </div>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p style={{ marginBottom: 0 }}>No data asset scorecards were returned for this workspace.</p>
                      )}
                    </AppCardContent>
                  </AppCard>

                  <AppCard className="health-scorecards-dashboard-panel">
                    <AppCardContent>
                      <div className="health-scorecards-sla-summary">
                        <div>
                          <h4 style={{ marginTop: 0 }}>SLA status</h4>
                          {serviceLevelError ? (
                            <AppBanner variant="error">{serviceLevelError}</AppBanner>
                          ) : (
                            <>
                              <div className="health-scorecards-sla-metrics">
                                <div className="health-scorecards-metric-card">
                                  <strong>{serviceLevelSummary?.totalDefinitions || 0}</strong>
                                  <div>Total definitions</div>
                                </div>
                                <div className="health-scorecards-metric-card">
                                  <strong>{serviceLevelSummary?.compliantDefinitions || 0}</strong>
                                  <div>Compliant</div>
                                </div>
                                <div className="health-scorecards-metric-card">
                                  <strong>{serviceLevelSummary?.atRiskDefinitions || 0}</strong>
                                  <div>At risk</div>
                                </div>
                                <div className="health-scorecards-metric-card">
                                  <strong>{serviceLevelStatusLabel}</strong>
                                  <div>Status</div>
                                </div>
                              </div>
                              <div style={{ marginTop: '0.75rem' }}>
                                <AppBadge tone={serviceLevelStatusTone}>{serviceLevelStatusLabel}</AppBadge>
                              </div>
                              <p style={{ marginBottom: 0, marginTop: '0.75rem' }}>
                                {serviceLevelSummary ? `${serviceLevelSummary.activeDefinitions} active definitions and ${serviceLevelSummary.approvedDefinitions} approved definitions are available for this workspace.` : 'Loading service levels from the backend.'}
                              </p>
                              <div style={{ marginTop: '0.75rem' }}>
                                {handleOpenServiceLevels && (
                                  <AppButton type="button" variant="secondary" onClick={handleOpenServiceLevels}>
                                    Open service levels
                                  </AppButton>
                                )}
                              </div>
                            </>
                          )}
                        </div>
                        {serviceLevelAtRiskDefinitions.length > 0 ? (
                          <div>
                            <h5 style={{ marginTop: 0 }}>At-risk definitions</h5>
                            <ul className="health-scorecards-list">
                              {serviceLevelAtRiskDefinitions.map((definition) => (
                                <li key={definition.id} className="health-scorecards-list-item">
                                  <strong>{definition.name}</strong>
                                  <div>
                                    {definition.metricKind} · {definition.scopeKind} / {definition.scopeId}
                                  </div>
                                  <div>{definition.adherence?.summary || 'Service level requires review.'}</div>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : (
                          <p style={{ marginBottom: 0 }}>No active service levels are currently at risk.</p>
                        )}
                      </div>
                    </AppCardContent>
                  </AppCard>
                </div>
              </div>
            ) : (
              <div style={{ display: 'grid', gap: '1rem' }}>
                <div style={{ display: 'grid', gap: '0.75rem', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
                  <div>
                    <strong>{workspaceScorecard?.failed_runs || 0}</strong>
                    <div>Current failures</div>
                    <div>{workspaceScorecard ? `${workspaceScorecard.total_failed_records} failed records` : 'No failed records in the current window'}</div>
                  </div>
                  <div>

                {page.workspace_summary.ownership_rollups.length > 0 ? (
                  <div>
                    <h4>Domain and product rollups</h4>
                    <div style={{ display: 'grid', gap: '0.75rem', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
                      {page.workspace_summary.ownership_rollups.slice(0, 4).map((rollup) => (
                        <div key={`${rollup.scope_kind}-${rollup.scope_id}`}>
                          <strong>{rollup.scope_kind === 'domain' ? 'Domain' : 'Data product'} · {rollup.scope_name}</strong>
                          <div>
                            Score {rollup.overall_score} · {rollup.asset_count} assets · {rollup.tracked_data_object_version_count} tracked versions
                          </div>
                          <div>{rollup.summary}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                    <strong>{page.workspace_summary.top_regressions.length}</strong>
                    <div>Worsening trends</div>
                    <div>Bucket-to-bucket regressions</div>
                  </div>
                  <div>
                    <strong>{page.workspace_summary.top_rules.length}</strong>
                    <div>Top failing rules</div>
                    <div>Current window</div>
                  </div>
                  <div>
                    <strong>{page.workspace_summary.active_incident_count}</strong>
                    <div>Active incidents</div>
                    <div>Open operational issues</div>
                  </div>
                </div>

                <div style={{ display: 'grid', gap: '1rem', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
                  <div>
                    <h4>Worsening trends</h4>
                    {page.workspace_summary.top_regressions.length > 0 ? (
                      <ul style={{ margin: 0, paddingInlineStart: '1.2rem' }}>
                        {page.workspace_summary.top_regressions.map((regression) => (
                          <li key={`${regression.bucket_start}-${regression.previous_bucket_start}`}>
                            {regression.previous_total} → {regression.current_total} failed records · +{regression.delta}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p style={{ marginBottom: 0 }}>No worsening trend windows were detected in this window.</p>
                    )}
                  </div>
                  <div>
                    <h4>Top failing rules</h4>
                    {page.workspace_summary.top_rules.length > 0 ? (
                      <ul style={{ margin: 0, paddingInlineStart: '1.2rem' }}>
                        {page.workspace_summary.top_rules.map((rule) => (
                          <li key={rule.rule_id || rule.rule_name}>
                            {rule.rule_id && onRuleSelect ? (
                              <button
                                type="button"
                                onClick={() => onRuleSelect(rule.rule_id || '')}
                                style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', color: 'inherit', textAlign: 'left' }}
                              >
                                {rule.rule_name}
                              </button>
                            ) : (
                              <span>{rule.rule_name}</span>
                            )}
                            {' '}· {rule.total}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p style={{ marginBottom: 0 }}>No failing rules were returned for this workspace summary.</p>
                    )}
                  </div>
                  <div>
                    <h4>Active incidents</h4>
                    {page.workspace_summary.active_incidents.length > 0 ? (
                      <ul style={{ margin: 0, paddingInlineStart: '1.2rem' }}>
                        {page.workspace_summary.active_incidents.map((incident) => (
                          <li key={incident.incident_id}>
                            <strong>{incident.title}</strong>
                            <div>
                              {incident.incident_kind} · {incident.status}
                              {incident.severity ? ` · ${incident.severity}` : ''}
                            </div>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p style={{ marginBottom: 0 }}>No active incidents are open for this workspace.</p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="dashboard-content" style={{ marginBottom: '1rem' }}>
        <div className="health-scorecards-history-panel">
          <div>
            <p style={{ margin: 0, opacity: 0.8 }}>Quality history</p>
            <h3 style={{ marginTop: '0.25rem' }}>View quality history by dataset, rule, domain, or data product</h3>
            <p style={{ marginBottom: 0 }}>
              Load the observed drift history for one canonical scope at a time and review the event timeline over the selected lookback window.
            </p>
          </div>

          <div className="health-scorecards-history-scope-scroll">
            <AppTabs
              ariaLabel="History scope"
              value={historyScopeType}
              onChange={setHistoryScopeType}
              className="health-scorecards-history-scope-control"
              tabs={(Object.keys(historyScopeLabels) as Array<keyof typeof historyScopeLabels>).map((scopeType) => ({
                value: scopeType,
                label: historyScopeLabels[scopeType],
                title: `Show ${historyScopeLabels[scopeType]}`,
              }))}
            />
          </div>

          <div className="health-scorecards-history-fields">
            <label className="health-scorecards-history-field" htmlFor="health-scorecards-history-scope-id">
              <span>{historyScopeLabels[historyScopeType]} ID</span>
              <AppInput
                label={`${historyScopeLabels[historyScopeType]} ID`}
                id="health-scorecards-history-scope-id"
                type="text"
                value={historyScopeId}
                onChange={(event: any) => setHistoryScopeId(event.target.value)}
                placeholder={`Enter ${historyScopeLabels[historyScopeType].toLowerCase()} ID`}
              />
            </label>
            <label className="health-scorecards-history-field" htmlFor="health-scorecards-history-lookback-hours">
              <span>Lookback hours</span>
              <AppInput
                label="Lookback hours"
                id="health-scorecards-history-lookback-hours"
                type="number"
                min={1}
                max={720}
                value={historyLookbackAmount}
                onChange={(event: any) => setHistoryLookbackAmount(Math.max(1, Math.min(720, parseNumber(event.target.value) || 24)))}
              />
            </label>
          </div>

          <div className="health-scorecards-history-actions">
            <Button type="button" onClick={handleLoadHistory} disabled={historyLoading}>
              {historyLoading ? 'Loading history...' : 'Load history'}
            </Button>
          </div>

          {historyError ? (
            <div role="alert" className="dashboard-content">
              <strong>Unable to load quality history.</strong> {historyError}
            </div>
          ) : null}

          {historySummary ? (
            <div style={{ display: 'grid', gap: '1rem' }}>
              <div style={{ display: 'grid', gap: '0.75rem', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
                <div>
                  <strong>{historySummary.total_detections}</strong>
                  <div>Detections</div>
                </div>
                <div>
                  <strong>{historySummary.scoped_groups}</strong>
                  <div>Scoped groups</div>
                </div>
                <div>
                  <strong>{historySummary.total_events}</strong>
                  <div>Total events</div>
                </div>
                <div>
                  <strong>{historySummary.latest_observed_at ? new Date(historySummary.latest_observed_at).toLocaleString() : 'n/a'}</strong>
                  <div>Latest observation</div>
                </div>
              </div>

              <TrendSparkline buckets={historyBuckets} />

              <div style={{ display: 'grid', gap: '1rem', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
                <div>
                  <h4>Detections by severity</h4>
                  <ul style={{ margin: 0, paddingInlineStart: '1.2rem' }}>
                    {Object.entries(historySummary.detections_by_severity).map(([severity, total]) => (
                      <li key={severity}>{severity} · {total}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h4>Drift events</h4>
                  {historySummary.drifts.length > 0 ? (
                    <ul style={{ margin: 0, paddingInlineStart: '1.2rem' }}>
                      {historySummary.drifts.slice(0, 5).map((drift) => {
                        const scopeId = drift.scope.rule_id || drift.scope.dataset_id || drift.scope.domain_id || drift.scope.data_product_id || 'unknown scope'
                        return (
                          <li key={`${drift.detector_type}-${drift.observed_at}-${scopeId}`}>
                            <strong>{drift.detector_type}</strong> · {drift.severity} · {scopeId} · {new Date(drift.observed_at).toLocaleString()}
                            <div>{drift.message}</div>
                            <div>
                              {drift.baseline_value !== null && drift.baseline_value !== undefined ? `Baseline ${drift.baseline_value}` : 'Baseline n/a'}
                              {' '}→{' '}
                              {drift.current_value !== null && drift.current_value !== undefined ? `current ${drift.current_value}` : 'current n/a'}
                              {drift.delta !== null && drift.delta !== undefined ? ` · delta ${drift.delta}` : ''}
                              {drift.threshold !== null && drift.threshold !== undefined ? ` · threshold ${drift.threshold}` : ''}
                            </div>
                          </li>
                        )
                      })}
                    </ul>
                  ) : (
                    <p style={{ marginBottom: 0 }}>No degradation or drift events were returned for this scope and lookback window.</p>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {isLoading && <div className="dashboard-content">Loading health scorecards...</div>}

      {error && !isLoading && (
        <div className="dashboard-content" role="alert">
          <strong>Unable to load health scorecards.</strong> {error}
        </div>
      )}

      {!isLoading && !error && scorecards.length === 0 && (
        <div className="dashboard-content">
          No health scorecards are available for this workspace yet.
        </div>
      )}

      {scorecards.length > 0 && (
        <div className="dashboard-grid" style={{ alignItems: 'stretch' }}>
          {scorecards.map((scorecard) => {
            const tone = scoreTone(scorecard.overall_score)
            return (
              <article key={`${scorecard.scope_type}-${scorecard.scope_id}`} className={`dashboard-card card-${tone}`}>
                <div className="dashboard-content">
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'flex-start' }}>
                    <div>
                      <p style={{ margin: 0, opacity: 0.8 }}>{scopeLabel(scorecard.scope_type)}</p>
                      <h3 style={{ marginTop: '0.25rem' }}>{scorecard.scope_name}</h3>
                      <p>{scorecard.summary}</p>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <strong style={{ display: 'block', fontSize: '2.75rem', lineHeight: 1 }}>
                        {scorecard.overall_score}
                      </strong>
                      <span>{formatHealthLabel(scorecard.health_label)}</span>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gap: '0.75rem', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', marginTop: '1rem' }}>
                    <div>
                      <strong>{scorecard.total_runs}</strong>
                      <div>Total runs</div>
                    </div>
                    <div>
                      <strong>{scorecard.failed_runs}</strong>
                      <div>Failed runs</div>
                    </div>
                    <div>
                      <strong>{scorecard.total_failed_records}</strong>
                      <div>Failed records</div>
                    </div>
                    <div>
                      <strong>{scorecard.tracked_data_object_version_ids.length}</strong>
                      <div>Tracked data versions</div>
                    </div>
                  </div>

                  <div style={{ marginTop: '1rem' }}>
                    <h4>Dimension rollups</h4>
                    <div style={{ display: 'grid', gap: '0.5rem' }}>
                      {scorecard.dimension_rollups.map((dimension) => (
                        <div
                          key={`${scorecard.scope_id}-${dimension.dimension}`}
                          style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'center' }}
                        >
                          <div>
                            <strong>{dimension.dimension}</strong>
                            <div>{dimension.rule_count} rules · {dimension.failed_record_total} failed records</div>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <strong>{dimension.score}</strong>
                            <div>{formatHealthLabel(dimension.status_label)}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <TrendSparkline buckets={scorecard.trend_buckets} />

                  <div style={{ display: 'grid', gap: '0.75rem', marginTop: '1rem' }}>
                    <div>
                      <h4>Top rules</h4>
                      <ul style={{ margin: 0, paddingInlineStart: '1.2rem' }}>
                        {scorecard.top_rules.slice(0, 5).map((rule) => (
                          <li key={`${scorecard.scope_id}-${rule.rule_id}`}>
                            {rule.rule_id && onRuleSelect ? (
                              <button
                                type="button"
                                onClick={() => onRuleSelect(rule.rule_id || '')}
                                style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', color: 'inherit', textAlign: 'left' }}
                              >
                                {rule.rule_name}
                              </button>
                            ) : (
                              <span>{rule.rule_name}</span>
                            )}
                            {' '}· {rule.total}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h4>Top reasons</h4>
                      <ul style={{ margin: 0, paddingInlineStart: '1.2rem' }}>
                        {scorecard.top_reasons.slice(0, 5).map((reason) => (
                          <li key={`${scorecard.scope_id}-${reason.reason_code}`}>
                            {reason.reason_text} · {reason.total}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {scorecard.data_asset_version_id && (
                    <p style={{ marginTop: '1rem', opacity: 0.8 }}>
                      Asset version {scorecard.data_asset_version_id}
                    </p>
                  )}
                </div>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
