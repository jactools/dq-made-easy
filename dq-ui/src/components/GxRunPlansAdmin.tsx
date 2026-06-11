import React, { useCallback, useEffect, useMemo, useState } from 'react'

import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { useSettings } from '../hooks/useContexts'
import { useAuth } from '../hooks/useKeycloak'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { PrimaryButton, SecondaryButton } from './Button'
import { AdminPageHeader } from './AdminPageHeader'
import { GxSuiteScopePickerModal, type GxSuiteScopeSelection } from './GxSuiteScopePickerModal'
import { AppSelect, AppPageShell } from './app-primitives'
import { SupportRequestFlow } from './SupportRequestFlow'
import { StatusBanner } from './StatusBanner'
import { AppBanner, AppCard, AppCardContent } from './app-primitives'
import './Settings.css'
import { createSupportReferenceId, formatSupportReferenceId } from '../utils/supportReference'
import { normalizeValidationUiText } from '../utils/validationTerminology'

type GxSuiteEnvelope = {
  suiteId: string
  suiteVersion: number
  artifactVersion: string
  assignmentScope: {
    dataObjectId: string | null
    datasetId: string | null
    dataProductId: string | null
    tagIds?: string[]
  }
  resolvedExecutionScope: {
    dataObjectVersionIds: string[]
  }
  compiledFrom: {
    ruleIds: string[]
    compilerVersion: string
    generatedAt: string
  }
  executionContract?: {
    engineTarget: string
    executionShape: string
  } | null
}

type ValidationRunPlanVersion = {
  runPlanVersionId: string
  runPlanId: string
  governanceState: string
  gxSuiteSelection?: {
    selectionMode?: string
    scopeSelector?: Record<string, unknown>
    suiteRefs?: Array<{ suiteId: string; suiteVersion: number }>
  } | null
  suiteId?: string | null
  suiteVersion?: number | null
  scheduleDefinition: {
    scheduledAt?: string
  }
  validationStatus?: string | null
  reviewStatus?: string | null
  supersedesVersionId?: string | null
  createdAt: string
}

type ValidationRunPlanTransitionEvent = {
  id: string
  runPlanId: string
  runPlanVersionId?: string | null
  action: string
  fromState?: string | null
  toState?: string | null
  actorId?: string | null
  correlationId?: string | null
  effectiveFrom?: string | null
  details?: Record<string, unknown>
  occurredAt: string
}

type ValidationRunPlan = {
  runPlanId: string
  workspaceId: string
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
  versions: ValidationRunPlanVersion[]
  transitionEvents?: ValidationRunPlanTransitionEvent[]
}

type ValidationRunPlanActivation = {
  plan: ValidationRunPlan
  dispatch: {
    queueMessageId: string
    scheduledAt?: string
    correlationId?: string
  }
}

type ValidationRunPlanValidation = {
  plan: ValidationRunPlan
  validationStatus: 'passed' | 'failed'
  message: string
  diagnostics: Array<Record<string, unknown>>
}

type RunPlanStatusFilter = 'all' | 'draft' | 'active'
type RunPlanMode = 'single_suite' | 'grouped_scope'

const PLAN_STATUS_OPTIONS: Array<{ value: RunPlanStatusFilter; label: string }> = [
  { value: 'all', label: 'All statuses' },
  { value: 'draft', label: 'Draft only' },
  { value: 'active', label: 'Active only' },
]

const RUN_PLAN_MODE_OPTIONS: Array<{ value: RunPlanMode; label: string }> = [
  { value: 'single_suite', label: 'Single suite' },
  { value: 'grouped_scope', label: 'Grouped scope' },
]

const canCreateBranchVersion = (plan: ValidationRunPlan): boolean => true

const canSubmitForValidation = (state: string | null | undefined): boolean => state === 'draft' || state === 'validation_failed'
const canMarkValidationFailed = (state: string | null | undefined): boolean => state === 'pending_validation'
const canSendToReview = (state: string | null | undefined): boolean => state === 'pending_validation'
const canApprove = (state: string | null | undefined): boolean => state === 'pending_review'
const canActivate = (state: string | null | undefined): boolean => state === 'approved_pending_activation'
const canRequestActivation = (state: string | null | undefined): boolean => state === 'draft' || state === 'inactive' || state === 'deactivated'
const canRequestDeactivation = (state: string | null | undefined): boolean => state === 'active'
const canCancel = (state: string | null | undefined): boolean => ['validation_failed', 'pending_review', 'approved_pending_activation'].includes(String(state || ''))

const describeVersionTarget = (version: ValidationRunPlanVersion): string => {
  if (version.gxSuiteSelection?.selectionMode === 'grouped_scope') {
    const refs = version.gxSuiteSelection.suiteRefs || []
    return `Grouped scope | ${refs.length} suite${refs.length === 1 ? '' : 's'}`
  }
  if (version.suiteId && version.suiteVersion) {
    return `Validation suite v${version.suiteVersion}`
  }
  return 'n/a'
}

const describeTransitionAction = (action: string): string => {
  if (action === 'version_created') return 'version created'
  if (action === 'transitioned') return 'transitioned'
  if (action === 'superseded') return 'superseded'
  if (action === 'activated') return 'activated'
  return action.replace(/_/g, ' ')
}

const buildDefaultScheduledAtInput = (): string => {
  const date = new Date(Date.now() + 60 * 60 * 1000)
  date.setSeconds(0, 0)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day}T${hours}:${minutes}`
}

const toScheduledAtIso = (value: string): string => {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    throw new Error('Enter a valid scheduled time.')
  }
  return parsed.toISOString()
}

const buildSuiteSelectionKey = (suiteId: string, suiteVersion: number): string => `${suiteId}:${suiteVersion}`

const formatCompactId = (value: string | null | undefined): string => {
  const raw = String(value || '').trim()
  if (!raw) return 'n/a'
  if (raw.length <= 18) return raw
  return `${raw.slice(0, 10)}…${raw.slice(-6)}`
}

const describeSelectedScope = (selection: GxSuiteScopeSelection | null): string => {
  if (!selection) return 'No scope selected.'

  const tagSummary = selection.tagIds && selection.tagIds.length > 0
    ? ` | Tags: ${selection.tagIds.join(', ')}`
    : ''

  if (selection.kind === 'attribute') {
    const objectLabel = selection.dataObjectName || selection.dataObjectId || 'unknown object'
    return `Attribute ${selection.attributeName} (${objectLabel}, version ${selection.dataObjectVersionId})${tagSummary}`
  }

  if (selection.kind === 'data_object_version') {
    const objectLabel = selection.dataObjectName || selection.dataObjectId || 'unknown object'
    return `Data object version (${objectLabel}, version ${selection.dataObjectVersionId})${tagSummary}`
  }

  if (selection.kind === 'data_object') {
    return `Data object ${selection.dataObjectName} (${selection.dataObjectId})${tagSummary}`
  }

  if (selection.kind === 'dataset') {
    return `Dataset ${selection.datasetName} (${selection.datasetId})${tagSummary}`
  }

  return `Data product ${selection.dataProductName} (${selection.dataProductId})${tagSummary}`
}

const formatAssignmentScope = (scope: GxSuiteEnvelope['assignmentScope'] | undefined): string => {
  if (!scope) return 'n/a'

  const parts = [
    scope.dataProductId ? 'Data product' : null,
    scope.datasetId ? 'Dataset' : null,
    scope.dataObjectId ? 'Data object' : null,
    scope.tagIds && scope.tagIds.length > 0 ? `Tags (${scope.tagIds.length})` : null,
  ].filter(Boolean)

  return parts.length > 0 ? parts.join(', ') : 'n/a'
}

const formatAssignmentScopeTitle = (scope: GxSuiteEnvelope['assignmentScope'] | undefined): string => {
  if (!scope) return 'n/a'

  const parts = [
    scope.dataProductId ? `dataProductId=${scope.dataProductId}` : null,
    scope.datasetId ? `datasetId=${scope.datasetId}` : null,
    scope.dataObjectId ? `dataObjectId=${scope.dataObjectId}` : null,
    scope.tagIds && scope.tagIds.length > 0 ? `tagIds=${scope.tagIds.join(',')}` : null,
  ].filter(Boolean)

  return parts.length > 0 ? parts.join(', ') : 'n/a'
}

const describeVersionTargetTitle = (version: ValidationRunPlanVersion): string => {
  if (version.gxSuiteSelection?.selectionMode === 'grouped_scope') {
    const refs = version.gxSuiteSelection.suiteRefs || []
    return refs.length > 0
      ? refs.map((ref) => `Suite ${ref.suiteId} v${ref.suiteVersion}`).join(', ')
      : 'Grouped scope'
  }
  if (version.suiteId && version.suiteVersion) {
    return `Suite ${version.suiteId} v${version.suiteVersion}`
  }
  return 'n/a'
}

const buildSuiteQueryFromSelection = (selection: GxSuiteScopeSelection): { key: string; value: string } => {
  if (selection.kind === 'data_product') {
    return { key: 'dataProductId', value: selection.dataProductId }
  }
  if (selection.kind === 'dataset') {
    return { key: 'datasetId', value: selection.datasetId }
  }
  if (selection.kind === 'data_object') {
    return { key: 'dataObjectId', value: selection.dataObjectId }
  }
  return { key: 'dataObjectVersionId', value: selection.dataObjectVersionId }
}

const formatDateTime = (value: string | null | undefined): string => {
  const raw = String(value || '').trim()
  if (!raw) return 'n/a'
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  return parsed.toLocaleString()
}

const extractErrorMessage = (payload: unknown, fallback: string, status: number): string => {
  const detail = (payload as any)?.detail
  const referenceId = typeof detail?.reference_id === 'string'
    ? detail.reference_id
    : typeof (payload as any)?.reference_id === 'string'
      ? (payload as any).reference_id
      : null
  if (typeof detail === 'string') {
    const message = referenceId ? `${detail} (${formatSupportReferenceId(referenceId)})` : detail
    return normalizeValidationUiText(message)
  }
  if (typeof detail?.message === 'string') {
    const message = referenceId ? `${detail.message} (${formatSupportReferenceId(referenceId)})` : detail.message
    return normalizeValidationUiText(message)
  }
  if (typeof (payload as any)?.message === 'string') {
    const message = referenceId ? `${(payload as any).message} (${formatSupportReferenceId(referenceId)})` : (payload as any).message
    return normalizeValidationUiText(message)
  }
  return normalizeValidationUiText(
    referenceId ? `${fallback} (${status}) - ${formatSupportReferenceId(referenceId)}` : `${fallback} (${status})`
  )
}

type AssistanceRequestContext = {
  referenceId: string
  runPlanId: string
  runPlanVersionId: string
  diagnostics: Array<Record<string, unknown>>
}

export const ValidationRunPlansAdmin: React.FC = () => {
  const auth = useAuth()
  const settings = useSettings()

  const apiBaseUrl = useMemo(() => {
    return toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  }, [settings.applicationSettings?.apiBaseUrl])

  const workspaceId = useMemo(() => {
    return auth.currentWorkspaceId || auth.user?.workspaceRoles?.[0]?.workspaceId || null
  }, [auth.currentWorkspaceId, auth.user?.workspaceRoles])

  const [isScopePickerOpen, setIsScopePickerOpen] = useState(false)
  const [scopeSelection, setScopeSelection] = useState<GxSuiteScopeSelection | null>(null)
  const [availableSuites, setAvailableSuites] = useState<GxSuiteEnvelope[]>([])
  const [selectedSuiteKey, setSelectedSuiteKey] = useState('')
  const [scheduleAtInput, setScheduleAtInput] = useState(buildDefaultScheduledAtInput)
  const [suiteLoading, setSuiteLoading] = useState(false)
  const [suiteError, setSuiteError] = useState<string | null>(null)
  const [planMode, setPlanMode] = useState<RunPlanMode>('single_suite')

  const [plans, setPlans] = useState<ValidationRunPlan[]>([])
  const [plansLoading, setPlansLoading] = useState(false)
  const [plansError, setPlansError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<RunPlanStatusFilter>('all')
  const [filterToSelectedSuite, setFilterToSelectedSuite] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const [supportRequestContext, setSupportRequestContext] = useState<AssistanceRequestContext | null>(null)
  const [supportRequestVisible, setSupportRequestVisible] = useState(false)

  const selectedSuite = useMemo(
    () => availableSuites.find((suite) => buildSuiteSelectionKey(suite.suiteId, suite.suiteVersion) === selectedSuiteKey) || null,
    [availableSuites, selectedSuiteKey]
  )

  const refreshPlans = useCallback(async () => {
    if (!workspaceId) {
      setPlans([])
      setPlansError('Select a workspace before managing validation run plans.')
      return
    }

    setPlansLoading(true)
    setPlansError(null)

    try {
      const token = getAuthToken()
      const params = new URLSearchParams()
      params.set('workspaceId', workspaceId)
      if (statusFilter !== 'all') {
        params.set('status', statusFilter)
      }
      if (filterToSelectedSuite && selectedSuite) {
        params.set('suiteId', selectedSuite.suiteId)
      }

      const response = await fetch(`${apiBaseUrl}/run-plans?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })

      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        payload = null
      }

      if (!response.ok) {
        throw new Error(extractErrorMessage(payload, 'Failed to load validation run plans', response.status))
      }

      if (!Array.isArray(payload)) {
        throw new Error('Unexpected response shape from validation run plan API.')
      }

      setPlans(snakeToCamel<ValidationRunPlan[]>(payload))
    } catch (exc) {
      setPlans([])
      setPlansError(exc instanceof Error ? normalizeValidationUiText(exc.message) : 'Failed to load validation run plans')
    } finally {
      setPlansLoading(false)
    }
  }, [apiBaseUrl, filterToSelectedSuite, selectedSuite, statusFilter, workspaceId])

  useEffect(() => {
    void refreshPlans()
  }, [refreshPlans])

  const loadSuites = useCallback(async () => {
    if (!scopeSelection) {
      setSuiteError('Please select a catalog scope first.')
      setAvailableSuites([])
      return
    }

    setSuiteLoading(true)
    setSuiteError(null)

    try {
      const token = getAuthToken()
      const params = new URLSearchParams()
      const query = buildSuiteQueryFromSelection(scopeSelection)
      params.set(query.key, query.value)
      params.set('status', 'active')
      params.set('latestOnly', 'true')

      const response = await fetch(`${apiBaseUrl}/gx/suites?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })

      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        payload = null
      }

      if (!response.ok) {
        throw new Error(extractErrorMessage(payload, 'Failed to load validation suites', response.status))
      }

      if (!Array.isArray(payload)) {
        throw new Error('Unexpected response shape from validation suites API.')
      }

      const normalized = snakeToCamel<GxSuiteEnvelope[]>(payload)
      setAvailableSuites(normalized)
      setSelectedSuiteKey((current) => {
        if (current && normalized.some((suite) => buildSuiteSelectionKey(suite.suiteId, suite.suiteVersion) === current)) {
          return current
        }
        return normalized[0] ? buildSuiteSelectionKey(normalized[0].suiteId, normalized[0].suiteVersion) : ''
      })
    } catch (exc) {
      setAvailableSuites([])
      setSelectedSuiteKey('')
      setSuiteError(exc instanceof Error ? normalizeValidationUiText(exc.message) : 'Failed to load validation suites')
    } finally {
      setSuiteLoading(false)
    }
  }, [apiBaseUrl, scopeSelection])

  const createDraftPlan = useCallback(async () => {
    if (!workspaceId) {
      setActionError('Select a workspace before creating validation run plans.')
      return
    }
    if (planMode === 'single_suite' && !selectedSuite) {
      setActionError('Select an active validation suite before creating a run plan.')
      return
    }
    if (planMode === 'grouped_scope' && !scopeSelection) {
      setActionError('Select a catalog scope before creating a grouped run plan.')
      return
    }

    setPendingAction('create-plan')
    setActionError(null)
    setActionMessage(null)
    setSupportRequestContext(null)
    setSupportRequestVisible(false)

    try {
      const token = getAuthToken()
      const response = await fetch(`${apiBaseUrl}/run-plans`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(camelToSnake({
          workspaceId,
          planningMode: planMode,
          ...(planMode === 'single_suite'
            ? {
                suiteId: selectedSuite?.suiteId,
                suiteVersion: selectedSuite?.suiteVersion,
              }
            : (() => {
                const query = scopeSelection ? buildSuiteQueryFromSelection(scopeSelection) : null
                return query ? { [query.key]: query.value } : {}
              })()),
          tagIds: scopeSelection?.tagIds || [],
          scheduledAt: toScheduledAtIso(scheduleAtInput),
        })),
      })

      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        payload = null
      }

      if (!response.ok) {
        throw new Error(extractErrorMessage(payload, 'Failed to create validation run plan', response.status))
      }

      const createdPlan = snakeToCamel<ValidationRunPlan>(payload)
      setActionMessage(`Draft run plan ${createdPlan.runPlanId} created.`)
      setSupportRequestVisible(false)
      await refreshPlans()
    } catch (exc) {
      setActionError(exc instanceof Error ? normalizeValidationUiText(exc.message) : 'Failed to create validation run plan')
    } finally {
      setPendingAction(null)
    }
  }, [apiBaseUrl, planMode, refreshPlans, scheduleAtInput, scopeSelection, selectedSuite, workspaceId])

  const createDraftVersion = useCallback(async (runPlanId: string) => {
    if (planMode === 'single_suite' && !selectedSuite) {
      setActionError('Select an active validation suite before creating a new plan version.')
      return
    }
    if (planMode === 'grouped_scope' && !scopeSelection) {
      setActionError('Select a catalog scope before creating a grouped plan version.')
      return
    }

    setPendingAction(`create-version:${runPlanId}`)
    setActionError(null)
    setActionMessage(null)
    setSupportRequestContext(null)
    setSupportRequestVisible(false)

    try {
      const token = getAuthToken()
      const response = await fetch(`${apiBaseUrl}/run-plans/${runPlanId}/versions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(camelToSnake({
          planningMode: planMode,
          ...(planMode === 'single_suite'
            ? {
                suiteId: selectedSuite?.suiteId,
                suiteVersion: selectedSuite?.suiteVersion,
              }
            : (() => {
                const query = scopeSelection ? buildSuiteQueryFromSelection(scopeSelection) : null
                return query ? { [query.key]: query.value } : {}
              })()),
          tagIds: scopeSelection?.tagIds || [],
          scheduledAt: toScheduledAtIso(scheduleAtInput),
        })),
      })

      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        payload = null
      }

      if (!response.ok) {
        throw new Error(extractErrorMessage(payload, 'Failed to create validation run plan version', response.status))
      }

      const updatedPlan = snakeToCamel<ValidationRunPlan>(payload)
      setActionMessage(`Added draft version ${updatedPlan.versions[updatedPlan.versions.length - 1]?.runPlanVersionId || ''}.`)
      setSupportRequestVisible(false)
      await refreshPlans()
    } catch (exc) {
      setActionError(exc instanceof Error ? normalizeValidationUiText(exc.message) : 'Failed to create validation run plan version')
    } finally {
      setPendingAction(null)
    }
  }, [apiBaseUrl, planMode, refreshPlans, scheduleAtInput, scopeSelection, selectedSuite])

  const transitionVersion = useCallback(async (runPlanId: string, runPlanVersionId: string, targetState: string) => {
    setPendingAction(`transition:${targetState}:${runPlanVersionId}`)
    setActionError(null)
    setActionMessage(null)
    setSupportRequestContext(null)
    setSupportRequestVisible(false)

    try {
      const token = getAuthToken()
      const response = await fetch(`${apiBaseUrl}/run-plans/${runPlanId}/versions/${runPlanVersionId}/governance-state`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(camelToSnake({
          targetState,
        })),
      })

      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        payload = null
      }

      if (!response.ok) {
        throw new Error(extractErrorMessage(payload, 'Failed to transition validation run plan version', response.status))
      }

      setActionMessage(`Updated ${runPlanVersionId} to ${targetState}.`)
      setSupportRequestVisible(false)
      await refreshPlans()
    } catch (exc) {
      setActionError(exc instanceof Error ? normalizeValidationUiText(exc.message) : 'Failed to transition validation run plan version')
    } finally {
      setPendingAction(null)
    }
  }, [apiBaseUrl, refreshPlans])

  const validateVersion = useCallback(async (runPlanId: string, runPlanVersionId: string) => {
    setPendingAction(`validate:${runPlanVersionId}`)
    setActionError(null)
    setActionMessage(null)
    setSupportRequestContext(null)
    setSupportRequestVisible(false)

    try {
      const token = getAuthToken()
      const response = await fetch(`${apiBaseUrl}/run-plans/${runPlanId}/versions/${runPlanVersionId}/validate`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })

      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        payload = null
      }

      if (!response.ok) {
        const errorMessage = extractErrorMessage(payload, 'Failed to validate validation run plan version', response.status)

        if (response.status === 422) {
          const referenceId = createSupportReferenceId()
          const detail = (payload as any)?.detail
          const diagnostics = Array.isArray(detail?.diagnostics) ? detail.diagnostics : []

          setActionError(normalizeValidationUiText(errorMessage))
          setSupportRequestVisible(true)
          setSupportRequestContext({
            referenceId,
            runPlanId,
            runPlanVersionId,
            diagnostics,
          })
          await refreshPlans()
          return
        }

        throw new Error(errorMessage)
      }

      const validation = snakeToCamel<ValidationRunPlanValidation>(payload)
      if (validation.validationStatus === 'passed') {
        setActionMessage(normalizeValidationUiText(validation.message))
        setSupportRequestContext(null)
        setSupportRequestVisible(false)
      } else {
        const currentRunPlanVersion = runPlanVersionId
        const referenceId = createSupportReferenceId()
        setActionError(normalizeValidationUiText(validation.message))
        setSupportRequestVisible(true)
        setSupportRequestContext({
          referenceId,
          runPlanId,
          runPlanVersionId: currentRunPlanVersion,
          diagnostics: validation.diagnostics || [],
        })
      }
      await refreshPlans()
    } catch (exc) {
      setActionError(exc instanceof Error ? normalizeValidationUiText(exc.message) : 'Failed to validate validation run plan version')
    } finally {
      setPendingAction(null)
    }
  }, [apiBaseUrl, refreshPlans])

  const activateVersion = useCallback(async (runPlanId: string, runPlanVersionId: string) => {
    setPendingAction(`activate:${runPlanVersionId}`)
    setActionError(null)
    setActionMessage(null)
    setSupportRequestContext(null)
    setSupportRequestVisible(false)

    try {
      const token = getAuthToken()
      const response = await fetch(`${apiBaseUrl}/run-plans/${runPlanId}/versions/${runPlanVersionId}/activate`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })

      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        payload = null
      }

      if (!response.ok) {
        throw new Error(extractErrorMessage(payload, 'Failed to activate validation run plan version', response.status))
      }

      const activation = snakeToCamel<ValidationRunPlanActivation>(payload)
      setActionMessage(
        `Activated plan ${activation.plan.runPlanId} as run ${activation.dispatch.queueMessageId}.`
      )
      setSupportRequestVisible(false)
      await refreshPlans()
    } catch (exc) {
      setActionError(exc instanceof Error ? normalizeValidationUiText(exc.message) : 'Failed to activate validation run plan version')
    } finally {
      setPendingAction(null)
    }
  }, [apiBaseUrl, refreshPlans])

  const handleSupportRequestSuccess = useCallback(() => {
    setActionError(null)
    setActionMessage(null)
    setSupportRequestContext(null)
  }, [])

  const supportRequestAction = supportRequestVisible ? (
    <SupportRequestFlow
      apiBaseUrl={settings.applicationSettings?.apiBaseUrl || ''}
      buttonLabel="Request assistance from operations team"
      createRequestBody={() => ({
        referenceId: supportRequestContext?.referenceId || createSupportReferenceId(),
        title: 'Validation run plan assistance',
        message: actionError,
        source: 'validation-run-plans-admin',
        runPlanId: supportRequestContext?.runPlanId || null,
        runPlanVersionId: supportRequestContext?.runPlanVersionId || null,
        workspaceId,
        diagnostics: supportRequestContext?.diagnostics || [],
      })}
      onSuccess={handleSupportRequestSuccess}
      onError={setActionError}
      onDismiss={() => setSupportRequestVisible(false)}
    />
  ) : null

  return (
    <AppPageShell className="settings-container">
      <AdminPageHeader
        title="Validation Run Plans"
        subtitle="Create draft run plans, iterate with immutable versions, and explicitly activate a chosen version."
      />
      <div className="settings-content">
        <div className="settings-panel">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <AppCard>
              <AppCardContent>
                <div className="gx-run-plan-card-heading">
                  <h3 className="gx-run-plan-card-title">Overview</h3>
                </div>
                <AppBanner variant="info" aria-live="polite">
                  Current workspace: <strong>{workspaceId || 'not selected'}</strong>. Direct scheduled runs remain available in monitoring; this screen governs draft and active run plans. Scheduling is canonical UTC, with local time used only for UI input and display.
                </AppBanner>
              </AppCardContent>
            </AppCard>

            <AppCard>
              <AppCardContent>
                <div className="gx-run-plan-card-heading">
                  <h3 className="gx-run-plan-card-title">Plan Drafting</h3>
                </div>
                <p className="settings-subtitle">{describeSelectedScope(scopeSelection)}</p>

                <div className="gx-run-plan-filter-row">
                  <div className="gx-run-plan-filter-item">
                    <AppSelect
                      id="validationRunPlanMode"
                      label="Plan mode"
                      value={planMode}
                      onChange={(value) => setPlanMode(value as RunPlanMode)}
                      options={RUN_PLAN_MODE_OPTIONS}
                      placeholderLabel="Choose mode"
                    />
                  </div>
                </div>

                <div className="settings-actions">
                  <PrimaryButton onClick={() => setIsScopePickerOpen(true)} disabled={Boolean(pendingAction)}>
                    Browse data catalog
                  </PrimaryButton>
                  <SecondaryButton onClick={() => void loadSuites()} disabled={!scopeSelection || suiteLoading || Boolean(pendingAction)}>
                    {suiteLoading ? 'Loading suites…' : 'Load active validation suites'}
                  </SecondaryButton>
                </div>

                {planMode === 'grouped_scope' && scopeSelection && (
                  <AppBanner variant="info" aria-live="polite">
                    Grouped scope plans reuse the selected catalog scope and schedule one grouped execution run across all active suites in that scope.
                  </AppBanner>
                )}

                {availableSuites.length > 0 && planMode === 'single_suite' && (
                  <>
                    <div className="form-group" style={{ marginTop: 16, maxWidth: 280 }}>
                      <label htmlFor="validationRunPlanScheduledAt">Scheduled time</label>
                      <input
                        id="validationRunPlanScheduledAt"
                        type="datetime-local"
                        value={scheduleAtInput}
                        onChange={(event) => setScheduleAtInput(event.target.value)}
                      />
                      <span className="settings-hint">Uses your local timezone for input, then converts to a UTC timestamp for the API. Timezone-native scheduling is not supported.</span>
                    </div>

                    <div className="admin-users gx-run-plan-suite-list">
                      {availableSuites.map((suite) => {
                        const suiteKey = buildSuiteSelectionKey(suite.suiteId, suite.suiteVersion)
                        const isSelected = suiteKey === selectedSuiteKey
                        return (
                          <label key={suiteKey} className={`admin-user-row gx-run-plan-suite-row${isSelected ? ' is-selected' : ''}`}>
                            <div className="admin-user-info">
                              <span className="admin-user-name" title={`Suite ${suite.suiteId} v${suite.suiteVersion}`}>Validation suite v{suite.suiteVersion}</span>
                              <span className="admin-user-email" title={formatAssignmentScopeTitle(suite.assignmentScope)}>Assignment: {formatAssignmentScope(suite.assignmentScope)}</span>
                              <span className="admin-user-id">Execution: {suite.executionContract?.engineTarget || 'n/a'} / {suite.executionContract?.executionShape || 'n/a'}</span>
                            </div>
                            <div className="admin-user-actions">
                              <input
                                type="radio"
                                name="gx-run-plan-suite"
                                aria-label={`Select validation suite v${suite.suiteVersion}`}
                                checked={isSelected}
                                onChange={() => setSelectedSuiteKey(suiteKey)}
                              />
                            </div>
                          </label>
                        )
                      })}
                    </div>

                    <div className="settings-actions" style={{ marginTop: 16 }}>
                      <PrimaryButton onClick={() => void createDraftPlan()} disabled={!workspaceId || !selectedSuite || Boolean(pendingAction)}>
                        {pendingAction === 'create-plan' ? 'Creating draft…' : 'Create draft plan'}
                      </PrimaryButton>
                    </div>
                  </>
                )}

                {planMode === 'grouped_scope' && (
                  <div className="settings-actions" style={{ marginTop: 16 }}>
                    <PrimaryButton onClick={() => void createDraftPlan()} disabled={!workspaceId || !scopeSelection || Boolean(pendingAction)}>
                      {pendingAction === 'create-plan' ? 'Creating draft…' : 'Create grouped draft plan'}
                    </PrimaryButton>
                  </div>
                )}

                {suiteError && (
                  <div style={{ marginTop: 16 }}>
                    <StatusBanner variant="error" message={suiteError} onDismiss={() => setSuiteError(null)} />
                  </div>
                )}
              </AppCardContent>
            </AppCard>

            <AppCard>
              <AppCardContent>
                <div className="gx-run-plan-card-heading">
                  <h3 className="gx-run-plan-card-title">Run Plan List</h3>
                </div>
                <div className="gx-run-plan-filter-row">
                  <div className="gx-run-plan-filter-item">
                    <AppSelect
                      id="validationRunPlanStatusFilter"
                      label="Status"
                      value={statusFilter}
                      onChange={(value) => setStatusFilter(value as RunPlanStatusFilter)}
                      options={PLAN_STATUS_OPTIONS}
                      placeholderLabel="Choose status"
                    />
                  </div>
                  <div className="form-group checkbox gx-run-plan-filter-checkbox">
                    <input
                      id="validationRunPlanSelectedSuiteFilter"
                      type="checkbox"
                      checked={filterToSelectedSuite}
                      onChange={(event) => setFilterToSelectedSuite(event.target.checked)}
                    />
                    <label htmlFor="validationRunPlanSelectedSuiteFilter">Filter to selected suite</label>
                  </div>
                  <div className="settings-actions gx-run-plan-filter-actions">
                    <SecondaryButton onClick={() => void refreshPlans()} disabled={plansLoading || Boolean(pendingAction)}>
                      {plansLoading ? 'Refreshing…' : 'Refresh plans'}
                    </SecondaryButton>
                  </div>
                </div>

                {actionMessage && (
                  <div style={{ marginTop: 16 }}>
                    <StatusBanner
                      variant="success"
                      message={actionMessage}
                      onDismiss={() => setActionMessage(null)}
                      referenceId={supportRequestContext?.referenceId}
                    />
                  </div>
                )}

                {actionError && (
                  <div style={{ marginTop: 16 }}>
                    <StatusBanner
                      variant="error"
                      message={actionError}
                      onDismiss={() => setActionError(null)}
                      referenceId={supportRequestContext?.referenceId}
                    />
                  </div>
                )}

                {supportRequestAction && (
                  <div style={{ marginTop: 16 }}>
                    {supportRequestAction}
                  </div>
                )}

                {plansError && (
                  <div style={{ marginTop: 16 }}>
                    <StatusBanner variant="error" message={plansError} onDismiss={() => setPlansError(null)} />
                  </div>
                )}

                {!plansLoading && plans.length === 0 && !plansError && (
                  <p className="settings-subtitle" style={{ marginTop: 16 }}>No validation run plans found for the current filters.</p>
                )}

                <div className="admin-users gx-run-plan-list">
                  {plans.map((plan) => {
                    const latestVersion = plan.versions[plan.versions.length - 1] || null
                    return (
                      <div key={plan.runPlanId} className="admin-user-row gx-run-plan-card">
                        <div className="admin-user-info gx-run-plan-card-info">
                          <span className="admin-user-name">{plan.runPlanId}</span>
                          <span className="admin-user-email">
                            Status: <strong>{plan.status}</strong> | Pending branch: {plan.pendingVersionGovernanceState || 'none'} | Versions: {plan.versions.length} | Latest schedule: {formatDateTime(latestVersion?.scheduleDefinition?.scheduledAt || null)}
                          </span>
                          <span className="admin-user-id">
                            Activated: {formatDateTime(plan.activatedAt)} | Last dispatched run: {plan.lastDispatchedRunId || 'n/a'}
                          </span>

                          <div className="gx-run-plan-version-list">
                            {plan.versions.map((version, index) => {
                              const isActiveVersion = plan.currentActiveVersionId === version.runPlanVersionId
                              const versionLabel = `version ${index + 1}`
                              return (
                                <div key={version.runPlanVersionId} className="gx-run-plan-version-row">
                                  <div>
                                    <div className="admin-user-name gx-run-plan-version-title" title={`Run plan version ID: ${version.runPlanVersionId}`}>
                                      Plan version {index + 1}
                                      {isActiveVersion ? ' (active)' : ''}
                                    </div>
                                    <div className="admin-user-email" title={describeVersionTargetTitle(version)}>
                                      {describeVersionTarget(version)} | Scheduled {formatDateTime(version.scheduleDefinition?.scheduledAt || null)}
                                    </div>
                                    <div className="admin-user-id" title={version.supersedesVersionId ? `Supersedes version ID: ${version.supersedesVersionId}` : undefined}>
                                      Version ID: {formatCompactId(version.runPlanVersionId)} | State: {version.governanceState} | Validation: {version.validationStatus || 'n/a'} | Review: {version.reviewStatus || 'n/a'}
                                    </div>
                                  </div>
                                  <div className="admin-user-actions gx-run-plan-version-actions">
                                    {canSubmitForValidation(version.governanceState) && (
                                      <SecondaryButton
                                        onClick={() => void validateVersion(plan.runPlanId, version.runPlanVersionId)}
                                        disabled={Boolean(pendingAction)}
                                      >
                                        {pendingAction === `validate:${version.runPlanVersionId}` ? 'Validating…' : `Validate ${versionLabel}`}
                                      </SecondaryButton>
                                    )}
                                    {canMarkValidationFailed(version.governanceState) && (
                                      <SecondaryButton
                                        onClick={() => void transitionVersion(plan.runPlanId, version.runPlanVersionId, 'validation_failed')}
                                        disabled={Boolean(pendingAction)}
                                      >
                                        {pendingAction === `transition:validation_failed:${version.runPlanVersionId}` ? 'Marking…' : `Mark ${versionLabel} validation failed`}
                                      </SecondaryButton>
                                    )}
                                    {canSendToReview(version.governanceState) && (
                                      <SecondaryButton
                                        onClick={() => void transitionVersion(plan.runPlanId, version.runPlanVersionId, 'pending_review')}
                                        disabled={Boolean(pendingAction)}
                                      >
                                        {pendingAction === `transition:pending_review:${version.runPlanVersionId}` ? 'Sending…' : `Send ${versionLabel} to review`}
                                      </SecondaryButton>
                                    )}
                                    {canApprove(version.governanceState) && (
                                      <SecondaryButton
                                        onClick={() => void transitionVersion(plan.runPlanId, version.runPlanVersionId, 'approved_pending_activation')}
                                        disabled={Boolean(pendingAction)}
                                      >
                                        {pendingAction === `transition:approved_pending_activation:${version.runPlanVersionId}` ? 'Approving…' : `Approve ${versionLabel}`}
                                      </SecondaryButton>
                                    )}
                                    {canRequestActivation(version.governanceState) && (
                                      <SecondaryButton
                                        onClick={() => void transitionVersion(plan.runPlanId, version.runPlanVersionId, 'activation-requested')}
                                        disabled={Boolean(pendingAction)}
                                      >
                                        {pendingAction === `transition:activation-requested:${version.runPlanVersionId}` ? 'Requesting…' : `Request activation for ${versionLabel}`}
                                      </SecondaryButton>
                                    )}
                                    {canRequestDeactivation(version.governanceState) && (
                                      <SecondaryButton
                                        onClick={() => void transitionVersion(plan.runPlanId, version.runPlanVersionId, 'deactivation-requested')}
                                        disabled={Boolean(pendingAction)}
                                      >
                                        {pendingAction === `transition:deactivation-requested:${version.runPlanVersionId}` ? 'Requesting…' : `Request deactivation for ${versionLabel}`}
                                      </SecondaryButton>
                                    )}
                                    {canCancel(version.governanceState) && (
                                      <SecondaryButton
                                        onClick={() => void transitionVersion(plan.runPlanId, version.runPlanVersionId, 'cancelled')}
                                        disabled={Boolean(pendingAction)}
                                      >
                                        {pendingAction === `transition:cancelled:${version.runPlanVersionId}` ? 'Cancelling…' : `Cancel ${versionLabel}`}
                                      </SecondaryButton>
                                    )}
                                    {canActivate(version.governanceState) && (
                                      <PrimaryButton
                                        onClick={() => void activateVersion(plan.runPlanId, version.runPlanVersionId)}
                                        disabled={Boolean(pendingAction)}
                                      >
                                        {pendingAction === `activate:${version.runPlanVersionId}` ? 'Activating…' : `Activate ${versionLabel}`}
                                      </PrimaryButton>
                                    )}
                                  </div>
                                </div>
                              )
                            })}
                          </div>

                          {(plan.transitionEvents || []).length > 0 && (
                            <div className="gx-run-plan-transition-history" style={{ marginTop: 16 }}>
                              <div className="admin-user-name gx-run-plan-transition-title">Transition history</div>
                              <div className="gx-run-plan-transition-list">
                                {plan.transitionEvents!.map((event) => (
                                  <div key={event.id} className="gx-run-plan-transition-row">
                                    <div className="admin-user-email">
                                      {formatDateTime(event.occurredAt)} | {describeTransitionAction(event.action)}
                                    </div>
                                    <div className="admin-user-id">
                                      {event.fromState || 'n/a'} {'->'} {event.toState || 'n/a'} | actor {event.actorId || 'system'} | correlation {event.correlationId || 'n/a'}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                        <div className="admin-user-actions gx-run-plan-card-actions">
                          {canCreateBranchVersion(plan) && (
                            <SecondaryButton
                              onClick={() => void createDraftVersion(plan.runPlanId)}
                              disabled={(planMode === 'single_suite' ? !selectedSuite : !scopeSelection) || Boolean(pendingAction)}
                            >
                              {pendingAction === `create-version:${plan.runPlanId}` ? 'Creating version…' : 'Create new branch version'}
                            </SecondaryButton>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </AppCardContent>
            </AppCard>
          </div>

          <GxSuiteScopePickerModal
            isOpen={isScopePickerOpen}
            onClose={() => setIsScopePickerOpen(false)}
            onSelect={(selection) => {
              setScopeSelection(selection)
              setAvailableSuites([])
              setSelectedSuiteKey('')
              setSuiteError(null)
            }}
          />
        </div>
      </div>
    </AppPageShell>
  )
}