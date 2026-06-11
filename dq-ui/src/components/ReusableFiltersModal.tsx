import React, { useEffect, useMemo, useState } from 'react'
import { AppBanner, AppInput, AppTextarea } from './app-primitives'
import { PrimaryButton, SecondaryButton, Button } from './Button'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import { useUnsavedChangesConfirmation } from '../hooks/useUnsavedChangesConfirmation'
import { AppModal } from './app-primitives'
import { useSettings } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { createSupportReferenceId, formatSupportReferenceId } from '../utils/supportReference'
import { DEFAULT_SEARCH_MINIMUM_LENGTH, committedSearchValue } from '../utils/listFilterState'
import './ReusableFiltersModal.css'

interface ReusableFilterItem {
  id: string
  name: string
  description?: string
  filter_expression?: string
  expression?: string
  workspace?: string
  active?: boolean
}

interface ReusableFiltersModalProps {
  isOpen: boolean
  onClose: () => void
  workspaceId?: string
  ruleName?: string
  currentFilterIds?: string[]
  onAssignToRule?: (filterIds: string[]) => Promise<void>
  readOnly?: boolean
}

const validateFilterExpression = (rawExpression: string): string | null => {
  const expression = rawExpression.trim()
  if (!expression) {
    return 'Filter expression is required'
  }

  if (expression.includes(';')) {
    return 'Do not use semicolons in filter expressions'
  }

  if (expression.includes('--') || expression.includes('/*') || expression.includes('*/')) {
    return 'Comments are not allowed in filter expressions'
  }

  let parenDepth = 0
  let inSingleQuote = false
  let inDoubleQuote = false

  for (let i = 0; i < expression.length; i += 1) {
    const current = expression[i]
    const next = expression[i + 1]

    if (inSingleQuote) {
      if (current === "'" && next === "'") {
        i += 1
        continue
      }
      if (current === "'") {
        inSingleQuote = false
      }
      continue
    }

    if (inDoubleQuote) {
      if (current === '"' && next === '"') {
        i += 1
        continue
      }
      if (current === '"') {
        inDoubleQuote = false
      }
      continue
    }

    if (current === "'") {
      inSingleQuote = true
      continue
    }

    if (current === '"') {
      inDoubleQuote = true
      continue
    }

    if (current === '(') {
      parenDepth += 1
      continue
    }

    if (current === ')') {
      parenDepth -= 1
      if (parenDepth < 0) {
        return 'Unbalanced parentheses: found a closing parenthesis without matching opening parenthesis'
      }
    }
  }

  if (inSingleQuote) {
    return 'Unclosed single quote in filter expression'
  }

  if (inDoubleQuote) {
    return 'Unclosed double quote in filter expression'
  }

  if (parenDepth !== 0) {
    return 'Unbalanced parentheses in filter expression'
  }

  if (/(^|\()\s*(AND|OR)\b/i.test(expression)) {
    return 'Expression cannot start with AND/OR'
  }

  if (/\b(AND|OR)\s*(\)|$)/i.test(expression)) {
    return 'Expression cannot end with AND/OR'
  }

  if (/\b(AND|OR)\s+(AND|OR)\b/i.test(expression)) {
    return 'Consecutive logical operators detected'
  }

  return null
}

export const ReusableFiltersModal: React.FC<ReusableFiltersModalProps> = ({
  isOpen,
  onClose,
  workspaceId,
  ruleName,
  currentFilterIds,
  onAssignToRule,
  readOnly = false,
}) => {
  const settings = useSettings()
  const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)

  const [filters, setFilters] = useState<ReusableFilterItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [expression, setExpression] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [selectedFilterIds, setSelectedFilterIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const errorReferenceId = useMemo(() => (error ? createSupportReferenceId() : null), [error])

  const canAssign = typeof onAssignToRule === 'function' && !readOnly
  const showAssignmentControls = canAssign
  const reusableFilterSearchQuery = useMemo(
    () => committedSearchValue(searchInput, DEFAULT_SEARCH_MINIMUM_LENGTH),
    [searchInput],
  )

  // Track if form has been modified
  const initialFilterIds = useMemo(() => currentFilterIds || [], [currentFilterIds])
  
  const hasChanges = useMemo(() => {
    if (readOnly) return false
    // Check if selected filters changed (for assignment mode)
    if (JSON.stringify(selectedFilterIds.sort()) !== JSON.stringify(initialFilterIds.sort())) return true
    // Check if creating new filter (name, description, or expression filled)
    if (name.trim().length > 0 || description.trim().length > 0 || expression.trim().length > 0) return true
    return false
  }, [readOnly, selectedFilterIds, initialFilterIds, name, description, expression])

  // Use reusable unsaved changes confirmation hook
  const {
    showConfirmation,
    handleCloseWithConfirmation,
    handleConfirmClose,
    handleCancelConfirmation,
  } = useUnsavedChangesConfirmation({
    isOpen,
    hasChanges,
    onClose,
  })

  const getFieldValue = (event: any): string => {
    const value = event?.detail?.value ?? event?.target?.value ?? event?.currentTarget?.value ?? ''
    return typeof value === 'string' ? value : ''
  }

  const authHeaders = useMemo(() => {
    const token = getAuthToken()
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
  }, [])

  const expressionSyntaxError = useMemo(() => {
    if (!expression.trim()) return null
    return validateFilterExpression(expression)
  }, [expression])
  const expressionSyntaxErrorReferenceId = useMemo(
    () => (expressionSyntaxError ? createSupportReferenceId() : null),
    [expressionSyntaxError]
  )

  const loadFilters = async () => {
    if (!isOpen) return
    if (!getAuthToken()) {
      setFilters([])
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      const queryParams = new URLSearchParams()
      if (workspaceId) {
        queryParams.set('workspace', workspaceId)
      }
      if (reusableFilterSearchQuery) {
        queryParams.set('q', reusableFilterSearchQuery)
      }
      const query = queryParams.toString() ? `?${queryParams.toString()}` : ''
      const response = await fetch(`${apiBase}/reusable-filters${query}`, {
        headers: authHeaders,
      })

      if (!response.ok) {
        throw new Error('Failed to load reusable filters')
      }

      const body = await response.json()
      setFilters(Array.isArray(body) ? body : [])
    } catch (err: any) {
      setError(err.message || 'Failed to load reusable filters')
      setFilters([])
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!isOpen) return
    setSelectedFilterIds(Array.isArray(currentFilterIds) ? currentFilterIds : [])
    loadFilters()
  }, [isOpen, workspaceId, currentFilterIds, reusableFilterSearchQuery])

  const selectedFilters = useMemo(() => {
    if (!Array.isArray(currentFilterIds) || currentFilterIds.length === 0) return []
    return currentFilterIds
      .map((filterId) => filters.find((filter) => filter.id === filterId))
      .filter((filter): filter is ReusableFilterItem => Boolean(filter))
  }, [currentFilterIds, filters])

  const handleCreateFilter = async () => {
    if (!name.trim() || !expression.trim()) {
      setError('Name and expression are required')
      return
    }

    if (expressionSyntaxError) {
      setError(expressionSyntaxError)
      return
    }

    setIsSaving(true)
    setError(null)
    try {
      const response = await fetch(`${apiBase}/reusable-filters`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim(),
          expression: expression.trim(),
          workspace: workspaceId || 'default',
          active: true,
        }),
      })

      if (!response.ok) {
        const message = await response.text()
        throw new Error(message || 'Failed to create reusable filter')
      }

      setName('')
      setDescription('')
      setExpression('')
      await loadFilters()
    } catch (err: any) {
      setError(err.message || 'Failed to create reusable filter')
    } finally {
      setIsSaving(false)
    }
  }

  const handleDeleteFilter = async (filterId: string) => {
    if (!window.confirm('Delete this reusable filter?')) return

    setIsSaving(true)
    setError(null)
    try {
      const response = await fetch(`${apiBase}/reusable-filters/${encodeURIComponent(filterId)}`, {
        method: 'DELETE',
        headers: authHeaders,
      })

      if (!response.ok) {
        const message = await response.text()
        throw new Error(message || 'Failed to delete reusable filter')
      }

      if (selectedFilterIds.includes(filterId)) {
        setSelectedFilterIds(prev => prev.filter(id => id !== filterId))
      }

      await loadFilters()
    } catch (err: any) {
      setError(err.message || 'Failed to delete reusable filter')
    } finally {
      setIsSaving(false)
    }
  }

  const handleApplyFilter = async () => {
    if (!onAssignToRule) return
    setIsSaving(true)
    setError(null)
    try {
      await onAssignToRule(selectedFilterIds)
      onClose()
    } catch (err: any) {
      setError(err.message || 'Failed to apply reusable filters to this rule')
    } finally {
      setIsSaving(false)
    }
  }

  if (!isOpen) return null

  const footer = (
    <>
      <SecondaryButton onClick={handleCloseWithConfirmation} disabled={isSaving}>Close</SecondaryButton>
      {showAssignmentControls && (
        <PrimaryButton onClick={handleApplyFilter} disabled={isSaving}>
          Apply to Rule
        </PrimaryButton>
      )}
    </>
  )

  return (
    <>
      <AppModal
        isOpen={isOpen}
        onClose={handleCloseWithConfirmation}
      title={readOnly ? 'Reusable Filters (Read-only)' : canAssign ? 'Reusable Filters for Rule' : 'Reusable Filters'}
      size="lg"
      bodyClassName="reusable-filters-body"
      footer={footer}
      closeLabel="Close reusable filters"
    >
      {ruleName && <div className="reusable-filters-rule">Rule: {ruleName}</div>}
      {error && (
        <AppBanner className="reusable-filters-error" variant="error">
          {error}
          {errorReferenceId && (
            <>
              <br />
              {formatSupportReferenceId(errorReferenceId)}
            </>
          )}
        </AppBanner>
      )}

      {showAssignmentControls && (
        <div className="reusable-filters-assign">
          <h4>Assigned filters</h4>
          <AppInput
            value={searchInput}
            label="Search reusable filters"
            placeholder="Name, description, or expression"
            disabled={isSaving || isLoading}
            onChange={(e: any) => setSearchInput(getFieldValue(e))}
            onInput={(e: any) => setSearchInput(getFieldValue(e))}
          />
          <div className="reusable-filters-search-hint">Search applies at {DEFAULT_SEARCH_MINIMUM_LENGTH}+ characters and is filtered by the API.</div>
          {filters.length === 0 ? (
            <p>{reusableFilterSearchQuery ? 'No reusable filters match the current search.' : 'No reusable filters available.'}</p>
          ) : (
            filters.map(filter => {
              const checked = selectedFilterIds.includes(filter.id)
              return (
                <label key={filter.id} className="reusable-filter-checkbox">
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={isSaving}
                    onChange={() => {
                      setSelectedFilterIds(prev =>
                        prev.includes(filter.id)
                          ? prev.filter(id => id !== filter.id)
                          : [...prev, filter.id]
                      )
                    }}
                  />
                  <span>{filter.name}</span>
                </label>
              )
            })
          )}
        </div>
      )}

      {readOnly && (
        <div className="reusable-filters-assign">
          <h4>Assigned filters</h4>
          {selectedFilters.length === 0 ? (
            <p>No reusable filters assigned to this rule.</p>
          ) : (
            selectedFilters.map((filter) => {
              const expr = filter.filter_expression || filter.expression || ''
              return (
                <div key={filter.id} className="reusable-filter-item">
                  <div className="reusable-filter-title">{filter.name}</div>
                  {filter.description && <div className="reusable-filter-description">{filter.description}</div>}
                  <code className="reusable-filter-expression">{expr}</code>
                </div>
              )
            })
          )}
        </div>
      )}

      {showAssignmentControls && (
      <div className="reusable-filters-create">
        <h4>Create reusable filter</h4>
        <AppInput
          value={name}
          label="Name"
          placeholder="e.g. Active Customers Only"
          disabled={isSaving}
          onChange={(e: any) => setName(getFieldValue(e))}
          onInput={(e: any) => setName(getFieldValue(e))}
        />

        <AppInput
          value={description}
          label="Description"
          placeholder="Optional description"
          disabled={isSaving}
          onChange={(e: any) => setDescription(getFieldValue(e))}
          onInput={(e: any) => setDescription(getFieldValue(e))}
        />

        <AppTextarea
          value={expression}
          label="Filter expression"
          placeholder={'e.g. "status" = \'ACTIVE\' AND "deleted_on" IS NULL'}
          disabled={isSaving}
          rows={3}
          onChange={(e: any) => setExpression(getFieldValue(e))}
          onInput={(e: any) => setExpression(getFieldValue(e))}
        />

        {expressionSyntaxError && (
          <div className="reusable-filters-validation-error" role="alert">
            {expressionSyntaxError}
            {expressionSyntaxErrorReferenceId && (
              <>
                <br />
                {formatSupportReferenceId(expressionSyntaxErrorReferenceId)}
              </>
            )}
          </div>
        )}

        <div className="reusable-filters-help" aria-label="Filter syntax help">
          <h5>Filter syntax help</h5>
          <ul>
            <li>Reference attributes with double quotes, for example <code>"customer_id"</code>.</li>
            <li>Use single quotes for text values, for example <code>'ACTIVE'</code>.</li>
            <li>Escape a single quote in text by doubling it: <code>'O''Reilly'</code>.</li>
            <li>Combine conditions with <code>AND</code> / <code>OR</code>, and use parentheses to group logic.</li>
            <li>Do not end expressions with semicolons or add SQL comments.</li>
          </ul>
          <pre className="reusable-filters-help-example">{"\"status\" = 'ACTIVE' AND (\"country\" = 'NL' OR \"country\" = 'BE')\n\"last_name\" = 'O''Reilly'\n\"deleted_on\" IS NULL"}</pre>
        </div>

        <PrimaryButton onClick={handleCreateFilter} disabled={isSaving || !name.trim() || !expression.trim() || !!expressionSyntaxError}>
          {isSaving ? 'Saving...' : 'Create Filter'}
        </PrimaryButton>
      </div>
      )}

      {!readOnly && (
        <div className="reusable-filters-list">
          <h4>Available reusable filters</h4>
          {isLoading ? (
            <p>Loading filters...</p>
          ) : filters.length === 0 ? (
            <p>No reusable filters found for this workspace.</p>
          ) : (
            filters.map((filter) => {
              const expr = filter.filter_expression || filter.expression || ''
              return (
                <div key={filter.id} className="reusable-filter-item">
                  <div className="reusable-filter-title">{filter.name}</div>
                  {filter.description && <div className="reusable-filter-description">{filter.description}</div>}
                  <code className="reusable-filter-expression">{expr}</code>
                  {showAssignmentControls && (
                    <div className="reusable-filter-actions">
                      <Button
                        onClick={() => handleDeleteFilter(filter.id)}
                        disabled={isSaving}
                        variant="secondary"
                      >
                        Delete
                      </Button>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      )}
      </AppModal>

      <UnsavedChangesDialog
        isOpen={showConfirmation}
        onConfirm={handleConfirmClose}
        onCancel={handleCancelConfirmation}
      />
    </>
  )
}
