import { useMemo } from 'react'
import { Rule, RuleStatus } from '../../types/rules'

export interface RuleDerivedData {
  filteredRules: Rule[]
  pagedRules: Rule[]
  statusCounts: Record<RuleStatus | 'all', number>
  pageSize: number
  totalPages: number
}

interface UseRuleDerivedDataProps {
  workspaceRules: Rule[]
  canViewPendingApprovals?: boolean
  filterStatus: RuleStatus | 'all'
  sortBy: 'name' | 'created' | 'status'
  sortDirection: 'asc' | 'desc'
  currentPage: number
  itemsPerPageSetting: number
  maxListItems?: number
}

export const useRuleDerivedData = (props: UseRuleDerivedDataProps): RuleDerivedData => {
  const {
    workspaceRules,
    canViewPendingApprovals = true,
    filterStatus,
    sortBy,
    sortDirection,
    currentPage,
    itemsPerPageSetting,
    maxListItems,
  } = props

  const visibleRules = useMemo(() => {
    if (canViewPendingApprovals) {
      return workspaceRules
    }
    return workspaceRules.filter((rule) => rule.status !== 'pending-approval')
  }, [workspaceRules, canViewPendingApprovals])

  const filteredRules = useMemo(() => {
    const normalizedSortBy = String(sortBy || '').trim().toLowerCase()
    const direction = String(sortDirection || 'asc').trim().toLowerCase() === 'desc' ? -1 : 1
    const collator = new Intl.Collator(undefined, { sensitivity: 'base', numeric: true })

    let filtered = [...visibleRules]
    if (filterStatus !== 'all') {
      filtered = filtered.filter(r => r.status === filterStatus)
    }

    const getName = (rule: Rule): string => String(rule.name || '').trim()
    const getStatus = (rule: Rule): string => String(rule.status || 'draft').trim()
    const getCreated = (rule: Rule): number => {
      const raw = rule.createdAt || rule.updatedAt || ''
      const ts = raw ? new Date(raw).getTime() : 0
      return Number.isFinite(ts) ? ts : 0
    }

    return filtered.sort((a, b) => {
      switch (normalizedSortBy) {
        case 'created': {
          const primary = (getCreated(a) - getCreated(b)) * direction
          if (primary !== 0) return primary
          return collator.compare(getName(a), getName(b)) * direction
        }
        case 'status': {
          const primary = collator.compare(getStatus(a), getStatus(b)) * direction
          if (primary !== 0) return primary
          return collator.compare(getName(a), getName(b)) * direction
        }
        case 'name':
        default: {
          const primary = collator.compare(getName(a), getName(b)) * direction
          if (primary !== 0) return primary
          return collator.compare(String(a.id || ''), String(b.id || '')) * direction
        }
      }
    })
  }, [visibleRules, filterStatus, sortBy, sortDirection])

  const pageSize = useMemo(() => {
    const defaultLimit = itemsPerPageSetting || 10
    if (maxListItems && maxListItems > 0) {
      return Math.min(defaultLimit, maxListItems)
    }
    return defaultLimit
  }, [itemsPerPageSetting, maxListItems])

  const totalPages = useMemo(() => {
    return Math.max(1, Math.ceil(filteredRules.length / pageSize))
  }, [filteredRules.length, pageSize])

  const pagedRules = useMemo(() => {
    const startIndex = (currentPage - 1) * pageSize
    return filteredRules.slice(startIndex, startIndex + pageSize)
  }, [filteredRules, currentPage, pageSize])

  const statusCounts = useMemo(() => {
    const counts: Record<RuleStatus | 'all', number> = {
      all: visibleRules.length,
      draft: visibleRules.filter(r => r.status === 'draft').length,
      testing: visibleRules.filter(r => r.status === 'testing').length,
      tested: visibleRules.filter(r => r.status === 'tested').length,
      'pending-approval': visibleRules.filter(r => r.status === 'pending-approval').length,
      approved: visibleRules.filter(r => r.status === 'approved').length,
      activated: visibleRules.filter(r => r.status === 'activated').length,
      deactivated: visibleRules.filter(r => r.status === 'deactivated').length,
      rejected: visibleRules.filter(r => r.status === 'rejected').length,
    }
    return counts
  }, [visibleRules])

  return {
    filteredRules,
    pagedRules,
    statusCounts,
    pageSize,
    totalPages,
  }
}
