import React, { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { AuthContext } from '../contexts/AuthContext'
import { SettingsContext } from '../contexts/SettingsContext'
import {
  MONITOR_NOTIFICATION_CATEGORIES,
  MONITOR_NOTIFICATION_CHANNELS,
  MonitorNotificationPreferenceRow,
  MonitorNotificationPreferencesResponse,
  useMonitorNotifications,
} from '../hooks/useMonitorNotifications'
import './MonitorSubscriptionsPanel.css'

const CATEGORY_LABELS: Record<string, string> = {
  anomaly: 'Anomaly detection',
  drift: 'Schema & field drift',
  root_cause: 'Root-cause analysis',
}

const CHANNEL_LABELS: Record<string, string> = {
  email: 'Email',
  in_app: 'In-app',
}

interface MonitorSubscriptionsPanelProps {
  /** Called after every successful save so the parent can react (e.g. show save success). */
  onSaved?: () => void
}

export const MonitorSubscriptionsPanel: React.FC<MonitorSubscriptionsPanelProps> = ({ onSaved }) => {
  const { fetchPreferences, updatePreferences, loading, error } = useMonitorNotifications()
  const auth = useContext(AuthContext)
  const settings = useContext(SettingsContext)

  const [data, setData] = useState<MonitorNotificationPreferencesResponse | null>(null)
  const [rows, setRows] = useState<MonitorNotificationPreferenceRow[]>([])
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const currentWorkspaceRole = useMemo(() => {
    const workspaceId = auth?.currentWorkspaceId
    if (!workspaceId || !auth?.user?.workspaceRoles) return null
    return auth.user.workspaceRoles.find((role) => role.workspaceId === workspaceId)?.role ?? null
  }, [auth?.currentWorkspaceId, auth?.user?.workspaceRoles])
  const alertRoutingPolicy = settings?.workspaceSettings?.alertRoutingPolicy ?? settings?.applicationSettings?.alertRoutingPolicy
  const mandatoryCategories = useMemo(() => {
    if (!alertRoutingPolicy || !currentWorkspaceRole) return []
    return alertRoutingPolicy.mandatoryRoles.includes(currentWorkspaceRole)
      ? alertRoutingPolicy.mandatoryCategories
      : []
  }, [alertRoutingPolicy, currentWorkspaceRole])

  // Load preferences on mount
  useEffect(() => {
    fetchPreferences()
      .then((response) => {
        setData(response)
        // Populate rows: one entry per accessible workspace, defaulting to the saved prefs or disabled
        const prefMap = new Map(
          response.monitor_notification_preferences.map((r) => [r.workspace_id, r])
        )
        const initialRows: MonitorNotificationPreferenceRow[] = response.accessible_workspace_ids.map(
          (wsId) =>
            prefMap.get(wsId) ?? {
              workspace_id: wsId,
              enabled: false,
              categories: [...MONITOR_NOTIFICATION_CATEGORIES],
              channels: [...MONITOR_NOTIFICATION_CHANNELS],
            }
        )
        setRows(initialRows)
      })
      .catch(() => {
        // error state handled by hook
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setRow = useCallback(
    (wsId: string, patch: Partial<MonitorNotificationPreferenceRow>) => {
      setRows((prev) =>
        prev.map((r) => (r.workspace_id === wsId ? { ...r, ...patch } : r))
      )
    },
    []
  )

  const handleSave = async () => {
    setSaveError(null)
    try {
      const nextRows = rows.map((row) => ({
        ...row,
        enabled: row.enabled || mandatoryCategories.length > 0,
        categories: Array.from(new Set([...row.categories, ...mandatoryCategories])),
      }))
      await updatePreferences(nextRows)
      setSaved(true)
      onSaved?.()
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current)
      savedTimerRef.current = setTimeout(() => setSaved(false), 3000)
    } catch (err: any) {
      setSaveError(err.message || 'Failed to save monitor notification preferences')
    }
  }

  if (loading && !data) {
    return <p className="monitor-subs-loading">Loading monitor subscriptions…</p>
  }

  if (!data) {
    return null
  }

  const accessibleWorkspaces = data.accessible_workspace_ids

  return (
    <div className="monitor-subs-panel">
      <h3 className="monitor-subs-heading">Monitor subscriptions</h3>
      <p className="monitor-subs-subtitle">
        Choose which workspaces and event types you want to be notified about.
        You will only receive notifications for workspaces you have access to.
      </p>

      {(error || saveError) && (
        <p className="monitor-subs-error" role="alert">{saveError || error}</p>
      )}

      {accessibleWorkspaces.length === 0 ? (
        <p className="monitor-subs-empty">No accessible workspaces found.</p>
      ) : (
        <div className="monitor-subs-list">
          {rows.map((row) => (
            <div key={row.workspace_id} className="monitor-subs-row">
              <div className="monitor-subs-row-header">
                <input
                  id={`ws-enabled-${row.workspace_id}`}
                  type="checkbox"
                  checked={row.enabled || mandatoryCategories.length > 0}
                  disabled={mandatoryCategories.length > 0}
                  onChange={(e) => setRow(row.workspace_id, { enabled: e.target.checked })}
                  aria-label={`Enable notifications for workspace ${row.workspace_id}`}
                />
                <label
                  htmlFor={`ws-enabled-${row.workspace_id}`}
                  className="monitor-subs-ws-label"
                >
                  {row.workspace_id}
                </label>
              </div>

              {mandatoryCategories.length > 0 && (
                <p className="monitor-subs-mandatory-note">
                  {currentWorkspaceRole} must stay subscribed to {mandatoryCategories.join(', ')}.
                </p>
              )}

              {(row.enabled || mandatoryCategories.length > 0) && (
                <div className="monitor-subs-row-detail">
                  <div className="monitor-subs-categories">
                    <span className="monitor-subs-group-label">Categories</span>
                    {MONITOR_NOTIFICATION_CATEGORIES.map((cat) => (
                      <label key={cat} className="monitor-subs-check-label">
                        <input
                          type="checkbox"
                          checked={row.categories.includes(cat) || mandatoryCategories.includes(cat)}
                          disabled={mandatoryCategories.includes(cat)}
                          onChange={(e) => {
                            const next = e.target.checked
                              ? [...row.categories, cat]
                              : row.categories.filter((c) => c !== cat)
                            setRow(row.workspace_id, { categories: next })
                          }}
                        />
                        {CATEGORY_LABELS[cat] ?? cat}
                      </label>
                    ))}
                  </div>

                  <div className="monitor-subs-channels">
                    <span className="monitor-subs-group-label">Channels</span>
                    {MONITOR_NOTIFICATION_CHANNELS.map((ch) => (
                      <label key={ch} className="monitor-subs-check-label">
                        <input
                          type="checkbox"
                          checked={row.channels.includes(ch)}
                          onChange={(e) => {
                            const next = e.target.checked
                              ? [...row.channels, ch]
                              : row.channels.filter((c) => c !== ch)
                            setRow(row.workspace_id, { channels: next })
                          }}
                        />
                        {CHANNEL_LABELS[ch] ?? ch}
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="monitor-subs-actions">
        <button
          type="button"
          className="monitor-subs-save-btn"
          onClick={() => void handleSave()}
          disabled={loading}
        >
          {loading ? 'Saving…' : 'Save subscriptions'}
        </button>
        {saved && <span className="monitor-subs-saved-msg">Saved</span>}
      </div>
    </div>
  )
}
