/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { Dashboard } from './Dashboard'
import { DASHBOARD_NAV_SELECTION_KEY } from '../utils/dashboardNavigation'

const mockUseAuth = vi.fn()
const mockUseRules = vi.fn()
const mockUseSettings = vi.fn()
const fetchMock = vi.fn()

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('../hooks/useContexts', () => ({
  useRules: () => mockUseRules(),
  useSettings: () => mockUseSettings(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))

vi.stubGlobal('fetch', fetchMock)

const buildJsonResponse = (body: unknown) => ({
  ok: true,
  status: 200,
  statusText: 'OK',
  text: async () => JSON.stringify(body),
})

const buildErrorResponse = (status: number, body: unknown) => ({
  ok: false,
  status,
  statusText: 'Service Unavailable',
  text: async () => JSON.stringify(body),
})

describe('Dashboard', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    window.sessionStorage.removeItem(DASHBOARD_NAV_SELECTION_KEY)
  })

  const setupDefaultMocks = () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        apiBaseUrl: 'http://localhost:8000/api/v1',
      },
    })

    fetchMock.mockImplementation(async (input) => {
      const url = String(input)
      if (url.includes('/approvals?')) {
        return buildJsonResponse({ data: [], pagination: { total: 0 } })
      }
      if (url.includes('/profiling/requests?')) {
        return buildJsonResponse({ profiling_requests: [] })
      }
      if (url.includes('/governance/drift/summary')) {
        return buildJsonResponse({
          total_rules_checked: 0,
          rules_with_drift: 0,
          total_drifts_detected: 0,
          critical_drifts: 0,
          warning_drifts: 0,
          by_drift_type: {},
          affected_rules: [],
        })
      }
      if (url.includes('/observability/health-scorecards?')) {
        return buildJsonResponse({ scorecards: [] })
      }
      return buildJsonResponse({})
    })
  }

  it('shows workspace-scoped suggestion interactions in recent activity', () => {
    setupDefaultMocks()
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { id: 'user-1', name: 'Tester' },
    })
    mockUseRules.mockReturnValue({
      rules: [],
      approvals: [],
      auditLog: [
        {
          id: 'audit-1',
          action: 'suggestion.accepted',
          timestamp: '2026-05-24T10:00:00Z',
          details: {
            suggestion_id: 'sug-1',
            workspace_id: 'retail-banking',
          },
          workspaceId: 'retail-banking',
          ruleId: '',
          userId: 'user-1',
          userName: 'Tester',
        },
        {
          id: 'audit-2',
          action: 'suggestion.dismissed',
          timestamp: '2026-05-24T11:00:00Z',
          details: {
            suggestion_id: 'sug-2',
            workspace_id: 'corporate-banking',
          },
          workspaceId: 'corporate-banking',
          ruleId: '',
          userName: 'Other',
        },
      ],
    })

    render(<Dashboard />)

    expect(screen.getByText('sug-1 accepted')).toBeTruthy()
    expect(screen.queryByText('sug-2 dismissed')).toBeNull()
  })

  it('shows additional workspace-scoped rule and contract activity', () => {
    setupDefaultMocks()
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { id: 'user-1', name: 'Tester' },
    })
    mockUseRules.mockReturnValue({
      rules: [
        {
          id: 'rule-1',
          name: 'Customer health',
          workspace: 'retail-banking',
          createdBy: 'user-1',
        },
      ],
      approvals: [],
      auditLog: [
        {
          id: 'audit-3',
          action: 'submitted-for-approval',
          timestamp: '2026-05-24T12:00:00Z',
          details: {
            rule_id: 'rule-1',
            workspace_id: 'retail-banking',
          },
          workspaceId: 'retail-banking',
          ruleId: 'rule-1',
          userId: 'user-1',
          userName: 'Tester',
        },
        {
          id: 'audit-4',
          action: 'drift-reviewed',
          timestamp: '2026-05-24T13:00:00Z',
          details: {
            rule_id: 'rule-1',
            workspace_id: 'retail-banking',
          },
          workspaceId: 'retail-banking',
          ruleId: 'rule-1',
          userId: 'user-1',
          userName: 'Tester',
        },
        {
          id: 'audit-5',
          action: 'notification.contract_change',
          timestamp: '2026-05-24T14:00:00Z',
          details: {
            asset_id: 'asset-1',
            review_status: 'approved',
            workspace_id: 'retail-banking',
          },
          workspaceId: 'retail-banking',
          ruleId: '',
          userId: 'user-1',
          userName: 'Tester',
        },
        {
          id: 'audit-6',
          action: 'activated',
          timestamp: '2026-05-24T15:00:00Z',
          details: {
            rule_id: 'rule-2',
            workspace_id: 'corporate-banking',
          },
          workspaceId: 'corporate-banking',
          ruleId: 'rule-2',
          userId: 'user-2',
          userName: 'Other',
        },
      ],
    })

    render(<Dashboard />)

    expect(screen.getByText('Customer health submitted for approval')).toBeTruthy()
    expect(screen.getByText('Customer health drift reviewed')).toBeTruthy()
    expect(screen.getByText("Data Asset 'asset-1' contract approved")).toBeTruthy()
    expect(screen.queryByText('rule-2 activated')).toBeNull()
  })

  it('shows profiling requests and replayed run plans for the current workspace', () => {
    setupDefaultMocks()
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { id: 'user-1', name: 'Tester' },
    })
    mockUseRules.mockReturnValue({
      rules: [],
      approvals: [],
      auditLog: [
        {
          id: 'audit-7',
          action: 'profiling.requested',
          timestamp: '2026-05-24T16:00:00Z',
          details: {
            workspace_id: 'retail-banking',
            data_source_id: 'source-1',
            data_source_name: 'Customer records',
            profiling_request_id: 'req-1',
          },
          workspaceId: 'retail-banking',
          ruleId: '',
          userId: 'user-1',
          userName: 'Tester',
        },
        {
          id: 'audit-8',
          action: 'validation_run_plan.replayed',
          timestamp: '2026-05-24T17:00:00Z',
          details: {
            workspace_id: 'retail-banking',
            run_plan_id: 'run-plan-1',
            business_key: 'Retail daily checks',
            run_plan_version_id: 'run-plan-version-1',
          },
          workspaceId: 'retail-banking',
          ruleId: '',
          userId: 'user-1',
          userName: 'Tester',
        },
        {
          id: 'audit-9',
          action: 'profiling.requested',
          timestamp: '2026-05-24T18:00:00Z',
          details: {
            workspace_id: 'corporate-banking',
            data_source_id: 'source-2',
          },
          workspaceId: 'corporate-banking',
          ruleId: '',
          userId: 'user-2',
          userName: 'Other',
        },
      ],
    })

    render(<Dashboard />)

    expect(screen.getByText('Profiling requested for Customer records')).toBeTruthy()
    expect(screen.getByText('Retail daily checks replayed')).toBeTruthy()
    expect(screen.queryByText('Profiling requested for source-2')).toBeNull()
  })

  it('shows API-driven workflow entry cards for the selected author role', async () => {
    setupDefaultMocks()
    const onNavigate = vi.fn()

    fetchMock.mockImplementation(async (input) => {
      const url = String(input)
      if (url.includes('/approvals?')) {
        return buildJsonResponse({ data: [], pagination: { total: 3 } })
      }
      if (url.includes('/profiling/requests?')) {
        return buildJsonResponse({ profiling_requests: [{ id: 'req-1' }, { id: 'req-2' }] })
      }
      if (url.includes('/governance/drift/summary')) {
        return buildJsonResponse({
          total_rules_checked: 2,
          rules_with_drift: 1,
          total_drifts_detected: 1,
          critical_drifts: 0,
          warning_drifts: 1,
          by_drift_type: { alias_retargeted: 1 },
          affected_rules: [],
        })
      }
      if (url.includes('/observability/health-scorecards?')) {
        return buildJsonResponse({
          scorecards: [
            {
              scope_type: 'workspace',
              scope_id: 'retail-banking',
              scope_name: 'Retail Banking',
              workspace_id: 'retail-banking',
              failed_runs: 4,
            },
          ],
        })
      }
      return buildJsonResponse({})
    })

    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { id: 'user-1', name: 'Tester', workspaceRoles: [{ workspaceId: 'retail-banking', role: 'data-steward' }] },
      getCurrentUserRole: () => 'data-steward',
      canApproveRule: () => false,
      canApproveGovernance: () => false,
      canEditGovernance: () => false,
      hasAnyScope: (scopes: string[]) => scopes.includes('dq:rules:read'),
    })
    mockUseRules.mockReturnValue({
      rules: [
        {
          id: 'rule-1',
          name: 'Customer health',
          workspace: 'retail-banking',
          createdBy: 'user-1',
          active: true,
        },
      ],
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          requestType: 'approval',
          status: 'pending',
        },
      ],
      auditLog: [
        {
          id: 'audit-10',
          action: 'profiling.requested',
          timestamp: '2026-05-24T16:00:00Z',
          workspaceId: 'retail-banking',
          details: { workspace_id: 'retail-banking' },
        },
        {
          id: 'audit-11',
          action: 'drift-reviewed',
          timestamp: '2026-05-24T17:00:00Z',
          workspaceId: 'retail-banking',
          details: { workspace_id: 'retail-banking', rule_id: 'rule-1' },
        },
        {
          id: 'audit-12',
          action: 'profiling.requested',
          timestamp: '2026-05-24T18:00:00Z',
          workspaceId: 'corporate-banking',
          details: { workspace_id: 'corporate-banking' },
        },
      ],
    })

    render(<Dashboard onNavigate={onNavigate} />)

    expect(await screen.findByText('Rule Author Focus')).toBeTruthy()
    expect(await screen.findByText('Approver Focus')).toBeTruthy()
    expect(screen.queryByText('Operational Oversight')).toBeNull()
    expect(screen.queryByText('Workspace Admin Focus')).toBeNull()
    expect(screen.queryByText('Pending Governance Actions')).toBeNull()
    expect(await screen.findByText('Profiling Activity')).toBeTruthy()
    expect(await screen.findByText('Catalog Drift Activity')).toBeTruthy()
    expect(await screen.findByText('Retail Banking Workspace Summary')).toBeTruthy()
    expect(screen.queryByText('Failed Validation Runs')).toBeNull()

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/profiling/requests?limit=20'),
      expect.any(Object),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/governance/drift/summary'),
      expect.any(Object),
    )

    fireEvent.click(screen.getByText('Profiling Activity').closest('.dashboard-card')!)
    fireEvent.click(screen.getByText('Catalog Drift Activity').closest('.dashboard-card')!)

    expect(onNavigate).toHaveBeenCalledWith('rule-quality-suggestions')
    expect(onNavigate).toHaveBeenCalledWith('rule-quality-drift')
  })

  it('routes workspace-admin operational rule cards to filtered rules views instead of my-rules defaults', async () => {
    setupDefaultMocks()
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { id: 'user-1', name: 'Tester', workspaceRoles: [{ workspaceId: 'retail-banking', role: 'admin' }] },
      getCurrentUserRole: () => 'admin',
      canApproveGovernance: () => false,
      canEditGovernance: () => false,
      canManageUsers: () => false,
      hasAnyScope: () => false,
    })
    mockUseRules.mockReturnValue({
      rules: [
        { id: 'rule-1', workspace: 'retail-banking', active: true, status: 'activated', ownerId: 'user-1' },
        { id: 'rule-2', workspace: 'retail-banking', active: false, status: 'deactivated', last_approval_status: 'deactivated', ownerId: 'user-2' },
        { id: 'rule-3', workspace: 'retail-banking', active: false, status: 'draft', last_approval_status: 'rejected', ownerId: 'user-2' },
      ],
      approvals: [],
      auditLog: [],
    })

    const onNavigate = vi.fn()
    render(<Dashboard onNavigate={onNavigate} />)

    fireEvent.click(screen.getByTitle('Rules that are currently enabled and actively monitoring your data for quality issues'))
    expect(onNavigate).toHaveBeenLastCalledWith('rules-all')
    expect(JSON.parse(window.sessionStorage.getItem(DASHBOARD_NAV_SELECTION_KEY) || '{}')).toMatchObject({
      destination: 'rules-all',
      preset: {
        view_scope: 'all',
        filter_status: 'activated',
      },
    })

    fireEvent.click(screen.getByText('Deactivated Rules').closest('.dashboard-card')!)
    expect(onNavigate).toHaveBeenLastCalledWith('rules-all')
    expect(JSON.parse(window.sessionStorage.getItem(DASHBOARD_NAV_SELECTION_KEY) || '{}')).toMatchObject({
      destination: 'rules-all',
      preset: {
        view_scope: 'all',
        filter_status: 'deactivated',
      },
    })
  })

  it('routes author rejected-rule follow-up to the filtered rules view', async () => {
    setupDefaultMocks()
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { id: 'user-1', name: 'Tester', workspaceRoles: [{ workspaceId: 'retail-banking', role: 'analyst' }] },
      getCurrentUserRole: () => 'analyst',
      canApproveGovernance: () => false,
      canEditGovernance: () => false,
      canManageUsers: () => false,
      hasAnyScope: (scopes: string[]) => scopes.includes('dq:rules:write') || scopes.includes('dq:rules:read'),
    })
    mockUseRules.mockReturnValue({
      rules: [
        { id: 'rule-3', workspace: 'retail-banking', active: false, status: 'draft', last_approval_status: 'rejected', ownerId: 'user-1' },
      ],
      approvals: [],
      auditLog: [],
    })

    const onNavigate = vi.fn()
    render(<Dashboard onNavigate={onNavigate} />)

    fireEvent.click(await screen.findByText('Rejected Rules'))
    expect(onNavigate).toHaveBeenLastCalledWith('rules-all')
    expect(JSON.parse(window.sessionStorage.getItem(DASHBOARD_NAV_SELECTION_KEY) || '{}')).toMatchObject({
      destination: 'rules-all',
      preset: {
        view_scope: 'all',
        filter_status: 'rejected',
      },
    })
  })

  it('hides governance and rule-quality entry cards when the user lacks the matching access', () => {
    setupDefaultMocks()
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { id: 'user-1', name: 'Tester' },
      getCurrentUserRole: () => null,
      canApproveGovernance: () => false,
      canEditGovernance: () => false,
      hasAnyScope: () => false,
    })
    mockUseRules.mockReturnValue({
      rules: [],
      approvals: [],
      auditLog: [],
    })

    render(<Dashboard />)

    expect(screen.queryByText('Rule Author Focus')).toBeNull()
    expect(screen.queryByText('Approver Focus')).toBeNull()
    expect(screen.queryByText('Workspace Admin Focus')).toBeNull()
    expect(screen.queryByText('Pending Governance Actions')).toBeNull()
    expect(screen.queryByText('Profiling Activity')).toBeNull()
    expect(screen.queryByText('Catalog Drift Activity')).toBeNull()
    expect(screen.queryByText('Failed Validation Runs')).toBeNull()
    expect(screen.getByText('Retail Banking Workspace Summary')).toBeTruthy()
    expect(screen.getByText('Workspace Status')).toBeTruthy()
    expect(screen.getByText('No immediate governance, monitoring, drift, or authoring follow-up is open in Retail Banking.')).toBeTruthy()
  })

  it('still shows workspace status when health scorecards are unavailable', async () => {
    setupDefaultMocks()
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { id: 'user-1', name: 'Tester', workspaceRoles: [{ workspaceId: 'retail-banking', role: 'admin' }] },
      getCurrentUserRole: () => 'admin',
      canApproveGovernance: () => false,
      canEditGovernance: () => false,
      hasAnyScope: (scopes: string[]) => scopes.includes('dq:reports:read') || scopes.includes('dq:reports:*') || scopes.includes('dq:*'),
    })
    mockUseRules.mockReturnValue({
      rules: [],
      approvals: [],
      auditLog: [],
    })

    fetchMock.mockImplementation(async (input) => {
      const url = String(input)
      if (url.includes('/approvals?')) {
        return buildJsonResponse({ data: [], pagination: { total: 0 } })
      }
      if (url.includes('/profiling/requests?')) {
        return buildJsonResponse({ profiling_requests: [] })
      }
      if (url.includes('/governance/drift/summary')) {
        return buildJsonResponse({
          total_rules_checked: 0,
          rules_with_drift: 0,
          total_drifts_detected: 0,
          critical_drifts: 0,
          warning_drifts: 0,
          by_drift_type: {},
          affected_rules: [],
        })
      }
      if (url.includes('/observability/health-scorecards?')) {
        return buildErrorResponse(503, {
          detail: {
            message: 'Health scorecards are unavailable',
          },
        })
      }
      return buildJsonResponse({})
    })

    render(<Dashboard />)

    expect(screen.getByText('Workspace Status')).toBeTruthy()
    expect(screen.getByText('No immediate governance, monitoring, drift, or authoring follow-up is open in Retail Banking.')).toBeTruthy()
    expect(screen.queryByText(/Unable to load workflow tiles/i)).toBeNull()
  })

  it('keeps active rules in the overview and out of the workspace summary', () => {
    setupDefaultMocks()
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { id: 'user-1', name: 'Tester', workspaceRoles: [{ workspaceId: 'retail-banking', role: 'admin' }] },
      getCurrentUserRole: () => 'admin',
      canEditGovernance: () => false,
      canApproveGovernance: () => false,
      hasAnyScope: () => false,
    })
    mockUseRules.mockReturnValue({
      rules: [
        { id: 'rule-1', workspace: 'retail-banking', active: true, status: 'activated' },
        { id: 'rule-2', workspace: 'retail-banking', active: true, status: 'activated' },
        { id: 'rule-3', workspace: 'retail-banking', active: false, status: 'draft' },
      ],
      approvals: [],
      auditLog: [],
    })

    render(<Dashboard />)

    expect(screen.getByText('Active Rules', { selector: '.dashboard-card h3' })).toBeTruthy()
    expect(screen.queryByText('Active Rules', { selector: '.dashboard-secondary-summary-title' })).toBeNull()
    expect(screen.getByText('Workspace Status')).toBeTruthy()
    expect(screen.getByText('No immediate governance, monitoring, drift, or authoring follow-up is open in Retail Banking.')).toBeTruthy()
  })

  it('shows author-focused entries without approver or workspace admin sections for rule authors', async () => {
    setupDefaultMocks()
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { id: 'user-1', name: 'Tester', workspaceRoles: [{ workspaceId: 'retail-banking', role: 'analyst' }] },
      getCurrentUserRole: () => 'analyst',
      canApproveRule: () => false,
      canApproveGovernance: () => false,
      canEditGovernance: () => false,
      canManageUsers: () => false,
      hasAnyScope: (scopes: string[]) => scopes.includes('dq:rules:write') || scopes.includes('dq:rules:read'),
    })
    mockUseRules.mockReturnValue({
      rules: [
        { id: 'rule-1', workspace: 'retail-banking', createdBy: 'user-1', active: false, status: 'draft' },
        { id: 'rule-2', workspace: 'retail-banking', createdBy: 'user-2', last_approval_status: 'rejected' },
      ],
      approvals: [],
      auditLog: [],
    })

    render(<Dashboard />)

    expect(await screen.findByText('Rule Author Focus')).toBeTruthy()
    expect(screen.getByText('My Working Rules')).toBeTruthy()
    expect(screen.getByText('Rejected Rules')).toBeTruthy()
    expect(screen.queryByText('Approver Focus')).toBeNull()
    expect(screen.queryByText('Workspace Admin Focus')).toBeNull()
    expect(screen.getByText('Workspace Overview')).toBeTruthy()
    expect(screen.queryByText('Pending Governance Actions')).toBeNull()
    expect(screen.queryByText('Failed Validation Runs')).toBeNull()
    expect(screen.getByTitle('Active Rules: 0')).toBeTruthy()
  })

  it('uses the selected role when a user has multiple roles in the current workspace', async () => {
    setupDefaultMocks()
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: {
        id: 'user-1',
        name: 'Tester',
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'admin' },
          { workspaceId: 'retail-banking', role: 'analyst' },
        ],
      },
      getCurrentUserRole: () => 'analyst',
      canApproveRule: () => false,
      canApproveGovernance: () => false,
      canEditGovernance: () => false,
      canManageUsers: () => false,
      hasAnyScope: (scopes: string[]) => scopes.includes('dq:rules:write') || scopes.includes('dq:rules:read'),
    })
    mockUseRules.mockReturnValue({
      rules: [
        { id: 'rule-1', workspace: 'retail-banking', createdBy: 'user-1', active: false, status: 'draft' },
        { id: 'rule-2', workspace: 'retail-banking', active: true, status: 'activated' },
      ],
      approvals: [],
      auditLog: [],
    })

    render(<Dashboard />)

    expect(await screen.findByText('Rule Author Focus')).toBeTruthy()
    expect(screen.getByText('My Working Rules')).toBeTruthy()
    expect(screen.queryByText('Workspace Admin Focus')).toBeNull()
    expect(screen.getByTitle('Rules that are currently enabled and actively monitoring your data for quality issues')).toBeTruthy()
  })

  it('shows workspace admin operational entries without authoring or approver sections when only admin access applies', async () => {
    setupDefaultMocks()
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: { id: 'admin-1', name: 'Workspace Admin', workspaceRoles: [{ workspaceId: 'retail-banking', role: 'admin' }] },
      getCurrentUserRole: () => 'admin',
      canApproveRule: () => false,
      canApproveGovernance: () => false,
      canEditGovernance: () => false,
      canManageUsers: () => false,
      hasAnyScope: () => false,
    })
    mockUseRules.mockReturnValue({
      rules: [
        { id: 'rule-1', workspace: 'retail-banking', active: true, status: 'activated' },
      ],
      approvals: [],
      auditLog: [],
    })

    render(<Dashboard />)

    expect(await screen.findByText('Workspace Admin Focus')).toBeTruthy()
    expect(screen.getByTitle('Rules that are currently enabled and actively monitoring your data for quality issues')).toBeTruthy()
    expect(screen.queryByText('Rule Author Focus')).toBeNull()
    expect(screen.queryByText('Approver Focus')).toBeNull()
    expect(screen.queryByText('Profiling Activity')).toBeNull()
    expect(screen.queryByText('Pending Governance Actions')).toBeNull()
  })
})
