import React, { useEffect, useMemo, useState } from 'react'
import { Button, PrimaryButton, SecondaryButton } from './Button'
import { AppInput, AppPageShell } from './app-primitives'
import { AdminPageHeader } from './AdminPageHeader'
import { AdminRoleSummary } from '../contexts/SettingsContext'
import { useSettings } from '../hooks/useContexts'
import { formatSupportReferenceId } from '../utils/supportReference'
import './Settings.css'

const AVAILABLE_PERMISSIONS = [
  'dq:admin:read',
  'dq:users:manage',
  'dq:workspace:manage',
  'dq:config:manage',
  'dq:workspace:read',
  'dq:rules:read',
  'dq:rules:write',
  'dq:rules:create',
  'dq:rules:edit',
  'dq:rules:delete',
  'dq:rules:test',
  'dq:rules:approve',
  'dq:rules:activate',
  'dq:profiling:request',
  'dq:data_catalog:read',
  'dq:reports:read',
  'dq:audit:read',
  'dq:templates:read',
  'dq:templates:write',
  'dq:notifications:read',
]

interface RoleDraft {
  id: string
  name: string
  workspace: string
  permissions: string[]
}

const EMPTY_DRAFT: RoleDraft = {
  id: '',
  name: '',
  workspace: 'default',
  permissions: [],
}

export const RoleManagement: React.FC = () => {
  const settings = useSettings()
  const [filter, setFilter] = useState('')
  const [draft, setDraft] = useState<RoleDraft>(EMPTY_DRAFT)
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null)

  useEffect(() => {
    settings.loadAdminRoles()
  }, [settings.loadAdminRoles])

  const selectedRole = useMemo(
    () => settings.adminRoles.find((role) => role.id === selectedRoleId) ?? null,
    [selectedRoleId, settings.adminRoles],
  )

  useEffect(() => {
    if (!selectedRole) {
      return
    }
    setDraft({
      id: selectedRole.id,
      name: selectedRole.name,
      workspace: selectedRole.workspace,
      permissions: [...selectedRole.permissions],
    })
  }, [selectedRole])

  const filteredRoles = settings.adminRoles.filter((role: AdminRoleSummary) => {
    if (!filter.trim()) {
      return true
    }
    const search = filter.toLowerCase()
    return [role.id, role.name, role.workspace, role.permissions.join(' ')].join(' ').toLowerCase().includes(search)
  })

  const resetDraft = () => {
    setSelectedRoleId(null)
    setDraft(EMPTY_DRAFT)
  }

  const togglePermission = (permission: string) => {
    setDraft((current) => ({
      ...current,
      permissions: current.permissions.includes(permission)
        ? current.permissions.filter((value) => value !== permission)
        : [...current.permissions, permission].sort(),
    }))
  }

  const handleSave = async () => {
    if (!draft.id.trim() || !draft.name.trim()) {
      alert('Role ID and role name are required.')
      return
    }

    try {
      if (selectedRoleId) {
        await settings.updateAdminRole(selectedRoleId, {
          name: draft.name.trim(),
          workspace: draft.workspace.trim() || 'default',
          permissions: draft.permissions,
        })
        alert('Role updated successfully')
      } else {
        await settings.createAdminRole({
          id: draft.id.trim(),
          name: draft.name.trim(),
          workspace: draft.workspace.trim() || 'default',
          permissions: draft.permissions,
        })
        alert('Role created successfully')
      }
      resetDraft()
    } catch {
      alert(selectedRoleId ? 'Failed to update role' : 'Failed to create role')
    }
  }

  if (settings.error && !settings.adminRoles.length) {
    return (
      <AppPageShell className="settings-container">
        <AdminPageHeader
          title="Role Management"
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
              <PrimaryButton onClick={() => settings.loadAdminRoles()}>Retry</PrimaryButton>
            </div>
          </div>
        </div>
      </AppPageShell>
    )
  }

  return (
    <AppPageShell className="settings-container">
      <AdminPageHeader
        title="Role Management"
        subtitle="Define workspace and cross-workspace roles with explicit permissions."
      />
      <div className="settings-content">
        <div className="settings-panel">
          <div className="role-management-layout">
            <section className="role-management-list">
              <div className="settings-section">
                <label htmlFor="roleFilter">Filter Roles</label>
                <AppInput
                  label="Filter Roles"
                  id="roleFilter"
                  type="text"
                  value={filter}
                  onChange={(event: any) => setFilter(event.target.value)}
                  placeholder="Search by ID, name, workspace, or permission..."
                />
              </div>

              <div className="admin-users">
                {filteredRoles.map((role) => (
                  <button
                    key={role.id}
                    className={`admin-user-row role-row-button${selectedRoleId === role.id ? ' active' : ''}`}
                    onClick={() => setSelectedRoleId(role.id)}
                    type="button"
                  >
                    <div className="admin-user-info">
                      <span className="admin-user-name">{role.name}</span>
                      <span className="admin-user-email">{role.workspace}</span>
                      <span className="admin-user-id">{role.id}</span>
                    </div>
                    <span className="role-permission-count">{role.permissions.length} permissions</span>
                  </button>
                ))}

                {filteredRoles.length === 0 && <div className="admin-empty">No roles match your search.</div>}
              </div>
            </section>

            <section className="role-management-editor settings-section">
              <div className="role-management-header">
                <h3>{selectedRoleId ? 'Edit Role' : 'Create Role'}</h3>
                <SecondaryButton onClick={resetDraft}>New Role</SecondaryButton>
              </div>

              <div className="role-management-grid">
                <div>
                  <label htmlFor="roleId">Role ID</label>
                  <AppInput
                    label="Role ID"
                    id="roleId"
                    type="text"
                    value={draft.id}
                    disabled={Boolean(selectedRoleId)}
                    onChange={(event: any) => setDraft((current) => ({ ...current, id: event.target.value }))}
                    placeholder="example: data-steward"
                  />
                </div>

                <div>
                  <label htmlFor="roleName">Role Name</label>
                  <AppInput
                    label="Role Name"
                    id="roleName"
                    type="text"
                    value={draft.name}
                    onChange={(event: any) => setDraft((current) => ({ ...current, name: event.target.value }))}
                    placeholder="Display name"
                  />
                </div>

                <div>
                  <label htmlFor="roleWorkspace">Workspace Scope</label>
                  <AppInput
                    label="Workspace Scope"
                    id="roleWorkspace"
                    type="text"
                    value={draft.workspace}
                    onChange={(event: any) => setDraft((current) => ({ ...current, workspace: event.target.value }))}
                    placeholder="default or global"
                  />
                </div>
              </div>

              <div className="role-permissions-section">
                <div className="role-management-header">
                  <h3>Permissions</h3>
                  <span className="settings-hint">{draft.permissions.length} selected</span>
                </div>
                <div className="permission-chip-grid">
                  {AVAILABLE_PERMISSIONS.map((permission) => {
                    const isSelected = draft.permissions.includes(permission)
                    return (
                      <button
                        key={permission}
                        type="button"
                        className={`permission-chip${isSelected ? ' selected' : ''}`}
                        onClick={() => togglePermission(permission)}
                      >
                        {permission}
                      </button>
                    )
                  })}
                </div>
              </div>

              <div className="admin-user-actions role-management-actions">
                <PrimaryButton onClick={handleSave}>{selectedRoleId ? 'Save Changes' : 'Create Role'}</PrimaryButton>
                <Button variant="secondary" onClick={resetDraft}>Clear</Button>
              </div>
            </section>
          </div>

          {settings.error && (
            <div className="settings-message error">
              <span className="settings-message-icon">!</span>
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