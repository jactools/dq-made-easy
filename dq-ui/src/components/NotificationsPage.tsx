import React, { useEffect, useMemo, useState } from 'react'
import { useAuth, useNotifications, useRules, useSettings } from '../hooks/useContexts'
import { NotificationItem } from '../contexts/NotificationContext'
import { AppIcon, AppInput, type AppIconName } from './app-primitives'
import './NotificationsPage.css'

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

const getNotificationIcon = (type: string): AppIconName => {
  switch (type) {
    case 'approval-pending':
      return 'exclamation-circle'
    case 'rule-activated':
      return 'check-circle'
    case 'rule-rejected':
      return 'close'
    case 'test-completed':
      return 'info-circle'
    case 'success':
      return 'check-circle'
    case 'warning':
      return 'exclamation-circle'
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
    case 'info':
      return 'notification-info'
    default:
      return 'notification-info'
  }
}

export const NotificationsPage: React.FC = () => {
  const auth = useAuth()
  const rules = useRules()
  const settings = useSettings()
  const { notifications, markAsRead, markAllAsRead, pushNotificationsEnabled } = useNotifications()
  const [searchQuery, setSearchQuery] = useState('')
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
      setReadApprovalIds(Array.from(new Set(parsed.map((value) => String(value).trim()).filter(Boolean))))
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
      // Ignore storage write failures.
    }
  }, [approvalReadStorageKey, readApprovalIds])

  const pendingApprovalsForCurrentWorkspace = useMemo(() => {
    if (!auth.currentWorkspaceId) {
      return []
    }

    return (rules.approvals || []).filter((approval) => {
      if (approval.status !== 'pending') {
        return false
      }
      if (String(approval.workspaceId || '').trim()) {
        return String(approval.workspaceId).trim() === auth.currentWorkspaceId
      }
      const approvalRule = rules.rules.find((rule) => String(rule.id) === String(approval.ruleId))
      return approvalRule?.workspace === auth.currentWorkspaceId
    })
  }, [rules.approvals, rules.rules, auth.currentWorkspaceId])

  useEffect(() => {
    const activeApprovalIds = new Set(pendingApprovalsForCurrentWorkspace.map((approval) => `approval-${approval.id}`))
    setReadApprovalIds((prev) => prev.filter((id) => activeApprovalIds.has(id)))
  }, [pendingApprovalsForCurrentWorkspace])

  const notificationsEnabled = settings.notificationSettings?.pushNotifications ?? pushNotificationsEnabled
  const showApprovalNotifications = settings.notificationSettings?.emailOnApproval ?? true

  const getApprovalEffectiveStatus = (approval: { effectiveStatus?: string | null; requestType?: string }): string | null => {
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
      ? pendingApprovalsForCurrentWorkspace.map((approval) => {
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
            type: 'approval-pending',
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
  }, [notificationsEnabled, showApprovalNotifications, pendingApprovalsForCurrentWorkspace, notifications, readApprovalIdSet])

  const sortedNotifications = useMemo(() => {
    return [...displayNotifications].sort((a, b) => {
      const dateA = new Date(a.timestamp).getTime()
      const dateB = new Date(b.timestamp).getTime()
      return dateB - dateA
    })
  }, [displayNotifications])

  const filteredNotifications = useMemo(() => {
    if (!searchQuery.trim()) {
      return sortedNotifications
    }

    const query = searchQuery.toLowerCase()
    return sortedNotifications.filter(
      (notification) =>
        notification.title.toLowerCase().includes(query) ||
        notification.message.toLowerCase().includes(query)
    )
  }, [sortedNotifications, searchQuery])

  const unreadCount = useMemo(() => {
    return displayNotifications.filter((n) => !n.read).length
  }, [displayNotifications])

  const handleNotificationClick = (notification: NotificationItem) => {
    if (notification.id.startsWith('approval-')) {
      setReadApprovalIds((prev) => {
        if (prev.includes(notification.id)) {
          return prev
        }
        return [notification.id, ...prev]
      })
      return
    }

    if (!notification.read) {
      markAsRead(notification.id)
    }
  }

  const handleMarkAllAsRead = () => {
    markAllAsRead()

    if (showApprovalNotifications && pendingApprovalsForCurrentWorkspace.length > 0) {
      const approvalIds = pendingApprovalsForCurrentWorkspace.map((approval) => `approval-${approval.id}`)
      setReadApprovalIds((prev) => Array.from(new Set([...approvalIds, ...prev])))
    }
  }

  return (
    <section className="notifications-page">
      <div className="notifications-header">
        <div className="header-top">
          <h1>Notifications</h1>
          {unreadCount > 0 && (
            <span className="unread-badge">{unreadCount} unread</span>
          )}
        </div>
        <p className="page-subtitle">View all your notifications</p>
      </div>

      <div className="notifications-controls">
        <div className="search-box">
          <AppIcon name="search" />
          <AppInput
            label="Search notifications"
            type="text"
            placeholder="Search notifications..."
            value={searchQuery}
            onChange={(e: any) => setSearchQuery(e.target.value)}
            className="search-input"
            fieldClassName="search-input-field"
            labelClassName="sr-only"
          />
          {searchQuery && (
            <button
              className="clear-search-btn"
              onClick={() => setSearchQuery('')}
              title="Clear search"
            >
              <AppIcon name="close" />
            </button>
          )}
        </div>
      </div>

      {unreadCount > 0 && (
        <div className="notifications-actions">
          <button
            className="mark-all-read-btn"
            onClick={handleMarkAllAsRead}
          >
            Mark all as read
          </button>
        </div>
      )}

      <div className="notifications-container">
        {filteredNotifications.length === 0 ? (
          <div className="empty-notifications">
            <div className="empty-icon">
              <AppIcon name="bell" />
            </div>
            <p>{searchQuery ? 'No notifications match your search' : 'No notifications yet'}</p>
          </div>
        ) : (
          <div className="notifications-list">
            {filteredNotifications.map((notification) => (
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
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
