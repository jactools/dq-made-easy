/** @vitest-environment jsdom */

import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { Settings } from './Settings'

const mockUseSettings = vi.fn()
const mockUseAuth = vi.fn()

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
  useAuth: () => mockUseAuth(),
}))

vi.mock('./Button', async () => {
  const React = await import('react')
  const Button = ({ children, ...props }: any) => React.createElement('button', { type: 'button', ...props }, children)
  return { Button, PrimaryButton: Button, SecondaryButton: Button, TertiaryButton: Button }
})

const buildSettingsValue = () => ({
  userSettings: {
    firstName: 'Ada',
    lastName: 'Lovelace',
    email: 'ada@example.com',
    phone: '',
    language: 'en',
    timezone: 'UTC',
  },
  notificationSettings: {
    emailOnApproval: true,
    emailOnRejection: false,
    emailOnTestingFailure: true,
    emailDigestFrequency: 'daily',
    pushNotifications: false,
    teamsIntegration: false,
    teamsChannelId: '',
    teamsChannelName: '',
    teamsChannels: [],
  },
  displaySettings: {
    theme: 'light',
    compactMode: false,
    showTooltips: true,
    preferredDateFormat: 'DD/MM/YYYY',
    participateInPreviews: false,
    itemsPerPage: 10,
  },
  workspaceSettings: {
    defaultRiskLevel: 'medium',
    requiresApprovalForActivation: true,
    requiresTestingBeforeApproval: true,
    autoRetestInterval: 30,
    maxListItems: 25,
    enabledDataSources: ['crm'],
    ruleNamingPrefix: 'DQ_',
  },
  error: null,
  errorReferenceId: null,
  updateSettings: vi.fn(async () => {}),
  loadSettings: vi.fn(async () => {}),
})

describe('Settings header pills', () => {
  it('moves settings tabs into the header and switches content via pills', () => {
    mockUseSettings.mockReturnValue(buildSettingsValue())
    mockUseAuth.mockReturnValue({
      getCurrentUserRole: () => 'analyst',
    })

    render(<Settings />)

    expect(screen.getByRole('tab', { name: 'Profile' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Notifications' })).toBeTruthy()
    expect(screen.queryByRole('tab', { name: 'Workspace' })).toBeNull()
    expect(screen.getByText('Profile Settings')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: 'Notifications' }))

    expect(screen.getByText('Notification Preferences')).toBeTruthy()
  })
})