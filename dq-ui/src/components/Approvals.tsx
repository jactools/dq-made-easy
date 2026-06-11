import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { useRules, useAuth, useSettings, useNotifications } from '../hooks/useContexts'
import { RuleApproval, Rule, ApprovalComment, ApprovalHistoryEvent } from '../types/rules'
import { Button } from './Button'
import { AppPageHeader, AppPageShell, AppSelect } from './app-primitives'
import { AppIcon, AppInput, AppTextarea, type AppIconName } from './app-primitives'
import { useRuleStatusGovernance, type GovernanceStatusModel } from './rules/useRuleStatusGovernance'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { snakeToCamel } from '../utils/caseConverters'
import {
  consumeDashboardNavigationSelection,
  getApprovalsDestinationForScope,
  isDashboardApprovalRequestFilter,
  isDashboardWorkspaceScope,
} from '../utils/dashboardNavigation'
import { DEFAULT_WORKSPACE_SCOPE_OPTIONS, WorkspaceScopeSegmentedControl, type WorkspaceScopeOption, type WorkspaceScope } from './WorkspaceScopeSegmentedControl'
import { DiscussionPanel, normalizeDiscussionEntries } from './discussion/DiscussionPanel'
import './Approvals.css'

const sameId = (a: unknown, b: unknown): boolean => String(a) === String(b)
const getApprovalLatestTimestamp = (approval: RuleApproval): number => {
  return new Date(approval.reviewedAt || approval.requestedAt).getTime()
}
const buildAuthHeaders = (): Record<string, string> => {
  const token = getAuthToken()
  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  return headers
}

type ApprovalRequestFilter = 'all' | 'activation' | 'deactivation' | 'gx_suite_repair'
type AccessRequestStatus = 'pending' | 'approved' | 'rejected' | 'revoked' | 'timed_out'

type AccessRequestRoleId = 'exception-fact-reader' | 'exception-fact-investigator'

type ExceptionFactAccessRequest = {
  id: string
  requesterId: string
  workspaceId: string
  roleId: AccessRequestRoleId
  status: AccessRequestStatus
  requestedDurationMinutes: number
  comments?: string | null
  requestedAt: string
  reviewedBy?: string | null
  reviewedAt?: string | null
  expiresAt?: string | null
}

type GovernanceInboxRuleView = {
  id: string
  name: string
  status?: string | null
  lifecycleStatus?: string | null
  workspace?: string | null
  dataSteward?: string | null
  domainOwner?: string | null
  technicalOwner?: string | null
  pendingDeactivationRequested?: boolean
}

type GovernanceInboxPageView<T> = {
  data: T[]
  pagination: {
    total: number
    page: number
    limit: number
    totalPages: number
    hasNext: boolean
    hasPrevious: boolean
  }
}

type GovernanceInboxesResponse = {
  approvalInbox: GovernanceInboxPageView<RuleApproval>
  reassignmentInbox: GovernanceInboxPageView<GovernanceInboxRuleView>
  deprecationReviewInbox: GovernanceInboxPageView<GovernanceInboxRuleView>
}

interface ApprovalsProps {
  viewScope?: 'my' | 'team' | 'all' | 'global'
}

type ApprovalsPageResponse = {
  data?: unknown[]
}

const normalizeApproval = (payload: unknown): RuleApproval => {
  const approval = snakeToCamel<RuleApproval>(payload)
  const normalizedRequestType = approval.requestType === 'deactivation' || approval.requestType === 'gx_suite_repair'
    ? approval.requestType
    : 'activation'
  const normalizedStatus = approval.status === 'approved' || approval.status === 'rejected'
    ? approval.status
    : 'pending'

  return {
    ...approval,
    ruleId: String(approval.ruleId || ''),
    requesterId: String(approval.requesterId || ''),
    requestedAt: String(approval.requestedAt || ''),
    status: normalizedStatus,
    workspaceId: String(approval.workspaceId || ''),
    requestType: normalizedRequestType,
    commentThread: Array.isArray(approval.commentThread) ? approval.commentThread : [],
  }
}

export const Approvals: React.FC<ApprovalsProps> = ({ viewScope = 'my' }) => {
  const [initialDashboardPreset] = useState(() => consumeDashboardNavigationSelection(getApprovalsDestinationForScope(viewScope)))
  const { rules, approveRule, rejectRule, getRulesByWorkspace, isLoading } = useRules()
  const auth = useAuth()
  const settings = useSettings()
  const { addNotification } = useNotifications()
  const rulebuilderApiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  const canViewPendingApprovals = Boolean(auth.canApproveRule?.() || auth.canApproveGovernance?.())
  const canViewAllApprovals = auth.canReadAcrossWorkspaces()
  const compactMode = settings.displaySettings?.compactMode ?? false
  const itemsPerPageSetting = settings.displaySettings?.itemsPerPage ?? 10
  const activeWorkspaceRoles = useMemo(() => {
    const currentWorkspaceId = String(auth.currentWorkspaceId || '').trim()
    if (!auth.user || !currentWorkspaceId) {
      return [] as Array<{ workspaceId: string; role: string }>
    }

    return (auth.user.workspaceRoles || []).filter((workspaceRole) => String(workspaceRole.workspaceId || '').trim() === currentWorkspaceId)
  }, [auth.currentWorkspaceId, auth.user])
  const canReviewAccessRequests = activeWorkspaceRoles.some((workspaceRole) => workspaceRole.role === 'admin') || Boolean(auth.canManageUsers?.() || auth.canApproveRule?.() || auth.canApproveGovernance?.())
  const [expandedApprovalId, setExpandedApprovalId] = useState<string | null>(null)
  const [approvalComments, setApprovalComments] = useState<Record<string, string>>({})
  const [pendingPage, setPendingPage] = useState(1)
  const [processedPage, setProcessedPage] = useState(1)
  const [selectedApprovals, setSelectedApprovals] = useState<Set<string>>(new Set())
  const [bulkActionType, setBulkActionType] = useState<'approve' | 'reject' | null>(null)
  const [bulkComments, setBulkComments] = useState('')
  const [newCommentText, setNewCommentText] = useState<Record<string, string>>({})
  const [commentType, setCommentType] = useState<Record<string, 'note' | 'concern' | 'question' | 'general'>>({})
  const [commentThreads, setCommentThreads] = useState<Record<string, ApprovalComment[]>>({})
  const [commentSubmittingId, setCommentSubmittingId] = useState<string | null>(null)
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken())
  const [requestFilter, setRequestFilter] = useState<ApprovalRequestFilter>(() => {
    const presetFilter = initialDashboardPreset?.request_filter
    return isDashboardApprovalRequestFilter(presetFilter) ? presetFilter : 'all'
  })
  const [searchQuery, setSearchQuery] = useState('')
  const [activeView, setActiveView] = useState<'queue' | 'governance'>('queue')
  const [selectedViewScope, setSelectedViewScope] = useState<WorkspaceScope>(() => {
    const presetScope = initialDashboardPreset?.view_scope
    return isDashboardWorkspaceScope(presetScope) ? presetScope : viewScope
  })
  const [loadedApprovals, setLoadedApprovals] = useState<RuleApproval[]>([])
  const [approvalsError, setApprovalsError] = useState<string | null>(null)
  const [loadingApprovals, setLoadingApprovals] = useState(false)
  const [governanceInboxes, setGovernanceInboxes] = useState<GovernanceInboxesResponse | null>(null)
  const [governanceInboxesError, setGovernanceInboxesError] = useState<string | null>(null)
  const [loadingGovernanceInboxes, setLoadingGovernanceInboxes] = useState(false)
  const [accessRequests, setAccessRequests] = useState<ExceptionFactAccessRequest[]>([])
  const [accessRequestsError, setAccessRequestsError] = useState<string | null>(null)
  const [accessRequestComments, setAccessRequestComments] = useState<Record<string, string>>({})
  const [accessRequestSubmittingId, setAccessRequestSubmittingId] = useState<string | null>(null)
  const canViewPendingApprovalsInCurrentScope = canViewPendingApprovals || (selectedViewScope === 'global' && canViewAllApprovals)
  const canViewAccessRequests = canReviewAccessRequests
  const approvalsRequestIdRef = useRef(0)
  const governanceInboxesRequestIdRef = useRef(0)

  useEffect(() => {
    setSelectedViewScope(viewScope)
  }, [viewScope])

  useEffect(() => {
    if (!auth.isAuthenticated || settings.adminUsers.length > 0) {
      return
    }

    if (typeof settings.loadAdminUsers !== 'function') {
      return
    }

    if (settings.adminUsers.length === 0) {
      void settings.loadAdminUsers().catch(() => undefined)
    }
  }, [auth.isAuthenticated, settings.adminUsers.length, settings.loadAdminUsers])

  useEffect(() => {
    if (!canViewAccessRequests || !auth.currentWorkspaceId) {
      setAccessRequests([])
      setAccessRequestsError(null)
      return
    }

    let cancelled = false

    const loadAccessRequests = async () => {
      try {
        setAccessRequestsError(null)
        const apiBase = toApiGroupV1Base('admin', settings.applicationSettings?.apiBaseUrl)
        const token = getAuthToken()
        const workspaceQuery = selectedViewScope === 'global' && canViewAllApprovals
          ? ''
          : `?workspaceId=${encodeURIComponent(String(auth.currentWorkspaceId || ''))}`
        const response = await fetch(`${apiBase}/exception-fact-access-requests${workspaceQuery}`, {
          headers: buildAuthHeaders(),
        })

        if (response.status === 404) {
          if (!cancelled) {
            setAccessRequests([])
          }
          return
        }

        if (!response.ok) {
          throw new Error(`Unable to load exception-record access requests (${response.status}).`)
        }

        const payload = snakeToCamel<ExceptionFactAccessRequest[]>(await response.json())
        if (cancelled) {
          return
        }

        setAccessRequests(Array.isArray(payload) ? payload : [])
      } catch (error) {
        if (!cancelled) {
          setAccessRequests([])
          setAccessRequestsError(error instanceof Error ? error.message : 'Unable to load exception-record access requests.')
        }
      }
    }

    void loadAccessRequests()

    return () => {
      cancelled = true
    }
  }, [auth.currentWorkspaceId, canReviewAccessRequests, canViewAccessRequests, canViewAllApprovals, selectedViewScope, settings.applicationSettings?.apiBaseUrl])

  const adminUsersById = useMemo(() => {
    return new Map(
      settings.adminUsers
        .map((user) => [String(user.id || '').trim().toLowerCase(), user] as const)
        .filter(([userId]) => Boolean(userId))
    )
  }, [settings.adminUsers])

  const { statusModel: ruleStatusModel } = useRuleStatusGovernance({
    authToken,
    apiBaseUrl: settings.applicationSettings?.apiBaseUrl,
    entity: 'rule',
  })

  const { allowedTransitionsByStatus: approvalAllowedTransitionsByStatus, statusModel: approvalStatusModel, isLoaded: approvalGovernanceLoaded } = useRuleStatusGovernance({
    authToken,
    apiBaseUrl: settings.applicationSettings?.apiBaseUrl,
    entity: 'approval',
  })

  const { statusModel: runPlanStatusModel } = useRuleStatusGovernance({
    authToken,
    apiBaseUrl: settings.applicationSettings?.apiBaseUrl,
    entity: 'run_plan',
  })

  useEffect(() => {
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
      }
    }
  }, [])

  const workspaceRules = useMemo(() => {
    if (!auth.currentWorkspaceId) return []
    return getRulesByWorkspace(auth.currentWorkspaceId)
  }, [getRulesByWorkspace, auth.currentWorkspaceId])

  const currentUserId = useMemo(() => {
    return String(auth.user?.id || auth.userId || '').trim()
  }, [auth.user?.id, auth.userId])

  const userTokens = useMemo(() => {
    return new Set(
      [auth.user?.id, auth.userId, auth.user?.email, auth.user?.name]
        .map((value) => String(value || '').trim().toLowerCase())
        .filter(Boolean)
    )
  }, [auth.user?.id, auth.userId, auth.user?.email, auth.user?.name])

  const loadApprovals = useCallback(async () => {
    const requestId = approvalsRequestIdRef.current + 1
    approvalsRequestIdRef.current = requestId

    if (!auth.isAuthenticated) {
      setLoadedApprovals([])
      setApprovalsError(null)
      setLoadingApprovals(false)
      return
    }

    if (selectedViewScope !== 'global' && !auth.currentWorkspaceId) {
      setLoadedApprovals([])
      setApprovalsError(null)
      setLoadingApprovals(false)
      return
    }

    if ((selectedViewScope === 'my' || selectedViewScope === 'team') && !currentUserId) {
      setLoadedApprovals([])
      setApprovalsError('Current user id is required to load this approval view.')
      setLoadingApprovals(false)
      return
    }

    const params = new URLSearchParams({ page: '1', limit: '100' })
    if (!(selectedViewScope === 'global' && canViewAllApprovals)) {
      params.set('workspace', String(auth.currentWorkspaceId || ''))
    }
    if (requestFilter !== 'all') {
      params.set('request_type', requestFilter)
    }
    if (selectedViewScope === 'my') {
      params.set('requester_id', currentUserId)
    }
    if (selectedViewScope === 'team') {
      params.set('exclude_requester_id', currentUserId)
    }
    if (searchQuery.trim()) {
      params.set('query', searchQuery.trim())
    }

    setLoadingApprovals(true)
    setApprovalsError(null)

    try {
      const response = await fetch(`${rulebuilderApiBase}/approvals?${params.toString()}`, {
        headers: buildAuthHeaders(),
      })
      if (!response.ok) {
        const detail = await response.text()
        throw new Error(detail || `Failed to load approvals (${response.status})`)
      }

      const payload = await response.json() as ApprovalsPageResponse
      const rows = Array.isArray(payload?.data) ? payload.data : []
      if (approvalsRequestIdRef.current !== requestId) {
        return
      }

      setLoadedApprovals(rows.map(normalizeApproval))
    } catch (error) {
      if (approvalsRequestIdRef.current !== requestId) {
        return
      }

      console.error('Failed to load approvals:', error)
      setLoadedApprovals([])
      setApprovalsError(error instanceof Error ? error.message : 'Failed to load approvals.')
    } finally {
      if (approvalsRequestIdRef.current === requestId) {
        setLoadingApprovals(false)
      }
    }
  }, [
    auth.currentWorkspaceId,
    auth.isAuthenticated,
    canViewAllApprovals,
    currentUserId,
    requestFilter,
    rulebuilderApiBase,
    searchQuery,
    selectedViewScope,
  ])

  const loadGovernanceInboxes = useCallback(async () => {
    const requestId = governanceInboxesRequestIdRef.current + 1
    governanceInboxesRequestIdRef.current = requestId

    if (!auth.isAuthenticated) {
      setGovernanceInboxes(null)
      setGovernanceInboxesError(null)
      setLoadingGovernanceInboxes(false)
      return
    }

    if (selectedViewScope !== 'global' && !auth.currentWorkspaceId) {
      setGovernanceInboxes(null)
      setGovernanceInboxesError(null)
      setLoadingGovernanceInboxes(false)
      return
    }

    setLoadingGovernanceInboxes(true)
    setGovernanceInboxesError(null)

    try {
      const userLimit = itemsPerPageSetting || 10
      const adminLimit = settings.workspaceSettings?.maxListItems
      const governanceInboxLimit = adminLimit && adminLimit > 0 ? Math.min(userLimit, adminLimit) : userLimit
      const params = new URLSearchParams({
        page: '1',
        limit: String(governanceInboxLimit),
      })

      if (!(selectedViewScope === 'global' && canViewAllApprovals)) {
        params.set('workspace_id', String(auth.currentWorkspaceId || ''))
      }

      const response = await fetch(`${rulebuilderApiBase}/governance/inboxes?${params.toString()}`, {
        headers: buildAuthHeaders(),
      })

      if (!response.ok) {
        const detail = await response.text()
        throw new Error(detail || `Failed to load governance inboxes (${response.status})`)
      }

      const payload = snakeToCamel<GovernanceInboxesResponse>(await response.json())
      if (governanceInboxesRequestIdRef.current !== requestId) {
        return
      }

      setGovernanceInboxes(payload)
    } catch (error) {
      if (governanceInboxesRequestIdRef.current !== requestId) {
        return
      }

      console.error('Failed to load governance inboxes:', error)
      setGovernanceInboxes(null)
      setGovernanceInboxesError(error instanceof Error ? error.message : 'Failed to load governance inboxes.')
    } finally {
      if (governanceInboxesRequestIdRef.current === requestId) {
        setLoadingGovernanceInboxes(false)
      }
    }
  }, [
    auth.currentWorkspaceId,
    auth.isAuthenticated,
    canViewAllApprovals,
    itemsPerPageSetting,
    rulebuilderApiBase,
    selectedViewScope,
    settings.workspaceSettings?.maxListItems,
  ])

  useEffect(() => {
    void loadApprovals()
  }, [loadApprovals])

  useEffect(() => {
    if (activeView !== 'governance') {
      return
    }

    void loadGovernanceInboxes()
  }, [activeView, loadGovernanceInboxes])

  const isSelfRequestedApproval = (approval: RuleApproval): boolean => {
    const requester = String(approval.requesterId || '').trim().toLowerCase()
    return Boolean(requester && userTokens.has(requester))
  }

  const getApprovalSubjectLabel = (approval: RuleApproval): string => {
    if (approval.gxRunPlanId) {
      const versionSuffix = approval.gxRunPlanVersionId ? ` v${approval.gxRunPlanVersionId}` : ''
      return `DQ run plan ${approval.gxRunPlanId}${versionSuffix}`
    }

    const rule = getRuleForApproval(approval)
    return rule?.name || approval.ruleId || 'Unknown rule'
  }

  const filteredApprovals = useMemo(() => {
    return loadedApprovals.filter((approval) => {
      if (!canViewPendingApprovalsInCurrentScope && approval.status === 'pending') {
        return false
      }

      return true
    })
  }, [loadedApprovals, canViewPendingApprovalsInCurrentScope])

  const pendingApprovals = useMemo(() => {
    return filteredApprovals
      .filter(a => a.status === 'pending')
      .sort((a, b) => getApprovalLatestTimestamp(b) - getApprovalLatestTimestamp(a))
  }, [filteredApprovals])

  const processedApprovals = useMemo(() => {
    return filteredApprovals
      .filter(a => a.status !== 'pending')
      .sort((a, b) => getApprovalLatestTimestamp(b) - getApprovalLatestTimestamp(a))
  }, [filteredApprovals])

  const pendingAccessRequests = useMemo(() => {
    return accessRequests
      .filter((request) => request.status === 'pending')
      .sort((left, right) => new Date(right.reviewedAt || right.requestedAt).getTime() - new Date(left.reviewedAt || left.requestedAt).getTime())
  }, [accessRequests])

  const processedAccessRequests = useMemo(() => {
    return accessRequests
      .filter((request) => request.status !== 'pending')
      .sort((left, right) => new Date(right.reviewedAt || right.requestedAt).getTime() - new Date(left.reviewedAt || left.requestedAt).getTime())
  }, [accessRequests])

  const pageSize = useMemo(() => {
    const userLimit = itemsPerPageSetting || 10
    const adminLimit = settings.workspaceSettings?.maxListItems
    if (adminLimit && adminLimit > 0) {
      return Math.min(userLimit, adminLimit)
    }
    return userLimit
  }, [itemsPerPageSetting, settings.workspaceSettings?.maxListItems])

  const pendingTotalPages = Math.max(1, Math.ceil(pendingApprovals.length / pageSize))
  const processedTotalPages = Math.max(1, Math.ceil(processedApprovals.length / pageSize))

  const pendingApprovalsPaged = useMemo(() => {
    const startIndex = (pendingPage - 1) * pageSize
    return pendingApprovals.slice(startIndex, startIndex + pageSize)
  }, [pendingApprovals, pendingPage, pageSize])

  const processedApprovalsPaged = useMemo(() => {
    const startIndex = (processedPage - 1) * pageSize
    return processedApprovals.slice(startIndex, startIndex + pageSize)
  }, [processedApprovals, processedPage, pageSize])

  useEffect(() => {
    setPendingPage(1)
    setProcessedPage(1)
    setSelectedApprovals(new Set())
  }, [auth.currentWorkspaceId, requestFilter, searchQuery, selectedViewScope])

  useEffect(() => {
    if (pendingPage > pendingTotalPages) {
      setPendingPage(pendingTotalPages)
    }
  }, [pendingPage, pendingTotalPages])

  useEffect(() => {
    if (processedPage > processedTotalPages) {
      setProcessedPage(processedTotalPages)
    }
  }, [processedPage, processedTotalPages])

  // Initialize comment threads from approvals
  useEffect(() => {
    const threads: Record<string, ApprovalComment[]> = {}
    loadedApprovals.forEach(approval => {
      threads[approval.id] = approval.commentThread || []
    })
    setCommentThreads(threads)
  }, [loadedApprovals])

  const getRuleForApproval = (approval: RuleApproval): Rule | undefined => {
    return rules.find(r => sameId(r.id, approval.ruleId))
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  const getCommentTypeColor = (type: string) => {
    switch (type) {
      case 'note': return '#0052a3'
      case 'concern': return '#c5192d'
      case 'question': return '#ed8700'
      default: return '#666666'
    }
  }

  const handleAddComment = async (approvalId: string, isLocked: boolean) => {
    const text = newCommentText[approvalId]?.trim()
    if (!text) return
    if (isLocked) {
      addNotification({
        type: 'error',
        title: 'Comments locked',
        message: 'This approval is locked from new comments.',
      })
      return
    }

    const workspaceId = String(auth.currentWorkspaceId || '').trim()
    if (!workspaceId) {
      addNotification({
        type: 'error',
        title: 'Workspace required',
        message: 'Select a workspace before posting a discussion comment.',
      })
      return
    }

    const newComment: ApprovalComment = {
      id: `comment-${Date.now()}`,
      authorId: auth.user?.id || 'user-3',
      authorName: auth.user?.name || 'Reviewer',
      content: text,
      type: commentType[approvalId] || 'general',
      createdAt: new Date().toISOString(),
    }

    setCommentSubmittingId(approvalId)

    try {
      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const response = await fetch(`${apiBase}/approvals/${encodeURIComponent(approvalId)}/comments`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...buildAuthHeaders(),
        },
        body: JSON.stringify({
          comment: text,
          comment_type: commentType[approvalId] || 'general',
          workspace_id: workspaceId,
        }),
      })

      if (!response.ok) {
        const errorMessage = await response.text()
        throw new Error(errorMessage.trim() || `Unable to post discussion comment (${response.status}).`)
      }

      const updatedApproval = snakeToCamel<RuleApproval>(await response.json())
      const nextThread = Array.isArray(updatedApproval.commentThread) ? updatedApproval.commentThread : [
        ...((commentThreads[approvalId] || []) as ApprovalComment[]),
        newComment,
      ]

      setCommentThreads(prev => ({
        ...prev,
        [approvalId]: nextThread,
      }))
      setNewCommentText(prev => ({ ...prev, [approvalId]: '' }))
      setCommentType(prev => ({ ...prev, [approvalId]: 'general' }))
      addNotification({
        type: 'success',
        title: 'Comment posted',
        message: 'The approval discussion was saved.',
      })
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Comment failed',
        message: error instanceof Error ? error.message : 'Unable to post approval discussion comment.',
      })
    } finally {
      setCommentSubmittingId((current) => (current === approvalId ? null : current))
    }
  }

  const getHistoryEventIcon = (eventType: string): AppIconName => {
    switch (eventType) {
      case 'requested': return 'arrow-right'
      case 'commented': return 'chat'
      case 'approved': return 'check-circle'
      case 'rejected': return 'close-circle'
      case 'escalated': return 'bell'
      default: return 'bell'
    }
  }

  const getHistoryEventLabel = (eventType: string) => {
    switch (eventType) {
      case 'requested': return 'Submitted for approval'
      case 'commented': return 'Added a comment'
      case 'approved': return 'Rule approved'
      case 'rejected': return 'Rule rejected'
      case 'escalated': return 'Escalated'
      default: return 'Event'
    }
  }

  const getEmailEventIcon = (eventType: string): AppIconName => {
    switch (eventType) {
      case 'submitted': return 'arrow-right'
      case 'commented': return 'chat'
      case 'approved': return 'check-circle'
      case 'rejected': return 'close-circle'
      case 'escalated': return 'bell'
      default: return 'bell'
    }
  }

  const getEmailStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'sent': return 'status-sent'
      case 'failed': return 'status-failed'
      case 'pending': return 'status-pending'
      default: return 'status-default'
    }
  }

  const getTeamsEventIcon = (eventType: string): AppIconName => {
    switch (eventType) {
      case 'submitted': return 'arrow-right'
      case 'commented': return 'chat'
      case 'approved': return 'check-circle'
      case 'rejected': return 'close-circle'
      case 'escalated': return 'bell'
      default: return 'bell'
    }
  }

  const getNotificationMethodIcons = (approval: RuleApproval) => {
    const icons = []
    if (approval.emailNotifications && approval.emailNotifications.length > 0) {
      icons.push({ icon: '📧', label: 'Email', count: approval.emailNotifications.length })
    }
    if (approval.teamsNotifications && approval.teamsNotifications.length > 0) {
      icons.push({ icon: '💻', label: 'Teams', count: approval.teamsNotifications.length })
    }
    return icons
  }

  const handleSelectToggle = (approvalId: string) => {
    const newSelected = new Set(selectedApprovals)
    if (newSelected.has(approvalId)) {
      newSelected.delete(approvalId)
    } else {
      newSelected.add(approvalId)
    }
    setSelectedApprovals(newSelected)
  }

  const normalizeApprovalStatus = (status: string): 'pending' | 'approved' | 'rejected' => {
    const normalized = String(status || '').trim().toLowerCase()
    if (normalized === 'declined') return 'rejected'
    if (normalized === 'approved') return 'approved'
    if (normalized === 'rejected') return 'rejected'
    return 'pending'
  }

  const getApprovalRequestType = (approval: RuleApproval): 'activation' | 'deactivation' | 'gx_suite_repair' => {
    return approval.requestType === 'deactivation' || approval.requestType === 'gx_suite_repair'
      ? approval.requestType
      : 'activation'
  }

  const getApprovalEffectiveStatus = (approval: RuleApproval): string | null => {
    if (approval.effectiveStatus) {
      return approval.effectiveStatus
    }

    const requestType = getApprovalRequestType(approval)
    if (requestType === 'activation') {
      return 'activated'
    }
    if (requestType === 'deactivation') {
      return 'deactivated'
    }
    return null
  }

  const getRequestFilterLabel = (filter: ApprovalRequestFilter): string => {
    switch (filter) {
      case 'activation':
        return 'approval requests'
      case 'deactivation':
        return 'deactivation requests'
      case 'gx_suite_repair':
        return 'suite repair requests'
      default:
        return 'approvals'
    }
  }

  const handleRequestFilterChange = (e: any) => {
    const rawValue = e?.detail?.value ?? e?.target?.value
    const normalized = String(rawValue || '').trim().toLowerCase()
    if (normalized === 'activation' || normalized === 'deactivation' || normalized === 'gx_suite_repair' || normalized === 'all') {
      setRequestFilter(normalized)
    }
  }

  const getApprovalRequestLabel = (approval: RuleApproval): string => {
    const requestType = getApprovalRequestType(approval)
    if (approval.gxRunPlanId) {
      return requestType === 'deactivation' ? 'DQ Run Plan Deactivation Request' : 'DQ Run Plan Activation Request'
    }
    if (requestType === 'deactivation') return 'Rule Deactivation Request'
    if (requestType === 'gx_suite_repair') return 'Suite Repair Request'
    return 'Rule Approval Request'
  }

  const getApprovalRequesterDisplayName = (approval: RuleApproval): string => {
    const requesterId = String(approval.requesterId || '').trim()
    const requesterEmail = String(
      (approval as any).requesterEmail ||
        (approval as any).requesterDisplayEmail ||
        (approval as any).requestedByEmail ||
        ''
    ).trim()
    if (requesterEmail) {
      return requesterEmail
    }

    const adminUser = adminUsersById.get(requesterId.toLowerCase())
    if (adminUser?.email) {
      return adminUser.email
    }

    return requesterId || 'Unknown requester'
  }

  const getApprovalRequesterLabel = (approval: RuleApproval): string => {
    return getApprovalRequesterDisplayName(approval)
  }

  const getAccessRequestRequesterLabel = (request: ExceptionFactAccessRequest): string => {
    const requesterId = String(request.requesterId || '').trim()
    const adminUser = adminUsersById.get(requesterId.toLowerCase())
    if (adminUser?.email) {
      return adminUser.email
    }

    return requesterId || 'Unknown requester'
  }

  const getAccessRequestRoleLabel = (request: ExceptionFactAccessRequest): string => {
    if (request.roleId === 'exception-fact-investigator') {
      return 'Exception Fact Investigator'
    }
    return 'Exception Fact Reader'
  }

  const getAccessRequestStatusLabel = (status: string): string => {
    const normalized = String(status || '').trim().toLowerCase()
    if (normalized === 'timed_out') return 'Timed out'
    if (normalized === 'revoked' || normalized === 'rejected') return 'Declined'
    return normalized
      .split('_')
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ')
  }

  const getAccessRequestSubjectLabel = (request: ExceptionFactAccessRequest): string => {
    return request.roleId === 'exception-fact-investigator'
      ? 'Exception Fact Investigator Request'
      : 'Exception Fact Reader Request'
  }

  const isGovernanceInboxApproval = (item: RuleApproval | GovernanceInboxRuleView): item is RuleApproval => {
    return Boolean((item as RuleApproval).requesterId || (item as RuleApproval).requestType)
  }

  const renderGovernanceInboxCard = (
    title: string,
    description: string,
    inbox: GovernanceInboxPageView<RuleApproval | GovernanceInboxRuleView> | undefined,
  ) => {
    const total = inbox?.pagination.total ?? 0
    const shown = inbox?.data.length ?? 0

    return (
      <section className="governance-inbox-card">
        <div className="governance-inbox-card-header">
          <div>
            <h4>{title}</h4>
            <p>{description}</p>
          </div>
          <div className="governance-inbox-card-count">
            <strong>{total}</strong>
            <span>items</span>
          </div>
        </div>

        <div className="governance-inbox-card-meta">
          <span>{shown} shown on this page</span>
          <span>Page {inbox?.pagination.page ?? 1} of {Math.max(1, inbox?.pagination.totalPages ?? 1)}</span>
        </div>

        {inbox?.data.length ? (
          <ul className="governance-inbox-list">
            {inbox.data.map((item) => {
              if (isGovernanceInboxApproval(item)) {
                const requesterLabel = getApprovalRequesterLabel(item)
                const requestLabel = getApprovalRequestLabel(item)

                return (
                  <li key={item.id} className="governance-inbox-item">
                    <div className="governance-inbox-item-title-row">
                      <strong>{getApprovalSubjectLabel(item)}</strong>
                      <span className="approval-type-badge">{requestLabel}</span>
                    </div>
                    <div className="governance-inbox-item-meta">
                      <span>Requested by {requesterLabel}</span>
                      <span>{new Date(item.requestedAt).toLocaleDateString()}</span>
                    </div>
                  </li>
                )
              }

              const missingOwners = [
                !String(item.dataSteward || '').trim() ? 'data steward' : null,
                !String(item.domainOwner || '').trim() ? 'domain owner' : null,
                !String(item.technicalOwner || '').trim() ? 'technical owner' : null,
              ].filter(Boolean)

              return (
                <li key={item.id} className="governance-inbox-item">
                  <div className="governance-inbox-item-title-row">
                    <strong>{item.name}</strong>
                    <span className="governance-inbox-item-id">{item.id}</span>
                  </div>
                  <div className="governance-inbox-item-meta">
                    <span>Lifecycle: {item.lifecycleStatus || item.status || 'unknown'}</span>
                    <span>
                      {missingOwners.length > 0
                        ? `Missing owners: ${missingOwners.join(', ')}`
                        : 'All ownership fields assigned'}
                    </span>
                    {item.pendingDeactivationRequested ? <span>Pending deactivation requested</span> : null}
                  </div>
                </li>
              )
            })}
          </ul>
        ) : (
          <div className="governance-inbox-empty">No items are currently waiting in this inbox.</div>
        )}
      </section>
    )
  }

  const handleApproveAccessRequest = async (requestId: string) => {
    await handleReviewAccessRequest(requestId, 'approved')
  }

  const handleRejectAccessRequest = async (requestId: string) => {
    await handleReviewAccessRequest(requestId, 'rejected')
  }

  const handleReviewAccessRequest = async (requestId: string, status: 'approved' | 'rejected') => {
    if (!canReviewAccessRequests) {
      addNotification({
        type: 'error',
        title: 'Approval Failed',
        message: 'Workspace admin access is required to review exception-record access requests.',
        relatedId: requestId,
      })
      return
    }

    if (!auth.currentWorkspaceId) {
      addNotification({
        type: 'error',
        title: 'Approval Failed',
        message: 'Select an active workspace before reviewing exception-record access requests.',
        relatedId: requestId,
      })
      return
    }

    try {
      setAccessRequestSubmittingId(requestId)
      const apiBase = toApiGroupV1Base('admin', settings.applicationSettings?.apiBaseUrl)
      const token = getAuthToken()
      const response = await fetch(`${apiBase}/exception-fact-access-requests/${encodeURIComponent(requestId)}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          status,
          comments: accessRequestComments[requestId] || '',
        }),
      })

      if (!response.ok) {
        const errorText = await response.text().catch(() => '')
        throw new Error(`Failed to update exception-record access request (${response.status})${errorText ? `: ${errorText}` : ''}`)
      }

      const updatedRequest = snakeToCamel<ExceptionFactAccessRequest>(await response.json())
      addNotification({
        type: status === 'approved' ? 'rule-activated' : 'rule-rejected',
        title: status === 'approved' ? 'Access Request Approved' : 'Access Request Rejected',
        message: `Exception-record access request ${status === 'approved' ? 'approved' : 'rejected'}.`,
        relatedId: requestId,
      })
      setAccessRequestComments((prev) => ({ ...prev, [requestId]: '' }))
      if (updatedRequest && updatedRequest.id) {
        setAccessRequests((prev) => prev.map((request) => (request.id === updatedRequest.id ? updatedRequest : request)))
      }
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Approval Failed',
        message: error instanceof Error ? error.message : 'Could not review exception-record access request. Please try again.',
        relatedId: requestId,
      })
    } finally {
      setAccessRequestSubmittingId(null)
    }
  }

  const renderGovernanceMatrix = (
    title: string,
    model: GovernanceStatusModel | null,
    sourceLabel: string,
  ) => {
    const transitionLookup = new Map<string, { label: string; requiredAnyScopes: string[] }>()
    if (model) {
      for (const transition of model.transitions) {
        transitionLookup.set(`${transition.fromStatus} -> ${transition.toStatus}`, {
          label: transition.label,
          requiredAnyScopes: Array.isArray(transition.requiredAnyScopes) ? transition.requiredAnyScopes : [],
        })
      }
    }

    if (!model) {
      return (
        <div className="transition-matrix-card transition-matrix-card-empty">
          <h3>{title}</h3>
          <p>Loading backend-defined governance policy...</p>
        </div>
      )
    }

    return (
      <div className="transition-matrix-card">
        <div className="transition-matrix-card-header">
          <div>
            <h3>{title}</h3>
            <p>{model.statuses.length} statuses, {model.transitions.length} defined transitions</p>
          </div>
          <div className="transition-matrix-source">
            <span className="transition-matrix-source-label">Source</span>
            <span className="transition-matrix-source-value">{sourceLabel}</span>
          </div>
        </div>

        <div className="transition-matrix-table-wrap">
          <table className="transition-matrix-table">
            <thead>
              <tr>
                <th>From / To</th>
                {model.statuses.map((status) => (
                  <th key={status.value}>
                    <div className="transition-matrix-column-label">
                      <span>{status.label}</span>
                      <span className="transition-matrix-column-value">{status.value}</span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {model.statuses.map((fromStatus) => (
                <tr key={fromStatus.value}>
                  <th scope="row">
                    <div className="transition-matrix-row-label">
                      <span>{fromStatus.label}</span>
                      <span className="transition-matrix-row-value">{fromStatus.value}</span>
                      {fromStatus.isInitial ? <span className="transition-matrix-pill">Initial</span> : null}
                      {fromStatus.isTerminal ? <span className="transition-matrix-pill transition-matrix-pill-terminal">Terminal</span> : null}
                    </div>
                  </th>
                  {model.statuses.map((toStatus) => {
                    const transition = transitionLookup.get(`${fromStatus.value} -> ${toStatus.value}`)
                    return (
                      <td key={`${fromStatus.value}-${toStatus.value}`} className={transition ? 'transition-matrix-cell-enabled' : 'transition-matrix-cell-disabled'}>
                        {transition ? (
                          <div className="transition-matrix-cell-content">
                            <span className="transition-matrix-label">{transition.label}</span>
                            {transition.requiredAnyScopes.length > 0 ? (
                              <span className="transition-matrix-scopes">{transition.requiredAnyScopes.join(', ')}</span>
                            ) : (
                              <span className="transition-matrix-scopes transition-matrix-scopes-empty">No scope gate</span>
                            )}
                          </div>
                        ) : (
                          <span className="transition-matrix-empty">—</span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {model.statuses.some((status) => status.description) ? (
          <div className="transition-matrix-notes">
            {model.statuses
              .filter((status) => status.description)
              .map((status) => (
                <div key={`${status.value}-description`} className="transition-matrix-note">
                  <strong>{status.label}</strong>
                  <span>{status.description}</span>
                </div>
              ))}
          </div>
        ) : null}
      </div>
    )
  }

  const canTransitionApproval = (approval: RuleApproval, target: 'approved' | 'rejected'): boolean => {
    const currentStatus = normalizeApprovalStatus(approval.status)
    if (approvalGovernanceLoaded) {
      const allowedTargets = approvalAllowedTransitionsByStatus?.[currentStatus] || []
      return allowedTargets.includes(target)
    }

    return currentStatus === 'pending' && (auth.canApproveRule?.() || false)
  }

  const canBulkApproveSelection = Array.from(selectedApprovals).every((id) => {
    const approval = pendingApprovals.find((item) => sameId(item.id, id))
    return approval ? canTransitionApproval(approval, 'approved') && !isSelfRequestedApproval(approval) : false
  })

  const canBulkRejectSelection = Array.from(selectedApprovals).every((id) => {
    const approval = pendingApprovals.find((item) => sameId(item.id, id))
    return approval ? canTransitionApproval(approval, 'rejected') : false
  })

  const handleSelectAllPage = () => {
    const currentPageIds = new Set(pendingApprovalsPaged.map(a => a.id))
    if (currentPageIds.size === selectedApprovals.size && Array.from(currentPageIds).every(id => selectedApprovals.has(id))) {
      setSelectedApprovals(new Set())
    } else {
      setSelectedApprovals(currentPageIds)
    }
  }

  const handleBulkApprove = async () => {
    try {
      let successCount = 0
      for (const approvalId of selectedApprovals) {
        await approveRule(approvalId, bulkComments)
        successCount += 1
      }
      await loadApprovals()
      addNotification({
        type: 'rule-activated',
        title: 'Bulk Approval Completed',
        message: `${successCount} approval${successCount === 1 ? '' : 's'} approved.`,
      })
      setSelectedApprovals(new Set())
      setBulkActionType(null)
      setBulkComments('')
    } catch (error) {
      console.error('Failed to bulk approve rules:', error)
      addNotification({
        type: 'error',
        title: 'Bulk Approval Failed',
        message: 'Could not complete bulk approval. Please try again.',
      })
    }
  }

  const handleBulkReject = async () => {
    try {
      let successCount = 0
      for (const approvalId of selectedApprovals) {
        await rejectRule(approvalId, bulkComments)
        successCount += 1
      }
      await loadApprovals()
      addNotification({
        type: 'rule-rejected',
        title: 'Bulk Rejection Completed',
        message: `${successCount} approval${successCount === 1 ? '' : 's'} rejected.`,
      })
      setSelectedApprovals(new Set())
      setBulkActionType(null)
      setBulkComments('')
    } catch (error) {
      console.error('Failed to bulk reject rules:', error)
      addNotification({
        type: 'error',
        title: 'Bulk Rejection Failed',
        message: 'Could not complete bulk rejection. Please try again.',
      })
    }
  }

  const handleApprove = async (approvalId: string) => {
    try {
      const comments = approvalComments[approvalId]
      const approval = loadedApprovals.find((item) => sameId(item.id, approvalId))
      if (approval && isSelfRequestedApproval(approval)) {
        addNotification({
          type: 'error',
          title: 'Approval Not Allowed',
          message: 'You cannot approve your own request. Ask another approver to review it.',
          relatedId: approvalId,
        })
        return
      }
      await approveRule(approvalId, comments)
      await loadApprovals()
      const rule = approval ? rules.find((r) => r.id === approval.ruleId) : undefined
      const requestType = approval ? getApprovalRequestType(approval) : 'activation'
      const subjectLabel = approval ? getApprovalSubjectLabel(approval) : 'Approval'
      const requestLabel = requestType === 'deactivation'
        ? 'Rule Deactivated'
        : requestType === 'gx_suite_repair'
          ? 'Suite Repair Approved'
          : 'Rule Approved'
      const message = requestType === 'deactivation'
        ? (approval?.gxRunPlanId ? `${subjectLabel} was deactivated.` : (rule ? `${rule.name} was deactivated.` : `Deactivation ${approvalId} completed.`))
        : requestType === 'gx_suite_repair'
          ? (rule ? `${rule.name} suite repair was approved.` : `Suite repair ${approvalId} completed.`)
          : (approval?.gxRunPlanId ? `${subjectLabel} was approved.` : (rule ? `${rule.name} was approved.` : `Approval ${approvalId} completed.`))
      addNotification({
        type: requestType === 'deactivation' ? 'rule-rejected' : requestType === 'gx_suite_repair' ? 'success' : 'rule-activated',
        title: requestLabel,
        message,
        relatedId: approvalId,
      })
      setApprovalComments(prev => ({ ...prev, [approvalId]: '' }))
    } catch (error) {
      console.error('Failed to approve rule:', error)
      const errorMessage = error instanceof Error ? error.message : ''
      const isSelfApprovalError = /Requester cannot approve their own request/i.test(errorMessage)
      addNotification({
        type: 'error',
        title: 'Approval Failed',
        message: isSelfApprovalError
          ? 'You cannot approve your own request. Ask another approver to review it.'
          : 'Could not approve rule. Please try again.',
        relatedId: approvalId,
      })
    }
  }

  const handleReject = async (approvalId: string) => {
    try {
      const comments = approvalComments[approvalId]
      const approval = loadedApprovals.find((item) => sameId(item.id, approvalId))
      if (!comments.trim()) {
        alert('Please provide comments for rejection')
        addNotification({
          type: 'warning',
          title: 'Comment Required',
          message: 'Please provide comments before rejecting.',
          relatedId: approvalId,
        })
        return
      }
      await rejectRule(approvalId, comments)
      await loadApprovals()
      const rule = approval ? rules.find((r) => sameId(r.id, approval.ruleId)) : undefined
      const requestType = approval ? getApprovalRequestType(approval) : 'activation'
      const subjectLabel = approval ? getApprovalSubjectLabel(approval) : 'Approval'
      const message = requestType === 'deactivation'
        ? (approval?.gxRunPlanId ? `${subjectLabel} deactivation was rejected.` : (rule ? `${rule.name} deactivation was rejected.` : `Deactivation ${approvalId} rejected.`))
        : requestType === 'gx_suite_repair'
          ? (rule ? `${rule.name} suite repair was rejected.` : `Suite repair ${approvalId} rejected.`)
          : (approval?.gxRunPlanId ? `${subjectLabel} was rejected.` : (rule ? `${rule.name} was rejected.` : `Approval ${approvalId} rejected.`))
      addNotification({
        type: 'rule-rejected',
        title: requestType === 'deactivation' ? 'Deactivation Rejected' : requestType === 'gx_suite_repair' ? 'Suite Repair Rejected' : 'Rule Rejected',
        message,
        relatedId: approvalId,
      })
      setApprovalComments(prev => ({ ...prev, [approvalId]: '' }))
    } catch (error) {
      console.error('Failed to reject rule:', error)
      addNotification({
        type: 'error',
        title: 'Rejection Failed',
        message: 'Could not reject rule. Please try again.',
        relatedId: approvalId,
      })
    }
  }

  if (!canViewPendingApprovals && !canReviewAccessRequests && !(selectedViewScope === 'global' && canViewAllApprovals)) {
    return (
      <div className="approvals-container">
        <div className="no-permissions">
          <p>You do not have permission to access governance review workflows.</p>
        </div>
      </div>
    )
  }

  return (
    <AppPageShell className={`approvals-container${compactMode ? ' compact' : ''}`}>
      <AppPageHeader
        className="approvals-header"
        title="Governance"
        description="Review approval queues, inspect policy transitions, and manage rule and exception-record access workflows."
      >
        <div className="approvals-header-meta">
          <WorkspaceScopeSegmentedControl
            value={selectedViewScope}
            onChange={setSelectedViewScope}
            ariaLabel="Governance scope"
            label="Show:"
            className="approvals-scope-group"
            controlClassName="approvals-scope-control"
            options={DEFAULT_WORKSPACE_SCOPE_OPTIONS.map((option): WorkspaceScopeOption => option.value === 'global'
              ? {
                  ...option,
                  disabled: !canViewAllApprovals,
                  disabledTitle: 'Admin access required for all across workspaces',
                }
              : option)}
          />
          <div className="approvals-tabs" role="tablist" aria-label="Governance views">
            <button
              type="button"
              role="tab"
              aria-selected={activeView === 'queue'}
              className={`approvals-tab ${activeView === 'queue' ? 'active' : ''}`}
              onClick={() => setActiveView('queue')}
            >
              Approval Queue
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeView === 'governance'}
              className={`approvals-tab ${activeView === 'governance' ? 'active' : ''}`}
              onClick={() => setActiveView('governance')}
            >
              Governance
            </button>
          </div>
          <div className="approval-stats">
            <span className="stat">
              <strong>{pendingApprovals.length}</strong> Pending
            </span>
            <span className="stat">
              <strong>{processedApprovals.length}</strong> Processed
            </span>
          </div>
        </div>
      </AppPageHeader>

      {activeView === 'governance' ? (
        <div className="approvals-governance-view">
          <div className="approvals-governance-intro">
            <div>
              <h3>Governance transitions</h3>
              <p>These matrices are driven by the backend-defined governance policy from the <code>/governance/status-models</code> endpoint and reject invalid state changes at the API layer. The DQ run plan lifecycle keeps execution requests separate from the effective active/inactive state, regardless of which engine will run the plan.</p>
            </div>
          </div>
          <div className="approvals-governance-grid">
            {renderGovernanceMatrix('Rule lifecycle', ruleStatusModel, '/governance/status-models/rule')}
            {renderGovernanceMatrix('Approval lifecycle', approvalStatusModel, '/governance/status-models/approval')}
            {renderGovernanceMatrix('DQ run plan lifecycle', runPlanStatusModel, '/governance/status-models/run_plan')}
          </div>
          <div className="governance-inboxes-section">
            <div className="governance-inboxes-section-header">
              <div>
                <h3>Governance inboxes</h3>
                <p>Backend-owned queues for approval decisions, missing ownership assignments, and deprecated-rule review.</p>
              </div>
              {loadingGovernanceInboxes ? <span className="governance-inboxes-loading">Loading inboxes…</span> : null}
            </div>

            {governanceInboxesError ? (
              <div className="governance-inboxes-error" role="alert">
                {governanceInboxesError}
              </div>
            ) : null}

            {governanceInboxes ? (
              <div className="governance-inbox-grid">
                {renderGovernanceInboxCard(
                  'Approval inbox',
                  'Pending approval requests owned by the backend contract.',
                  governanceInboxes.approvalInbox,
                )}
                {renderGovernanceInboxCard(
                  'Reassignment inbox',
                  'Rules that still need one or more ownership fields assigned.',
                  governanceInboxes.reassignmentInbox,
                )}
                {renderGovernanceInboxCard(
                  'Deprecation review inbox',
                  'Rules in deprecated or superseded lifecycle states that need review.',
                  governanceInboxes.deprecationReviewInbox,
                )}
              </div>
            ) : loadingGovernanceInboxes ? (
              <div className="governance-inboxes-empty">Loading governance inboxes…</div>
            ) : (
              <div className="governance-inboxes-empty">Open the governance view to load the backend-owned inbox queues.</div>
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="approvals-controls">
            <div className="approvals-filter-group">
              <AppSelect
                label="Request type"
                value={requestFilter}
                onChange={handleRequestFilterChange}
                options={[
                  { value: 'all', label: 'All requests' },
                  { value: 'activation', label: 'Approval requests' },
                  { value: 'deactivation', label: 'Deactivation requests' },
                  { value: 'gx_suite_repair', label: 'Suite repair requests' },
                ]}
              />
            </div>
            <div className="approvals-search-group">
              <AppInput
                id="approvals-search-input"
                label="Search"
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search by requester, reviewer, status, or comments"
              />
            </div>
          </div>

          {approvalsError ? (
            <div className="no-approvals">
              <p>{approvalsError}</p>
            </div>
          ) : loadingApprovals && pendingApprovals.length === 0 && processedApprovals.length === 0 && !canViewAccessRequests ? (
            <div className="no-approvals">
              <p>Loading approvals...</p>
            </div>
          ) : pendingApprovals.length === 0 && processedApprovals.length === 0 && !canViewAccessRequests ? (
            <div className="no-approvals">
              <p>No {getRequestFilterLabel(requestFilter)} to review.</p>
            </div>
          ) : (
            <>
          {selectedApprovals.size > 0 && (
            <div className="bulk-action-bar">
              <div className="bulk-action-content">
                <span className="selection-count">{selectedApprovals.size} approval{selectedApprovals.size !== 1 ? 's' : ''} selected</span>
                {!bulkActionType ? (
                  <div className="bulk-action-buttons">
                    <button
                      className="bulk-btn bulk-approve-btn"
                      disabled={!canBulkApproveSelection}
                      onClick={() => setBulkActionType('approve')}
                    >
                      Approve Selected
                    </button>
                    <button
                      className="bulk-btn bulk-reject-btn"
                      disabled={!canBulkRejectSelection}
                      onClick={() => setBulkActionType('reject')}
                    >
                      Reject Selected
                    </button>
                    <button
                      className="bulk-btn bulk-cancel-btn"
                      onClick={() => setSelectedApprovals(new Set())}
                    >
                      Clear Selection
                    </button>
                  </div>
                ) : (
                  <div className="bulk-action-form">
                    <AppTextarea
                      label={`Bulk ${bulkActionType} comments`}
                      placeholder={`Add comments for bulk ${bulkActionType}...`}
                      value={bulkComments}
                      onChange={(e) => setBulkComments(e.target.value)}
                    />
                    <div className="bulk-action-form-buttons">
                      <button
                        className={`bulk-btn ${bulkActionType === 'approve' ? 'bulk-approve-btn' : 'bulk-reject-btn'}`}
                        disabled={bulkActionType === 'approve' ? !canBulkApproveSelection : !canBulkRejectSelection}
                        onClick={bulkActionType === 'approve' ? handleBulkApprove : handleBulkReject}
                      >
                        Confirm {bulkActionType === 'approve' ? 'Approve' : 'Reject'}
                      </button>
                      <button
                        className="bulk-btn bulk-cancel-btn"
                        onClick={() => {
                          setBulkActionType(null)
                          setBulkComments('')
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
          {pendingApprovals.length > 0 && (
            <div className="approvals-section">
              <div className="section-header">
                <h3 className="section-title">Pending Review</h3>
                {pendingApprovalsPaged.length > 0 && (
                  <label className="select-all-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedApprovals.size > 0 && pendingApprovalsPaged.every(a => selectedApprovals.has(a.id))}
                      onChange={handleSelectAllPage}
                    />
                    Select All on Page
                  </label>
                )}
              </div>
              <div className="approvals-list">
                {pendingApprovalsPaged.map(approval => {
                  const rule = getRuleForApproval(approval)
                  const ruleLabel = getApprovalSubjectLabel(approval)
                  const requesterLabel = getApprovalRequesterLabel(approval)
                  const requestTypeLabel = getApprovalRequestLabel(approval)
                  const effectiveStatusLabel = getApprovalEffectiveStatus(approval)

                  return (
                    <div
                      key={approval.id}
                      className={`approval-card pending ${expandedApprovalId === approval.id ? 'expanded' : ''} ${selectedApprovals.has(approval.id) ? 'selected' : ''}`}
                    >
                      <div className="approval-header">
                        <input
                          type="checkbox"
                          className="approval-checkbox"
                          checked={selectedApprovals.has(approval.id)}
                          onChange={() => handleSelectToggle(approval.id)}
                        />
                        <div className="approval-content">
                          <div className="approval-title-row">
                            <h4>{ruleLabel}</h4>
                            <span className="approval-requester">Requested by {requesterLabel}</span>
                            <span className="approval-type-badge">{requestTypeLabel}</span>
                            {approval.delegation && approval.delegation.status === 'active' && (
                              <span className="delegation-badge" title={`Delegated from ${approval.delegation.delegatedFromName} to ${approval.delegation.delegatedToName}`}>
                                🔄 Delegated
                              </span>
                            )}
                          </div>
                          <div className="approval-meta">
                            <span className="meta-item">
                              <strong>Request type:</strong> {requestTypeLabel}
                            </span>
                            {effectiveStatusLabel && (
                              <span className="meta-item">
                                <strong>Effective status:</strong> {effectiveStatusLabel}
                              </span>
                            )}
                            <span className="meta-item">
                              <strong>Requested:</strong>{' '}
                              {new Date(approval.requestedAt).toLocaleDateString()}
                            </span>
                            {getNotificationMethodIcons(approval).length > 0 && (
                              <span className="meta-item notification-methods">
                                {getNotificationMethodIcons(approval).map((method, idx) => (
                                  <span key={idx} title={`${method.label} (${method.count})`} className="notification-icon">
                                    {method.icon}
                                  </span>
                                ))}
                              </span>
                            )}
                          </div>
                        </div>
                        <button
                          className="expand-btn"
                          onClick={() =>
                            setExpandedApprovalId(
                              expandedApprovalId === approval.id ? null : approval.id
                            )
                          }
                        >
                          {expandedApprovalId === approval.id ? '▼' : '▶'}
                        </button>
                      </div>

                      {expandedApprovalId === approval.id && (
                        <div className="approval-details">
                          <div className="rule-info">
                            <p>
                              <strong>Description:</strong> {approval.gxRunPlanId ? 'DQ run plan approval request' : (rule?.description || 'Rule details are not loaded.')}
                            </p>
                            {rule?.testResults && (
                              <p>
                                <strong>Test Results:</strong> DQ Score {rule.testResults.coverage}%
                                {rule.testResults.status === 'passed' ? (
                                  <span className="test-status passed"> ✓ Passed</span>
                                ) : (
                                  <span className="test-status failed"> ✗ Failed</span>
                                )}
                              </p>
                            )}
                            <p>
                              <strong>Risk Level:</strong>{' '}
                              <span className="risk-level">{rule?.riskLevel?.toUpperCase() || 'UNKNOWN'}</span>
                            </p>
                          </div>

                          {approval.delegation && approval.delegation.status === 'active' && (
                            <div className="approval-delegation-section">
                              <h5>📋 Approval Delegation</h5>
                              <div className="delegation-info">
                                <div className="delegation-row">
                                  <span className="delegation-label">Delegated from:</span>
                                  <span className="delegation-value">{approval.delegation.delegatedFromName}</span>
                                </div>
                                <div className="delegation-row">
                                  <span className="delegation-label">Delegated to:</span>
                                  <span className="delegation-value" style={{ fontWeight: 600 }}>{approval.delegation.delegatedToName}</span>
                                </div>
                                {approval.delegation.delegationReason && (
                                  <div className="delegation-row">
                                    <span className="delegation-label">Reason:</span>
                                    <span className="delegation-reason">{approval.delegation.delegationReason}</span>
                                  </div>
                                )}
                                <div className="delegation-row">
                                  <span className="delegation-label">Valid until:</span>
                                  <span className="delegation-value">{approval.delegation.validUntil ? new Date(approval.delegation.validUntil).toLocaleDateString() : 'No expiration'}</span>
                                </div>
                                <div className="delegation-row">
                                  <span className="delegation-label">Delegated at:</span>
                                  <span className="delegation-value">{formatDate(approval.delegation.delegatedAt)}</span>
                                </div>
                              </div>
                            </div>
                          )}

                          <DiscussionPanel
                            title="Notes & Discussion"
                            entries={normalizeDiscussionEntries(commentThreads[approval.id] || approval.commentThread || [], auth.user?.name || 'Reviewer')}
                            emptyState="No discussion comments yet."
                            composer={{
                              commentType: commentType[approval.id] || 'general',
                              commentText: newCommentText[approval.id] || '',
                              onCommentTypeChange: (nextType) => setCommentType((prev) => ({ ...prev, [approval.id]: nextType })),
                              onCommentTextChange: (nextText) => setNewCommentText((prev) => ({ ...prev, [approval.id]: nextText })),
                              onSubmit: () => handleAddComment(approval.id, Boolean(approval.commentsLocked)),
                              submitLabel: commentSubmittingId === approval.id ? 'Posting…' : 'Add Comment',
                              placeholder: 'Add a note or question...',
                              disabled: commentSubmittingId === approval.id || Boolean(approval.commentsLocked),
                              typeSelectId: `comment-type-${approval.id}`,
                              textareaId: `comment-text-${approval.id}`,
                            }}
                          />

                          {approval.history && approval.history.length > 0 && (
                            <div className="approval-history-section">
                              <h5>Timeline</h5>
                              <div className="history-timeline">
                                {approval.history.map((event) => (
                                  <div key={event.id} className={`history-event history-event-${event.eventType}`}>
                                    <div className="event-icon"><AppIcon name={getHistoryEventIcon(event.eventType)} /></div>
                                    <div className="event-content">
                                      <div className="event-header">
                                        <span className="event-user">{event.userName}</span>
                                        <span className="event-label">{getHistoryEventLabel(event.eventType)}</span>
                                        <span className="event-time">{formatDate(event.timestamp)}</span>
                                      </div>
                                      {event.details?.comment && (
                                        <div className="event-details">{event.details.comment}</div>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {approval.emailNotifications && approval.emailNotifications.length > 0 && (
                            <div className="approval-emails-section">
                              <h5>
                                Email Notifications
                                <span className="email-count-badge">{approval.emailNotifications.length}</span>
                              </h5>
                              <div className="email-list">
                                {approval.emailNotifications.map((email) => (
                                  <div key={email.id} className={`email-item ${getEmailStatusBadgeClass(email.status)}`}>
                                    <div className="email-icon"><AppIcon name={getEmailEventIcon(email.eventType)} /></div>
                                    <div className="email-content">
                                      <div className="email-header">
                                        <span className="email-recipient">{email.recipientName}</span>
                                        <span className="email-address">{email.recipientEmail}</span>
                                        <span className={`email-status ${getEmailStatusBadgeClass(email.status)}`}>
                                          {email.status.toUpperCase()}
                                        </span>
                                      </div>
                                      <div className="email-subject">{email.subject}</div>
                                      <div className="email-footer">
                                        <span className="email-event-type">{email.eventType}</span>
                                        <span className="email-time">{formatDate(email.sentAt)}</span>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {approval.teamsNotifications && approval.teamsNotifications.length > 0 && (
                            <div className="approval-teams-section">
                              <h5>
                                Teams Notifications
                                <span className="teams-count-badge">{approval.teamsNotifications.length}</span>
                              </h5>
                              <div className="teams-list">
                                {approval.teamsNotifications.map((notification) => (
                                  <div key={notification.id} className={`teams-item ${getEmailStatusBadgeClass(notification.status)}`}>
                                    <div className="teams-icon"><AppIcon name={getTeamsEventIcon(notification.eventType)} /></div>
                                    <div className="teams-content">
                                      <div className="teams-header">
                                        <span className="teams-channel">
                                          <strong>#</strong>{notification.teamsChannelName}
                                        </span>
                                        <span className={`teams-status ${getEmailStatusBadgeClass(notification.status)}`}>
                                          {notification.status.toUpperCase()}
                                        </span>
                                      </div>
                                      <div className="teams-message">{notification.message}</div>
                                      <div className="teams-footer">
                                        <span className="teams-event-type">{notification.eventType}</span>
                                        <span className="teams-time">{formatDate(notification.sentAt)}</span>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          <div className="approval-actions">
                            <div className="comment-section">
                              <AppTextarea
                                label="Approval Decision Comment (optional)"
                                placeholder="Add approval decision comments..."
                                value={approvalComments[approval.id] || ''}
                                onChange={e =>
                                  setApprovalComments(prev => ({
                                    ...prev,
                                    [approval.id]: e.target.value,
                                  }))
                                }
                              />
                            </div>

                            <div className="action-buttons">
                              <Button
                                className="approval-action-btn"
                                onClick={() => handleApprove(approval.id)}
                                disabled={isLoading || !canTransitionApproval(approval, 'approved') || isSelfRequestedApproval(approval)}
                                title={isSelfRequestedApproval(approval) ? 'You cannot approve your own request.' : undefined}
                                variant="primary-default"
                              >
                                <AppIcon slot="icon" name="check" />
                                Approve
                              </Button>
                              <Button
                                className="approval-action-btn"
                                onClick={() => void handleReject(approval.id)}
                                disabled={isLoading || !canTransitionApproval(approval, 'rejected')}
                                variant="primary-destructive"
                              >
                                <AppIcon slot="icon" name="times" />
                                Reject
                              </Button>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
              {pendingApprovals.length > pageSize && (
                <div className="list-pagination">
                  <button
                    className="pagination-btn"
                    onClick={() => setPendingPage(prev => Math.max(1, prev - 1))}
                    disabled={pendingPage === 1}
                  >
                    Previous
                  </button>
                  <span className="pagination-info">
                    Page {pendingPage} of {pendingTotalPages}
                  </span>
                  <button
                    className="pagination-btn"
                    onClick={() => setPendingPage(prev => Math.min(pendingTotalPages, prev + 1))}
                    disabled={pendingPage === pendingTotalPages}
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          )}

          {processedApprovals.length > 0 && (
            <div className="approvals-section">
              <h3 className="section-title">Processing History</h3>
              <div className="approvals-list">
                {processedApprovalsPaged.map(approval => {
                  const rule = getRuleForApproval(approval)
                  const ruleLabel = getApprovalSubjectLabel(approval)
                  const requesterLabel = getApprovalRequesterLabel(approval)
                  const requestTypeLabel = getApprovalRequestLabel(approval)
                  const effectiveStatusLabel = getApprovalEffectiveStatus(approval)

                  return (
                    <div
                      key={approval.id}
                      className={`approval-card processed ${approval.status}`}
                      onClick={() =>
                        setExpandedApprovalId(
                          expandedApprovalId === approval.id ? null : approval.id
                        )
                      }
                    >
                      <div className="approval-header">
                        <div className="approval-content">
                          <div className="approval-title-row">
                            <h4>{ruleLabel}</h4>
                            <span className="approval-requester">Requested by {requesterLabel}</span>
                            <span className="approval-type-badge">{requestTypeLabel}</span>
                            {approval.delegation && approval.delegation.status === 'active' && (
                              <span className="delegation-badge" title={`Delegated from ${approval.delegation.delegatedFromName} to ${approval.delegation.delegatedToName}`}>
                                🔄 Delegated
                              </span>
                            )}
                          </div>
                          <div className="approval-meta">
                            <span className="meta-item">
                              <strong>Status:</strong>{' '}
                              <span className={`badge ${approval.status}`}>
                                {approval.status.toUpperCase()}
                              </span>
                            </span>
                            <span className="meta-item">
                              <strong>Request type:</strong> {requestTypeLabel}
                            </span>
                            {effectiveStatusLabel && (
                              <span className="meta-item">
                                <strong>Effective status:</strong> {effectiveStatusLabel}
                              </span>
                            )}
                            <span className="meta-item">
                              <strong>Reviewed by:</strong> {approval.reviewedBy || 'N/A'}
                            </span>
                            <span className="meta-item">
                              <strong>Date:</strong>{' '}
                              {new Date(approval.reviewedAt || approval.requestedAt).toLocaleDateString()}
                            </span>
                            {getNotificationMethodIcons(approval).length > 0 && (
                              <span className="meta-item notification-methods">
                                {getNotificationMethodIcons(approval).map((method, idx) => (
                                  <span key={idx} title={`${method.label} (${method.count})`} className="notification-icon">
                                    {method.icon}
                                  </span>
                                ))}
                              </span>
                            )}
                          </div>
                        </div>
                        <button
                          className="expand-btn"
                          onClick={e => {
                            e.stopPropagation()
                            setExpandedApprovalId(
                              expandedApprovalId === approval.id ? null : approval.id
                            )
                          }}
                        >
                          {expandedApprovalId === approval.id ? '▼' : '▶'}
                        </button>
                      </div>

                      {expandedApprovalId === approval.id && (
                        <div className="approval-details">
                          <div className="rule-info">
                            <p>
                              <strong>Description:</strong> {approval.gxRunPlanId ? 'DQ run plan approval request' : (rule?.description || 'Rule details are not loaded.')}
                            </p>
                            {rule?.testResults && (
                              <p>
                                <strong>Test Results:</strong> DQ Score {rule.testResults.coverage}%
                                {rule.testResults.status === 'passed' ? (
                                  <span className="test-status passed"> ✓ Passed</span>
                                ) : (
                                  <span className="test-status failed"> ✗ Failed</span>
                                )}
                              </p>
                            )}
                            <p>
                              <strong>Risk Level:</strong>{' '}
                              <span className="risk-level">{rule?.riskLevel?.toUpperCase() || 'UNKNOWN'}</span>
                            </p>
                          </div>

                          {approval.comments && (
                            <div className="comment-section">
                              <label>Review Comments:</label>
                              <p className="comments-text">{approval.comments}</p>
                            </div>
                          )}

                          <div className="comment-thread-section">
                            <h5>Notes & Discussion</h5>
                            <div className="comment-thread">
                              {commentThreads[approval.id]?.map(comment => (
                                <div key={comment.id} className="comment-item">
                                  <div className="comment-header">
                                    <span className="comment-author">{comment.authorName}</span>
                                    <span className={`comment-type comment-type-${comment.type}`}>
                                      {comment.type.charAt(0).toUpperCase() + comment.type.slice(1)}
                                    </span>
                                    <span className="comment-time">{formatDate(comment.createdAt)}</span>
                                  </div>
                                  <div className="comment-content">{comment.content}</div>
                                </div>
                              ))}
                            </div>
                          </div>

                          {approval.history && approval.history.length > 0 && (
                            <div className="approval-history-section">
                              <h5>Timeline</h5>
                              <div className="history-timeline">
                                {approval.history.map((event) => (
                                  <div key={event.id} className={`history-event history-event-${event.eventType}`}>
                                    <div className="event-icon">{getHistoryEventIcon(event.eventType)}</div>
                                    <div className="event-content">
                                      <div className="event-header">
                                        <span className="event-user">{event.userName}</span>
                                        <span className="event-label">{getHistoryEventLabel(event.eventType)}</span>
                                        <span className="event-time">{formatDate(event.timestamp)}</span>
                                      </div>
                                      {event.details?.comment && (
                                        <div className="event-details">{event.details.comment}</div>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {approval.emailNotifications && approval.emailNotifications.length > 0 && (
                            <div className="approval-emails-section">
                              <h5>
                                Email Notifications
                                <span className="email-count-badge">{approval.emailNotifications.length}</span>
                              </h5>
                              <div className="email-list">
                                {approval.emailNotifications.map((email) => (
                                  <div key={email.id} className={`email-item ${getEmailStatusBadgeClass(email.status)}`}>
                                    <div className="email-icon">{getEmailEventIcon(email.eventType)}</div>
                                    <div className="email-content">
                                      <div className="email-header">
                                        <span className="email-recipient">{email.recipientName}</span>
                                        <span className="email-address">{email.recipientEmail}</span>
                                        <span className={`email-status ${getEmailStatusBadgeClass(email.status)}`}>
                                          {email.status.toUpperCase()}
                                        </span>
                                      </div>
                                      <div className="email-subject">{email.subject}</div>
                                      <div className="email-footer">
                                        <span className="email-event-type">{email.eventType}</span>
                                        <span className="email-time">{formatDate(email.sentAt)}</span>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
              {processedApprovals.length > pageSize && (
                <div className="list-pagination">
                  <button
                    className="pagination-btn"
                    onClick={() => setProcessedPage(prev => Math.max(1, prev - 1))}
                    disabled={processedPage === 1}
                  >
                    Previous
                  </button>
                  <span className="pagination-info">
                    Page {processedPage} of {processedTotalPages}
                  </span>
                  <button
                    className="pagination-btn"
                    onClick={() => setProcessedPage(prev => Math.min(processedTotalPages, prev + 1))}
                    disabled={processedPage === processedTotalPages}
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          )}

          {canViewAccessRequests ? (
            <div className="approvals-section">
              <div className="section-header">
                <h3 className="section-title">Access Requests</h3>
                <span className="approval-stats">
                  <span className="stat"><strong>{pendingAccessRequests.length}</strong> Pending</span>
                  <span className="stat"><strong>{processedAccessRequests.length}</strong> Processed</span>
                </span>
              </div>

              {accessRequestsError ? <div className="no-approvals">{accessRequestsError}</div> : null}

              {pendingAccessRequests.length === 0 && processedAccessRequests.length === 0 ? (
                <div className="no-approvals">
                  <p>No exception-record access requests to review.</p>
                </div>
              ) : (
                <>
                  {pendingAccessRequests.length > 0 ? (
                    <div className="approvals-section">
                      <h3 className="section-title">Pending Access Reviews</h3>
                      <div className="approvals-list">
                        {pendingAccessRequests.map((request) => (
                          <div key={request.id} className="approval-card pending">
                            <div className="approval-header">
                              <div className="approval-content">
                                <div className="approval-title-row">
                                  <h4>{getAccessRequestSubjectLabel(request)}</h4>
                                  <span className="approval-requester">Requested by {getAccessRequestRequesterLabel(request)}</span>
                                  <span className="approval-type-badge">{getAccessRequestRoleLabel(request)}</span>
                                </div>
                                <div className="approval-meta">
                                  <span className="meta-item">
                                    <strong>Workspace:</strong> {request.workspaceId}
                                  </span>
                                  <span className="meta-item">
                                    <strong>Duration:</strong> {request.requestedDurationMinutes} min
                                  </span>
                                  <span className="meta-item">
                                    <strong>Requested:</strong>{' '}
                                    {new Date(request.requestedAt).toLocaleDateString()}
                                  </span>
                                </div>
                              </div>
                              <button
                                className="expand-btn"
                                onClick={() => setExpandedApprovalId(expandedApprovalId === request.id ? null : request.id)}
                              >
                                {expandedApprovalId === request.id ? '▼' : '▶'}
                              </button>
                            </div>

                            {expandedApprovalId === request.id && (
                              <div className="approval-details">
                                <div className="rule-info">
                                  <p>
                                    <strong>Reason:</strong> {request.comments || 'No reason provided.'}
                                  </p>
                                  <p>
                                    <strong>Role requested:</strong> {getAccessRequestRoleLabel(request)}
                                  </p>
                                  <p>
                                    <strong>Expires:</strong> {request.expiresAt ? new Date(request.expiresAt).toLocaleString() : 'Pending review'}
                                  </p>
                                </div>

                                <div className="approval-actions">
                                  <div className="comment-section">
                                    <AppTextarea
                                      id={`access-review-comment-${request.id}`}
                                      label="Decision Comment (optional)"
                                      placeholder="Add review comments..."
                                      value={accessRequestComments[request.id] || ''}
                                      onChange={(event) => setAccessRequestComments((prev) => ({ ...prev, [request.id]: event.target.value }))}
                                    />
                                  </div>

                                  <div className="action-buttons">
                                    <Button
                                      className="approval-action-btn"
                                      onClick={() => void handleRejectAccessRequest(request.id)}
                                      disabled={accessRequestSubmittingId === request.id}
                                      variant="primary-destructive"
                                    >
                                      <AppIcon slot="icon" name="times" />
                                      Reject
                                    </Button>
                                    <Button
                                      className="approval-action-btn"
                                      onClick={() => void handleApproveAccessRequest(request.id)}
                                      disabled={accessRequestSubmittingId === request.id}
                                      variant="primary-default"
                                    >
                                      <AppIcon slot="icon" name="check" />
                                      {accessRequestSubmittingId === request.id ? 'Reviewing...' : 'Approve'}
                                    </Button>
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                                      <AppIcon slot="icon" name="check" />
                    <div className="approvals-section">
                      <h3 className="section-title">Access Request History</h3>
                      <div className="approvals-list">
                        {processedAccessRequests.map((request) => (
                          <div key={request.id} className={`approval-card processed ${request.status}`}>
                            <div className="approval-header">
                              <div className="approval-content">
                                <div className="approval-title-row">
                                  <h4>{getAccessRequestSubjectLabel(request)}</h4>
                                  <span className="approval-requester">Requested by {getAccessRequestRequesterLabel(request)}</span>
                                  <span className="approval-type-badge">{getAccessRequestRoleLabel(request)}</span>
                                </div>
                                <div className="approval-meta">
                                  <span className="meta-item">
                                    <strong>Status:</strong>{' '}
                                    <span className={`badge ${request.status}`}>{getAccessRequestStatusLabel(request.status).toUpperCase()}</span>
                                  </span>
                                  <span className="meta-item">
                                    <strong>Workspace:</strong> {request.workspaceId}
                                  </span>
                                  <span className="meta-item">
                                    <strong>Reviewed by:</strong> {request.reviewedBy || 'N/A'}
                                  </span>
                                  <span className="meta-item">
                                    <strong>Date:</strong>{' '}
                                    {new Date(request.reviewedAt || request.requestedAt).toLocaleDateString()}
                                  </span>
                                </div>
                              </div>
                              <button
                                className="expand-btn"
                                onClick={() => setExpandedApprovalId(expandedApprovalId === request.id ? null : request.id)}
                              >
                                {expandedApprovalId === request.id ? '▼' : '▶'}
                              </button>
                            </div>

                            {expandedApprovalId === request.id && (
                              <div className="approval-details">
                                <div className="rule-info">
                                  <p>
                                    <strong>Reason:</strong> {request.comments || 'No reason provided.'}
                                  </p>
                                  <p>
                                    <strong>Requested duration:</strong> {request.requestedDurationMinutes} min
                                  </p>
                                  <p>
                                    <strong>Expires:</strong> {request.expiresAt ? new Date(request.expiresAt).toLocaleString() : 'N/A'}
                                  </p>
                                </div>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </div>
            ) : null}
          </>
            )}
          </>
        )}
      </AppPageShell>
  )
}
