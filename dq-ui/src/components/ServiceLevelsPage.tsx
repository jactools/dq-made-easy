import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth, useSettings } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { snakeToCamel } from '../utils/caseConverters'
import { AppBanner, AppButton, AppInput, AppSelect, AppTextarea } from './app-primitives'
import './ServiceLevelsPage.css'

type ServiceLevelAdherence = {
  metricValue?: number | null
  thresholdValue?: number | null
  thresholdOperator?: string
  observedEventCount?: number
  compliantEventCount?: number
  nonCompliantEventCount?: number
  complianceRatePct?: number | null
  currentValue?: number | null
  currentObservedAt?: string | null
  latestObservedAt?: string | null
  meetsTarget?: boolean | null
  summary?: string | null
}

type ServiceLevelDefinition = {
  id: string
  workspaceId?: string | null
  name: string
  description?: string | null
  scopeKind: string
  scopeId: string
  metricKind: string
  thresholdValue: number
  thresholdOperator: string
  lookbackAmount: number
  lookbackUnit: string
  lifecycleStatus?: string | null
  approvalStatus?: string | null
  requestedBy?: string | null
  requestedAt?: string | null
  reviewedBy?: string | null
  reviewedAt?: string | null
  itsmSystem?: string | null
  itsmTicketId?: string | null
  itsmTicketNumber?: string | null
  itsmTicketUrl?: string | null
  createdAt?: string | null
  updatedAt?: string | null
  adherence?: ServiceLevelAdherence | null
}

type ServiceLevelsSummary = {
  workspaceId?: string | null
  definitions: ServiceLevelDefinition[]
  totalDefinitions: number
  activeDefinitions: number
  draftDefinitions: number
  approvedDefinitions: number
  deprecatedDefinitions: number
  compliantDefinitions: number
  atRiskDefinitions: number
}

type ServiceLevelBreach = {
  definitionId: string
  definitionName: string
  scopeKind: string
  scopeId: string
  metricKind: string
  thresholdValue: number | string
  thresholdOperator: string
  currentValue?: number | null
  observedEventCount: number
  emittedAt: string
  correlationId: string
  severity: string
  summary?: string | null
}

type ServiceLevelEvaluation = {
  workspaceId?: string | null
  evaluatedAt: string
  evaluatedDefinitions: number
  breachedDefinitions: number
  breachEventsRecorded: number
  breaches: ServiceLevelBreach[]
}

type ServiceLevelFormState = {
  name: string
  description: string
  scopeKind: string
  scopeId: string
  metricKind: string
  thresholdValue: string
  thresholdOperator: string
  lookbackAmount: string
  lookbackUnit: string
}

const SCOPE_KIND_OPTIONS = [
  { value: 'dataset', label: 'Dataset' },
  { value: 'domain', label: 'Domain' },
  { value: 'rule', label: 'Rule' },
  { value: 'data_product', label: 'Data product' },
]

const METRIC_KIND_OPTIONS = [
  { value: 'quality_score', label: 'Quality score' },
  { value: 'critical_rule_pass_rate', label: 'Critical rule pass rate' },
  { value: 'incident_rate', label: 'Incident rate' },
  { value: 'freshness', label: 'Freshness' },
  { value: 'validity', label: 'Validity' },
]

const LOOKBACK_UNIT_OPTIONS = [
  { value: 'day', label: 'Days' },
  { value: 'hour', label: 'Hours' },
  { value: 'week', label: 'Weeks' },
]

const THRESHOLD_OPERATOR_OPTIONS = [
  { value: 'gte', label: 'Greater than or equal' },
  { value: 'lte', label: 'Less than or equal' },
]

const formatPercent = (value?: number | null): string => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'No adherence yet'
  }

  return `${Math.round(Number(value))}%`
}

const formatDateTime = (value?: string | null): string => {
  if (!value) {
    return 'Not recorded'
  }

  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

const formatLabel = (value: string): string => {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

const createBlankForm = (): ServiceLevelFormState => ({
  name: '',
  description: '',
  scopeKind: 'dataset',
  scopeId: '',
  metricKind: 'quality_score',
  thresholdValue: '90',
  thresholdOperator: 'gte',
  lookbackAmount: '30',
  lookbackUnit: 'day',
})

const definitionToForm = (definition: ServiceLevelDefinition): ServiceLevelFormState => ({
  name: definition.name || '',
  description: definition.description || '',
  scopeKind: definition.scopeKind || 'dataset',
  scopeId: definition.scopeId || '',
  metricKind: definition.metricKind || 'quality_score',
  thresholdValue: String(definition.thresholdValue ?? 90),
  thresholdOperator: definition.thresholdOperator || 'gte',
  lookbackAmount: String(definition.lookbackAmount ?? 30),
  lookbackUnit: definition.lookbackUnit || 'day',
})

const buildErrorMessage = async (response: Response, fallbackMessage: string): Promise<string> => {
  try {
    const payload = await response.json()
    const detail = payload?.detail
    if (typeof detail === 'string') {
      return detail
    }
    if (detail && typeof detail === 'object') {
      return detail.message || detail.error || fallbackMessage
    }
    return payload?.message || fallbackMessage
  } catch {
    return fallbackMessage
  }
}

export const ServiceLevelsPage: React.FC = () => {
  const auth = useAuth()
  const settings = useSettings()
  const currentWorkspaceId = auth.currentWorkspaceId || ''
  const apiBaseUrl = settings.applicationSettings?.apiBaseUrl || ''
  const [summary, setSummary] = useState<ServiceLevelsSummary | null>(null)
  const [selectedDefinitionId, setSelectedDefinitionId] = useState<string | null>(null)
  const [formState, setFormState] = useState<ServiceLevelFormState>(() => createBlankForm())
  const [approvalComments, setApprovalComments] = useState('Review completed in dq-made-easy.')
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isApproving, setIsApproving] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  const selectedDefinition = useMemo(() => {
    return summary?.definitions.find((definition) => definition.id === selectedDefinitionId) || null
  }, [selectedDefinitionId, summary])

  const statusCounts = useMemo(() => {
    return {
      total: summary?.totalDefinitions || 0,
      active: summary?.activeDefinitions || 0,
      approved: summary?.approvedDefinitions || 0,
      draft: summary?.draftDefinitions || 0,
      compliant: summary?.compliantDefinitions || 0,
      atRisk: summary?.atRiskDefinitions || 0,
    }
  }, [summary])

  const loadServiceLevels = useCallback(async (signal?: AbortSignal) => {
    if (!apiBaseUrl) {
      setSummary(null)
      setErrorMessage('The API base URL is not configured.')
      setIsLoading(false)
      return
    }

    if (!currentWorkspaceId) {
      setSummary(null)
      setErrorMessage('Select a workspace before viewing service levels.')
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    setErrorMessage(null)

    try {
      const token = getAuthToken()
      const requestUrl = `${toApiGroupV1Base('rulebuilder', apiBaseUrl)}/service-levels?workspace_id=${encodeURIComponent(currentWorkspaceId)}`
      const response = await fetch(requestUrl, {
        method: 'GET',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        signal,
      })

      if (!response.ok) {
        throw new Error(await buildErrorMessage(response, 'Unable to load service levels.'))
      }

      const payload = snakeToCamel<ServiceLevelsSummary>(await response.json())
      setSummary(payload)
      setSelectedDefinitionId((currentSelection) => {
        if (currentSelection && payload.definitions.some((definition) => definition.id === currentSelection)) {
          return currentSelection
        }
        return payload.definitions[0]?.id || null
      })
    } catch (error) {
      if (signal?.aborted) {
        return
      }
      setSummary(null)
      setErrorMessage(error instanceof Error ? error.message : 'Unable to load service levels.')
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false)
      }
    }
  }, [apiBaseUrl, currentWorkspaceId])

  useEffect(() => {
    const controller = new AbortController()
    void loadServiceLevels(controller.signal)
    return () => controller.abort()
  }, [loadServiceLevels, reloadToken])

  useEffect(() => {
    if (!currentWorkspaceId) {
      setFormState(createBlankForm())
      return
    }

    if (selectedDefinition) {
      setFormState(definitionToForm(selectedDefinition))
      setApprovalComments(selectedDefinition.approvalStatus === 'approved'
        ? 'Review updated and synchronized with ITSM.'
        : 'Review completed in dq-made-easy.')
      return
    }

    setFormState(createBlankForm())
    setApprovalComments('Review completed in dq-made-easy.')
  }, [currentWorkspaceId, selectedDefinition])

  const handleFieldChange = useCallback((field: keyof ServiceLevelFormState, value: string) => {
    setFormState((current) => ({ ...current, [field]: value }))
  }, [])

  const handleSelectDefinition = useCallback((definitionId: string) => {
    setSelectedDefinitionId(definitionId)
  }, [])

  const handleCreateNew = useCallback(() => {
    setSelectedDefinitionId(null)
    setErrorMessage(null)
    setStatusMessage('Preparing a new SLA/SLO draft for the active workspace.')
    setFormState(createBlankForm())
    setApprovalComments('Review completed in dq-made-easy.')
  }, [])

  const persistDefinition = useCallback(async (nextDefinitionId?: string) => {
    if (!apiBaseUrl) {
      throw new Error('The API base URL is not configured.')
    }
    if (!currentWorkspaceId) {
      throw new Error('Select a workspace before saving service levels.')
    }

    const token = getAuthToken()
    const payload = {
      workspace_id: currentWorkspaceId,
      name: formState.name.trim(),
      description: formState.description.trim() || null,
      scope_kind: formState.scopeKind.trim(),
      scope_id: formState.scopeId.trim(),
      metric_kind: formState.metricKind.trim(),
      threshold_value: Number(formState.thresholdValue),
      threshold_operator: formState.thresholdOperator.trim(),
      lookback_amount: Number(formState.lookbackAmount),
      lookback_unit: formState.lookbackUnit.trim(),
    }

    const endpoint = nextDefinitionId
      ? `${toApiGroupV1Base('rulebuilder', apiBaseUrl)}/service-levels/${nextDefinitionId}`
      : `${toApiGroupV1Base('rulebuilder', apiBaseUrl)}/service-levels`

    const response = await fetch(endpoint, {
      method: nextDefinitionId ? 'PUT' : 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      throw new Error(await buildErrorMessage(response, 'Unable to save the service level.'))
    }

    const saved = snakeToCamel<ServiceLevelDefinition>(await response.json())
    setSelectedDefinitionId(saved.id)
    setStatusMessage(`${saved.name} was saved in dq-made-easy.`)
    setReloadToken((current) => current + 1)
    return saved
  }, [apiBaseUrl, currentWorkspaceId, formState])

  const handleSave = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setErrorMessage(null)
    setStatusMessage(null)
    setIsSaving(true)

    try {
      if (!formState.name.trim()) {
        throw new Error('Enter a service level name.')
      }
      if (!formState.scopeId.trim()) {
        throw new Error('Enter the scope identifier.')
      }
      if (!Number.isFinite(Number(formState.thresholdValue))) {
        throw new Error('Enter a numeric threshold value.')
      }
      if (!Number.isFinite(Number(formState.lookbackAmount))) {
        throw new Error('Enter a numeric lookback amount.')
      }

      await persistDefinition(selectedDefinitionId || undefined)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to save the service level.')
    } finally {
      setIsSaving(false)
    }
  }, [formState.lookbackAmount, formState.name, formState.scopeId, formState.thresholdValue, persistDefinition, selectedDefinitionId])

  const handleApprove = useCallback(async () => {
    if (!selectedDefinitionId) {
      setErrorMessage('Select a draft service level before approving it.')
      return
    }

    setErrorMessage(null)
    setStatusMessage(null)
    setIsApproving(true)

    try {
      if (!apiBaseUrl) {
        throw new Error('The API base URL is not configured.')
      }
      if (!currentWorkspaceId) {
        throw new Error('Select a workspace before approving service levels.')
      }

      const token = getAuthToken()
      const response = await fetch(`${toApiGroupV1Base('rulebuilder', apiBaseUrl)}/service-levels/${selectedDefinitionId}/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ comments: approvalComments.trim() }),
      })

      if (!response.ok) {
        throw new Error(await buildErrorMessage(response, 'Unable to approve the service level.'))
      }

      const approved = snakeToCamel<ServiceLevelDefinition>(await response.json())
      setSelectedDefinitionId(approved.id)
      setStatusMessage(`${approved.name} was approved and synchronized to ITSM ticket ${approved.itsmTicketNumber || approved.itsmTicketId || 'pending'}.`)
      setReloadToken((current) => current + 1)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to approve the service level.')
    } finally {
      setIsApproving(false)
    }
  }, [approvalComments, apiBaseUrl, currentWorkspaceId, selectedDefinitionId])

  const handleEvaluateBreaches = useCallback(async () => {
    setErrorMessage(null)
    setStatusMessage(null)

    try {
      if (!apiBaseUrl) {
        throw new Error('The API base URL is not configured.')
      }
      if (!currentWorkspaceId) {
        throw new Error('Select a workspace before evaluating breaches.')
      }

      const token = getAuthToken()
      const requestUrl = `${toApiGroupV1Base('rulebuilder', apiBaseUrl)}/service-levels/evaluate?workspace_id=${encodeURIComponent(currentWorkspaceId)}`
      const response = await fetch(requestUrl, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })

      if (!response.ok) {
        throw new Error(await buildErrorMessage(response, 'Unable to evaluate service level breaches.'))
      }

      const result = snakeToCamel<ServiceLevelEvaluation>(await response.json())
      setStatusMessage(
        result.breachEventsRecorded > 0
          ? `Recorded ${result.breachEventsRecorded} breach event${result.breachEventsRecorded === 1 ? '' : 's'} across ${result.breachedDefinitions} definition${result.breachedDefinitions === 1 ? '' : 's'}.`
          : 'No SLA/SLO breaches were recorded for the current workspace.'
      )
      setReloadToken((current) => current + 1)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to evaluate service level breaches.')
    }
  }, [apiBaseUrl, currentWorkspaceId])

  const currentApprovalState = selectedDefinition
    ? `${formatLabel(selectedDefinition.lifecycleStatus || 'draft')} · ${formatLabel(selectedDefinition.approvalStatus || 'draft')}`
    : 'Draft'

  return (
    <div className="service-levels-page">
      <section className="service-levels-hero">
        <div>
          <p className="service-levels-kicker">Operations</p>
          <h1>Service levels</h1>
          <p className="service-levels-intro">
            Define the SLA/SLO contract in dq-made-easy, approve it into ITSM, and track adherence from the stored result history.
          </p>
        </div>
        <div className="service-levels-hero-meta">
          <div>
            <span className="service-levels-meta-label">Workspace</span>
            <strong>{currentWorkspaceId || 'Select a workspace'}</strong>
          </div>
          <div>
            <span className="service-levels-meta-label">Selected definition</span>
            <strong>{selectedDefinition?.name || 'New draft'}</strong>
          </div>
        </div>
      </section>

      <section className="service-levels-stats" aria-label="Service level summary">
        <article className="service-level-stat-card">
          <span>Total</span>
          <strong>{statusCounts.total}</strong>
        </article>
        <article className="service-level-stat-card">
          <span>Active</span>
          <strong>{statusCounts.active}</strong>
        </article>
        <article className="service-level-stat-card">
          <span>Approved</span>
          <strong>{statusCounts.approved}</strong>
        </article>
        <article className="service-level-stat-card">
          <span>Compliant</span>
          <strong>{statusCounts.compliant}</strong>
        </article>
        <article className="service-level-stat-card">
          <span>At risk</span>
          <strong>{statusCounts.atRisk}</strong>
        </article>
      </section>

      {errorMessage && <AppBanner variant="error" className="service-levels-banner">{errorMessage}</AppBanner>}
      {statusMessage && <AppBanner variant="success" className="service-levels-banner">{statusMessage}</AppBanner>}

      {!apiBaseUrl && <div className="service-levels-empty-state">Configure the API base URL to load service levels.</div>}
      {apiBaseUrl && !currentWorkspaceId && <div className="service-levels-empty-state">Select a workspace to manage service levels.</div>}

      {apiBaseUrl && currentWorkspaceId && (
        <div className="service-levels-layout">
          <section className="service-levels-list-panel">
            <div className="service-levels-panel-header">
              <div>
                <p className="service-levels-panel-label">Definitions</p>
                <h2>Saved service levels</h2>
              </div>
              <div className="service-levels-panel-actions">
                <AppButton variant="secondary" type="button" onClick={handleCreateNew} disabled={isLoading}>New draft</AppButton>
                <AppButton variant="secondary" type="button" onClick={() => setReloadToken((current) => current + 1)} disabled={isLoading}>Reload</AppButton>
              </div>
            </div>

            {isLoading ? (
              <div className="service-levels-empty-state">Loading service levels from the backend…</div>
            ) : summary && summary.definitions.length === 0 ? (
              <div className="service-levels-empty-state">No service levels exist in this workspace yet. Create the first draft to get started.</div>
            ) : (
              <div className="service-levels-card-list">
                {summary?.definitions.map((definition) => {
                  const adherence = definition.adherence
                  const isSelected = definition.id === selectedDefinitionId
                  return (
                    <button
                      key={definition.id}
                      type="button"
                      className={`service-level-card${isSelected ? ' selected' : ''}`}
                      onClick={() => handleSelectDefinition(definition.id)}
                    >
                      <div className="service-level-card-topline">
                        <strong>{definition.name}</strong>
                        <span className={`service-level-pill tone-${(definition.lifecycleStatus || 'draft').toLowerCase()}`}>{formatLabel(definition.lifecycleStatus || 'draft')}</span>
                      </div>
                      <div className="service-level-card-metadata">
                        <span>{formatLabel(definition.scopeKind)} / {definition.scopeId}</span>
                        <span>{formatLabel(definition.metricKind)} · threshold {definition.thresholdOperator} {definition.thresholdValue}</span>
                      </div>
                      <div className="service-level-card-metadata">
                        <span>Status: {formatLabel(definition.approvalStatus || 'draft')}</span>
                        <span>Updated {formatDateTime(definition.updatedAt || definition.createdAt)}</span>
                      </div>
                      <div className="service-level-card-adherence">
                        <span>{adherence?.summary || 'No adherence summary yet'}</span>
                        <strong>{formatPercent(adherence?.complianceRatePct)}</strong>
                      </div>
                      <div className="service-level-card-footer">
                        <span>{definition.itsmTicketNumber ? `ITSM ${definition.itsmTicketNumber}` : 'Not yet synced to ITSM'}</span>
                        <span>{definition.approvalStatus === 'approved' ? 'Approved' : 'Review pending'}</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </section>

          <section className="service-levels-editor-panel">
            <div className="service-levels-panel-header">
              <div>
                <p className="service-levels-panel-label">Editor</p>
                <h2>{selectedDefinition ? 'Edit service level' : 'Create service level'}</h2>
              </div>
              <div className="service-levels-state-chip">{currentApprovalState}</div>
            </div>

            <form className="service-levels-form" onSubmit={handleSave}>
              <div className="service-levels-form-grid">
                <AppInput
                  id="service-levels-name"
                  label="Name"
                  fieldClassName="service-levels-field"
                  type="text"
                  value={formState.name}
                  onChange={(event) => handleFieldChange('name', event.target.value)}
                  placeholder="Customer dataset availability"
                  required
                />

                <AppTextarea
                  id="service-levels-description"
                  label="Description"
                  fieldClassName="service-levels-field service-levels-field-wide"
                  value={formState.description}
                  onChange={(event) => handleFieldChange('description', event.target.value)}
                  placeholder="Describe the service target, business impact, and review cadence."
                  rows={4}
                />

                <AppSelect
                  id="service-levels-scope-kind"
                  label="Scope kind"
                  value={formState.scopeKind}
                  onChange={(value) => handleFieldChange('scopeKind', value)}
                  options={SCOPE_KIND_OPTIONS}
                  fieldClassName="service-levels-field"
                />

                <AppSelect
                  id="service-levels-metric-kind"
                  label="Metric kind"
                  value={formState.metricKind}
                  onChange={(value) => handleFieldChange('metricKind', value)}
                  options={METRIC_KIND_OPTIONS}
                  fieldClassName="service-levels-field"
                />

                <AppSelect
                  id="service-levels-threshold-operator"
                  label="Threshold operator"
                  value={formState.thresholdOperator}
                  onChange={(value) => handleFieldChange('thresholdOperator', value)}
                  options={THRESHOLD_OPERATOR_OPTIONS}
                  fieldClassName="service-levels-field"
                />

                <AppInput
                  id="service-levels-threshold-value"
                  label="Threshold value"
                  fieldClassName="service-levels-field"
                  type="number"
                  value={formState.thresholdValue}
                  onChange={(event) => handleFieldChange('thresholdValue', event.target.value)}
                  min="0"
                  step="0.01"
                  required
                />

                <AppInput
                  id="service-levels-scope-id"
                  label="Scope id"
                  fieldClassName="service-levels-field"
                  type="text"
                  value={formState.scopeId}
                  onChange={(event) => handleFieldChange('scopeId', event.target.value)}
                  placeholder="dataset-1"
                  required
                />

                <AppInput
                  id="service-levels-lookback-amount"
                  label="Lookback amount"
                  fieldClassName="service-levels-field"
                  type="number"
                  value={formState.lookbackAmount}
                  onChange={(event) => handleFieldChange('lookbackAmount', event.target.value)}
                  min="1"
                  step="1"
                  required
                />

                <AppSelect
                  id="service-levels-lookback-unit"
                  label="Lookback unit"
                  value={formState.lookbackUnit}
                  onChange={(value) => handleFieldChange('lookbackUnit', value)}
                  options={LOOKBACK_UNIT_OPTIONS}
                  fieldClassName="service-levels-field"
                />
              </div>

              <div className="service-levels-form-summary">
                <div>
                  <span className="service-levels-meta-label">Workspace</span>
                  <strong>{currentWorkspaceId}</strong>
                </div>
                <div>
                  <span className="service-levels-meta-label">Selected adherence</span>
                  <strong>{selectedDefinition?.adherence?.summary || 'No history yet'}</strong>
                </div>
                <div>
                  <span className="service-levels-meta-label">ITSM ticket</span>
                  <strong>{selectedDefinition?.itsmTicketNumber || 'Not synced yet'}</strong>
                </div>
              </div>

              <AppTextarea
                id="service-levels-approval-comments"
                label="Approval comments"
                fieldClassName="service-levels-field service-levels-field-wide"
                value={approvalComments}
                onChange={(event) => setApprovalComments(event.target.value)}
                placeholder="Describe the review decision before syncing to ITSM."
                rows={3}
              />

              <div className="service-levels-action-row">
                <AppButton variant="primary" type="submit" disabled={isLoading || isSaving}>
                  {isSaving ? 'Saving…' : selectedDefinition ? 'Save changes' : 'Save draft'}
                </AppButton>
                <AppButton variant="secondary" type="button" onClick={handleEvaluateBreaches} disabled={isLoading}>
                  Evaluate breaches
                </AppButton>
                <AppButton variant="secondary" type="button" onClick={handleApprove} disabled={isLoading || isApproving || !selectedDefinitionId || selectedDefinition?.approvalStatus === 'approved'}>
                  {isApproving ? 'Approving…' : selectedDefinition?.approvalStatus === 'approved' ? 'Already approved' : 'Approve and sync to ITSM'}
                </AppButton>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  )
}
