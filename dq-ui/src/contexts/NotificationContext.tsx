import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { SettingsContext } from './SettingsContext'
import { AuthContext } from './AuthContext'
import { createSupportReferenceId } from '../utils/supportReference'

export type NotificationType =
  | 'approval-pending'
  | 'rule-activated'
  | 'rule-rejected'
  | 'test-completed'
  | 'success'
  | 'warning'
  | 'error'
  | 'info'

export interface NotificationItem {
  id: string
  type: NotificationType
  title: string
  message: string
  timestamp: string
  read: boolean
  referenceId?: string
  relatedId?: string
  actionUrl?: string
  metadata?: Record<string, unknown>
}

interface NotificationContextType {
  notifications: NotificationItem[]
  unreadCount: number
  pushNotificationsEnabled: boolean
  isSnoozed: boolean
  toasts: NotificationItem[]
  addNotification: (notification: Omit<NotificationItem, 'id' | 'timestamp' | 'read'> & { id?: string; timestamp?: string }) => string
  markAsRead: (id: string) => void
  markAllAsRead: () => void
  dismissToast: (id: string) => void
  removeNotification: (id: string) => void
  clearNotifications: () => void
}

const STORAGE_KEY_PREFIX = 'dq-notifications'
const MAX_NOTIFICATIONS = 100
const TOAST_DURATION_MS = 5000

export const NotificationContext = createContext<NotificationContextType | null>(null)

export const NotificationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const settings = useContext(SettingsContext)
  const auth = useContext(AuthContext)
  const currentWorkspaceId = auth?.currentWorkspaceId || null
  const currentUserId = auth?.user?.id || null
  const storageKey = useMemo(() => {
    if (!currentWorkspaceId || !currentUserId) return null
    return `${STORAGE_KEY_PREFIX}:${currentUserId}:${currentWorkspaceId}`
  }, [currentUserId, currentWorkspaceId])
  const pushNotificationsEnabled = settings?.notificationSettings?.pushNotifications ?? true
  const emailOnApproval = settings?.notificationSettings?.emailOnApproval ?? true
  const emailOnRejection = settings?.notificationSettings?.emailOnRejection ?? true
  const emailOnTestingFailure = settings?.notificationSettings?.emailOnTestingFailure ?? true
  const isSnoozed = useMemo(() => {
    const until = settings?.notificationSettings?.snoozedUntil
    return !!until && new Date(until) > new Date()
  }, [settings?.notificationSettings?.snoozedUntil])
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [toasts, setToasts] = useState<NotificationItem[]>([])
  const toastTimeoutsRef = useRef<Record<string, number>>({})

  useEffect(() => {
    Object.values(toastTimeoutsRef.current).forEach((timeoutId) => window.clearTimeout(timeoutId))
    toastTimeoutsRef.current = {}
    setToasts([])

    if (!storageKey) {
      setNotifications([])
      return
    }

    try {
      const raw = localStorage.getItem(storageKey)
      if (!raw) {
        setNotifications([])
        return
      }
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) {
        setNotifications([])
        return
      }

      const normalized = parsed
        .filter((item) => item && typeof item.id === 'string')
        .map((item) => ({
          id: String(item.id),
          type: String(item.type || 'info') as NotificationType,
          title: String(item.title || ''),
          message: String(item.message || ''),
          timestamp: String(item.timestamp || new Date().toISOString()),
          read: Boolean(item.read),
          referenceId: item.referenceId ? String(item.referenceId) : createSupportReferenceId(),
          relatedId: item.relatedId ? String(item.relatedId) : undefined,
          actionUrl: item.actionUrl ? String(item.actionUrl) : undefined,
          metadata: item.metadata && typeof item.metadata === 'object' ? item.metadata as Record<string, unknown> : undefined,
        }))
        .slice(0, MAX_NOTIFICATIONS)

      setNotifications(normalized)
    } catch {
      setNotifications([])
    }
  }, [storageKey])

  useEffect(() => {
    if (!storageKey) return

    try {
      localStorage.setItem(storageKey, JSON.stringify(notifications.slice(0, MAX_NOTIFICATIONS)))
    } catch {
      // Ignore storage write failures (private mode/full quota)
    }
  }, [notifications, storageKey])

  useEffect(() => {
    return () => {
      Object.values(toastTimeoutsRef.current).forEach((timeoutId) => window.clearTimeout(timeoutId))
      toastTimeoutsRef.current = {}
    }
  }, [])

  const dismissToast = useCallback((id: string) => {
    const timeoutId = toastTimeoutsRef.current[id]
    if (timeoutId) {
      window.clearTimeout(timeoutId)
      delete toastTimeoutsRef.current[id]
    }
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
  }, [])

  const shouldDeliverNotification = useCallback(
    (notification: Pick<NotificationItem, 'type' | 'metadata'>): boolean => {
      if (notification.metadata && typeof notification.metadata === 'object') {
        const deliveryTarget = (notification.metadata as Record<string, unknown>).deliveryTarget
        if (deliveryTarget === 'itsm') {
          return false
        }
      }
      switch (notification.type) {
        case 'approval-pending':
        case 'rule-activated':
          return emailOnApproval
        case 'rule-rejected':
          return emailOnRejection
        case 'test-completed':
          return emailOnTestingFailure
        default:
          return true
      }
    },
    [emailOnApproval, emailOnRejection, emailOnTestingFailure]
  )

  const addNotification: NotificationContextType['addNotification'] = useCallback((notification) => {
    if (!pushNotificationsEnabled) {
      return ''
    }

    if (!storageKey) {
      return ''
    }

    if (!shouldDeliverNotification(notification)) {
      return ''
    }

    const id = notification.id || `ntf-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const timestamp = notification.timestamp || new Date().toISOString()
    const referenceId = notification.referenceId || createSupportReferenceId()

    setNotifications((prev) => {
      const existingIndex = prev.findIndex((n) => n.id === id)
      const next: NotificationItem = {
        id,
        type: notification.type,
        title: notification.title,
        message: notification.message,
        timestamp,
        read: false,
        referenceId,
        relatedId: notification.relatedId,
        actionUrl: notification.actionUrl,
        metadata: notification.metadata,
      }

      if (existingIndex >= 0) {
        const copy = [...prev]
        copy[existingIndex] = next
        return copy
      }

      return [next, ...prev].slice(0, MAX_NOTIFICATIONS)
    })

    // When snoozed, add to the notification list but suppress toast popups.
    if (isSnoozed) return id

    setToasts((prev) => [
      {
        id,
        type: notification.type,
        title: notification.title,
        message: notification.message,
        timestamp,
        read: false,
        referenceId,
        relatedId: notification.relatedId,
        actionUrl: notification.actionUrl,
        metadata: notification.metadata,
      },
      ...prev.filter((toast) => toast.id !== id),
    ].slice(0, 3))

    if (toastTimeoutsRef.current[id]) {
      window.clearTimeout(toastTimeoutsRef.current[id])
    }
    toastTimeoutsRef.current[id] = window.setTimeout(() => {
      dismissToast(id)
    }, TOAST_DURATION_MS)

    return id
  }, [pushNotificationsEnabled, isSnoozed, shouldDeliverNotification, dismissToast, storageKey])

  const markAsRead = useCallback((id: string) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)))
  }, [])

  const markAllAsRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
  }, [])

  const removeNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id))
  }, [])

  const clearNotifications = useCallback(() => {
    Object.values(toastTimeoutsRef.current).forEach((timeoutId) => window.clearTimeout(timeoutId))
    toastTimeoutsRef.current = {}
    setToasts([])
    setNotifications([])
  }, [])

  const unreadCount = useMemo(() => notifications.filter((n) => !n.read).length, [notifications])

  const value = useMemo<NotificationContextType>(
    () => ({
      notifications,
      unreadCount,
      pushNotificationsEnabled,
      isSnoozed,
      toasts,
      addNotification,
      markAsRead,
      markAllAsRead,
      dismissToast,
      removeNotification,
      clearNotifications,
    }),
    [notifications, unreadCount, pushNotificationsEnabled, isSnoozed, toasts, addNotification, markAsRead, markAllAsRead, dismissToast, removeNotification, clearNotifications]
  )

  // Listen for session-expired events emitted by AuthContext and show a toast.
  useEffect(() => {
    const handler = (ev: Event) => {
      try {
        const appSettings = settings?.applicationSettings as any
        const notify = appSettings?.session?.notifyOnExpiry ?? true
        if (!notify) return
        addNotification({
          type: 'warning',
          title: 'Session expired',
          message: 'You were signed out due to session expiration. Please sign in again.',
        })
      } catch {
        // ignore
      }
    }

    window.addEventListener('dq-auth-session-expired', handler)
    return () => window.removeEventListener('dq-auth-session-expired', handler)
  }, [addNotification, settings?.applicationSettings])

  return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>
}

// Listen for session-expired events emitted by AuthContext and show a toast.
// The application settings control whether to show this notification; default to true.
export const _installSessionExpiredListener = (() => {
  if (typeof window === 'undefined') return
  const handler = (event: Event) => {
    // This is a no-op placeholder — NotificationProvider installs its own listener
  }
  // keep for static analysis; actual listener installed inside provider via hook
  return () => window.removeEventListener('dq-auth-session-expired', handler)
})()
