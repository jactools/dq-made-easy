import React, { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../hooks/useKeycloak'
import { useRules, useSettings } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { snakeToCamel } from '../utils/caseConverters'
import { getDashboardNavigationIntent, navigateFromDashboardCard } from '../utils/dashboardNavigation'
import { getWorkspaceDisplayName } from './WorkspaceSelector'
import { AppIcon, type AppIconName } from './app-primitives'
import type { UserRole } from '../types/keycloak'

const sameId = (a: unknown, b: unknown): boolean => String(a) === String(b)

interface DashboardCard {
  id: string
  title: string
  value: string | number
  icon: AppIconName
  color: 'success' | 'warning' | 'danger' | 'info'
  description: string
  focus: DashboardFocusSectionId
}

interface DashboardData {
  sections: DashboardFocusSection[]
  secondarySummaries: Array<{ id: string; title: string; detail: string; tone: 'success' | 'warning' | 'danger' | 'info' }>
  recentActivity: Array<{ time: string; text: string }>
}

interface DashboardCapabilities {
  canAuthorRules: boolean
  canReviewApprovals: boolean
  canAdminWorkspace: boolean
  canManageGovernance: boolean
  canAccessRuleQuality: boolean
  canAccessExecutionMonitoring: boolean
}

type DashboardFocusSectionId = 'author' | 'approver' | 'operations'

interface DashboardFocusSection {
  id: DashboardFocusSectionId
  title: string
  description: string
  cards: DashboardCard[]
}

interface DashboardWorkflowCounts {
  pendingGovernanceActions: number | null
  profilingActivity: number | null
  catalogDriftActivity: number | null
  failedValidationRuns: number | null
}

const ZERO_COUNT_INDICATOR_ICON: AppIconName = 'info-circle'

interface DashboardProps {
  onNavigate?: (destination: string) => void
}

const buildRequestHeaders = (): Record<string, string> => {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const parseJsonResponse = async (response: Response): Promise<any> => {
  const payload = await response.text()
  if (!payload) {
    return {}
  }

  try {
    return snakeToCamel(JSON.parse(payload))
  } catch {
    return {}
  }
}

const DASHBOARD_FOCUS_CARD_IDS: Record<DashboardFocusSectionId, string[]> = {
  author: ['my-working-rules', 'rejected-rules', 'profiling-activity', 'catalog-drift-activity'],
  approver: ['pending-review', 'pending-deactivation', 'pending-governance-actions'],
  operations: ['active-rules', 'deactivated-rules', 'failed-validation-runs'],
}

const AUTHOR_FOCUS_ROLES = new Set<UserRole>(['analyst', 'data-steward', 'editor'])
const APPROVER_FOCUS_ROLES = new Set<UserRole>(['approver', 'reviewer', 'data-steward', 'governance-admin', 'governance-editor'])
const WORKSPACE_ADMIN_FOCUS_ROLES = new Set<UserRole>(['admin', 'cross-admin'])

const buildDashboardSections = (args: {
  cards: DashboardCard[]
  capabilities: DashboardCapabilities
}): DashboardFocusSection[] => {
  const { cards, capabilities } = args
  const cardById = new Map(cards.map((card) => [card.id, card]))
  const sections: DashboardFocusSection[] = []

  if (capabilities.canAuthorRules || capabilities.canAccessRuleQuality) {
    sections.push({
      id: 'author',
      title: 'Rule Author Focus',
      description: 'Follow authoring work, rejected revisions, and profiling or drift follow-up that can turn into new or updated rules.',
      cards: DASHBOARD_FOCUS_CARD_IDS.author
        .map((cardId) => cardById.get(cardId))
        .filter((card): card is DashboardCard => Boolean(card)),
    })
  }

  if (capabilities.canReviewApprovals || capabilities.canManageGovernance) {
    sections.push({
      id: 'approver',
      title: 'Approver Focus',
      description: 'Keep approval, deactivation, and governance review work visible for the users who own those decisions.',
      cards: DASHBOARD_FOCUS_CARD_IDS.approver
        .map((cardId) => cardById.get(cardId))
        .filter((card): card is DashboardCard => Boolean(card)),
    })
  }

  const workspaceOverviewCardIds = capabilities.canAccessExecutionMonitoring
    ? DASHBOARD_FOCUS_CARD_IDS.operations
    : DASHBOARD_FOCUS_CARD_IDS.operations.filter((cardId) => cardId !== 'failed-validation-runs')

  sections.push({
    id: 'operations',
    title: capabilities.canAdminWorkspace ? 'Workspace Admin Focus' : 'Workspace Overview',
    description: capabilities.canAdminWorkspace
      ? 'Track active coverage, deactivated rules, and failed runs that need workspace-level attention.'
      : capabilities.canAccessExecutionMonitoring
        ? 'Track active coverage, deactivated rules, and failed runs that are relevant in this workspace.'
        : 'Track active coverage and deactivated rules that are relevant in this workspace.',
    cards: workspaceOverviewCardIds
      .map((cardId) => cardById.get(cardId))
      .filter((card): card is DashboardCard => Boolean(card)),
  })

  return sections.filter((section) => section.cards.length > 0)
}

const buildSecondarySummaries = (args: {
  sections: DashboardFocusSection[]
  workspaceId: string | null
}): Array<{ id: string; title: string; detail: string; tone: 'success' | 'warning' | 'danger' | 'info' }> => {
  const { sections, workspaceId } = args
  const cards = sections.flatMap((section) => section.cards)
  const workspaceName = workspaceId ? getWorkspaceDisplayName(workspaceId) : 'this workspace'
  const cardById = new Map(cards.map((card) => [card.id, card]))
  const summaries: Array<{ id: string; title: string; detail: string; tone: 'success' | 'warning' | 'danger' | 'info' }> = []

  const failedRuns = Number(cardById.get('failed-validation-runs')?.value || 0)
  if (failedRuns > 0) {
    summaries.push({
      id: 'failed-validation-runs',
      title: 'Execution Monitoring',
      detail: `${failedRuns} failed validation run${failedRuns === 1 ? '' : 's'} need investigation in ${workspaceName}.`,
      tone: 'danger',
    })
  }

  const pendingGovernanceActions = Number(cardById.get('pending-governance-actions')?.value || 0)
  if (pendingGovernanceActions > 0) {
    summaries.push({
      id: 'pending-governance-actions',
      title: 'Governance Queue',
      detail: `${pendingGovernanceActions} governance action${pendingGovernanceActions === 1 ? '' : 's'} are waiting for review in ${workspaceName}.`,
      tone: 'warning',
    })
  }

  const rejectedRules = Number(cardById.get('rejected-rules')?.value || 0)
  if (rejectedRules > 0) {
    summaries.push({
      id: 'rejected-rules',
      title: 'Rule Revisions',
      detail: `${rejectedRules} rejected rule${rejectedRules === 1 ? '' : 's'} need revision before resubmission in ${workspaceName}.`,
      tone: 'danger',
    })
  }

  const catalogDriftActivity = Number(cardById.get('catalog-drift-activity')?.value || 0)
  if (catalogDriftActivity > 0) {
    summaries.push({
      id: 'catalog-drift-activity',
      title: 'Catalog Drift',
      detail: `${catalogDriftActivity} rule${catalogDriftActivity === 1 ? '' : 's'} with drift still need follow-up in ${workspaceName}.`,
      tone: 'warning',
    })
  }

  const profilingActivity = Number(cardById.get('profiling-activity')?.value || 0)
  if (profilingActivity > 0) {
    summaries.push({
      id: 'profiling-activity',
      title: 'Profiling Follow-up',
      detail: `${profilingActivity} recent profiling request${profilingActivity === 1 ? '' : 's'} may need rule follow-up for ${workspaceName}.`,
      tone: 'info',
    })
  }

  const myWorkingRules = Number(cardById.get('my-working-rules')?.value || 0)
  if (myWorkingRules > 0) {
    summaries.push({
      id: 'my-working-rules',
      title: 'Authoring In Progress',
      detail: `${myWorkingRules} rule${myWorkingRules === 1 ? '' : 's'} you own are still in progress in ${workspaceName}.`,
      tone: 'info',
    })
  }

  if (summaries.length === 0) {
    summaries.push({
      id: 'all-clear',
      title: 'Workspace Status',
      detail: `No immediate governance, monitoring, drift, or authoring follow-up is open in ${workspaceName}.`,
      tone: 'success',
    })
  }

  return summaries.slice(0, 4)
}

const buildKeyboardNavigateHandler = (cardId: string, onNavigate?: (dest: string) => void) => {
  return (event: React.KeyboardEvent) => {
    if (!onNavigate) return
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      navigateFromDashboardCard(cardId, onNavigate)
    }
  }
}

// Calculate dashboard metrics from actual rules
const calculateDashboardMetrics = (
  rules: any[],
  currentWorkspace: string | null,
  user: { id?: string; email?: string; name?: string } | null,
  capabilities: DashboardCapabilities,
  workflowCounts: DashboardWorkflowCounts,
): DashboardCard[] => {
  const workspaceRules = currentWorkspace 
    ? rules.filter((r) => r.workspace === currentWorkspace)
    : rules

  // Count rules by approval status and active flag
  const activeRules = workspaceRules.filter(r => r.active === true).length
  const deactivatedRules = workspaceRules.filter((rule) => {
    const status = String(rule.status || '').trim().toLowerCase()
    const approvalStatus = String(rule.last_approval_status || '').trim().toLowerCase()
    return status === 'deactivated' || approvalStatus === 'deactivated'
  }).length

  const userTokens = new Set(
    [user?.id, user?.email, user?.name]
      .map((value) => String(value || '').trim().toLowerCase())
      .filter(Boolean)
  )

  const myWorkingRules = workspaceRules.filter((rule) => {
    const ownerToken = String(rule.createdBy || '').trim().toLowerCase()
    if (!ownerToken || !userTokens.has(ownerToken)) {
      return false
    }

    const status = String(rule.status || rule.last_approval_status || '').trim().toLowerCase()
    return status !== 'activated' && status !== 'deactivated'
  }).length
  const pendingDeactivation = 0
  const pendingReview = 0
  
  // Count rules whose approval was rejected
  const rejectedRules = workspaceRules.filter(
    r => r.last_approval_status === 'rejected',
  ).length

  const cards: DashboardCard[] = [
    {
      id: 'my-working-rules',
      title: 'My Working Rules',
      value: myWorkingRules,
      icon: 'user',
      color: 'info',
      description: 'Rules you own in this workspace that are currently in progress',
      focus: 'author',
    },
    {
      id: 'active-rules',
      title: 'Active Rules',
      value: activeRules,
      icon: 'check-circle',
      color: 'success',
      description: 'Rules that are currently enabled and actively monitoring your data for quality issues',
      focus: 'operations',
    },
    {
      id: 'pending-deactivation',
      title: 'Pending Deactivation',
      value: pendingDeactivation,
      icon: 'hourglass',
      color: 'info',
      description: 'Active rules with a submitted deactivation request waiting for reviewer approval',
      focus: 'approver',
    },
    {
      id: 'pending-review',
      title: 'Pending Review',
      value: pendingReview,
      icon: 'clock',
      color: 'warning',
      description: 'Rules submitted for approval that are waiting for stakeholder review and sign-off',
      focus: 'approver',
    },
    {
      id: 'deactivated-rules',
      title: 'Deactivated Rules',
      value: deactivatedRules,
      icon: 'times-circle-fill',
      color: 'danger',
      description: 'Rules that were deactivated after approval',
      focus: 'operations',
    },
    {
      id: 'rejected-rules',
      title: 'Rejected Rules',
      value: rejectedRules,
      icon: 'exclamation-circle',
      color: 'danger',
      description: 'Rules whose approval was rejected and need to be revised before resubmission',
      focus: 'author',
    },
  ]

  if (capabilities.canManageGovernance) {
    const pendingGovernanceActions = workflowCounts.pendingGovernanceActions
    if (pendingGovernanceActions !== null) {
      cards.push({
        id: 'pending-governance-actions',
        title: 'Pending Governance Actions',
        value: pendingGovernanceActions,
        icon: 'shield-check',
        color: pendingGovernanceActions > 0 ? 'warning' : 'info',
        description: 'Open the governance overview to review pending approval and deactivation work in this workspace',
        focus: 'approver',
      })
    }
  }

  if (capabilities.canAccessRuleQuality) {
    if (workflowCounts.profilingActivity !== null) {
      cards.push({
        id: 'profiling-activity',
        title: 'Profiling Activity',
        value: workflowCounts.profilingActivity,
        icon: 'info-circle',
        color: workflowCounts.profilingActivity > 0 ? 'info' : 'success',
        description: 'Open rule suggestions to review recent profiling requests and follow-up rule recommendations',
        focus: 'author',
      })
    }
    if (workflowCounts.catalogDriftActivity !== null) {
      cards.push({
        id: 'catalog-drift-activity',
        title: 'Catalog Drift Activity',
        value: workflowCounts.catalogDriftActivity,
        icon: 'exclamation-circle',
        color: workflowCounts.catalogDriftActivity > 0 ? 'warning' : 'success',
        description: 'Open catalog drift review to inspect recent drift work and revalidation follow-up for this workspace',
        focus: 'author',
      })
    }
  }

  if (capabilities.canAccessExecutionMonitoring && workflowCounts.failedValidationRuns !== null) {
    cards.push({
      id: 'failed-validation-runs',
      title: 'Failed Validation Runs',
      value: workflowCounts.failedValidationRuns,
      icon: 'exclamation-circle',
      color: workflowCounts.failedValidationRuns > 0 ? 'danger' : 'success',
      description: 'Open execution monitoring to inspect recent failed validation runs for this workspace',
      focus: 'operations',
    })
  }

  return cards
}

// Mock recent activity - in production this would come from audit log
const parseIsoDate = (value: unknown): Date | null => {
  const text = String(value || '').trim()
  if (!text) return null
  const parsed = new Date(text)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

const formatRelativeTime = (timestamp: unknown): string => {
  const date = parseIsoDate(timestamp)
  if (!date) return '—'
  const now = Date.now()
  const deltaMs = Math.max(0, now - date.getTime())
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  if (deltaMs < minute) return 'Just now'
  if (deltaMs < hour) {
    const minutes = Math.floor(deltaMs / minute)
    return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  }
  if (deltaMs < day) {
    const hours = Math.floor(deltaMs / hour)
    return `${hours} hour${hours === 1 ? '' : 's'} ago`
  }
  const days = Math.floor(deltaMs / day)
  return days === 1 ? 'Yesterday' : `${days} days ago`
}

const readAuditValue = (row: any, camelKey: string, snakeKey: string): any => {
  if (!row || typeof row !== 'object') return undefined
  if (camelKey in row) return (row as any)[camelKey]
  if (snakeKey in row) return (row as any)[snakeKey]
  return undefined
}

const getRecentActivityForWorkspace = (args: {
  workspaceId: string | null
  rules: any[]
  approvals: any[]
  auditLog: any[]
}): Array<{ time: string; text: string }> => {
  const { workspaceId, rules, approvals, auditLog } = args
  const ruleById = new Map<string, any>()
  for (const rule of rules) {
    if (rule?.id) {
      ruleById.set(String(rule.id), rule)
    }
  }

  const approvalById = new Map<string, any>()
  for (const approval of approvals) {
    if (approval?.id) {
      approvalById.set(String(approval.id), approval)
    }
  }

  const entries = (Array.isArray(auditLog) ? auditLog : [])
    .map((row) => {
      const action = String(readAuditValue(row, 'action', 'action') || '').trim()
      if (!action) return null

      const approvalId = String(readAuditValue(row, 'approvalId', 'approval_id') || '').trim()
      const timestamp = readAuditValue(row, 'timestamp', 'timestamp')
      const details = readAuditValue(row, 'details', 'details')
      const detailsObj = details && typeof details === 'object' ? details : {}

      const approval = approvalId ? approvalById.get(approvalId) : undefined
      const ruleIdFromDetails = String((detailsObj as any).rule_id || (detailsObj as any).ruleId || '').trim()
      const ruleId = String(approval?.ruleId || ruleIdFromDetails || '').trim()
      const rule = ruleId ? ruleById.get(ruleId) : undefined

      const entryWorkspaceId = String(
        approval?.workspaceId
        || rule?.workspace
        || (detailsObj as any).workspace_id
        || (detailsObj as any).workspaceId
        || (detailsObj as any).workspace
        || ''
      ).trim() || null
      if (workspaceId && entryWorkspaceId && entryWorkspaceId !== workspaceId) {
        return null
      }
      if (workspaceId && !entryWorkspaceId) {
        return null
      }

      const suggestionName = String(
        (detailsObj as any).suggestion_name
        || (detailsObj as any).suggestionName
        || (detailsObj as any).suggestion_id
        || (detailsObj as any).suggestionId
        || approvalId
        || 'Suggestion'
      ).trim()
      const ruleName = String(rule?.name || ruleId || suggestionName || 'Rule').trim()
      const requestType = String(approval?.requestType || (detailsObj as any).request_type || '').trim()

      const suiteId = String((detailsObj as any).suite_id || (detailsObj as any).suiteId || '').trim()
      const toSuiteVersion = (detailsObj as any).to_suite_version
        ?? (detailsObj as any).toSuiteVersion
        ?? (detailsObj as any).suite_version
        ?? (detailsObj as any).suiteVersion
      const assetId = String((detailsObj as any).asset_id || (detailsObj as any).assetId || '').trim()
      const dataSourceId = String((detailsObj as any).data_source_id || (detailsObj as any).dataSourceId || '').trim()
      const dataSourceName = String((detailsObj as any).data_source_name || (detailsObj as any).dataSourceName || '').trim()
      const runPlanId = String((detailsObj as any).run_plan_id || (detailsObj as any).runPlanId || '').trim()
      const runPlanName = String((detailsObj as any).business_key || (detailsObj as any).businessKey || runPlanId || '').trim()
      const reviewStatus = String((detailsObj as any).review_status || (detailsObj as any).reviewStatus || '').trim()

      if (action.startsWith('notification.') && action !== 'notification.contract_change') return null

      let text = ''
      if (action === 'suggestion.accepted') {
        text = `${suggestionName} accepted`
      } else if (action === 'suggestion.dismissed') {
        text = `${suggestionName} dismissed`
      } else if (action === 'suggestion.applied') {
        text = `${suggestionName} applied as a rule`
      } else if (action === 'created' || action === 'submitted-for-approval') {
        text = requestType === 'deactivation'
          ? `${ruleName} deactivation requested`
          : requestType === 'gx_suite_repair'
            ? `${ruleName} suite repair requested`
            : `${ruleName} submitted for approval`
      } else if (action === 'approved') {
        text = requestType === 'deactivation'
          ? `${ruleName} deactivation approved`
          : requestType === 'gx_suite_repair'
            ? `${ruleName} suite repair approved`
            : `${ruleName} approved`
      } else if (action === 'rejected') {
        text = requestType === 'deactivation'
          ? `${ruleName} deactivation rejected`
          : requestType === 'gx_suite_repair'
            ? `${ruleName} suite repair rejected`
            : `${ruleName} rejected`
      } else if (action === 'activated') {
        text = `${ruleName} activated`
      } else if (action === 'deactivated') {
        text = `${ruleName} deactivated`
      } else if (action === 'modified') {
        text = `${ruleName} updated`
      } else if (action === 'tested') {
        text = `${ruleName} tested`
      } else if (action === 'drift-reviewed') {
        text = `${ruleName} drift reviewed`
      } else if (action === 'profiling.requested') {
        const subject = dataSourceName || dataSourceId || 'Data source'
        text = `Profiling requested for ${subject}`
      } else if (action === 'cancelled') {
        text = `${ruleName} approval request cancelled`
      } else if (action === 'validation_run_plan.replayed') {
        const subject = runPlanName || runPlanId || 'Validation run plan'
        text = `${subject} replayed`
      } else if (action === 'notification.contract_change') {
        const subject = assetId ? `Data Asset '${assetId}'` : 'Data Asset contract'
        text = reviewStatus ? `${subject} contract ${reviewStatus}` : `${subject} review updated`
      } else if (action === 'gx_suite.empty.registered') {
        const suffix = suiteId ? ` (suite ${suiteId}${toSuiteVersion ? ` v${toSuiteVersion}` : ''})` : ''
        text = `Validation suite became empty after ${ruleName} deactivation${suffix}`
      } else if (action === 'gx_suite.reversion.completed') {
        const suffix = suiteId ? ` (suite ${suiteId}${toSuiteVersion ? ` v${toSuiteVersion}` : ''})` : ''
        text = `Validation suite updated after ${ruleName} deactivation${suffix}`
      } else if (action === 'gx_suite.repair.completed') {
        const suffix = suiteId ? ` (suite ${suiteId}${toSuiteVersion ? ` v${toSuiteVersion}` : ''})` : ''
        text = `Validation suite repaired for ${ruleName}${suffix}`
      } else {
        text = `${ruleName}: ${action}`
      }

      const date = parseIsoDate(timestamp)
      return {
        time: formatRelativeTime(timestamp),
        text,
        _ts: date ? date.getTime() : 0,
      }
    })
    .filter(Boolean) as Array<{ time: string; text: string; _ts: number }>

  entries.sort((a, b) => b._ts - a._ts)
  return entries.slice(0, 6).map(({ time, text }) => ({ time, text }))
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate }) => {
  const auth = useAuth()
  const settings = useSettings()
  const { rules, approvals, auditLog } = useRules()
  const [workflowCounts, setWorkflowCounts] = useState<DashboardWorkflowCounts>({
    pendingGovernanceActions: null,
    profilingActivity: null,
    catalogDriftActivity: null,
    failedValidationRuns: null,
  })
  const [workflowError, setWorkflowError] = useState<string | null>(null)

  const currentRole = auth.getCurrentUserRole?.() ?? null

  const capabilities = useMemo<DashboardCapabilities>(() => ({
    canAuthorRules: Boolean(currentRole && AUTHOR_FOCUS_ROLES.has(currentRole)),
    canReviewApprovals: Boolean(currentRole && APPROVER_FOCUS_ROLES.has(currentRole)),
    canAdminWorkspace: Boolean(currentRole && WORKSPACE_ADMIN_FOCUS_ROLES.has(currentRole)),
    canManageGovernance: Boolean(auth.canEditGovernance?.() || auth.canApproveGovernance?.()),
    canAccessRuleQuality: Boolean(currentRole && AUTHOR_FOCUS_ROLES.has(currentRole) && auth.hasAnyScope?.(['dq:rules:read', 'dq:rules:write', 'dq:rules:*', 'dq:*'])),
    canAccessExecutionMonitoring: Boolean(currentRole && WORKSPACE_ADMIN_FOCUS_ROLES.has(currentRole) && auth.hasAnyScope?.(['dq:reports:read', 'dq:reports:*', 'dq:*'])),
  }), [auth.canApproveGovernance, auth.canEditGovernance, auth.hasAnyScope, currentRole])

  useEffect(() => {
    let cancelled = false

    const loadWorkflowCounts = async () => {
      const currentWorkspaceId = String(auth.currentWorkspaceId || '').trim()
      if (!currentWorkspaceId) {
        setWorkflowCounts({
          pendingGovernanceActions: null,
          profilingActivity: null,
          catalogDriftActivity: null,
          failedValidationRuns: null,
        })
        setWorkflowError(null)
        return
      }

      const rulebuilderApiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const dataCatalogApiBase = toApiGroupV1Base('data-catalog', settings.applicationSettings?.apiBaseUrl)
      const headers = buildRequestHeaders()

      try {
        const nextCounts: DashboardWorkflowCounts = {
          pendingGovernanceActions: null,
          profilingActivity: null,
          catalogDriftActivity: null,
          failedValidationRuns: null,
        }

        const requests: Array<Promise<void>> = []

        if (capabilities.canManageGovernance) {
          requests.push((async () => {
            const response = await fetch(
              `${rulebuilderApiBase}/approvals?workspace=${encodeURIComponent(currentWorkspaceId)}&status=pending&limit=1`,
              { headers },
            )
            const payload = await parseJsonResponse(response)
            if (!response.ok) {
              throw new Error('Unable to load pending governance actions.')
            }
            nextCounts.pendingGovernanceActions = Number(payload?.pagination?.total || 0)
          })())
        }

        if (capabilities.canAccessRuleQuality) {
          requests.push((async () => {
            const response = await fetch(`${dataCatalogApiBase}/profiling/requests?limit=20`, { headers })
            const payload = await parseJsonResponse(response)
            if (!response.ok) {
              throw new Error('Unable to load profiling activity.')
            }
            nextCounts.profilingActivity = Array.isArray(payload?.profilingRequests) ? payload.profilingRequests.length : 0
          })())

          requests.push((async () => {
            const response = await fetch(`${rulebuilderApiBase}/governance/drift/summary`, { headers })
            const payload = await parseJsonResponse(response)
            if (!response.ok) {
              throw new Error('Unable to load catalog drift activity.')
            }
            nextCounts.catalogDriftActivity = Number(payload?.rulesWithDrift || 0)
          })())
        }

        if (capabilities.canAccessExecutionMonitoring) {
          requests.push((async () => {
            const response = await fetch(
              `${rulebuilderApiBase}/observability/health-scorecards?workspaceId=${encodeURIComponent(currentWorkspaceId)}`,
              { headers },
            )
            const payload = await parseJsonResponse(response)
            if (!response.ok) {
              return
            }
            const workspaceScorecard = Array.isArray(payload?.scorecards)
              ? payload.scorecards.find((entry: any) => String(entry?.scopeType || '').trim() === 'workspace')
              : null
            nextCounts.failedValidationRuns = Number(workspaceScorecard?.failedRuns || 0)
          })())
        }

        await Promise.all(requests)

        if (!cancelled) {
          setWorkflowCounts(nextCounts)
          setWorkflowError(null)
        }
      } catch (error) {
        if (!cancelled) {
          setWorkflowCounts({
            pendingGovernanceActions: null,
            profilingActivity: null,
            catalogDriftActivity: null,
            failedValidationRuns: null,
          })
          setWorkflowError(error instanceof Error ? error.message : 'Unable to load workflow dashboard tiles.')
        }
      }
    }

    void loadWorkflowCounts()

    return () => {
      cancelled = true
    }
  }, [auth.currentWorkspaceId, capabilities, settings.applicationSettings?.apiBaseUrl])

  const dashboardData = useMemo<DashboardData>(() => {
    const currentWorkspace = auth.currentWorkspaceId || null
    const cards = calculateDashboardMetrics(
      rules,
      currentWorkspace,
      auth.user || null,
      capabilities,
      workflowCounts,
    )
    const sections = buildDashboardSections({
      cards,
      capabilities,
    })
    const recentActivity = getRecentActivityForWorkspace({
      workspaceId: currentWorkspace,
      rules,
      approvals,
      auditLog,
    })

    return {
      sections,
      secondarySummaries: buildSecondarySummaries({
        sections,
        workspaceId: currentWorkspace,
      }),
      recentActivity,
    }
  }, [rules, approvals, auditLog, auth.currentWorkspaceId, auth.user, capabilities, workflowCounts])
  

  return (
    <section className="dashboard">
      {workflowError ? (
        <div className="dashboard-content" style={{ marginBottom: '1rem' }}>
          <strong>Unable to load workflow tiles.</strong> {workflowError}
        </div>
      ) : null}
      {dashboardData.sections.map((section) => {
        const visibleCards = section.cards.filter((card) => typeof card.value !== 'number' || card.value > 0)
        const zeroValueCards = section.cards.filter((card) => typeof card.value === 'number' && card.value === 0)

        return (
          <div key={section.id} className="dashboard-role-section">
            <div className="dashboard-role-header">
              <div>
                <h3 className="dashboard-role-title">{section.title}</h3>
                <p className="dashboard-role-description">{section.description}</p>
              </div>
            </div>

            {visibleCards.length > 0 ? (
              <div className="dashboard-grid">
                {visibleCards.map((card) => {
                  const destination = getDashboardNavigationIntent(card.id)?.destination ?? null
                  const isNavigable = Boolean(destination && onNavigate)
                  return (
                    <div
                      key={card.id}
                      className={`dashboard-card card-${card.color}${isNavigable ? ' dashboard-card-clickable' : ''}`}
                      title={card.description}
                      onClick={isNavigable ? () => navigateFromDashboardCard(card.id, onNavigate) : undefined}
                      role={isNavigable ? 'button' : undefined}
                      tabIndex={isNavigable ? 0 : undefined}
                      onKeyDown={isNavigable ? buildKeyboardNavigateHandler(card.id, onNavigate) : undefined}
                    >
                      <div className="card-header">
                        <AppIcon name={card.icon} />
                        <h3>{card.title}</h3>
                      </div>
                      <div className="card-value">{card.value}</div>
                      <div className="card-description">{card.description}</div>
                    </div>
                  )
                })}
              </div>
            ) : null}

            {zeroValueCards.length > 0 && (
              <div className="dashboard-zero-summary" aria-label={`${section.title} zero-value dashboard indicators`}>
                <span className="zero-summary-label">Nothing open for {section.title}:</span>
                <div className="dashboard-zero-indicators">
                  {zeroValueCards.map((card) => (
                    (() => {
                      const destination = getDashboardNavigationIntent(card.id)?.destination ?? null
                      const isNavigable = Boolean(destination && onNavigate)
                      return (
                        <span
                          key={card.id}
                          className={`zero-indicator zero-indicator-${card.color} zero-indicator-${card.id}${isNavigable ? ' dashboard-card-clickable' : ''}`}
                          title={`${card.title}: 0`}
                          onClick={isNavigable ? () => navigateFromDashboardCard(card.id, onNavigate) : undefined}
                          role={isNavigable ? 'button' : undefined}
                          tabIndex={isNavigable ? 0 : undefined}
                          onKeyDown={isNavigable ? buildKeyboardNavigateHandler(card.id, onNavigate) : undefined}
                        >
                          <AppIcon name={ZERO_COUNT_INDICATOR_ICON} />
                          <span className="zero-indicator-label">{card.title}</span>
                        </span>
                      )
                    })()
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      })}

      <div className="dashboard-content dashboard-secondary-summary">
        <div className="dashboard-secondary-summary-header">
          <h3>{`${getWorkspaceDisplayName(String(auth.currentWorkspaceId || '')) || 'Current workspace'} Workspace Summary`}</h3>
          <p>This summary displays open governance, drift, monitoring, and authoring follow-up for the current workspace.</p>
        </div>
        <div className="dashboard-secondary-summary-list">
          {dashboardData.secondarySummaries.map((summary) => (
            <div key={summary.id} className={`dashboard-secondary-summary-item dashboard-secondary-summary-item-${summary.tone}`}>
              <div className="dashboard-secondary-summary-title">{summary.title}</div>
              <div className="dashboard-secondary-summary-detail">{summary.detail}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="dashboard-content">
        <h3>Recent Activity</h3>
        <div className="activity-list">
          {dashboardData.recentActivity.length === 0 ? (
            <div className="activity-item">
              <span className="activity-time">—</span>
              <span className="activity-text">No recent activity yet</span>
            </div>
          ) : (
            dashboardData.recentActivity.map((activity, index) => (
              <div key={index} className="activity-item">
                <span className="activity-time">{activity.time}</span>
                <span className="activity-text">{activity.text}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  )
}
