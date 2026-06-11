import { useCallback, useState } from 'react'
import { useSettings } from './useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'

export const MONITOR_NOTIFICATION_CATEGORIES = ['anomaly', 'drift', 'root_cause'] as const
export const MONITOR_NOTIFICATION_CHANNELS = ['email', 'in_app'] as const

export interface MonitorNotificationPreferenceRow {
  workspace_id: string
  enabled: boolean
  categories: string[]
  channels: string[]
}

export interface MonitorNotificationPreferencesResponse {
  accessible_workspace_ids: string[]
  available_categories: string[]
  available_channels: string[]
  monitor_notification_preferences: MonitorNotificationPreferenceRow[]
  summary?: {
    workspace_count: number
    workspace_preference_count: number
    category_count: number
  }
  last_synced: string
}

const buildSubscribePreferenceRow = (workspaceId: string): MonitorNotificationPreferenceRow => ({
  workspace_id: workspaceId,
  enabled: true,
  categories: [...MONITOR_NOTIFICATION_CATEGORIES],
  channels: [...MONITOR_NOTIFICATION_CHANNELS],
})

export interface UseMonitorNotificationsReturn {
  fetchPreferences: () => Promise<MonitorNotificationPreferencesResponse>
  subscribeWorkspaceNotifications: (workspaceId: string) => Promise<MonitorNotificationPreferencesResponse>
  updatePreferences: (rows: MonitorNotificationPreferenceRow[]) => Promise<MonitorNotificationPreferencesResponse>
  loading: boolean
  error: string | null
}

export const useMonitorNotifications = (): UseMonitorNotificationsReturn => {
  const settings = useSettings()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const getApiBase = useCallback(
    () => toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl),
    [settings]
  )

  const fetchPreferences = useCallback(async (): Promise<MonitorNotificationPreferencesResponse> => {
    setLoading(true)
    setError(null)
    try {
      const authToken = getAuthToken()
      if (!authToken) throw new Error('Not authenticated')
      const response = await fetch(`${getApiBase()}/governance/monitor-notification-preferences`, {
        headers: { Authorization: `Bearer ${authToken}` },
      })
      if (!response.ok) throw new Error(`Failed to fetch monitor notification preferences: ${response.statusText}`)
      return (await response.json()) as MonitorNotificationPreferencesResponse
    } catch (err: any) {
      const msg = err.message || 'Failed to fetch monitor notification preferences'
      setError(msg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [getApiBase])

  const updatePreferences = useCallback(
    async (rows: MonitorNotificationPreferenceRow[]): Promise<MonitorNotificationPreferencesResponse> => {
      setLoading(true)
      setError(null)
      try {
        const authToken = getAuthToken()
        if (!authToken) throw new Error('Not authenticated')
        const response = await fetch(`${getApiBase()}/governance/monitor-notification-preferences`, {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ monitor_notification_preferences: rows }),
        })
        if (!response.ok) throw new Error(`Failed to update monitor notification preferences: ${response.statusText}`)
        return (await response.json()) as MonitorNotificationPreferencesResponse
      } catch (err: any) {
        const msg = err.message || 'Failed to update monitor notification preferences'
        setError(msg)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [getApiBase]
  )

  const subscribeWorkspaceNotifications = useCallback(
    async (workspaceId: string): Promise<MonitorNotificationPreferencesResponse> => {
      const normalizedWorkspaceId = String(workspaceId || '').trim()
      if (!normalizedWorkspaceId) {
        throw new Error('Workspace id is required')
      }
      return updatePreferences([buildSubscribePreferenceRow(normalizedWorkspaceId)])
    },
    [updatePreferences]
  )

  return {
    fetchPreferences,
    subscribeWorkspaceNotifications,
    updatePreferences,
    loading,
    error,
  }
}
