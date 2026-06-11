import React, { useState, useEffect, useRef } from 'react'
import { useSettings } from '../hooks/useContexts'
import {
  UserSettings,
  NotificationSettings,
  DisplaySettings,
} from '../types/settings'
import { AppSelect, AppPageHeader, AppPageShell } from './app-primitives'
import { PrimaryButton, SecondaryButton } from './Button'
import { AppIcon, AppTabs, type AppIconName } from './app-primitives'
import { formatSupportReferenceId, createSupportReferenceId } from '../utils/supportReference'
import { MonitorSubscriptionsPanel } from './MonitorSubscriptionsPanel'
import { NotificationSnoozeControl } from './NotificationSnoozeControl'
import './Settings.css'

type Tab = 'profile' | 'notifications' | 'display' | 'preview'

type SettingsTabOption = {
  value: Tab
  label: string
  icon: AppIconName
}

interface SettingsProps {
  onNavigate?: (destination: string) => void
}

const applyThemePreview = (theme: 'light' | 'dark' | 'auto') => {
  const effectiveTheme =
    theme === 'auto'
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : theme

  localStorage.setItem('dq-theme-preference', theme)

  document.documentElement.setAttribute('data-theme', effectiveTheme)
  document.documentElement.setAttribute('data-app-theme', effectiveTheme)
  document.documentElement.classList.toggle('dark', effectiveTheme === 'dark')
}

const SETTINGS_TAB_OPTIONS: readonly SettingsTabOption[] = [
  { value: 'profile', label: 'Profile', icon: 'person' },
  { value: 'notifications', label: 'Notifications', icon: 'bell' },
  { value: 'display', label: 'Display', icon: 'eye-open' },
  { value: 'preview', label: 'Preview Features', icon: 'lightbulb' },
] as const

export const Settings: React.FC<SettingsProps> = ({ onNavigate }) => {
  const [activeTab, setActiveTab] = useState<Tab>('profile')
  const [hasChanges, setHasChanges] = useState(false)
  const [showSaveSuccess, setShowSaveSuccess] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveErrorReferenceId, setSaveErrorReferenceId] = useState<string | null>(null)
  const [show2FAModal, setShow2FAModal] = useState(false)
  const [qrSecret, setQRSecret] = useState('')
  const [newApiKey, setNewApiKey] = useState('')

  const settings = useSettings()
  const visibleTabs = SETTINGS_TAB_OPTIONS

  // Profile tab state
  const [profileData, setProfileData] = useState<UserSettings | null>(settings.userSettings || null)

  // Notification tab state
  const [notificationsData, setNotificationsData] = useState<NotificationSettings | null>(
    settings.notificationSettings || null
  )

  // Display tab state
  const [displayData, setDisplayData] = useState<DisplaySettings | null>(settings.displaySettings || null)

  const handleSave = async () => {
    try {
      setSaveError(null)
      setSaveErrorReferenceId(null)
      switch (activeTab) {
        case 'profile':
          if (profileData) {
            await settings.updateSettings({ category: 'profile', data: profileData })
          }
          break
        case 'notifications':
          if (notificationsData) {
            await settings.updateSettings({ category: 'notifications', data: notificationsData })
          }
          break
        case 'display':
        case 'preview':
          if (displayData) {
            await settings.updateSettings({ category: 'display', data: displayData })
          }
          break
      }
      setHasChanges(false)
      setShowSaveSuccess(true)
      setTimeout(() => setShowSaveSuccess(false), 3000)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error || 'Error saving settings')
      console.error('Error saving settings:', error)
      setSaveError(message)
      setSaveErrorReferenceId(createSupportReferenceId())
    }
  }

  const handleCancel = () => {
    setProfileData(settings.userSettings || null)
    setNotificationsData(settings.notificationSettings || null)
    setDisplayData(settings.displaySettings || null)
    setHasChanges(false)
    setSaveError(null)
    setSaveErrorReferenceId(null)
  }

  useEffect(() => {
    setProfileData(settings.userSettings || null)
    setNotificationsData(settings.notificationSettings || null)
    setDisplayData(settings.displaySettings || null)
    setSaveError(null)
    setSaveErrorReferenceId(null)
  }, [
    settings.userSettings,
    settings.notificationSettings,
    settings.displaySettings,
  ])

  if (settings.error && !profileData) {
    return (
      <AppPageShell className="settings-container">
        <AppPageHeader
          className="settings-header"
          title="Settings"
          description={
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
          actions={<PrimaryButton onClick={() => settings.loadSettings()}>Retry</PrimaryButton>}
        />
      </AppPageShell>
    )
  }

  if (saveError) {
    // Keep the user in context but make the save failure very explicit.
    // This is especially important for preview-feature opt-in persistence.
    // No fallbacks: show the error so the user can correct backend/auth issues.
  }

  if (!profileData || !notificationsData || !displayData) {
    return (
      <AppPageShell className="settings-container">
        <AppPageHeader className="settings-header" title="Settings" description="Loading settings..." />
      </AppPageShell>
    )
  }

  return (
    <AppPageShell className="settings-container">
      <AppPageHeader className="settings-header" title="Settings" description="Manage your preferences and configuration">
        <div className="settings-header-tabs" aria-label="Settings sections">
          <div className="settings-header-tabs-scroll">
            <AppTabs
              ariaLabel="Settings sections"
              value={activeTab}
              onChange={setActiveTab}
              className="settings-header-tabs-control"
              tabs={visibleTabs.map((tab) => ({
                value: tab.value,
                label: tab.label,
                title: `Open ${tab.label}`,
              }))}
            />
          </div>
        </div>
      </AppPageHeader>

      <div className="settings-content">
          {/* Profile Tab */}
          {activeTab === 'profile' && (
            <div className="settings-panel">
              <h2>Profile Settings</h2>

              <div className="settings-form">
                <div className="form-group">
                  <label htmlFor="firstName">First Name</label>
                  <input
                    id="firstName"
                    type="text"
                    value={profileData.firstName}
                    onChange={(e) => {
                      setProfileData({ ...profileData, firstName: e.target.value })
                      setHasChanges(true)
                    }}
                    placeholder="Enter first name"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="lastName">Last Name</label>
                  <input
                    id="lastName"
                    type="text"
                    value={profileData.lastName}
                    onChange={(e) => {
                      setProfileData({ ...profileData, lastName: e.target.value })
                      setHasChanges(true)
                    }}
                    placeholder="Enter last name"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="email">Email Address</label>
                  <input
                    id="email"
                    type="email"
                    value={profileData.email}
                    onChange={(e) => {
                      setProfileData({ ...profileData, email: e.target.value })
                      setHasChanges(true)
                    }}
                    placeholder="Enter email"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="phone">Phone Number</label>
                  <input
                    id="phone"
                    type="tel"
                    value={profileData.phone}
                    onChange={(e) => {
                      setProfileData({ ...profileData, phone: e.target.value })
                      setHasChanges(true)
                    }}
                    placeholder="Enter phone number"
                  />
                </div>

                <div className="form-group">
                  <AppSelect
                    id="language"
                    label="Language"
                    value={profileData.language}
                    onChange={(value) => {
                      setProfileData({
                        ...profileData,
                        language: value as 'en' | 'nl' | 'de' | 'fr',
                      })
                      setHasChanges(true)
                    }}
                    options={[
                      { value: 'en', label: 'English' },
                      { value: 'nl', label: 'Dutch' },
                      { value: 'de', label: 'German' },
                      { value: 'fr', label: 'French' },
                    ]}
                  />
                </div>

                <div className="form-group">
                  <AppSelect
                    id="timezone"
                    label="Timezone"
                    value={profileData.timezone}
                    onChange={(value) => {
                      setProfileData({ ...profileData, timezone: value })
                      setHasChanges(true)
                    }}
                    options={[
                      { value: 'UTC', label: 'UTC' },
                      { value: 'Europe/Amsterdam', label: 'Europe/Amsterdam' },
                      { value: 'Europe/London', label: 'Europe/London' },
                      { value: 'Europe/Paris', label: 'Europe/Paris' },
                      { value: 'America/New_York', label: 'America/New_York' },
                    ]}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Notifications Tab */}
          {activeTab === 'notifications' && (
            <div className="settings-panel">
              <h2>Notification Preferences</h2>

              <div className="settings-form">
                <div className="form-group checkbox">
                  <input
                    id="emailOnApproval"
                    type="checkbox"
                    checked={notificationsData.emailOnApproval}
                    onChange={(e) => {
                      setNotificationsData({
                        ...notificationsData,
                        emailOnApproval: e.target.checked,
                      })
                      setHasChanges(true)
                    }}
                  />
                  <label htmlFor="emailOnApproval">Email when rule is approved</label>
                </div>

                <div className="form-group checkbox">
                  <input
                    id="emailOnRejection"
                    type="checkbox"
                    checked={notificationsData.emailOnRejection}
                    onChange={(e) => {
                      setNotificationsData({
                        ...notificationsData,
                        emailOnRejection: e.target.checked,
                      })
                      setHasChanges(true)
                    }}
                  />
                  <label htmlFor="emailOnRejection">Email when rule is rejected</label>
                </div>

                <div className="form-group checkbox">
                  <input
                    id="emailOnTestingFailure"
                    type="checkbox"
                    checked={notificationsData.emailOnTestingFailure}
                    onChange={(e) => {
                      setNotificationsData({
                        ...notificationsData,
                        emailOnTestingFailure: e.target.checked,
                      })
                      setHasChanges(true)
                    }}
                  />
                  <label htmlFor="emailOnTestingFailure">Email when testing fails</label>
                </div>

                <div className="form-group">
                  <AppSelect
                    id="emailDigestFrequency"
                    label="Email Digest Frequency"
                    value={notificationsData.emailDigestFrequency}
                    onChange={(value) => {
                      setNotificationsData({
                        ...notificationsData,
                        emailDigestFrequency: value as any,
                      })
                      setHasChanges(true)
                    }}
                    options={[
                      { value: 'immediate', label: 'Immediate' },
                      { value: 'daily', label: 'Daily' },
                      { value: 'weekly', label: 'Weekly' },
                    ]}
                  />
                </div>

                <div className="form-group checkbox">
                  <input
                    id="pushNotifications"
                    type="checkbox"
                    checked={notificationsData.pushNotifications}
                    onChange={(e) => {
                      setNotificationsData({
                        ...notificationsData,
                        pushNotifications: e.target.checked,
                      })
                      setHasChanges(true)
                    }}
                  />
                  <label htmlFor="pushNotifications">Push notifications enabled</label>
                </div>

                <div className="form-group checkbox">
                  <input
                    id="teamsIntegration"
                    type="checkbox"
                    checked={notificationsData.teamsIntegration}
                    onChange={(e) => {
                      setNotificationsData({
                        ...notificationsData,
                        teamsIntegration: e.target.checked,
                      })
                      setHasChanges(true)
                    }}
                  />
                  <label htmlFor="teamsIntegration">Microsoft Teams channel notifications enabled</label>
                </div>

                {notificationsData.teamsIntegration && (
                  <div className="form-group">
                    <AppSelect
                      id="teamsChannel"
                      label="Select Teams Channel"
                      value={notificationsData.teamsChannelId || ''}
                      onChange={(value) => {
                        const selectedChannel = notificationsData.teamsChannels?.find(
                          ch => ch.id === value
                        )
                        setNotificationsData({
                          ...notificationsData,
                          teamsChannelId: value,
                          teamsChannelName: selectedChannel?.name,
                        })
                        setHasChanges(true)
                      }}
                      options={[
                        { value: '', label: '-- Select a channel --' },
                        ...(notificationsData.teamsChannels?.map(channel => ({
                          value: channel.id,
                          label: channel.displayName,
                        })) || []),
                      ]}
                    />
                  </div>
                )}
              </div>

              {/* Snooze / temporary silence */}
              <NotificationSnoozeControl
                snoozedUntil={notificationsData.snoozedUntil}
                onChange={(snoozedUntil) => {
                  setNotificationsData({ ...notificationsData, snoozedUntil })
                  setHasChanges(true)
                }}
              />

              {/* Per-workspace monitor subscriptions */}
              <MonitorSubscriptionsPanel onSaved={() => setShowSaveSuccess(true)} />
            </div>
          )}

          {/* Display Tab */}
          {activeTab === 'display' && (
            <div className="settings-panel">
              <h2>Display Preferences</h2>

              <div className="settings-form">
                <div className="form-group">
                  <AppSelect
                    id="theme"
                    label="Theme"
                    value={displayData.theme}
                    onChange={(value) => {
                      const normalizedTheme =
                        value === 'light' || value === 'dark' || value === 'auto'
                          ? value
                          : (value === 'system' ? 'auto' : 'light')

                      setDisplayData({ ...displayData, theme: normalizedTheme })
                      applyThemePreview(normalizedTheme)
                      setHasChanges(true)
                    }}
                    options={[
                      { value: 'light', label: 'Light' },
                      { value: 'dark', label: 'Dark' },
                      { value: 'auto', label: 'Auto (System)' },
                    ]}
                  />
                </div>

                <div className="form-group checkbox">
                  <input
                    id="compactMode"
                    type="checkbox"
                    checked={displayData.compactMode}
                    onChange={(e) => {
                      setDisplayData({ ...displayData, compactMode: e.target.checked })
                      setHasChanges(true)
                    }}
                  />
                  <label htmlFor="compactMode">Compact mode</label>
                </div>

                <div className="form-group checkbox">
                  <input
                    id="showTooltips"
                    type="checkbox"
                    checked={displayData.showTooltips}
                    onChange={(e) => {
                      setDisplayData({ ...displayData, showTooltips: e.target.checked })
                      setHasChanges(true)
                    }}
                  />
                  <label htmlFor="showTooltips">Show tooltips</label>
                </div>

                <div className="form-group">
                  <AppSelect
                    id="dateFormat"
                    label="Date Format"
                    value={displayData.preferredDateFormat}
                    onChange={(value) => {
                      setDisplayData({ ...displayData, preferredDateFormat: value as any })
                      setHasChanges(true)
                    }}
                    options={[
                      { value: 'DD/MM/YYYY', label: 'DD/MM/YYYY' },
                      { value: 'MM/DD/YYYY', label: 'MM/DD/YYYY' },
                      { value: 'YYYY-MM-DD', label: 'YYYY-MM-DD' },
                    ]}
                  />
                </div>

              </div>
            </div>
          )}

          {/* Preview Features Tab */}
          {activeTab === 'preview' && (
            <div className="settings-panel">
              <h2>Preview Features</h2>

              <div className="settings-form">
                <div className="form-group checkbox">
                  <input
                    id="participateInPreviews"
                    type="checkbox"
                    checked={displayData.participateInPreviews}
                    onChange={(e) => {
                      setDisplayData({ ...displayData, participateInPreviews: e.target.checked })
                      setHasChanges(true)
                    }}
                  />
                  <label htmlFor="participateInPreviews">Participate in preview features</label>
                </div>

                <div className="settings-info-box" style={{ marginTop: '12px' }}>
                  <AppIcon name="info-circle" />
                  <p>
                    Preview features are experimental and may change or be removed.
                    Enabling this option gives you early access to preview-stage functionality in its intended navigation area.
                  </p>
                </div>

                <div className="form-group">
                  <label htmlFor="catalogTermMatchThresholdPct">Catalog term match threshold (%)</label>
                  <input
                    id="catalogTermMatchThresholdPct"
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    value={displayData.catalogTermMatchThresholdPct ?? ''}
                    onChange={(e) => {
                      const rawValue = e.target.value.trim()
                      setDisplayData({
                        ...displayData,
                        catalogTermMatchThresholdPct: rawValue ? parseFloat(rawValue) || 0 : undefined,
                      })
                      setHasChanges(true)
                    }}
                    placeholder="Uses app default when blank"
                  />
                </div>

                {displayData.participateInPreviews && (
                  <div className="settings-info-box" style={{ marginTop: '16px' }}>
                    <AppIcon name="lightbulb" />
                    <p>
                      Preview-stage features will appear directly in their normal navigation area after you save your settings.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Security Tab */}
      </div>

      {/* Save/Cancel Actions */}
      {hasChanges && (
        <div className="settings-actions">
          {saveError && (
            <div className="settings-error" role="alert" style={{ marginRight: 'auto' }}>
              {saveError}
              {saveErrorReferenceId && (
                <>
                  <br />
                  {formatSupportReferenceId(saveErrorReferenceId)}
                </>
              )}
            </div>
          )}
          <SecondaryButton onClick={handleCancel}>
            Cancel
          </SecondaryButton>
          <PrimaryButton onClick={handleSave}>
            Save Changes
          </PrimaryButton>
        </div>
      )}

      {/* Success Message */}
      {showSaveSuccess && (
        <div className="settings-success-banner">
          <AppIcon name="check-circle" />
          <span>Settings saved successfully!</span>
        </div>
      )}

      {/* 2FA Modal */}
      {show2FAModal && (
        <div className="settings-modal-overlay" onClick={() => setShow2FAModal(false)}>
          <div className="settings-modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="settings-modal-header">
              <h3>Enable Two-Factor Authentication</h3>
              <button
                className="settings-modal-close"
                onClick={() => setShow2FAModal(false)}
              >
                ✕
              </button>
            </div>
            <div className="settings-modal-body">
              <p>Scan this QR code with your authenticator app:</p>
              <div className="qr-code-placeholder">
                <div className="qr-text">{qrSecret}</div>
              </div>
              <p className="qr-info">
                Enter the 6-digit code from your authenticator app to confirm setup.
              </p>
            </div>
            <div className="settings-modal-footer">
              <SecondaryButton onClick={() => setShow2FAModal(false)}>
                Close
              </SecondaryButton>
            </div>
          </div>
        </div>
      )}
    </AppPageShell>
  )
}
