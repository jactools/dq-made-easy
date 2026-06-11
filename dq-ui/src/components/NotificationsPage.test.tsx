/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

import { NotificationsPage } from './NotificationsPage'

const mockUseAuth = vi.fn()
const mockUseRules = vi.fn()
const mockUseSettings = vi.fn()
const mockUseNotifications = vi.fn()

vi.mock('../hooks/useContexts', () => ({
  useAuth: () => mockUseAuth(),
  useRules: () => mockUseRules(),
  useSettings: () => mockUseSettings(),
  useSettingsOptional: () => mockUseSettings(),
  useNotifications: () => mockUseNotifications(),
}))

afterEach(() => {
  cleanup()
  localStorage.clear()
  vi.clearAllMocks()
})

describe('NotificationsPage', () => {
  it('renders pending approvals from the current workspace as notifications', () => {
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'retail-banking',
      user: {
        id: 'u1',
      },
    })

    mockUseRules.mockReturnValue({
      approvals: [
        {
          id: 'approval-1',
          ruleId: 'rule-1',
          requesterId: 'alice@jaccloud.nl',
          requestedAt: '2026-04-10T10:00:00Z',
          status: 'pending',
          requestType: 'activation',
          effectiveStatus: 'activated',
        },
        {
          id: 'approval-2',
          ruleId: 'rule-2',
          requesterId: 'bob@jaccloud.nl',
          requestedAt: '2026-04-10T11:00:00Z',
          status: 'pending',
          requestType: 'deactivation',
          effectiveStatus: 'deactivated',
        },
      ],
      rules: [
        { id: 'rule-1', workspace: 'retail-banking' },
        { id: 'rule-2', workspace: 'retail-banking' },
      ],
    })

    mockUseSettings.mockReturnValue({
      notificationSettings: {
        pushNotifications: true,
        emailOnApproval: true,
      },
    })

    mockUseNotifications.mockReturnValue({
      notifications: [],
      markAsRead: vi.fn(),
      markAllAsRead: vi.fn(),
      pushNotificationsEnabled: true,
    })

    render(<NotificationsPage />)

    expect(screen.getByText('2 unread')).toBeTruthy()
    expect(screen.getByText('Rule Awaiting Approval')).toBeTruthy()
    expect(screen.getByText('Deactivation Awaiting Approval')).toBeTruthy()
    expect(screen.getByText('Effective: activated')).toBeTruthy()
    expect(screen.getByText('Effective: deactivated')).toBeTruthy()
    expect(screen.getByText('alice@jaccloud.nl requested approval review')).toBeTruthy()
    expect(screen.getByText('bob@jaccloud.nl requested deactivation review')).toBeTruthy()
  })
})