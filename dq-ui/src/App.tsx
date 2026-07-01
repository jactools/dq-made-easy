import React, { useState, useEffect, useCallback, useRef } from 'react'
import { AuthProvider, getAuthToken } from './contexts/AuthContext'
import { RuleProvider } from './contexts/RuleContext'
import { SettingsProvider } from './contexts/SettingsContext'
import { DataProductProvider } from './contexts/DataProductContext'
import { NotificationProvider } from './contexts/NotificationContext'
import { AsyncRequestTrackerProvider } from './contexts/AsyncRequestTrackerContext'
import { VersionCatalogProvider } from './contexts/VersionCatalogContext'
import { Header } from './components/Header'
import { Sidebar } from './components/Sidebar'
import { Toolbar } from './components/Toolbar'
import { Button } from './components/Button'
import { Welcome } from './components/Welcome'
import { Dashboard } from './components/Dashboard'
import { LoginModal } from './components/AuthModal'
import { WorkspaceSelector } from './components/WorkspaceSelector'
import { Rules } from './components/Rules'
import { Approvals } from './components/Approvals'
import { AuditTrail } from './components/AuditTrail'
import { Settings } from './components/Settings'
import { TemplatesTab } from './components/Templates'
import { Reports } from './components/Reports'
import { ServiceLevelsPage } from './components/ServiceLevelsPage'
import { ValidationPlans } from './components/ValidationPlans'
import { DiscussionHub } from './components/DiscussionHub'
import { Suggestions } from './components/Suggestions'
import { Documentation } from './components/Documentation'
import { DataBrowser } from './components/DataBrowser'
import { DataAssetsBuilder } from './components/DataAssetsBuilder'
import { DefinitionMappingsPage } from './components/DefinitionMappingsPage'
import { DeliveryInventory } from './components/DeliveryInventory'
import { SystemMetrics } from './components/SystemMetrics'
import { ApplicationSettings } from './components/ApplicationSettings'
import { RoleManagement } from './components/RoleManagement'
import { UserManagement } from './components/UserManagement'
import { snakeToCamel } from './utils/caseConverters'
import { IconGallery } from './components/IconGallery'
import { ValidationRunPlansAdmin } from './components/GxRunPlansAdmin'
import { GxSuitesAdmin } from './components/GxSuitesAdmin'
import { AccessRequestsDashboard } from './components/AccessRequestsDashboard'
import { CatalogDriftReview } from './components/CatalogDriftReview'
import { PolicyDocumentsPage } from './components/PolicyDocumentsPage'
import { NotificationsPage } from './components/NotificationsPage'
import { SupportRequestFooter } from './components/SupportRequestFooter'
import { ConnectorWorkbench } from './components/ConnectorWorkbench'
import { SessionTimeoutWarning } from './components/SessionTimeoutWarning'
import SessionExpired from './components/SessionExpired'
import { RuntimeModeIndicator } from './components/RuntimeModeIndicator'
import { StyleThemeProvider } from './contexts/StyleThemeContext'
import { useAuth } from './hooks/useKeycloak'
import { useSettings } from './hooks/useContexts'
import { toApiGroupV1Base } from './config/api'
import { recordUiPageView, startUiSpan, withUiSpan } from './telemetry'
import type { UserWorkspaceRole } from './types/keycloak'
import type { RuleTemplate } from './types/templates'
import type { DefinitionMappingTarget } from './types/dataProducts'
import {
  RuleValidation,
  RuleLifecycleManagement,
  RuleResultAggregation,
  ExceptionRecordHandling,
  RuleExecutionMonitoring,
} from './components/features'
import { DEFAULT_STYLE_PACKAGE, type StyleRegistryStyle } from './contexts/styleThemeCatalog'

const RULE_VALIDATION_NAV_SELECTION_KEY = 'dq-rule-validation-navigation-selection'

const NAV_SECTION_DEFAULTS: Record<string, string> = {
  rules: 'rules-my',
  'rule-quality': 'rule-quality-validation',
  approvals: 'approvals-my',
  'data-browser': 'data-browser-my',
  reports: 'reports-metrics',
  templates: 'templates-my',
  administration: 'administration-connectors',
}

type ThemePreference = 'light' | 'dark' | 'auto'
type EffectiveTheme = 'light' | 'dark'

const NAV_SCOPE_REQUIREMENTS: Array<{ match: RegExp; scopes: string[] }> = [
  { match: /^(rules-all-workspaces|approvals-all-workspaces|data-browser-all-workspaces|templates-all-workspaces)$/, scopes: ['dq:workspace:read', 'dq:*'] },
  { match: /^(rules|rules-)/, scopes: ['dq:rules:read', 'dq:rules:write', 'dq:rules:*', 'dq:*'] },
  { match: /^(rule-quality|rule-quality-)/, scopes: ['dq:rules:read', 'dq:rules:write', 'dq:rules:*', 'dq:*'] },
  { match: /^approvals-policies$/, scopes: ['dq:rules:approve', 'dq:workspace:read', 'dq:*'] },
  { match: /^approvals-exceptions$/, scopes: ['dq:exceptions:read', 'dq:exceptions:detail', 'dq:*'] },
  { match: /^(approvals|approvals-)/, scopes: ['dq:rules:approve', 'dq:workspace:read', 'dq:*'] },
  { match: /^notifications$/, scopes: ['dq:notifications:read', 'dq:notifications:*', 'dq:*'] },
  { match: /^(data-browser|data-browser-|definition-mappings)/, scopes: ['dq:data_catalog:read', 'dq:data_catalog:*', 'dq:*'] },
  { match: /^data-assets$/, scopes: ['dq:data_catalog:read', 'dq:data_catalog:write', 'dq:data_catalog:*', 'dq:*'] },
  { match: /^(delivery-inventory|delivery-inventory-)/, scopes: ['dq:data_catalog:read', 'dq:data_catalog:*', 'dq:*'] },
  { match: /^(reports|reports-)/, scopes: ['dq:reports:read', 'dq:reports:*', 'dq:*'] },
  { match: /^discussions$/, scopes: ['dq:rules:approve', 'dq:reports:read', 'dq:data_catalog:read', 'dq:workspace:read', 'dq:*'] },
  { match: /^(audit|audit-)/, scopes: ['dq:audit:read', 'dq:audit:*', 'dq:*'] },
  { match: /^(templates|templates-)/, scopes: ['dq:templates:read', 'dq:templates:write', 'dq:templates:*', 'dq:*'] },
  { match: /^(administration|administration-)/, scopes: ['dq:admin:read', 'dq:workspace:read', 'dq:*'] },
]

const normalizeThemePreference = (value: unknown): ThemePreference => {
  if (value === 'light' || value === 'dark' || value === 'auto') {
    return value
  }
  if (value === 'system') {
    return 'auto'
  }
  return 'auto'
}

const getStoredThemePreference = (): ThemePreference => {
  const savedPreferenceRaw = localStorage.getItem('dq-theme-preference')
  if (savedPreferenceRaw !== null) {
    return normalizeThemePreference(savedPreferenceRaw)
  }

  return 'auto'
}

const resolveEffectiveTheme = (theme: ThemePreference): EffectiveTheme => {
  if (theme === 'auto') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }

  return theme
}

const applyThemeAttributes = (theme: ThemePreference) => {
  const effectiveTheme = resolveEffectiveTheme(theme)
  const root = document.documentElement
  root.setAttribute('data-theme', effectiveTheme)
  root.setAttribute('data-app-theme', effectiveTheme)
  root.classList.toggle('dark', effectiveTheme === 'dark')
  return effectiveTheme
}

// Apply initial theme from localStorage on app load
const applyInitialTheme = () => {
  applyThemeAttributes(getStoredThemePreference())
}

function AppContent() {
  const SIDEBAR_MIN_WIDTH = 260
  const SIDEBAR_MAX_WIDTH = 420
  const [activeNav, setActiveNav] = useState('dashboard')
  const previousNavRef = useRef('dashboard')
  const [loginModalOpen, setLoginModalOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('dq-sidebar-collapsed') === 'true'
  })
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = Number(localStorage.getItem('dq-sidebar-width'))
    return Number.isFinite(saved)
      ? Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, saved))
      : 300
  })
  const [isResizingSidebar, setIsResizingSidebar] = useState(false)
  const [selectedTemplateForRules, setSelectedTemplateForRules] = useState<any>(null)
  const [maintenanceState, setMaintenanceState] = useState<{ enabled: boolean; message: string }>({
    enabled: false,
    message: '',
  })
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken())
  const [uiRegistryStyles, setUiRegistryStyles] = useState<readonly StyleRegistryStyle[] | null>(null)
  const auth = useAuth()
  const settings = useSettings()
  const allowLocalAuth = settings.applicationSettings?.allowLocalAuth === true
  const stylePackage = settings.applicationSettings?.stylePackage || DEFAULT_STYLE_PACKAGE
  const effectiveTheme = resolveEffectiveTheme(
    normalizeThemePreference(settings.displaySettings?.theme || getStoredThemePreference())
  )
  const supportRequestFooter = auth.isAuthenticated && settings.applicationSettings?.apiBaseUrl ? (
    <SupportRequestFooter
      apiBaseUrl={settings.applicationSettings.apiBaseUrl}
      pageId={activeNav}
      workspaceId={auth.currentWorkspaceId}
    />
  ) : null
  const hasAdminWorkspaceAccess = Boolean(
    auth.isAuthenticated && auth.currentWorkspaceId && auth.user?.workspaceRoles.some((workspaceRole) => {
      return workspaceRole.workspaceId === auth.currentWorkspaceId && (workspaceRole.role === 'admin' || workspaceRole.role === 'cross-admin')
    }),
  )
  const publicDocsPathname = typeof window !== 'undefined' ? window.location.pathname : ''
  const publicDocsRoute = /^\/docs(?:\/|$)/.test(publicDocsPathname) && !/^\/docs\/(?:assets|img)\//.test(publicDocsPathname)

  useEffect(() => {
    if (!publicDocsRoute || typeof window === 'undefined') {
      return
    }

    if (publicDocsPathname.endsWith('.html')) {
      return
    }

    if (!publicDocsPathname.startsWith('/docs')) {
      return
    }

    const normalizedDocsPath = publicDocsPathname === '/docs' || publicDocsPathname === '/docs/'
      ? '/docs/index.html'
      : `${publicDocsPathname.replace(/\/?$/, '/') }index.html`

    if (window.location.pathname !== normalizedDocsPath) {
      window.location.replace(`${normalizedDocsPath}${window.location.search}${window.location.hash}`)
    }
  }, [publicDocsPathname, publicDocsRoute])

  useEffect(() => {
    if (!auth.isAuthenticated || !auth.user) {
      return
    }

    const requiresWorkspaceSelection = auth.user.workspaceRoles.length > 1 && !auth.currentWorkspaceId
    if (!requiresWorkspaceSelection) {
      return
    }

    setLoginModalOpen(true)
  }, [auth.currentWorkspaceId, auth.isAuthenticated, auth.user, loginModalOpen])

  useEffect(() => {
    const apiBaseUrl = settings.applicationSettings?.apiBaseUrl
    if (!apiBaseUrl || !authToken) {
      setUiRegistryStyles(null)
      return
    }

    let cancelled = false

    const loadUiRegistry = async () => {
      try {
        const apiBase = toApiGroupV1Base('system', apiBaseUrl)
        const response = await fetch(`${apiBase}/ui-registry`, {
          headers: {
            ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
          },
        })

        if (!response.ok || cancelled) {
          return
        }

        const view = (await response.json()) as { styles?: StyleRegistryStyle[] }
        if (!cancelled) {
          setUiRegistryStyles(Array.isArray(view.styles) ? view.styles : [])
        }
      } catch {
        if (!cancelled) {
          setUiRegistryStyles(null)
        }
      }
    }

    void loadUiRegistry()

    return () => {
      cancelled = true
    }
  }, [authToken, settings.applicationSettings?.apiBaseUrl])

  const isAdminUser = auth.getCurrentUserRole() === 'admin'

  const hasNavAccess = useCallback((navId: string): boolean => {
    if (navId === 'administration-connectors') {
      return hasAdminWorkspaceAccess
    }

    const requirement = NAV_SCOPE_REQUIREMENTS.find((entry) => entry.match.test(navId))

    if (navId === 'approvals-policies') {
      return Boolean(auth.canEditGovernance?.())
    }

    if (navId === 'approvals-governance') {
      return Boolean(auth.canEditGovernance?.() || auth.canApproveGovernance?.())
    }

    if (navId === 'approvals' || navId === 'approvals-my' || navId === 'approvals-team' || navId === 'approvals-all' || navId === 'approvals-all-workspaces') {
      return Boolean(auth.canApproveGovernance?.() || auth.hasAnyScope(['dq:rules:approve', 'dq:workspace:read', 'dq:*']))
    }

    if (requirement && !auth.hasAnyScope(requirement.scopes)) {
      return false
    }

    return true
  }, [auth, hasAdminWorkspaceAccess])

  const handleNavigate = useCallback((nextNav: string) => {
    const normalizedNextNav = NAV_SECTION_DEFAULTS[nextNav] || nextNav
    if (auth.isAuthenticated && !hasNavAccess(normalizedNextNav)) {
      return
    }

    const fromNav = previousNavRef.current

    if (fromNav === normalizedNextNav) {
      return
    }

    void withUiSpan(
      'ui.navigation.transition',
      {
        'dq.nav.from': fromNav,
        'dq.nav.to': normalizedNextNav,
      },
      async () => {
        setActiveNav(normalizedNextNav)
        await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()))
      }
    ).catch(() => undefined)

    previousNavRef.current = normalizedNextNav
  }, [auth.isAuthenticated, hasNavAccess])

  const handleOpenRuleValidation = useCallback((ruleIds: string[]) => {
    const normalizedRuleIds = Array.from(new Set(ruleIds.map((ruleId) => String(ruleId || '').trim()).filter(Boolean)))
    if (normalizedRuleIds.length === 0) {
      handleNavigate('rule-quality-validation')
      return
    }

    try {
      window.sessionStorage.setItem(
        RULE_VALIDATION_NAV_SELECTION_KEY,
        JSON.stringify({
          rule_ids: normalizedRuleIds,
          source: 'rules',
          created_at: new Date().toISOString(),
        })
      )
    } catch {
      // Ignore storage failures and still navigate.
    }

    handleNavigate('rule-quality-validation')
  }, [handleNavigate])

  const handleOpenDefinitionMappings = useCallback((target: DefinitionMappingTarget) => {
    try {
      sessionStorage.setItem('dq-definition-mapping-target', JSON.stringify(target))
    } catch {
      // ignore storage write failures and still navigate
    }
    handleNavigate('definition-mappings')
  }, [handleNavigate])

  // Apply theme setting to document
  useEffect(() => {
    if (!settings.displaySettings) return

    const theme = normalizeThemePreference(settings.displaySettings.theme)
    const syncTheme = () => {
      applyThemeAttributes(theme)
    }

    // Persist theme to localStorage
    localStorage.setItem('dq-theme-preference', theme)

    syncTheme()

    if (theme !== 'auto') {
      return
    }

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    mediaQuery.addEventListener('change', syncTheme)
    return () => mediaQuery.removeEventListener('change', syncTheme)
  }, [settings.displaySettings])

  useEffect(() => {
    localStorage.setItem('dq-sidebar-collapsed', String(sidebarCollapsed))
  }, [sidebarCollapsed])

  useEffect(() => {
    localStorage.setItem('dq-sidebar-width', String(sidebarWidth))
  }, [sidebarWidth])

  useEffect(() => {
    if (!isResizingSidebar) return

    const handleMouseMove = (event: MouseEvent) => {
      const nextWidth = Math.min(
        SIDEBAR_MAX_WIDTH,
        Math.max(SIDEBAR_MIN_WIDTH, event.clientX)
      )
      setSidebarWidth(nextWidth)
    }

    const handleMouseUp = () => {
      setIsResizingSidebar(false)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)

    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizingSidebar])

  useEffect(() => {
    const sessionExpiredHandler = () => {
      setActiveNav('session-expired')
      try {
        history.replaceState({}, '', '/session-expired')
      } catch {
        // ignore
      }
    }

    window.addEventListener('dq-auth-session-expired', sessionExpiredHandler)

    // If the current URL explicitly points to the session-expired page, show it.
    try {
      if (window.location && window.location.pathname === '/session-expired') {
        setActiveNav('session-expired')
      }

      // If a session-expired flag was set (post-logout redirect), show the page immediately and normalize the URL.
      if (sessionStorage.getItem('dq-session-expired') === '1') {
        setActiveNav('session-expired')
        sessionStorage.removeItem('dq-session-expired')
        try {
          history.replaceState({}, '', '/session-expired')
        } catch {
          // ignore
        }
      }
    } catch {
      // ignore
    }

    const syncTokenFromStorage = () => {
      setAuthToken(getAuthToken())
    }

    syncTokenFromStorage()
    if (typeof window !== 'undefined') {
      window.addEventListener('storage', syncTokenFromStorage)
      window.addEventListener('dq-auth-token-changed', syncTokenFromStorage)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('storage', syncTokenFromStorage)
        window.removeEventListener('dq-auth-token-changed', syncTokenFromStorage)
        window.removeEventListener('dq-auth-session-expired', sessionExpiredHandler)
      }
    }
  }, [])

  useEffect(() => {
    const handleOpenRuleEvent = (event: Event) => {
      const customEvent = event as CustomEvent<{ ruleId?: string }>
      const ruleId = String(customEvent.detail?.ruleId || '').trim()
      if (!ruleId) return
      localStorage.setItem('dq-open-rule-id', ruleId)
      handleNavigate('rules')
    }

    const handleOpenNewRuleEvent = () => {
      sessionStorage.setItem('dq-open-new-rule', '1')
      handleNavigate('rules')
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('dq-open-rule', handleOpenRuleEvent as EventListener)
      window.addEventListener('dq-open-new-rule', handleOpenNewRuleEvent as EventListener)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('dq-open-rule', handleOpenRuleEvent as EventListener)
        window.removeEventListener('dq-open-new-rule', handleOpenNewRuleEvent as EventListener)
      }
    }
  }, [handleNavigate])

  useEffect(() => {
    recordUiPageView(activeNav)
  }, [activeNav])

  useEffect(() => {
    if (!auth.isAuthenticated || activeNav !== 'dashboard') {
      return
    }

    const span = startUiSpan('ui.dashboard.load', {
      'dq.nav': 'dashboard',
    })

    let ended = false
    const rafId = window.requestAnimationFrame(() => {
      span.end()
      ended = true
    })

    return () => {
      window.cancelAnimationFrame(rafId)
      if (!ended) {
        span.end()
      }
    }
  }, [activeNav, auth.isAuthenticated])

  useEffect(() => {
    if (!auth.isAuthenticated) {
      return
    }

    if (hasNavAccess(activeNav)) {
      return
    }

    setActiveNav('dashboard')
    previousNavRef.current = 'dashboard'
  }, [activeNav, auth.isAuthenticated, hasNavAccess])

  useEffect(() => {
    if (!auth.isAuthenticated) {
      return
    }

    if (activeNav !== 'session-expired') {
      return
    }

    setActiveNav('dashboard')
    previousNavRef.current = 'dashboard'
    try {
      history.replaceState({}, '', '/')
    } catch {
      // ignore
    }
  }, [activeNav, auth.isAuthenticated])

  useEffect(() => {
    let cancelled = false

    const loadMaintenanceState = async () => {
      if (!authToken) {
        if (!cancelled) {
          setMaintenanceState({ enabled: false, message: '' })
        }
        return
      }

      try {
        const apiBase = toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)
        const response = await fetch(`${apiBase}/app-config`, {
          headers: {
            Authorization: `Bearer ${authToken}`,
          },
        })
        if (!response.ok) {
          if (response.status === 401) {
            // Do not invalidate the whole session from a background poll.
            // Other authenticated views should remain stable until explicit logout.
            return
          }
          return
        }

        const config = snakeToCamel<Record<string, unknown>>(await response.json())
        if (cancelled) return

        setMaintenanceState({
          enabled: Boolean(config?.maintenanceMode),
          message: String(config?.maintenanceMessage || '').trim(),
        })
      } catch {
        if (cancelled) return
      }
    }

    if (!authToken) {
      return () => {
        cancelled = true
      }
    }

    loadMaintenanceState()
    const interval = window.setInterval(loadMaintenanceState, 30000)

    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [settings.applicationSettings?.apiBaseUrl, authToken])

  if (maintenanceState.enabled && !isAdminUser) {
    return (
      <StyleThemeProvider stylePackage={stylePackage} registryStyles={uiRegistryStyles}>
        <div className="app maintenance-mode" data-theme={effectiveTheme} data-app-theme={effectiveTheme}>
          <Header
            onLoginClick={() => setLoginModalOpen(true)}
            onHelpClick={() => handleNavigate('documentation')}
            onSettingsClick={() => handleNavigate('settings')}
            onNavigate={handleNavigate}
            maintenanceActive={maintenanceState.enabled}
          />
          <LoginModal isOpen={loginModalOpen} onClose={() => setLoginModalOpen(false)} />
          <div className="maintenance-layout">
            <div className="maintenance-card">
              <h2>Scheduled Maintenance In Progress</h2>
              <p>
                {maintenanceState.message ||
                  'The platform is temporarily unavailable while updates are being applied. Please try again shortly.'}
              </p>
              <div className="maintenance-actions">
                <Button onClick={() => window.location.reload()}>
                  Refresh
                </Button>
                {!auth.isAuthenticated && allowLocalAuth && (
                  <Button variant="secondary" onClick={() => setLoginModalOpen(true)}>
                    Admin Login
                  </Button>
                )}
              </div>
            </div>
          </div>
          <RuntimeModeIndicator />
        </div>
      </StyleThemeProvider>
    )
  }

  if (publicDocsRoute) {
    return (
      <StyleThemeProvider stylePackage={stylePackage} registryStyles={uiRegistryStyles}>
        <div className="app public-documentation" data-theme={effectiveTheme} data-app-theme={effectiveTheme}>
          <main className="app-main app-main-full">
            <div className="app-content">
              <div className="documentation-container">
                <div className="documentation-header">
                  <h1>Public documentation</h1>
                  <p className="documentation-subtitle">Redirecting to the static docs portal…</p>
                </div>
              </div>
            </div>
          </main>
          <RuntimeModeIndicator />
        </div>
      </StyleThemeProvider>
    )
  }

  return (
    <StyleThemeProvider stylePackage={stylePackage} registryStyles={uiRegistryStyles}>
      <div className="app" data-theme={effectiveTheme} data-app-theme={effectiveTheme}>
      <Header
        onLoginClick={() => setLoginModalOpen(true)}
        onHelpClick={() => handleNavigate('documentation')}
        onSettingsClick={() => handleNavigate('settings')}
        onNavigate={handleNavigate}
        maintenanceActive={maintenanceState.enabled}
      />
      <LoginModal isOpen={loginModalOpen} onClose={() => setLoginModalOpen(false)} />
      <SessionTimeoutWarning />

      {activeNav === 'session-expired' ? (
        <div className="app-container">
          <main className="app-main app-main-full">
            <div className="app-content">
              <SessionExpired onOpenLogin={() => setLoginModalOpen(true)} />
            </div>
          </main>
        </div>
      ) : auth.isAuthenticated ? (
        <div className="app-container">
          <Sidebar
            activeItem={activeNav}
            onItemClick={handleNavigate}
            collapsed={sidebarCollapsed}
            width={!sidebarCollapsed ? sidebarWidth : undefined}
            onToggleCollapsed={() => setSidebarCollapsed(prev => !prev)}
          />

          {!sidebarCollapsed && (
            <div
              className={`sidebar-resize-handle${isResizingSidebar ? ' active' : ''}`}
              onMouseDown={() => setIsResizingSidebar(true)}
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize sidebar"
            />
          )}

          <main className="app-main">
            <Toolbar />
            <div className="app-content">
              {activeNav === 'dashboard' && (
                <>
                  <Welcome userName={auth.user?.name || 'Guest'} />
                  <Dashboard onNavigate={handleNavigate} />
                </>
              )}
              {(activeNav === 'rules' || activeNav.startsWith('rules-')) && (
                hasNavAccess(activeNav) && (
                <Rules 
                  key={activeNav}
                  viewScope={
                    activeNav === 'rules-team'
                      ? 'team'
                      : activeNav === 'rules-all-workspaces'
                      ? 'global'
                      : activeNav === 'rules-all'
                      ? 'all'
                      : 'my'
                  }
                  preSelectedTemplate={selectedTemplateForRules}
                  onTemplateUsed={() => setSelectedTemplateForRules(null)}
                  onOpenRuleValidation={handleOpenRuleValidation}
                  onOpenDataAssets={() => handleNavigate('data-assets')}
                />
                )
              )}
              {(activeNav === 'rule-quality' || activeNav.startsWith('rule-quality-')) && hasNavAccess(activeNav) && (
                <>
                  {(activeNav === 'rule-quality' || activeNav === 'rule-quality-validation') && <RuleValidation />}
                  {activeNav === 'rule-quality-drift' && <CatalogDriftReview />}
                  {activeNav === 'rule-quality-suggestions' && <Suggestions />}
                </>
              )}
              {(activeNav === 'approvals' || activeNav.startsWith('approvals-')) && hasNavAccess(activeNav) && (
                <>
                  {(activeNav === 'approvals' || activeNav === 'approvals-my' || activeNav === 'approvals-team' || activeNav === 'approvals-all' || activeNav === 'approvals-all-workspaces') && (
                    <Approvals
                      key={activeNav}
                      viewScope={
                        activeNav === 'approvals-team'
                          ? 'team'
                          : activeNav === 'approvals-all-workspaces'
                          ? 'global'
                          : activeNav === 'approvals-all'
                          ? 'all'
                          : 'my'
                      }
                    />
                  )}
                  {activeNav === 'approvals-governance' && <AccessRequestsDashboard onNavigate={handleNavigate} />}
                  { activeNav === 'approvals-policies' && <PolicyDocumentsPage />}
                  {activeNav === 'approvals-lifecycle' && <RuleLifecycleManagement />}
                  {activeNav === 'approvals-exceptions' && <ExceptionRecordHandling onNavigate={handleNavigate} />}
                </>
              )}
              {activeNav === 'access-requests' && hasNavAccess(activeNav) && (
                <AccessRequestsDashboard mode="access-requests" onNavigate={handleNavigate} />
              )}
              {activeNav === 'notifications' && hasNavAccess(activeNav) && <NotificationsPage />}
              {(activeNav === 'data-browser' || activeNav.startsWith('data-browser-')) && hasNavAccess(activeNav) && (
                <DataBrowser
                  key={activeNav}
                  viewScope={
                    activeNav === 'data-browser-team'
                      ? 'team'
                      : activeNav === 'data-browser-all-workspaces'
                      ? 'global'
                      : activeNav === 'data-browser-all'
                      ? 'all'
                      : 'my'
                  }
                  onOpenDefinitionMappings={handleOpenDefinitionMappings}
                />
              )}
              {activeNav === 'data-assets' && hasNavAccess(activeNav) && <DataAssetsBuilder onNavigate={handleNavigate} />}
              {activeNav === 'definition-mappings' && hasNavAccess(activeNav) && <DefinitionMappingsPage />}
              {activeNav === 'delivery-inventory' && hasNavAccess(activeNav) && (
                <DeliveryInventory />
              )}
              {(activeNav === 'reports' || activeNav.startsWith('reports-')) && (
                hasNavAccess(activeNav) && (
                <>
                  {(activeNav === 'reports' || activeNav === 'reports-metrics' || activeNav === 'reports-test-results' || activeNav === 'reports-incidents' || activeNav === 'reports-reconciliation') && (
                    <Reports
                      initialTab={activeNav === 'reports-test-results' ? 'test-results' : activeNav === 'reports-incidents' ? 'incidents' : activeNav === 'reports-reconciliation' ? 'reconciliation' : 'metrics'}
                      onNavigate={handleNavigate}
                    />
                  )}
                  {activeNav === 'reports-service-levels' && <ServiceLevelsPage />}
                  {activeNav === 'reports-rule-aggregation' && <RuleResultAggregation />}
                  {activeNav === 'reports-rule-monitoring' && <RuleExecutionMonitoring onNavigate={handleNavigate} />}
                  {activeNav === 'reports-validation-plans' && <ValidationPlans />}
                </>
                )
              )}
              {activeNav === 'discussions' && hasNavAccess(activeNav) && <DiscussionHub />}
              {(activeNav === 'templates' || activeNav.startsWith('templates-')) && hasNavAccess(activeNav) && (
                <TemplatesTab 
                  key={activeNav}
                  viewScope={
                    activeNav === 'templates-team'
                      ? 'team'
                      : activeNav === 'templates-all-workspaces'
                        ? 'global'
                        : activeNav === 'templates-all'
                          ? 'all'
                          : 'my'
                  }
                  onUseTemplate={(template: RuleTemplate) => {
                    setSelectedTemplateForRules(template)
                    handleNavigate('rules')
                  }} 
                />
              )}
              {(activeNav === 'audit' || activeNav.startsWith('audit-')) && (
                hasNavAccess(activeNav) && (
                <>
                  <AuditTrail
                    initialTab={
                      activeNav === 'audit-rule-compiler-versions'
                        ? 'versions'
                        : activeNav === 'audit-data-definition'
                          ? 'data-definition'
                          : activeNav === 'audit-validation'
                            ? 'validation'
                            : activeNav === 'audit-approvals'
                              ? 'approvals'
                              : activeNav === 'audit-changes'
                                ? 'rules'
                                : 'overview'
                    }
                  />
                </>
                )
              )}
              {(activeNav === 'administration' || activeNav.startsWith('administration-')) && (
                hasNavAccess(activeNav) && (
                <>
                  {activeNav === 'administration-connectors' && <ConnectorWorkbench />}
                  {activeNav === 'administration-system-metrics' && <SystemMetrics />}
                  {activeNav === 'administration-application' && <ApplicationSettings />}
                  {activeNav === 'administration-users' && <UserManagement />}
                  {activeNav === 'administration-roles' && <RoleManagement />}
                  {activeNav === 'administration-gx-run-plans' && <ValidationRunPlansAdmin />}
                  {activeNav === 'administration-gx-suites' && <GxSuitesAdmin />}
                  {activeNav === 'administration-icon-gallery' && <IconGallery />}
                </>
                )
              )}
              {activeNav === 'documentation' && <Documentation onNavigate={handleNavigate} />}
              {activeNav === 'settings' && <Settings onNavigate={handleNavigate} />}
            </div>
            {supportRequestFooter}
          </main>
        </div>
      ) : (
        <div className="app-container">
          <main className="app-main app-main-full">
            <div className="app-content">
              <div style={{ padding: '24px', textAlign: 'center' }}>
                <p style={{ marginBottom: '16px' }}>
                  Please log in to access the full application
                </p>
                <Button onClick={() => setLoginModalOpen(true)}>
                  Open Login
                </Button>
              </div>
            </div>
          </main>
        </div>
      )}
        <RuntimeModeIndicator />
      </div>
    </StyleThemeProvider>
  )
}

export default function App() {
  // Apply theme immediately on app load
  useEffect(() => {
    applyInitialTheme()
  }, [])

  return (
    <SettingsProvider>
      <AuthProvider>
        <RuleProvider>
          <NotificationProvider>
            <AsyncRequestTrackerProvider>
              <VersionCatalogProvider>
                <DataProductProvider>
                  <AppContent />
                </DataProductProvider>
              </VersionCatalogProvider>
            </AsyncRequestTrackerProvider>
          </NotificationProvider>
        </RuleProvider>
      </AuthProvider>
    </SettingsProvider>
  )
}
