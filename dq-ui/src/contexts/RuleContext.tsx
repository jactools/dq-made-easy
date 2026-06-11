import React, { createContext, useState, useCallback, ReactNode, useEffect, useContext, useRef } from 'react'

// Unwrap paginated { data: [] } envelope or pass through raw arrays
const unwrapPage = (r: any): any[] => Array.isArray(r?.data) ? r.data : (Array.isArray(r) ? r : [])
const sameId = (a: unknown, b: unknown): boolean => String(a) === String(b)
import { Rule, RuleApproval, AuditAction, AuditLogEntry, RuleStats, RuleAttributeThresholds, RuleTestResult } from '../types/rules'
import { SettingsContext } from './SettingsContext'
import { AuthContext, getAuthToken } from './AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { buildRuleDslPayload } from '../utils/ruleDsl'
import { buildRuleValidationFailureResult } from '../utils/ruleValidationErrors'

const getWorkspaceFromStorage = (): string | undefined => {
  try {
    const saved = localStorage.getItem('authState')
    if (saved) {
      const parsed = JSON.parse(saved)
      const ws = parsed?.currentWorkspaceId
      return typeof ws === 'string' && ws.trim() ? ws.trim() : undefined
    }
  } catch {
    // ignore
  }
  return undefined
}

interface RuleContextType {
  rules: Rule[]
  rulesPagination: {
    total: number
    page: number
    limit: number
    totalPages: number
    hasNext: boolean
    hasPrevious: boolean
  }
  approvals: RuleApproval[]
  auditLog: AuditLogEntry[]
  stats: RuleStats | null
  isLoading: boolean
  error: string | null
  ruleAttributeMappings: Record<string,string[]> // ruleId -> attributeId[]
  ruleAttributeThresholds: RuleAttributeThresholds // ruleId -> attributeId -> override threshold
  createRule: (rule: Omit<Rule, 'id' | 'createdAt' | 'updatedAt'>) => Promise<Rule>
  updateRule: (ruleId: string, updates: Partial<Rule>) => Promise<Rule>
  updateRuleStatus: (ruleId: string, newStatus: Rule['status']) => Promise<void>
  submitForApproval: (ruleId: string, comments?: string) => Promise<void>
  requestRuleDeactivation: (ruleId: string, comments?: string) => Promise<void>
  approveRule: (approvalId: string, comments?: string) => Promise<void>
  rejectRule: (approvalId: string, comments: string) => Promise<void>
  activateRule: (ruleId: string) => Promise<void>
  logTestAction: (ruleId: string, testData: { coverage: number; passed: boolean; recordsTestedCount: number; failuresFound: number; proofData?: any }) => Promise<void>
  applyRuleTestResult: (ruleId: string, testResult: RuleTestResult) => void
  applyStoredTestProof: (ruleId: string, storedProof: any) => void
  saveRuleAsTemplate: (ruleId: string, templateName: string, templateDescription: string) => Promise<void>
  assignAttributesToRule: (ruleId: string, attributeIds: string[], thresholdOverrides?: Record<string, number | undefined>) => Promise<void>
  validateRuleComposition: (ruleId: string) => Promise<any>
  getRulesByWorkspace: (workspaceId: string) => Rule[]
  getApprovalsPending: () => RuleApproval[]
  getAuditTrail: (ruleId?: string) => AuditLogEntry[]
  calculateStats: (workspaceId: string) => RuleStats
  clearError: () => void
  loadRulesPage: (params?: { page?: number; limit?: number; workspace?: string; status?: string; q?: string; owner?: string; updatedSince?: string; updatedBefore?: string }) => Promise<void>
}

export const RuleContext = createContext<RuleContextType | undefined>(undefined)

const normalizeJoinConditions = (value: any) => {
  if (Array.isArray(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

const normalizeReusableFilterIds = (idsValue: any): string[] => {
  if (Array.isArray(idsValue)) {
    return idsValue.map(v => String(v || '').trim()).filter(Boolean)
  }

  if (typeof idsValue === 'string' && idsValue.trim()) {
    try {
      const parsed = JSON.parse(idsValue)
      if (Array.isArray(parsed)) {
        return parsed.map(v => String(v || '').trim()).filter(Boolean)
      }
    } catch {
      // Ignore parse failures.
    }
  }
  return []
}

const normalizeAliasMappings = (value: any): Record<string, any> => {
  if (!value) return {}

  const parsed = typeof value === 'string'
    ? (() => {
        try {
          return JSON.parse(value)
        } catch {
          return {}
        }
      })()
    : value

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return {}
  }

  return Object.entries(parsed).reduce<Record<string, any>>((acc, [alias, mapping]) => {
    const normalizedAlias = String(alias || '').trim()
    if (!normalizedAlias) return acc

    if (mapping && typeof mapping === 'object' && !Array.isArray(mapping)) {
      const attributeId = String((mapping as any).attributeId || '').trim()
      if (!attributeId) return acc
      acc[normalizedAlias] = {
        attributeId,
        expectedDataType: (mapping as any).expectedDataType ? String((mapping as any).expectedDataType) : undefined,
        actualDataType: (mapping as any).actualDataType ? String((mapping as any).actualDataType) : undefined,
        compatible: typeof (mapping as any).compatible === 'boolean' ? (mapping as any).compatible : undefined,
      }
    }
    return acc
  }, {})
}

const toFiniteNumber = (value: unknown, fallback = 0): number => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

const normalizeRuleTestStatus = (
  value: unknown,
  fallback: RuleTestResult['status'] = 'failed',
): RuleTestResult['status'] => {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'running') {
    return 'pending'
  }
  if (normalized === 'passed' || normalized === 'failed' || normalized === 'pending') {
    return normalized
  }
  return fallback
}

const getRuleTestResultTimestamp = (value?: Partial<RuleTestResult> | null): number => {
  if (!value?.testDate) {
    return 0
  }
  const timestamp = new Date(String(value.testDate)).getTime()
  return Number.isFinite(timestamp) ? timestamp : 0
}

const chooseNewerRuleTestResult = (
  current?: RuleTestResult,
  incoming?: RuleTestResult,
): RuleTestResult | undefined => {
  if (!incoming) {
    return current
  }
  if (!current) {
    return incoming
  }

  const currentTimestamp = getRuleTestResultTimestamp(current)
  const incomingTimestamp = getRuleTestResultTimestamp(incoming)

  if (String(current.id || '') === String(incoming.id || '')) {
    if (current.status === 'pending' && incoming.status !== 'pending') {
      return incoming
    }
    if (incoming.status === 'pending' && current.status !== 'pending') {
      return current
    }
    return incomingTimestamp >= currentTimestamp ? incoming : current
  }

  if (current.status === 'pending' && currentTimestamp >= incomingTimestamp) {
    return current
  }

  return incomingTimestamp >= currentTimestamp ? incoming : current
}

const sortRuleTestResults = (results: RuleTestResult[]): RuleTestResult[] => {
  return results
    .slice()
    .sort((left, right) => getRuleTestResultTimestamp(right) - getRuleTestResultTimestamp(left))
}

const mergeRuleTestResultsHistory = (
  current: RuleTestResult[] | undefined,
  incoming: RuleTestResult[] | undefined,
): RuleTestResult[] => {
  const mergedById = new Map<string, RuleTestResult>()

  for (const result of current || []) {
    const resultId = String(result.id || '').trim()
    if (resultId) {
      mergedById.set(resultId, result)
    }
  }

  for (const result of incoming || []) {
    const resultId = String(result.id || '').trim()
    if (!resultId) {
      continue
    }
    mergedById.set(resultId, chooseNewerRuleTestResult(mergedById.get(resultId), result) || result)
  }

  return sortRuleTestResults(Array.from(mergedById.values()))
}

const getLatestRuleTestResult = (history: RuleTestResult[] | undefined): RuleTestResult | undefined => {
  const sortedHistory = sortRuleTestResults(history || [])
  return sortedHistory[0]
}

const buildRuleTestResult = (
  ruleId: string,
  source: any,
  fallback?: Partial<RuleTestResult>,
): RuleTestResult => {
  const fallbackStatus = normalizeRuleTestStatus(fallback?.status, 'failed')
  const status = typeof source?.passed === 'boolean'
    ? (source.passed ? 'passed' : 'failed')
    : normalizeRuleTestStatus(source?.status, fallbackStatus)

  return {
    id: String(source?.proofId || source?.id || fallback?.id || `test-${Date.now()}`),
    ruleId,
    testDate: String(source?.testDate || fallback?.testDate || new Date().toISOString()),
    status,
    coverage: toFiniteNumber(source?.coverage, toFiniteNumber(fallback?.coverage, 0)),
    recordsTestedCount: toFiniteNumber(source?.recordsTestedCount, toFiniteNumber(fallback?.recordsTestedCount, 0)),
    failuresFound: toFiniteNumber(source?.failuresFound, toFiniteNumber(fallback?.failuresFound, 0)),
    failureDetails:
      (typeof source?.failureDetails === 'string' && source.failureDetails.trim())
      || (typeof fallback?.failureDetails === 'string' && fallback.failureDetails.trim())
      || (typeof source?.proofData?.error === 'string' && source.proofData.error.trim())
      || (typeof fallback?.proofData?.error === 'string' && fallback.proofData.error.trim())
      || undefined,
    proofData: source?.proofData ?? fallback?.proofData ?? {},
    metrics: source?.metrics ?? fallback?.metrics ?? null,
    diagnostics: source?.diagnostics ?? fallback?.diagnostics ?? null,
  }
}

const normalizeApproval = (approval: any): RuleApproval => {
  const normalized = snakeToCamel<any>(approval || {})
  const rawRequestType = String(
    normalized?.requestType
      ?? normalized?.request_type
      ?? approval?.requestType
      ?? approval?.request_type
      ?? 'activation'
  ).trim()
  const requestType = rawRequestType === 'deactivation' || rawRequestType === 'gx_suite_repair' ? rawRequestType : 'activation'
  const rawEffectiveStatus = String(
    normalized?.effectiveStatus
      ?? normalized?.effective_status
      ?? approval?.effectiveStatus
      ?? approval?.effective_status
      ?? ''
  ).trim()
  const effectiveStatus = rawEffectiveStatus || (requestType === 'activation' ? 'activated' : requestType === 'deactivation' ? 'deactivated' : undefined)
  return {
    id: String(normalized?.id ?? approval?.id ?? ''),
    ruleId: String(normalized?.ruleId ?? normalized?.rule_id ?? approval?.ruleId ?? approval?.rule_id ?? '').trim(),
    effectiveStatus: effectiveStatus as RuleApproval['effectiveStatus'],
    requesterId: String(normalized?.requesterId ?? normalized?.requester_id ?? approval?.requesterId ?? approval?.requester_id ?? '').trim(),
    requestedAt: String(normalized?.requestedAt ?? normalized?.requested_at ?? approval?.requestedAt ?? approval?.requested_at ?? ''),
    reviewedBy: normalized?.reviewedBy ?? normalized?.reviewed_by ?? approval?.reviewedBy ?? approval?.reviewed_by,
    reviewedAt: normalized?.reviewedAt ?? normalized?.reviewed_at ?? approval?.reviewedAt ?? approval?.reviewed_at,
    status: (normalized?.status || approval?.status || 'pending') as RuleApproval['status'],
    requestType,
    comments: normalized?.comments ?? approval?.comments,
    commentThread: normalized?.commentThread ?? normalized?.comment_thread,
    history: normalized?.history,
    emailNotifications: normalized?.emailNotifications ?? normalized?.email_notifications,
    teamsNotifications: normalized?.teamsNotifications ?? normalized?.teams_notifications,
    delegation: normalized?.delegation,
    workspaceId: String(normalized?.workspaceId ?? normalized?.workspace_id ?? approval?.workspaceId ?? approval?.workspace_id ?? ''),
  }
}

const normalizeAuditLogEntry = (row: any, approvals: RuleApproval[], rules: Rule[]): AuditLogEntry | null => {
  const normalized = snakeToCamel<any>(row || {})
  const details = snakeToCamel<any>(normalized?.details || {})
  const approvalId = String(normalized?.approvalId ?? normalized?.approval_id ?? '').trim()
  const approval = approvals.find((item) => sameId(item.id, approvalId))

  const ruleId = String(
    normalized?.ruleId
      ?? normalized?.rule_id
      ?? details?.ruleId
      ?? details?.rule_id
      ?? approval?.ruleId
      ?? approvalId
      ?? ''
  ).trim()
  const rule = rules.find((item) => sameId(item.id, ruleId))

  const userId = String(
    normalized?.userId
      ?? normalized?.user_id
      ?? normalized?.actorId
      ?? normalized?.actor_id
      ?? details?.reviewedById
      ?? details?.reviewed_by_id
      ?? approval?.requesterId
      ?? rule?.createdBy
      ?? ''
  ).trim()
  const userName = String(
    normalized?.userName
      ?? normalized?.user_name
      ?? details?.reviewedBy
      ?? details?.reviewed_by
      ?? details?.reviewedByName
      ?? details?.reviewed_by_name
      ?? userId
      ?? ''
  ).trim()
  const workspaceId = String(
    normalized?.workspaceId
      ?? normalized?.workspace_id
      ?? details?.workspaceId
      ?? details?.workspace_id
      ?? approval?.workspaceId
      ?? rule?.workspace
      ?? 'default'
  ).trim() || 'default'
  const timestamp = String(normalized?.timestamp ?? '').trim()
  const action = String(normalized?.action ?? '').trim()
  const id = String(normalized?.id ?? '').trim()

  if (!action || !timestamp || !id) {
    return null
  }

  return {
    id,
    ruleId,
    action: action as AuditAction,
    userId: userId || userName || 'system',
    userName: userName || userId || 'system',
    timestamp,
    details,
    workspaceId,
  }
}

const buildMockRules = (): Rule[] => {
  // No mock data - all data should come from the API/database
  return []
}

export const RuleProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const settings = useContext(SettingsContext)
  const authContext = useContext(AuthContext)
  const rulebuilderApiBase = toApiGroupV1Base('rulebuilder', settings?.applicationSettings?.apiBaseUrl)
  const dataCatalogApiBase = toApiGroupV1Base('data-catalog', settings?.applicationSettings?.apiBaseUrl)

  const getCurrentReviewer = useCallback((): string => {
    try {
      const saved = localStorage.getItem('authState')
      if (saved) {
        const parsed = JSON.parse(saved)
        const user = parsed?.user
        if (typeof user?.name === 'string' && user.name.trim()) return user.name
        if (typeof user?.email === 'string' && user.email.trim()) return user.email
        if (typeof user?.id === 'string' && user.id.trim()) return user.id
      }
    } catch {
      // Ignore and fall back.
    }
    return 'current-user'
  }, [])
  
  const [rules, setRules] = useState<Rule[]>([])
  const [rulesPagination, setRulesPagination] = useState({
    total: 0,
    page: 1,
    limit: 20,
    totalPages: 0,
    hasNext: false,
    hasPrevious: false,
  })
  const [approvals, setApprovals] = useState<RuleApproval[]>([])
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([])
  const [ruleAttributeMappings, setRuleAttributeMappings] = useState<Record<string, string[]>>({})
  const [ruleAttributeThresholds, setRuleAttributeThresholds] = useState<RuleAttributeThresholds>({})
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken())
  const hasLoadedRulesFromDatabaseRef = useRef(false)
  const hasLoadedApprovalsFromDatabaseRef = useRef(false)
  const hasAuthenticatedSession = Boolean(authContext?.isAuthenticated)
  const canUseAuthenticatedRequests = Boolean(authToken)

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

  const getRequestHeaders = useCallback((includeJson = false): HeadersInit => {
    const token = authToken || getAuthToken()

    return {
      ...(includeJson ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
  }, [authToken])

  const normalizeDbRule = useCallback((dbRule: any): Rule => {
    const normalizedReusableFilterIds = normalizeReusableFilterIds(
      dbRule.reusableFilterIds ?? dbRule.reusable_filter_ids,
    )
    const normalizedReusableFilters = Array.isArray(dbRule.reusableFilters)
      ? dbRule.reusableFilters
      : []

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

    const normalizedCreatedBy =
      dbRule.created_by ??
      dbRule.createdBy ??
      dbRule.createdby ??
      dbRule.created_by_email ??
      dbRule.createdByEmail ??
      dbRule.created_by_user ??
      dbRule.createdByUser

    const normalizedWorkspaceId = String(dbRule.workspace || '').trim()

    return {
      ...dbRule,
      status: dbRule.status
        ? dbRule.status
        : dbRule.active
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
      testResultsHistory: Array.isArray(dbRule.testResultsHistory) ? dbRule.testResultsHistory : [],
      attributes: Array.isArray(dbRule.attributes) ? dbRule.attributes : [],
      joinConditions: normalizeJoinConditions(dbRule.joinConditions ?? dbRule.join_conditions),
      reusableFilterIds: normalizedReusableFilterIds,
      reusableFilters: normalizedReusableFilters,
      aliasMappings: normalizeAliasMappings(dbRule.aliasMappings ?? dbRule.alias_mappings),
      riskLevel: 'medium' as const,
      validationStatus: (dbRule.validationStatus ?? dbRule.validation_status) as 'valid' | 'invalid' | null | undefined,
      validatedAt: dbRule.validatedAt ?? dbRule.validated_at ?? null,
      checkType: normalizedCheckType as Rule['checkType'],
      checkTypeParams: normalizedCheckTypeParams,
      dsl: dbRule.dsl && typeof dbRule.dsl === 'object' ? dbRule.dsl : undefined,
      createdBy: String(normalizedCreatedBy || '').trim() || undefined,
      workspace: normalizedWorkspaceId || undefined,
      manualOverrideBy: dbRule.manualOverrideBy ?? dbRule.manual_override_by ?? undefined,
      manualOverrideAt: dbRule.manualOverrideAt ?? dbRule.manual_override_at ?? undefined,
      currentVersionNumber:
        Number(dbRule.currentVersionNumber ?? dbRule.current_version_number ?? dbRule.total_versions ?? 0) || 0,
      pendingDeactivationRequested: Boolean(
        dbRule.pendingDeactivationRequested ?? dbRule.pending_deactivation_requested ?? false,
      ),
    }
  }, [])

  const applyRuleTestResult = useCallback((ruleId: string, testResult: RuleTestResult): void => {
    setRules(prev =>
      prev.map(rule =>
        rule.id === ruleId
          ? (() => {
              const mergedHistory = mergeRuleTestResultsHistory(rule.testResultsHistory, [testResult])
              const latestTestResult = getLatestRuleTestResult(mergedHistory) || testResult
              return {
                ...rule,
                testResults: latestTestResult,
                testResultsHistory: mergedHistory,
                updatedAt: String(latestTestResult.testDate || new Date().toISOString()),
              }
            })()
          : rule,
      ),
    )
  }, [])

  const loadLatestTestProofs = useCallback(
    async (loadedRules: Rule[]): Promise<void> => {
      if (!canUseAuthenticatedRequests || loadedRules.length === 0) {
        return
      }

      try {
        const latestProofs = await Promise.all(
          loadedRules.map(async (rule) => {
            const response = await fetch(`${rulebuilderApiBase}/test-proofs/${encodeURIComponent(String(rule.id))}`, {
              headers: getRequestHeaders(),
            })

            if (!response.ok) {
              return null
            }

            const proofs = snakeToCamel<any[]>(await response.json())
            if (!Array.isArray(proofs) || proofs.length === 0) {
              return null
            }

            return {
              ruleId: String(rule.id),
              testResults: proofs.map((proof) => buildRuleTestResult(String(rule.id), proof)),
            }
          }),
        )

        const latestByRuleId = new Map<string, RuleTestResult[]>()
        latestProofs.forEach((entry) => {
          if (entry?.ruleId && entry.testResults) {
            latestByRuleId.set(entry.ruleId, entry.testResults)
          }
        })

        if (latestByRuleId.size === 0) {
          return
        }

        setRules(prev =>
          prev.map(rule => {
            const history = latestByRuleId.get(String(rule.id))
            if (!history) {
              return rule
            }

            const mergedHistory = mergeRuleTestResultsHistory(rule.testResultsHistory, history)
            const latestTestResult = getLatestRuleTestResult(mergedHistory)
            if (!latestTestResult) {
              return rule
            }

            return {
              ...rule,
              testResults: latestTestResult,
              testResultsHistory: mergedHistory,
              updatedAt: String(latestTestResult.testDate || rule.updatedAt || new Date().toISOString()),
            }
          }),
        )
      } catch (error) {
        console.error('Error loading latest test proofs:', error)
      }
    },
    [rulebuilderApiBase, canUseAuthenticatedRequests, getRequestHeaders],
  )

  const loadRulesPage = useCallback(
    async (params?: { page?: number; limit?: number; workspace?: string; status?: string; q?: string; owner?: string; updatedSince?: string; updatedBefore?: string }): Promise<void> => {
      if (!canUseAuthenticatedRequests) {
        if (hasAuthenticatedSession || hasLoadedRulesFromDatabaseRef.current) {
          setIsLoading(false)
          return
        }
        setRules(buildMockRules())
        setRulesPagination({
          total: 0,
          page: 1,
          limit: params?.limit || 20,
          totalPages: 0,
          hasNext: false,
          hasPrevious: false,
        })
        setIsLoading(false)
        return
      }

      const page = Math.max(1, Number(params?.page || 1))
      const limit = Math.max(1, Math.min(100, Number(params?.limit || 20)))

      const queryParams = new URLSearchParams({
        page: String(page),
        limit: String(limit),
      })
      const workspace = String(params?.workspace || '').trim()
      if (workspace) {
        queryParams.set('workspace', workspace)
      }
      const status = String(params?.status || '').trim()
      if (status) {
        queryParams.set('status', status)
      }
      const q = String(params?.q || '').trim()
      if (q) {
        queryParams.set('q', q)
      }
      const owner = String(params?.owner || '').trim()
      if (owner) {
        queryParams.set('owner', owner)
      }
      const updatedSince = String(params?.updatedSince || '').trim()
      if (updatedSince) {
        queryParams.set('updated_since', updatedSince)
      }
      const updatedBefore = String(params?.updatedBefore || '').trim()
      if (updatedBefore) {
        queryParams.set('updated_before', updatedBefore)
      }

      setIsLoading(true)
      try {
        const response = await fetch(`${rulebuilderApiBase}/rules?${queryParams.toString()}`, {
          headers: getRequestHeaders(),
        })
        if (!response.ok) {
          if (response.status === 401) {
            throw new Error('Unauthorized while fetching rules')
          }
          throw new Error('Failed to fetch rules from database')
        }

        const payload = await response.json()
        const data = unwrapPage(payload)
        const transformedRules = Array.isArray(data) ? data.map(normalizeDbRule) : []

        setRules((prev) => {
          const mergedById = new Map<string, Rule>()

          // Keep previously loaded rules so scope switches and paged loads do not
          // temporarily drop entities that are outside the current page payload.
          prev.forEach((rule) => {
            mergedById.set(String(rule.id), rule)
          })

          transformedRules.forEach((rule) => {
            const existingRule = mergedById.get(String(rule.id))
            const preservedHistory = mergeRuleTestResultsHistory(existingRule?.testResultsHistory, rule.testResultsHistory)
            const preservedTestResults = chooseNewerRuleTestResult(
              existingRule?.testResults,
              rule.testResults || getLatestRuleTestResult(preservedHistory),
            )
            mergedById.set(
              String(rule.id),
              preservedTestResults || preservedHistory.length > 0
                ? {
                    ...rule,
                    testResults: preservedTestResults || getLatestRuleTestResult(preservedHistory),
                    testResultsHistory: preservedHistory,
                  }
                : rule,
            )
          })

          return Array.from(mergedById.values())
        })
        setRulesPagination({
          total: Number(payload?.pagination?.total || transformedRules.length || 0),
          page: Number(payload?.pagination?.page || page),
          limit: Number(payload?.pagination?.limit || limit),
          totalPages: Number(payload?.pagination?.totalPages || 0),
          hasNext: Boolean(payload?.pagination?.hasNext),
          hasPrevious: Boolean(payload?.pagination?.hasPrevious),
        })
        hasLoadedRulesFromDatabaseRef.current = true
        setIsLoading(false)
        void loadLatestTestProofs(transformedRules)
      } catch (fetchError) {
        console.error('Error fetching rules:', fetchError)
        setRules(buildMockRules())
        setRulesPagination({
          total: 0,
          page,
          limit,
          totalPages: 0,
          hasNext: false,
          hasPrevious: false,
        })
        setIsLoading(false)
      }
    },
    [rulebuilderApiBase, canUseAuthenticatedRequests, getRequestHeaders, loadLatestTestProofs, normalizeDbRule, hasAuthenticatedSession]
  )

  // Load initial page from database, scoped to the current workspace when known.
  // Use currentWorkspaceId from AuthContext (always in sync) rather than reading
  // from localStorage which may not yet be written when this effect fires.
  const currentWorkspaceId = authContext?.currentWorkspaceId ?? undefined
  useEffect(() => {
    void loadRulesPage({ page: 1, limit: 20, workspace: currentWorkspaceId || getWorkspaceFromStorage() })
  }, [loadRulesPage, currentWorkspaceId])

  // Load approvals from database
  useEffect(() => {
    const fetchApprovals = async () => {
      if (!canUseAuthenticatedRequests) {
        if (hasAuthenticatedSession || hasLoadedApprovalsFromDatabaseRef.current) {
          return
        }
        setApprovals([])
        return
      }

      try {
        const response = await fetch(`${rulebuilderApiBase}/approvals`, {
          headers: getRequestHeaders(),
        })
        if (!response.ok) {
          // A stale token can briefly happen during auth transitions; avoid noisy console errors.
          if (response.status === 401) {
            throw new Error('Unauthorized while fetching approvals')
          }
          console.error('Failed to fetch approvals from database')
          setApprovals([])
          return
        }
        const data = unwrapPage(await response.json())
        const normalizedApprovals = data.map(normalizeApproval)
        hasLoadedApprovalsFromDatabaseRef.current = true
        setApprovals(normalizedApprovals)
      } catch (error) {
        console.error('Error fetching approvals:', error)
        setApprovals([])
      }
    }

    fetchApprovals()
  }, [rulebuilderApiBase, canUseAuthenticatedRequests, getRequestHeaders, hasAuthenticatedSession])

  // Load audit log from database
  useEffect(() => {
    const fetchAuditLog = async () => {
      if (!canUseAuthenticatedRequests) {
        setAuditLog([])
        return
      }

      try {
        const response = await fetch(`${rulebuilderApiBase}/approvals/audit`, {
          headers: getRequestHeaders(),
        })
        if (!response.ok) {
          // A stale token can briefly happen during auth transitions; avoid noisy console errors.
          if (response.status === 401) {
            setAuditLog([])
            return
          }
          console.error('Failed to fetch audit log from database')
          setAuditLog([])
          return
        }
        const data = await response.json()
        const normalizedAuditLog = Array.isArray(data)
          ? data
              .map((entry) => normalizeAuditLogEntry(entry, approvals, rules))
              .filter((entry): entry is AuditLogEntry => entry !== null)
          : []
        setAuditLog(normalizedAuditLog)
      } catch (error) {
        console.error('Error fetching audit log:', error)
        setAuditLog([])
      }
    }

    fetchAuditLog()
  }, [approvals, canUseAuthenticatedRequests, getRequestHeaders, rulebuilderApiBase, rules])

  // Load rule-attribute mappings from database
  useEffect(() => {
    const fetchRuleAttributeMappings = async () => {
      if (!canUseAuthenticatedRequests) {
        setRuleAttributeMappings({})
        setRuleAttributeThresholds({})
        return
      }

      try {
        const response = await fetch(`${dataCatalogApiBase}/rule-attributes`, {
          headers: getRequestHeaders(),
        })
        if (!response.ok) {
          // A stale token can briefly happen during auth transitions; avoid noisy console errors.
          if (response.status === 401) {
            setRuleAttributeMappings({})
            setRuleAttributeThresholds({})
            return
          }
          console.error('Failed to fetch rule-attribute mappings')
          return
        }
        const body = await response.json()
        const data = unwrapPage(body)
        // Transform array to map: ruleId -> attributeIds[]
        const mappings: Record<string, string[]> = {}
        const thresholds: RuleAttributeThresholds = {}
        data.forEach((item: {
          ruleid?: string
          attributeid?: string
          ruleId?: string
          attributeId?: string
          threshold_override?: number | null
          thresholdOverride?: number | null
        }) => {
          const ruleId = item.ruleid || item.ruleId
          const attrId = item.attributeid || item.attributeId
          const thresholdOverride = item.threshold_override ?? item.thresholdOverride
          if (!ruleId) return // Skip if no ruleId
          if (!mappings[ruleId]) {
            mappings[ruleId] = []
          }
          if (attrId && !mappings[ruleId].includes(attrId)) {
            mappings[ruleId].push(attrId)
          }
          if (attrId && thresholdOverride != null) {
            if (!thresholds[ruleId]) thresholds[ruleId] = {}
            thresholds[ruleId][attrId] = thresholdOverride
          }
        })
        setRuleAttributeMappings(mappings)
        setRuleAttributeThresholds(thresholds)
      } catch (error) {
        console.error('Error fetching rule-attribute mappings:', error)
      }
    }

    fetchRuleAttributeMappings()
  }, [dataCatalogApiBase, canUseAuthenticatedRequests, getRequestHeaders])

  const createRule = useCallback(
    async (rule: Omit<Rule, 'id' | 'createdAt' | 'updatedAt'>): Promise<Rule> => {
      setIsLoading(true)
      setError(null)
      try {
        const requestPayload = camelToSnake({
          name: rule.name,
          description: rule.description,
          comments: rule.comments,
          dimension: rule.dimension,
          active: rule.active,
          workspace: rule.workspace,
          generated: rule.generated,
          isTemplate: (rule as any).isTemplate ?? (rule as any).is_template,
          templateId: (rule as any).templateId ?? (rule as any).template_id,
          suggestionId: rule.suggestionId,
          dsl: buildRuleDslPayload(rule),
        })
        const response = await fetch(`${rulebuilderApiBase}/rules`, {
          method: 'POST',
          headers: getRequestHeaders(true),
          body: JSON.stringify(requestPayload),
        })
        if (!response.ok) {
          let errorDetail = ''
          try {
            const body = await response.json()
            if (typeof body?.detail === 'string') {
              errorDetail = body.detail
            } else {
              errorDetail = JSON.stringify(body)
            }
          } catch {
            try {
              errorDetail = await response.text()
            } catch {
              errorDetail = ''
            }
          }
          const userFeedback =
            response.status === 409
              ? (errorDetail || 'A rule with this name already exists in this workspace.')
              : (errorDetail || `Request failed with status ${response.status}.`)
          setError(userFeedback)
          throw new Error(`Failed to create rule (${response.status}): ${errorDetail || 'No response body'}`)
        }
        const newRuleRaw = await response.json()
        const newRule = normalizeDbRule(newRuleRaw)

        // Confirm the rule can be fetched from the API before finalizing local state.
        // This avoids showing transient client-only rules that were not actually persisted.
        let persistedRule: Rule = newRule
        if (newRule.id) {
          const verifyResponse = await fetch(`${rulebuilderApiBase}/rules/${newRule.id}`, {
            headers: getRequestHeaders(),
          })
          if (!verifyResponse.ok) {
            const verifyBody = await verifyResponse.text().catch(() => '')
            throw new Error(
              `Rule creation could not be confirmed (${verifyResponse.status}): ${verifyBody || 'Rule not found after create.'}`
            )
          }

          const persistedRuleRaw = await verifyResponse.json()
          persistedRule = normalizeDbRule(persistedRuleRaw)
        }

        if (!persistedRule.createdBy) {
          const fallbackCreatedBy = String(
            authContext?.user?.email || authContext?.user?.id || authContext?.user?.name || ''
          ).trim()
          if (fallbackCreatedBy) {
            persistedRule = {
              ...persistedRule,
              createdBy: fallbackCreatedBy,
            }
          }
        }

        const requestedWorkspaceId = String((rule as any).workspace || '').trim()
        if (!persistedRule.workspace && requestedWorkspaceId) {
          persistedRule = {
            ...persistedRule,
            workspace: requestedWorkspaceId,
          } as Rule
        }

        setRules((prev) => {
          const existingIndex = prev.findIndex((item) => sameId(item.id, persistedRule.id))
          if (existingIndex >= 0) {
            const next = [...prev]
            next[existingIndex] = persistedRule
            return next
          }
          // Prepend so the new rule is immediately visible at the top of the list.
          return [persistedRule, ...prev]
        })
        setIsLoading(false)
        return persistedRule
      } catch (error) {
        if (error instanceof Error && !error.message.includes('(409)')) {
          setError(error.message)
        }
        setIsLoading(false)
        // Refresh the list so any rule that was committed server-side before an
        // error (e.g. old DetachedInstanceError 500s) becomes visible immediately.
        loadRulesPage().catch(() => undefined)
        throw error
      }
    },
    [rulebuilderApiBase, getRequestHeaders, normalizeDbRule, loadRulesPage]
  )

  const updateRule = useCallback(
    async (ruleId: string, updates: Partial<Rule>): Promise<Rule> => {
      const existingRule = rules.find(rule => rule.id === ruleId)
      if (!existingRule) {
        throw new Error(`Rule not found: ${ruleId}`)
      }

      const mergedRule = {
        name: updates.name ?? existingRule.name ?? '',
        description: updates.description ?? existingRule.description ?? '',
        comments: updates.comments ?? existingRule.comments ?? '',
        expression: updates.expression ?? existingRule.expression ?? '',
        dimension: updates.dimension ?? existingRule.dimension ?? '',
        active: typeof updates.active === 'boolean' ? updates.active : !!existingRule.active,
        generated:
          typeof updates.generated === 'boolean'
            ? updates.generated
            : (typeof existingRule.generated === 'boolean' ? existingRule.generated : undefined),
        workspace: updates.workspace ?? existingRule.workspace,
        joinConditions: updates.joinConditions ?? existingRule.joinConditions ?? [],
        reusableFilterIds:
          updates.reusableFilterIds !== undefined
            ? updates.reusableFilterIds
            : existingRule.reusableFilterIds ?? [],
        aliasMappings:
          updates.aliasMappings !== undefined
            ? updates.aliasMappings
            : existingRule.aliasMappings ?? {},
        checkType: updates.checkType ?? existingRule.checkType ?? null,
        checkTypeParams: updates.checkTypeParams ?? existingRule.checkTypeParams ?? null,
        reusableJoinId:
          updates.reusableJoinId !== undefined
            ? updates.reusableJoinId
            : existingRule.reusableJoinId ?? null,
        manualOverrideConfirmed:
          typeof updates.manualOverrideConfirmed === 'boolean'
            ? updates.manualOverrideConfirmed
            : existingRule.manualOverrideConfirmed,
      }

      const payload = {
        name: mergedRule.name,
        description: mergedRule.description,
        comments: mergedRule.comments,
        dimension: mergedRule.dimension,
        active: mergedRule.active,
        generated: mergedRule.generated,
        workspace: mergedRule.workspace,
        dsl: buildRuleDslPayload(mergedRule as Rule),
      }

      const response = await fetch(`${rulebuilderApiBase}/rules/${ruleId}`, {
        method: 'PUT',
        headers: getRequestHeaders(true),
        body: JSON.stringify(camelToSnake(payload)),
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Failed to update rule (${response.status}): ${errorText || 'No response body'}`)
      }

      const updatedFromApiRaw = await response.json()
      const updatedFromApi = normalizeDbRule(updatedFromApiRaw)
      const normalizedJoinConditions = normalizeJoinConditions(updatedFromApi.joinConditions)
      const normalizedReusableFilterIds = normalizeReusableFilterIds(updatedFromApi.reusableFilterIds)
      const normalizedReusableFilters = Array.isArray(updatedFromApi.reusableFilters)
        ? updatedFromApi.reusableFilters
        : []

      let updatedRule: Rule = existingRule
      setRules(prev =>
        prev.map(rule => {
          if (rule.id !== ruleId) return rule
          updatedRule = {
            ...rule,
            ...updatedFromApi,
            ...updates,
            comments: updatedFromApi.comments ?? updates.comments ?? rule.comments,
            joinConditions: normalizedJoinConditions,
            reusableFilterIds: normalizedReusableFilterIds,
            reusableFilters: normalizedReusableFilters,
            aliasMappings: normalizeAliasMappings(updatedFromApi.aliasMappings ?? updates.aliasMappings ?? rule.aliasMappings),
            updatedAt: new Date().toISOString(),
          }
          return updatedRule
        })
      )

      return updatedRule
    },
    [rulebuilderApiBase, getRequestHeaders, normalizeDbRule, rules]
  )

  const updateRuleStatus = useCallback(async (ruleId: string, newStatus: Rule['status']): Promise<void> => {
    try {
      // Update local state only - status is not persisted in backend
      setRules(prev =>
        prev.map(rule =>
          rule.id === ruleId
            ? {
                ...rule,
                status: newStatus,
                updatedAt: new Date().toISOString(),
              }
            : rule
        )
      )
    } catch (error) {
      console.error('Error updating rule status:', error)
      throw error
    }
  }, [rulebuilderApiBase])

  const submitForApproval = useCallback(
    async (ruleId: string, comments?: string): Promise<void> => {
      const existingRule = rules.find(rule => rule.id === ruleId)
      if (!existingRule) {
        throw new Error(`Rule not found: ${ruleId}`)
      }
      setIsLoading(true)
      try {
        const response = await fetch(`${rulebuilderApiBase}/approvals`, {
          method: 'POST',
          headers: getRequestHeaders(true),
          body: JSON.stringify(camelToSnake({ ruleId, comments, workspace: existingRule.workspace, workspaceId: existingRule.workspace })),
        })
        if (!response.ok) {
          throw new Error('Failed to submit for approval')
        }
        const newApproval = normalizeApproval(await response.json())
        setApprovals(prev => [...prev, newApproval])
        
        // Update rule status
        setRules(prev =>
          prev.map(rule =>
            rule.id === ruleId
              ? {
                  ...rule,
                  status: 'pending-approval',
                  updatedAt: new Date().toISOString(),
                }
              : rule
          )
        )
        setIsLoading(false)
      } catch (error) {
        console.error('Error submitting for approval:', error)
        setIsLoading(false)
        throw error
      }
    },
    [rulebuilderApiBase, getRequestHeaders, rules]
  )

  const requestRuleDeactivation = useCallback(
    async (ruleId: string, comments?: string): Promise<void> => {
      const existingRule = rules.find(rule => rule.id === ruleId)
      if (!existingRule) {
        throw new Error(`Rule not found: ${ruleId}`)
      }
      const token = authToken || getAuthToken()
      if (!token) {
        throw new Error('Authentication token is not available yet. Please try again after login completes.')
      }
      setIsLoading(true)
      try {
        const response = await fetch(`${rulebuilderApiBase}/approvals`, {
          method: 'POST',
          headers: getRequestHeaders(true),
          body: JSON.stringify(camelToSnake({ ruleId, comments, requestType: 'deactivation', workspace: existingRule.workspace, workspaceId: existingRule.workspace })),
        })
        if (!response.ok) {
          throw new Error('Failed to request rule deactivation')
        }
        const newApproval = normalizeApproval(await response.json())
        setApprovals(prev => [...prev, newApproval])
        setRules(prev =>
          prev.map(rule =>
            rule.id === ruleId
              ? {
                  ...rule,
                  updatedAt: new Date().toISOString(),
                }
              : rule
          )
        )
        setIsLoading(false)
      } catch (error) {
        console.error('Error requesting rule deactivation:', error)
        setIsLoading(false)
        throw error
      }
    },
    [authToken, rulebuilderApiBase, getRequestHeaders, rules]
  )

  const approveRule = useCallback(
    async (approvalId: string, comments?: string): Promise<void> => {
      setIsLoading(true)
      try {
        const response = await fetch(`${rulebuilderApiBase}/approvals/${approvalId}`, {
          method: 'PUT',
          headers: getRequestHeaders(true),
          body: JSON.stringify(camelToSnake({ status: 'approved', comments })),
        })
        if (!response.ok) {
          const errorBody = await response.text()
          let errorDetail = errorBody.trim()
          if (errorBody) {
            try {
              const parsedBody = JSON.parse(errorBody)
              errorDetail = String(parsedBody?.detail || parsedBody?.message || errorBody).trim()
            } catch {
              // Keep the raw response text when the body is not JSON.
            }
          }
          throw new Error(errorDetail ? `Failed to approve rule: ${errorDetail}` : 'Failed to approve rule')
        }
        const updatedApproval = await response.json()
        const nextStatus = updatedApproval?.status || 'approved'
        const reviewedAt = updatedApproval?.reviewedAt || new Date().toISOString()
        const reviewedBy =
          updatedApproval?.reviewedBy ||
          updatedApproval?.reviewed_by ||
          updatedApproval?.reviewerId ||
          updatedApproval?.actorId ||
          getCurrentReviewer()
        
        const approval = approvals.find(a => sameId(a.id, approvalId))
        
        // Update approval
        setApprovals(prev =>
          prev.map(a =>
            sameId(a.id, approvalId)
              ? {
                  ...a,
                  status: nextStatus,
                  reviewedBy,
                  reviewedAt,
                  comments,
                }
              : a
          )
        )

        // Update rule status
        if (approval) {
          const requestType = approval.requestType || 'activation'
          if (requestType === 'activation' || requestType === 'deactivation') {
            setRules(prev =>
              prev.map(rule =>
                sameId(rule.id, approval.ruleId)
                  ? {
                      ...rule,
                      status:
                        requestType === 'deactivation'
                          ? (nextStatus === 'approved' ? 'deactivated' : 'activated')
                          : (nextStatus === 'approved' ? 'approved' : 'rejected'),
                      active: requestType === 'deactivation' ? false : rule.active,
                      last_approval_status:
                        requestType === 'deactivation'
                          ? (nextStatus === 'approved' ? 'deactivated' : rule.last_approval_status)
                          : nextStatus,
                      last_approval_by: reviewedBy,
                      last_approval_at: reviewedAt,
                      updatedAt: reviewedAt,
                    }
                  : rule
              )
            )
          }
        }
        setIsLoading(false)
      } catch (error) {
        console.error('Error approving rule:', error)
        setIsLoading(false)
        throw error
      }
    },
    [rulebuilderApiBase, approvals, getCurrentReviewer, getRequestHeaders]
  )

  const rejectRule = useCallback(
    async (approvalId: string, comments: string): Promise<void> => {
      setIsLoading(true)
      try {
        const response = await fetch(`${rulebuilderApiBase}/approvals/${approvalId}`, {
          method: 'PUT',
          headers: getRequestHeaders(true),
          body: JSON.stringify(camelToSnake({ status: 'rejected', comments })),
        })
        if (!response.ok) {
          throw new Error('Failed to reject rule')
        }
        const updatedApproval = await response.json()
        const nextStatus = updatedApproval?.status || 'rejected'
        const reviewedAt = updatedApproval?.reviewedAt || new Date().toISOString()
        const reviewedBy =
          updatedApproval?.reviewedBy ||
          updatedApproval?.reviewed_by ||
          updatedApproval?.reviewerId ||
          updatedApproval?.actorId ||
          getCurrentReviewer()
        
        const approval = approvals.find(a => sameId(a.id, approvalId))

        // Update approval
        setApprovals(prev =>
          prev.map(a =>
            sameId(a.id, approvalId)
              ? {
                  ...a,
                  status: nextStatus,
                  reviewedBy,
                  reviewedAt,
                  comments,
                }
              : a
          )
        )

        // Update rule status
        if (approval) {
          const requestType = approval.requestType || 'activation'
          if (requestType === 'activation' || requestType === 'deactivation') {
            setRules(prev =>
              prev.map(rule =>
                sameId(rule.id, approval.ruleId)
                  ? {
                      ...rule,
                      status: requestType === 'deactivation' ? 'activated' : 'rejected',
                      last_approval_status:
                        requestType === 'deactivation'
                          ? (rule.last_approval_status || 'approved')
                          : nextStatus,
                      last_approval_by: reviewedBy,
                      last_approval_at: reviewedAt,
                      updatedAt: reviewedAt,
                    }
                  : rule
              )
            )
          }
        }
        setIsLoading(false)
      } catch (error) {
        console.error('Error rejecting rule:', error)
        setIsLoading(false)
        throw error
      }
    },
    [rulebuilderApiBase, approvals, getCurrentReviewer, getRequestHeaders]
  )

  const activateRule = useCallback(
    async (ruleId: string): Promise<void> => {
      setIsLoading(true)
      try {
        const response = await fetch(`${rulebuilderApiBase}/rules/${ruleId}/activate`, {
          method: 'POST',
          headers: getRequestHeaders(),
        })
        if (!response.ok) {
          throw new Error('Failed to activate rule')
        }
        
        setRules(prev =>
          prev.map(r =>
            r.id === ruleId
              ? {
                  ...r,
                  status: 'activated',
                  updatedAt: new Date().toISOString(),
                }
              : r
          )
        )
        setIsLoading(false)
      } catch (error) {
        console.error('Error activating rule:', error)
        setIsLoading(false)
        throw error
      }
    },
    [rulebuilderApiBase, getRequestHeaders]
  )

  const logTestAction = useCallback(
    async (ruleId: string, testData: { coverage: number; passed: boolean; recordsTestedCount: number; failuresFound: number; proofData?: any }): Promise<void> => {
      setIsLoading(true)
      try {
        const response = await fetch(`${rulebuilderApiBase}/rules/${ruleId}/test`, {
          method: 'POST',
          headers: getRequestHeaders(true),
          body: JSON.stringify(camelToSnake(testData)),
        })
        if (!response.ok) {
          throw new Error('Failed to log test action')
        }

        const storedProof = snakeToCamel<any>(await response.json())
        applyRuleTestResult(
          ruleId,
          buildRuleTestResult(ruleId, storedProof, {
            coverage: testData.coverage,
            recordsTestedCount: testData.recordsTestedCount,
            failuresFound: testData.failuresFound,
            proofData: testData.proofData,
          }),
        )
        setIsLoading(false)
      } catch (error) {
        console.error('Error logging test action:', error)
        setIsLoading(false)
        throw error
      }
    },
    [rulebuilderApiBase, applyRuleTestResult, getRequestHeaders]
  )

  const applyStoredTestProof = useCallback((ruleId: string, storedProofRaw: any): void => {
    const storedProof = snakeToCamel<any>(storedProofRaw)
    applyRuleTestResult(ruleId, buildRuleTestResult(ruleId, storedProof))
  }, [applyRuleTestResult])

  const saveRuleAsTemplate = useCallback(
    async (ruleId: string, templateName: string, templateDescription: string): Promise<void> => {
      setIsLoading(true)
      try {
        const response = await fetch(`${rulebuilderApiBase}/rules/${ruleId}/template`, {
          method: 'POST',
          headers: getRequestHeaders(true),
          body: JSON.stringify(camelToSnake({ templateName, templateDescription })),
        })
        if (!response.ok) {
          throw new Error('Failed to save rule as template')
        }
        console.log('Template saved:', { templateName, templateDescription, ruleId })
        setIsLoading(false)
      } catch (error) {
        console.error('Error saving rule as template:', error)
        setIsLoading(false)
        throw error
      }
    },
    [rulebuilderApiBase, getRequestHeaders]
  )

  const getRulesByWorkspace = useCallback((workspaceId: string): Rule[] => {
    return rules.filter((r) => r.workspace === workspaceId)
  }, [rules])

  const getApprovalsPending = useCallback((): RuleApproval[] => {
    return approvals.filter(a => a.status === 'pending')
  }, [approvals])

  const getAuditTrail = useCallback(
    (ruleId?: string): AuditLogEntry[] => {
      if (ruleId) {
        return auditLog.filter(entry => sameId(entry.ruleId, ruleId))
      }
      return auditLog
    },
    [auditLog]
  )

  const calculateStats = useCallback((workspaceId: string): RuleStats => {
    const wsRules = rules.filter((r) => r.workspace === workspaceId)
    const awaitingApproval = approvals.filter(
      a => a.status === 'pending' && wsRules.some(r => sameId(r.id, a.ruleId))
    ).length

    const stats: RuleStats = {
      total: wsRules.length,
      byStatus: {
        draft: wsRules.filter(r => r.status === 'draft').length,
        testing: wsRules.filter(r => r.status === 'testing').length,
        tested: wsRules.filter(r => r.status === 'tested').length,
        'pending-approval': wsRules.filter(r => r.status === 'pending-approval').length,
        approved: wsRules.filter(r => r.status === 'approved').length,
        activated: wsRules.filter(r => r.status === 'activated').length,
        deactivated: wsRules.filter(r => r.status === 'deactivated').length,
        rejected: wsRules.filter(r => r.status === 'rejected').length,
      },
      awaitingApproval,
      recentlyActivated: wsRules.filter(r => r.status === 'activated').slice(0, 3).length,
      failedTests: wsRules.filter(r => r.testResults?.status === 'failed').length,
    }
    return stats
  }, [rules, approvals])

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  const assignAttributesToRule = useCallback(
    async (ruleId: string, attributeIds: string[], thresholdOverrides?: Record<string, number | undefined>) => {
      try {
        // Create entries array for the API, including optional per-attribute threshold overrides
        const entries = attributeIds.map((attrId) => {
          const entry: { ruleId: string; attributeId: string; thresholdOverride?: number } = { ruleId, attributeId: attrId }
          const override = thresholdOverrides?.[attrId]
          if (override != null) entry.thresholdOverride = override
          return entry
        })

        // Post to backend
        const response = await fetch(`${dataCatalogApiBase}/rule-attributes`, {
          method: 'POST',
          headers: getRequestHeaders(true),
          body: JSON.stringify(camelToSnake({ entries })),
        })

        if (!response.ok) {
          throw new Error('Failed to assign attributes to rule')
        }

        // Update local state
        setRuleAttributeMappings((prev) => ({
          ...prev,
          [ruleId]: attributeIds,
        }))
        if (thresholdOverrides) {
          setRuleAttributeThresholds((prev) => ({
            ...prev,
            [ruleId]: { ...thresholdOverrides },
          }))
        }
      } catch (error) {
        console.error('Error assigning attributes to rule:', error)
        throw error
      }
    },
    [dataCatalogApiBase, getRequestHeaders]
  )

  const validateRuleComposition = useCallback(
    async (ruleId: string): Promise<any> => {
      const response = await fetch(`${rulebuilderApiBase}/rules/${ruleId}/validate`, {
        method: 'POST',
        headers: getRequestHeaders(),
      })

      if (!response.ok) {
        const errorText = await response.text().catch(() => '')
        if (response.status === 400 || response.status === 422) {
          try {
            const parsedError = errorText ? JSON.parse(errorText) : null
            const validationFailure = buildRuleValidationFailureResult(parsedError)
            if (validationFailure) {
              return validationFailure
            }
          } catch {
            // Fall through to the generic transport error below.
          }
        }

        throw new Error(errorText || `Failed to validate rule (${response.status})`)
      }

      return await response.json()
    },
    [rulebuilderApiBase, getRequestHeaders]
  )

  const value: RuleContextType = {
    rules,
    rulesPagination,
    approvals,
    auditLog,
    stats: null,
    isLoading,
    error,
    createRule,
    updateRule,
    updateRuleStatus,
    submitForApproval,
    requestRuleDeactivation,
    approveRule,
    rejectRule,
    activateRule,
    logTestAction,
    applyRuleTestResult,
    applyStoredTestProof,
    saveRuleAsTemplate,
    getRulesByWorkspace,
    getApprovalsPending,
    getAuditTrail,
    calculateStats,
    clearError,
    loadRulesPage,
    ruleAttributeMappings,
    ruleAttributeThresholds,
    assignAttributesToRule,
    validateRuleComposition,
  }

  return <RuleContext.Provider value={value}>{children}</RuleContext.Provider>
}

export const useRule = () => {
  const context = React.useContext(RuleContext)
  if (context === undefined) {
    throw new Error('useRule must be used within a RuleProvider')
  }
  return context
}
