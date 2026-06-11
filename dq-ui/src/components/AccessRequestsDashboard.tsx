
const buildAuthHeaders = (): Record<string, string> => {
  const token = getAuthToken()
  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  return headers
}
import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { useCatalogDrift, DriftSummary } from '../hooks/useCatalogDrift'
import { useSettings, useAuth } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { PrimaryButton, SecondaryButton } from './Button'
import { AppPageHeader, AppPageShell, AppSelect } from './app-primitives'
import { AppIcon } from './app-primitives'
import { StatusBanner } from './StatusBanner'
import { SupportRequestFlow } from './SupportRequestFlow'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { normalizeValidationUiText } from '../utils/validationTerminology'
import './AccessRequestsDashboard.css'

type GovernanceStatusValue = {
  value: string
  label: string
  description?: string | null
  isInitial?: boolean
  isTerminal?: boolean
}

type GovernanceStatusTransition = {
  fromStatus: string
  toStatus: string
  label: string
  requiredAnyScopes: string[]
}

type GovernanceStatusModel = {
  entity: string
  statuses: GovernanceStatusValue[]
  transitions: GovernanceStatusTransition[]
  allowedTransitionsByStatus: Record<string, string[]>
}
type GovernancePolicyDraft = {
  rule?: {
    transitions?: GovernanceStatusTransition[]
  }
  approval?: {
    transitions?: GovernanceStatusTransition[]
  }
  runPlan?: {
    transitions?: GovernanceStatusTransition[]
  }
}

type JitAccessRequestView = {
  id: string
  requesterId: string
  workspaceId: string
  roleId: string
  status: string
  requestedDurationMinutes: number
  comments?: string | null
  requestedAt: string
  reviewedBy?: string | null
  reviewedAt?: string | null
  expiresAt?: string | null
}

type JitAccessRequestFormState = {
  roleId: 'exception-fact-reader' | 'exception-fact-investigator'
  requestedDurationMinutes: string
  comments: string
}

type JitAccessSupportRequestContext = {
  errorMessage: string
  errorDetails: string
  responseStatus: number
  roleId: JitAccessRequestFormState['roleId']
  requestedDurationMinutes: number
  comments: string
}

const JIT_ACCESS_ROLE_OPTIONS: Array<{
  value: JitAccessRequestFormState['roleId']
  label: string
  description: string
}> = [
  {
    value: 'exception-fact-reader',
    label: 'Exception Fact Reader',
    description: 'List, summary, and analytics access without exports.',
  },
  {
    value: 'exception-fact-investigator',
    label: 'Exception Fact Investigator',
    description: 'Raw fact detail access without exports.',
  },
]

const normalizeWorkspaceId = (value: unknown): string => String(value ?? '').trim()

const isExceptionJitRole = (role: string): boolean => String(role || '').trim().startsWith('exception-fact-')

const parseResponseDetail = (value: string): string => {
  const text = String(value || '').trim()
  if (!text) {
    return ''
  }

  try {
    const parsed = JSON.parse(text) as { detail?: unknown; title?: unknown }
    if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
      return parsed.detail.trim()
    }
    if (typeof parsed.title === 'string' && parsed.title.trim()) {
      return parsed.title.trim()
    }
  } catch {
    // Keep the original body when it is not JSON.
  }

  return text
}

const formatJitAccessSubmissionError = (responseStatus: number, errorDetails: string): string => {
  const normalizedDetails = normalizeValidationUiText(errorDetails).trim()

  if (/exception_fact_access_requests_role_id_fkey/i.test(errorDetails) || /Key \(role_id\)=\([^)]+\) is not present in table "roles"/i.test(errorDetails)) {
    return 'This exception-record role is not configured for the current environment. Request assistance to report the error.'
  }

  if (normalizedDetails) {
    return normalizedDetails
  }

  return `Failed to submit exception-record access request (${responseStatus}).`
}

const formatJitAccessStatus = (status: string): string => {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'timed_out') return 'Timed out'
  if (normalized === 'rejected' || normalized === 'revoked') return 'Declined'
  return normalized
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

const normalizeStatusModel = (payload: unknown): GovernanceStatusModel | null => {
  const record = snakeToCamel(payload) as Record<string, unknown>
  if (!record || typeof record !== 'object') {
    return null
  }

  const statuses = Array.isArray(record.statuses) ? (record.statuses as GovernanceStatusValue[]) : []
  const transitions = Array.isArray(record.transitions)
    ? (record.transitions as GovernanceStatusTransition[])
    : []
  const allowedTransitionsByStatus =
    record.allowedTransitionsByStatus && typeof record.allowedTransitionsByStatus === 'object'
      ? (record.allowedTransitionsByStatus as Record<string, string[]>)
      : {}

  return {
    entity: String(record.entity || ''),
    statuses,
    transitions,
    allowedTransitionsByStatus,
  }
}

const buildTransitionLookup = (model: GovernanceStatusModel | null): Map<string, GovernanceStatusTransition> => {
  const lookup = new Map<string, GovernanceStatusTransition>()
  if (!model) {
    return lookup
  }

  for (const transition of model.transitions) {
    lookup.set(`${transition.fromStatus} -> ${transition.toStatus}`, transition)
  }

  return lookup
}

export const AccessRequestsDashboard: React.FC<{ onNavigate?: (id: string) => void; mode?: 'overview' | 'access-requests' }> = ({ onNavigate, mode = 'overview' }) => {
  const settings = useSettings()
  const auth = useAuth()
  const { getDriftSummary, loading: driftLoading, error: driftError } = useCatalogDrift()
  const isAccessRequestMode = mode === 'access-requests'

  const [driftSummary, setDriftSummary] = useState<DriftSummary | null>(null)
  const [ruleStatusModel, setRuleStatusModel] = useState<GovernanceStatusModel | null>(null)
  const [approvalStatusModel, setApprovalStatusModel] = useState<GovernanceStatusModel | null>(null)
  const [runPlanStatusModel, setRunPlanStatusModel] = useState<GovernanceStatusModel | null>(null)
  const [appConfigData, setAppConfigData] = useState<(Record<string, unknown> & { statusGovernance?: GovernancePolicyDraft }) | null>(null)
  const [jitAccessRequests, setJitAccessRequests] = useState<JitAccessRequestView[]>([])
  const [jitRequestForm, setJitRequestForm] = useState<JitAccessRequestFormState>({
    roleId: 'exception-fact-reader',
    requestedDurationMinutes: '30',
    comments: '',
  })
  const [jitRequestSubmitting, setJitRequestSubmitting] = useState(false)
  const [policyDraft, setPolicyDraft] = useState('')
  const [policySaving, setPolicySaving] = useState(false)
  const [matrixError, setMatrixError] = useState<string | null>(null)
  const [policyError, setPolicyError] = useState<string | null>(null)
  const [policyNotice, setPolicyNotice] = useState<string | null>(null)
  const [jitAccessError, setJitAccessError] = useState<string | null>(null)
  const [jitAccessNotice, setJitAccessNotice] = useState<string | null>(null)
  const [jitAccessSupportRequestContext, setJitAccessSupportRequestContext] = useState<JitAccessSupportRequestContext | null>(null)
  const [jitAccessSupportRequestError, setJitAccessSupportRequestError] = useState<string | null>(null)

  const currentWorkspaceId = normalizeWorkspaceId(auth.currentWorkspaceId)
  const activeWorkspaceRoles = useMemo(
    () => {
      if (!auth.user || !currentWorkspaceId) {
        return []
      }

      return auth.user.workspaceRoles.filter(
        (workspaceRole) => normalizeWorkspaceId(workspaceRole.workspaceId) === currentWorkspaceId
      )
    },
    [auth.user, currentWorkspaceId]
  )
  const canSubmitJitRequest = Boolean(
    auth.isAuthenticated
    && currentWorkspaceId
    && activeWorkspaceRoles.some((workspaceRole) => !isExceptionJitRole(workspaceRole.role))
  )

  // Load drift summary on component mount
  useEffect(() => {
    const loadDriftSummary = async () => {
      try {
        const summary = await getDriftSummary()
        setDriftSummary(summary)
      } catch (err) {
        console.error('Failed to load drift summary:', err)
      }
    }

    loadDriftSummary()
  }, [getDriftSummary])

  useEffect(() => {
    let cancelled = false

    const loadStatusModels = async () => {
      try {
        setMatrixError(null)
        const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
        const headers = buildAuthHeaders()

        const [ruleResponse, approvalResponse, runPlanResponse] = await Promise.all([
          fetch(`${apiBase}/governance/status-models/rule`, { headers }),
          fetch(`${apiBase}/governance/status-models/approval`, { headers }),
          fetch(`${apiBase}/governance/status-models/run_plan`, { headers }),
        ])

        if (!ruleResponse.ok) {
          throw new Error(`Unable to load rule transition matrix (${ruleResponse.status}).`)
        }
        if (!approvalResponse.ok) {
          throw new Error(`Unable to load approval transition matrix (${approvalResponse.status}).`)
        }
        if (!runPlanResponse.ok) {
          throw new Error(`Unable to load DQ run plan transition matrix (${runPlanResponse.status}).`)
        }

        const [rulePayload, approvalPayload, runPlanPayload] = await Promise.all([
          ruleResponse.json(),
          approvalResponse.json(),
          runPlanResponse.json(),
        ])
        if (cancelled) {
          return
        }

        setRuleStatusModel(normalizeStatusModel(rulePayload))
        setApprovalStatusModel(normalizeStatusModel(approvalPayload))
        setRunPlanStatusModel(normalizeStatusModel(runPlanPayload))
      } catch (error) {
        if (!cancelled) {
          setMatrixError(error instanceof Error ? error.message : 'Unable to load transition matrix.')
        }
      }
    }

    loadStatusModels()

    return () => {
      cancelled = true
    }
  }, [settings.applicationSettings?.apiBaseUrl])

  const loadJitAccessRequests = useCallback(async () => {
    try {
      setJitAccessError(null)

      if (!currentWorkspaceId) {
        throw new Error('Select an active workspace before reviewing exception-record access requests.')
      }

      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const response = await fetch(`${apiBase}/exception-fact-access-requests`, {
        headers: buildAuthHeaders(),
      })

      if (response.status === 404) {
        setJitAccessRequests([])
        return
      }

      if (!response.ok) {
        throw new Error(`Unable to load exception-record access requests (${response.status}).`)
      }

      const payload = snakeToCamel<JitAccessRequestView[]>(await response.json())
      const requests = Array.isArray(payload)
        ? payload.filter((request) => String(request.workspaceId || '').trim() === currentWorkspaceId)
        : []
      setJitAccessRequests(requests)
    } catch (error) {
      setJitAccessRequests([])
      setJitAccessError(error instanceof Error ? error.message : 'Unable to load exception-record access requests.')
    }
  }, [currentWorkspaceId, settings.applicationSettings?.apiBaseUrl])

  useEffect(() => {
    if (!isAccessRequestMode) {
      return
    }

    void loadJitAccessRequests()
  }, [isAccessRequestMode, loadJitAccessRequests])

  useEffect(() => {
    let cancelled = false

    const loadAppConfig = async () => {
      try {
        const apiBase = toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)
        const response = await fetch(`${apiBase}/app-config`, {
          headers: buildAuthHeaders(),
        })

        if (!response.ok) {
          throw new Error(`Unable to load application config (${response.status}).`)
        }

        const config = snakeToCamel<Record<string, unknown> & { statusGovernance?: GovernancePolicyDraft }>(await response.json())
        if (cancelled) {
          return
        }

        setAppConfigData(config)
        setPolicyDraft(JSON.stringify((config.statusGovernance as GovernancePolicyDraft | undefined) || {}, null, 2))
      } catch (error) {
        if (!cancelled) {
          setPolicyError(error instanceof Error ? error.message : 'Unable to load application config.')
          setAppConfigData(null)
        }
      }
    }

    loadAppConfig()

    return () => {
      cancelled = true
    }
  }, [settings.applicationSettings?.apiBaseUrl])

  const transitionLookups = useMemo(
    () => ({
      rule: buildTransitionLookup(ruleStatusModel),
      approval: buildTransitionLookup(approvalStatusModel),
      runPlan: buildTransitionLookup(runPlanStatusModel),
    }),
    [ruleStatusModel, approvalStatusModel, runPlanStatusModel]
  )

  const jitRequestTimeoutMinutes = Number((appConfigData?.exceptionFactJitRequestTimeoutMinutes as number | undefined) ?? 30)
  const jitRequestMaxDurationMinutes = Math.max(1, Number((appConfigData?.exceptionFactJitRoleMaxDurationMinutes as number | undefined) ?? 120))
  const jitRequestReason = jitRequestForm.comments.trim()
  const isJitRequestReasonValid = jitRequestReason.length >= 10

  const handleSubmitJitAccessRequest = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    setJitAccessError(null)
    setJitAccessNotice(null)
    setJitAccessSupportRequestContext(null)
    setJitAccessSupportRequestError(null)

    if (!currentWorkspaceId) {
      setJitAccessError('Select an active workspace before submitting an exception-record access request.')
      return
    }

    if (!canSubmitJitRequest) {
      setJitAccessError('An existing non-exception workspace role is required before requesting exception-record access.')
      return
    }

    if (!isJitRequestReasonValid) {
      setJitAccessError('Reason must be at least 10 characters.')
      return
    }

    const requestedDurationMinutes = Number.parseInt(jitRequestForm.requestedDurationMinutes, 10)
    if (!Number.isFinite(requestedDurationMinutes) || requestedDurationMinutes <= 0) {
      setJitAccessError('Enter a requested duration in minutes.')
      return
    }

    try {
      setJitRequestSubmitting(true)

      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const token = getAuthToken()
      const response = await fetch(`${apiBase}/exception-fact-access-requests`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          workspace_id: currentWorkspaceId,
          role_id: jitRequestForm.roleId,
          requested_duration_minutes: requestedDurationMinutes,
          comments: jitRequestForm.comments.trim(),
        }),
      })

      if (!response.ok) {
        const errorBody = await response.text().catch(() => '')
        const errorDetails = parseResponseDetail(errorBody)
        const errorMessage = formatJitAccessSubmissionError(response.status, errorDetails)

        setJitAccessSupportRequestContext({
          errorMessage,
          errorDetails,
          responseStatus: response.status,
          roleId: jitRequestForm.roleId,
          requestedDurationMinutes,
          comments: jitRequestForm.comments.trim(),
        })
        setJitAccessError(errorMessage)
        return
      }

      await response.json().catch(() => null)
      setJitAccessNotice('Exception-record access request submitted successfully.')
      setJitRequestForm((prev) => ({ ...prev, comments: '' }))
      await loadJitAccessRequests()
    } catch (error) {
      const errorMessage = error instanceof Error ? normalizeValidationUiText(error.message) : 'Failed to submit exception-record access request.'
      setJitAccessError(errorMessage)
      setJitAccessSupportRequestContext({
        errorMessage,
        errorDetails: errorMessage,
        responseStatus: 0,
        roleId: jitRequestForm.roleId,
        requestedDurationMinutes,
        comments: jitRequestForm.comments.trim(),
      })
    } finally {
      setJitRequestSubmitting(false)
    }
  }, [canSubmitJitRequest, currentWorkspaceId, isJitRequestReasonValid, jitRequestForm.comments, jitRequestForm.requestedDurationMinutes, jitRequestForm.roleId, loadJitAccessRequests, settings.applicationSettings?.apiBaseUrl])

  const clearJitAccessErrors = useCallback(() => {
    setJitAccessError(null)
    setJitAccessSupportRequestContext(null)
    setJitAccessSupportRequestError(null)
  }, [])

  const supportRequestAction = jitAccessSupportRequestContext && settings.applicationSettings?.apiBaseUrl ? (
    <div className="jit-access-support-request">
      <p className="settings-hint" style={{ margin: '0 0 12px' }}>
        Request assistance and we will include the exact backend error with your request.
      </p>
      <SupportRequestFlow
        apiBaseUrl={settings.applicationSettings.apiBaseUrl}
        buttonLabel="Request assistance"
        createRequestBody={() => ({
          title: 'Exception-record access request submission failed',
          message: `Exception-record access request failed: ${jitAccessSupportRequestContext.errorMessage}`,
          source: 'access-requests-dashboard',
          workspaceId: currentWorkspaceId,
          roleId: jitAccessSupportRequestContext.roleId,
          requestedDurationMinutes: jitAccessSupportRequestContext.requestedDurationMinutes,
          comments: jitAccessSupportRequestContext.comments,
          details: {
            error: jitAccessSupportRequestContext.errorDetails,
            responseStatus: jitAccessSupportRequestContext.responseStatus,
          },
        })}
        onSuccess={() => setJitAccessSupportRequestError(null)}
        onError={setJitAccessSupportRequestError}
      />
      {jitAccessSupportRequestError ? (
        <div style={{ marginTop: 12 }}>
          <StatusBanner
            variant="error"
            message={jitAccessSupportRequestError}
            onDismiss={() => setJitAccessSupportRequestError(null)}
          />
        </div>
      ) : null}
    </div>
  ) : null

  const jitRequestStatusCounts = useMemo(() => {
    const counts = {
      total: 0,
      pending: 0,
      approved: 0,
      declined: 0,
      timedOut: 0,
    }

    for (const request of jitAccessRequests) {
      const status = String(request.status || '').trim().toLowerCase()
      if (!status) {
        continue
      }

      counts.total += 1
      if (status === 'pending') {
        counts.pending += 1
      } else if (status === 'approved') {
        counts.approved += 1
      } else if (status === 'timed_out') {
        counts.timedOut += 1
      } else if (status === 'rejected' || status === 'revoked') {
        counts.declined += 1
      }
    }

    return counts
  }, [jitAccessRequests])

  if (isAccessRequestMode) {
    return (
      <AppPageShell className="governance-dashboard governance-dashboard-access-requests">
        <AppPageHeader
          className="governance-header"
          title={<> <AppIcon name="shield-check" /> Access Requests </>}
          description="Submit temporary exception-record access for the active workspace and review request status in one place."
        />

        <div className="governance-summary">
          <div className="summary-card summary-primary">
            <div className="card-icon">🗂️</div>
            <div className="card-content">
              <div className="card-label">Total Requests</div>
              <div className="card-value">{jitRequestStatusCounts.total}</div>
              <div className="card-subtitle">Current workspace exception-record access requests</div>
            </div>
          </div>

          <div className="summary-card summary-warning">
            <div className="card-icon">⏳</div>
            <div className="card-content">
              <div className="card-label">Pending</div>
              <div className="card-value">{jitRequestStatusCounts.pending}</div>
              <div className="card-subtitle">Waiting for workspace admin review</div>
            </div>
          </div>

          <div className="summary-card summary-info">
            <div className="card-icon">✅</div>
            <div className="card-content">
              <div className="card-label">Approved / Declined / Timed out</div>
              <div className="card-value">
                {jitRequestStatusCounts.approved} / {jitRequestStatusCounts.declined} / {jitRequestStatusCounts.timedOut}
              </div>
              <div className="card-subtitle">Status history for completed requests</div>
            </div>
          </div>
        </div>

        <div className="governance-section">
          <div className="section-heading-with-action">
            <div>
              <h2 className="section-title">
                <AppIcon name="shield-check" />
                Request or review access
              </h2>
              <p className="section-copy">
                Request a temporary exception-record role for the active workspace and track its review status here.
              </p>
            </div>
            <div className="transition-policy-badge">
              <span>Timeout</span>
              <strong>{jitRequestTimeoutMinutes} min</strong>
            </div>
          </div>

          <div className="jit-access-panel">
            <div className="jit-access-panel-header">
              <div>
                <h3>Submit a request</h3>
                <p>
                  Choose the temporary exception-record role, specify the duration, and capture the request reason.
                </p>
              </div>
              <div className="transition-policy-badge">
                <span>Max duration</span>
                <strong>{jitRequestMaxDurationMinutes} min</strong>
              </div>
            </div>

            {!canSubmitJitRequest ? (
              <div className="transition-policy-alert">
                A non-exception workspace role is required before submitting an exception-record request.
              </div>
            ) : null}

            <form className="jit-access-form" onSubmit={handleSubmitJitAccessRequest}>
              <div className="jit-access-form-grid">
                <AppSelect
                  id="jit-access-role"
                  label="Role to request"
                  value={jitRequestForm.roleId}
                  onChange={(value) => setJitRequestForm((prev) => ({ ...prev, roleId: value as JitAccessRequestFormState['roleId'] }))}
                  options={JIT_ACCESS_ROLE_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
                  placeholderLabel="Choose a role to request"
                  hint={JIT_ACCESS_ROLE_OPTIONS.find((option) => option.value === jitRequestForm.roleId)?.description}
                  disabled={!canSubmitJitRequest || jitRequestSubmitting}
                />

                <label className="jit-access-field" htmlFor="jit-access-duration">
                  <span>Requested duration (minutes)</span>
                  <input
                    id="jit-access-duration"
                    type="number"
                    min={1}
                    max={jitRequestMaxDurationMinutes}
                    value={jitRequestForm.requestedDurationMinutes}
                    onChange={(event) => setJitRequestForm((prev) => ({ ...prev, requestedDurationMinutes: event.target.value }))}
                    disabled={!canSubmitJitRequest || jitRequestSubmitting}
                  />
                  <small>Approvals are capped by the app setting.</small>
                </label>
              </div>

              <label className="jit-access-field jit-access-field-wide" htmlFor="jit-access-comments">
                <span>Reason</span>
                <textarea
                  id="jit-access-comments"
                  rows={3}
                  value={jitRequestForm.comments}
                  onChange={(event) => setJitRequestForm((prev) => ({ ...prev, comments: event.target.value }))}
                  disabled={!canSubmitJitRequest || jitRequestSubmitting}
                  aria-invalid={jitRequestForm.comments.trim().length > 0 && !isJitRequestReasonValid}
                />
                <small>
                  Capture why the temporary access is needed. Minimum 10 characters. {jitRequestReason.length}/10 characters used.
                </small>
              </label>

              <div className="jit-access-form-actions">
                <button type="submit" className="jit-access-submit-button" disabled={!canSubmitJitRequest || jitRequestSubmitting}>
                  {jitRequestSubmitting ? 'Submitting...' : 'Submit request'}
                </button>
              </div>
            </form>

            <div aria-live="polite" aria-atomic="true">
              {jitAccessNotice ? <div className="transition-policy-notice" role="status">{jitAccessNotice}</div> : null}
              {jitAccessError ? (
                <div style={{ marginTop: 16 }}>
                  <StatusBanner
                    variant="error"
                    message={jitAccessError}
                    onDismiss={clearJitAccessErrors}
                  />
                </div>
              ) : null}
              {supportRequestAction ? (
                <div style={{ marginTop: 16 }}>
                  {supportRequestAction}
                </div>
              ) : null}
            </div>
          </div>

          <div className="transition-matrix-notes">
            <div className="transition-matrix-note">
              <strong>pending</strong>
              <span>The request is waiting for workspace admin review.</span>
            </div>
            <div className="transition-matrix-note">
              <strong>approved</strong>
              <span>The temporary exception-record role is granted for the approved duration.</span>
            </div>
            <div className="transition-matrix-note">
              <strong>declined</strong>
              <span>The request was rejected or revoked before it became active.</span>
            </div>
            <div className="transition-matrix-note">
              <strong>timed_out</strong>
              <span>The request was not handled before the configured timeout elapsed.</span>
            </div>
          </div>

          {jitAccessRequests.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">🗂️</div>
              <h3>No exception-record requests yet</h3>
              <p>Your access requests will appear here with their current status.</p>
            </div>
          ) : (
            <div className="transition-matrix-table-wrap">
              <table className="transition-matrix-table">
                <thead>
                  <tr>
                    <th>Workspace</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Requested</th>
                    <th>Reviewed</th>
                  </tr>
                </thead>
                <tbody>
                  {jitAccessRequests.map((request) => (
                    <tr key={request.id}>
                      <th scope="row">
                        <div className="transition-matrix-row-label">
                          <span>{request.workspaceId}</span>
                          <span className="transition-matrix-row-value">{request.requesterId}</span>
                        </div>
                      </th>
                      <td>{request.roleId}</td>
                      <td>
                        <span className={`transition-matrix-pill ${['rejected', 'revoked', 'timed_out'].includes(String(request.status || '').trim().toLowerCase()) ? 'transition-matrix-pill-terminal' : ''}`}>
                          {formatJitAccessStatus(request.status)}
                        </span>
                      </td>
                      <td>{request.requestedAt}</td>
                      <td>{request.reviewedAt || 'Pending review'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </AppPageShell>
    )
  }

  const renderStatusMatrix = (title: string, model: GovernanceStatusModel | null, entityKey: 'rule' | 'approval' | 'runPlan') => {
    if (!model) {
      return (
        <div className="transition-matrix-card transition-matrix-card-empty">
          <h3>{title}</h3>
          <p>Loading policy...</p>
        </div>
      )
    }

    const lookup = transitionLookups[entityKey]

    return (
      <div className="transition-matrix-card">
        <div className="transition-matrix-card-header">
          <div>
            <h3>{title}</h3>
            <p>{model.statuses.length} statuses, {model.transitions.length} defined transitions</p>
          </div>
          <div className="transition-matrix-source">
            <span className="transition-matrix-source-label">Source</span>
            <span className="transition-matrix-source-value">/app-config</span>
          </div>
        </div>

        <div className="transition-matrix-table-wrap">
          <table className="transition-matrix-table">
            <thead>
              <tr>
                <th>From / To</th>
                {model.statuses.map((status) => (
                  <th key={status.value}>
                    <div className="transition-matrix-column-label">
                      <span>{status.label}</span>
                      <span className="transition-matrix-column-value">{status.value}</span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {model.statuses.map((fromStatus) => (
                <tr key={fromStatus.value}>
                  <th scope="row">
                    <div className="transition-matrix-row-label">
                      <span>{fromStatus.label}</span>
                      <span className="transition-matrix-row-value">{fromStatus.value}</span>
                      {fromStatus.isInitial ? <span className="transition-matrix-pill">Initial</span> : null}
                      {fromStatus.isTerminal ? <span className="transition-matrix-pill transition-matrix-pill-terminal">Terminal</span> : null}
                    </div>
                  </th>
                  {model.statuses.map((toStatus) => {
                    const transition = lookup.get(`${fromStatus.value} -> ${toStatus.value}`)
                    return (
                      <td key={`${fromStatus.value}-${toStatus.value}`} className={transition ? 'transition-matrix-cell-enabled' : 'transition-matrix-cell-disabled'}>
                        {transition ? (
                          <div className="transition-matrix-cell-content">
                            <span className="transition-matrix-label">{transition.label}</span>
                            {transition.requiredAnyScopes.length > 0 ? (
                              <span className="transition-matrix-scopes">{transition.requiredAnyScopes.join(', ')}</span>
                            ) : (
                              <span className="transition-matrix-scopes transition-matrix-scopes-empty">No scope gate</span>
                            )}
                          </div>
                        ) : (
                          <span className="transition-matrix-empty">—</span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {model.statuses.some((status) => status.description) ? (
          <div className="transition-matrix-notes">
            {model.statuses
              .filter((status) => status.description)
              .map((status) => (
                <div key={`${status.value}-description`} className="transition-matrix-note">
                  <strong>{status.label}</strong>
                  <span>{status.description}</span>
                </div>
              ))}
          </div>
        ) : null}
      </div>
    )
  }

  const handlePolicySave = async () => {
    if (!appConfigData) {
      return
    }

    try {
      setPolicySaving(true)
      setPolicyError(null)
      setPolicyNotice(null)

      const parsedPolicy = policyDraft.trim() ? (JSON.parse(policyDraft) as GovernancePolicyDraft) : {}
      const payload = camelToSnake({
        ...appConfigData,
        statusGovernance: parsedPolicy,
      })

      const apiBase = toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)
      const token = getAuthToken()
      const response = await fetch(`${apiBase}/app-config`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const errorText = await response.text().catch(() => '')
        throw new Error(
          `Failed to save transition policy (${response.status})${errorText ? `: ${errorText}` : ''}`
        )
      }

      const persistedConfig = snakeToCamel<Record<string, unknown> & { statusGovernance?: GovernancePolicyDraft }>(await response.json())
      setAppConfigData(persistedConfig)
      setPolicyDraft(JSON.stringify((persistedConfig.statusGovernance as GovernancePolicyDraft | undefined) || {}, null, 2))
      setPolicyNotice('Transition policy saved successfully.')
    } catch (error) {
      setPolicyError(error instanceof Error ? error.message : 'Failed to save transition policy.')
    } finally {
      setPolicySaving(false)
    }
  }

  if (driftError) {
    return (
      <div className="governance-dashboard-error">
        <div className="error-icon">⚠️</div>
        <h2>Unable to load Governance Dashboard</h2>
        <p>{driftError}</p>
      </div>
    )
  }

  if (driftSummary && (!driftSummary.byDriftType || typeof driftSummary.byDriftType !== 'object')) {
    return (
      <div className="governance-dashboard-error">
        <div className="error-icon">⚠️</div>
        <h2>Unable to load Governance Dashboard</h2>
        <p>Unexpected drift summary payload: missing byDriftType.</p>
      </div>
    )
  }

  return (
    <AppPageShell className="governance-dashboard">
      <AppPageHeader
        className="governance-header"
        title={<> <AppIcon name="pie-chart" /> Governance Overview </>}
        description="Review governance policy, approval impact, and workspace-level drift signal."
      />

      {/* Drift Summary Cards */}
      <div className="governance-summary">
        <div className="summary-card summary-primary">
          <div className="card-icon"><AppIcon name="pie-chart" /></div>
          <div className="card-content">
            <div className="card-label">Rules with Drift</div>
            <div className="card-value">{driftSummary?.rulesWithDrift || 0}</div>
            <div className="card-subtitle">of {driftSummary?.totalRulesChecked || 0} total rules</div>
          </div>
        </div>

        <div className="summary-card summary-warning">
          <div className="card-icon"><AppIcon name="warning" /></div>
          <div className="card-content">
            <div className="card-label">Total Drifts Detected</div>
            <div className="card-value">{driftSummary?.totalDriftsDetected || 0}</div>
            <div className="card-critical">
              {driftSummary?.criticalDrifts || 0} critical
            </div>
          </div>
        </div>

        <div className="summary-card summary-info">
          <div className="card-icon"><AppIcon name="info-circle" /></div>
          <div className="card-content">
            <div className="card-label">Drift Types</div>
            <div className="card-value">{Object.keys(driftSummary?.byDriftType || {}).length}</div>
            <div className="card-subtitle">
              {Object.entries(driftSummary?.byDriftType || {})
                .slice(0, 3)
                .map(([type, count]) => `${type} (${count})`)
                .join(', ')}
            </div>
          </div>
        </div>
      </div>

      {onNavigate && (
        <div className="governance-actions">
          <div className="action-info">
            <span className="action-icon"><AppIcon name="arrow-right" /></span>
            <span className="action-text">
              Catalog drift review and revalidation now live under Rule Quality.
            </span>
          </div>
          <SecondaryButton onClick={() => onNavigate('rule-quality-drift')}>
            Open Catalog Drift
          </SecondaryButton>
        </div>
      )}

      {/* Transition Policy */}
      <div className="governance-section governance-section-transition-policy">
        <div className="section-heading-with-action">
          <div>
            <h2 className="section-title">
              <AppIcon name="table" />
              Status Transition Matrix
            </h2>
            <p className="section-copy">
              The API enforces these transitions directly. Admins can edit the policy in app-config.
            </p>
          </div>
          <div className="transition-policy-badge">
            <span>Live policy</span>
            <strong>/app-config</strong>
          </div>
        </div>

        {matrixError ? <div className="transition-policy-alert">{matrixError}</div> : null}

        <div className="transition-matrix-grid">
          {renderStatusMatrix('Rule lifecycle', ruleStatusModel, 'rule')}
          {renderStatusMatrix('Approval lifecycle', approvalStatusModel, 'approval')}
          {renderStatusMatrix('DQ run plan lifecycle', runPlanStatusModel, 'runPlan')}
        </div>

        <div className="transition-policy-editor">
          <div className="transition-policy-editor-header">
            <div>
              <h3>Edit policy JSON</h3>
              <p>
                Save the app-config object to change the allowed transitions. Invalid payloads are rejected.
              </p>
            </div>
            <div className="transition-policy-editor-actions">
              <SecondaryButton
                onClick={() => {
                  setPolicyDraft(JSON.stringify((appConfigData?.statusGovernance as GovernancePolicyDraft | undefined) || {}, null, 2))
                  setPolicyError(null)
                  setPolicyNotice(null)
                }}
                disabled={!appConfigData || policySaving}
              >
                Reset
              </SecondaryButton>
              <PrimaryButton onClick={handlePolicySave} disabled={!appConfigData || policySaving}>
                {policySaving ? 'Saving...' : 'Save Policy'}
              </PrimaryButton>
            </div>
          </div>

          <textarea
            className="transition-policy-textarea"
            value={policyDraft}
            onChange={(event) => setPolicyDraft(event.target.value)}
            spellCheck={false}
            aria-label="Transition policy JSON"
          />

          {policyNotice ? <div className="transition-policy-notice">{policyNotice}</div> : null}
          {policyError ? <div className="transition-policy-alert transition-policy-alert-editor">{policyError}</div> : null}
        </div>
      </div>

      <div className="governance-content">
        <div className="governance-section">
            <h2 className="section-title">
              <AppIcon name="warning" />
            Drift Summary
          </h2>

          {(driftSummary?.rulesWithDrift || 0) === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><AppIcon name="check-circle" /></div>
              <h3>No drift detected</h3>
              <p>All rules are aligned with the current catalog definitions.</p>
            </div>
          ) : (
            <p className="section-copy">
              {driftSummary?.rulesWithDrift || 0} rules currently show catalog drift. Use Rule Quality → Catalog Drift for affected-rule inspection, comparison details, and revalidation.
            </p>
          )}
        </div>

        {/* Drift Type Breakdown */}
        {driftSummary && Object.keys(driftSummary.byDriftType || {}).length > 0 && (
          <div className="governance-section">
            <h2 className="section-title">
              <AppIcon name="line-chart" />
              Drift Type Breakdown
            </h2>
            <div className="drift-type-breakdown">
              {Object.entries(driftSummary.byDriftType || {}).map(([driftType, count]) => (
                <div key={driftType} className="drift-type-item">
                  <div className="drift-type-name">{driftType.replace(/_/g, ' ')}</div>
                  <div className="drift-type-bar">
                    <div
                      className="drift-type-bar-fill"
                      style={{
                        width: `${((count as number) / Math.max(...Object.values(driftSummary.byDriftType || { [driftType]: count as number }))) * 100}%`,
                      }}
                    />
                  </div>
                  <div className="drift-type-count">{count}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      {driftLoading && (
        <div className="governance-loading">
          <div className="spinner" />
          <p>Loading governance data...</p>
        </div>
      )}
    </AppPageShell>
  )
}
