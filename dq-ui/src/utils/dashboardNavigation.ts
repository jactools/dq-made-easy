export const DASHBOARD_NAV_SELECTION_KEY = 'dq-dashboard-navigation-selection'

export type DashboardWorkspaceScope = 'my' | 'team' | 'all' | 'global'
export type DashboardRuleStatus =
  | 'all'
  | 'draft'
  | 'testing'
  | 'tested'
  | 'pending-approval'
  | 'approved'
  | 'activated'
  | 'deactivated'
  | 'rejected'
export type DashboardApprovalRequestFilter = 'all' | 'activation' | 'deactivation' | 'gx_suite_repair'
export type DashboardBrowseStatus = 'all' | 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface DashboardNavigationPreset {
  view_scope?: DashboardWorkspaceScope
  filter_status?: DashboardRuleStatus
  request_filter?: DashboardApprovalRequestFilter
  browse_status?: DashboardBrowseStatus
}

export interface DashboardNavigationIntent {
  destination: string
  preset?: DashboardNavigationPreset
}

interface StoredDashboardNavigationSelection {
  destination: string
  preset?: DashboardNavigationPreset
  source: 'dashboard'
  card_id: string
  created_at: string
}

const DASHBOARD_NAVIGATION_BY_CARD_ID: Record<string, DashboardNavigationIntent> = {
  'my-working-rules': {
    destination: 'rules-my',
  },
  'active-rules': {
    destination: 'rules-all',
    preset: {
      view_scope: 'all',
      filter_status: 'activated',
    },
  },
  'pending-deactivation': {
    destination: 'approvals-my',
    preset: {
      view_scope: 'my',
      request_filter: 'deactivation',
    },
  },
  'pending-review': {
    destination: 'approvals-my',
    preset: {
      view_scope: 'my',
      request_filter: 'activation',
    },
  },
  'pending-governance-actions': {
    destination: 'approvals-governance',
  },
  'profiling-activity': {
    destination: 'rule-quality-suggestions',
  },
  'catalog-drift-activity': {
    destination: 'rule-quality-drift',
  },
  'failed-validation-runs': {
    destination: 'reports-rule-monitoring',
    preset: {
      browse_status: 'failed',
    },
  },
  'deactivated-rules': {
    destination: 'rules-all',
    preset: {
      view_scope: 'all',
      filter_status: 'deactivated',
    },
  },
  'rejected-rules': {
    destination: 'rules-all',
    preset: {
      view_scope: 'all',
      filter_status: 'rejected',
    },
  },
}

const hasPreset = (preset?: DashboardNavigationPreset): boolean => {
  return Boolean(preset && Object.keys(preset).length > 0)
}

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export const getDashboardNavigationIntent = (cardId: string): DashboardNavigationIntent | null => {
  const intent = DASHBOARD_NAVIGATION_BY_CARD_ID[String(cardId || '')]
  if (!intent) {
    return null
  }

  return {
    destination: intent.destination,
    preset: intent.preset ? { ...intent.preset } : undefined,
  }
}

export const navigateFromDashboardCard = (
  cardId: string,
  onNavigate?: (destination: string) => void,
): void => {
  const intent = getDashboardNavigationIntent(cardId)
  if (!intent || !onNavigate) {
    return
  }

  if (hasPreset(intent.preset) && typeof window !== 'undefined') {
    try {
      const selection: StoredDashboardNavigationSelection = {
        destination: intent.destination,
        preset: intent.preset,
        source: 'dashboard',
        card_id: cardId,
        created_at: new Date().toISOString(),
      }
      window.sessionStorage.setItem(DASHBOARD_NAV_SELECTION_KEY, JSON.stringify(selection))
    } catch {
      // Ignore storage failures and still navigate.
    }
  }

  onNavigate(intent.destination)
}

export const consumeDashboardNavigationSelection = (destination: string): DashboardNavigationPreset | null => {
  if (typeof window === 'undefined') {
    return null
  }

  const raw = window.sessionStorage.getItem(DASHBOARD_NAV_SELECTION_KEY)
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw) as StoredDashboardNavigationSelection
    if (!isRecord(parsed) || parsed.destination !== destination) {
      return null
    }

    window.sessionStorage.removeItem(DASHBOARD_NAV_SELECTION_KEY)
    return isRecord(parsed.preset) ? (parsed.preset as DashboardNavigationPreset) : null
  } catch {
    window.sessionStorage.removeItem(DASHBOARD_NAV_SELECTION_KEY)
    return null
  }
}

export const getRulesDestinationForScope = (scope: DashboardWorkspaceScope): string => {
  switch (scope) {
    case 'team':
      return 'rules-team'
    case 'all':
      return 'rules-all'
    case 'global':
      return 'rules-all-workspaces'
    default:
      return 'rules-my'
  }
}

export const getApprovalsDestinationForScope = (scope: DashboardWorkspaceScope): string => {
  switch (scope) {
    case 'team':
      return 'approvals-team'
    case 'all':
      return 'approvals-all'
    case 'global':
      return 'approvals-all-workspaces'
    default:
      return 'approvals-my'
  }
}

export const isDashboardWorkspaceScope = (value: unknown): value is DashboardWorkspaceScope => {
  return value === 'my' || value === 'team' || value === 'all' || value === 'global'
}

export const isDashboardRuleStatus = (value: unknown): value is DashboardRuleStatus => {
  return value === 'all'
    || value === 'draft'
    || value === 'testing'
    || value === 'tested'
    || value === 'pending-approval'
    || value === 'approved'
    || value === 'activated'
    || value === 'deactivated'
    || value === 'rejected'
}

export const isDashboardApprovalRequestFilter = (value: unknown): value is DashboardApprovalRequestFilter => {
  return value === 'all' || value === 'activation' || value === 'deactivation' || value === 'gx_suite_repair'
}

export const isDashboardBrowseStatus = (value: unknown): value is DashboardBrowseStatus => {
  return value === 'all'
    || value === 'pending'
    || value === 'running'
    || value === 'succeeded'
    || value === 'failed'
    || value === 'cancelled'
}
