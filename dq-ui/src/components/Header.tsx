import React from 'react'
import { useAuth } from '../hooks/useKeycloak'
import { useRules, useSettings } from '../hooks/useContexts'
import { WorkspaceSelector, getWorkspaceDisplayName } from './WorkspaceSelector'
import { NotificationCenter } from './NotificationCenter'
import { VersionInfoModal } from './VersionInfoModal'
import { NotificationItem } from '../contexts/NotificationContext'
import { useVersionCatalog } from '../hooks/useVersionCatalog'
import { NotificationSnoozeControl } from './NotificationSnoozeControl'
import { Button } from './Button'
import { AppIcon } from './app-primitives'
import './VersionInfoModal.css'

const sameId = (a: unknown, b: unknown): boolean => String(a) === String(b)

const formatRoleLabel = (role: string): string => {
  const normalized = role.trim().toLowerCase()
  if (normalized === 'data-steward') return 'Data Steward'
  if (normalized === 'cross-admin') return 'Cross-Admin'
  if (normalized === 'exception-fact-reader') return 'Exception Fact Reader'
  if (normalized === 'exception-fact-investigator') return 'Exception Fact Investigator'
  return normalized
    .split('-')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

// These are injected by Vite at build time from package.json and build timestamp
declare const __BUILD_DATE__: string

export const Header: React.FC<{
  onLoginClick: () => void
  onHelpClick?: () => void
  onSettingsClick?: () => void
  onNavigate?: (page: string) => void
  maintenanceActive?: boolean
  children?: React.ReactNode
}> = ({ onLoginClick, onHelpClick, onSettingsClick, onNavigate, maintenanceActive = false, children }) => {
  const auth = useAuth()
  const rules = useRules()
  const settings = useSettings()
  const [isDarkMode, setIsDarkMode] = React.useState(false)
  const [showVersionModal, setShowVersionModal] = React.useState(false)
  const [showUserMenu, setShowUserMenu] = React.useState(false)
  const userMenuRef = React.useRef<HTMLDivElement | null>(null)
  const { versionCatalog } = useVersionCatalog()
  const uiVersion = versionCatalog.apps.ui || __APP_VERSION__
  const hasAdminRole = Boolean(
    auth.user?.workspaceRoles?.some((workspaceRole) => workspaceRole.role === 'admin')
  )
  const isAdminModeActive = hasAdminRole && auth.isAdminModeEnabled

  const currentWorkspace = React.useMemo(() => {
    const workspaceRoles = auth.user?.workspaceRoles || []
    if (workspaceRoles.length === 0) {
      return null
    }

    if (auth.currentWorkspaceId) {
      const selectedWorkspace = workspaceRoles.find(
        (workspaceRole) => String(workspaceRole.workspaceId) === String(auth.currentWorkspaceId)
      )
      if (selectedWorkspace) {
        return selectedWorkspace
      }
    }

    if (workspaceRoles.length === 1) {
      return workspaceRoles[0]
    }

    return null
  }, [auth.currentWorkspaceId, auth.user?.workspaceRoles])

  const currentRole = auth.getCurrentUserRole()
  const currentRoleLabel = currentRole ? formatRoleLabel(currentRole) : null
  const showRoleBadge = Boolean(currentRoleLabel && !(isAdminModeActive && currentRole === 'admin'))

  // Watch for theme changes
  React.useEffect(() => {
    const updateTheme = () => {
      const theme = document.documentElement.getAttribute('data-theme')
      setIsDarkMode(theme === 'dark')
    }

    // Initial check
    updateTheme()

    // Watch for theme attribute changes
    const observer = new MutationObserver(updateTheme)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme']
    })

    return () => observer.disconnect()
  }, [])

  const isAdminUser = auth.getCurrentUserRole() === 'admin'

  React.useEffect(() => {
    const handleDocumentClick = (event: MouseEvent) => {
      if (!showUserMenu) return
      const target = event.target as Node | null
      if (target && userMenuRef.current?.contains(target)) {
        return
      }
      setShowUserMenu(false)
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowUserMenu(false)
      }
    }

    document.addEventListener('mousedown', handleDocumentClick)
    document.addEventListener('keydown', handleEscape)

    return () => {
      document.removeEventListener('mousedown', handleDocumentClick)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [showUserMenu])

  React.useEffect(() => {
    if (!auth.isAuthenticated) {
      setShowUserMenu(false)
    }
  }, [auth.isAuthenticated])

  const handleNotificationNavigation = React.useCallback((notification: NotificationItem) => {
    if (!onNavigate) return
    const url = notification.actionUrl || ''
    if (url.startsWith('/approvals')) { onNavigate('approvals'); return }
    if (url.startsWith('/rules')) { onNavigate('rules'); return }
    switch (notification.type) {
      case 'approval-pending':
      case 'rule-rejected':
        onNavigate('approvals')
        break
      case 'rule-activated':
      case 'test-completed':
        onNavigate('rules')
        break
      default:
        break
    }
  }, [onNavigate])

  const pendingApprovalsForCurrentWorkspace = React.useMemo(() => {
    if (!auth.currentWorkspaceId) return []

    return (rules.approvals || []).filter((approval) => {
      if (approval.status !== 'pending') return false
      if (String(approval.workspaceId || '').trim()) {
        return String(approval.workspaceId).trim() === auth.currentWorkspaceId
      }
      const approvalRule = rules.rules.find((rule) => sameId(rule.id, approval.ruleId))
      return approvalRule?.workspace === auth.currentWorkspaceId
    })
  }, [rules.approvals, rules.rules, auth.currentWorkspaceId])

  return (
    <header className="app-header">
      <div className="header-content">
        <div className="logo-section">
          <div className="logo">
            <button
              type="button"
              className="logo-button"
              onClick={() => onNavigate?.('dashboard')}
              aria-label="Go to homepage"
            >
              <img
                src={isDarkMode ? '/assets/dq-made-easy-dark.svg' : '/assets/dq-made-easy-light.svg'}
                alt="Data Quality Made Easy"
                className="logo-image"
              />
            </button>
          </div>
          <div 
            className="version-info" 
            title={`Click for system information - Version ${uiVersion} (${__BUILD_DATE__})`}
            onClick={() => setShowVersionModal(true)}
            style={{ cursor: 'pointer' }}
          >
            <span className="version-label">v{uiVersion}</span>
          </div>
        </div>

        <div className="header-actions">
          {auth.isAuthenticated && (
            <NotificationCenter 
              pendingApprovals={pendingApprovalsForCurrentWorkspace}
              onNotificationClick={handleNotificationNavigation}
              onNavigate={onNavigate}
            />
          )}
          {auth.isAuthenticated && currentWorkspace && (
            <div className="workspace-info" title={`Current workspace: ${getWorkspaceDisplayName(currentWorkspace.workspaceId)} (${currentRoleLabel || currentWorkspace.role})`}>
              <div className="current-workspace">
                <p className="workspace-label">Current workspace</p>
                <span className="workspace-name">{getWorkspaceDisplayName(currentWorkspace.workspaceId)}</span>
              </div>
              {showRoleBadge && (
                <span className={`user-role-indicator user-role-indicator-${currentRole}`} title={`Current role: ${currentRoleLabel}`}>
                  {currentRoleLabel}
                </span>
              )}
            </div>
          )}
          {onHelpClick && (
            <button
              type="button"
              className="help-trigger"
              aria-label="help and documentation"
              title="Help & Documentation"
              onClick={onHelpClick}
            >
                <AppIcon name="question-mark" />
            </button>
          )}
          <button
            type="button"
            className="settings-trigger"
            aria-label="settings"
            title="Settings"
            onClick={onSettingsClick}
          >
            <AppIcon name="sliders" />
          </button>

          {auth.isAuthenticated && maintenanceActive && isAdminUser && (
            <span className="maintenance-indicator" title="Maintenance mode is enabled. Admin bypass is active.">
              Maintenance Active
            </span>
          )}

          {auth.isAuthenticated && hasAdminRole && isAdminModeActive && (
            <span className="admin-mode-indicator" title="Admin mode is enabled. Use the user menu to temporarily disable it.">
              Admin Mode
            </span>
          )}

          {auth.isAuthenticated && auth.user ? (
            <div className="user-menu" ref={userMenuRef}>
              <button
                type="button"
                className="user-menu-trigger"
                onClick={() => setShowUserMenu(prev => !prev)}
                aria-expanded={showUserMenu}
                aria-haspopup="menu"
              >
                <div className="user-info">
                  {auth.user.avatarUrl && (
                    <img src={auth.user.avatarUrl} alt={auth.user.name} className="avatar" />
                  )}
                  <span className="user-name">{auth.user.name}</span>
                </div>
                <AppIcon name={showUserMenu ? 'chevron-up' : 'chevron-down'} />
              </button>
              {showUserMenu && (
                <div className="user-menu-dropdown" role="menu" aria-label="User menu">
                  <WorkspaceSelector onWorkspaceSelected={() => setShowUserMenu(false)} />
                  {hasAdminRole && (
                    <Button
                      onClick={() => {
                        auth.setAdminModeEnabled(!auth.isAdminModeEnabled)
                        setShowUserMenu(false)
                      }}
                      variant="secondary"
                    >
                      <AppIcon slot="icon" name="shield-check" />
                      {auth.isAdminModeEnabled ? 'Disable admin mode' : 'Enable admin mode'}
                    </Button>
                  )}
                  <NotificationSnoozeControl
                    compact
                    snoozedUntil={settings.notificationSettings?.snoozedUntil}
                    onChange={(snoozedUntil) => {
                      void settings.updateSettings({
                        category: 'notifications',
                        data: { snoozedUntil },
                      })
                    }}
                  />
                  <Button onClick={() => auth.logout()} variant="secondary">
                    <AppIcon slot="icon" name="power" />
                    Logout
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <Button onClick={onLoginClick} variant="tertiary">
              Login
            </Button>
          )}
        </div>
      </div>

      <VersionInfoModal 
        isOpen={showVersionModal} 
        onClose={() => setShowVersionModal(false)} 
      />
    </header>
  )
}
