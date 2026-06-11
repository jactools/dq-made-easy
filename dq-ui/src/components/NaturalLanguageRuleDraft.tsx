import React, { useEffect, useMemo, useState } from 'react'

import {
  NaturalLanguageAnalysisProvider,
  NaturalLanguageDraftSuggestionRequest,
  NaturalLanguageDraftSuggestionResult,
  NaturalLanguagePreviewTelemetryRequest,
  NaturalLanguagePreviewResult,
  NaturalLanguageRuleDslDocument,
  NaturalLanguageRulePreview,
  NaturalLanguageSearchScope,
} from '../hooks/useSuggestions'
import { useCatalogTerms } from '../hooks/useCatalogTerms'
import { useAsyncRequests } from '../hooks/useAsyncRequests'
import { Button, SecondaryButton } from './Button'
import { AppSelect } from './app-primitives'
import { snakeToCamel } from '../utils/caseConverters'
import type { TrackedAsyncRequest } from '../contexts/AsyncRequestTrackerContext'

interface NaturalLanguageRuleDraftPreviewProps {
  canCreateRule: boolean
  currentWorkspaceId: string | null
  accessibleWorkspaceIds: string[]
  generatePreview: (request: {
    prompt: string
    searchScope: NaturalLanguageSearchScope
    currentWorkspaceId: string
    analysisProvider: NaturalLanguageAnalysisProvider
  }) => Promise<NaturalLanguagePreviewResult>
  createDraftSuggestion: (request: NaturalLanguageDraftSuggestionRequest) => Promise<NaturalLanguageDraftSuggestionResult>
  recordTelemetry?: (request: NaturalLanguagePreviewTelemetryRequest) => Promise<boolean>
  onDraftCreated?: (result: NaturalLanguageDraftSuggestionResult) => void
}

const DEFAULT_PROMPT = ''

const formatWorkspaceLabel = (workspaceId: string) => workspaceId.replace(/[-_]+/g, ' ')

const formatRoleLabel = (role: string) => {
  if (role === 'condition') return 'Condition'
  if (role === 'target') return 'Target'
  return role
}

const formatDslKindLabel = (kind: string) => kind.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase())

const formatDslSubject = (subject?: { column?: string; columns?: string[] }) => {
  if (!subject) return '—'
  if (subject.column) return subject.column
  if (subject.columns && subject.columns.length > 0) return subject.columns.join(', ')
  return '—'
}

const formatDslScope = (scope: NaturalLanguageRuleDslDocument['rule']['scope']) => {
  const parts = [`Data object: ${scope.dataset.dataObjectId || '—'}`]
  if (scope.dataset.dataObjectVersionId) parts.push(`Version: ${scope.dataset.dataObjectVersionId}`)
  if (scope.rowFilter) parts.push(`Row filter: ${scope.rowFilter.expression}`)
  if (scope.comparison) parts.push('Comparison scope configured')
  if (scope.join) parts.push('Join scope configured')
  if (scope.grouping) parts.push('Grouping scope configured')
  if (scope.timeWindow) parts.push('Time window configured')
  return parts.join(' • ')
}

const formatDslMeasure = (measure: NaturalLanguageRuleDslDocument['rule']['measure']) => {
  if (measure.type === 'metric') {
    return `${measure.metric || 'metric'}${measure.subject ? ` on ${formatDslSubject(measure.subject)}` : ''}`
  }
  if (measure.type === 'row_predicate') {
    return measure.predicate?.expression || ''
  }
  if (measure.type === 'schema') {
    return measure.schemaAssertion || 'schema assertion'
  }
  if (measure.type === 'query') {
    return measure.query
  }
  return measure.type
}

const formatDslExpectation = (expectation: NaturalLanguageRuleDslDocument['rule']['expectation']) => {
  if (expectation.type === 'threshold') {
    if (expectation.operator === 'between') {
      return `between ${expectation.minValue ?? '—'} and ${expectation.maxValue ?? '—'}${expectation.unit ? ` ${expectation.unit}` : ''}`
    }
    return `${expectation.operator || 'threshold'} ${expectation.value ?? '—'}${expectation.unit ? ` ${expectation.unit}` : ''}`
  }
  return expectation.type
}

const formatDslEvidence = (evidence: NaturalLanguageRuleDslDocument['rule']['evidence']) => {
  const failedRows = evidence.failedRows
  return `${failedRows.mode}${failedRows.limit ? ` up to ${failedRows.limit}` : ''}; row id ${failedRows.includeRowIdentifier ? 'on' : 'off'}; primary key ${failedRows.includePrimaryKey ? 'on' : 'off'}`
}

const formatDslOperations = (operations: NaturalLanguageRuleDslDocument['rule']['operations']) => (
  `${operations.severity} via ${operations.preferredEngines.join(', ')}${operations.failIfNotNative ? '; fail if not native' : ''}`
)

const catalogTermFieldTooltip = (fieldLabel: string) =>
  `${fieldLabel} value`

const getPreviewRuleKind = (previewResult: NaturalLanguageRulePreview | null) => {
  if (!previewResult) return null
  return previewResult.draftRulePreview.dsl?.rule?.kind || (previewResult as any).checkType || null
}

const extractCatalogTermQuery = (prompt: string) => {
  const trimmedPrompt = prompt.trim()
  if (!trimmedPrompt) return ''

  const explicitMatch = trimmedPrompt.match(/(?:attribute|column|field)\s+([a-zA-Z][a-zA-Z0-9_.-]*)/i)
  if (explicitMatch?.[1]) return explicitMatch[1].trim()

  const quotedMatch = trimmedPrompt.match(/`([^`]+)`|"([^"]+)"|'([^']+)'/)
  if (quotedMatch) {
    return (quotedMatch[1] || quotedMatch[2] || quotedMatch[3] || '').trim()
  }

  const identifierMatch = trimmedPrompt.match(/\b[a-zA-Z]+_[a-zA-Z0-9_]+\b/)
  if (identifierMatch?.[0]) return identifierMatch[0].trim()

  return trimmedPrompt
}

const getScopeDescription = (scope: NaturalLanguageSearchScope, currentWorkspaceId: string) => {
  if (scope === 'current') {
    return `No narrower page-level catalog context exists on this screen, so Current resolves against the current workspace in ${formatWorkspaceLabel(currentWorkspaceId)}.`
  }
  if (scope === 'all') {
    return `All searches the full active workspace catalog in ${formatWorkspaceLabel(currentWorkspaceId)}.`
  }
  return 'All Across Workspaces searches every workspace you are explicitly allowed to search.'
}

const formatRequestStatusLabel = (status: TrackedAsyncRequest['status']) => {
  if (status === 'timed_out') return 'Timed out'
  return status.charAt(0).toUpperCase() + status.slice(1)
}

const extractPreviewPayload = (result: unknown) => {
  if (!result || typeof result !== 'object') return null
  const requestRecord = result as { result?: unknown }
  return requestRecord.result || result
}

export const NaturalLanguageRuleDraftPreview: React.FC<NaturalLanguageRuleDraftPreviewProps> = ({
  canCreateRule,
  currentWorkspaceId,
  accessibleWorkspaceIds,
  generatePreview,
  createDraftSuggestion,
  recordTelemetry,
  onDraftCreated,
}) => {
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT)
  const [searchScope, setSearchScope] = useState<NaturalLanguageSearchScope>('current')
  const [analysisProvider, setAnalysisProvider] = useState<NaturalLanguageAnalysisProvider>('rapidfuzz')
  const [previewResult, setPreviewResult] = useState<NaturalLanguageRulePreview | null>(null)
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(new Set())
  const [validationMessage, setValidationMessage] = useState<string | null>(null)
  const [savedMessage, setSavedMessage] = useState<string | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [hasRecordedSelectionTelemetry, setHasRecordedSelectionTelemetry] = useState(false)
  const [activePreviewRequestId, setActivePreviewRequestId] = useState<string | null>(null)
  const {
    requests,
    trackNaturalLanguageDraftRequest,
    naturalLanguageAnalysisRequests = [],
    naturalLanguageAnalysisRequestsError = null,
  } = useAsyncRequests()
  const catalogTermQuery = previewResult?.targetTerms?.[0] || extractCatalogTermQuery(prompt)
  const { error: catalogTermsError, loading: catalogTermsLoading, terms: catalogTermResults } = useCatalogTerms(catalogTermQuery)
  const matchingCatalogTerms = useMemo(() => catalogTermResults.slice(0, 5), [catalogTermResults])
  const activePreviewRequest = activePreviewRequestId ? requests[activePreviewRequestId] || null : null
  const recentAnalysisRequests = useMemo(() => {
    if (!currentWorkspaceId) return []

    const mergedRequests = new Map<string, TrackedAsyncRequest>()
    for (const request of naturalLanguageAnalysisRequests) {
      mergedRequests.set(request.requestId || request.id, request)
    }
    for (const request of Object.values(requests)) {
      if (request.kind !== 'natural-language-draft') continue
      mergedRequests.set(request.requestId || request.id, request)
    }

    return Array.from(mergedRequests.values())
      .filter((request) => request.kind === 'natural-language-draft')
      .filter((request) => request.sourceId === currentWorkspaceId)
      .filter((request) => request.metadata?.analysisProvider === 'llm')
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
      .slice(0, 5)
  }, [currentWorkspaceId, naturalLanguageAnalysisRequests, requests])

  const workspaceIds = useMemo(
    () => Array.from(new Set(accessibleWorkspaceIds.filter(Boolean))),
    [accessibleWorkspaceIds],
  )

  const availableScopes = useMemo(() => {
    const scopes = [
      { value: 'current', label: 'Current' },
      { value: 'all', label: 'All in Current Workspace' },
    ]

    if (workspaceIds.length > 1) {
      scopes.push({ value: 'all_across_workspaces', label: 'All Across Workspaces' })
    }

    return scopes
  }, [workspaceIds])

  const availableAnalysisProviders = useMemo(
    () => [
      { value: 'rapidfuzz', label: 'RapidFuzz (local)' },
      { value: 'llm', label: 'LLM service (dq-llm)' },
    ],
    [],
  )

  const selectedCandidates = useMemo(() => {
    if (!previewResult) return []
    return previewResult.candidateAttributes.filter(candidate => selectedCandidateIds.has(candidate.attributeId))
  }, [previewResult, selectedCandidateIds])

  const generatedDraft = useMemo(() => {
    if (!previewResult || !currentWorkspaceId || selectedCandidates.length === 0) return null

    return {
      name: previewResult.draftRulePreview.name,
      workspaceId: currentWorkspaceId,
      summary: previewResult.draftRulePreview.summary,
      dsl: previewResult.draftRulePreview.dsl || null,
    }
  }, [currentWorkspaceId, previewResult, selectedCandidates])

  useEffect(() => {
    setHasRecordedSelectionTelemetry(false)
  }, [previewResult])

  useEffect(() => {
    if (!activePreviewRequest) return

    if (activePreviewRequest.status === 'pending' || activePreviewRequest.status === 'running') {
      return
    }

    if (activePreviewRequest.status === 'completed') {
      const previewPayload = extractPreviewPayload(activePreviewRequest.result)
      if (previewPayload) {
        const normalizedPreview = snakeToCamel<NaturalLanguageRulePreview>(previewPayload)
        setPreviewResult(normalizedPreview)
        setSelectedCandidateIds(new Set())
        setValidationMessage(
          normalizedPreview.candidateAttributes.length === 0
            ? 'No candidate attributes matched this request in the selected search scope. Adjust the prompt or scope and try again.'
            : null,
        )
      }
      setActivePreviewRequestId(null)
      return
    }

    if (activePreviewRequest.status === 'failed' || activePreviewRequest.status === 'timed_out') {
      setPreviewResult(null)
      setSelectedCandidateIds(new Set())
      setValidationMessage(activePreviewRequest.errorMessage || activePreviewRequest.message || 'LLM preview request failed. Check recent requests below for details.')
      setActivePreviewRequestId(null)
    }
  }, [activePreviewRequest])

  if (!canCreateRule) {
    return null
  }

  const handleGeneratePreview = async () => {
    setSavedMessage(null)
    setValidationMessage(null)

    if (!currentWorkspaceId) {
      setPreviewResult(null)
      setSelectedCandidateIds(new Set())
      setValidationMessage('Select a workspace before using this preview flow.')
      return
    }

    const trimmedPrompt = prompt.trim()
    if (!trimmedPrompt) {
      setPreviewResult(null)
      setSelectedCandidateIds(new Set())
      setValidationMessage('Describe the rule you want in one sentence.')
      return
    }

    setPreviewResult(null)
    setSelectedCandidateIds(new Set())
    setActivePreviewRequestId(null)
    setIsGenerating(true)
    const result = await generatePreview({
      prompt: trimmedPrompt,
      searchScope,
      currentWorkspaceId,
      analysisProvider,
    })
    setIsGenerating(false)

    if (result.queued && result.requestId) {
      setValidationMessage(null)
      setActivePreviewRequestId(trackNaturalLanguageDraftRequest({
        requestId: result.requestId,
        workspaceId: currentWorkspaceId,
        workspaceName: formatWorkspaceLabel(currentWorkspaceId),
        analysisProvider,
        analysisType: 'preview',
      }))
      return
    }

    if (!result.success || !result.preview) {
      setPreviewResult(null)
      setSelectedCandidateIds(new Set())
      setValidationMessage(result.message)
      return
    }

    setPreviewResult(result.preview)
    setSelectedCandidateIds(new Set())
    setValidationMessage(
      result.preview.candidateAttributes.length === 0
        ? 'No candidate attributes matched this request in the selected search scope. Adjust the prompt or scope and try again.'
        : null,
    )
  }

  const handleReset = () => {
    if (
      recordTelemetry
      && currentWorkspaceId
      && (previewResult || selectedCandidateIds.size > 0 || prompt.trim() !== DEFAULT_PROMPT)
    ) {
      void recordTelemetry({
        action: 'preview_cancelled',
        currentWorkspaceId,
        selectedAttributeCount: selectedCandidateIds.size,
      })
    }
    setPreviewResult(null)
    setSelectedCandidateIds(new Set())
    setValidationMessage(null)
    setSavedMessage(null)
    setActivePreviewRequestId(null)
    setPrompt(DEFAULT_PROMPT)
    setAnalysisProvider('rapidfuzz')
    setHasRecordedSelectionTelemetry(false)
  }

  const handleToggleCandidate = (candidateId: string) => {
    setSavedMessage(null)
    const isAddingFirstSelection = (
      Boolean(recordTelemetry)
      && Boolean(currentWorkspaceId)
      && !hasRecordedSelectionTelemetry
      && !selectedCandidateIds.has(candidateId)
      && selectedCandidateIds.size === 0
    )
    setSelectedCandidateIds(previousSelection => {
      const nextSelection = new Set(previousSelection)
      if (nextSelection.has(candidateId)) {
        nextSelection.delete(candidateId)
      } else {
        nextSelection.add(candidateId)
      }
      return nextSelection
    })
    if (isAddingFirstSelection && recordTelemetry && currentWorkspaceId) {
      setHasRecordedSelectionTelemetry(true)
      void recordTelemetry({
        action: 'attributes_selected',
        currentWorkspaceId,
        selectedAttributeCount: 1,
      })
    }
  }

  const handleCreateDraft = async () => {
    if (!previewResult || !generatedDraft || !currentWorkspaceId || selectedCandidates.length === 0) {
      setValidationMessage('Select at least one candidate attribute before creating a draft suggestion.')
      return
    }

    setIsSaving(true)
    const result = await createDraftSuggestion({
      currentWorkspaceId,
      prompt: prompt.trim(),
      searchScope: previewResult.searchScope,
      analysisProvider,
      selectedAttributeIds: selectedCandidates.map(candidate => candidate.attributeId),
    })
    setIsSaving(false)

    if (!result.success) {
      setValidationMessage(result.message)
      return
    }

    setSavedMessage(result.message)
    onDraftCreated?.(result)
  }

  return (
    <section className="nl-rule-preview-section" aria-labelledby="nl-rule-preview-title">
      <div className="nl-rule-preview-header">
        <div>
          <div className="header-content">
            <h2 id="nl-rule-preview-title">Describe a Rule Draft</h2>
            <span className="preview-badge">Preview</span>
          </div>
          <p className="nl-rule-preview-subtitle">
            Describe the rule you want in plain language, review candidate attributes, and generate a draft suggestion for the current workspace.
          </p>
        </div>
        <div className="nl-rule-preview-workspace-callout">
          <span className="nl-rule-preview-workspace-label">Target workspace</span>
          <strong>{currentWorkspaceId ? formatWorkspaceLabel(currentWorkspaceId) : 'No workspace selected'}</strong>
        </div>
      </div>

      <div className="nl-rule-preview-grid">
        <div className="nl-rule-preview-form-card">
          <label className="nl-rule-preview-label" htmlFor="nl-rule-prompt">
            What rule do you want?
          </label>
          <textarea
            id="nl-rule-prompt"
            className="nl-rule-preview-textarea"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Describe the rule in plain language"
            rows={4}
          />
          <p className="nl-rule-preview-scope-help">
            Note: the text you enter here will be stored with the resulting draft suggestion for validation and audit purposes.
          </p>

          <div className="nl-rule-preview-controls">
            <AppSelect
              id="nl-rule-search-scope"
              label="Attribute matching scope"
              value={searchScope}
              onChange={(value) => setSearchScope(value as NaturalLanguageSearchScope)}
              options={availableScopes}
            />
            <p className="nl-rule-preview-scope-help">
              {currentWorkspaceId ? getScopeDescription(searchScope, currentWorkspaceId) : 'A current workspace is required to generate a draft suggestion.'}
            </p>
          </div>

          <div className="nl-rule-preview-controls">
            <AppSelect
              id="nl-rule-analysis-provider"
              label="Analysis engine"
              value={analysisProvider}
              onChange={(value) => setAnalysisProvider(value as NaturalLanguageAnalysisProvider)}
              options={availableAnalysisProviders}
              placeholderLabel="Choose an analysis engine"
              hint="RapidFuzz stays local. LLM mode queues analysis requests and keeps them visible in Recent LLM Analysis Requests below."
            />
          </div>

          <div className="nl-rule-preview-candidates-card">
            <div className="nl-rule-preview-card-header">
              <div>
                <h3 className="nl-rule-preview-card-title">Matching Business Terms</h3>
                <p className="nl-rule-preview-card-subtitle">
                  These catalog terms are best-effort matches for the prompt text. Generate a preview to see candidate attributes.
                </p>
              </div>
            </div>

            {catalogTermsError ? (
              <div className="nl-rule-preview-alert warning" role="alert">
                Business terms could not be loaded: {catalogTermsError}
              </div>
            ) : catalogTermsLoading ? (
              <p className="nl-rule-preview-empty">Loading business terms...</p>
            ) : matchingCatalogTerms.length === 0 ? (
              <p className="nl-rule-preview-empty">No business terms matched the current prompt.</p>
            ) : (
              <ul className="nl-rule-preview-term-list">
                {matchingCatalogTerms.map((term) => (
                  <li key={term.termKey} className="nl-rule-preview-term-item">
                    <div className="nl-rule-preview-term-header">
                      <strong className="nl-rule-preview-term-name" title={catalogTermFieldTooltip('term')}>
                        {term.termName}
                      </strong>
                    </div>
                    <span className="nl-rule-preview-term-key" title={catalogTermFieldTooltip('key')}>
                      Key: {term.termKey}
                    </span>
                    {typeof term.matchScorePct === 'number' && (
                      <span
                        className="nl-rule-preview-term-score"
                        title="Fuzzy similarity score returned by the backend after normalizing the prompt and catalog term text. Higher means the term is a stronger match."
                      >
                        Match score: {Math.round(term.matchScorePct)}%
                      </span>
                    )}
                    {term.description && (
                      <span className="nl-rule-preview-term-description" title={catalogTermFieldTooltip('catalog attribute description')}>
                        {term.description}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="nl-rule-preview-actions">
            <Button type="button" onClick={handleGeneratePreview}>
              {isGenerating ? 'Generating...' : 'Generate Preview'}
            </Button>
            <SecondaryButton type="button" onClick={handleReset}>
              Reset
            </SecondaryButton>
          </div>

          {(analysisProvider === 'llm' || recentAnalysisRequests.length > 0) && (
            <div className="nl-rule-preview-history-card">
              <div className="nl-rule-preview-card-header">
                <div>
                  <h3 className="nl-rule-preview-card-title">Recent LLM Analysis Requests</h3>
                  <p className="nl-rule-preview-card-subtitle">
                    Queued preview and draft requests for {formatWorkspaceLabel(currentWorkspaceId || 'current workspace')} stay visible while dq-llm works.
                  </p>
                </div>
              </div>

              {naturalLanguageAnalysisRequestsError ? (
                <p className="nl-rule-preview-alert warning">{naturalLanguageAnalysisRequestsError}</p>
              ) : null}

              {recentAnalysisRequests.length === 0 ? (
                <p className="nl-rule-preview-empty">No LLM analysis requests have been queued for this workspace yet.</p>
              ) : (
                <div className="nl-rule-preview-history-list">
                  {recentAnalysisRequests.map((request) => (
                    <div key={request.id} className="nl-rule-preview-history-item">
                      <div className="nl-rule-preview-history-header">
                        <strong>{request.title}</strong>
                        <span className={`nl-rule-preview-history-status status-${request.status}`}>
                          {formatRequestStatusLabel(request.status)}
                        </span>
                      </div>
                      <div className="nl-rule-preview-history-meta">
                        <span>{request.metadata?.analysisType === 'preview' ? 'Preview' : 'Draft suggestion'}</span>
                        <span>{request.sourceName || formatWorkspaceLabel(request.sourceId || currentWorkspaceId || 'current workspace')}</span>
                      </div>
                      <p>{request.errorMessage || request.message || 'Waiting for the LLM analysis service to respond.'}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {validationMessage && (
            <div className="nl-rule-preview-alert warning" role="alert">
              {validationMessage}
            </div>
          )}

          {savedMessage && (
            <div className="nl-rule-preview-alert success" role="status">
              {savedMessage}
            </div>
          )}
        </div>

        <div className="nl-rule-preview-form-card compact">
          <h3 className="nl-rule-preview-card-title">Preview Rules</h3>
          <ul className="nl-rule-preview-rules-list">
            <li>Only users who can create rules in the active workspace can use this preview flow.</li>
            <li>The resulting draft suggestion always targets the current workspace.</li>
            <li>All Across Workspaces appears only when you have more than one searchable workspace in this session.</li>
            <li>Conditional prompts require the target and condition attributes to come from the same data object version.</li>
            <li>Saving the confirmed draft creates a real suggestion in the existing Suggestions lifecycle.</li>
          </ul>
        </div>
      </div>

      {previewResult && (
        <div className="nl-rule-preview-results">
          <div className="nl-rule-preview-summary-card">
            <div className="nl-rule-preview-summary-row">
              <span className="nl-rule-preview-summary-label">Draft rule kind</span>
              <span className="nl-rule-preview-summary-value emphasis">
                {getPreviewRuleKind(previewResult) ? formatDslKindLabel(String(getPreviewRuleKind(previewResult))) : 'Pending preview data'}
              </span>
            </div>
            <div className="nl-rule-preview-summary-row">
              <span className="nl-rule-preview-summary-label">Target term</span>
              <span className="nl-rule-preview-summary-value">{previewResult.targetTerms[0] || '—'}</span>
            </div>
            <div className="nl-rule-preview-summary-row">
              <span className="nl-rule-preview-summary-label">Search scope</span>
              <span className="nl-rule-preview-summary-value">{availableScopes.find(scope => scope.value === previewResult.searchScope)?.label || previewResult.searchScope}</span>
            </div>
            {previewResult.parsedCondition && (
              <div className="nl-rule-preview-summary-row">
                <span className="nl-rule-preview-summary-label">Condition</span>
                <span className="nl-rule-preview-summary-value">
                  {previewResult.parsedCondition.attributeTerm} = {previewResult.parsedCondition.value}
                </span>
              </div>
            )}
            <div className="nl-rule-preview-summary-row">
              <span className="nl-rule-preview-summary-label">Candidate count</span>
              <span className="nl-rule-preview-summary-value">{previewResult.candidateAttributes.length}</span>
            </div>
          </div>

          <div className="nl-rule-preview-candidates-card">
            <div className="nl-rule-preview-card-header">
              <div>
                <h3 className="nl-rule-preview-card-title">Candidate Attributes</h3>
                <p className="nl-rule-preview-card-subtitle">
                  {previewResult.parsedCondition
                    ? 'Select one target attribute and one condition attribute from the same data object version.'
                    : 'Confirm which attributes belong in scope before creating a draft suggestion.'}
                </p>
              </div>
            </div>

            {previewResult.candidateAttributes.length === 0 ? (
              <p className="nl-rule-preview-empty">No candidate attributes were found for this preview request.</p>
            ) : (
              <div className="nl-rule-preview-candidate-list">
                {previewResult.candidateAttributes.map((candidate) => {
                  const fullPath = `${candidate.parentPath.join('.')} -> ${candidate.attributeName}`
                  return (
                    <label key={candidate.attributeId} className="nl-rule-preview-candidate-item">
                      <input
                        type="checkbox"
                        checked={selectedCandidateIds.has(candidate.attributeId)}
                        onChange={() => handleToggleCandidate(candidate.attributeId)}
                      />
                      <div className="nl-rule-preview-candidate-body">
                        <div className="nl-rule-preview-candidate-header">
                          <strong>{fullPath}</strong>
                          <div className="nl-rule-preview-candidate-badges">
                            {candidate.matchRoles.map((role) => (
                              <span key={`${candidate.attributeId}-${role}`} className="nl-rule-preview-chip workspace">{formatRoleLabel(role)}</span>
                            ))}
                            {candidate.workspaceId !== currentWorkspaceId && (
                              <span className="nl-rule-preview-chip workspace">{formatWorkspaceLabel(candidate.workspaceId)}</span>
                            )}
                            <span className="nl-rule-preview-chip confidence">{Math.round(candidate.confidenceScore * 100)}% match</span>
                          </div>
                        </div>
                        <div className="nl-rule-preview-candidate-meta">
                          <span>Parent path: {candidate.parentPath.join(' / ')}</span>
                          <span>Reasons: {candidate.matchReasons.join(', ')}</span>
                        </div>
                      </div>
                    </label>
                  )
                })}
              </div>
            )}
          </div>

          <div className="nl-rule-preview-draft-card">
            <div className="nl-rule-preview-card-header">
              <div>
                <h3 className="nl-rule-preview-card-title">Draft Rule DSL</h3>
                <p className="nl-rule-preview-card-subtitle">
                  The draft suggestion is created in the active workspace even when matching searched a broader scope.
                </p>
              </div>
            </div>

            {!generatedDraft ? (
              <p className="nl-rule-preview-empty">Select one or more candidate attributes to build the draft summary.</p>
            ) : (
              <>
                <div className="nl-rule-preview-summary-row">
                  <span className="nl-rule-preview-summary-label">Draft name</span>
                  <span className="nl-rule-preview-summary-value">{generatedDraft.name}</span>
                </div>
                <div className="nl-rule-preview-summary-row">
                  <span className="nl-rule-preview-summary-label">Draft summary</span>
                  <span className="nl-rule-preview-summary-value">{generatedDraft.summary}</span>
                </div>
                <div className="nl-rule-preview-summary-row">
                  <span className="nl-rule-preview-summary-label">Workspace</span>
                  <span className="nl-rule-preview-summary-value">{formatWorkspaceLabel(generatedDraft.workspaceId)}</span>
                </div>
                {generatedDraft.dsl ? (
                  <>
                    <div className="nl-rule-preview-summary-row">
                      <span className="nl-rule-preview-summary-label">Schema version</span>
                      <span className="nl-rule-preview-summary-value">{generatedDraft.dsl.schemaVersion}</span>
                    </div>
                    <div className="nl-rule-preview-summary-row">
                      <span className="nl-rule-preview-summary-label">Rule kind</span>
                      <span className="nl-rule-preview-summary-value">{formatDslKindLabel(generatedDraft.dsl.rule.kind)}</span>
                    </div>
                    <div className="nl-rule-preview-summary-row">
                      <span className="nl-rule-preview-summary-label">Scope</span>
                      <span className="nl-rule-preview-summary-value">{formatDslScope(generatedDraft.dsl.rule.scope)}</span>
                    </div>
                    <div className="nl-rule-preview-summary-row">
                      <span className="nl-rule-preview-summary-label">Measure</span>
                      <span className="nl-rule-preview-summary-value">{formatDslMeasure(generatedDraft.dsl.rule.measure)}</span>
                    </div>
                    <div className="nl-rule-preview-summary-row">
                      <span className="nl-rule-preview-summary-label">Expectation</span>
                      <span className="nl-rule-preview-summary-value">{formatDslExpectation(generatedDraft.dsl.rule.expectation)}</span>
                    </div>
                    <div className="nl-rule-preview-summary-row">
                      <span className="nl-rule-preview-summary-label">Evidence</span>
                      <span className="nl-rule-preview-summary-value">{formatDslEvidence(generatedDraft.dsl.rule.evidence)}</span>
                    </div>
                    <div className="nl-rule-preview-summary-row">
                      <span className="nl-rule-preview-summary-label">Operations</span>
                      <span className="nl-rule-preview-summary-value">{formatDslOperations(generatedDraft.dsl.rule.operations)}</span>
                    </div>
                  </>
                ) : (
                  <div className="nl-rule-preview-summary-row">
                    <span className="nl-rule-preview-summary-label">DSL preview</span>
                    <span className="nl-rule-preview-summary-value">Preview data is not available from this response yet.</span>
                  </div>
                )}
                {previewResult.parsedCondition && (
                  <div className="nl-rule-preview-summary-row">
                    <span className="nl-rule-preview-summary-label">Selection rule</span>
                    <span className="nl-rule-preview-summary-value">Choose one target and one condition attribute from the same object version.</span>
                  </div>
                )}
                <div className="nl-rule-preview-selection-list">
                  {selectedCandidates.map(candidate => (
                    <div key={candidate.attributeId} className="nl-rule-preview-selection-item">
                      <strong>{candidate.attributeName}</strong>
                      {candidate.matchRoles.length > 0 && (
                        <span>{candidate.matchRoles.map(formatRoleLabel).join(' / ')}</span>
                      )}
                      <span>{candidate.parentPath.join(' / ')}</span>
                      {candidate.workspaceId !== currentWorkspaceId && (
                        <span className="nl-rule-preview-selection-note">
                          Matched in {formatWorkspaceLabel(candidate.workspaceId)}; draft still saves to {formatWorkspaceLabel(currentWorkspaceId || '')}.
                        </span>
                      )}
                    </div>
                  ))}
                </div>

                <div className="nl-rule-preview-actions">
                  <Button type="button" onClick={handleCreateDraft}>
                    {isSaving ? (analysisProvider === 'llm' ? 'Queueing Draft...' : 'Saving Draft...') : (analysisProvider === 'llm' ? 'Queue Draft Suggestion' : 'Create Draft Suggestion')}
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
