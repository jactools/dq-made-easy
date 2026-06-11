import React, { useState, useEffect } from 'react'
import { RuleVersion, RuleRollback } from '../types/rules'
import { useSettings } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { Button } from './Button'
import { AppIcon, type AppIconName } from './app-primitives'
import { RollbackHistory } from './RollbackHistory'
import './RuleVersionHistory.css'

interface RuleVersionHistoryProps {
  ruleId: string
  ruleName: string
  onVersionSelect: (version: RuleVersion) => void
  onCompareVersions: (v1: RuleVersion, v2: RuleVersion) => void
  onRollback: (targetVersion: RuleVersion) => void
  onCurrentVersionDetected?: (version: RuleVersion | null) => void
}

export const RuleVersionHistory: React.FC<RuleVersionHistoryProps> = ({
  ruleId,
  ruleName,
  onVersionSelect,
  onCompareVersions,
  onRollback,
  onCurrentVersionDetected,
}) => {
  const settings = useSettings()
  const apiBaseUrl = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken())
  
  const [versions, setVersions] = useState<RuleVersion[]>([])
  const [rollbacks, setRollbacks] = useState<RuleRollback[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedVersion1, setSelectedVersion1] = useState<RuleVersion | null>(null)
  const [selectedVersion2, setSelectedVersion2] = useState<RuleVersion | null>(null)
  const [compareMode, setCompareMode] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [changeTypeFilter, setChangeTypeFilter] = useState('all')
  const [userFilter, setUserFilter] = useState('all')
  const [dateRangeFilter, setDateRangeFilter] = useState('all')
  const [customStartDate, setCustomStartDate] = useState('')
  const [customEndDate, setCustomEndDate] = useState('')
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc')
  const [restoredCompareSelection, setRestoredCompareSelection] = useState<{
    selectedVersion1Id?: string
    selectedVersion2Id?: string
  } | null>(null)
  const [editingTagsVersionId, setEditingTagsVersionId] = useState<string | null>(null)
  const [newTagInput, setNewTagInput] = useState<Record<string, string>>({})
  const [tooltipVersionId, setTooltipVersionId] = useState<string | null>(null)
  const [expandedVersionIds, setExpandedVersionIds] = useState<Set<string>>(new Set())
  const [rollbackFilter, setRollbackFilter] = useState<'all' | 'rolled-back' | 'not-rolled-back'>('all')
  const [bulkSelectedVersionIds, setBulkSelectedVersionIds] = useState<Set<string>>(new Set())
  const [bulkTagInput, setBulkTagInput] = useState('')

  const storageKey = `ruleVersionHistoryFilters:${ruleId}`
  const compareStorageKey = `ruleVersionHistoryCompare:${ruleId}`

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

  useEffect(() => {
    try {
      const savedFilters = sessionStorage.getItem(storageKey)
      const savedCompareState = sessionStorage.getItem(compareStorageKey)

      if (!savedFilters) {
        setSearchQuery('')
        setChangeTypeFilter('all')
        setUserFilter('all')
        setDateRangeFilter('all')
        setCustomStartDate('')
        setCustomEndDate('')
        setSortOrder('desc')
        setRollbackFilter('all')
      } else {
        const parsed = JSON.parse(savedFilters) as {
          searchQuery?: string
          changeTypeFilter?: string
          userFilter?: string
          dateRangeFilter?: string
          customStartDate?: string
          customEndDate?: string
          sortOrder?: 'desc' | 'asc'
          rollbackFilter?: 'all' | 'rolled-back' | 'not-rolled-back'
        }

        setSearchQuery(parsed.searchQuery ?? '')
        setChangeTypeFilter(parsed.changeTypeFilter ?? 'all')
        setUserFilter(parsed.userFilter ?? 'all')
        setDateRangeFilter(parsed.dateRangeFilter ?? 'all')
        setCustomStartDate(parsed.customStartDate ?? '')
        setCustomEndDate(parsed.customEndDate ?? '')
        setSortOrder(parsed.sortOrder === 'asc' ? 'asc' : 'desc')
        setRollbackFilter((parsed.rollbackFilter ?? 'all') as 'all' | 'rolled-back' | 'not-rolled-back')
      }

      if (!savedCompareState) {
        setCompareMode(false)
        setSelectedVersion1(null)
        setSelectedVersion2(null)
        setRestoredCompareSelection(null)
      } else {
        const parsedCompareState = JSON.parse(savedCompareState) as {
          compareMode?: boolean
          selectedVersion1Id?: string
          selectedVersion2Id?: string
        }

        setCompareMode(Boolean(parsedCompareState.compareMode))
        setSelectedVersion1(null)
        setSelectedVersion2(null)
        setRestoredCompareSelection({
          selectedVersion1Id: parsedCompareState.selectedVersion1Id,
          selectedVersion2Id: parsedCompareState.selectedVersion2Id,
        })
      }
    } catch (err) {
      console.error('Failed to restore version history filters:', err)
    }

    fetchVersionHistory()
    fetchRollbackHistory()
  }, [apiBaseUrl, authToken, ruleId, storageKey, compareStorageKey])

  useEffect(() => {
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({
          searchQuery,
          changeTypeFilter,
          userFilter,
          dateRangeFilter,
          customStartDate,
          customEndDate,
          sortOrder,
          rollbackFilter,
        })
      )
    } catch (err) {
      console.error('Failed to persist version history filters:', err)
    }
  }, [
    storageKey,
    searchQuery,
    changeTypeFilter,
    userFilter,
    dateRangeFilter,
    customStartDate,
    customEndDate,
    sortOrder,
    rollbackFilter,
  ])

  useEffect(() => {
    if (!restoredCompareSelection) {
      return
    }

    const resolvedVersion1 = restoredCompareSelection.selectedVersion1Id
      ? versions.find(version => version.id === restoredCompareSelection.selectedVersion1Id) || null
      : null
    const resolvedVersion2 = restoredCompareSelection.selectedVersion2Id
      ? versions.find(version => version.id === restoredCompareSelection.selectedVersion2Id) || null
      : null

    setSelectedVersion1(resolvedVersion1)
    setSelectedVersion2(resolvedVersion2)
    setRestoredCompareSelection(null)
  }, [versions, restoredCompareSelection])

  useEffect(() => {
    try {
      sessionStorage.setItem(
        compareStorageKey,
        JSON.stringify({
          compareMode,
          selectedVersion1Id: selectedVersion1?.id,
          selectedVersion2Id: selectedVersion2?.id,
        })
      )
    } catch (err) {
      console.error('Failed to persist version compare state:', err)
    }
  }, [compareStorageKey, compareMode, selectedVersion1, selectedVersion2])

  const fetchVersionHistory = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${apiBaseUrl}/rules/${ruleId}/versions`, {
        headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
      })
      if (!response.ok) throw new Error('Failed to fetch version history')
      const data = await response.json()
      const resolvedVersions = data.versions || []
      setVersions(resolvedVersions)
      onCurrentVersionDetected?.(resolvedVersions[0] || null)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load versions')
    } finally {
      setLoading(false)
    }
  }

  const fetchRollbackHistory = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/rules/${ruleId}/versions/rollback-history`, {
        headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
      })
      if (!response.ok) throw new Error('Failed to fetch rollback history')
      const data = await response.json()
      setRollbacks(data.rollbacks || [])
    } catch (err) {
      console.error('Failed to load rollback history:', err)
      setRollbacks([])
    }
  }

  const handleVersionClick = (version: RuleVersion) => {
    if (compareMode) {
      if (!selectedVersion1) {
        setSelectedVersion1(version)
      } else if (!selectedVersion2 && version.id !== selectedVersion1.id) {
        setSelectedVersion2(version)
      }
    } else {
      onVersionSelect(version)
    }
  }

  const handleVersionItemKeyDown = (event: React.KeyboardEvent<HTMLDivElement>, version: RuleVersion) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      handleVersionClick(version)
    }
  }

  const handleCompare = () => {
    if (selectedVersion1 && selectedVersion2) {
      onCompareVersions(selectedVersion1, selectedVersion2)
      resetCompareMode()
    }
  }

  const handleCopyVersionId = (versionId: string) => {
    navigator.clipboard.writeText(versionId).then(() => {
      // Could add a toast notification here in the future
      console.log('Version ID copied to clipboard:', versionId)
    }).catch(err => {
      console.error('Failed to copy version ID:', err)
    })
  }

  const handleAddTag = (versionId: string) => {
    const tagValue = newTagInput[versionId]?.trim()
    if (!tagValue) return

    const updatedVersions = versions.map(v => {
      if (v.id === versionId) {
        return {
          ...v,
          tags: [...(v.tags || []), tagValue]
        }
      }
      return v
    })
    setVersions(updatedVersions)
    setNewTagInput({ ...newTagInput, [versionId]: '' })
  }

  const handleRemoveTag = (versionId: string, tagToRemove: string) => {
    const updatedVersions = versions.map(v => {
      if (v.id === versionId) {
        return {
          ...v,
          tags: v.tags?.filter(tag => tag !== tagToRemove) || []
        }
      }
      return v
    })
    setVersions(updatedVersions)
  }

  const handleToggleExpanded = (versionId: string) => {
    const newExpandedSet = new Set(expandedVersionIds)
    if (newExpandedSet.has(versionId)) {
      newExpandedSet.delete(versionId)
    } else {
      newExpandedSet.add(versionId)
    }
    setExpandedVersionIds(newExpandedSet)
  }

  const handleBulkSelectVersion = (versionId: string) => {
    const newBulkSet = new Set(bulkSelectedVersionIds)
    if (newBulkSet.has(versionId)) {
      newBulkSet.delete(versionId)
    } else {
      newBulkSet.add(versionId)
    }
    setBulkSelectedVersionIds(newBulkSet)
  }

  const handleSelectAllVersions = () => {
    setBulkSelectedVersionIds(new Set(filteredAndSortedVersions.map(v => v.id)))
  }

  const handleDeselectAllVersions = () => {
    setBulkSelectedVersionIds(new Set())
  }

  const handleBulkApplyTag = () => {
    const tagValue = bulkTagInput.trim()
    if (!tagValue || bulkSelectedVersionIds.size === 0) return

    const updatedVersions = versions.map(v => {
      if (bulkSelectedVersionIds.has(v.id)) {
        const existingTags = v.tags || []
        if (!existingTags.includes(tagValue)) {
          return {
            ...v,
            tags: [...existingTags, tagValue]
          }
        }
      }
      return v
    })
    setVersions(updatedVersions)
    setBulkTagInput('')
  }

  const clearCompareSelection = () => {
    setSelectedVersion1(null)
    setSelectedVersion2(null)
  }

  const removeComparedVersion = (versionId: string) => {
    if (selectedVersion1?.id === versionId) {
      if (selectedVersion2) {
        setSelectedVersion1(selectedVersion2)
        setSelectedVersion2(null)
        return
      }
      setSelectedVersion1(null)
      return
    }

    if (selectedVersion2?.id === versionId) {
      setSelectedVersion2(null)
    }
  }

  const resetCompareMode = () => {
    setCompareMode(false)
    setSelectedVersion1(null)
    setSelectedVersion2(null)
  }

  const toggleCompareMode = () => {
    if (compareMode) {
      resetCompareMode()
    } else {
      setCompareMode(true)
    }
  }

  useEffect(() => {
    if (!compareMode) {
      return
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        resetCompareMode()
        return
      }

      if (
        event.key === 'Enter' &&
        selectedVersion1 &&
        selectedVersion2
      ) {
        const target = event.target as HTMLElement | null
        const tagName = target?.tagName
        if (tagName === 'INPUT' || tagName === 'TEXTAREA' || tagName === 'SELECT' || tagName === 'BUTTON') {
          return
        }

        event.preventDefault()
        handleCompare()
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [compareMode, selectedVersion1, selectedVersion2])

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const getChangeTypeIconName = (changeType: string): AppIconName => {
    switch (changeType) {
      case 'created':
        return 'plus'
      case 'expression_updated':
        return 'pencil'
      case 'metadata_updated':
        return 'info-circle'
      case 'status_changed':
        return 'sliders'
      case 'rollback':
        return 'arrow-curve-left'
      case 'approval_applied':
        return 'check-circle'
      case 'test_proof_attached':
        return 'paperclip'
      default:
        return 'document'
    }
  }

  const getChangeTypeLabel = (changeType: string) => {
    return changeType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  }

  const isVersionInRollback = (versionId: string) => {
    return rollbacks.some(rb => rb.toVersionId === versionId)
  }

  const availableChangeTypes = Array.from(new Set(versions.map(version => version.changeType)))
  const availableUsers = Array.from(new Set(versions.map(version => version.createdBy))).sort((a, b) =>
    a.localeCompare(b)
  )

  const isWithinDateRange = (createdAt: string) => {
    if (dateRangeFilter === 'all') return true

    const versionDate = new Date(createdAt)

    if (dateRangeFilter === 'custom') {
      if (customStartDate) {
        const startDate = new Date(customStartDate)
        startDate.setHours(0, 0, 0, 0)
        if (versionDate < startDate) return false
      }

      if (customEndDate) {
        const endDate = new Date(customEndDate)
        endDate.setHours(23, 59, 59, 999)
        if (versionDate > endDate) return false
      }

      return true
    }

    const now = new Date()
    const days = Number(dateRangeFilter)
    if (Number.isNaN(days)) return true
    const cutoffDate = new Date(now)
    cutoffDate.setDate(now.getDate() - days)

    return versionDate >= cutoffDate
  }

  const getDateRangeLabel = () => {
    switch (dateRangeFilter) {
      case '7':
        return 'Last 7 days'
      case '30':
        return 'Last 30 days'
      case '90':
        return 'Last 90 days'
      case 'custom': {
        if (customStartDate && customEndDate) {
          return `From ${customStartDate} to ${customEndDate}`
        }
        if (customStartDate) {
          return `From ${customStartDate}`
        }
        if (customEndDate) {
          return `Until ${customEndDate}`
        }
        return 'Custom range'
      }
      default:
        return 'All dates'
    }
  }

  const hasActiveFilters =
    searchQuery.trim().length > 0 ||
    changeTypeFilter !== 'all' ||
    userFilter !== 'all' ||
    dateRangeFilter !== 'all' ||
    sortOrder !== 'desc' ||
    rollbackFilter !== 'all'

  const clearFilters = () => {
    setSearchQuery('')
    setChangeTypeFilter('all')
    setUserFilter('all')
    setDateRangeFilter('all')
    setCustomStartDate('')
    setCustomEndDate('')
    setSortOrder('desc')
    setRollbackFilter('all')
  }

  const filteredVersions = versions.filter(version => {
    const changeTypeMatches = changeTypeFilter === 'all' || version.changeType === changeTypeFilter
    const userMatches = userFilter === 'all' || version.createdBy === userFilter
    const dateMatches = isWithinDateRange(version.createdAt)
    const normalizedQuery = searchQuery.trim().toLowerCase()
    const normalizedVersionQuery = normalizedQuery.startsWith('v')
      ? normalizedQuery.slice(1)
      : normalizedQuery

    const wasRolledBack = isVersionInRollback(version.id)
    const rollbackMatches =
      rollbackFilter === 'all' ||
      (rollbackFilter === 'rolled-back' && wasRolledBack) ||
      (rollbackFilter === 'not-rolled-back' && !wasRolledBack)

    const baseFilterMatches = changeTypeMatches && userMatches && dateMatches && rollbackMatches

    if (!normalizedQuery) {
      return baseFilterMatches
    }

    const queryMatches =
      version.createdBy.toLowerCase().includes(normalizedQuery) ||
      version.changeDescription?.toLowerCase().includes(normalizedQuery) ||
      version.changeType.toLowerCase().includes(normalizedQuery) ||
      String(version.versionNumber).includes(normalizedVersionQuery) ||
      version.tags?.some(tag => tag.toLowerCase().includes(normalizedQuery))

    return baseFilterMatches && queryMatches
  })

  const filteredAndSortedVersions = [...filteredVersions].sort((a, b) => {
    const left = new Date(a.createdAt).getTime()
    const right = new Date(b.createdAt).getTime()
    return sortOrder === 'desc' ? right - left : left - right
  })

  if (loading) {
    return (
      <div className="version-history-loading">
        <div className="spinner"></div>
        <p>Loading version history...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="version-history-error">
        <p>❌ {error}</p>
        <Button variant="secondary" onClick={fetchVersionHistory}>Retry</Button>
      </div>
    )
  }

  return (
    <div className="version-history-container">
      <div className="version-history-header">
        <div>
          <h3>Version History</h3>
          <div className="version-header-info">
            <p className="version-count">
              {filteredVersions.length} of {versions.length} version{versions.length !== 1 ? 's' : ''}
            </p>
            {compareMode && selectedVersion1 && (
              <div className="compare-selected-indicator">
                <AppIcon name="check-circle" />
                {selectedVersion2 ? 'Ready to compare' : 'Comparing...'}
              </div>
            )}
          </div>
        </div>
        <div className="version-history-actions">
          {compareMode && (
            <>
              <span className="compare-instructions">
                Select 2 versions to compare
                {selectedVersion1 && ` (1/2 selected)`}
                {selectedVersion2 && ` (2/2 selected)`}
              </span>
              <Button
                variant="secondary"
                onClick={clearCompareSelection}
                disabled={!selectedVersion1 && !selectedVersion2}
              >
                Clear Selection
              </Button>
              <Button
                variant="primary"
                onClick={handleCompare} 
                disabled={!selectedVersion1 || !selectedVersion2}
              >
                Compare
              </Button>
            </>
          )}
          <Button variant="secondary" onClick={toggleCompareMode}>
            {compareMode ? 'Cancel Compare' : 'Compare Versions'}
          </Button>
        </div>
      </div>

      {compareMode && (selectedVersion1 || selectedVersion2) && (
        <div className="compare-selection-summary">
          <span className="compare-selection-label">Selected:</span>
          {selectedVersion1 && (
            <button
              type="button"
              className="compare-selection-chip"
              onClick={() => removeComparedVersion(selectedVersion1.id)}
            >
              v{selectedVersion1.versionNumber} ×
            </button>
          )}
          {selectedVersion2 && (
            <button
              type="button"
              className="compare-selection-chip"
              onClick={() => removeComparedVersion(selectedVersion2.id)}
            >
              v{selectedVersion2.versionNumber} ×
            </button>
          )}
        </div>
      )}

      {bulkSelectedVersionIds.size > 0 && (
        <div className="bulk-operations-toolbar">
          <span className="bulk-selection-info">
            {bulkSelectedVersionIds.size} version{bulkSelectedVersionIds.size !== 1 ? 's' : ''} selected
          </span>
          <div className="bulk-operations-controls">
            <input
              type="text"
              className="bulk-tag-input"
              placeholder="Add tag to selected..."
              value={bulkTagInput}
              onChange={(e) => setBulkTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  handleBulkApplyTag()
                }
              }}
              aria-label="Bulk tag input"
            />
            <Button
              variant="secondary"
              onClick={handleBulkApplyTag}
              disabled={!bulkTagInput.trim()}
            >
              Apply Tag
            </Button>
            <Button
              variant="tertiary"
              onClick={handleDeselectAllVersions}
            >
              Clear Selection
            </Button>
          </div>
        </div>
      )}

      <div className="version-history-filters">
        <input
          placeholder="Search by version, change type, user, description, or tag..."
          value={searchQuery}
          onInput={(e: any) => setSearchQuery(e.target.value)}
        />
        <div className="filter-group">
          <label className="filter-label">Change Type</label>
          <select
            value={changeTypeFilter}
            onChange={(e: any) => setChangeTypeFilter(e.target.value)}
            aria-label="Filter by change type"
          >
            <option value="all">All change types</option>
            {availableChangeTypes.map(changeType => (
              <option key={changeType} value={changeType}>
                {getChangeTypeLabel(changeType)}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Modified By</label>
          <select
            value={userFilter}
            onChange={(e: any) => setUserFilter(e.target.value)}
            aria-label="Filter by user"
          >
            <option value="all">All users</option>
            {availableUsers.map(user => (
              <option key={user} value={user}>
                {user}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Date Range</label>
          <select
            value={dateRangeFilter}
            onChange={(e: any) => {
              const value = e.target.value
              setDateRangeFilter(value)
              if (value !== 'custom') {
                setCustomStartDate('')
                setCustomEndDate('')
              }
            }}
            aria-label="Filter by date range"
          >
            <option value="all">All dates</option>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
            <option value="custom">Custom range</option>
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Sort Order</label>
          <select
            value={sortOrder}
            onChange={(e: any) => setSortOrder(e.target.value as 'desc' | 'asc')}
            aria-label="Sort versions"
          >
            <option value="desc">Newest first</option>
            <option value="asc">Oldest first</option>
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Rollback Status</label>
          <select
            value={rollbackFilter}
            onChange={(e: any) => setRollbackFilter(e.target.value as 'all' | 'rolled-back' | 'not-rolled-back')}
            aria-label="Filter by rollback status"
          >
            <option value="all">All versions</option>
            <option value="rolled-back">Rolled back to</option>
            <option value="not-rolled-back">Not rolled back</option>
          </select>
        </div>
        {dateRangeFilter === 'custom' && (
          <div className="custom-date-range">
            <input
              type="date"
              value={customStartDate}
              max={customEndDate || undefined}
              onInput={(e: any) => setCustomStartDate(e.target.value)}
              aria-label="Custom start date"
            />
            <span className="custom-date-separator">to</span>
            <input
              type="date"
              value={customEndDate}
              min={customStartDate || undefined}
              onInput={(e: any) => setCustomEndDate(e.target.value)}
              aria-label="Custom end date"
            />
          </div>
        )}
        {hasActiveFilters && (
          <Button
            variant="tertiary"
            onClick={clearFilters}
          >
            Clear filters
          </Button>
        )}
      </div>

      {hasActiveFilters && (
        <div className="active-filter-chips">
          {searchQuery.trim().length > 0 && (
            <Button
              variant="tertiary"
              onClick={() => setSearchQuery('')}
            >
              Search: {searchQuery.trim()} ×
            </Button>
          )}
          {changeTypeFilter !== 'all' && (
            <Button
              variant="tertiary"
              onClick={() => setChangeTypeFilter('all')}
            >
              Type: {getChangeTypeLabel(changeTypeFilter)} ×
            </Button>
          )}
          {userFilter !== 'all' && (
            <Button
              variant="tertiary"
              onClick={() => setUserFilter('all')}
            >
              User: {userFilter} ×
            </Button>
          )}
          {dateRangeFilter !== 'all' && (
            <Button
              variant="tertiary"
              onClick={() => {
                setDateRangeFilter('all')
                setCustomStartDate('')
                setCustomEndDate('')
              }}
            >
              Date: {getDateRangeLabel()} ×
            </Button>
          )}
          {sortOrder !== 'desc' && (
            <Button
              variant="tertiary"
              onClick={() => setSortOrder('desc')}
            >
              Sort: Oldest first ×
            </Button>
          )}
          {rollbackFilter !== 'all' && (
            <Button
              variant="tertiary"
              onClick={() => setRollbackFilter('all')}
            >
              {rollbackFilter === 'rolled-back' ? 'Rolled back only' : 'Not rolled back only'} ×
            </Button>
          )}
        </div>
      )}

      {filteredAndSortedVersions.length > 0 && (
        <div className="bulk-selection-controls">
          <Button
            variant="tertiary"
            onClick={handleSelectAllVersions}
          >
            Select All Filtered
          </Button>
          <Button
            variant="tertiary"
            onClick={handleDeselectAllVersions}
            disabled={bulkSelectedVersionIds.size === 0}
          >
            Deselect All
          </Button>
        </div>
      )}

      <div className="version-timeline">
        {filteredAndSortedVersions.length === 0 && (
          <div className="version-history-empty">
            <p>No versions match the current filter.</p>
            {hasActiveFilters && (
              <Button
                variant="secondary"
                onClick={clearFilters}
              >
                Reset filters
              </Button>
            )}
          </div>
        )}

        {filteredAndSortedVersions.map((version, index) => {
          const isCurrentVersion = versions[0]?.id === version.id
          const wasRolledBackTo = isVersionInRollback(version.id)
          const isSelected = 
            (compareMode && selectedVersion1?.id === version.id) ||
            (compareMode && selectedVersion2?.id === version.id)

          return (
            <div
              key={version.id}
              className={`version-item ${isCurrentVersion ? 'current' : ''} ${wasRolledBackTo ? 'rolled-back' : ''} ${isSelected ? 'selected' : ''} ${compareMode ? 'compare-mode' : ''}`}
              onClick={() => handleVersionClick(version)}
              onKeyDown={event => handleVersionItemKeyDown(event, version)}
              onMouseEnter={() => setTooltipVersionId(version.id)}
              onMouseLeave={() => setTooltipVersionId(null)}
              role="button"
              tabIndex={0}
              aria-current={isCurrentVersion ? 'true' : undefined}
              aria-pressed={compareMode ? isSelected : undefined}
              aria-label={`Version ${version.versionNumber}${isCurrentVersion ? ', current version' : ''}${wasRolledBackTo ? ', rollback target' : ''}`}
            >
              <div className="version-marker">
                <div className="version-dot"></div>
                {index < filteredAndSortedVersions.length - 1 && <div className="version-line"></div>}
              </div>

              <input
                type="checkbox"
                className="version-checkbox"
                checked={bulkSelectedVersionIds.has(version.id)}
                onChange={(e) => {
                  e.stopPropagation()
                  handleBulkSelectVersion(version.id)
                }}
                aria-label={`Select version ${version.versionNumber}`}
              />
              
              <div className="version-content">
                <div className="version-header-row">
                  <div className="version-number-badge">
                    v{version.versionNumber}
                    {isCurrentVersion && <span className="current-badge">Current</span>}
                    {wasRolledBackTo && <span className="rollback-badge">Rolled Back To</span>}
                  </div>
                  <span className="version-date">{formatDate(version.createdAt)}</span>
                  <Button
                    variant="tertiary"
                    aria-label="Copy version ID"
                    onClick={(e: any) => {
                      e.stopPropagation()
                      handleCopyVersionId(version.id)
                    }}
                  >
                    <AppIcon name="copy" />
                  </Button>
                  <Button
                    variant="tertiary"
                    aria-label="Show version details"
                    onClick={(e: any) => {
                      e.stopPropagation()
                      setTooltipVersionId(version.id === tooltipVersionId ? null : version.id)
                    }}
                  >
                    <AppIcon name="info-circle" />
                  </Button>
                  <Button
                    variant="tertiary"
                    aria-label={expandedVersionIds.has(version.id) ? 'Collapse details' : 'Expand details'}
                    onClick={(e: any) => {
                      e.stopPropagation()
                      handleToggleExpanded(version.id)
                    }}
                  >
                    <AppIcon name={expandedVersionIds.has(version.id) ? 'times' : 'plus'} />
                  </Button>
                </div>

                <div className="version-change-info">
                  <AppIcon name={getChangeTypeIconName(version.changeType)} />
                  <span className="change-type">{getChangeTypeLabel(version.changeType)}</span>
                  {version.changeDescription && (
                    <span className="change-description">— {version.changeDescription}</span>
                  )}
                </div>

                <div className="version-meta">
                  <span className="version-author">By {version.createdBy}</span>
                  {version.validationStatus && (
                    <span className="version-author">
                      Validated by {version.validatedBy || version.validatedByUserId || 'unknown'}
                      {version.validatedAt ? ` on ${formatDate(version.validatedAt)}` : ''}
                      {version.validationStatus !== 'valid' ? ` (${version.validationStatus})` : ''}
                    </span>
                  )}
                  <div className="version-tags-container">
                    {version.tags && version.tags.length > 0 && (
                      <div className="version-tags">
                        {version.tags.map(tag => (
                          <div key={tag} className="version-tag-item">
                            <span className="version-tag">{tag}</span>
                            <Button
                              variant="tertiary"
                              aria-label="Remove tag"
                              onClick={(e: any) => {
                                e.stopPropagation()
                                handleRemoveTag(version.id, tag)
                              }}
                            >
                              <AppIcon name="times" />
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}
                    {editingTagsVersionId === version.id && (
                      <div className="add-tag-input-group">
                        <input
                          type="text"
                          className="add-tag-input"
                          placeholder="Add new tag..."
                          value={newTagInput[version.id] || ''}
                          onChange={(e) => setNewTagInput({ ...newTagInput, [version.id]: e.target.value })}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.stopPropagation()
                              handleAddTag(version.id)
                            }
                          }}
                        />
                        <Button
                          variant="secondary"
                          onClick={() => handleAddTag(version.id)}
                        >
                          Add
                        </Button>
                        <Button
                          variant="tertiary"
                          onClick={() => setEditingTagsVersionId(null)}
                        >
                          Done
                        </Button>
                      </div>
                    )}
                    {editingTagsVersionId !== version.id && (
                      <Button
                        variant="tertiary"
                        aria-label="Edit tags"
                        onClick={(e: any) => {
                          e.stopPropagation()
                          setEditingTagsVersionId(version.id)
                        }}
                      >
                        <AppIcon name="plus" />
                      </Button>
                    )}
                  </div>
                </div>

                {version.markedForRollback && (
                  <div className="rollback-warning">
                    ⚠️ Marked for rollback
                  </div>
                )}

                {!isCurrentVersion && !compareMode && (
                  <div className="version-actions">
                    <Button
                      variant="secondary"
                      onClick={() => onVersionSelect(version)}
                    >
                      View Details
                    </Button>
                    <Button
                      variant="primary"
                      onClick={() => onRollback(version)}
                    >
                      Rollback to This Version
                    </Button>
                  </div>
                )}
              </div>

              {tooltipVersionId === version.id && (
                <div className="version-tooltip">
                  <div className="tooltip-header">
                    <strong>Version {version.versionNumber} Details</strong>
                  </div>
                  <div className="tooltip-content">
                    <div className="tooltip-row">
                      <span className="tooltip-label">Created:</span>
                      <span className="tooltip-value">{formatDate(version.createdAt)}</span>
                    </div>
                    <div className="tooltip-row">
                      <span className="tooltip-label">Change Type:</span>
                      <span className="tooltip-value">{getChangeTypeLabel(version.changeType)}</span>
                    </div>
                    <div className="tooltip-row">
                      <span className="tooltip-label">Author:</span>
                      <span className="tooltip-value">{version.createdBy}</span>
                    </div>
                    {version.changeDescription && (
                      <div className="tooltip-row">
                        <span className="tooltip-label">Description:</span>
                        <span className="tooltip-value">{version.changeDescription}</span>
                      </div>
                    )}
                    {version.tags && version.tags.length > 0 && (
                      <div className="tooltip-row">
                        <span className="tooltip-label">Tags:</span>
                        <div className="tooltip-tags">
                          {version.tags.map(tag => (
                            <span key={tag} className="tooltip-tag">{tag}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {expandedVersionIds.has(version.id) && (
                <div className="version-expanded-details">
                  <div className="expanded-section">
                    <h4 className="expanded-section-title">Version Information</h4>
                    <div className="expanded-info-grid">
                      <div className="expanded-info-item">
                        <span className="expanded-label">Version Number:</span>
                        <span className="expanded-value">v{version.versionNumber}</span>
                      </div>
                      <div className="expanded-info-item">
                        <span className="expanded-label">Created:</span>
                        <span className="expanded-value">{formatDate(version.createdAt)}</span>
                      </div>
                      <div className="expanded-info-item">
                        <span className="expanded-label">Author:</span>
                        <span className="expanded-value">{version.createdBy}</span>
                      </div>
                      <div className="expanded-info-item">
                        <span className="expanded-label">Change Type:</span>
                        <span className="expanded-value">{getChangeTypeLabel(version.changeType)}</span>
                      </div>
                    </div>
                  </div>
                  
                  {version.changeDescription && (
                    <div className="expanded-section">
                      <h4 className="expanded-section-title">Description</h4>
                      <p className="expanded-description">{version.changeDescription}</p>
                    </div>
                  )}
                  
                  {version.tags && version.tags.length > 0 && (
                    <div className="expanded-section">
                      <h4 className="expanded-section-title">Tags</h4>
                      <div className="expanded-tags">
                        {version.tags.map(tag => (
                          <span key={tag} className="expanded-tag">{tag}</span>
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

      <RollbackHistory rollbacks={rollbacks} versions={versions} />
    </div>
  )
}
