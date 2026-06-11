import React, { useEffect, useMemo, useState } from 'react'
import { AppBanner, AppSelect } from './app-primitives'
import { PrimaryButton, SecondaryButton, Button } from './Button'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import { useUnsavedChangesConfirmation } from '../hooks/useUnsavedChangesConfirmation'
import { AppModal } from './app-primitives'
import { useSettings } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { RuleJoinDefinition } from '../types/rules'
import { createSupportReferenceId, formatSupportReferenceId } from '../utils/supportReference'
import './ReusableJoinsModal.css'

interface ReusableJoinItem {
  id: string
  name: string
  description?: string
  join_definition?: string
  workspace?: string
  active?: boolean
}

interface ReusableJoinsModalProps {
  isOpen: boolean
  onClose: () => void
  workspaceId?: string
  ruleName?: string
  currentJoinId?: string | null
  onAssignToRule?: (joinId: string | null) => Promise<void>
  readOnly?: boolean
}

const parseJoinDefinition = (raw?: string): RuleJoinDefinition[] => {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const summarizeJoinDefinition = (defs: RuleJoinDefinition[]): string => {
  if (defs.length === 0) return 'No joins defined'
  const totalConditions = defs.reduce(
    (sum, d) => sum + (Array.isArray(d.conditions) ? d.conditions.length : 0),
    0
  )
  return `${defs.length} join${defs.length === 1 ? '' : 's'}, ${totalConditions} condition${totalConditions === 1 ? '' : 's'}`
}

export const ReusableJoinsModal: React.FC<ReusableJoinsModalProps> = ({
  isOpen,
  onClose,
  workspaceId,
  ruleName,
  currentJoinId,
  onAssignToRule,
  readOnly = false,
}) => {
  const settings = useSettings()
  const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)

  const [joins, setJoins] = useState<ReusableJoinItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [selectedJoinId, setSelectedJoinId] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const errorReferenceId = useMemo(() => (error ? createSupportReferenceId() : null), [error])

  const canAssign = typeof onAssignToRule === 'function' && !readOnly

  // Track if form has been modified
  const initialJoinId = useMemo(() => currentJoinId || '', [currentJoinId])
  
  const hasChanges = useMemo(() => {
    if (readOnly) return false
    return selectedJoinId !== initialJoinId
  }, [readOnly, selectedJoinId, initialJoinId])

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

  const authHeaders = useMemo(() => {
    const token = getAuthToken()
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
  }, [])

  const loadJoins = async () => {
    if (!isOpen) return
    if (!getAuthToken()) {
      setJoins([])
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      const query = workspaceId ? `?workspace=${encodeURIComponent(workspaceId)}` : ''
      const response = await fetch(`${apiBase}/reusable-joins${query}`, {
        headers: authHeaders,
      })

      if (!response.ok) {
        throw new Error('Failed to load reusable joins')
      }

      const body = await response.json()
      setJoins(Array.isArray(body) ? body : [])
    } catch (err: any) {
      setError(err.message || 'Failed to load reusable joins')
      setJoins([])
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!isOpen) return
    setSelectedJoinId(currentJoinId || '')
    loadJoins()
  }, [isOpen, workspaceId, currentJoinId])

  const selectedJoin = useMemo(() => {
    if (!currentJoinId) return null
    return joins.find((join) => join.id === currentJoinId) || null
  }, [currentJoinId, joins])

  const handleDeleteJoin = async (joinId: string) => {
    if (!window.confirm('Delete this reusable join?')) return

    setIsSaving(true)
    setError(null)
    try {
      const response = await fetch(`${apiBase}/reusable-joins/${encodeURIComponent(joinId)}`, {
        method: 'DELETE',
        headers: authHeaders,
      })

      if (!response.ok) {
        const message = await response.text()
        throw new Error(message || 'Failed to delete reusable join')
      }

      if (selectedJoinId === joinId) {
        setSelectedJoinId('')
      }

      await loadJoins()
    } catch (err: any) {
      setError(err.message || 'Failed to delete reusable join')
    } finally {
      setIsSaving(false)
    }
  }

  const handleApplyJoin = async () => {
    if (!onAssignToRule) return
    setIsSaving(true)
    setError(null)
    try {
      await onAssignToRule(selectedJoinId || null)
      onClose()
    } catch (err: any) {
      setError(err.message || 'Failed to apply reusable join to this rule')
    } finally {
      setIsSaving(false)
    }
  }

  if (!isOpen) return null

  const footer = (
    <>
      <SecondaryButton onClick={handleCloseWithConfirmation} disabled={isSaving}>Close</SecondaryButton>
      {canAssign && (
        <PrimaryButton onClick={handleApplyJoin} disabled={isSaving}>
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
        title={readOnly ? 'Reusable Joins (Read-only)' : canAssign ? 'Reusable Joins for Rule' : 'Reusable Joins (Compatibility)'}
        size="lg"
        bodyClassName="reusable-joins-body"
        footer={footer}
        closeLabel="Close reusable joins"
      >
      {ruleName && <div className="reusable-joins-rule">Rule: {ruleName}</div>}
      {error && (
        <AppBanner className="reusable-joins-error" variant="error">
          {error}
          {errorReferenceId && (
            <>
              <br />
              {formatSupportReferenceId(errorReferenceId)}
            </>
          )}
        </AppBanner>
      )}

      {canAssign && (
        <div className="reusable-joins-assign">
          <AppSelect
            label="Assigned join"
            value={selectedJoinId}
            onChange={setSelectedJoinId}
            placeholderLabel=""
            options={[
              { value: '', label: 'No reusable join' },
              ...joins.map((join) => ({ value: join.id, label: join.name })),
            ]}
          />
        </div>
      )}

      {readOnly && (
        <div className="reusable-joins-assign">
          <h4>Assigned join</h4>
          {selectedJoin ? (
            <div className="reusable-join-item">
              <div className="reusable-join-title">{selectedJoin.name}</div>
              {selectedJoin.description && <div className="reusable-join-description">{selectedJoin.description}</div>}
              <code className="reusable-join-summary">{summarizeJoinDefinition(parseJoinDefinition(selectedJoin.join_definition))}</code>
            </div>
          ) : (
            <p>No reusable join assigned to this rule.</p>
          )}
        </div>
      )}

      {!readOnly && (
        <>
          <div className="reusable-joins-hint">
            <p>Data Assets are the primary authoring surface for new join-backed business shapes. Use this panel only to assign or review reusable joins during migration.</p>
          </div>

          <div className="reusable-joins-list">
            <h4>Available reusable joins</h4>
            {isLoading ? (
              <p>Loading joins...</p>
            ) : joins.length === 0 ? (
              <p>No reusable joins found for this workspace.</p>
            ) : (
              joins.map((join) => {
                const defs = parseJoinDefinition(join.join_definition)
                const summary = summarizeJoinDefinition(defs)
                return (
                  <div key={join.id} className="reusable-join-item">
                    <div className="reusable-join-title">{join.name}</div>
                    {join.description && <div className="reusable-join-description">{join.description}</div>}
                    <code className="reusable-join-summary">{summary}</code>
                    {canAssign && (
                      <div className="reusable-join-actions">
                        <Button
                          onClick={() => handleDeleteJoin(join.id)}
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
        </>
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
