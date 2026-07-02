import React, { useState, useEffect } from 'react'
import { useAuth } from '../hooks/useKeycloak'
import { usePreviewFeatures } from '../hooks/useFeatureFlags'
import { PREVIEW_FEATURES } from './features'
import { useFeatureLifecycleConfig } from '../hooks/useFeatureLifecycleConfig'
import { AppIcon, type AppIconName } from './app-primitives'

interface MenuItem {
  id: string
  label: string
  icon: AppIconName
  requiredRoles?: string[]
  requiredScopes?: string[]
  submenu?: SubmenuItem[]
}

interface SubmenuItem {
  id: string
  label: string
  icon?: AppIconName
  description?: string
  requiredRoles?: string[]
  requiredScopes?: string[]
}

const SCOPE_REQUIREMENTS = {
  rules: ['dq:rules:read', 'dq:rules:write', 'dq:rules:*', 'dq:*'],
  ruleQuality: ['dq:rules:read', 'dq:rules:write', 'dq:rules:*', 'dq:*'],
  approvals: ['dq:rules:approve', 'dq:workspace:read', 'dq:exceptions:read', 'dq:exceptions:detail', 'dq:*'],
  exceptionRecords: ['dq:exceptions:read', 'dq:exceptions:detail', 'dq:*'],
  dataCatalog: ['dq:data_catalog:read', 'dq:data_catalog:*', 'dq:*'],
  dataAssets: ['dq:data_catalog:read', 'dq:data_catalog:write', 'dq:data_catalog:*', 'dq:*'],
  reports: ['dq:reports:read', 'dq:reports:*', 'dq:*'],
  audit: ['dq:audit:read', 'dq:audit:*', 'dq:*'],
  templates: ['dq:templates:read', 'dq:templates:write', 'dq:templates:*', 'dq:*'],
  notifications: ['dq:notifications:read', 'dq:notifications:*', 'dq:*'],
  administration: ['dq:admin:read', 'dq:workspace:read', 'dq:*'],
} as const

export const SIDEBAR_MENU_ITEMS: MenuItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: 'pie-chart' },
  {
    id: 'rules',
    label: 'Rules',
    icon: 'list',
    requiredScopes: [...SCOPE_REQUIREMENTS.rules],
    requiredRoles: ['analyst', 'data-steward', 'admin'],
    submenu: [
      { id: 'rules-my', label: 'My Rules', icon: 'person' },
      { id: 'rules-team', label: "My Team's Rules", icon: 'people' },
      {
        id: 'rules-all',
        label: 'All Rules',
        icon: 'table',
        description: 'Rules from any workspace that use data object versions in the current workspace.',
      },
      { id: 'rules-all-workspaces', label: 'All Across Workspaces', icon: 'globe', requiredScopes: ['dq:workspace:read'] },
    ],
  },
  {
    id: 'rule-quality',
    label: 'Rule Quality',
    icon: 'check-circle',
    requiredScopes: [...SCOPE_REQUIREMENTS.ruleQuality],
    requiredRoles: ['analyst', 'data-steward', 'admin'],
    submenu: [
      { id: 'rule-quality-drift', label: 'Catalog Drift', icon: 'warning' },
    ],
  },
  {
    id: 'approvals',
    label: 'Governance',
    icon: 'shield-check',
    requiredScopes: [...SCOPE_REQUIREMENTS.approvals],
    requiredRoles: ['data-steward', 'admin', 'auditor', 'regulator', 'governance-admin', 'governance-editor'],
    submenu: [
      { id: 'approvals-my', label: 'My Approval Queue', icon: 'person' },
      { id: 'approvals-team', label: "My Team's Approval Queue", icon: 'people' },
      { id: 'approvals-all', label: 'All Approval Requests', icon: 'table' },
      { id: 'approvals-all-workspaces', label: 'All Approval Requests Across Workspaces', icon: 'globe', requiredScopes: ['dq:workspace:read'] },
      { id: 'approvals-policies', label: 'Policy Documents', icon: 'book', requiredRoles: ['governance-admin', 'governance-editor'] },
      { id: 'approvals-governance', label: 'Governance Overview', icon: 'info-circle' },
    ],
  },
  {
    id: 'access-requests',
    label: 'Access Requests',
    icon: 'shield-check',
  },
  {
    id: 'data-browser',
    label: 'Data Catalog',
    icon: 'book',
    requiredScopes: [...SCOPE_REQUIREMENTS.dataCatalog],
    requiredRoles: ['analyst', 'data-steward', 'admin'],
    submenu: [
      { id: 'data-browser-my', label: 'My Data Catalog', icon: 'person' },
      { id: 'data-browser-team', label: "My Team's Data Catalog", icon: 'people' },
      { id: 'data-browser-all', label: 'All Data Catalog', icon: 'table' },
      { id: 'data-browser-all-workspaces', label: 'All Across Workspaces', icon: 'globe', requiredScopes: ['dq:workspace:read'] },
      {
        id: 'definition-mappings',
        label: 'Definition Mappings',
        icon: 'link',
        requiredScopes: [...SCOPE_REQUIREMENTS.dataCatalog],
      },
      {
        id: 'delivery-inventory',
        label: 'Delivery Inventory',
        icon: 'database',
        requiredScopes: [...SCOPE_REQUIREMENTS.dataCatalog],
      },
    ],
  },
  {
    id: 'data-assets',
    label: 'Data Assets',
    icon: 'table',
    requiredScopes: [...SCOPE_REQUIREMENTS.dataAssets],
    requiredRoles: ['analyst', 'data-steward', 'admin'],
  },
  {
    id: 'reports',
    label: 'Operations',
    icon: 'folder',
    requiredScopes: [...SCOPE_REQUIREMENTS.reports],
    requiredRoles: ['analyst', 'data-steward', 'admin'],
    submenu: [
      { id: 'reports-metrics', label: 'Operational Metrics', icon: 'info-circle' },
      { id: 'reports-test-results', label: 'Validation Test Results', icon: 'play' },
      { id: 'reports-incidents', label: 'Incidents', icon: 'warning' },
      { id: 'reports-service-levels', label: 'Service Levels', icon: 'shield-check' },
      { id: 'reports-reconciliation', label: 'Reconciliation', icon: 'table' },
      { id: 'reports-validation-plans', label: 'Validation Plans', icon: 'calendar' },
    ],
  },
  {
    id: 'discussions',
    label: 'Discussions',
    icon: 'chat',
    requiredScopes: ['dq:rules:approve', 'dq:reports:read', 'dq:data_catalog:read', 'dq:workspace:read', 'dq:*'],
  },
  {
    id: 'audit',
    label: 'Audit Trail',
    icon: 'receipt',
    requiredScopes: [...SCOPE_REQUIREMENTS.audit],
    requiredRoles: ['analyst', 'data-steward', 'admin'],
    submenu: [
      { id: 'audit-all', label: 'Overview', icon: 'list' },
      { id: 'audit-changes', label: 'Rule History', icon: 'arrow-curve-right' },
      { id: 'audit-data-definition', label: 'Data-Definition History', icon: 'document' },
      { id: 'audit-validation', label: 'Validation History', icon: 'play' },
      { id: 'audit-approvals', label: 'Approval History', icon: 'check-circle' },
      { id: 'audit-rule-compiler-versions', label: 'Rule & Compiler Versions', icon: 'info-circle' },
    ],
  },
  {
    id: 'templates',
    label: 'Templates',
    icon: 'document',
    requiredScopes: [...SCOPE_REQUIREMENTS.templates],
    requiredRoles: ['analyst', 'admin'],
    submenu: [
      { id: 'templates-my', label: 'My Templates', icon: 'person' },
      { id: 'templates-team', label: "My Team's Templates", icon: 'people' },
      { id: 'templates-all', label: 'All Templates', icon: 'table' },
      { id: 'templates-all-workspaces', label: 'All Across Workspaces', icon: 'globe', requiredScopes: ['dq:workspace:read'] },
    ],
  },
  {
    id: 'notifications',
    label: 'Notifications',
    icon: 'bell',
    requiredRoles: ['analyst', 'data-steward', 'admin'],
  },
  {
    id: 'administration',
    label: 'Administration',
    icon: 'sliders',
    requiredScopes: [...SCOPE_REQUIREMENTS.administration],
    requiredRoles: ['admin'],
    submenu: [
      { id: 'administration-connectors', label: 'Connectors', icon: 'database', requiredRoles: ['admin'] },
      { id: 'administration-users', label: 'User Management', icon: 'folder', requiredScopes: ['dq:admin:read', 'dq:workspace:read'] },
      { id: 'administration-roles', label: 'Role Management', icon: 'shield-check', requiredScopes: ['dq:admin:read', 'dq:workspace:read'] },
      { id: 'administration-system-metrics', label: 'System Metrics', icon: 'info-circle', requiredScopes: ['dq:admin:read'] },
      { id: 'administration-gx-run-plans', label: 'Validation Run Plans', icon: 'calendar', requiredScopes: ['dq:admin:read'] },
      { id: 'administration-gx-suites', label: 'Validation Suites', icon: 'list', requiredScopes: ['dq:admin:read'] },
      { id: 'administration-ui-registry', label: 'UI Registry', icon: 'sliders', requiredRoles: ['admin'] },
      { id: 'administration-application', label: 'Application Settings', icon: 'sliders', requiredScopes: ['dq:admin:read'] },
    ],
  },
  { id: 'documentation', label: 'Documentation', icon: 'book' },
  { id: 'settings', label: 'Settings', icon: 'sliders' },
]

const FEATURE_NAV_CONFIG: Record<string, { id: string; parentId: 'rule-quality' | 'approvals' | 'reports' }> = {
  feature_rule_validation: { id: 'rule-quality-validation', parentId: 'rule-quality' },
  feature_rule_lifecycle_management: { id: 'approvals-lifecycle', parentId: 'approvals' },
  feature_rule_result_aggregation: { id: 'reports-rule-aggregation', parentId: 'reports' },
  feature_rule_suggestions: { id: 'rule-quality-suggestions', parentId: 'rule-quality' },
  feature_exception_record_handling: { id: 'approvals-exceptions', parentId: 'approvals' },
  feature_rule_execution_monitoring: { id: 'reports-rule-monitoring', parentId: 'reports' },
}

const FEATURE_SCOPE_REQUIREMENTS: Partial<Record<string, string[]>> = {
  feature_exception_record_handling: [...SCOPE_REQUIREMENTS.exceptionRecords],
}

const FORCE_PREVIEW_FEATURE_KEYS = new Set<string>([])

export const shouldShowFeatureNavItem = (
  featureKey: string,
  lifecycle: { enabled: boolean; stage: 'off' | 'preview' | 'live' },
  isPreviewEnabled: boolean,
): boolean => {
  if (!lifecycle.enabled) return false
  if (lifecycle.stage === 'live') return true
  if (FORCE_PREVIEW_FEATURE_KEYS.has(featureKey)) return isPreviewEnabled
  return lifecycle.stage === 'preview' && isPreviewEnabled
}

export const getFeatureNavItemLabel = (label: string, stage: 'off' | 'preview' | 'live'): string => {
  return stage === 'preview' ? `${label} (Preview)` : label
}

export const canShowSidebarItem = (
  item: Pick<MenuItem, 'id' | 'requiredRoles' | 'requiredScopes'>,
  input: {
    isAuthenticated: boolean
    currentRole: string | null | undefined
    canEditGovernance: boolean
    hasAnyScope: (scopes: string[]) => boolean
    hasAdminWorkspaceAccess: boolean
  },
): boolean => {
  if (item.id === 'administration') {
    return input.isAuthenticated && input.hasAdminWorkspaceAccess
  }

  if (item.id === 'administration-connectors' || item.id === 'administration-ui-registry') {
    return input.isAuthenticated && input.currentRole === 'admin'
  }

  if (!item.requiredRoles && !item.requiredScopes) {
    return input.isAuthenticated
  }

  if (item.id === 'approvals' && input.canEditGovernance) {
    return true
  }

  if (item.requiredScopes && item.requiredScopes.length > 0) {
    return input.isAuthenticated && input.hasAnyScope(item.requiredScopes)
  }

  return Boolean(input.isAuthenticated && input.currentRole && item.requiredRoles?.includes(input.currentRole))
}

export const shouldRenderSidebarItem = (item: Pick<MenuItem, 'id' | 'submenu'>): boolean => {
  if (item.id === 'administration') {
    return Boolean(item.submenu && item.submenu.length > 0)
  }

  return true
}

export const SIDEBAR_PARENT_DEFAULTS: Record<string, string> = {
  rules: 'rules-my',
  'rule-quality': 'rule-quality-validation',
  approvals: 'approvals-my',
  'data-browser': 'data-browser-my',
  reports: 'reports-metrics',
  templates: 'templates-my',
  administration: 'administration-connectors',
}

export const Sidebar: React.FC<{
  activeItem: string
  onItemClick: (id: string) => void
  collapsed: boolean
  width?: number
  onToggleCollapsed: () => void
}> = ({ activeItem, onItemClick, collapsed, width, onToggleCollapsed }) => {
  const auth = useAuth()
  const currentRole = auth.getCurrentUserRole()
  const canEditGovernance = Boolean(auth.canEditGovernance?.())
  const canApproveGovernance = Boolean(auth.canApproveGovernance?.())
  const canReadAcrossWorkspaces = auth.canReadAcrossWorkspaces()
  const hasAdminWorkspaceAccess = Boolean(
    auth.isAuthenticated && auth.currentWorkspaceId && auth.user?.workspaceRoles.some((workspaceRole) => {
      return workspaceRole.workspaceId === auth.currentWorkspaceId && (workspaceRole.role === 'admin' || workspaceRole.role === 'cross-admin')
    }),
  )
  const { isPreviewEnabled } = usePreviewFeatures()
  const { getFeatureState } = useFeatureLifecycleConfig()
  const [expandedMenu, setExpandedMenu] = useState<string | null>(null)

  const featureItems = Object.values(PREVIEW_FEATURES)
    .map(feature => ({
      key: feature.key,
      id: FEATURE_NAV_CONFIG[feature.key]?.id,
      parentId: FEATURE_NAV_CONFIG[feature.key]?.parentId,
      label: feature.name,
      icon: feature.icon,
      lifecycle: getFeatureState(feature.key),
      requiredScopes: FEATURE_SCOPE_REQUIREMENTS[feature.key] || [],
    }))
    .filter(item => item.id && item.parentId)

  const buildFeatureSubmenu = (parentId: 'rule-quality' | 'approvals' | 'reports'): SubmenuItem[] => (
    featureItems
      .filter(item => item.parentId === parentId)
      .filter(item => item.requiredScopes.length === 0 || auth.hasAnyScope(item.requiredScopes))
      .filter(item => shouldShowFeatureNavItem(item.key, item.lifecycle, isPreviewEnabled))
      .map(item => ({
        id: item.id,
        label: getFeatureNavItemLabel(item.label, item.lifecycle.stage),
        icon: item.icon,
        description: item.lifecycle.stage === 'preview' ? 'Preview feature' : undefined,
      }))
  )

  // Update expanded menu when activeItem changes to keep submenu visible
  useEffect(() => {
    // Find which parent menu contains the active item
    let found = false
    
    for (const item of resolvedMenuItems) {
      if (item.submenu && item.submenu.some(sub => sub.id === activeItem)) {
        setExpandedMenu(item.id)
        found = true
        break
      }
    }
    
    // If active item is not in any submenu, collapse all menus
    if (!found) {
      setExpandedMenu(null)
    }
  }, [activeItem])

  const resolvedMenuItems = SIDEBAR_MENU_ITEMS
    .map(item => {
      if ((item.id === 'data-browser' || item.id === 'templates') && item.submenu) {
        return {
          ...item,
          submenu: item.submenu.filter((sub) => (
            sub.id.endsWith('-all') || sub.id.endsWith('-all-workspaces')
              ? canReadAcrossWorkspaces
              : true
          )),
        }
      }
      if (item.id === 'approvals' && item.submenu) {
        return {
          ...item,
          submenu: [
            ...item.submenu.filter((sub) => {
              if (canEditGovernance && !canApproveGovernance) {
                return sub.id === 'approvals-policies' || sub.id === 'approvals-governance'
              }

              return sub.id === 'approvals-all-workspaces'
                ? canReadAcrossWorkspaces
                : true
            }),
            ...buildFeatureSubmenu('approvals'),
          ],
        }
      }
        if (item.id === 'rule-quality') {
        const featureSubmenu = buildFeatureSubmenu('rule-quality')
        const validationItem = featureSubmenu.find((subItem) => subItem.id === 'rule-quality-validation')
        const remainingFeatureItems = featureSubmenu.filter((subItem) => subItem.id !== 'rule-quality-validation')

        return {
          ...item,
          submenu: [
            ...(validationItem ? [validationItem] : []),
            ...(item.submenu || []),
            ...remainingFeatureItems,
          ],
        }
      }
      if (item.id === 'reports' && item.submenu) {
        return {
          ...item,
          submenu: [
            ...item.submenu,
            ...buildFeatureSubmenu('reports'),
          ],
        }
      }
      if (item.id === 'data-browser' && item.submenu) {
        return {
          ...item,
          submenu: item.submenu.filter((subItem) => {
            return subItem.id === 'data-browser-all-workspaces'
              ? canReadAcrossWorkspaces
              : true
          }),
        }
      }
      if (item.submenu) {
        return {
          ...item,
          submenu: item.submenu.filter((subItem) => {
            if (subItem.id === 'administration-connectors' || subItem.id === 'administration-ui-registry') {
              return currentRole === 'admin'
            }

            const scopeAllowed = !subItem.requiredScopes || subItem.requiredScopes.length === 0
              || auth.hasAnyScope(subItem.requiredScopes)
            const roleAllowed = !subItem.requiredRoles || subItem.requiredRoles.length === 0
              || Boolean(currentRole && subItem.requiredRoles.includes(currentRole))
            return scopeAllowed && roleAllowed
          }),
        }
      }
      return item
    })
    .filter(item => !(item.submenu && item.submenu.length === 0 && item.id === 'rule-quality'))

  // Filter menu items based on user authentication and role
  const visibleItems = resolvedMenuItems.filter(item => {
    return canShowSidebarItem(item, {
      isAuthenticated: auth.isAuthenticated,
      currentRole,
        canEditGovernance,
      hasAnyScope: auth.hasAnyScope,
      hasAdminWorkspaceAccess,
    }) && shouldRenderSidebarItem(item)
  })

  const handleMenuClick = (itemId: string, hasSubmenu: boolean) => {
    if (hasSubmenu) {
      const resolvedItem = resolvedMenuItems.find((item) => item.id === itemId)

      const isExpanded = expandedMenu === itemId
      const visibleSubmenu = resolvedItem?.submenu || []
      const staticDefaultSubItem = SIDEBAR_PARENT_DEFAULTS[itemId]
      const governanceDefaultSubItem = itemId === 'approvals' && canEditGovernance && !canApproveGovernance
        ? 'approvals-policies'
        : staticDefaultSubItem
      const defaultSubItem = staticDefaultSubItem && visibleSubmenu.some((subItem) => subItem.id === staticDefaultSubItem)
        ? governanceDefaultSubItem
        : visibleSubmenu[0]?.id

      // When the sidebar is collapsed, submenus are not visible,
      // so clicking a parent should navigate to a sensible default.
      if (collapsed) {
        if (defaultSubItem) {
          onItemClick(defaultSubItem)
          setExpandedMenu(itemId)
          return
        }
      }

      if (isExpanded) {
        setExpandedMenu(null)
        return
      }

      setExpandedMenu(itemId)

      const isAlreadyInSection = activeItem.startsWith(itemId + '-')
      if (defaultSubItem && !isAlreadyInSection) {
        onItemClick(defaultSubItem)
      }
    } else {
      onItemClick(itemId)
    }
  }

  return (
    <aside
      className={`app-sidebar${collapsed ? ' collapsed' : ''}`}
      style={!collapsed && width ? { width: `${width}px` } : undefined}
    >
      <div className="sidebar-header">
        <span className="sidebar-title">Navigation</span>
        <button
          type="button"
          className="sidebar-toggle-btn"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          onClick={onToggleCollapsed}
        >
          <AppIcon name={collapsed ? 'arrow-right' : 'arrow-left'} />
        </button>
      </div>
      <nav className="sidebar-nav">
        <ul>
          {visibleItems.map(item => (
            <li key={item.id}>
              <button
                className={`nav-item ${activeItem === item.id || activeItem.startsWith(item.id + '-') ? 'active' : ''}`}
                onClick={() => handleMenuClick(item.id, !!item.submenu)}
                aria-current={activeItem === item.id ? 'page' : undefined}
                title={collapsed ? item.label : undefined}
              >
                <AppIcon name={item.icon} />
                <span className="nav-label">{item.label}</span>
                {item.submenu && (
                  <AppIcon
                    name={expandedMenu === item.id ? 'chevron-down' : 'chevron-right'}
                    className="submenu-chevron"
                  />
                )}
              </button>
              {item.submenu && expandedMenu === item.id && !collapsed && (
                <ul className="submenu">
                  {item.submenu.map(subItem => (
                    <li key={subItem.id}>
                      <button
                        className={`nav-item submenu-item ${activeItem === subItem.id ? 'active' : ''}`}
                        onClick={() => onItemClick(subItem.id)}
                        aria-current={activeItem === subItem.id ? 'page' : undefined}
                        title={subItem.description}
                      >
                        {subItem.icon && <AppIcon name={subItem.icon} />}
                        <span className="nav-label">{subItem.label}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  )
}
