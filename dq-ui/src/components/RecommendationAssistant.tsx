import React, { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../hooks/useKeycloak'
import { useNotifications } from '../hooks/useContexts'
import { useAsyncRequests, useTrackedAsyncRequest } from '../hooks/useAsyncRequests'
import type {
  NaturalLanguageAnalysisProvider,
  NaturalLanguageDraftSuggestionRequest,
  NaturalLanguageDraftSuggestionResult,
  NaturalLanguagePreviewResult,
  NaturalLanguageRequestHistoryItem,
  NaturalLanguageSearchScope,
} from '../hooks/useSuggestions'
import { AppSelect } from './app-primitives'
import { Button, SecondaryButton } from './Button'

type RecommendationTargetType = 'rule' | 'monitor' | 'data_asset_definition'
type RecommendationStatus = 'queued' | 'ready' | 'confirmed' | 'rejected' | 'failed'

interface RecommendationHistoryEntry {
  id: string
  targetType: RecommendationTargetType
  prompt: string
  workspaceId: string
  analysisProvider: NaturalLanguageAnalysisProvider
  searchScope: NaturalLanguageSearchScope
  status: RecommendationStatus
  createdAt: string
  title: string
  reason: string
  candidateSummary: string
  requestId?: string
  suggestionId?: string
  decisionAt?: string
  decisionNote?: string
}

interface RecommendationAssistantProps {
  canCreateRule: boolean
  naturalLanguageRequests: NaturalLanguageRequestHistoryItem[]
  generatePreview: (request: {
    prompt: string
    searchScope: NaturalLanguageSearchScope
    currentWorkspaceId: string
    analysisProvider: NaturalLanguageAnalysisProvider
  }) => Promise<NaturalLanguagePreviewResult>
  createDraftSuggestion: (request: NaturalLanguageDraftSuggestionRequest) => Promise<NaturalLanguageDraftSuggestionResult>
}

const RECOMMENDATION_TARGET_OPTIONS: Array<{
  value: RecommendationTargetType
  label: string
  description: string
}> = [
  {
    value: 'rule',
    label: 'Rule',
    description: 'Suggest a reusable data quality check.',
  },
  {
    value: 'monitor',
    label: 'Monitor',
    description: 'Suggest an operational monitor for the same signal.',
  },
  {
    value: 'data_asset_definition',
    label: 'Data Asset definition',
    description: 'Suggest a governed data asset contract or definition.',
  },
]

const ANALYSIS_PROVIDER_OPTIONS: Array<{ value: NaturalLanguageAnalysisProvider; label: string }> = [
  { value: 'rapidfuzz', label: 'RapidFuzz (local)' },
  { value: 'llm', label: 'LLM service (dq-llm)' },
]

const formatWorkspaceLabel = (workspaceId: string) => workspaceId.replace(/[-_]+/g, ' ')

const formatTargetLabel = (targetType: RecommendationTargetType) => {
  const option = RECOMMENDATION_TARGET_OPTIONS.find((entry) => entry.value === targetType)
  return option?.label || 'Recommendation'
}

const makeId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  return `rec-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

const extractPreviewPayload = (result: unknown) => {
  if (!result || typeof result !== 'object') return null
  const requestRecord = result as { result?: unknown }
  return requestRecord.result || result
}

const snakeToCamelKey = (value: string) => value.replace(/_([a-z])/g, (_, character: string) => character.toUpperCase())

const snakeToCamelDeep = (value: unknown): unknown => {
  if (Array.isArray(value)) {
    return value.map((entry) => snakeToCamelDeep(entry))
  }

  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).reduce<Record<string, unknown>>((accumulator, [key, entry]) => {
      accumulator[snakeToCamelKey(key)] = snakeToCamelDeep(entry)
      return accumulator
    }, {})
  }

  return value
}

const mapRequestStatusToRecommendationStatus = (status: NaturalLanguageRequestHistoryItem['status']): RecommendationStatus => {
  if (status === 'failed') return 'failed'
  if (status === 'completed') return 'ready'
  return 'queued'
}

const buildHistoryEntryFromRequest = (request: NaturalLanguageRequestHistoryItem): RecommendationHistoryEntry => {
  const rawPreview = request.result && typeof request.result === 'object' && !Array.isArray(request.result)
    ? ((request.result as Record<string, unknown>).candidate_attributes || (request.result as Record<string, unknown>).draft_rule_preview
      ? snakeToCamelDeep(request.result)
      : null)
    : null

  const normalizedPreview = rawPreview && typeof rawPreview === 'object'
    ? (rawPreview as NaturalLanguagePreviewResult['preview'])
    : null

  const previewResult = normalizedPreview
    ? {
        success: true,
        message: 'Recommendation preview generated.',
        preview: normalizedPreview,
      } satisfies NaturalLanguagePreviewResult
    : null

  return {
    id: request.requestId,
    targetType: 'rule',
    prompt: request.prompt,
    workspaceId: request.currentWorkspaceId,
    analysisProvider: request.analysisProvider,
    searchScope: request.searchScope,
    status: mapRequestStatusToRecommendationStatus(request.status),
    createdAt: request.requestedAt || request.startedAt || request.completedAt || new Date().toISOString(),
    title: request.analysisType === 'draft' ? 'Draft suggestion request' : 'Recommendation preview',
    reason: request.errorMessage || (previewResult ? buildRecommendationReason(previewResult, 'rule') : 'Recommendation request recorded in Postgres.'),
    candidateSummary: previewResult ? buildCandidateSummary(previewResult) : 'No candidate attributes were matched.',
    requestId: request.requestId,
    suggestionId: request.suggestionId || undefined,
  }
}

const buildRecommendationReason = (previewResult: NaturalLanguagePreviewResult, targetType: RecommendationTargetType): string => {
  const preview = previewResult.preview
  const candidate = preview?.candidateAttributes?.[0]
  const reasons = [
    candidate?.matchReasons?.[0],
    preview?.parsedCondition ? `Parsed condition: ${preview.parsedCondition.attributeTerm} ${preview.parsedCondition.operator} ${preview.parsedCondition.value}.` : null,
    preview?.requiresStewardConfirmation ? 'Steward confirmation is required before saving.' : null,
    targetType === 'monitor' ? 'The monitor recommendation keeps the same signal visible to operations.' : null,
    targetType === 'data_asset_definition' ? 'The data asset definition keeps the governed contract aligned with the prompt.' : null,
  ].filter(Boolean)

  return reasons.length > 0
    ? reasons.join(' ')
    : 'The prompt matched the current workspace catalog and produced a preview-first recommendation.'
}

const buildCandidateSummary = (previewResult: NaturalLanguagePreviewResult): string => {
  const preview = previewResult.preview
  if (!preview || preview.candidateAttributes.length === 0) {
    return 'No candidate attributes were matched.'
  }

  return preview.candidateAttributes
    .slice(0, 3)
    .map((candidate) => candidate.attributeName)
    .join(', ')
}

const buildRecommendationTitle = (targetType: RecommendationTargetType, previewResult: NaturalLanguagePreviewResult, prompt: string) => {
  const previewName = previewResult.preview?.draftRulePreview?.name || prompt.trim() || 'Draft recommendation'
  return `${formatTargetLabel(targetType)}: ${previewName}`
}

export const RecommendationAssistant: React.FC<RecommendationAssistantProps> = ({
  canCreateRule,
  naturalLanguageRequests,
  generatePreview,
  createDraftSuggestion,
}) => {
  const auth = useAuth()
  const { addNotification } = useNotifications()
  const { trackNaturalLanguageDraftRequest } = useAsyncRequests()

  const currentWorkspaceId = auth.currentWorkspaceId || ''
  const accessibleWorkspaceIds = useMemo(() => Array.from(new Set((auth.user?.workspaceRoles || [])
    .map((workspaceRole) => String(workspaceRole.workspaceId || '').trim())
    .filter(Boolean))), [auth.user?.workspaceRoles])

  const backendHistoryEntries = useMemo(
    () => naturalLanguageRequests
      .filter((request) => request.currentWorkspaceId === currentWorkspaceId)
      .map(buildHistoryEntryFromRequest)
      .slice(0, 12),
    [currentWorkspaceId, naturalLanguageRequests],
  )

  const [targetType, setTargetType] = useState<RecommendationTargetType>('rule')
  const [prompt, setPrompt] = useState('')
  const [analysisProvider, setAnalysisProvider] = useState<NaturalLanguageAnalysisProvider>('rapidfuzz')
  const [searchScope, setSearchScope] = useState<NaturalLanguageSearchScope>('current')
  const [previewResult, setPreviewResult] = useState<NaturalLanguagePreviewResult | null>(null)
  const [history, setHistory] = useState<RecommendationHistoryEntry[]>([])
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isConfirming, setIsConfirming] = useState(false)
  const [activeRecommendationRequestId, setActiveRecommendationRequestId] = useState<string | null>(null)
  const [activeRecommendationHistoryId, setActiveRecommendationHistoryId] = useState<string | null>(null)
  const activeRecommendationTask = useTrackedAsyncRequest(activeRecommendationRequestId)

  useEffect(() => {
    setHistory([])
    setPreviewResult(null)
    setStatusMessage(null)
    setErrorMessage(null)
    setActiveRecommendationRequestId(null)
    setActiveRecommendationHistoryId(null)
    setPrompt('')
    setTargetType('rule')
    setAnalysisProvider('rapidfuzz')
    setSearchScope('current')
  }, [currentWorkspaceId])

  useEffect(() => {
    setHistory((currentHistory) => {
      const nextHistory = [...currentHistory]

      backendHistoryEntries.forEach((entry) => {
        if (nextHistory.some((existingEntry) => existingEntry.id === entry.id)) {
          return
        }

        nextHistory.push(entry)
      })

      return nextHistory.slice(0, 12)
    })
  }, [backendHistoryEntries])

  useEffect(() => {
    if (!activeRecommendationTask) return

    if (activeRecommendationTask.status === 'pending' || activeRecommendationTask.status === 'running') {
      return
    }

    const handledPreview = `${activeRecommendationTask.id}:${activeRecommendationTask.status}`

    if (activeRecommendationTask.status === 'completed') {
      const previewPayload = extractPreviewPayload(activeRecommendationTask.result)
      if (previewPayload && activeRecommendationHistoryId) {
        const normalizedPreview = snakeToCamelDeep(previewPayload) as NaturalLanguagePreviewResult['preview']
        const nextPreviewResult = {
          success: true,
          message: 'Recommendation preview generated.',
          preview: normalizedPreview,
        } satisfies NaturalLanguagePreviewResult

        setPreviewResult(nextPreviewResult)
        setHistory((currentHistory) => currentHistory.map((entry) => {
          if (entry.id !== activeRecommendationHistoryId) {
            return entry
          }

          return {
            ...entry,
            status: 'ready',
            reason: buildRecommendationReason(nextPreviewResult, entry.targetType),
            candidateSummary: buildCandidateSummary(nextPreviewResult),
            requestId: activeRecommendationTask.requestId,
          }
        }))
        setStatusMessage('Recommendation preview is ready. Confirm or reject it to record a decision.')
      }

      setActiveRecommendationRequestId(null)
      return
    }

    if (activeRecommendationTask.status === 'failed' || activeRecommendationTask.status === 'timed_out') {
      setHistory((currentHistory) => currentHistory.map((entry) => {
        if (entry.requestId !== activeRecommendationTask.requestId) {
          return entry
        }

        return {
          ...entry,
          status: 'failed',
          decisionAt: new Date().toISOString(),
          decisionNote: activeRecommendationTask.errorMessage || activeRecommendationTask.message || 'Recommendation preview failed.',
        }
      }))
      setErrorMessage(activeRecommendationTask.errorMessage || activeRecommendationTask.message || 'Recommendation preview failed.')
      setStatusMessage(null)
      setActiveRecommendationRequestId(null)
    }

    void handledPreview
  }, [activeRecommendationHistoryId, activeRecommendationTask])

  const availableScopes = useMemo(() => {
    const scopes = [
      { value: 'current', label: 'Current' },
      { value: 'all', label: 'All in Current Workspace' },
    ]

    if (accessibleWorkspaceIds.length > 1) {
      scopes.push({ value: 'all_across_workspaces', label: 'All Across Workspaces' })
    }

    return scopes
  }, [accessibleWorkspaceIds.length])

  const latestHistoryEntry = history[0] || null

  if (!canCreateRule) {
    return null
  }

  const appendHistoryEntry = (entry: RecommendationHistoryEntry) => {
    setHistory((currentHistory) => [entry, ...currentHistory.filter((existingEntry) => existingEntry.id !== entry.id)].slice(0, 12))
  }

  const updateHistoryEntry = (entryId: string, updater: (entry: RecommendationHistoryEntry) => RecommendationHistoryEntry) => {
    setHistory((currentHistory) => currentHistory.map((entry) => (entry.id === entryId ? updater(entry) : entry)))
  }

  const handleGeneratePreview = async () => {
    const trimmedPrompt = prompt.trim()
    setErrorMessage(null)
    setStatusMessage(null)

    if (!currentWorkspaceId) {
      setErrorMessage('Select a workspace before using the assistant.')
      setPreviewResult(null)
      return
    }

    if (!trimmedPrompt) {
      setErrorMessage('Describe the recommendation you want in one sentence.')
      setPreviewResult(null)
      return
    }

    setIsGenerating(true)

    const result = await generatePreview({
      prompt: trimmedPrompt,
      searchScope,
      currentWorkspaceId,
      analysisProvider,
    })

    setIsGenerating(false)

    const historyId = makeId()
    const createdAt = new Date().toISOString()
    const historyEntry: RecommendationHistoryEntry = {
      id: historyId,
      targetType,
      prompt: trimmedPrompt,
      workspaceId: currentWorkspaceId,
      analysisProvider,
      searchScope,
      status: result.queued ? 'queued' : result.success ? 'ready' : 'failed',
      createdAt,
      title: formatTargetLabel(targetType),
      reason: result.success && result.preview ? buildRecommendationReason(result, targetType) : result.message,
      candidateSummary: result.success && result.preview ? buildCandidateSummary(result) : 'No preview available.',
      requestId: result.requestId,
    }

    setActiveRecommendationHistoryId(historyId)

    if (result.queued && result.requestId) {
      setPreviewResult(null)
      appendHistoryEntry(historyEntry)
      setActiveRecommendationRequestId(trackNaturalLanguageDraftRequest({
        requestId: result.requestId,
        workspaceId: currentWorkspaceId,
        workspaceName: formatWorkspaceLabel(currentWorkspaceId),
        analysisProvider,
        analysisType: 'preview',
      }))
      setStatusMessage('Recommendation preview queued. Keep this panel open while the analysis service responds.')
      return
    }

    if (!result.success || !result.preview) {
      appendHistoryEntry(historyEntry)
      setPreviewResult(null)
      setErrorMessage(result.message)
      setStatusMessage(null)
      return
    }

    setPreviewResult(result)
    appendHistoryEntry(historyEntry)
    setStatusMessage('Recommendation preview ready. Confirm or reject it to record a decision.')
  }

  const handleConfirm = async () => {
    if (!currentWorkspaceId) {
      setErrorMessage('Select a workspace before confirming a recommendation.')
      return
    }

    if (!previewResult || !activeRecommendationHistoryId) {
      setErrorMessage('Generate a preview before confirming a recommendation.')
      return
    }

    setIsConfirming(true)
    const decisionAt = new Date().toISOString()

    if (targetType === 'rule') {
      const selectedAttributeIds = previewResult.preview?.candidateAttributes.map((candidate) => candidate.attributeId) || []
      if (selectedAttributeIds.length === 0) {
        setIsConfirming(false)
        setErrorMessage('Select a prompt that matches at least one candidate attribute before saving a rule recommendation.')
        return
      }

      const result = await createDraftSuggestion({
        currentWorkspaceId,
        prompt: prompt.trim(),
        searchScope: previewResult.preview?.searchScope || searchScope,
        analysisProvider,
        selectedAttributeIds,
      })

      setIsConfirming(false)

      if (!result.success) {
        setErrorMessage(result.message)
        return
      }

      updateHistoryEntry(activeRecommendationHistoryId, (entry) => ({
        ...entry,
        status: 'confirmed',
        suggestionId: result.suggestion?.id,
        decisionAt,
        decisionNote: result.message,
      }))
      setStatusMessage('Rule recommendation confirmed and saved as a draft suggestion.')
      addNotification({
        type: 'success',
        title: 'Recommendation Confirmed',
        message: result.message,
        relatedId: result.suggestion?.id || activeRecommendationHistoryId,
      })
      return
    }

    updateHistoryEntry(activeRecommendationHistoryId, (entry) => ({
      ...entry,
      status: 'confirmed',
      decisionAt,
      decisionNote: `${formatTargetLabel(targetType)} recommendation recorded for follow-up.`,
    }))
    setIsConfirming(false)
    setStatusMessage(`${formatTargetLabel(targetType)} recommendation confirmed and recorded in history.`)
    addNotification({
      type: 'success',
      title: 'Recommendation Confirmed',
      message: `${formatTargetLabel(targetType)} recommendation recorded in history.`,
      relatedId: activeRecommendationHistoryId,
    })
  }

  const handleReject = () => {
    if (!activeRecommendationHistoryId) {
      setErrorMessage('Generate a preview before rejecting a recommendation.')
      return
    }

    const decisionAt = new Date().toISOString()
    updateHistoryEntry(activeRecommendationHistoryId, (entry) => ({
      ...entry,
      status: 'rejected',
      decisionAt,
      decisionNote: 'Recommendation rejected before save.',
    }))
    setStatusMessage('Recommendation rejected and retained in history.')
    setErrorMessage(null)
    addNotification({
      type: 'info',
      title: 'Recommendation Rejected',
      message: 'The recommendation was rejected before saving.',
      relatedId: activeRecommendationHistoryId,
    })
  }

  const handleReset = () => {
    setPrompt('')
    setPreviewResult(null)
    setStatusMessage(null)
    setErrorMessage(null)
    setActiveRecommendationRequestId(null)
    setActiveRecommendationHistoryId(null)
  }

  const preview = previewResult?.preview || null
  const previewTargetLabel = preview ? formatTargetLabel(targetType) : ''
  const previewHeadline = preview ? buildRecommendationTitle(targetType, previewResult, prompt) : ''
  const candidateAttributes = preview?.candidateAttributes || []

  return (
    <section className="ai-recommendation-panel" aria-labelledby="ai-recommendation-title">
      <div className="ai-recommendation-header">
        <div>
          <p className="policy-documents-eyebrow">AI assistant</p>
          <h3 id="ai-recommendation-title">Generate recommendations</h3>
          <p>
            Draft rules, monitors, or data asset definitions from a prompt. Preview first, then confirm or reject.
          </p>
        </div>
        <div className="ai-recommendation-workspace-callout">
          <span className="ai-recommendation-workspace-label">Workspace</span>
          <strong>{currentWorkspaceId ? formatWorkspaceLabel(currentWorkspaceId) : 'No workspace selected'}</strong>
        </div>
      </div>

      <div className="ai-recommendation-grid">
        <div className="ai-recommendation-form-card">
          <div className="ai-recommendation-field">
            <span className="ai-recommendation-label">Recommendation target</span>
            <div className="ai-recommendation-target-grid" role="tablist" aria-label="Recommendation target type">
              {RECOMMENDATION_TARGET_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`ai-recommendation-target-btn ${targetType === option.value ? 'active' : ''}`}
                  aria-pressed={targetType === option.value}
                  onClick={() => setTargetType(option.value)}
                >
                  <span className="ai-recommendation-target-label">{option.label}</span>
                  <span className="ai-recommendation-target-description">{option.description}</span>
                </button>
              ))}
            </div>
          </div>

          <label className="ai-recommendation-field" htmlFor="ai-recommendation-prompt">
            <span className="ai-recommendation-label">Prompt</span>
            <textarea
              id="ai-recommendation-prompt"
              className="ai-recommendation-textarea"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Describe the rule, monitor, or data asset definition you want"
              rows={5}
            />
          </label>

          <div className="ai-recommendation-controls">
            <AppSelect
              id="ai-recommendation-search-scope"
              label="Attribute matching scope"
              value={searchScope}
              onChange={(value) => setSearchScope(value as NaturalLanguageSearchScope)}
              options={availableScopes}
            />
          </div>

          <div className="ai-recommendation-controls">
            <AppSelect
              id="ai-recommendation-provider"
              label="Analysis engine"
              value={analysisProvider}
              onChange={(value) => setAnalysisProvider(value as NaturalLanguageAnalysisProvider)}
              options={ANALYSIS_PROVIDER_OPTIONS}
              hint="RapidFuzz stays local. LLM mode queues analysis requests and keeps them visible in history."
            />
          </div>

          <div className="ai-recommendation-actions">
            <Button type="button" onClick={() => void handleGeneratePreview()} disabled={isGenerating}>
              {isGenerating ? 'Generating...' : 'Generate Preview'}
            </Button>
            <SecondaryButton type="button" onClick={handleReset}>
              Reset
            </SecondaryButton>
          </div>

          {errorMessage && (
            <div className="ai-recommendation-alert error" role="alert">
              {errorMessage}
            </div>
          )}

          {statusMessage && !errorMessage && (
            <div className="ai-recommendation-alert success" role="status">
              {statusMessage}
            </div>
          )}

          <div className="ai-recommendation-history-card">
            <div className="ai-recommendation-history-header">
              <div>
                <h4>Prompt and suggestion history</h4>
                <p>Review what was requested, previewed, confirmed, or rejected in this workspace.</p>
              </div>
            </div>

            {history.length === 0 ? (
              <p className="ai-recommendation-history-empty">No prompts have been recorded for this workspace yet.</p>
            ) : (
              <div className="ai-recommendation-history-list">
                {history.map((entry) => (
                  <div key={entry.id} className="ai-recommendation-history-item">
                    <div className="ai-recommendation-history-title-row">
                      <div>
                        <div className="ai-recommendation-history-title">{entry.title}</div>
                        <div className="ai-recommendation-history-meta">
                          <span>{formatTargetLabel(entry.targetType)}</span>
                          <span>{formatWorkspaceLabel(entry.workspaceId)}</span>
                          <span>{entry.analysisProvider}</span>
                        </div>
                      </div>
                      <span className={`ai-recommendation-history-status status-${entry.status}`}>
                        {entry.status.charAt(0).toUpperCase() + entry.status.slice(1)}
                      </span>
                    </div>
                    <p className="ai-recommendation-history-prompt">{entry.prompt}</p>
                    <p className="ai-recommendation-history-reason">{entry.reason}</p>
                    <div className="ai-recommendation-history-footnote">
                      <span>{entry.candidateSummary}</span>
                      <span>{new Date(entry.createdAt).toLocaleString()}</span>
                    </div>
                    {entry.decisionNote && (
                      <p className="ai-recommendation-history-decision">{entry.decisionNote}</p>
                    )}
                    {entry.suggestionId && (
                      <p className="ai-recommendation-history-decision">Draft suggestion: {entry.suggestionId}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="ai-recommendation-preview-card">
          <h4>Recommendation preview</h4>
          {preview ? (
            <>
              <div className="ai-recommendation-preview-meta">
                <span><strong>Target:</strong> {previewTargetLabel}</span>
                  <span><strong>Scope:</strong> {availableScopes.find((option) => option.value === searchScope)?.label || searchScope}</span>
                <span><strong>Workspace:</strong> {currentWorkspaceId ? formatWorkspaceLabel(currentWorkspaceId) : 'No workspace selected'}</span>
              </div>

              <div className="ai-recommendation-preview-summary">
                <strong>{previewHeadline}</strong>
                <p>{preview.draftRulePreview.summary}</p>
              </div>

              <div className="ai-recommendation-preview-reasons">
                <h5>Why this recommendation?</h5>
                <p>{buildRecommendationReason(previewResult, targetType)}</p>
              </div>

              {preview.parsedCondition && (
                <div className="ai-recommendation-preview-condition">
                  <h5>Parsed condition</h5>
                  <p>
                    {preview.parsedCondition.attributeTerm} {preview.parsedCondition.operator} {preview.parsedCondition.value}
                  </p>
                </div>
              )}

              <div className="ai-recommendation-preview-candidates">
                <h5>Candidate attributes</h5>
                {candidateAttributes.length === 0 ? (
                  <p>No candidate attributes matched this prompt.</p>
                ) : (
                  <ul>
                    {candidateAttributes.slice(0, 4).map((candidate) => (
                      <li key={candidate.attributeId}>
                        <strong>{candidate.attributeName}</strong>
                        <span>{candidate.matchReasons?.[0] || 'Matched from the current workspace catalog.'}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="ai-recommendation-preview-actions">
                <Button type="button" onClick={() => void handleConfirm()} disabled={isConfirming}>
                  {targetType === 'rule' ? 'Confirm and Save Draft' : 'Confirm Recommendation'}
                </Button>
                <SecondaryButton type="button" onClick={handleReject}>
                  Reject Recommendation
                </SecondaryButton>
              </div>
            </>
          ) : (
            <div className="ai-recommendation-preview-empty">
              <p>Preview-only until confirmed.</p>
              <p>Use a prompt to generate a recommendation for a rule, monitor, or data asset definition.</p>
            </div>
          )}
          {latestHistoryEntry && (
            <div className="ai-recommendation-preview-footnote">
              Latest history entry: {latestHistoryEntry.title} · {latestHistoryEntry.status}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}