import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react'
import { useRules, useAuth, useSettings } from '../hooks/useContexts'
import { type Rule, type RuleStatus, type RuleVersion, type RuleJoinDefinition, type RuleCheckType, type RuleCheckTypeParams } from '../types/rules'
import { TemplatesSelectorModal } from './Templates'
import { toApiGroupV1Base } from '../config/api'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { SubmitApprovalModal, ApproveRejectModal, ActivateRuleModal, DeactivateRuleModal, SaveTemplateModal } from './RuleActionModals'
import { AssignAttributesModal } from './AssignAttributesModal'
import { JoinConditionsModal } from './JoinConditionsModal'
import { ReusableFiltersModal } from './ReusableFiltersModal'
import { ReusableJoinsModal } from './ReusableJoinsModal'
import { TestRuleModal } from './TestRuleModal'
import { ValidationDiagnosticsModal } from './ValidationDiagnosticsModal'
import { BulkActionsToolbar } from './BulkActionsToolbar'
import { RuleDetailsModal } from './RuleDetailsModal'
import { AdhocRuleExecutionModal } from './AdhocRuleExecutionModal'
import { RuleCard } from './rules/RuleCard'
import { RulesHeader } from './rules/RulesHeader'
import { OnboardingRuleScopeSelector, type OnboardingProposalsResponse, type OnboardingScopeSelectorState } from './OnboardingRuleScopeSelector'
import { OnboardingRuleReview, type OnboardingReviewUiState } from './OnboardingRuleReview'
import { useRuleActions } from './rules/useRuleActions'
import { useRuleDerivedData } from './rules/useRuleDerivedData'
import { useRulesScope } from './rules/useRulesScope'
import { useRuleModals } from './rules/useRuleModals'
import { useRuleTemplateFlow } from './rules/useRuleTemplateFlow'
import { useRuleAttributeCatalog } from './rules/useRuleAttributeCatalog'
import { useRuleCompilerInfo } from './rules/useRuleCompilerInfo'
import { DEFAULT_SEARCH_MINIMUM_LENGTH, committedSearchValue, readUrlFilterState, serializeUrlFilterState } from '../utils/listFilterState'
import { useRuleStatusGovernance } from './rules/useRuleStatusGovernance'
import { collectPendingDeactivationRuleIds } from './rules/pendingDeactivation'
import { hasResolvableAssignedAttributes } from './rules/ruleDisplayUtils'
import { getAuthToken } from '../contexts/AuthContext'
import { AppPageShell } from './app-primitives'
import {
  consumeDashboardNavigationSelection,
  getRulesDestinationForScope,
  isDashboardRuleStatus,
  isDashboardWorkspaceScope,
} from '../utils/dashboardNavigation'
import type { WorkspaceScope } from './WorkspaceScopeSegmentedControl'
import './Rules.css'

const VALIDATION_STATE_CACHE_KEY = 'dq-rule-validation-state-by-version'
const ONBOARDING_SESSION_STATE_VERSION = 1
const ONBOARDING_SESSION_TTL_MS = 8 * 60 * 60 * 1000
const ONBOARDING_SESSION_STORAGE_PREFIX = 'dq-onboarding-session-v1'
const RULES_SEARCH_MINIMUM_LENGTH = DEFAULT_SEARCH_MINIMUM_LENGTH
const RULES_FILTER_URL_STATE = {
  scope: { param: 'rules_scope', defaultValue: 'my', allowedValues: ['my', 'team', 'all', 'global'] },
  status: { param: 'rules_status', defaultValue: 'all', allowedValues: ['all', 'draft', 'testing', 'tested', 'pending-approval', 'approved', 'activated', 'deactivated', 'rejected'] },
  query: { param: 'rules_q', defaultValue: '' },
  owner: { param: 'rules_owner', defaultValue: '' },
  updatedSince: { param: 'rules_updated_since', defaultValue: '' },
  updatedBefore: { param: 'rules_updated_before', defaultValue: '' },
} as const

const toApiDateTime = (value: string, boundary: 'start' | 'end'): string => {
  const trimmed = String(value || '').trim()
  if (!trimmed) return ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return boundary === 'start' ? `${trimmed}T00:00:00Z` : `${trimmed}T23:59:59Z`
  }
  return trimmed
}

const buildValidationVersionKey = (rule: Rule): string => {
  const version = Number(rule.currentVersionNumber ?? 0)
  const updatedAt = String(rule.updatedAt ?? '')
  return `${rule.id}::v${version}::${updatedAt}`
}

interface RulesProps {
  onSelectRule?: (rule: Rule) => void
  preSelectedTemplate?: any
  onTemplateUsed?: () => void
  viewScope?: 'my' | 'team' | 'all' | 'global'
  onOpenRuleValidation?: (ruleIds: string[]) => void
  onOpenDataAssets?: () => void
}

interface RuleNotice {
  type: 'success' | 'error'
  message: string
  ruleId?: string
  details?: string[]
  context?: 'test' | 'validation' | 'copy' | 'general'
}

interface CheckTypeDraftValidationResult {
  valid: boolean
  message: string | null
  fieldErrors: Record<string, string>
  normalizedCheckTypeParams: RuleCheckTypeParams | null
}

interface StoredOnboardingSessionState {
  version: number
  workspaceId: string
  userKey: string
  step: 'scope' | 'review'
  savedAtMs: number
  expiresAtMs: number
  proposalsResponse: OnboardingProposalsResponse | null
  scopeState: OnboardingScopeSelectorState | null
  reviewUiState: OnboardingReviewUiState | null
}

export const Rules: React.FC<RulesProps> = ({ onSelectRule, preSelectedTemplate, onTemplateUsed, viewScope = 'my', onOpenRuleValidation, onOpenDataAssets }) => {
  const [initialDashboardPreset] = useState(() => consumeDashboardNavigationSelection(getRulesDestinationForScope(viewScope)))
  const [initialUrlFilters] = useState(() => (
    typeof window === 'undefined'
      ? readUrlFilterState('', RULES_FILTER_URL_STATE)
      : readUrlFilterState(window.location.search, RULES_FILTER_URL_STATE)
  ))
  const { rules, approvals, getRulesByWorkspace, submitForApproval, requestRuleDeactivation, approveRule, rejectRule, activateRule, updateRule, updateRuleStatus, logTestAction, saveRuleAsTemplate, getAuditTrail, isLoading, error, clearError, ruleAttributeMappings, ruleAttributeThresholds, assignAttributesToRule, validateRuleComposition, createRule, loadRulesPage } = useRules()
  const auth = useAuth()
  const settings = useSettings()
  const compactMode = settings.displaySettings?.compactMode ?? false
  const itemsPerPageSetting = settings.displaySettings?.itemsPerPage ?? 10
  const previousViewScopePropRef = useRef(viewScope)
  const [selectedViewScope, setSelectedViewScope] = useState<WorkspaceScope>(() => {
    const presetScope = initialDashboardPreset?.view_scope
    if (isDashboardWorkspaceScope(presetScope)) return presetScope
    const urlScope = initialUrlFilters.scope
    return isDashboardWorkspaceScope(urlScope) ? urlScope : viewScope
  })
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null)
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null)
  const [selectedBulkRuleIds, setSelectedBulkRuleIds] = useState<Set<string>>(new Set())
  const [filterStatus, setFilterStatus] = useState<RuleStatus | 'all'>(() => {
    const presetStatus = initialDashboardPreset?.filter_status
    if (isDashboardRuleStatus(presetStatus)) return presetStatus
    const urlStatus = initialUrlFilters.status
    return isDashboardRuleStatus(urlStatus) ? urlStatus : 'all'
  })
  const [ruleSearchInput, setRuleSearchInput] = useState(initialUrlFilters.query)
  const [ownerFilter, setOwnerFilter] = useState(initialUrlFilters.owner)
  const [updatedSince, setUpdatedSince] = useState(initialUrlFilters.updatedSince)
  const [updatedBefore, setUpdatedBefore] = useState(initialUrlFilters.updatedBefore)
  const [sortBy, setSortBy] = useState<'name' | 'created' | 'status'>('status')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const [filtersExpanded, setFiltersExpanded] = useState(true)
  const [currentPage, setCurrentPage] = useState(1)
  const [testNotice, setTestNotice] = useState<RuleNotice | null>(null)
  const [isOnboardingScopeSelectorOpen, setIsOnboardingScopeSelectorOpen] = useState(false)
  const [isOnboardingReviewOpen, setIsOnboardingReviewOpen] = useState(false)
  const [onboardingProposalsResponse, setOnboardingProposalsResponse] = useState<OnboardingProposalsResponse | null>(null)
  const [onboardingScopeState, setOnboardingScopeState] = useState<OnboardingScopeSelectorState | null>(null)
  const [onboardingReviewUiState, setOnboardingReviewUiState] = useState<OnboardingReviewUiState | null>(null)
  const [isCreatingOnboardingDrafts, setIsCreatingOnboardingDrafts] = useState(false)
  const [expandedDetailTabByRule, setExpandedDetailTabByRule] = useState<Record<string, 'details' | 'versions'>>({})
  const [compiledExpressionByRuleId, setCompiledExpressionByRuleId] = useState<Record<string, string>>({})
  const [validationStateByRuleId, setValidationStateByRuleId] = useState<Record<string, 'valid' | 'invalid' | 'upstream-error'>>({})
  const [validationStateByVersionKey, setValidationStateByVersionKey] = useState<Record<string, 'valid' | 'invalid' | 'upstream-error'>>(() => {
    if (typeof window === 'undefined') return {}
    try {
      const raw = window.sessionStorage.getItem(VALIDATION_STATE_CACHE_KEY)
      return raw ? JSON.parse(raw) : {}
    } catch {
      return {}
    }
  })
  const [fetchedRulesById, setFetchedRulesById] = useState<Record<string, Rule>>({})
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken())
  const onboardingResumePromptedRef = useRef(false)
  const rulebuilderApiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  const validateCheckTypeDraft = useCallback(async (
    checkType: RuleCheckType,
    checkTypeParams: Partial<RuleCheckTypeParams>,
  ): Promise<CheckTypeDraftValidationResult> => {
    if (!authToken) {
      throw new Error('Cannot validate a check type draft without an authenticated session')
    }

    const response = await fetch(`${rulebuilderApiBase}/rules/validate/check-type`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(camelToSnake({
        checkType,
        checkTypeParams,
      })),
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(errorText || `Failed to validate check type draft (${response.status})`)
    }

    const payload = snakeToCamel(await response.json()) as CheckTypeDraftValidationResult
    return payload
  }, [authToken, rulebuilderApiBase])
  const { latestCompiledInfoByRuleId } = useRuleCompilerInfo({
    authToken,
    apiBaseUrl: settings.applicationSettings?.apiBaseUrl,
  })
  const { allowedTransitionsByStatus, isLoaded: statusGovernanceLoaded } = useRuleStatusGovernance({
    authToken,
    apiBaseUrl: settings.applicationSettings?.apiBaseUrl,
  })
  const { attributeCatalog } = useRuleAttributeCatalog({
    authToken,
    apiBaseUrl: settings.applicationSettings?.apiBaseUrl,
    refreshKey: compiledExpressionByRuleId,
  })

  const { workspaceRules, scopedRules, emptyRulesMessage } = useRulesScope({
    rules,
    fetchedRulesById,
    ruleAttributeMappings,
    attributeCatalog,
    getRulesByWorkspace,
    currentWorkspaceId: auth.currentWorkspaceId || auth.user?.workspaceRoles?.[0]?.workspaceId || null,
    user: auth.user,
    canReadAcrossWorkspaces: auth.canReadAcrossWorkspaces,
    viewScope: selectedViewScope,
  })

  useEffect(() => {
    if (previousViewScopePropRef.current !== viewScope) {
      previousViewScopePropRef.current = viewScope
      setSelectedViewScope(viewScope)
    }
  }, [viewScope])

  const committedRuleSearchQuery = useMemo(() => (
    committedSearchValue(ruleSearchInput, RULES_SEARCH_MINIMUM_LENGTH)
  ), [ruleSearchInput])

  const resolvedWorkspaceId = useMemo(() => (
    auth.currentWorkspaceId || auth.user?.workspaceRoles?.[0]?.workspaceId || null
  ), [auth.currentWorkspaceId, auth.user?.workspaceRoles])

  const currentUserOwnerQuery = useMemo(() => (
    String(auth.user?.email || auth.user?.id || auth.user?.name || '').trim()
  ), [auth.user?.email, auth.user?.id, auth.user?.name])

  const onboardingUserKey = useMemo(() => {
    const value = String(auth.user?.id || auth.user?.email || auth.user?.name || '').trim()
    return value || 'anonymous'
  }, [auth.user?.email, auth.user?.id, auth.user?.name])

  const onboardingSessionStorageKey = useMemo(() => {
    if (!resolvedWorkspaceId) {
      return null
    }

    return `${ONBOARDING_SESSION_STORAGE_PREFIX}:${resolvedWorkspaceId}:${onboardingUserKey}`
  }, [onboardingUserKey, resolvedWorkspaceId])

  const clearOnboardingSessionState = useCallback(() => {
    if (typeof window === 'undefined' || !onboardingSessionStorageKey) {
      return
    }
    window.sessionStorage.removeItem(onboardingSessionStorageKey)
  }, [onboardingSessionStorageKey])

  useEffect(() => {
    if (typeof window === 'undefined' || !onboardingSessionStorageKey || onboardingResumePromptedRef.current) {
      return
    }

    onboardingResumePromptedRef.current = true

    let parsed: StoredOnboardingSessionState | null = null
    try {
      const raw = window.sessionStorage.getItem(onboardingSessionStorageKey)
      if (!raw) {
        return
      }
      parsed = JSON.parse(raw) as StoredOnboardingSessionState
    } catch {
      clearOnboardingSessionState()
      return
    }

    if (!parsed || parsed.version !== ONBOARDING_SESSION_STATE_VERSION) {
      clearOnboardingSessionState()
      return
    }

    if (parsed.expiresAtMs <= Date.now()) {
      clearOnboardingSessionState()
      return
    }

    const shouldResume = window.confirm('Resume your guided rule generation session from where you left off?')
    if (!shouldResume) {
      clearOnboardingSessionState()
      return
    }

    setOnboardingScopeState(parsed.scopeState || null)
    setOnboardingReviewUiState(parsed.reviewUiState || null)
    setOnboardingProposalsResponse(parsed.proposalsResponse || null)
    if (parsed.step === 'review' && parsed.proposalsResponse) {
      setIsOnboardingScopeSelectorOpen(false)
      setIsOnboardingReviewOpen(true)
      return
    }
    setIsOnboardingReviewOpen(false)
    setIsOnboardingScopeSelectorOpen(true)
  }, [clearOnboardingSessionState, onboardingSessionStorageKey])

  useEffect(() => {
    if (typeof window === 'undefined' || !onboardingSessionStorageKey) {
      return
    }

    const hasSessionState = Boolean(
      isOnboardingScopeSelectorOpen ||
      isOnboardingReviewOpen ||
      onboardingProposalsResponse ||
      onboardingScopeState ||
      onboardingReviewUiState,
    )

    if (!hasSessionState) {
      clearOnboardingSessionState()
      return
    }

    const now = Date.now()
    const payload: StoredOnboardingSessionState = {
      version: ONBOARDING_SESSION_STATE_VERSION,
      workspaceId: resolvedWorkspaceId || '',
      userKey: onboardingUserKey,
      step: isOnboardingReviewOpen ? 'review' : 'scope',
      savedAtMs: now,
      expiresAtMs: now + ONBOARDING_SESSION_TTL_MS,
      proposalsResponse: onboardingProposalsResponse,
      scopeState: onboardingScopeState,
      reviewUiState: onboardingReviewUiState,
    }

    window.sessionStorage.setItem(onboardingSessionStorageKey, JSON.stringify(payload))
  }, [
    clearOnboardingSessionState,
    isOnboardingReviewOpen,
    isOnboardingScopeSelectorOpen,
    onboardingProposalsResponse,
    onboardingReviewUiState,
    onboardingScopeState,
    onboardingSessionStorageKey,
    onboardingUserKey,
    resolvedWorkspaceId,
  ])

  const apiOwnerFilter = useMemo(() => {
    const explicitOwner = String(ownerFilter || '').trim()
    if (explicitOwner) return explicitOwner
    return selectedViewScope === 'my' ? currentUserOwnerQuery : ''
  }, [ownerFilter, selectedViewScope, currentUserOwnerQuery])

  const filterScopeDescription = useMemo(() => {
    const workspaceLabel = resolvedWorkspaceId ? `workspace ${resolvedWorkspaceId}` : 'the selected workspace'
    if (selectedViewScope === 'global') return 'Scope: all workspaces.'
    if (selectedViewScope === 'my') return `Scope: my rules in ${workspaceLabel}.`
    if (selectedViewScope === 'team') return `Scope: team rules in ${workspaceLabel}.`
    return `Scope: rules using assets in ${workspaceLabel}.`
  }, [resolvedWorkspaceId, selectedViewScope])

  const clearRuleFilters = useCallback(() => {
    setFilterStatus('all')
    setRuleSearchInput('')
    setOwnerFilter('')
    setUpdatedSince('')
    setUpdatedBefore('')
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const nextSearch = serializeUrlFilterState(window.location.search, RULES_FILTER_URL_STATE, {
      scope: selectedViewScope,
      status: filterStatus,
      query: ruleSearchInput,
      owner: ownerFilter,
      updatedSince,
      updatedBefore,
    })
    const nextUrl = `${window.location.pathname}${nextSearch}${window.location.hash}`
    if (nextUrl !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
      window.history.replaceState(null, '', nextUrl)
    }
  }, [selectedViewScope, filterStatus, ruleSearchInput, ownerFilter, updatedSince, updatedBefore])

  useEffect(() => {
    const workspace = selectedViewScope === 'global' ? undefined : resolvedWorkspaceId || undefined
    const limit = Math.max(Number(settings.workspaceSettings?.maxListItems || 0), 100)
    void loadRulesPage({
      page: 1,
      limit,
      workspace,
      status: filterStatus === 'all' ? undefined : filterStatus,
      q: committedRuleSearchQuery || undefined,
      owner: apiOwnerFilter || undefined,
      updatedSince: toApiDateTime(updatedSince, 'start') || undefined,
      updatedBefore: toApiDateTime(updatedBefore, 'end') || undefined,
    })
  }, [
    selectedViewScope,
    resolvedWorkspaceId,
    filterStatus,
    committedRuleSearchQuery,
    apiOwnerFilter,
    updatedSince,
    updatedBefore,
    loadRulesPage,
    settings.workspaceSettings?.maxListItems,
  ])

  useEffect(() => {
    const syncTokenFromStorage = () => {
      setAuthToken(getAuthToken())
    }

    syncTokenFromStorage()
    if (typeof window !== 'undefined') {
      window.addEventListener('storage', syncTokenFromStorage)
      window.addEventListener('dq-auth-token-changed', syncTokenFromStorage)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('storage', syncTokenFromStorage)
        window.removeEventListener('dq-auth-token-changed', syncTokenFromStorage)
      }
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.sessionStorage.setItem(VALIDATION_STATE_CACHE_KEY, JSON.stringify(validationStateByVersionKey))
    } catch {
      // Ignore storage failures.
    }
  }, [validationStateByVersionKey])

  useEffect(() => {
    setValidationStateByVersionKey((prev) => {
      let changed = false
      const next = { ...prev }
      for (const rule of rules) {
        if (rule.validationStatus === 'valid' || rule.validationStatus === 'invalid') {
          const key = buildValidationVersionKey(rule)
          if (next[key] !== rule.validationStatus) {
            next[key] = rule.validationStatus
            changed = true
          }
        }
      }
      return changed ? next : prev
    })
  }, [rules])

  useEffect(() => {
    setValidationStateByVersionKey((prev) => {
      let changed = false
      const next = { ...prev }
      for (const [ruleId, state] of Object.entries(validationStateByRuleId)) {
        const rule = rules.find((r) => r.id === ruleId)
        if (!rule) continue
        const key = buildValidationVersionKey(rule)
        if (next[key] !== state) {
          next[key] = state
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [validationStateByRuleId, rules])

  const {
    activeModalRule,
    activeModalType,
    activeModalReadOnly,
    setActiveModalType,
    closeActiveModal,
    openActionModal,
    testDetailsRuleId,
    openTestDetails,
    closeTestDetails,
    validationDiagnosticsModal,
    setValidationDiagnosticsModal,
    closeValidationDiagnostics,
  } = useRuleModals()

  const showNotice = useCallback((notice: RuleNotice) => {
    setTestNotice(notice)
  }, [])

  const openOnboardingRuleGeneration = useCallback(() => {
    if (!resolvedWorkspaceId) {
      showNotice({
        type: 'error',
        message: 'Cannot start guided rule generation without an active workspace.',
        context: 'general',
      })
      return
    }

    closeActiveModal()
    setOnboardingProposalsResponse(null)
    setOnboardingScopeState(null)
    setOnboardingReviewUiState(null)
    setIsOnboardingReviewOpen(false)
    setIsOnboardingScopeSelectorOpen(true)
  }, [closeActiveModal, resolvedWorkspaceId, showNotice])

  const handleOnboardingProposalsGenerated = useCallback((response: OnboardingProposalsResponse) => {
    setOnboardingProposalsResponse(response)
    setOnboardingReviewUiState(null)
    setIsOnboardingScopeSelectorOpen(false)
    setIsOnboardingReviewOpen(true)
  }, [])

  const handleOnboardingCreateDraftRules = useCallback(async (selectedProposalIds: string[]) => {
    if (!resolvedWorkspaceId) {
      showNotice({
        type: 'error',
        message: 'Cannot create onboarding drafts without an active workspace.',
        context: 'general',
      })
      return
    }

    if (selectedProposalIds.length === 0) {
      showNotice({
        type: 'error',
        message: 'Select at least one proposed rule before creating drafts.',
        context: 'general',
      })
      return
    }

    const token = getAuthToken()
    if (!token) {
      showNotice({
        type: 'error',
        message: 'Authentication is required to create onboarding draft rules.',
        context: 'general',
      })
      return
    }

    setIsCreatingOnboardingDrafts(true)
    try {
      const response = await fetch(`${rulebuilderApiBase}/onboarding/create-batch`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(
          camelToSnake({
            workspaceId: resolvedWorkspaceId,
            acceptedProposalIds: selectedProposalIds,
          }),
        ),
      })

      if (!response.ok) {
        const errorBody = await response.json().catch(() => null)
        const detail = errorBody && typeof errorBody === 'object' ? (errorBody as any).detail : null
        const detailMessage = typeof detail === 'string'
          ? detail
          : detail && typeof detail === 'object' && typeof (detail as any).message === 'string'
            ? (detail as any).message
            : null
        throw new Error(detailMessage || `Failed to create onboarding drafts (${response.status})`)
      }

      const payload = snakeToCamel(await response.json()) as {
        created?: number
        skipped?: number
        failed?: number
      }

      showNotice({
        type: 'success',
        message: `Onboarding draft creation finished: ${Number(payload.created || 0)} created, ${Number(payload.skipped || 0)} skipped, ${Number(payload.failed || 0)} failed.`,
        context: 'general',
      })

      setIsOnboardingReviewOpen(false)
      setOnboardingProposalsResponse(null)
      setOnboardingScopeState(null)
      setOnboardingReviewUiState(null)
      clearOnboardingSessionState()
      const workspace = selectedViewScope === 'global' ? undefined : resolvedWorkspaceId || undefined
      const limit = Math.max(Number(settings.workspaceSettings?.maxListItems || 0), 100)
      void loadRulesPage({
        page: 1,
        limit,
        workspace,
        filters: {
          search: committedRuleSearchQuery,
          status: filterStatus === 'all' ? undefined : filterStatus,
          owner: apiOwnerFilter || undefined,
          updatedAfter: toApiDateTime(updatedSince, 'start') || undefined,
          updatedBefore: toApiDateTime(updatedBefore, 'end') || undefined,
        },
      })
    } catch (error) {
      showNotice({
        type: 'error',
        message: error instanceof Error ? error.message : 'Failed to create onboarding draft rules.',
        context: 'general',
      })
    } finally {
      setIsCreatingOnboardingDrafts(false)
    }
  }, [
    apiOwnerFilter,
    committedRuleSearchQuery,
    filterStatus,
    loadRulesPage,
    resolvedWorkspaceId,
    rulebuilderApiBase,
    selectedViewScope,
    settings.workspaceSettings?.maxListItems,
    showNotice,
    updatedBefore,
    updatedSince,
    clearOnboardingSessionState,
  ])

  const onRuleFocused = useCallback((ruleId: string) => {
    setSelectedRuleId(ruleId)
    setExpandedRuleId(ruleId)
  }, [])

  const {
    showTemplateSelector,
    templatePreviewData,
    templateInitialCustomizations,
    editingRuleId,
    openCreateRuleWizard,
    closeTemplateWizard,
    handleSelectTemplate,
    openEditRuleWizard,
  } = useRuleTemplateFlow({
    authToken,
    apiBaseUrl: settings.applicationSettings?.apiBaseUrl,
    currentWorkspaceId: resolvedWorkspaceId,
    attributeCatalog,
    ruleAttributeMappings,
    workspaceRules,
    fetchedRulesById,
    createRule,
    updateRule,
    assignAttributesToRule,
    showNotice,
    onRuleFocused,
  })

  const renderNoticeContent = useCallback((notice: RuleNotice) => {
    const details = Array.isArray(notice.details)
      ? notice.details.map((item) => String(item || '').trim()).filter(Boolean)
      : []
    const showTestDetailsAction = notice.context === 'test' && Boolean(notice.ruleId)

    const testDetailsAction = showTestDetailsAction ? (
      <button
        type="button"
        className="rules-notice-action-btn"
        onClick={() => openTestDetails(String(notice.ruleId))}
      >
        View full test details
      </button>
    ) : null
    const dismissAction = (
      <button
        type="button"
        className="rules-notice-action-btn"
        onClick={() => setTestNotice(null)}
      >
        Dismiss
      </button>
    )

    const actionRow = (
      <div className="rules-notice-actions">
        {testDetailsAction}
        {dismissAction}
      </div>
    )

    if (details.length === 0) {
      return (
        <>
          <div>{notice.message}</div>
          {actionRow}
        </>
      )
    }

    return (
      <>
        <div>{notice.message}</div>
        <ul className="rules-notice-details">
          {details.map((detail, index) => (
            <li key={`${index}-${detail}`}>{detail}</li>
          ))}
        </ul>
        {actionRow}
      </>
    )
  }, [])

  // Auto-open template preview if navigating from Templates tab
  useEffect(() => {
    if (preSelectedTemplate) {
      openCreateRuleWizard(preSelectedTemplate)
      onTemplateUsed?.()
    }
  }, [preSelectedTemplate, onTemplateUsed, openCreateRuleWizard])

  useEffect(() => {
    const message = String(error || '').trim()
    if (!message) return

    showNotice({
      type: 'error',
      message,
      context: 'general',
    })
    clearError()
  }, [error, clearError, showNotice])

  useEffect(() => {
    const fetchRuleOnDemand = async (ruleId: string): Promise<Rule | undefined> => {
      const token = getAuthToken()
      if (!token) return undefined

      try {
          const response = await fetch(`${toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)}/rules/${encodeURIComponent(ruleId)}`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })

        if (!response.ok) {
          return undefined
        }

        const dbRule = await response.json()
        const rawCheckType = dbRule.checkType ?? dbRule.check_type
        const normalizedCheckType =
          typeof rawCheckType === 'string' && rawCheckType.trim()
            ? rawCheckType.trim().toUpperCase()
            : undefined
        const rawCheckTypeParams = dbRule.checkTypeParams ?? dbRule.check_type_params
        let normalizedCheckTypeParams: any = undefined
        if (typeof rawCheckTypeParams === 'string' && rawCheckTypeParams.trim()) {
          try {
            normalizedCheckTypeParams = JSON.parse(rawCheckTypeParams)
          } catch {
            normalizedCheckTypeParams = undefined
          }
        } else if (rawCheckTypeParams && typeof rawCheckTypeParams === 'object') {
          normalizedCheckTypeParams = rawCheckTypeParams
        }
        const normalizedReusableFilterIds = Array.isArray(dbRule.reusableFilterIds)
          ? dbRule.reusableFilterIds
          : []
        const normalizedReusableFilters = Array.isArray(dbRule.reusableFilters)
          ? dbRule.reusableFilters
          : []
        const normalizedRule: Rule = {
          ...dbRule,
          status: dbRule.active
            ? 'activated'
            : dbRule.last_approval_status === 'deactivated'
            ? 'deactivated'
            : dbRule.last_approval_status === 'approved'
            ? 'approved'
            : dbRule.last_approval_status === 'pending'
            ? 'pending-approval'
            : dbRule.last_approval_status === 'rejected'
            ? 'rejected'
            : 'draft',
          createdAt: dbRule.created_at || new Date().toISOString(),
          updatedAt: dbRule.updated_at || new Date().toISOString(),
          attributes: Array.isArray(dbRule.attributes) ? dbRule.attributes : [],
          joinConditions: Array.isArray(dbRule.joinConditions) ? dbRule.joinConditions : [],
          reusableFilterIds: normalizedReusableFilterIds,
          reusableFilters: normalizedReusableFilters,
          aliasMappings: dbRule.aliasMappings && typeof dbRule.aliasMappings === 'object' ? dbRule.aliasMappings : {},
          riskLevel: 'medium',
          validationStatus: (dbRule.validationStatus ?? dbRule.validation_status) as 'valid' | 'invalid' | null | undefined,
          validatedAt: dbRule.validatedAt ?? dbRule.validated_at ?? null,
          checkType: normalizedCheckType,
          checkTypeParams: normalizedCheckTypeParams,
          createdBy: String((dbRule.created_by ?? dbRule.createdBy) || '').trim() || undefined,
          currentVersionNumber:
            Number(dbRule.currentVersionNumber ?? dbRule.current_version_number ?? dbRule.total_versions ?? 0) || 0,
        }

        setFetchedRulesById((prev) => ({
          ...prev,
          [normalizedRule.id]: normalizedRule,
        }))

        return normalizedRule
      } catch {
        return undefined
      }
    }

    const focusRuleFromStorage = async (ruleId: string) => {
      const normalizedRuleId = String(ruleId || '').trim()
      if (!normalizedRuleId) return

      let targetRule = rules.find((rule) => rule.id === normalizedRuleId)
      if (!targetRule) {
        targetRule = fetchedRulesById[normalizedRuleId]
      }
      if (!targetRule) {
        targetRule = await fetchRuleOnDemand(normalizedRuleId)
      }
      if (!targetRule) {
        return
      }

      setFilterStatus('all')
      setRuleSearchInput('')
      setOwnerFilter('')
      setUpdatedSince('')
      setUpdatedBefore('')
      setCurrentPage(1)
      setSelectedRuleId(normalizedRuleId)
      setExpandedRuleId(normalizedRuleId)
      setExpandedDetailTabByRule((prev) => ({
        ...prev,
        [normalizedRuleId]: prev[normalizedRuleId] || 'details',
      }))
      onSelectRule?.(targetRule)
      localStorage.removeItem('dq-open-rule-id')
    }

    const pendingRuleId = localStorage.getItem('dq-open-rule-id')
    if (pendingRuleId) {
      void focusRuleFromStorage(pendingRuleId)
    }

    const handleOpenRuleEvent = (event: Event) => {
      const customEvent = event as CustomEvent<{ ruleId?: string }>
      const ruleId = String(customEvent.detail?.ruleId || '').trim()
      if (!ruleId) return
      void focusRuleFromStorage(ruleId)
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('dq-open-rule', handleOpenRuleEvent as EventListener)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('dq-open-rule', handleOpenRuleEvent as EventListener)
      }
    }
  }, [rules, fetchedRulesById, onSelectRule, settings.applicationSettings?.apiBaseUrl])

  useEffect(() => {
    const openNewRuleModal = () => {
      // Clear the sessionStorage flag so it doesn't survive a logout/login
      // redirect and auto-open the modal on the next Rules mount.
      sessionStorage.removeItem('dq-open-new-rule')
      openCreateRuleWizard()
    }

    if (typeof window !== 'undefined') {
      const pending = sessionStorage.getItem('dq-open-new-rule')
      if (pending === '1') {
        sessionStorage.removeItem('dq-open-new-rule')
        openNewRuleModal()
      }

      // Cleanup old behavior so stale localStorage flags do not auto-open wizard.
      localStorage.removeItem('dq-open-new-rule')

      window.addEventListener('dq-open-new-rule', openNewRuleModal as EventListener)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('dq-open-new-rule', openNewRuleModal as EventListener)
      }
    }
  }, [openCreateRuleWizard])

  // Derived data: filtering, pagination, status counts
  const { filteredRules, pagedRules, statusCounts, pageSize, totalPages } = useRuleDerivedData({
    workspaceRules: scopedRules,
    canViewPendingApprovals: auth.canApproveRule(),
    filterStatus,
    sortBy,
    sortDirection,
    currentPage,
    itemsPerPageSetting,
    maxListItems: settings.workspaceSettings?.maxListItems,
  })

  // Reset to page 1 when filter status/sort changes; clear selected pin so sorted order stays visible
  useEffect(() => {
    setCurrentPage(1)
    setSelectedRuleId(null)
  }, [filterStatus, ruleSearchInput, ownerFilter, updatedSince, updatedBefore, sortBy, sortDirection, resolvedWorkspaceId, selectedViewScope])

  // Ensure current page is valid for the total pages
  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages)
    }
  }, [currentPage, totalPages])

  const visibleRules = useMemo(() => {
    if (!selectedRuleId) return pagedRules
    if (pagedRules.some((rule) => rule.id === selectedRuleId)) return pagedRules
    const selectedRule = filteredRules.find((rule) => rule.id === selectedRuleId)
    if (!selectedRule) return pagedRules
    const remainder = pagedRules.filter((rule) => rule.id !== selectedRuleId)
    const maxRemainder = Math.max(0, pageSize - 1)
    return [selectedRule, ...remainder.slice(0, maxRemainder)]
  }, [selectedRuleId, pagedRules, filteredRules, pageSize])

  const getEffectiveValidationState = (rule: Rule): 'valid' | 'invalid' | 'upstream-error' | null => {
    const mappedAttributes = Array.isArray(ruleAttributeMappings[rule.id]) ? ruleAttributeMappings[rule.id] : []
    if (!hasResolvableAssignedAttributes(mappedAttributes, attributeCatalog)) return 'invalid'

    const localState = validationStateByRuleId[rule.id]
    if (localState) return localState
    if (rule.validationStatus === 'valid' || rule.validationStatus === 'invalid') return rule.validationStatus
    const cachedState = validationStateByVersionKey[buildValidationVersionKey(rule)]
    if (cachedState) return cachedState
    return null
  }

  const canTransitionByLegacyPermissions = (targetStatus: RuleStatus): boolean => {
    switch (targetStatus) {
      case 'pending-approval':
        return auth.canCreateRule?.() || false
      case 'approved':
        return auth.canApproveRule?.() || false
      case 'activated':
        return auth.canActivateRule?.() || false
      case 'deactivated':
        return auth.canCreateRule?.() || false
      case 'rejected':
        return auth.canApproveRule?.() || false
      case 'draft':
      case 'testing':
      case 'tested':
      default:
        return true
    }
  }

  const canTransitionTo = (rule: Rule, targetStatus: RuleStatus): boolean => {
    if (!auth.user) return false

    if (statusGovernanceLoaded) {
      const allowedTargets = allowedTransitionsByStatus?.[rule.status] || []
      return allowedTargets.includes(targetStatus)
    }

    const transitions: Record<RuleStatus, RuleStatus[]> = {
      draft: ['testing'],
      testing: ['tested'],
      tested: ['pending-approval'],
      'pending-approval': ['approved', 'rejected'],
      approved: ['activated'],
      activated: ['deactivated'],
      deactivated: ['draft'],
      rejected: ['draft'],
    }

    if (!transitions[rule.status]?.includes(targetStatus)) {
      return false
    }

    return canTransitionByLegacyPermissions(targetStatus)
  }

  const getNextActions = (rule: Rule): { status: RuleStatus; label: string }[] => {
    const transitions: Record<RuleStatus, { status: RuleStatus; label: string }[]> = {
      draft: [{ status: 'pending-approval', label: 'Submit for Approval' }],
      testing: [],
      tested: [],
      'pending-approval': [],
      approved: [{ status: 'activated', label: 'Activate' }],
      activated: [],
      deactivated: [],
      rejected: [{ status: 'draft', label: 'Reopen' }],
    }

    return transitions[rule.status]?.filter(action =>
      canTransitionTo(rule, action.status)
    ) || []
  }

  const getRuleActionButtons = (rule: Rule) => {
    // Session state takes precedence over persisted DB state (optimistic update after validate)
    const effectiveValidationState = getEffectiveValidationState(rule)
    const isValidated = effectiveValidationState === 'valid'
    const validationTooltip = isValidated
      ? undefined
      : effectiveValidationState === 'upstream-error'
        ? 'Validation could not complete due to an upstream/server error'
        : 'Rule must pass validation before this action'
    const canModifyCurrentVersion = rule.status !== 'approved' && rule.status !== 'activated'
    const buttons: Array<{ 
      label: string
      type: 'submit' | 'deactivate' | 'approve' | 'activate' | 'template' | 'assign' | 'join' | 'test' | 'adhoc-run' | 'filter' | 'reusable-join' | 'validate' | 'edit'
      show: boolean
      disabled?: boolean
      disabledTitle?: string
    }> = [
      { label: '✏️ Edit Rule', type: 'edit', show: canModifyCurrentVersion },
      { label: '📋 Assign Attributes', type: 'assign', show: canModifyCurrentVersion },
      { label: '🧰 Reusable Filter', type: 'filter', show: canModifyCurrentVersion },
      { label: '🔗 Define Joins', type: 'join', show: canModifyCurrentVersion },
      { label: '🔁 Reusable Joins', type: 'reusable-join', show: canModifyCurrentVersion },
      { label: '✅ Validate Rule', type: 'validate', show: true },
      { label: '🧪 Test Rule', type: 'test', show: true, disabled: !isValidated, disabledTitle: validationTooltip },
      { label: '▶ Run Ad-hoc', type: 'adhoc-run', show: true, disabled: !isValidated, disabledTitle: validationTooltip },
      { label: '📤 Submit for Approval', type: 'submit', show: canTransitionTo(rule, 'pending-approval') },
      { label: '⏹ Request Deactivation', type: 'deactivate', show: canTransitionTo(rule, 'deactivated') },
      { label: '✅ Approve / ❌ Reject', type: 'approve', show: canTransitionTo(rule, 'approved') || canTransitionTo(rule, 'rejected') },
      { label: '🚀 Activate', type: 'activate', show: canTransitionTo(rule, 'activated'), disabled: !isValidated, disabledTitle: validationTooltip },
      { label: '� Create Template', type: 'template', show: true },
    ]
    return buttons.filter(b => b.show)
  }

  const getActionIcon = (type: 'submit' | 'deactivate' | 'approve' | 'activate' | 'template' | 'assign' | 'join' | 'test' | 'adhoc-run' | 'filter' | 'reusable-join' | 'validate' | 'edit'): string => {
    const iconMap: Record<string, string> = {
      edit: 'pencil',
      assign: 'tag',
      filter: 'filter',
      join: 'link',
      'reusable-join': 'arrow-circle-repeat',
      validate: 'check-circle',
      test: 'check',
      'adhoc-run': 'play',
      submit: 'arrow-up',
      deactivate: 'times-circle-fill',
      approve: 'check-circle',
      activate: 'play',
      template: 'document',
    }
    return iconMap[type]
  }

  const getActionTitle = (type: 'submit' | 'deactivate' | 'approve' | 'activate' | 'template' | 'assign' | 'join' | 'test' | 'adhoc-run' | 'filter' | 'reusable-join' | 'validate' | 'edit'): string => {
    const titleMap: Record<string, string> = {
      edit: 'Edit Rule',
      assign: 'Assign Attributes',
      filter: 'Reusable Filter',
      join: 'Define Join Conditions',
      'reusable-join': 'Reusable Joins',
      validate: 'Validate Rule Composition',
      test: 'Test Rule',
      'adhoc-run': 'Run Ad-hoc Execution',
      submit: 'Submit for Approval',
      deactivate: 'Request Deactivation',
      approve: 'Approve / Reject',
      activate: 'Activate Rule',
      template: 'Create Template from this Rule',
    }
    return titleMap[type]
  }

  const selectedRulesForBulkActions = useMemo(
    () => scopedRules.filter((rule) => selectedBulkRuleIds.has(rule.id)),
    [scopedRules, selectedBulkRuleIds]
  )

  const pendingDeactivationRequestsByRuleId = useMemo(() => {
    return collectPendingDeactivationRuleIds(approvals)
  }, [approvals])

  const canBulkApprove = selectedRulesForBulkActions.some(
    (rule) => canTransitionTo(rule, 'approved')
  )
  const canBulkActivate = selectedRulesForBulkActions.some((rule) => canTransitionTo(rule, 'activated'))

  const bulkApproveRuleIds = useMemo(
    () => selectedRulesForBulkActions.filter((rule) => canTransitionTo(rule, 'approved')).map((rule) => rule.id),
    [selectedRulesForBulkActions, allowedTransitionsByStatus, statusGovernanceLoaded, auth.user]
  )
  const bulkActivateRuleIds = useMemo(
    () => selectedRulesForBulkActions.filter((rule) => canTransitionTo(rule, 'activated')).map((rule) => rule.id),
    [selectedRulesForBulkActions, allowedTransitionsByStatus, statusGovernanceLoaded, auth.user]
  )

  const bulkBlockedSummaries = useMemo(() => {
    return selectedRulesForBulkActions
      .filter((rule) => !bulkApproveRuleIds.includes(rule.id) && !bulkActivateRuleIds.includes(rule.id))
      .map((rule) => ({
        ruleId: rule.id,
        ruleName: rule.name,
        reason: `No approve or activate action is available for status ${rule.status}.`,
      }))
  }, [selectedRulesForBulkActions, bulkApproveRuleIds, bulkActivateRuleIds])

  const handleSelectVisibleRules = useCallback(() => {
    setSelectedBulkRuleIds(new Set([
      ...Array.from(selectedBulkRuleIds),
      ...visibleRules.map((rule) => rule.id),
    ]))
  }, [selectedBulkRuleIds, visibleRules])

  // Set activeRule early for use in hooks; include on-demand fetched rules fallback.
  const activeRule = useMemo(() => {
    if (!activeModalRule) return undefined
    return rules.find(r => r.id === activeModalRule) || fetchedRulesById[activeModalRule]
  }, [activeModalRule, rules, fetchedRulesById])

  // Modal action handlers - delegated to custom hook
  const ruleActionHandlers = useRuleActions({
    rules,
    approvals,
    activeModalRule,
    activeRule,
    selectedBulkRuleIds,
    bulkApproveRuleIds,
    bulkActivateRuleIds,
    submitForApproval,
    requestRuleDeactivation,
    approveRule,
    rejectRule,
    activateRule,
    updateRule,
    logTestAction,
    saveRuleAsTemplate,
    assignAttributesToRule,
    validateRuleComposition,
    onModalClose: closeActiveModal,
    setSelectedBulkRuleIds,
    showNotice,
    setValidationStateByRuleId,
    setCompiledExpressionByRuleId,
    setValidationDiagnosticsModal,
    settings,
  })

  const {
    handleSubmitForApproval,
    handleDeactivateRule,
    handleApproval,
    handleRejection,
    handleActivateRule,
    handleSaveTemplate,
    handleAssignAttributes,
    handleAssignReusableFilter,
    handleAssignReusableJoin,
    handleSaveJoinConditions,
    handleCopyJoinExpression,
    handleCopyCompleteExpression,
    handleTestRule,
    handleValidateRule,
    handleToggleBulkSelect,
    handleBulkApprove,
    handleBulkActivate,
  } = ruleActionHandlers

  const toggleRuleExpanded = (ruleId: string) => {
    setExpandedRuleId(prev => {
      const next = prev === ruleId ? null : ruleId
      if (next) {
        setExpandedDetailTabByRule(tabState => ({
          ...tabState,
          [next]: tabState[next] || 'details',
        }))
      }
      return next
    })
  }

  const setExpandedTab = (ruleId: string, tab: 'details' | 'versions') => {
    setExpandedDetailTabByRule(prev => ({ ...prev, [ruleId]: tab }))
  }

  const getExpandedTab = (ruleId: string): 'details' | 'versions' => {
    return expandedDetailTabByRule[ruleId] || 'details'
  }

  const toCurrentRuleVersion = (rule: Rule): RuleVersion => ({
    id: `${rule.id}-current`,
    ruleId: rule.id,
    versionNumber: 1,
    createdAt: rule.updatedAt || rule.createdAt,
    createdBy: rule.createdBy || auth.user?.name || 'System',
    changeType: 'metadata_updated',
    changeDescription: 'Current active state',
    name: rule.name,
    description: rule.description,
    expression: rule.expression || '',
    dimension: rule.dimension,
    active: rule.status === 'activated' || !!rule.active,
    isTemplate: !!rule.is_template,
    templateId: rule.template_id,
    tags: [],
    markedForRollback: false,
  })

  const modalRules = useMemo(() => {
    return activeRule ? [activeRule] : []
  }, [activeRule, rules])

  const activeRuleAssignedAttributes = useMemo(() => {
    if (!activeRule) return []
    const ids = Array.isArray(ruleAttributeMappings[activeRule.id]) ? ruleAttributeMappings[activeRule.id] : []
    return ids.map((id) => {
      const resolved = attributeCatalog[id]
      if (resolved) {
        return {
          id: resolved.id,
          name: String(resolved.name || '').trim(),
          versionId: resolved.versionId || '',
          dataObjectName: resolved.dataObjectName,
          datasetName: resolved.datasetName,
          dataProductName: resolved.dataProductName,
        }
      }
      return {
        id,
        name: '',
        versionId: '',
        dataObjectName: undefined,
        datasetName: undefined,
        dataProductName: undefined,
      }
    })
  }, [activeRule, ruleAttributeMappings, attributeCatalog])

  return (
    <AppPageShell className={`rules-container${compactMode ? ' compact' : ''}`}>
      {testNotice && !testNotice.ruleId && (
        <div className={`rules-notice ${testNotice.type}`}>
          {renderNoticeContent(testNotice)}
        </div>
      )}
      <RulesHeader
        viewScope={selectedViewScope}
        filterStatus={filterStatus}
        searchQuery={ruleSearchInput}
        ownerFilter={ownerFilter}
        updatedSince={updatedSince}
        updatedBefore={updatedBefore}
        sortBy={sortBy}
        sortDirection={sortDirection}
        filtersExpanded={filtersExpanded}
        statusCounts={statusCounts}
        scopeDescription={filterScopeDescription}
        searchMinimumLength={RULES_SEARCH_MINIMUM_LENGTH}
        onViewScopeChange={setSelectedViewScope}
        onFilterStatusChange={setFilterStatus}
        onSearchQueryChange={setRuleSearchInput}
        onOwnerFilterChange={setOwnerFilter}
        onUpdatedSinceChange={setUpdatedSince}
        onUpdatedBeforeChange={setUpdatedBefore}
        onSortByChange={setSortBy}
        onSortDirectionChange={setSortDirection}
        onClearFilters={clearRuleFilters}
        onToggleFilters={() => setFiltersExpanded((prev) => !prev)}
        onOpenReusableFilters={() => {
          closeActiveModal()
          setActiveModalType('filter')
        }}
        onOpenTemplateSelector={openCreateRuleWizard}
        onOpenOnboardingRuleGeneration={openOnboardingRuleGeneration}
      />

      {filteredRules.length > 0 && (
        <div className="rules-selection-row">
          <span>{selectedBulkRuleIds.size} rules selected</span>
          <div className="rules-selection-actions">
            <button type="button" className="link-button" onClick={handleSelectVisibleRules}>
              Select visible ({visibleRules.length})
            </button>
            <button type="button" className="link-button" onClick={() => setSelectedBulkRuleIds(new Set())} disabled={selectedBulkRuleIds.size === 0}>
              Clear all
            </button>
          </div>
        </div>
      )}

      <BulkActionsToolbar 
        selectedRuleIds={Array.from(selectedBulkRuleIds)}
        canApprove={canBulkApprove}
        canActivate={canBulkActivate}
        approveEligibleCount={bulkApproveRuleIds.length}
        activateEligibleCount={bulkActivateRuleIds.length}
        ruleValidationEligibleCount={selectedBulkRuleIds.size}
        blockedRules={bulkBlockedSummaries}
        onApproveSelected={handleBulkApprove}
        onActivateSelected={handleBulkActivate}
        onOpenInRuleValidation={onOpenRuleValidation ? () => onOpenRuleValidation(Array.from(selectedBulkRuleIds)) : undefined}
        onClearSelection={() => setSelectedBulkRuleIds(new Set())}
        totalCount={filteredRules.length}
      />

      <div className="rules-list">
        {filteredRules.length === 0 ? (
          <div className="no-rules">
            <p>{emptyRulesMessage}</p>
          </div>
        ) : (
          visibleRules.map(rule => (
            <RuleCard
              key={rule.id}
              rule={rule}
              pendingDeactivationRequested={Boolean(rule.pendingDeactivationRequested || pendingDeactivationRequestsByRuleId[rule.id])}
              currentWorkspaceId={resolvedWorkspaceId}
              selectedRuleId={selectedRuleId}
              selectedBulkRuleIds={selectedBulkRuleIds}
              expandedRuleId={expandedRuleId}
              testNotice={testNotice}
              compiledExpressionByRuleId={compiledExpressionByRuleId}
              latestCompiledInfoByRuleId={latestCompiledInfoByRuleId}
              attributeCatalog={attributeCatalog}
              ruleAttributeMappings={ruleAttributeMappings}
              ruleAttributeThresholds={ruleAttributeThresholds}
              onSelectRule={onSelectRule}
              onSelectRuleId={setSelectedRuleId}
              onToggleBulkSelect={handleToggleBulkSelect}
              onToggleExpand={toggleRuleExpanded}
              getExpandedTab={getExpandedTab}
              onSetExpandedTab={setExpandedTab}
              getEffectiveValidationState={getEffectiveValidationState}
              getRuleActionButtons={getRuleActionButtons}
              canTransitionTo={canTransitionTo}
              getActionTitle={getActionTitle}
              getActionIcon={getActionIcon}
              onValidateRule={handleValidateRule}
              onOpenRuleValidation={onOpenRuleValidation ? () => onOpenRuleValidation([rule.id]) : undefined}
              onEditRule={openEditRuleWizard}
              onOpenActionModal={openActionModal}
              renderNoticeContent={renderNoticeContent}
              onCopyJoinExpression={handleCopyJoinExpression}
              onCopyCompleteExpression={handleCopyCompleteExpression}
              toCurrentRuleVersion={toCurrentRuleVersion}
              onRollbackComplete={(ruleId, newVersionId) => {
                showNotice({
                  type: 'success',
                  message: `Rollback completed. New version created: ${newVersionId}`,
                  ruleId,
                })
              }}
            />
          ))
        )}
      </div>

      {filteredRules.length > pageSize && (
        <div className="list-pagination">
          <button
            className="pagination-btn"
            onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
            disabled={currentPage === 1}
          >
            Previous
          </button>
          <span className="pagination-info">
            Page {currentPage} of {totalPages}
          </span>
          <button
            className="pagination-btn"
            onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
            disabled={currentPage === totalPages}
          >
            Next
          </button>
        </div>
      )}

      {/* Modals */}
      <SubmitApprovalModal
        isOpen={activeModalType === 'submit'}
        onClose={closeActiveModal}
        onSubmit={handleSubmitForApproval}
      />

      <DeactivateRuleModal
        isOpen={activeModalType === 'deactivate'}
        onClose={closeActiveModal}
        onSubmit={handleDeactivateRule}
      />

      <ApproveRejectModal
        isOpen={activeModalType === 'approve'}
        ruleName={activeRule?.name || ''}
        onClose={closeActiveModal}
        onApprove={handleApproval}
        onReject={handleRejection}
      />

      <ActivateRuleModal
        isOpen={activeModalType === 'activate'}
        onClose={closeActiveModal}
        onSubmit={handleActivateRule}
      />

      <SaveTemplateModal
        isOpen={activeModalType === 'template'}
        currentRuleName={activeRule?.name || ''}
        onClose={closeActiveModal}
        onSubmit={handleSaveTemplate}
      />

      <AssignAttributesModal
        isOpen={activeModalType === 'assign'}
        ruleId={activeModalRule || undefined}
        ruleVersionId={activeRule ? (latestCompiledInfoByRuleId[activeRule.id]?.ruleVersionId || undefined) : undefined}
        ruleName={activeRule?.name || ''}
        ruleExpression={activeRule?.expression || ''}
        currentAttributeIds={activeModalRule ? (ruleAttributeMappings[activeModalRule] || []) : []}
        currentAliasMappings={(activeRule as any)?.aliasMappings || {}}
        onClose={closeActiveModal}
        checkType={activeRule?.checkType}
        defaultThreshold={
          activeRule?.checkType === 'THRESHOLD'
            ? (activeRule?.checkTypeParams as any)?.threshold
            : undefined
        }
        currentThresholdOverrides={activeModalRule ? ruleAttributeThresholds[activeModalRule] : undefined}
        onSave={handleAssignAttributes}
      />

      <JoinConditionsModal
        isOpen={activeModalType === 'join'}
        ruleName={activeRule?.name || ''}
        workspaceId={resolvedWorkspaceId || undefined}
        currentJoinConditions={activeRule?.joinConditions || []}
        onClose={closeActiveModal}
        onOpenDataAssets={onOpenDataAssets || (() => undefined)}
        onSave={handleSaveJoinConditions}
      />

      <ReusableFiltersModal
        isOpen={activeModalType === 'filter'}
        workspaceId={resolvedWorkspaceId || undefined}
        ruleName={activeRule?.name}
        currentFilterIds={activeRule?.reusableFilterIds ?? []}
        onClose={closeActiveModal}
        onAssignToRule={activeModalRule && !activeModalReadOnly ? handleAssignReusableFilter : undefined}
        readOnly={activeModalReadOnly}
      />

      <ReusableJoinsModal
        isOpen={activeModalType === 'reusable-join'}
        workspaceId={resolvedWorkspaceId || undefined}
        ruleName={activeRule?.name}
        currentJoinId={activeRule?.reusableJoinId ?? null}
        onClose={closeActiveModal}
        onAssignToRule={activeModalRule && !activeModalReadOnly ? handleAssignReusableJoin : undefined}
        readOnly={activeModalReadOnly}
      />

      <TestRuleModal
        isOpen={activeModalType === 'test'}
        ruleName={activeRule?.name || ''}
        ruleId={activeModalRule || ''}
        versionId={''}
        ruleExpression={activeRule?.expression || ''}
        assignedAttributes={activeRuleAssignedAttributes}
        hasJoinConditions={activeRule?.joinConditions && activeRule.joinConditions.length > 0}
        onClose={closeActiveModal}
        onTest={handleTestRule}
      />

      <AdhocRuleExecutionModal
        isOpen={activeModalType === 'adhoc-run'}
        onClose={closeActiveModal}
        mode="rule"
        ruleId={activeModalRule || undefined}
        ruleLabel={activeRule?.name || activeModalRule || ''}
      />

      {validationDiagnosticsModal && (
        <ValidationDiagnosticsModal
          isOpen
          ruleName={validationDiagnosticsModal.ruleName}
          result={validationDiagnosticsModal.result}
          onClose={closeValidationDiagnostics}
        />
      )}

      <TemplatesSelectorModal
        isOpen={showTemplateSelector}
        onClose={closeTemplateWizard}
        onSelectTemplate={handleSelectTemplate}
        validateCheckTypeDraft={validateCheckTypeDraft}
        initialTemplate={templatePreviewData ?? undefined}
        initialCustomizations={templateInitialCustomizations}
        isEditMode={Boolean(editingRuleId)}
        attributeOptions={Object.values(attributeCatalog).map((item) => ({
          id: item.id,
          name: item.name,
          versionId: item.versionId,
          dataObjectVersion: item.dataObjectVersion,
          dataObjectName: item.dataObjectName,
        }))}
        existingRuleNames={workspaceRules
          .filter((rule) => !editingRuleId || rule.id !== editingRuleId)
          .map((rule) => rule.name)}
      />

      <RuleDetailsModal
        isOpen={Boolean(testDetailsRuleId)}
        onClose={closeTestDetails}
        ruleId={testDetailsRuleId}
      />

      <OnboardingRuleScopeSelector
        isOpen={isOnboardingScopeSelectorOpen}
        onClose={() => setIsOnboardingScopeSelectorOpen(false)}
        workspaceId={resolvedWorkspaceId || ''}
        onProposalsGenerated={handleOnboardingProposalsGenerated}
        initialState={onboardingScopeState}
        onStateChange={setOnboardingScopeState}
      />

      <OnboardingRuleReview
        isOpen={isOnboardingReviewOpen}
        response={onboardingProposalsResponse}
        onClose={() => setIsOnboardingReviewOpen(false)}
        onBackToScopeSelection={() => {
          setIsOnboardingReviewOpen(false)
          setIsOnboardingScopeSelectorOpen(true)
        }}
        isCreatingDrafts={isCreatingOnboardingDrafts}
        onCreateDraftRules={handleOnboardingCreateDraftRules}
        initialUiState={onboardingReviewUiState}
        onUiStateChange={setOnboardingReviewUiState}
      />
    </AppPageShell>
  )
}
