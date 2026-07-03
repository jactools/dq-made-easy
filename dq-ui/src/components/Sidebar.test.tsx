/** @vitest-environment jsdom */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

import { canShowSidebarItem, getFeatureNavItemLabel, shouldRenderSidebarItem, shouldShowFeatureNavItem, SIDEBAR_MENU_ITEMS, SIDEBAR_PARENT_DEFAULTS } from './Sidebar'

const mockUseAuth = vi.fn()
const mockUsePreviewFeatures = vi.fn()
const mockUseFeatureLifecycleConfig = vi.fn()

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('../hooks/useFeatureFlags', () => ({
  usePreviewFeatures: () => mockUsePreviewFeatures(),
}))

vi.mock('../hooks/useFeatureLifecycleConfig', () => ({
  useFeatureLifecycleConfig: () => mockUseFeatureLifecycleConfig(),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('Sidebar', () => {
  it('uses Rule Quality, Governance, and Operations as the canonical section labels', () => {
    const sectionLabels = SIDEBAR_MENU_ITEMS.map((item) => item.label)

    expect(sectionLabels).toContain('Rule Quality')
    expect(sectionLabels).toContain('Governance')
    expect(sectionLabels).toContain('Operations')
    expect(sectionLabels).toContain('Administration')
    expect(sectionLabels).toContain('Discussions')
    expect(sectionLabels).not.toContain('Features')
    expect(sectionLabels).not.toContain('Approvals')
    expect(sectionLabels).not.toContain('Reports')
    expect(SIDEBAR_PARENT_DEFAULTS['rule-quality']).toBe('rule-quality-validation')
    expect(SIDEBAR_PARENT_DEFAULTS.administration).toBe('administration-connectors')
    expect(canShowSidebarItem(
      {
        id: 'administration',
        requiredScopes: ['dq:admin:read'],
        requiredRoles: ['admin'],
      },
      {
        isAuthenticated: true,
        currentRole: 'viewer',
        canEditGovernance: false,
        hasAnyScope: () => false,
        hasAdminWorkspaceAccess: true,
      },
    )).toBe(true)
    expect(SIDEBAR_MENU_ITEMS.find((item) => item.id === 'administration')?.submenu?.some((subItem) => subItem.id === 'administration-connectors')).toBe(true)
    expect(SIDEBAR_MENU_ITEMS.find((item) => item.id === 'administration')?.submenu?.some((subItem) => subItem.id === 'administration-ui-registry')).toBe(true)
    expect(canShowSidebarItem(
      {
        id: 'administration-connectors',
        requiredRoles: ['admin'],
      },
      {
        isAuthenticated: true,
        currentRole: 'cross-admin',
        canEditGovernance: false,
        hasAnyScope: () => false,
        hasAdminWorkspaceAccess: true,
      },
    )).toBe(false)
    expect(SIDEBAR_MENU_ITEMS.find((item) => item.id === 'reports')?.submenu?.some((subItem) => subItem.id === 'reports-validation-plans')).toBe(true)
    expect(SIDEBAR_MENU_ITEMS.find((item) => item.id === 'reports')?.submenu?.some((subItem) => subItem.id === 'reports-incidents')).toBe(true)
    expect(SIDEBAR_MENU_ITEMS.find((item) => item.id === 'reports')?.submenu?.some((subItem) => subItem.id === 'reports-service-levels')).toBe(true)
    expect(SIDEBAR_MENU_ITEMS.find((item) => item.id === 'reports')?.submenu?.some((subItem) => subItem.id === 'reports-agent-access')).toBe(true)
    expect(SIDEBAR_MENU_ITEMS.find((item) => item.id === 'reports')?.submenu?.some((subItem) => subItem.id === 'reports-data-definition')).toBe(true)
    expect(SIDEBAR_MENU_ITEMS.find((item) => item.id === 'audit')?.submenu?.some((subItem) => subItem.id === 'audit-data-definition')).toBe(false)
  })

  it('keeps All Rules visible and reserves All Across Workspaces for workspace-read access', () => {
    const rulesMenu = SIDEBAR_MENU_ITEMS.find((item) => item.id === 'rules')
    const allRules = rulesMenu?.submenu?.find((subItem) => subItem.id === 'rules-all')
    const allAcrossRules = rulesMenu?.submenu?.find((subItem) => subItem.id === 'rules-all-workspaces')

    expect(allRules?.requiredScopes).toBeUndefined()
    expect(allAcrossRules?.requiredScopes).toEqual(['dq:workspace:read'])
  })

  it('keeps Governance All visible and reserves All Across Workspaces for workspace-read access', () => {
    const approvalsMenu = SIDEBAR_MENU_ITEMS.find((item) => item.id === 'approvals')
    const allApprovals = approvalsMenu?.submenu?.find((subItem) => subItem.id === 'approvals-all')
    const allAcrossApprovals = approvalsMenu?.submenu?.find((subItem) => subItem.id === 'approvals-all-workspaces')

    expect(allApprovals?.requiredScopes).toBeUndefined()
    expect(allAcrossApprovals?.requiredScopes).toEqual(['dq:workspace:read'])
  })

  it('keeps Data Catalog All visible and reserves All Across Workspaces for workspace-read access', () => {
    const dataBrowserMenu = SIDEBAR_MENU_ITEMS.find((item) => item.id === 'data-browser')
    const allDataCatalog = dataBrowserMenu?.submenu?.find((subItem) => subItem.id === 'data-browser-all')
    const allAcrossDataCatalog = dataBrowserMenu?.submenu?.find((subItem) => subItem.id === 'data-browser-all-workspaces')

    expect(allDataCatalog?.requiredScopes).toBeUndefined()
    expect(allAcrossDataCatalog?.requiredScopes).toEqual(['dq:workspace:read'])
  })

  it('keeps live Rule Validation and Rule Suggestions visible without preview opt-in', () => {
    expect(shouldShowFeatureNavItem('feature_rule_validation', { enabled: true, stage: 'live' }, false)).toBe(true)
    expect(shouldShowFeatureNavItem('feature_rule_suggestions', { enabled: true, stage: 'live' }, false)).toBe(true)
  })

  it('preserves scope-based access control for Rule Quality navigation', () => {
    expect(canShowSidebarItem(
      {
        id: 'rule-quality',
        requiredScopes: ['dq:rules:read'],
        requiredRoles: ['admin'],
      },
      {
        isAuthenticated: true,
        currentRole: 'admin',
        canEditGovernance: false,
        hasAnyScope: () => false,
        hasAdminWorkspaceAccess: false,
      },
    )).toBe(false)
  })

  it('allows Governance navigation when the session has a governance editor role', () => {
    const governanceItem = SIDEBAR_MENU_ITEMS.find((item) => item.id === 'approvals')

    expect(governanceItem).toBeTruthy()
    expect(canShowSidebarItem(
      governanceItem!,
      {
        isAuthenticated: true,
        currentRole: 'governance-editor',
        canEditGovernance: true,
        hasAnyScope: () => false,
        hasAdminWorkspaceAccess: false,
      },
    )).toBe(true)
  })

  it('hides the Administration section when no submenu items remain visible', () => {
    expect(shouldRenderSidebarItem({ id: 'administration', submenu: [] })).toBe(false)
    expect(shouldRenderSidebarItem({ id: 'administration', submenu: [{ id: 'administration-users', label: 'User Management' }] })).toBe(true)
    expect(shouldRenderSidebarItem({ id: 'reports' })).toBe(true)
  })

  it('only appends preview labels for preview-stage capabilities', () => {
    expect(getFeatureNavItemLabel('Rule Suggestions', 'live')).toBe('Rule Suggestions')
    expect(getFeatureNavItemLabel('Rule Suggestions', 'preview')).toBe('Rule Suggestions (Preview)')
  })
})