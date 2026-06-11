import React, { useContext, useEffect, useState } from 'react'
import { useAuth } from '../hooks/useKeycloak'
import { SettingsContext } from '../contexts/SettingsContext'
import { AppBanner, AppButton, AppInput, AppModal } from './app-primitives'
import { getWorkspaceDisplayName } from './WorkspaceSelector'
import { canUseBrowserSsoAuth } from '../auth/browserAuthClient'
import { formatSupportReferenceId } from '../utils/supportReference'
import './AuthModal.css'

interface LoginModalProps {
  isOpen: boolean
  onClose: () => void
}
export const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onClose }) => {
  const auth = useAuth()
  const settings = useContext(SettingsContext)
  const ssoEnabled = settings?.applicationSettings?.ssoEnabled !== false
  const allowLocalAuth = settings?.applicationSettings?.allowLocalAuth === true
  const browserSsoSupported = canUseBrowserSsoAuth(settings?.applicationSettings?.ssoIssuerUrl)
  const canUseSso = ssoEnabled && browserSsoSupported
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [emailError, setEmailError] = useState('')
  const [loginMode, setLoginMode] = useState<'select' | 'admin'>('select')
  const [ssoLoading, setSsoLoading] = useState(false)

  useEffect(() => {
    if (isOpen) {
      setEmail('')
      setPassword('')
      setEmailError('')
      setLoginMode('select')
      setSsoLoading(false)
    }
  }, [isOpen])

  useEffect(() => {
    if (!allowLocalAuth && loginMode === 'admin') {
      setLoginMode('select')
    }
  }, [allowLocalAuth, loginMode])

  useEffect(() => {
    if (!isOpen || !auth.user) return

    const workspaces = auth.user.workspaceRoles || []
    if (workspaces.length <= 1) {
      if (workspaces.length === 1) {
        const onlyWorkspaceId = workspaces[0].workspaceId
        if (auth.currentWorkspaceId !== onlyWorkspaceId) {
          auth.switchWorkspace(onlyWorkspaceId)
        }
      }
      onClose()
    }
  }, [auth.currentWorkspaceId, auth.user, isOpen, onClose])

  const validateEmail = (value: string): boolean => {
    if (!value) {
      setEmailError('Email is required')
      return false
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(value)) {
      setEmailError('Please enter a valid email address')
      return false
    }
    setEmailError('')
    return true
  }

  const hasLoginInput = email.length > 0 || password.length > 0
  const isLoginDisabled = auth.isLoading || !hasLoginInput

  const handleEmailChange = (e: any) => {
    const value = e.target.value
    setEmail(value)
    if (emailError) {
      setEmailError('')
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validateEmail(email)) {
      return
    }
    try {
      await auth.login(email, password)
      setEmail('')
      setPassword('')
    } catch (error) {
      console.error('Login failed:', error)
    }
  }

  const handleWorkspaceSelect = (workspaceId: string) => {
    auth.switchWorkspace(workspaceId)
    onClose()
  }

  const handleSsoLogin = async () => {
    if (!canUseSso) return
    setSsoLoading(true)
    try {
      await auth.loginWithSso()
    } catch (error) {
      console.error('SSO login failed:', error)
      setSsoLoading(false)
    }
  }

  const handleDemoLogin = async (email: string) => {
    try {
      await auth.login(email, 'demo')
      setEmail('')
      setPassword('')
    } catch (error) {
      console.error('Demo login failed:', error)
    }
  }

  const demoAccounts = [
    { email: 'admin@example.com', role: 'Admin' },
    { email: 'analyst@example.com', role: 'Analyst' },
    { email: 'data-steward@example.com', role: 'Data Steward' },
    { email: 'viewer@example.com', role: 'Viewer' },
  ]

  const userWorkspaces = auth.user?.workspaceRoles.map(wr => ({
    id: String(wr.workspaceId ?? '').trim(),
    name: getWorkspaceDisplayName(String(wr.workspaceId ?? '').trim()),
    role: wr.role,
  })) || []

  const currentWorkspace = userWorkspaces.find(w => w.id === auth.currentWorkspaceId)
  const showWorkspaceSelector = Boolean(isOpen && auth.user && userWorkspaces.length > 1)

  return (
    <AppModal
      isOpen={isOpen}
      onClose={onClose}
      title={showWorkspaceSelector ? 'Select Workspace' : (loginMode === 'select' ? 'Choose Login Method' : 'Admin Login')}
      size="sm"
      dialogClassName="auth-login-modal"
      bodyClassName="auth-modal-content"
    >
          {!showWorkspaceSelector ? (
            <>
              {loginMode === 'select' ? (
                <div className="login-method-selector">
                  <AppButton
                    onClick={handleSsoLogin}
                    className="login-method-btn"
                    aria-disabled={ssoLoading || !canUseSso}
                    {...(ssoLoading || !canUseSso ? { disabled: true } : {})}
                  >
                    {ssoLoading ? 'Opening Keycloak...' : 'SSO Login'}
                  </AppButton>
                  {allowLocalAuth && (
                    <AppButton
                      variant="secondary"
                      onClick={() => setLoginMode('admin')}
                      className="login-method-btn"
                    >
                      Admin Login
                    </AppButton>
                  )}
                  {ssoEnabled && !browserSsoSupported && (
                    <p className="login-method-hint">Browser SSO login is unavailable here; SSO will continue through the redirect flow.</p>
                  )}
                  {!ssoEnabled && (
                    <p className="login-method-hint">SSO is currently disabled in application settings.</p>
                  )}
                  {!canUseSso && !allowLocalAuth && (
                    <p className="login-method-hint">No login method is currently available.</p>
                  )}
                </div>
              ) : (
                <>
                  <form onSubmit={handleSubmit} className="login-form">
                    <div className="form-field">
                      <AppInput
                        id="email-input"
                        label="Email"
                        labelClassName="form-label"
                        type="text"
                        value={email}
                        onChange={handleEmailChange}
                        placeholder="Enter your email"
                      />
                      {emailError && <span className="field-error">{emailError}</span>}
                    </div>

                    <div className="form-field">
                      <AppInput
                        id="password-input"
                        label="Password"
                        labelClassName="form-label"
                        type="password"
                        value={password}
                        onChange={(e: any) => setPassword(e.target.value)}
                        placeholder="Enter your password"
                      />
                    </div>

                    {auth.error && (
                      <AppBanner variant="error">
                        {auth.error}
                        {auth.errorReferenceId && (
                          <>
                            <br />
                            {formatSupportReferenceId(auth.errorReferenceId)}
                          </>
                        )}
                      </AppBanner>
                    )}

                    <AppButton
                      type="submit"
                      className="login-button"
                      aria-disabled={isLoginDisabled}
                      {...(isLoginDisabled ? { disabled: true } : {})}
                    >
                      {auth.isLoading ? 'Logging in...' : 'Login'}
                    </AppButton>

                    <AppButton
                      variant="secondary"
                      type="button"
                      className="login-button"
                      onClick={() => setLoginMode('select')}
                    >
                      Back
                    </AppButton>
                  </form>

                  <div className="demo-accounts">
                    <p className="demo-label">Demo Accounts</p>
                    <div className="demo-list">
                      {demoAccounts.map(account => (
                        <AppButton
                          variant="tertiary"
                          key={account.email}
                          onClick={() => handleDemoLogin(account.email)}
                          className="demo-account-btn"
                        >
                          <span className="email">{account.email}</span>
                          <span className="role">{account.role}</span>
                        </AppButton>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </>
          ) : (
            <div className="workspace-selector">
              {currentWorkspace && (
                <div className="current-workspace">
                  <p className="workspace-label">Currently Active:</p>
                  <div className="workspace-badge">
                    <span className="workspace-name">{currentWorkspace.name}</span>
                    <span className="workspace-role">{currentWorkspace.role}</span>
                  </div>
                </div>
              )}

              {userWorkspaces.length > 1 && (
                <>
                  <p className="workspace-label" style={{ marginTop: currentWorkspace ? 24 : 0 }}>Switch Workspace:</p>
                  <div className="workspace-list">
                    {userWorkspaces.map(workspace => {
                      const isCurrentWorkspace = workspace.id === auth.currentWorkspaceId
                      return (
                        <AppButton
                          key={workspace.id}
                          variant={isCurrentWorkspace ? 'primary' : 'secondary'}
                          onClick={() => handleWorkspaceSelect(workspace.id)}
                          className="workspace-btn"
                        >
                          <span className="workspace-name">{workspace.name}</span>
                          <span className="workspace-role">{workspace.role}</span>
                        </AppButton>
                      )
                    })}
                  </div>
                </>
              )}

              <AppButton
                variant="secondary"
                onClick={() => {
                  auth.logout()
                }}
                className="logout-button"
              >
                Logout
              </AppButton>

              {userWorkspaces.length === 1 && (
                <AppButton
                  onClick={() => handleWorkspaceSelect(userWorkspaces[0].id)}
                  className="continue-button"
                >
                  Continue
                </AppButton>
              )}
            </div>
          )}
    </AppModal>
  )
}

