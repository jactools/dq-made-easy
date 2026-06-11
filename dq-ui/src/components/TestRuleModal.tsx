import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { AppButton, AppInput, AppModal, AppSelect } from './app-primitives'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import { useUnsavedChangesConfirmation } from '../hooks/useUnsavedChangesConfirmation'
import { AttributeCard } from './rules/AttributeCard'
import { ResolvedRuleAttribute } from './rules/ruleDisplayUtils'
import { useTrackedAsyncRequest } from '../hooks/useAsyncRequests'
import './TestRuleModal.css'

const SQL_KEYWORDS = new Set([
  'AND', 'OR', 'NOT', 'NULL', 'TRUE', 'FALSE', 'IN', 'IS', 'LIKE', 'BETWEEN', 'EXISTS',
  'LOWER', 'UPPER', 'TRIM', 'LENGTH', 'COUNT', 'COALESCE', 'CAST', 'CONVERT',
  'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'SELECT', 'FROM', 'WHERE', 'JOIN',
  'LEFT', 'RIGHT', 'INNER', 'OUTER', 'ON', 'GROUP', 'BY', 'HAVING', 'ORDER',
  'ASC', 'DESC', 'DISTINCT', 'AS',
])

interface TestRuleModalProps {
  isOpen: boolean
  ruleName: string
  ruleId: string
  versionId: string
  ruleExpression?: string
  assignedAttributes?: ResolvedRuleAttribute[]
  hasJoinConditions?: boolean
  onClose: () => void
  onTest: (request: {
    sampleCount: number
    versionId: string
    semanticMatching?: {
      enabled: boolean
      fieldAliasMappings?: Record<string, string>
      activeSynonyms?: string[]
      inactiveSynonyms?: string[]
    }
    selectedAttributes: ResolvedRuleAttribute[]
  }) => Promise<{ taskId: string }>
}

interface TestResult {
  sampleCount: number
  passed: number
  failed: number
  coverage: number
  rulePassed?: boolean
  requiredSuccessRate?: number
  joinEvaluated?: boolean
  joinMatchedContexts?: number
  joinDefinitions?: any[]
  proofId?: string
  selectedAttributes?: ResolvedRuleAttribute[]
  semanticMatching?: {
    enabled?: boolean
    configured?: boolean
    fieldAliasHits?: number
    valueCoercionMatches?: number
    semanticCoercionUsed?: boolean
  }
  error?: string
}

interface TestRuleModalFormState {
  sampleCount: string
  selectedAttributeIds: string[]
  semanticEnabled: boolean
  semanticAliasName: string
  semanticAliasTargetId: string
  activeSynonymsInput: string
  inactiveSynonymsInput: string
}

export const TestRuleModal: React.FC<TestRuleModalProps> = ({
  isOpen,
  ruleName,
  ruleId,
  versionId,
  ruleExpression = '',
  assignedAttributes = [],
  hasJoinConditions,
  onClose,
  onTest,
}) => {
  const getSelectValue = (event: any): string => {
    return event?.detail?.value ?? event?.target?.value ?? ''
  }

  const expressionAttributeCandidates = useMemo(() => {
    if (!ruleExpression) return []
    const candidates: string[] = []
    const opPattern = /\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|!=|<>|<=|>=|<|>)/g
    const kwPattern = /\b([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:IN|IS|LIKE|BETWEEN|NOT)\b/gi
    const fnPattern = /\b[A-Z_]+\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)/gi
    for (const pattern of [opPattern, kwPattern, fnPattern]) {
      let match
      while ((match = pattern.exec(ruleExpression)) !== null) {
        const name = match[1]
        if (!SQL_KEYWORDS.has(name.toUpperCase())) {
          candidates.push(name)
        }
      }
    }
    return [...new Set(candidates)]
  }, [ruleExpression])

  const semanticStorageKey = ruleId ? `dq-semantic-session-config-${ruleId}` : null

  const loadPersistedSemantic = (id: string) => {
    try {
      const raw = sessionStorage.getItem(`dq-semantic-session-config-${id}`)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  }

  const persistSemantic = (config: {
    enabled: boolean
    aliasName: string
    aliasTargetId: string
    activeSynonyms: string
    inactiveSynonyms: string
  }) => {
    if (!semanticStorageKey) return
    try {
      sessionStorage.setItem(semanticStorageKey, JSON.stringify(config))
    } catch { /* storage full or unavailable */ }
  }

  const [sampleCount, setSampleCount] = useState('10')
  const [selectedAttributeIds, setSelectedAttributeIds] = useState<string[]>([])
  const [semanticEnabled, setSemanticEnabled] = useState(true)
  const [semanticAliasName, setSemanticAliasName] = useState('')
  const [semanticAliasTargetId, setSemanticAliasTargetId] = useState('')
  const [activeSynonymsInput, setActiveSynonymsInput] = useState('active, enabled, true, 1, yes, on')
  const [inactiveSynonymsInput, setInactiveSynonymsInput] = useState('inactive, disabled, false, 0, no, off')
  const [isLoading, setIsLoading] = useState(false)
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const wasOpenRef = useRef(false)
  const previousRuleIdRef = useRef<string>('')
  const initialFormStateRef = useRef<TestRuleModalFormState | null>(null)
  const activeTask = useTrackedAsyncRequest(activeTaskId)

  useEffect(() => {
    if (!isOpen) {
      wasOpenRef.current = false
      return
    }

    const firstOpen = !wasOpenRef.current
    const ruleChanged = previousRuleIdRef.current !== ruleId
    if (!firstOpen && !ruleChanged) {
      return
    }

    wasOpenRef.current = true
    previousRuleIdRef.current = ruleId
    const nextSampleCount = '10'
    const nextSelectedAttributeIds = assignedAttributes.map((attribute) => attribute.id)
    const persisted = loadPersistedSemantic(ruleId)
    const nextSemanticEnabled = persisted?.enabled ?? true
    const nextSemanticAliasName =
      persisted?.aliasName ??
      (expressionAttributeCandidates.length === 1 ? expressionAttributeCandidates[0] : '')
    const nextSemanticAliasTargetId = persisted?.aliasTargetId ?? ''
    const nextActiveSynonymsInput = persisted?.activeSynonyms ?? 'active, enabled, true, 1, yes, on'
    const nextInactiveSynonymsInput = persisted?.inactiveSynonyms ?? 'inactive, disabled, false, 0, no, off'

    setSampleCount(nextSampleCount)
    setSelectedAttributeIds(nextSelectedAttributeIds)
    setSemanticEnabled(nextSemanticEnabled)
    setSemanticAliasName(nextSemanticAliasName)
    setSemanticAliasTargetId(nextSemanticAliasTargetId)
    setActiveSynonymsInput(nextActiveSynonymsInput)
    setInactiveSynonymsInput(nextInactiveSynonymsInput)
    setActiveTaskId(null)
    setTestResult(null)
    setError(null)

    initialFormStateRef.current = {
      sampleCount: nextSampleCount,
      selectedAttributeIds: nextSelectedAttributeIds,
      semanticEnabled: nextSemanticEnabled,
      semanticAliasName: nextSemanticAliasName,
      semanticAliasTargetId: nextSemanticAliasTargetId,
      activeSynonymsInput: nextActiveSynonymsInput,
      inactiveSynonymsInput: nextInactiveSynonymsInput,
    }
  }, [isOpen, ruleId, assignedAttributes, expressionAttributeCandidates])

  // Persist semantic config whenever any of its values change
  useEffect(() => {
    if (!isOpen || !ruleId) return
    persistSemantic({
      enabled: semanticEnabled,
      aliasName: semanticAliasName,
      aliasTargetId: semanticAliasTargetId,
      activeSynonyms: activeSynonymsInput,
      inactiveSynonyms: inactiveSynonymsInput,
    })
  }, [semanticEnabled, semanticAliasName, semanticAliasTargetId, activeSynonymsInput, inactiveSynonymsInput])

  const hasChanges = useMemo(
    () => {
      if (testResult !== null || isLoading || activeTaskId || error) {
        return false
      }

      const initialState = initialFormStateRef.current
      if (!initialState) {
        return false
      }

      if (sampleCount !== initialState.sampleCount) {
        return true
      }
      if (semanticEnabled !== initialState.semanticEnabled) {
        return true
      }
      if (semanticAliasName !== initialState.semanticAliasName) {
        return true
      }
      if (semanticAliasTargetId !== initialState.semanticAliasTargetId) {
        return true
      }
      if (activeSynonymsInput !== initialState.activeSynonymsInput) {
        return true
      }
      if (inactiveSynonymsInput !== initialState.inactiveSynonymsInput) {
        return true
      }

      if (selectedAttributeIds.length !== initialState.selectedAttributeIds.length) {
        return true
      }

      return selectedAttributeIds.some((attributeId, index) => attributeId !== initialState.selectedAttributeIds[index])
    },
    [
      activeTaskId,
      activeSynonymsInput,
      error,
      inactiveSynonymsInput,
      isLoading,
      sampleCount,
      selectedAttributeIds,
      semanticAliasName,
      semanticAliasTargetId,
      semanticEnabled,
      testResult,
    ]
  )

  const resetAndClose = useCallback(() => {
    setActiveTaskId(null)
    setTestResult(null)
    setError(null)
    setIsLoading(false)
    setSampleCount('10')
    onClose()
  }, [onClose])

  const {
    showConfirmation,
    handleCloseWithConfirmation,
    handleConfirmClose,
    handleCancelConfirmation,
  } = useUnsavedChangesConfirmation({
    isOpen,
    hasChanges,
    onClose: resetAndClose,
  })

  const handleRunTest = async () => {
    const normalizedSampleCount = Number.parseInt(String(sampleCount || '').trim(), 10)
    if (!Number.isFinite(normalizedSampleCount) || normalizedSampleCount <= 0) {
      setError('Sample count must be greater than 0')
      return
    }

    if (assignedAttributes.length === 0) {
      setError('Assign at least one technical attribute to this rule before running a test.')
      return
    }

    if (selectedAttributeIds.length === 0) {
      setError('Select at least one technical attribute to run the test against.')
      return
    }

    const selectedAttributes = assignedAttributes.filter((attribute) => selectedAttributeIds.includes(attribute.id))
    const selectedAliasTarget = assignedAttributes.find((attribute) => attribute.id === semanticAliasTargetId)
    const aliasName = semanticAliasName.trim()
    const activeSynonyms = activeSynonymsInput
      .split(',')
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean)
    const inactiveSynonyms = inactiveSynonymsInput
      .split(',')
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean)
    const selectedVersionIds = Array.from(
      new Set(
        selectedAttributes
          .map((attribute) => String(attribute.versionId || '').trim())
          .filter(Boolean)
      )
    )

    if (selectedVersionIds.length === 0) {
      setError('Could not resolve a data-object version for the selected attributes.')
      return
    }

    if (selectedVersionIds.length > 1) {
      setError('Selected attributes span multiple data-object versions. Select attributes from a single version per test run.')
      return
    }

    setIsLoading(true)
    setError(null)
    try {
      const result = await onTest({
        sampleCount: normalizedSampleCount,
        versionId: selectedVersionIds[0],
        semanticMatching: {
          enabled: semanticEnabled,
          fieldAliasMappings: semanticEnabled && aliasName && selectedAliasTarget
            ? { [aliasName]: selectedAliasTarget.name }
            : {},
          activeSynonyms,
          inactiveSynonyms,
        },
        selectedAttributes,
      })
      setActiveTaskId(result.taskId)
    } catch (err: any) {
      setError(err.message || 'Test failed')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!activeTask) return

    if (activeTask.status === 'completed' && activeTask.result) {
      const result = activeTask.result
      const recordsTestedCount = Number(result?.recordsTestedCount ?? result?.sampleCount ?? 0)
      const failedCount = Number(result?.failed ?? 0)
      const passedCount = Number(result?.passed ?? Math.max(0, recordsTestedCount - failedCount))

      setTestResult({
        sampleCount: recordsTestedCount,
        passed: passedCount,
        failed: failedCount,
        coverage: Number(result?.coverage || 0),
        rulePassed: typeof result?.rulePassed === 'boolean' ? result.rulePassed : undefined,
        requiredSuccessRate: typeof result?.requiredSuccessRate === 'number' ? result.requiredSuccessRate : undefined,
        joinEvaluated: result?.joinEvaluated,
        joinMatchedContexts: result?.joinMatchedContexts,
        joinDefinitions: result?.joinDefinitions,
        proofId: result?.proofId,
        selectedAttributes: Array.isArray(result?.selectedAttributes) ? result.selectedAttributes : [],
        semanticMatching: result?.semanticMatching,
      })
      setError(null)
      return
    }

    if (activeTask.status === 'failed' || activeTask.status === 'timed_out') {
      setError(activeTask.errorMessage || activeTask.message || 'Test failed')
    }
  }, [activeTask])

  const handleClose = () => {
    if (isLoading || activeTaskId || error || testResult) {
      resetAndClose()
      return
    }

    handleCloseWithConfirmation()
  }

  return (
    <>
    <AppModal
      isOpen={isOpen}
      onClose={handleClose}
      title={`Test Rule: ${ruleName}`}
      titleAs="h3"
      size="lg"
      dialogClassName="test-rule-modal-content"
      bodyClassName="test-rule-modal-body"
      footerClassName="test-rule-modal-footer"
      footer={
        testResult ? (
          <>
            <AppButton variant="secondary" onClick={handleClose}>
              Close
            </AppButton>
            <AppButton onClick={() => {
              setTestResult(null)
              setError(null)
            }}>
              Run Another Test
            </AppButton>
          </>
        ) : (
          <>
            <AppButton variant="secondary" onClick={handleClose}>
              Cancel
            </AppButton>
            <AppButton onClick={handleRunTest} disabled={isLoading || activeTask?.status === 'running' || activeTask?.status === 'pending'}>
              {isLoading || activeTask?.status === 'running' || activeTask?.status === 'pending' ? 'Testing...' : 'Run Test'}
            </AppButton>
          </>
        )
      }
    >
        {testResult ? (
          <>
            <div className="test-results-summary">
              <div className={`result-status ${(typeof testResult.rulePassed === 'boolean' ? testResult.rulePassed : testResult.failed === 0) ? 'result-success-bg' : 'result-failure-bg'}`}>
                {(typeof testResult.rulePassed === 'boolean' ? testResult.rulePassed : testResult.failed === 0) ? (
                  <div className="result-success">
                    <strong>✓ Rule Passed</strong>
                    <p>{testResult.passed} / {testResult.sampleCount} records validated</p>
                    {typeof testResult.requiredSuccessRate === 'number' && (
                      <p>Required success rate: {testResult.requiredSuccessRate}%</p>
                    )}
                  </div>
                ) : (
                  <div className="result-failure">
                    <strong>✗ Rule Failed</strong>
                    <p>{testResult.failed} / {testResult.sampleCount} records failed ({((testResult.failed / testResult.sampleCount) * 100).toFixed(1)}%)</p>
                    {typeof testResult.requiredSuccessRate === 'number' && (
                      <p>Required success rate: {testResult.requiredSuccessRate}%</p>
                    )}
                  </div>
                )}
              </div>

              <div className="test-metrics">
                <div className="metric">
                  <span className="metric-label">Records Tested</span>
                  <span className="metric-value">{testResult.sampleCount}</span>
                </div>
                <div className="metric">
                  <span className="metric-label">Success Rate</span>
                  <span className={`metric-value ${testResult.failed === 0 ? 'success-color' : 'failure-color'}`}>
                    {((testResult.passed / testResult.sampleCount) * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="metric">
                    <span className="metric-label">DQ Score</span>
                  <span className="metric-value">{testResult.coverage}%</span>
                </div>
              </div>

              <div className="semantic-summary">
                <h4>Business Term Matching</h4>
                <p>
                  Mode: <strong>{testResult.semanticMatching?.enabled ? 'Enabled' : 'Disabled'}</strong>
                </p>
                <p>
                  Business term mapping hits: {Number(testResult.semanticMatching?.fieldAliasHits || 0)}
                  {' · '}
                  Value coercion matches: {Number(testResult.semanticMatching?.valueCoercionMatches || 0)}
                </p>
                {testResult.semanticMatching?.semanticCoercionUsed ? (
                  <p className="semantic-summary-note">Semantic equivalence was applied in this run.</p>
                ) : (
                  <p className="semantic-summary-note">No semantic coercion was needed or configured values did not match.</p>
                )}
              </div>

              <div className="tested-attributes-summary">
                <h4>Selected Technical Attribute Scope</h4>
                <div className="rule-attribute-summary">
                  {(testResult.selectedAttributes || []).map((attribute) => (
                    <AttributeCard key={attribute.id} attribute={attribute} />
                  ))}
                </div>
                {testResult.failed > 0 && (testResult.selectedAttributes || []).length > 1 && (
                  <p className="tested-attributes-note">
                    Failed records were detected while testing multiple technical attributes. Failures may involve one or more
                    of the selected technical attributes listed above.
                  </p>
                )}
                {testResult.failed > 0 && (testResult.selectedAttributes || []).length === 1 && (
                  <p className="tested-attributes-note">
                    Failures were detected on the selected technical attribute: {(testResult.selectedAttributes || [])[0]?.name}.
                  </p>
                )}
              </div>

              {hasJoinConditions && testResult.joinEvaluated && (
                <div className="join-evaluation-info">
                  <h4>Join Conditions Evaluation</h4>
                  <div className="join-stats">
                    <div className="join-stat">
                      <span className="stat-label">Matched Contexts</span>
                      <span className="stat-value">{testResult.joinMatchedContexts}</span>
                    </div>
                    {testResult.joinDefinitions && testResult.joinDefinitions.length > 0 && (
                      <div className="join-definitions">
                        <span className="stat-label">Join Rules</span>
                        <ul>
                          {testResult.joinDefinitions.map((jd: any, idx: number) => (
                            <li key={idx}>
                              {jd.leftDataObject}[{jd.leftAttribute}] {jd.joinType} {jd.rightDataObject}[{jd.rightAttribute}]
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {error && (
                <div className="test-error">
                  <strong>Error:</strong> {error}
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            {hasJoinConditions && (
              <div className="join-notice">
                <strong>ℹ️ Join Conditions Configured</strong>
                <p>This rule has join conditions. Test data will be generated for all involved data objects.</p>
              </div>
            )}

            <div className="form-group">
              <label htmlFor="sample-count">Number of samples to generate:</label>
              <AppInput
                id="sample-count"
                label="Number of samples to generate:"
                type="number"
                value={sampleCount}
                onChange={(e: any) => {
                  const value = e?.target?.value ?? e?.detail?.value ?? ''
                  setSampleCount(String(value || ''))
                  setError(null)
                }}
                onInput={(e: any) => {
                  const value = e?.target?.value ?? e?.detail?.value ?? ''
                  setSampleCount(String(value || ''))
                  setError(null)
                }}
                placeholder="10"
                disabled={isLoading}
              />
              <small>Generates realistic test data for the rule's data object(s)</small>
            </div>

            <div className="form-group">
              <label>Run test against technical attribute(s):</label>
              <div className="test-attributes-panel">
                <div className="test-attributes-actions">
                  <button
                    type="button"
                    className="test-attributes-btn"
                    onClick={() => setSelectedAttributeIds(assignedAttributes.map((attribute) => attribute.id))}
                    disabled={isLoading || assignedAttributes.length === 0}
                  >
                    Select all
                  </button>
                  <button
                    type="button"
                    className="test-attributes-btn"
                    onClick={() => setSelectedAttributeIds([])}
                    disabled={isLoading || assignedAttributes.length === 0}
                  >
                    Clear
                  </button>
                </div>
                {assignedAttributes.length === 0 ? (
                  <div className="test-attributes-empty">No assigned technical attributes found for this rule.</div>
                ) : (
                  <div className="test-attributes-list">
                    {assignedAttributes.map((attribute) => {
                      const checked = selectedAttributeIds.includes(attribute.id)
                      return (
                        <label key={attribute.id} className="test-attribute-item">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(event) => {
                              const isChecked = event.target.checked
                              setSelectedAttributeIds((prev) => {
                                if (isChecked) {
                                  if (prev.includes(attribute.id)) return prev
                                  return [...prev, attribute.id]
                                }
                                return prev.filter((id) => id !== attribute.id)
                              })
                            }}
                            disabled={isLoading}
                          />
                          <AttributeCard attribute={attribute} />
                        </label>
                      )
                    })}
                  </div>
                )}
              </div>
              <small>Selected technical attributes determine the data-object version used for test data generation.</small>
            </div>

            <div className="form-group semantic-settings-group">
              <label className="semantic-toggle">
                <input
                  type="checkbox"
                  checked={semanticEnabled}
                  onChange={(event) => setSemanticEnabled(event.target.checked)}
                  disabled={isLoading}
                />
                Enable semantic matching (business term and value equivalence)
              </label>

              {semanticEnabled && (
                <div className="semantic-settings-panel">
                  <div className="semantic-inline-fields">
                    <div>
                      <label htmlFor="semantic-alias-name">Business term name</label>
                      <AppInput
                        id="semantic-alias-name"
                        label="Business term name"
                        type="text"
                        value={semanticAliasName}
                        onChange={(e: any) => setSemanticAliasName(String(e?.target?.value ?? e?.detail?.value ?? ''))}
                        onInput={(e: any) => setSemanticAliasName(String(e?.target?.value ?? e?.detail?.value ?? ''))}
                        placeholder="e.g. account_status"
                        disabled={isLoading}
                      />
                      {expressionAttributeCandidates.length > 1 && (
                        <div className="semantic-alias-suggestions">
                          {expressionAttributeCandidates.map((name) => (
                            <button
                              key={name}
                              type="button"
                              className="semantic-alias-chip"
                              onClick={() => setSemanticAliasName(name)}
                              disabled={isLoading}
                            >{name}</button>
                          ))}
                        </div>
                      )}
                    </div>
                    <div>
                      <label htmlFor="semantic-alias-target">Map to selected technical attribute</label>
                      <AppSelect
                        id="semantic-alias-target"
                        label="Map to selected technical attribute"
                        value={semanticAliasTargetId}
                        onChange={setSemanticAliasTargetId}
                        disabled={isLoading}
                        placeholderLabel=""
                        options={[
                          { value: '', label: 'No mapping' },
                          ...assignedAttributes
                            .filter((attribute) => selectedAttributeIds.includes(attribute.id))
                            .map((attribute) => ({ value: attribute.id, label: attribute.name })),
                        ]}
                      />
                    </div>
                  </div>

                  <div className="semantic-inline-fields">
                    <div>
                      <label htmlFor="semantic-active-values">Active synonyms (comma separated)</label>
                      <AppInput
                        id="semantic-active-values"
                        label="Active synonyms (comma separated)"
                        type="text"
                        value={activeSynonymsInput}
                        onChange={(e: any) => setActiveSynonymsInput(String(e?.target?.value ?? e?.detail?.value ?? ''))}
                        disabled={isLoading}
                      />
                    </div>
                    <div>
                      <label htmlFor="semantic-inactive-values">Inactive synonyms (comma separated)</label>
                      <AppInput
                        id="semantic-inactive-values"
                        label="Inactive synonyms (comma separated)"
                        type="text"
                        value={inactiveSynonymsInput}
                        onChange={(e: any) => setInactiveSynonymsInput(String(e?.target?.value ?? e?.detail?.value ?? ''))}
                        disabled={isLoading}
                      />
                    </div>
                  </div>
                </div>
              )}
              <small>
                This mapping applies only when testing this rule. It is stored for this browser session and removed when the session/browser storage is cleared.
                Long term mappings between business terms and versioned technical attributes should be managed centrally.
              </small>
            </div>

            {error && (
              <div className="test-error">
                {error}
              </div>
            )}
          </>
        )}
    </AppModal>
    <UnsavedChangesDialog
      isOpen={showConfirmation}
      onConfirm={handleConfirmClose}
      onCancel={handleCancelConfirmation}
      title="Discard Test Configuration?"
      message="You have unsaved changes to the sample count. Do you want to discard these changes?"
      confirmLabel="Discard Changes"
      cancelLabel="Keep Editing"
    />
  </>
  )
}
