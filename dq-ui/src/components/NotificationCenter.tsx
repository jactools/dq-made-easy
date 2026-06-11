import React, { useEffect, useMemo, useState } from 'react'
import { RuleApproval } from '../types/rules'
import { NotificationItem } from '../contexts/NotificationContext'
import { useAuth, useNotifications, useSettings } from '../hooks/useContexts'
import { AppButton, AppIcon, type AppIconName } from './app-primitives'
import './NotificationCenter.css'

interface NotificationCenterProps {
  pendingApprovals?: RuleApproval[]
  onNotificationClick?: (notification: NotificationItem) => void
  onNavigate?: (destination: string) => void
}

export const NotificationCenter: React.FC<NotificationCenterProps> = ({
  pendingApprovals = [],
  onNotificationClick,
  onNavigate,
}) => {
  const auth = useAuth()
  const { notifications, toasts, pushNotificationsEnabled, markAsRead, markAllAsRead, dismissToast } = useNotifications()
  const settings = useSettings()
  const [isExpanded, setIsExpanded] = useState(false)
  const [readApprovalIds, setReadApprovalIds] = useState<string[]>([])

  const readApprovalIdSet = useMemo(() => new Set(readApprovalIds), [readApprovalIds])

  const approvalReadStorageKey = useMemo(() => {
    const userId = String(auth.user?.id || '').trim()
    const workspaceId = String(auth.currentWorkspaceId || '').trim()
    if (!userId || !workspaceId) {
      return null
    }
    return `dq-notifications:approval-read:${userId}:${workspaceId}`
  }, [auth.user?.id, auth.currentWorkspaceId])

  useEffect(() => {
    if (!approvalReadStorageKey) {
      setReadApprovalIds([])
      return
    }

    try {
      const raw = localStorage.getItem(approvalReadStorageKey)
      if (!raw) {
        setReadApprovalIds([])
        return
      }
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) {
        setReadApprovalIds([])
        return
      }
      const normalized = Array.from(
        new Set(
          parsed
            .map((value) => String(value).trim())
            .filter(Boolean)
        )
      )
      setReadApprovalIds(normalized)
    } catch {
      setReadApprovalIds([])
    }
  }, [approvalReadStorageKey])

  useEffect(() => {
    if (!approvalReadStorageKey) {
      return
    }

    try {
      localStorage.setItem(approvalReadStorageKey, JSON.stringify(readApprovalIds))
    } catch {
      // Ignore storage write failures (private mode/full quota)
    }
  }, [approvalReadStorageKey, readApprovalIds])

  useEffect(() => {
    const activeApprovalIds = new Set(pendingApprovals.map((approval) => `approval-${approval.id}`))
    setReadApprovalIds((prev) => prev.filter((id) => activeApprovalIds.has(id)))
  }, [pendingApprovals])

  const notificationsEnabled = settings.notificationSettings?.pushNotifications ?? pushNotificationsEnabled
  const showApprovalNotifications = settings.notificationSettings?.emailOnApproval ?? true

  const getApprovalEffectiveStatus = (approval: RuleApproval): string | null => {
    if (approval.effectiveStatus) {
      return approval.effectiveStatus
    }

    if (approval.requestType === 'deactivation') {
      return 'deactivated'
    }

    if (approval.requestType === 'activation') {
      return 'activated'
    }

    return null
  }
  
  const displayNotifications = useMemo<NotificationItem[]>(() => {
    if (!notificationsEnabled) {
      return []
    }

    const approvalNotifications: NotificationItem[] = showApprovalNotifications
      ? pendingApprovals.map((approval) => {
          const requesterName = approval.requesterId.trim()
          const actionType = approval.requestType === 'deactivation'
            ? 'deactivation'
            : approval.requestType === 'gx_suite_repair'
              ? 'suite repair'
              : 'approval'
          const effectiveStatus = getApprovalEffectiveStatus(approval)
          const approvalNotificationId = `approval-${approval.id}`
          
          return {
            id: approvalNotificationId,
            type: 'approval-pending' as const,
            title: approval.requestType === 'deactivation'
              ? 'Deactivation Awaiting Approval'
              : approval.requestType === 'gx_suite_repair'
                ? 'Suite Repair Awaiting Approval'
                : 'Rule Awaiting Approval',
            message: `${requesterName} requested ${actionType} review`,
            timestamp: approval.requestedAt || new Date().toISOString(),
            read: readApprovalIdSet.has(approvalNotificationId),
            relatedId: approval.id,
            actionUrl: `/approvals/${approval.id}`,
            metadata: effectiveStatus ? { effectiveStatus } : undefined,
          }
        })
      : []
    return [...approvalNotifications, ...notifications]
  }, [notificationsEnabled, showApprovalNotifications, pendingApprovals, notifications, readApprovalIdSet])

  const filteredNotifications = displayNotifications

  const unreadCount = displayNotifications.filter((n) => !n.read).length

  const handleNotificationClick = (notification: NotificationItem) => {
    if (notification.id.startsWith('approval-')) {
      setReadApprovalIds((prev) => {
        if (prev.includes(notification.id)) {
          return prev
        }
        return [notification.id, ...prev]
      })
    } else {
      markAsRead(notification.id)
    }
    setIsExpanded(false)
    onNotificationClick?.(notification)
  }

  const handleMarkAllAsRead = () => {
    markAllAsRead()

    if (showApprovalNotifications && pendingApprovals.length > 0) {
      const approvalIds = pendingApprovals.map((approval) => `approval-${approval.id}`)
      setReadApprovalIds((prev) => Array.from(new Set([...approvalIds, ...prev])))
    }
    setIsExpanded(false)
  }

  const getNotificationIcon = (type: string): AppIconName => {
    switch (type) {
      case 'approval-pending':
        return 'warning'
      case 'rule-activated':
        return 'check-circle'
      case 'rule-rejected':
        return 'close'
      case 'test-completed':
        return 'info-circle'
      case 'success':
        return 'check-circle'
      case 'warning':
        return 'warning'
      case 'error':
        return 'close'
      default:
        return 'info-circle'
    }
  }

  const getNotificationClass = (type: string) => {
    switch (type) {
      case 'approval-pending':
      case 'warning':
        return 'notification-warning'
      case 'rule-activated':
      case 'success':
        return 'notification-success'
      case 'rule-rejected':
      case 'error':
        return 'notification-error'
      case 'test-completed':
        return 'notification-info'
      default:
        return 'notification-info'
    }
  }

  return (
    <div className="notification-center">
      <button
        type="button"
        className="notification-trigger"
        onClick={() => setIsExpanded(!isExpanded)}
        title={unreadCount > 0 ? `${unreadCount} new notifications` : 'Notifications'}
        aria-label={unreadCount > 0 ? `${unreadCount} unread notifications` : 'Notifications'}
      >
        <AppIcon name="bell" />
        {unreadCount > 0 && <span className="notification-badge">{unreadCount}</span>}
      </button>

      {isExpanded && (
        <div className="notification-panel">
          <div className="notification-header">
            <h3>Notifications</h3>
            <button
              className="panel-close"
              onClick={() => setIsExpanded(false)}
              aria-label="Close"
            >
              ✕
            </button>
          </div>

          {notificationsEnabled && (
            <div className="notification-list">
              {filteredNotifications.length === 0 ? (
                <div className="empty-notifications">
                  <p>No notifications</p>
                </div>
              ) : (
                filteredNotifications.map((notification) => (
                <div
                  key={notification.id}
                  className={`notification-item ${getNotificationClass(
                    notification.type
                  )} ${!notification.read ? 'unread' : ''}`}
                  onClick={() => handleNotificationClick(notification)}
                >
                  <div className="notification-icon">
                    <AppIcon name={getNotificationIcon(notification.type)} />
                  </div>

                  <div className="notification-content">
                    <h4 className="notification-title">{notification.title}</h4>
                    {notification.type === 'approval-pending' && typeof notification.metadata?.effectiveStatus === 'string' && (
                      <span className={`notification-status-badge notification-status-badge-${notification.metadata.effectiveStatus}`}>
                        Effective: {notification.metadata.effectiveStatus}
                      </span>
                    )}
                    <p className="notification-message">{notification.message}</p>
                    {notification.referenceId && (
                      <p className="notification-reference-id">Reference ID: {notification.referenceId}</p>
                    )}
                    <span className="notification-time">
                      {getRelativeTime(new Date(notification.timestamp))}
                    </span>
                  </div>

                  {!notification.read && <div className="notification-dot" />}
                </div>
              ))
              )}
            </div>
          )}
          {notificationsEnabled && displayNotifications.length > 0 && (
            <div className="notification-footer">
              <div className="footer-buttons">
                <AppButton
                  variant="tertiary"
                  className="mark-all-read"
                  onClick={handleMarkAllAsRead}
                >
                  Mark all as read
                </AppButton>
                {onNavigate && (
                  <AppButton
                    variant="tertiary"
                    className="view-all-notifications"
                    onClick={() => {
                      setIsExpanded(false)
                      onNavigate('notifications')
                    }}
                  >
                    View All
                  </AppButton>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {notificationsEnabled && toasts.length > 0 && (
        <div className="notification-toasts" aria-live="polite" aria-atomic="false">
          {toasts.map((toast) => (
            <div
              key={`toast-${toast.id}`}
              className={`notification-toast ${getNotificationClass(toast.type)}`}
            >
              <div className="notification-toast-icon">
                <AppIcon name={getNotificationIcon(toast.type)} />
              </div>
              <div className="notification-toast-content">
                <p className="notification-toast-title">{toast.title}</p>
                <p className="notification-toast-message">{toast.message}</p>
                {toast.referenceId && (
                  <p className="notification-toast-reference">Reference ID: {toast.referenceId}</p>
                )}
              </div>
              <AppButton
                variant="tertiary"
                className="notification-toast-close"
                onClick={() => dismissToast(toast.id)}
                aria-label="Dismiss notification"
              >
                ×
              </AppButton>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Helper function to get relative time
function getRelativeTime(date: Date): string {
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}
