/* @vitest-environment jsdom */

import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { UserManagement } from './UserManagement'

const updateAdminUser = vi.fn(async () => {})

const settingsMock = {
  adminUsers: [
    {
      id: 'u1',
      firstName: 'Alice',
      lastName: 'Admin',
      email: 'alice@example.com',
      roles: ['viewer'],
      workspaces: ['default'],
      workspaceRoles: [{ workspaceId: 'default', role: 'viewer' }],
    },
  ],
  adminRoles: [
    { id: 'viewer', name: 'Viewer', workspace: 'default', permissions: ['dq:rules:read'] },
    { id: 'analyst', name: 'Analyst', workspace: 'retail-banking', permissions: ['dq:rules:write'] },
  ],
  isLoading: false,
  error: null,
  errorReferenceId: null,
  loadAdminUsers: vi.fn(async () => {}),
  loadAdminRoles: vi.fn(async () => {}),
  updateAdminUser,
  resetUserProfile: vi.fn(async () => {}),
  resetUserSettings: vi.fn(async () => {}),
  clearError: vi.fn(() => {}),
}

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => settingsMock,
}))

describe('UserManagement', () => {
  beforeEach(() => {
    updateAdminUser.mockClear()
    settingsMock.loadAdminUsers.mockClear()
    settingsMock.loadAdminRoles.mockClear()
  })

  it('saves role memberships and derives workspaces from the selected roles', async () => {
    render(<UserManagement />)

    fireEvent.click(screen.getByRole('button', { name: /alice admin/i }))
    fireEvent.click(screen.getByRole('button', { name: /viewer default 1 permissions/i }))
    fireEvent.click(screen.getByRole('button', { name: /analyst retail-banking 1 permissions/i }))
    fireEvent.click(screen.getByRole('button', { name: /save role membership/i }))

    await waitFor(() => {
      expect(updateAdminUser).toHaveBeenCalledWith('u1', {
        roles: ['analyst'],
        workspaces: ['retail-banking'],
      })
    })

    expect(settingsMock.loadAdminUsers).toHaveBeenCalled()
    expect(settingsMock.loadAdminRoles).toHaveBeenCalled()
  })
})