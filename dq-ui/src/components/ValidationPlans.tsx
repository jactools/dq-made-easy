import React, { useCallback, useEffect, useMemo, useState } from 'react'

import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { useSettings } from '../hooks/useContexts'
import { useAuth } from '../hooks/useKeycloak'
import { snakeToCamel } from '../utils/caseConverters'
import { SecondaryButton } from './Button'
import { AdminPageHeader } from './AdminPageHeader'
import { StatusBanner } from './StatusBanner'
import { AppPageShell } from './app-primitives/AppPageShell'
import './Settings.css'

type ValidationPlanVersion = {
  runPlanVersionId: string
  governanceState: string
  scheduleDefinition?: {
    scheduledAt?: string | null
  } | null
  createdAt: string
}

type ValidationPlanScopeSelector = {
  tagIds?: string[]
}

type ValidationPlan = {
  runPlanId: string
  workspaceId: string
  scopeSelector?: ValidationPlanScopeSelector
  planningMode: string
  status: string
  currentActiveVersionId?: string | null
  pendingVersionId?: string | null
  pendingVersionGovernanceState?: string | null
  activatedBy?: string | null
  activatedAt?: string | null
  lastDispatchedRunId?: string | null
  createdAt: string
  updatedAt: string
  versions: ValidationPlanVersion[]
}

type ValidationPlanSuite = {
  runPlanId: string
  runPlanVersionId: string
  governanceState: string
  artifactId?: string | null
  artifactVersion?: number | null
  engineType?: string | null
  tagIds?: string[]
  scheduleDefinition?: {
    scheduledAt?: string | null
  } | null
  artifactSnapshot?: Record<string, unknown> | null
  createdAt: string
}

type ValidationPlanCatalog = {
  validationRunPlans: ValidationPlan[]
  validationSuites: ValidationPlanSuite[]
}

type ValidationPlanRecentRun = {
  id: string
  runPlanId?: string | null
  suiteId?: string | null
  suiteVersion?: number | null
  ruleName?: string | null
  ruleId?: string | null
  dataObjectNames?: string[]
  status: string
  submittedAt: string
}

type ValidationPlanRecentRunsResponse = {
  recentRuns: ValidationPlanRecentRun[]
}

type ValidationPlanReplayResponse = {
  runId: string
  queueMessageId: string
  runPlanId: string
  runPlanVersionId: string
  selectionMode?: string | null
  suiteId?: string | null
  suiteVersion?: number | null
  engineType?: string | null
  engineTarget?: string | null
  executionShape?: string | null
  dispatchMode?: string | null
  queueKey?: string | null
  scheduledAt: string
  correlationId?: string | null
}

type ValidationPlanReplayStatus = {
  message: string
  scheduledAt: string
  queueMessageId?: string | null
  queueKey?: string | null
  correlationId?: string | null
  dispatchMode?: string | null
}

const RECENT_RUN_LOOKBACK_AMOUNT = 30
const RECENT_RUN_LOOKBACK_UNIT = 'days'
const RECENT_RUN_LIMIT = 5
const RECENT_RUN_REFRESH_ATTEMPTS = 6
const RECENT_RUN_REFRESH_INTERVAL_MS = 1000

const formatDateTime = (value: string | null | undefined): string => {
  if (!value) return 'n/a'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

const formatTagIds = (tagIds: string[] | null | undefined): string => {
  const normalized = (tagIds || []).map((tagId) => String(tagId || '').trim()).filter(Boolean)
  return normalized.length > 0 ? normalized.join(', ') : 'none'
}

const extractErrorMessage = (payload: unknown, fallback: string): string => {
  const detail = (payload as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  const payloadMessage = (payload as { message?: unknown })?.message
  if (typeof payloadMessage === 'string') return payloadMessage
  return fallback
}

export const ValidationPlans: React.FC = () => {
  const auth = useAuth()
  const settings = useSettings()
  const apiBaseUrl = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  const workspaceId = auth.currentWorkspaceId?.trim() || ''

  const [plans, setPlans] = useState<ValidationPlan[]>([])
  const [suites, setSuites] = useState<ValidationPlanSuite[]>([])
  const [recentRunsByPlanId, setRecentRunsByPlanId] = useState<Record<string, ValidationPlanRecentRun[]>>({})
  const [recentRunsErrorsByPlanId, setRecentRunsErrorsByPlanId] = useState<Record<string, string | null>>({})
  const [pendingReplayPlanId, setPendingReplayPlanId] = useState<string | null>(null)
  const [replayStatusByPlanId, setReplayStatusByPlanId] = useState<Record<string, ValidationPlanReplayStatus>>({})
  const [highlightedRecentRunByPlanId, setHighlightedRecentRunByPlanId] = useState<Record<string, string | null>>({})
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const activeSuiteByPlanVersionKey = useMemo(() => {
    const index: Record<string, ValidationPlanSuite> = {}
    for (const suite of suites) {
      index[`${suite.runPlanId}:${suite.runPlanVersionId}`] = suite
    }
    return index
  }, [suites])

  const loadPlans = useCallback(async () => {
    if (!workspaceId) {
      setPlans([])
      setSuites([])
      setRecentRunsByPlanId({})
      setRecentRunsErrorsByPlanId({})
      setHighlightedRecentRunByPlanId({})
      setReplayStatusByPlanId({})
      setError('Select a workspace to view validation plans.')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const token = getAuthToken()
      const params = new URLSearchParams({ workspaceId })
      const response = await fetch(`${apiBaseUrl}/run-plan?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })

      const payload = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Failed to load validation plan catalog.')
      }
      if (!payload || Array.isArray(payload) || typeof payload !== 'object') {
        throw new Error('Unexpected response shape from validation plan catalog API.')
      }

      const catalog = snakeToCamel<ValidationPlanCatalog>(payload)
      if (!Array.isArray(catalog.validationRunPlans) || !Array.isArray(catalog.validationSuites)) {
        throw new Error('Unexpected response shape from validation plan catalog API.')
      }

      setPlans(catalog.validationRunPlans)
      setSuites(catalog.validationSuites)

      const planRecentRunResults = await Promise.all(
        catalog.validationRunPlans.map(async (plan) => {
          const result = await fetchRecentRunsForPlan(plan.runPlanId)
          return { planId: plan.runPlanId, recentRuns: result.recentRuns, error: result.error }
        })
      )

      const nextRecentRunsByPlanId: Record<string, ValidationPlanRecentRun[]> = {}
      const nextRecentRunsErrorsByPlanId: Record<string, string | null> = {}
      for (const result of planRecentRunResults) {
        nextRecentRunsByPlanId[result.planId] = result.recentRuns
        nextRecentRunsErrorsByPlanId[result.planId] = result.error
      }

      setRecentRunsByPlanId(nextRecentRunsByPlanId)
      setRecentRunsErrorsByPlanId(nextRecentRunsErrorsByPlanId)
    } catch (exc) {
      setPlans([])
      setSuites([])
      setRecentRunsByPlanId({})
      setRecentRunsErrorsByPlanId({})
      setHighlightedRecentRunByPlanId({})
      setReplayStatusByPlanId({})
      setError(exc instanceof Error ? exc.message : 'Failed to load validation plans.')
    } finally {
      setLoading(false)
    }
  }, [apiBaseUrl, workspaceId])

  const fetchRecentRunsForPlan = useCallback(
    async (planId: string): Promise<{ recentRuns: ValidationPlanRecentRun[]; error: string | null }> => {
      if (!workspaceId) {
        return { recentRuns: [], error: 'Select a workspace to view validation plans.' }
      }

      const token = getAuthToken()
      const recentRunsParams = new URLSearchParams({
        workspaceId,
        runPlanId: planId,
        lookbackAmount: String(RECENT_RUN_LOOKBACK_AMOUNT),
        lookbackUnit: RECENT_RUN_LOOKBACK_UNIT,
        recentLimit: String(RECENT_RUN_LIMIT),
      })

      try {
        const recentRunsResponse = await fetch(`${apiBaseUrl}/gx/runs/stats?${recentRunsParams.toString()}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        const recentRunsPayload = await recentRunsResponse.json().catch(() => null)
        if (!recentRunsResponse.ok) {
          throw new Error(
            typeof recentRunsPayload?.detail === 'string'
              ? recentRunsPayload.detail
              : `Failed to load recent runs for ${planId}.`
          )
        }
        const recentRunsCatalog = snakeToCamel<ValidationPlanRecentRunsResponse>(recentRunsPayload)
        if (!Array.isArray(recentRunsCatalog.recentRuns)) {
          throw new Error(`Unexpected response shape while loading recent runs for ${planId}.`)
        }
        return { recentRuns: recentRunsCatalog.recentRuns, error: null }
      } catch (exc) {
        return {
          recentRuns: [],
          error: exc instanceof Error ? exc.message : `Failed to load recent runs for ${planId}.`,
        }
      }
    },
    [apiBaseUrl, workspaceId]
  )

  const replayPlan = useCallback(
    async (plan: ValidationPlan) => {
      if (!workspaceId) {
        setActionError('Select a workspace before replaying validation plans.')
        return
      }
      if (!plan.currentActiveVersionId) {
        setActionError(`Validation plan ${plan.runPlanId} has no active version to replay.`)
        return
      }

      setPendingReplayPlanId(plan.runPlanId)
      setActionError(null)
      setActionMessage(null)

      try {
        const token = getAuthToken()
        const response = await fetch(`${apiBaseUrl}/validation-run-plans/${encodeURIComponent(plan.runPlanId)}/replay`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        })

        const payload = await response.json().catch(() => null)
        if (!response.ok) {
          throw new Error(extractErrorMessage(payload, `Failed to replay validation plan ${plan.runPlanId}.`))
        }

        const replay = snakeToCamel<ValidationPlanReplayResponse>(payload)
        const scheduledAt = formatDateTime(replay.scheduledAt)
        const queueReference = replay.queueMessageId || replay.runId
        setReplayStatusByPlanId((current) => ({
          ...current,
          [plan.runPlanId]: {
            message: `Replay scheduled for ${plan.runPlanId} at ${scheduledAt}. Queue message ${queueReference}${replay.queueKey ? ` on ${replay.queueKey}` : ''}${replay.correlationId ? `; correlation ${replay.correlationId}` : ''}.`,
            scheduledAt: replay.scheduledAt,
            queueMessageId: replay.queueMessageId,
            queueKey: replay.queueKey,
            correlationId: replay.correlationId,
            dispatchMode: replay.dispatchMode,
          },
        }))
        setHighlightedRecentRunByPlanId((current) => ({
          ...current,
          [plan.runPlanId]: replay.runId,
        }))
        setActionMessage(`Replay scheduled for ${replay.runPlanId} at ${scheduledAt}.`)
        await loadPlans()
        void refreshRecentRunsUntilVisible(plan.runPlanId, replay.runId)
      } catch (exc) {
        setActionError(exc instanceof Error ? exc.message : `Failed to replay validation plan ${plan.runPlanId}.`)
      } finally {
        setPendingReplayPlanId(null)
      }
    },
    [apiBaseUrl, loadPlans, refreshRecentRunsUntilVisible, workspaceId]
  )

  function refreshRecentRunsUntilVisible(planId: string, replayRunId: string): Promise<void> {
    return (async () => {
      for (let attempt = 0; attempt < RECENT_RUN_REFRESH_ATTEMPTS; attempt += 1) {
        const result = await fetchRecentRunsForPlan(planId)
        setRecentRunsByPlanId((current) => ({
          ...current,
          [planId]: result.recentRuns,
        }))
        setRecentRunsErrorsByPlanId((current) => ({
          ...current,
          [planId]: result.error,
        }))

        if (result.recentRuns.some((run) => run.id === replayRunId)) {
          setHighlightedRecentRunByPlanId((current) => ({
            ...current,
            [planId]: replayRunId,
          }))
          return
        }

        if (attempt < RECENT_RUN_REFRESH_ATTEMPTS - 1) {
          await new Promise((resolve) => {
            globalThis.setTimeout(resolve, RECENT_RUN_REFRESH_INTERVAL_MS)
          })
        }
      }
    })()
  }

  useEffect(() => {
    void loadPlans()
  }, [loadPlans])

  return (
    <AppPageShell className="settings-container">
      <AdminPageHeader
        title="Validation Plans"
        subtitle="View workspace-scoped validation plans and suites regardless of the execution engine used to run them."
      />
      <div className="settings-content">
        <div className="settings-panel">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <div className="settings-panel" style={{ margin: 0 }}>
              <div className="gx-run-plan-card-heading">
                <h3 className="gx-run-plan-card-title">Overview</h3>
              </div>
              <p className="settings-subtitle" style={{ margin: 0 }}>
                Current workspace: <strong>{workspaceId || 'not selected'}</strong>. This page lists validation plans, suites, and plan-scoped recent runs; runtime monitoring remains in Operations.
              </p>
            </div>

            {error && <StatusBanner variant="error" message={error} onDismiss={() => setError(null)} />}
            {actionError && <StatusBanner variant="error" message={actionError} onDismiss={() => setActionError(null)} />}
            {actionMessage && <StatusBanner variant="success" message={actionMessage} onDismiss={() => setActionMessage(null)} />}

            <div className="settings-panel" style={{ margin: 0 }}>
              <div className="gx-run-plan-card-heading">
                <h3 className="gx-run-plan-card-title">Validation Plan List</h3>
              </div>

              {loading && <p className="settings-subtitle" style={{ marginTop: 16 }}>Loading validation plans…</p>}

              {!loading && plans.length === 0 && !error && (
                <p className="settings-subtitle" style={{ marginTop: 16 }}>No validation plans found for the current workspace.</p>
              )}

              <div className="admin-users gx-run-plan-list">
                {plans.map((plan) => {
                  const latestVersion = plan.versions[plan.versions.length - 1] || null
                  const activeSuite = plan.currentActiveVersionId
                    ? activeSuiteByPlanVersionKey[`${plan.runPlanId}:${plan.currentActiveVersionId}`] || null
                    : null
                  return (
                    <div key={plan.runPlanId} className="admin-user-row gx-run-plan-card">
                      <div className="admin-user-info gx-run-plan-card-info">
                        <span className="admin-user-name">{plan.runPlanId}</span>
                        <span className="admin-user-email">
                          Planning mode: <strong>{plan.planningMode}</strong> | Status: <strong>{plan.status}</strong> | Versions: {plan.versions.length}
                        </span>
                        <span className="admin-user-id">
                          Active version: {plan.currentActiveVersionId || 'n/a'} | Pending branch: {plan.pendingVersionGovernanceState || 'none'} | Last dispatched run: {plan.lastDispatchedRunId || 'n/a'}
                        </span>
                        <span className="admin-user-id">Tags: {formatTagIds(plan.scopeSelector?.tagIds)}</span>
                        <span className="admin-user-id">
                          Active suite: {activeSuite?.artifactId || 'n/a'} v{activeSuite?.artifactVersion ?? 'n/a'} | Engine: {activeSuite?.engineType || 'n/a'}
                        </span>
                        <span className="admin-user-id">
                          Latest schedule: {formatDateTime(latestVersion?.scheduleDefinition?.scheduledAt || null)} | Updated: {formatDateTime(plan.updatedAt)}
                        </span>
                      </div>
                      <div className="gx-run-plan-version-list">
                        {plan.versions.map((version, index) => {
                          const isActiveVersion = plan.currentActiveVersionId === version.runPlanVersionId
                          return (
                            <div key={version.runPlanVersionId} className="gx-run-plan-version-row">
                              <div>
                                <div className="admin-user-name gx-run-plan-version-title">
                                  Plan version {index + 1}{isActiveVersion ? ' (active)' : ''}
                                </div>
                                <div className="admin-user-email">
                                  Scheduled {formatDateTime(version.scheduleDefinition?.scheduledAt || null)}
                                </div>
                                <div className="admin-user-id">
                                  Version ID: {version.runPlanVersionId} | State: {version.governanceState}
                                </div>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                      <div className="settings-panel" style={{ marginTop: 16, marginBottom: 0 }}>
                        <div className="gx-run-plan-card-heading">
                          <h4 className="gx-run-plan-card-title">Recent Runs</h4>
                        </div>
                        {recentRunsErrorsByPlanId[plan.runPlanId] && (
                          <p className="settings-subtitle" style={{ marginTop: 16 }}>
                            Unable to load recent runs: {recentRunsErrorsByPlanId[plan.runPlanId]}
                          </p>
                        )}
                        {!recentRunsErrorsByPlanId[plan.runPlanId] && (recentRunsByPlanId[plan.runPlanId]?.length || 0) === 0 && !loading && (
                          <p className="settings-subtitle" style={{ marginTop: 16 }}>No recent runs found for this plan.</p>
                        )}
                        {!recentRunsErrorsByPlanId[plan.runPlanId] && (recentRunsByPlanId[plan.runPlanId]?.length || 0) > 0 && (
                          <div className="gx-run-plan-version-list">
                            {recentRunsByPlanId[plan.runPlanId].map((run) => {
                              const isHighlightedRun = highlightedRecentRunByPlanId[plan.runPlanId] === run.id
                              return (
                                <div
                                  key={run.id}
                                  className="gx-run-plan-version-row"
                                  style={isHighlightedRun ? {
                                    boxShadow: '0 0 0 2px rgba(21, 101, 192, 0.28)',
                                    background: 'rgba(21, 101, 192, 0.08)',
                                  } : undefined}
                                >
                                  <div>
                                    <div className="admin-user-name gx-run-plan-version-title">
                                      {run.id}
                                      {isHighlightedRun && (
                                        <span style={{ marginLeft: 8, color: '#1565c0', fontSize: 12, fontWeight: 700 }}>
                                          Newly queued replay
                                        </span>
                                      )}
                                    </div>
                                    <div className="admin-user-email">
                                      Status: <strong>{run.status}</strong> | Submitted: {formatDateTime(run.submittedAt)}
                                    </div>
                                    <div className="admin-user-id">
                                      Rule: {run.ruleName || run.ruleId || 'n/a'} | Suite: {run.suiteId || 'n/a'}
                                    </div>
                                    {run.dataObjectNames && run.dataObjectNames.length > 0 && (
                                      <div className="admin-user-id">
                                        Data objects: {run.dataObjectNames.join(', ')}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        )}
                        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
                          <SecondaryButton
                            onClick={() => void replayPlan(plan)}
                            disabled={!plan.currentActiveVersionId || pendingReplayPlanId === plan.runPlanId}
                          >
                            {pendingReplayPlanId === plan.runPlanId ? 'Scheduling…' : 'Run again'}
                          </SecondaryButton>
                        </div>
                        {replayStatusByPlanId[plan.runPlanId] && (
                          <p className="settings-subtitle" style={{ marginTop: 12, marginBottom: 0, textAlign: 'right' }}>
                            {replayStatusByPlanId[plan.runPlanId].message}
                          </p>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="settings-panel" style={{ margin: 0 }}>
              <div className="gx-run-plan-card-heading">
                <h3 className="gx-run-plan-card-title">Validation Suite List</h3>
              </div>

              {!loading && suites.length === 0 && !error && (
                <p className="settings-subtitle" style={{ marginTop: 16 }}>No validation suites found for the current workspace.</p>
              )}

              <div className="admin-users gx-run-plan-list">
                {suites.map((suite) => (
                  <div key={`${suite.runPlanId}:${suite.runPlanVersionId}`} className="admin-user-row gx-run-plan-card">
                    <div className="admin-user-info gx-run-plan-card-info">
                      <span className="admin-user-name">{suite.artifactId || suite.runPlanVersionId}</span>
                      <span className="admin-user-email">
                        Engine: <strong>{suite.engineType || 'n/a'}</strong> | Governance state: <strong>{suite.governanceState}</strong>
                      </span>
                      <span className="admin-user-id">
                        Run plan: {suite.runPlanId} | Version: {suite.runPlanVersionId}
                      </span>
                      <span className="admin-user-id">Tags: {formatTagIds(suite.tagIds)}</span>
                      <span className="admin-user-id">
                        Suite version: {suite.artifactVersion ?? 'n/a'} | Scheduled: {formatDateTime(suite.scheduleDefinition?.scheduledAt || null)}
                      </span>
                      <span className="admin-user-id">
                        Created: {formatDateTime(suite.createdAt)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppPageShell>
  )
}