/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { Approvals } from './Approvals'
import { snakeToCamel } from '../utils/caseConverters'

vi.mock('./Button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  PrimaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  SecondaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  TertiaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
}))


vi.mock('./rules/useRuleStatusGovernance', () => ({
  useRuleStatusGovernance: ({ entity }: { entity?: string } = {}) => {
    if (entity === 'rule') {
      return {
        allowedTransitionsByStatus: {
          draft: ['testing'],
          testing: ['tested'],
          tested: ['pending-approval'],
          'pending-approval': ['approved', 'rejected'],
          approved: ['activated'],
          activated: ['deactivated'],
          deactivated: ['draft'],
          rejected: ['draft'],
        },
        statusModel: {
          entity: 'rule',
          statuses: [
            { value: 'draft', label: 'Draft', description: 'Rule has been authored', isInitial: true },
            { value: 'testing', label: 'Testing', description: 'Rule is being tested' },
            { value: 'tested', label: 'Tested', description: 'Rule is ready for review' },
            { value: 'pending-approval', label: 'Pending Approval', description: 'Awaiting reviewer decision' },
            { value: 'approved', label: 'Approved', description: 'Approved and ready for activation' },
            { value: 'activated', label: 'Activated', description: 'Rule is active in production' },
            { value: 'deactivated', label: 'Deactivated', description: 'Rule was deactivated' },
            { value: 'rejected', label: 'Rejected', description: 'Rule was rejected', isTerminal: true },
          ],
          transitions: [
            { fromStatus: 'draft', toStatus: 'testing', label: 'Start Test', requiredAnyScopes: ['dq:rules:test'] },
            { fromStatus: 'testing', toStatus: 'tested', label: 'Mark Tested', requiredAnyScopes: ['dq:rules:test'] },
            { fromStatus: 'tested', toStatus: 'pending-approval', label: 'Submit for Approval', requiredAnyScopes: ['dq:rules:create'] },
            { fromStatus: 'pending-approval', toStatus: 'approved', label: 'Approve', requiredAnyScopes: ['dq:rules:approve'] },
            { fromStatus: 'pending-approval', toStatus: 'rejected', label: 'Reject', requiredAnyScopes: ['dq:rules:approve'] },
            { fromStatus: 'approved', toStatus: 'activated', label: 'Activate', requiredAnyScopes: ['dq:rules:activate'] },
            { fromStatus: 'activated', toStatus: 'deactivated', label: 'Deactivate', requiredAnyScopes: ['dq:rules:approve'] },
            { fromStatus: 'deactivated', toStatus: 'draft', label: 'Reopen', requiredAnyScopes: ['dq:rules:edit'] },
            { fromStatus: 'rejected', toStatus: 'draft', label: 'Reopen', requiredAnyScopes: ['dq:rules:edit'] },
          ],
          allowedTransitionsByStatus: {
            draft: ['testing'],
            testing: ['tested'],
            tested: ['pending-approval'],
            'pending-approval': ['approved', 'rejected'],
            approved: ['activated'],
            activated: ['deactivated'],
            deactivated: ['draft'],
            rejected: ['draft'],
          },
        },
        isLoaded: true,
      }
    }

    if (entity === 'run_plan') {
      return {
        allowedTransitionsByStatus: {
          inactive: ['activation-requested'],
          'activation-requested': ['active', 'inactive'],
          active: ['deactivation-requested'],
          'deactivation-requested': ['deactivated', 'active'],
          deactivated: ['activation-requested'],
        },
        statusModel: {
          entity: 'run_plan',
          statuses: [
            { value: 'inactive', label: 'Inactive', description: 'Plan is not allowed to run', isInitial: true },
            { value: 'activation-requested', label: 'Activation Requested', description: 'Approval requested; plan remains inactive until approved' },
            { value: 'active', label: 'Active', description: 'Plan is allowed to run' },
            { value: 'deactivation-requested', label: 'Deactivation Requested', description: 'Approval requested; plan remains active until approved' },
            { value: 'deactivated', label: 'Deactivated', description: 'Plan is no longer allowed to run', isTerminal: true },
          ],
          transitions: [
            { fromStatus: 'inactive', toStatus: 'activation-requested', label: 'Request Activation', requiredAnyScopes: ['dq:rules:write'] },
            { fromStatus: 'activation-requested', toStatus: 'active', label: 'Approve Activation', requiredAnyScopes: ['dq:rules:approve'] },
            { fromStatus: 'activation-requested', toStatus: 'inactive', label: 'Reject Activation', requiredAnyScopes: ['dq:rules:approve'] },
            { fromStatus: 'active', toStatus: 'deactivation-requested', label: 'Request Deactivation', requiredAnyScopes: ['dq:rules:write'] },
            { fromStatus: 'deactivation-requested', toStatus: 'deactivated', label: 'Approve Deactivation', requiredAnyScopes: ['dq:rules:approve'] },
            { fromStatus: 'deactivation-requested', toStatus: 'active', label: 'Reject Deactivation', requiredAnyScopes: ['dq:rules:approve'] },
          ],
          allowedTransitionsByStatus: {
            inactive: ['activation-requested'],
            'activation-requested': ['active', 'inactive'],
            active: ['deactivation-requested'],
            'deactivation-requested': ['deactivated', 'active'],
            deactivated: ['activation-requested'],
          },
        },
        isLoaded: true,
      }
    }

    return {
      allowedTransitionsByStatus: {
        pending: ['approved', 'rejected'],
        approved: [],
        rejected: [],
      },
      statusModel: {
        entity: 'approval',
        statuses: [
          { value: 'pending', label: 'Pending', description: 'Approval request is waiting for review', isInitial: true },
          { value: 'approved', label: 'Approved', description: 'Approval was accepted', isTerminal: true },
          { value: 'rejected', label: 'Rejected', description: 'Approval was rejected', isTerminal: true },
        ],
        transitions: [
          { fromStatus: 'pending', toStatus: 'approved', label: 'Approve', requiredAnyScopes: ['dq:rules:approve'] },
          { fromStatus: 'pending', toStatus: 'rejected', label: 'Reject', requiredAnyScopes: ['dq:rules:approve'] },
        ],
        allowedTransitionsByStatus: {
          pending: ['approved', 'rejected'],
          approved: [],
          rejected: [],
        },
      },
      isLoaded: true,
    }
  },
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => null,
}))

const mockUseRules = vi.fn()
const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()
const mockUseNotifications = vi.fn()
const mockAddNotification = vi.fn()
const fetchMock = vi.fn()

const normalizeApprovalRequestType = (approval: Record<string, unknown>): string => {
  const requestType = String(approval.requestType ?? approval.request_type ?? 'activation').trim().toLowerCase()
  return requestType === 'deactivation' || requestType === 'gx_suite_repair' ? requestType : 'activation'
}

const buildApprovalsResponse = (url: string) => {
  const parsedUrl = new URL(String(url), 'http://localhost')
  if (!parsedUrl.pathname.endsWith('/approvals')) {
    return null
  }

  const workspace = parsedUrl.searchParams.get('workspace')
  const requestType = parsedUrl.searchParams.get('request_type')
  const requesterId = parsedUrl.searchParams.get('requester_id')
  const excludeRequesterId = parsedUrl.searchParams.get('exclude_requester_id')
  const query = String(parsedUrl.searchParams.get('query') || '').trim().toLowerCase()
  const rules = mockUseRules()?.rules ?? []
  const approvals = mockUseRules()?.approvals ?? []

  const filteredApprovals = approvals.filter((approval: any) => {
    const approvalWorkspaceId = String(approval.workspaceId ?? approval.workspace_id ?? '').trim()
    const rule = rules.find((candidate: any) => String(candidate.id) === String(approval.ruleId ?? approval.rule_id ?? ''))
    const ruleWorkspaceId = String(rule?.workspace || '').trim()
    const currentRequesterId = String(approval.requesterId ?? approval.requester_id ?? '').trim()

    if (workspace && approvalWorkspaceId !== workspace && ruleWorkspaceId !== workspace) {
      return false
    }
    if (requestType && normalizeApprovalRequestType(approval) !== requestType) {
      return false
    }
    if (requesterId && currentRequesterId !== requesterId) {
      return false
    }
    if (excludeRequesterId && currentRequesterId === excludeRequesterId) {
      return false
    }
    if (!query) {
      return true
    }

    const searchFields = [
      approval.ruleId ?? approval.rule_id ?? '',
      currentRequesterId,
      approval.reviewedBy ?? approval.reviewed_by ?? '',
      approval.status ?? '',
      approval.comments ?? '',
    ]
    return searchFields.some((value) => String(value || '').toLowerCase().includes(query))
  })

  return Promise.resolve({
    ok: true,
    json: async () => ({
      data: filteredApprovals,
      pagination: {
        total: filteredApprovals.length,
        page: 1,
        limit: 100,
        total_pages: filteredApprovals.length > 0 ? 1 : 0,
        has_next: false,
        has_previous: false,
      },
    }),
    text: async () => '',
  } as Response)
}

vi.mock('../hooks/useContexts', () => ({
  useRules: () => mockUseRules(),
  useAuth: () => mockUseAuth(),
  useSettings: () => mockUseSettings(),
  useSettingsOptional: () => mockUseSettings(),
  useNotifications: () => mockUseNotifications(),
}))

vi.stubGlobal('fetch', fetchMock)

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  fetchMock.mockReset()
})

const baseRules = [
  {
    id: 'rule-1',
    workspace: 'ws-a',
    name: 'Rule Alpha',
    description: 'desc',
    status: 'pending-approval',
    createdAt: '2026-03-01T00:00:00Z',
    attributes: [],
    riskLevel: 'medium',
  },
  {
    id: 'rule-2',
    workspace: 'ws-a',
    name: 'Rule Legacy',
    description: 'desc',
    status: 'pending-approval',
    createdAt: '2026-03-01T00:00:00Z',
    attributes: [],
    riskLevel: 'medium',
  },
]

const setupCommonMocks = () => {
  fetchMock.mockImplementation((url: string) => {
    const approvalsResponse = buildApprovalsResponse(url)
    if (approvalsResponse) {
      return approvalsResponse
    }

    if (String(url).includes('/exception-fact-access-requests')) {
      return Promise.resolve({
        ok: true,
        json: async () => [],
        text: async () => '[]',
      } as Response)
    }

    return Promise.reject(new Error(`Unexpected URL: ${url}`))
  })

  mockUseSettings.mockReturnValue({
      adminUsers: [
        { id: 'alice-id', name: 'Alice Admin', email: 'alice@example.com' },
        { id: 'other-user', name: 'Bob Reviewer', email: 'bob@example.com' },
      ],
    displaySettings: {
      compactMode: false,
      itemsPerPage: 10,
    },
    workspaceSettings: {
      maxListItems: 50,
    },
    applicationSettings: {
      apiBaseUrl: 'http://localhost:8000/v1',
    },
    notificationSettings: {
      pushNotifications: true,
      emailOnApproval: true,
    },
  })

  mockUseNotifications.mockReturnValue({
    addNotification: mockAddNotification,
  })

  mockUseAuth.mockReturnValue({
    isAuthenticated: true,
    currentWorkspaceId: 'ws-a',
    userId: 'alice-id',
    userName: 'alice-name',
    user: {
      id: 'alice-id',
      email: 'alice@example.com',
      name: 'alice-name',
    },
    canApproveRule: () => true,
    canReadAcrossWorkspaces: () => true,
    canManageUsers: () => true,
  })
}

const makeAccessRequest = (overrides: Record<string, unknown> = {}) => ({
  id: 'access-request-1',
  requester_id: 'other-user',
  workspace_id: 'ws-a',
  role_id: 'exception-fact-investigator',
  status: 'pending',
  requested_duration_minutes: 45,
  comments: 'Need temporary raw detail access',
  requested_at: '2026-05-06T00:00:00Z',
  reviewed_by: null,
  reviewed_at: null,
  expires_at: null,
  ...overrides,
})

describe('Approvals requester canonical contract', () => {
  it('renders requester email in approval cards', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: baseRules,
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          requesterId: 'alice-id',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'activation',
        },
      ],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: (workspaceId: string) => baseRules.filter((rule) => rule.workspace === workspaceId),
      isLoading: false,
    })

    render(<Approvals viewScope="all" />)

    expect(await screen.findByText('Requested by alice@example.com')).toBeTruthy()
  })

  it('posts approval discussion comments and renders the persisted thread', async () => {
    setupCommonMocks()

    const approval = {
      id: 'approval-1',
      ruleId: 'rule-1',
      requesterId: 'alice-id',
      requestedAt: '2026-03-01T00:00:00Z',
      status: 'pending',
      workspaceId: 'ws-a',
      requestType: 'activation',
      commentThread: [
        {
          id: 'audit-1',
          authorId: 'alice-id',
          authorName: 'alice-name',
          content: 'Initial request note',
          type: 'note',
          createdAt: '2026-03-01T00:00:00Z',
        },
      ],
    }

    mockUseRules.mockReturnValue({
      rules: baseRules,
      approvals: [approval],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: (workspaceId: string) => baseRules.filter((rule) => rule.workspace === workspaceId),
      isLoading: false,
    })

    fetchMock.mockImplementation((url: string, options?: RequestInit) => {
      const approvalsResponse = buildApprovalsResponse(url)
      if (approvalsResponse) {
        return approvalsResponse
      }

      if (String(url).includes('/exception-fact-access-requests')) {
        return Promise.resolve({
          ok: true,
          json: async () => [],
          text: async () => '[]',
        } as Response)
      }

      if (String(url).includes('/approvals/approval-1/comments') && (options?.method || 'GET') === 'POST') {
        const body = JSON.parse(String(options?.body || '{}')) as Record<string, unknown>
        return Promise.resolve({
          ok: true,
          json: async () => snakeToCamel({
            id: 'approval-1',
            rule_id: 'rule-1',
            requester_id: 'alice-id',
            requested_at: '2026-03-01T00:00:00Z',
            status: 'pending',
            workspace_id: 'ws-a',
            request_type: 'activation',
            comment_thread: [
              ...approval.commentThread,
              {
                id: 'audit-2',
                author_id: 'user-admin',
                author_name: 'admin',
                content: body.comment,
                type: body.comment_type,
                created_at: '2026-03-02T00:00:00Z',
              },
            ],
          }),
          text: async () => '',
        } as Response)
      }

      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    render(<Approvals viewScope="all" />)

    await screen.findByText('Rule Alpha')
    fireEvent.click(screen.getByRole('button', { name: '▶' }))

    expect(await screen.findByText('Initial request note')).toBeTruthy()

    fireEvent.change(screen.getByPlaceholderText('Add a note or question...'), { target: { value: 'Please attach the contract snapshot.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add Comment' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/rulebuilder/v1/approvals/approval-1/comments'),
        expect.objectContaining({ method: 'POST' }),
      )
    })

    expect(await screen.findByText('Please attach the contract snapshot.')).toBeTruthy()
    expect(mockAddNotification).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Comment posted',
        message: 'The approval discussion was saved.',
      })
    )
  })

  it('shows a human-readable request type for deactivation approvals', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: baseRules,
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          requesterId: 'other-user',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'deactivation',
          effectiveStatus: 'deactivated',
        },
      ],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: (workspaceId: string) => baseRules.filter((rule) => rule.workspace === workspaceId),
      isLoading: false,
    })

    render(<Approvals viewScope="all" />)

    expect(await screen.findByText('Rule Deactivation Request', { selector: '.approval-type-badge' })).toBeTruthy()
    expect(await screen.findByText('Requested by bob@example.com')).toBeTruthy()
    expect(await screen.findByText('Request type:')).toBeTruthy()
    expect(await screen.findByText('Effective status:')).toBeTruthy()
    expect(await screen.findByText('deactivated')).toBeTruthy()
  })

  it('shows global approvals even when the rule record is not loaded', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: [],
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          requesterId: 'alice-id',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'deactivation',
        },
      ],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: () => [],
      isLoading: false,
    })

    render(<Approvals viewScope="global" />)

    expect(await screen.findByText('rule-1')).toBeTruthy()
    expect(await screen.findByText('Rule Deactivation Request', { selector: '.approval-type-badge' })).toBeTruthy()
  })

  it('shows same-workspace pending deactivation approvals even when the rule record is not loaded', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: [],
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          requesterId: 'alice-id',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'deactivation',
        },
      ],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: () => [],
      isLoading: false,
    })

    render(<Approvals viewScope="all" />)

    expect(await screen.findByText('rule-1')).toBeTruthy()
    expect(await screen.findByText('Rule Deactivation Request', { selector: '.approval-type-badge' })).toBeTruthy()
  })

  it('shows pending approvals in the all-across view for admins who can view all workspaces', async () => {
    setupCommonMocks()

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'ws-a',
      userId: 'alice-id',
      userName: 'alice-name',
      user: {
        id: 'alice-id',
        email: 'alice@example.com',
        name: 'alice-name',
      },
      canApproveRule: () => false,
        canReadAcrossWorkspaces: () => true,
      canManageUsers: () => true,
    })

    mockUseRules.mockReturnValue({
      rules: [],
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          requesterId: 'alice-id',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-b',
          requestType: 'deactivation',
        },
      ],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: () => [],
      isLoading: false,
    })

    render(<Approvals viewScope="global" />)

    expect(await screen.findByText('rule-1')).toBeTruthy()
    expect(await screen.findByText('Rule Deactivation Request', { selector: '.approval-type-badge' })).toBeTruthy()
  })

  it('filters my-scope by requesterId and does not rely on requestedBy fallback', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: baseRules,
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          requesterId: 'alice-id',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'activation',
        },
        {
          id: 'approval-2',
          ruleId: 'rule-2',
          requesterId: 'other-user',
          requestedBy: 'alice-id',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'activation',
        },
      ],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: (workspaceId: string) => baseRules.filter((rule) => rule.workspace === workspaceId),
      isLoading: false,
    })

    render(<Approvals viewScope="my" />)

    expect(await screen.findByText('Rule Alpha')).toBeTruthy()
    expect(screen.queryByText('Rule Legacy')).toBeNull()
  })

  it('requests approvals with API-backed my-scope filters', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: baseRules,
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          requesterId: 'alice-id',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'activation',
        },
      ],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: (workspaceId: string) => baseRules.filter((rule) => rule.workspace === workspaceId),
      isLoading: false,
    })

    render(<Approvals viewScope="my" />)

    await screen.findByText('Rule Alpha')

    const approvalsRequest = fetchMock.mock.calls.find(([url]) => String(url).includes('/approvals?'))
    expect(String(approvalsRequest?.[0])).toContain('workspace=ws-a')
    expect(String(approvalsRequest?.[0])).toContain('requester_id=alice-id')
  })

  it('disables approve for self-requested approvals', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: baseRules,
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          requesterId: 'alice-id',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'deactivation',
        },
      ],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: (workspaceId: string) => baseRules.filter((rule) => rule.workspace === workspaceId),
      isLoading: false,
    })

    render(<Approvals viewScope="my" />)

    await screen.findByText('Rule Alpha')
    fireEvent.click(screen.getByRole('button', { name: '▶' }))

    expect((screen.getByRole('button', { name: 'Approve' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('renders approvals after snake_case normalization', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: baseRules,
      approvals: [
        snakeToCamel({
          id: 'approval-1',
          rule_id: 'rule-1',
          requester_id: 'alice-id',
          requested_at: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspace_id: 'ws-a',
          request_type: 'deactivation',
          effective_status: 'deactivated',
        }),
      ],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: (workspaceId: string) => baseRules.filter((rule) => rule.workspace === workspaceId),
      isLoading: false,
    })

    render(<Approvals viewScope="my" />)

    expect(await screen.findByText('Requested by alice@example.com')).toBeTruthy()
    expect(await screen.findByText('Effective status:')).toBeTruthy()
    expect(await screen.findByText('deactivated')).toBeTruthy()
  })

  it('loads governance inboxes from the backend contract and renders the queue summaries', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: baseRules,
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-2',
          requesterId: 'alice-id',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'activation',
        },
      ],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: (workspaceId: string) => baseRules.filter((rule) => rule.workspace === workspaceId),
      isLoading: false,
    })

    fetchMock.mockImplementation((url: string) => {
      const approvalsResponse = buildApprovalsResponse(url)
      if (approvalsResponse) {
        return approvalsResponse
      }

      if (String(url).includes('/governance/inboxes')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            approval_inbox: {
              data: [
                {
                  id: 'approval-1',
                  rule_id: 'rule-2',
                  requester_id: 'alice-id',
                  requested_at: '2026-03-01T00:00:00Z',
                  status: 'pending',
                  workspace_id: 'ws-a',
                  request_type: 'activation',
                },
              ],
              pagination: {
                total: 1,
                page: 1,
                limit: 10,
                total_pages: 1,
                has_next: false,
                has_previous: false,
              },
            },
            reassignment_inbox: {
              data: [
                {
                  id: 'rule-reassign',
                  name: 'Needs reassignment',
                  status: 'active',
                  lifecycle_status: 'active',
                  workspace: 'ws-a',
                  data_steward: 'alice@example.com',
                  domain_owner: null,
                  technical_owner: null,
                },
              ],
              pagination: {
                total: 1,
                page: 1,
                limit: 10,
                total_pages: 1,
                has_next: false,
                has_previous: false,
              },
            },
            deprecation_review_inbox: {
              data: [
                {
                  id: 'rule-deprecated',
                  name: 'Deprecated rule',
                  status: 'inactive',
                  lifecycle_status: 'deprecated',
                  workspace: 'ws-a',
                  data_steward: 'alice@example.com',
                  domain_owner: 'domain-owner@example.com',
                  technical_owner: 'tech-owner@example.com',
                  pending_deactivation_requested: true,
                },
              ],
              pagination: {
                total: 1,
                page: 1,
                limit: 10,
                total_pages: 1,
                has_next: false,
                has_previous: false,
              },
            },
          }),
          text: async () => '',
        } as Response)
      }

      if (String(url).includes('/exception-fact-access-requests')) {
        return Promise.resolve({
          ok: true,
          json: async () => [],
          text: async () => '[]',
        } as Response)
      }

      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    render(<Approvals viewScope="all" />)

    fireEvent.click(await screen.findByRole('tab', { name: 'Governance' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/rulebuilder/v1/governance/inboxes?page=1&limit=10&workspace_id=ws-a'),
        expect.objectContaining({ headers: expect.any(Object) }),
      )
    })

    expect(await screen.findByText('Governance inboxes')).toBeTruthy()
    expect(await screen.findByText('Approval inbox')).toBeTruthy()
    expect(await screen.findByText('Reassignment inbox')).toBeTruthy()
    expect(await screen.findByText('Deprecation review inbox')).toBeTruthy()
    expect(await screen.findByText('Rule Legacy')).toBeTruthy()
    expect(await screen.findByText('Needs reassignment')).toBeTruthy()
    expect(await screen.findByText('Deprecated rule')).toBeTruthy()
  })

  it('approves exception-record access requests from the approval queue', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: [],
      approvals: [],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: () => [],
      isLoading: false,
    })

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'ws-a',
      userId: 'alice-id',
      userName: 'alice-name',
      user: {
        id: 'alice-id',
        email: 'alice@example.com',
        name: 'alice-name',
        workspaceRoles: [
          {
            workspaceId: 'ws-a',
            role: 'admin',
          },
        ],
      },
      canApproveRule: () => false,
      canReadAcrossWorkspaces: () => false,
      canManageUsers: () => true,
    })

    const requests = [makeAccessRequest()]

    fetchMock.mockImplementation((url: string, options?: RequestInit) => {
      const approvalsResponse = buildApprovalsResponse(url)
      if (approvalsResponse) {
        return approvalsResponse
      }

      if (!String(url).includes('/admin/v1/exception-fact-access-requests')) {
        return Promise.reject(new Error(`Unexpected URL: ${url}`))
      }

      if ((options?.method || 'GET') === 'PUT') {
        const body = JSON.parse(String(options?.body || '{}')) as Record<string, unknown>
        const updated = makeAccessRequest({
          status: body.status,
          reviewed_by: 'alice-id',
          reviewed_at: '2026-05-06T01:00:00Z',
          expires_at: '2026-05-06T02:00:00Z',
          comments: body.comments,
        })
        requests.splice(0, requests.length, updated)
        return Promise.resolve({
          ok: true,
          json: async () => updated,
          text: async () => JSON.stringify(updated),
        } as Response)
      }

      return Promise.resolve({
        ok: true,
        json: async () => requests,
        text: async () => JSON.stringify(requests),
      } as Response)
    })

    render(<Approvals viewScope="all" />)

    expect(await screen.findByText('Access Requests')).toBeTruthy()
    expect(await screen.findByText('Exception Fact Investigator Request')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '▶' }))
    fireEvent.change(screen.getByLabelText('Decision Comment (optional)'), { target: { value: 'Approved for short-term investigation' } })
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/admin/v1/exception-fact-access-requests/access-request-1'),
        expect.objectContaining({ method: 'PUT' }),
      )
    })

    expect(mockAddNotification).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Access Request Approved',
        message: 'Exception-record access request approved.',
      })
    )
  })

  it('shows an empty access-request state when the access list is not found', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: [],
      approvals: [],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: () => [],
      isLoading: false,
    })

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'ws-a',
      userId: 'alice-id',
      userName: 'alice-name',
      user: {
        id: 'alice-id',
        email: 'alice@example.com',
        name: 'alice-name',
        workspaceRoles: [
          {
            workspaceId: 'ws-a',
            role: 'admin',
          },
        ],
      },
      canApproveRule: () => false,
      canReadAcrossWorkspaces: () => false,
      canManageUsers: () => true,
    })

    fetchMock.mockImplementation((url: string) => {
      const approvalsResponse = buildApprovalsResponse(url)
      if (approvalsResponse) {
        return approvalsResponse
      }

      if (!String(url).includes('/admin/v1/exception-fact-access-requests')) {
        return Promise.reject(new Error(`Unexpected URL: ${url}`))
      }

      return Promise.resolve({
        ok: false,
        status: 404,
        json: async () => [],
        text: async () => '',
      } as Response)
    })

    render(<Approvals viewScope="all" />)

    expect(await screen.findByText('Access Requests')).toBeTruthy()
    expect(await screen.findByText('No exception-record access requests to review.')).toBeTruthy()
    expect(screen.queryByText(/Unable to load exception-record access requests/)).toBeNull()
  })

  it('shows a specific message when the approval API rejects self-approval', async () => {
    setupCommonMocks()

    const approveRule = vi.fn(async () => {
      throw new Error('Failed to approve rule: Requester cannot approve their own request')
    })

    mockUseRules.mockReturnValue({
      rules: baseRules,
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          requesterId: 'other-user',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'deactivation',
        },
      ],
      approveRule,
      rejectRule: vi.fn(),
      getRulesByWorkspace: (workspaceId: string) => baseRules.filter((rule) => rule.workspace === workspaceId),
      isLoading: false,
    })

    render(<Approvals viewScope="all" />)

    await screen.findByText('Rule Alpha')
    fireEvent.click(screen.getByRole('button', { name: '▶' }))

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    })

    expect(mockAddNotification).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'error',
        title: 'Approval Failed',
        message: 'You cannot approve your own request. Ask another approver to review it.',
        relatedId: 'approval-1',
      }),
    )
  })

  it('renders backend governance matrices in the governance view', () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: baseRules,
      approvals: [],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: (workspaceId: string) => baseRules.filter((rule) => rule.workspace === workspaceId),
      isLoading: false,
    })

    render(<Approvals viewScope="my" />)

    expect(screen.getByRole('heading', { name: 'Governance' })).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: 'Governance' }))

    expect(screen.getByText('Rule lifecycle')).toBeTruthy()
    expect(screen.getByText('Approval lifecycle')).toBeTruthy()
    expect(screen.getByText('DQ run plan lifecycle')).toBeTruthy()
    expect(screen.getByText(/backend-defined governance policy/i)).toBeTruthy()
  })

  it('lets the user switch approval scope inline', async () => {
    setupCommonMocks()

    mockUseRules.mockReturnValue({
      rules: baseRules,
      approvals: [
        {
          id: 'approval-my',
          ruleId: 'rule-1',
          requesterId: 'alice-id',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'activation',
        },
        {
          id: 'approval-team',
          ruleId: 'rule-2',
          requesterId: 'other-user',
          requestedAt: '2026-03-01T00:00:00Z',
          status: 'pending',
          workspaceId: 'ws-a',
          requestType: 'activation',
        },
      ],
      approveRule: vi.fn(),
      rejectRule: vi.fn(),
      getRulesByWorkspace: (workspaceId: string) => baseRules.filter((rule) => rule.workspace === workspaceId),
      isLoading: false,
    })

    render(<Approvals viewScope="all" />)

    expect(await screen.findByText('Rule Alpha')).toBeTruthy()
    expect(await screen.findByText('Rule Legacy')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: /^my$/i }))

    await waitFor(() => {
      expect(screen.getByText('Rule Alpha')).toBeTruthy()
      expect(screen.queryByText('Rule Legacy')).toBeNull()
    })

    fireEvent.click(screen.getByRole('tab', { name: /my team's/i }))

    await waitFor(() => {
      expect(screen.queryByText('Rule Alpha')).toBeNull()
      expect(screen.getByText('Rule Legacy')).toBeTruthy()
    })
  })
})
