import React, { useEffect, useMemo, useState } from 'react'
import { useSettings } from '../hooks/useContexts'
import { AdminUserSummary } from '../contexts/SettingsContext'
import { Button, PrimaryButton, SecondaryButton } from './Button'
import { AppIcon, AppInput, AppPageShell } from './app-primitives'
import { AdminPageHeader } from './AdminPageHeader'
import { formatSupportReferenceId } from '../utils/supportReference'
import { formatPersonName } from '../utils/personName'
import './Settings.css'

export const UserManagement: React.FC = () => {
  const [userFilter, setUserFilter] = useState('')
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [draftRoles, setDraftRoles] = useState<string[]>([])
  const [isSaving, setIsSaving] = useState(false)
  const settings = useSettings()

  useEffect(() => {
    settings.loadAdminUsers()
    settings.loadAdminRoles()
  }, [settings.loadAdminRoles, settings.loadAdminUsers])

  const selectedUser = useMemo(
    () => settings.adminUsers.find((user) => user.id === selectedUserId) ?? null,
    [selectedUserId, settings.adminUsers],
  )

  const roleOptions = useMemo(
    () => [...settings.adminRoles].sort((left, right) => `${left.workspace}:${left.name}`.localeCompare(`${right.workspace}:${right.name}`)),
    [settings.adminRoles],
  )

  const selectedRoleWorkspaces = useMemo(
    () => Array.from(new Set(
      draftRoles
        .map((roleId) => roleOptions.find((role) => role.id === roleId)?.workspace)
        .filter((workspace): workspace is string => Boolean(workspace)),
    )).sort(),
    [draftRoles, roleOptions],
  )

  useEffect(() => {
    if (!settings.adminUsers.length) {
      setSelectedUserId(null)
      setDraftRoles([])
      return
    }

    if (!selectedUserId || !settings.adminUsers.some((user) => user.id === selectedUserId)) {
      setSelectedUserId(settings.adminUsers[0].id)
    }
  }, [selectedUserId, settings.adminUsers])

  useEffect(() => {
    setDraftRoles(selectedUser?.roles ? [...selectedUser.roles].sort() : [])
  }, [selectedUser?.id, selectedUser?.roles])

  const toggleRole = (roleId: string) => {
    setDraftRoles((current) => (
      current.includes(roleId)
        ? current.filter((value) => value !== roleId)
        : [...current, roleId].sort()
    ))
  }

  const handleSaveRoles = async () => {
    if (!selectedUser) {
      return
    }

    setIsSaving(true)
    try {
      await settings.updateAdminUser(selectedUser.id, {
        roles: draftRoles,
        workspaces: selectedRoleWorkspaces,
      })
      await settings.loadAdminUsers()
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Failed to update user roles')
    } finally {
      setIsSaving(false)
    }
  }

  const handleResetProfile = async (userId: string) => {
    if (window.confirm('Are you sure you want to reset this user\'s profile? This will clear their profile settings.')) {
      try {
        await settings.resetUserProfile(userId)
        alert('User profile reset successfully')
      } catch (error) {
        alert('Failed to reset user profile')
      }
    }
  }

  const handleResetSettings = async (userId: string) => {
    if (window.confirm('Are you sure you want to reset ALL settings for this user? This cannot be undone.')) {
      try {
        await settings.resetUserSettings(userId)
        alert('User settings reset successfully')
      } catch (error) {
        alert('Failed to reset user settings')
      }
    }
  }

  const filteredUsers = settings.adminUsers.filter((user: AdminUserSummary) => {
    if (!userFilter.trim()) return true
    const search = userFilter.toLowerCase()
    const displayName = formatPersonName(user.firstName, user.lastName, user.email || user.id)
    return (
      displayName.toLowerCase().includes(search) ||
      (user.email && user.email.toLowerCase().includes(search)) ||
      user.id.toLowerCase().includes(search) ||
      user.roles.some((role) => role.toLowerCase().includes(search)) ||
      user.workspaces.some((workspace) => workspace.toLowerCase().includes(search))
    )
  })

  if (settings.error && !settings.adminUsers.length) {
    return (
      <AppPageShell className="settings-container">
        <AdminPageHeader
          title="User Management"
          subtitle={
            <>
              {settings.error}
              {settings.errorReferenceId && (
                <>
                  <br />
                  {formatSupportReferenceId(settings.errorReferenceId)}
                </>
              )}
            </>
          }
        />
        <div className="settings-content">
          <div className="settings-panel">
            <div className="settings-actions">
              <PrimaryButton className="user-management-retry-btn" onClick={() => settings.loadAdminUsers()}>
                Retry
              </PrimaryButton>
            </div>
          </div>
        </div>
      </AppPageShell>
    )
  }

  if (settings.isLoading && !settings.adminUsers.length) {
    return (
      <AppPageShell className="settings-container">
        <AdminPageHeader title="User Management" subtitle="Loading users..." />
        <div className="settings-content">
          <div className="settings-panel" />
        </div>
      </AppPageShell>
    )
  }

  return (
    <AppPageShell className="settings-container">
      <AdminPageHeader title="User Management" subtitle="Assign workspace roles and reset user profiles/settings" />
      <div className="settings-content">
        <div className="settings-panel">
          <div className="settings-section">
            <label htmlFor="userFilter">Filter Users</label>
            <AppInput
              label="Filter Users"
              id="userFilter"
              type="text"
              value={userFilter}
              onChange={(e: any) => setUserFilter(e.target.value)}
              placeholder="Search by name, email, or ID..."
            />
          </div>

          <div className="role-management-layout">
            <div className="role-management-list">
              <div className="admin-users">
                {settings.adminUsers.length === 0 && (
                  <div className="admin-empty">No users available.</div>
                )}

                {filteredUsers.map((user: AdminUserSummary) => {
                  const displayName = formatPersonName(user.firstName, user.lastName, user.email || user.id) || user.id
                  return (
                    <div key={user.id} className="admin-user-row">
                      <button
                        type="button"
                        className={`role-row-button ${selectedUser?.id === user.id ? 'active' : ''}`}
                        onClick={() => setSelectedUserId(user.id)}
                      >
                        <div className="admin-user-info">
                          <span className="admin-user-name">{displayName}</span>
                          {user.email && <span className="admin-user-email">{user.email}</span>}
                          <span className="admin-user-id">{user.id}</span>
                          <span className="admin-user-role-summary">
                            {user.roles.length > 0 ? user.roles.join(', ') : 'No roles assigned'}
                          </span>
                          <span className="admin-user-role-summary">
                            {user.workspaces.length > 0 ? user.workspaces.join(', ') : 'No workspaces assigned'}
                          </span>
                        </div>
                      </button>
                      <div className="admin-user-actions">
                        <SecondaryButton
                          className="user-management-action-btn"
                          onClick={() => handleResetProfile(user.id)}
                        >
                          Reset Profile
                        </SecondaryButton>
                        <Button
                          className="user-management-action-btn"
                          variant="primary-destructive"
                          onClick={() => handleResetSettings(user.id)}
                        >
                          Reset All Settings
                        </Button>
                      </div>
                    </div>
                  )
                })}

                {userFilter.trim() && filteredUsers.length === 0 && (
                  <div className="admin-empty">No users match your search.</div>
                )}
              </div>
            </div>

            <div className="role-management-editor">
              <div className="role-management-header">
                <div>
                  <h3>{selectedUser ? formatPersonName(selectedUser.firstName, selectedUser.lastName, selectedUser.email || selectedUser.id) : 'Select a user'}</h3>
                  <p className="settings-hint">Assign roles here. Workspaces are derived from the selected role set.</p>
                </div>
                {selectedUser && (
                  <SecondaryButton className="user-management-action-btn" onClick={() => setDraftRoles([])}>
                    Clear Roles
                  </SecondaryButton>
                )}
              </div>

              {!selectedUser && (
                <div className="admin-empty">Choose a user from the list to edit role membership.</div>
              )}

              {selectedUser && (
                <>
                  <div className="role-management-grid">
                    <div>
                      <label>User ID</label>
                      <div>{selectedUser.id}</div>
                    </div>
                    <div>
                      <label>Current Roles</label>
                      <div>{selectedUser.roles.length > 0 ? selectedUser.roles.join(', ') : 'No roles assigned'}</div>
                    </div>
                    <div>
                      <label>Current Workspaces</label>
                      <div>{selectedUser.workspaces.length > 0 ? selectedUser.workspaces.join(', ') : 'No workspaces assigned'}</div>
                    </div>
                  </div>

                  <div className="role-permissions-section">
                    <h3>Roles</h3>
                    <span className="settings-hint">{draftRoles.length} selected</span>
                    <div className="permission-chip-grid">
                      {roleOptions.length === 0 && <div className="admin-empty">No roles available.</div>}
                      {roleOptions.map((role) => {
                        const isSelected = draftRoles.includes(role.id)
                        return (
                          <button
                            key={role.id}
                            type="button"
                            className={`permission-chip ${isSelected ? 'selected' : ''}`}
                            onClick={() => toggleRole(role.id)}
                          >
                            <strong>{role.name}</strong>
                            <div>{role.workspace}</div>
                            <div>{role.permissions.length} permissions</div>
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  <div className="settings-section">
                    <label>Derived Workspaces</label>
                    <div className="permission-chip-grid">
                      {selectedRoleWorkspaces.length === 0 ? (
                        <div className="admin-empty">No workspaces selected.</div>
                      ) : selectedRoleWorkspaces.map((workspace) => (
                        <span key={workspace} className="permission-chip selected">
                          {workspace}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="role-management-actions">
                    <PrimaryButton className="user-management-action-btn" onClick={handleSaveRoles} disabled={isSaving}>
                      {isSaving ? 'Saving...' : 'Save Role Membership'}
                    </PrimaryButton>
                  </div>
                </>
              )}
            </div>
          </div>

          {settings.error && (
            <div className="settings-message error">
              <AppIcon name="warning" />
              <span>
                {settings.error}
                {settings.errorReferenceId && (
                  <>
                    <br />
                    {formatSupportReferenceId(settings.errorReferenceId)}
                  </>
                )}
              </span>
              <button onClick={() => settings.clearError()}>Dismiss</button>
            </div>
          )}
        </div>
      </div>
    </AppPageShell>
  )
}
