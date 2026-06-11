import React, { useEffect, useRef, useState } from 'react'
import { useSuggestions } from '../hooks/useSuggestions'
import { Suggestion } from '../types/rules'
import { AppButton, AppIcon, AppPageHeader, AppPageShell, AppSelect, type AppIconName } from './app-primitives'
import { useNotifications } from '../hooks/useContexts'
import { useAuth } from '../hooks/useKeycloak'
import { useAsyncRequests, useTrackedAsyncRequest } from '../hooks/useAsyncRequests'
import { AgentChatPanel } from './AgentChatPanel'
import { RecommendationAssistant } from './RecommendationAssistant'
import { NaturalLanguageRuleDraftPreview } from './NaturalLanguageRuleDraft'
import './Suggestions.css'

export const Suggestions: React.FC = () => {
  const auth = useAuth()
  const { addNotification } = useNotifications()
  const { trackProfilingRequest, trackNaturalLanguageDraftRequest } = useAsyncRequests()
  const [selectedDataSourceId, setSelectedDataSourceId] = useState<string>('')
  const {
    suggestions,
    dataSources,
    profilingRequests,
    naturalLanguageRequests,
    hasProfilingPermission,
    loading,
    loadingDataSources,
    loadingProfilingRequests,
    error,
    profilingRequestsError,
    acceptSuggestion,
    dismissSuggestion,
    generateNaturalLanguagePreview,
    createNaturalLanguageDraftSuggestion,
    recordNaturalLanguagePreviewTelemetry,
    requestProfiling,
    getProfilingRequestStatus,
    refreshProfilingRequests,
    refetch,
    previewSample,
    previewSuggestions,
  } = useSuggestions(selectedDataSourceId || undefined)

  useEffect(() => {
    try {
      console.debug('[Suggestions] hook state', JSON.stringify({
        suggestionsCount: suggestions.length,
        dataSourcesCount: dataSources.length,
        hasProfilingPermission,
        loading,
        loadingDataSources,
        error: error || null,
      }))
    } catch {}
  }, [suggestions, dataSources, hasProfilingPermission, loading, loadingDataSources, error])
  const [actionInProgress, setActionInProgress] = useState<Record<string, boolean>>({})
  const [isRequestingProfiling, setIsRequestingProfiling] = useState(false)
  const [activeProfilingTaskId, setActiveProfilingTaskId] = useState<string | null>(null)
  const [profilingFeedback, setProfilingFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [activeDraftTaskId, setActiveDraftTaskId] = useState<string | null>(null)
  const [newSuggestionIds, setNewSuggestionIds] = useState<Set<string>>(new Set())
  const baselineSuggestionIdsRef = useRef<Set<string> | null>(null)
  const awaitingRefreshRef = useRef(false)
  const handledProfilingTaskRef = useRef<string>('')
  const handledDraftTaskRef = useRef<string>('')
  const activeProfilingTask = useTrackedAsyncRequest(activeProfilingTaskId)
  const activeDraftTask = useTrackedAsyncRequest(activeDraftTaskId)
  const isPollingProfilingStatus = activeProfilingTask?.status === 'pending' || activeProfilingTask?.status === 'running'

  useEffect(() => {
    if (!awaitingRefreshRef.current || !baselineSuggestionIdsRef.current) return

    const baseline = baselineSuggestionIdsRef.current
    const added = suggestions
      .filter(s => !baseline.has(s.id))
      .map(s => s.id)

    setNewSuggestionIds(new Set(added))
    awaitingRefreshRef.current = false
    baselineSuggestionIdsRef.current = null

    if (added.length > 0) {
      addNotification({
        type: 'success',
        title: 'New Suggestions Available',
        message: `${added.length} new suggestion${added.length > 1 ? 's' : ''} added after profiling.`,
      })
      setProfilingFeedback({
        type: 'success',
        text: `Profiling completed. ${added.length} new suggestion${added.length > 1 ? 's' : ''} added.`,
      })
    } else {
      addNotification({
        type: 'info',
        title: 'Profiling Completed',
        message: 'Profiling completed and suggestions were refreshed.',
      })
      setProfilingFeedback({
        type: 'success',
        text: 'Profiling completed. Suggestions have been refreshed.',
      })
    }
  }, [suggestions, addNotification])

  useEffect(() => {
    // Follow HOWTO: do NOT implement implicit fallbacks.
    // If data sources are loading, wait. If none are configured, surface a clear message.
    if (loadingDataSources) return

    if (dataSources.length === 0) {
      setProfilingFeedback({ type: 'error', text: 'No data sources configured. Please add a data source to request profiling.' })
      // ensure selection is empty so user must choose explicitly
      if (selectedDataSourceId) setSelectedDataSourceId('')
      return
    }

    // If the previously selected source no longer exists, clear it so the user must re-select.
    const currentSelectionExists = dataSources.some(source => source.dataSourceId === selectedDataSourceId)
    if (!currentSelectionExists && selectedDataSourceId) {
      setSelectedDataSourceId('')
    }

    // Clear any previous "no data sources" feedback once data sources arrive
    if (dataSources.length > 0 && profilingFeedback) {
      setProfilingFeedback(null)
    }
  }, [loadingDataSources, dataSources, selectedDataSourceId])

  const getConfidenceBadgeClass = (score: number) => {
    if (score >= 0.8) return 'high'
    if (score >= 0.6) return 'medium'
    return 'low'
  }

  const getConfidenceLabel = (score: number) => {
    if (score >= 0.8) return 'High'
    if (score >= 0.6) return 'Medium'
    return 'Low'
  }

  const getRuleTypeIcon = (ruleType: string): AppIconName => {
    switch (ruleType) {
      case 'NOT_NULL':
        return 'warning'
      case 'UNIQUE':
        return 'padlock-closed'
      case 'FORMAT_VALIDATION':
        return 'document'
      case 'RANGE_CHECK':
        return 'line-chart'
      case 'REFERENTIAL_INTEGRITY':
        return 'link'
      case 'UNIQUENESS':
        return 'padlock-closed'
      case 'PRESENT':
        return 'warning'
      case 'REGEX':
        return 'document'
      case 'RANGE':
        return 'line-chart'
      case 'ALLOWLIST':
        return 'book'
      case 'FRESHNESS':
        return 'clock'
      default:
        return 'lightbulb'
    }
  }

  const handleAccept = async (suggestionId: string) => {
    setActionInProgress(prev => ({ ...prev, [suggestionId]: true }))
    const success = await acceptSuggestion(suggestionId)
    addNotification({
      type: success ? 'success' : 'error',
      title: success ? 'Suggestion Accepted' : 'Accept Failed',
      message: success
        ? 'The suggestion was accepted and a rule was created.'
        : 'Could not accept suggestion. Please try again.',
      relatedId: suggestionId,
    })
    setActionInProgress(prev => ({ ...prev, [suggestionId]: false }))
  }

  const handleDismiss = async (suggestionId: string) => {
    setActionInProgress(prev => ({ ...prev, [suggestionId]: true }))
    const success = await dismissSuggestion(suggestionId)
    addNotification({
      type: success ? 'success' : 'error',
      title: success ? 'Suggestion Dismissed' : 'Dismiss Failed',
      message: success
        ? 'The suggestion was dismissed.'
        : 'Could not dismiss suggestion. Please try again.',
      relatedId: suggestionId,
    })
    setActionInProgress(prev => ({ ...prev, [suggestionId]: false }))
  }

  const handleRequestProfiling = async () => {
    if (!selectedDataSourceId) return

    setIsRequestingProfiling(true)
    setProfilingFeedback(null)
    baselineSuggestionIdsRef.current = new Set(suggestions.map(s => s.id))
    setNewSuggestionIds(new Set())

    const result = await requestProfiling(selectedDataSourceId)

    setProfilingFeedback({
      type: result.success ? 'success' : 'error',
      text: result.message,
    })

    addNotification({
      type: result.success ? 'success' : 'error',
      title: result.success ? 'Profiling Request Started' : 'Profiling Request Failed',
      message: result.message,
      relatedId: selectedDataSourceId,
    })

    if (result.success && result.profilingRequestId) {
      if (!result.eventsUrl) {
        throw new Error('Profiling request did not return events_url.')
      }
      await refreshProfilingRequests()
      const selectedSource = dataSources.find(source => source.dataSourceId === selectedDataSourceId)
      const taskId = trackProfilingRequest({
        requestId: result.profilingRequestId,
        eventsUrl: result.eventsUrl,
        dataSourceId: selectedDataSourceId,
        dataSourceName: selectedSource?.name || selectedDataSourceId,
        mode: selectedSource?.sourceType === 'mock' ? 'mock-preview' : 'profiling',
      })
      handledProfilingTaskRef.current = ''
      setActiveProfilingTaskId(taskId)
    }

    setIsRequestingProfiling(false)
  }

  useEffect(() => {
    if (!activeDraftTask) return

    if (activeDraftTask.status === 'pending' || activeDraftTask.status === 'running') {
      return
    }

    const handledKey = `${activeDraftTask.id}:${activeDraftTask.status}`
    if (handledDraftTaskRef.current === handledKey) {
      return
    }
    handledDraftTaskRef.current = handledKey

    if (activeDraftTask.status === 'completed') {
      void (async () => {
        await refetch()
        addNotification({
          type: 'success',
          title: 'Draft Suggestion Ready',
          message: 'Draft suggestion creation completed and suggestions were refreshed.',
          relatedId: activeDraftTask.requestId,
        })
      })()
      return
    }

    if (activeDraftTask.status === 'failed' || activeDraftTask.status === 'timed_out') {
      addNotification({
        type: 'error',
        title: 'Draft Suggestion Failed',
        message: activeDraftTask.errorMessage || activeDraftTask.message || 'Draft suggestion request failed. Check recent notifications for details.',
        relatedId: activeDraftTask.requestId,
      })
    }
  }, [activeDraftTask, addNotification, refetch])

  useEffect(() => {
    if (!activeProfilingTask) return

    if (activeProfilingTask.status === 'pending' || activeProfilingTask.status === 'running') {
      void refreshProfilingRequests()
      return
    }

    const handledKey = `${activeProfilingTask.id}:${activeProfilingTask.status}`
    if (handledProfilingTaskRef.current === handledKey) {
      return
    }
    handledProfilingTaskRef.current = handledKey

    if (activeProfilingTask.status === 'completed') {
      awaitingRefreshRef.current = true
      void (async () => {
        if (activeProfilingTask.metadata?.mode === 'mock-preview') {
          await getProfilingRequestStatus(activeProfilingTask.requestId)
        }
        await Promise.all([refetch(), refreshProfilingRequests()])
        setProfilingFeedback({
          type: 'success',
          text: activeProfilingTask.metadata?.mode === 'mock-preview'
            ? 'Mock data generation completed. Suggestions have been refreshed.'
            : 'Profiling completed. Suggestions have been refreshed.',
        })
      })()
      return
    }

    if (activeProfilingTask.status === 'failed' || activeProfilingTask.status === 'timed_out') {
      void refreshProfilingRequests()
      setProfilingFeedback({
        type: 'error',
        text: activeProfilingTask.errorMessage || activeProfilingTask.message || 'Profiling failed. Check recent requests below for details.',
      })
    }
  }, [activeProfilingTask, getProfilingRequestStatus, refetch, refreshProfilingRequests])

  const [showPreviewSample, setShowPreviewSample] = useState(false)
  const [showPreviewSuggestions, setShowPreviewSuggestions] = useState(false)

  // Only allow requesting profiling when a valid data source is explicitly selected
  const selectedSourceExists = Boolean(selectedDataSourceId && dataSources.some(ds => ds.dataSourceId === selectedDataSourceId))
  const canRequestProfiling = selectedSourceExists && !isRequestingProfiling && !loadingDataSources

  const selectedSource = dataSources.find(ds => ds.dataSourceId === selectedDataSourceId)
  const showSampleToggleVisible = Boolean(selectedSource && (selectedSource.sourceType === 'mock' || selectedDataSourceId === 'mock-preview-source'))
  const showProfiledToggleVisible = Boolean(previewSuggestions && previewSuggestions.length > 0)

  const getCreatedAtLabel = (createdAt?: string) => {
    if (!createdAt) return '—'
    const date = new Date(createdAt)
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString()
  }

  const extractColumnName = (expression?: string, name?: string) => {
    if (!expression && !name) return '—'
    
    // Try to extract column name from expression (e.g., "column_name IS NOT NULL" → "column_name")
    if (expression) {
      const match = expression.match(/^(\w+)\s|COUNT\(DISTINCT\s+(\w+)\)|COUNT\((\w+)\)/)
      if (match) {
        return match[1] || match[2] || match[3]
      }
    }
    
    // Try to extract from name (e.g., "customer_id is not null" → "customer_id")
    if (name) {
      const match = name.match(/^(\w+)\s/)
      if (match) return match[1]
    }
    
    return expression || name || '—'
  }

  const getDataSourceName = (dataSourceId: string) => {
    const source = dataSources.find(ds => ds.dataSourceId === dataSourceId)
    if (!source && dataSourceId.startsWith('nl-preview:')) {
      return `Natural-language draft · ${dataSourceId.replace('nl-preview:', '').replace(/[-_]+/g, ' ')}`
    }
    return source ? source.name : dataSourceId
  }

  const getDateTimeLabel = (value?: string) => {
    if (!value) return '—'
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
  }

  const getProfilingStatusLabel = (status?: string) => {
    const normalizedStatus = (status || 'unknown').toLowerCase()
    return normalizedStatus.charAt(0).toUpperCase() + normalizedStatus.slice(1)
  }

  const getProfilingStatusClass = (status?: string) => `status-${(status || 'unknown').toLowerCase()}`

  const accessibleWorkspaceIds = Array.from(
    new Set(
      (auth.user?.workspaceRoles || [])
        .map(workspaceRole => String(workspaceRole.workspaceId || '').trim())
        .filter(Boolean),
    ),
  )

  useEffect(() => {
    // debug aid: show selection and availability to help diagnose why button may be disabled
    try {
      console.debug('[Suggestions] selection debug', {
        selectedDataSourceId,
        selectedSourceExists,
        canRequestProfiling,
        loadingDataSources,
        dataSourcesCount: dataSources.length,
      })
    } catch {}
  }, [selectedDataSourceId, selectedSourceExists, canRequestProfiling, loadingDataSources, dataSources])

  return (
    <AppPageShell className="suggestions-container">
      <AppPageHeader
        className="page-header"
        title="AI-Powered Suggestions"
        description="Get intelligent recommendations for rules, monitors, and data asset definitions based on your data patterns"
      />

      <div className="suggestions-content">
        <section className="suggestions-pane" aria-label="Suggestions and rule draft preview">
          <RecommendationAssistant
            canCreateRule={auth.canCreateRule?.() ?? false}
            naturalLanguageRequests={naturalLanguageRequests}
            generatePreview={generateNaturalLanguagePreview}
            createDraftSuggestion={createNaturalLanguageDraftSuggestion}
          />

          <AgentChatPanel
            defaultAgentType="dq_rule"
            defaultPrompt="Help me turn a natural-language rule description into a precise, testable data quality rule suggestion for this workspace. Suggest candidate attributes, the expected condition, and a safe validation plan."
            title="Rule drafting assistant"
            description="Use the dq-llm agent to refine natural-language rule text into a concrete suggestion before you generate or save a draft."
          />

          <NaturalLanguageRuleDraftPreview
            canCreateRule={auth.canCreateRule?.() ?? false}
            currentWorkspaceId={auth.currentWorkspaceId}
            accessibleWorkspaceIds={accessibleWorkspaceIds}
            generatePreview={generateNaturalLanguagePreview}
            createDraftSuggestion={createNaturalLanguageDraftSuggestion}
            recordTelemetry={recordNaturalLanguagePreviewTelemetry}
            onDraftCreated={(result) => {
              if (result.queued && result.requestId) {
                const taskId = trackNaturalLanguageDraftRequest({
                  requestId: result.requestId,
                  workspaceId: auth.currentWorkspaceId || '',
                  workspaceName: (auth.currentWorkspaceId || 'current workspace').replace(/[-_]+/g, ' '),
                  analysisProvider: 'llm',
                  analysisType: 'draft',
                })
                handledDraftTaskRef.current = ''
                setActiveDraftTaskId(taskId)
              }

              addNotification({
                type: result.success ? 'success' : 'error',
                title: result.queued ? 'Draft Suggestion Queued' : result.success ? 'Draft Suggestion Created' : 'Draft Suggestion Failed',
                message: result.message,
                relatedId: result.suggestion?.id || result.requestId,
              })
            }}
          />

            {loading && (
              <div className="loading-state">
                <div className="spinner"></div>
                <p>Loading suggestions...</p>
              </div>
            )}

            {error && (
              <div className="error-state">
                <AppIcon name="info-circle" />
                <p>{error}</p>
              </div>
            )}

            {!loading && suggestions.length === 0 && !error && (
              <div className="empty-state">
                <AppIcon name="lightbulb" />
                <h3>No suggestions available yet</h3>
                <p>
                  Run data profiling on your data sources to generate intelligent suggestions.
                </p>
              </div>
            )}

            {!loading && !error && hasProfilingPermission && (
              <div className="profiling-request-section">
                <h3>Request Data Profiling</h3>
                <p className="profiling-request-description">
                  Select a data source to analyze and generate AI-powered rule suggestions.
                </p>
                <div className="profiling-request-panel">
                  <div className="profiling-request-row">
                    <div className="profiling-request-left">
                      <div className="profiling-controls-box">
                        <div className="profiling-controls-left">
                          <div className="profiling-inline-label">Select data source</div>
                          <AppSelect
                            id="profiling-data-source"
                            label="Select data source"
                            value={selectedDataSourceId}
                            onChange={setSelectedDataSourceId}
                            options={dataSources.map(source => ({
                              value: source.dataSourceId,
                              label: `${source.name} (${source.sourceType})`
                            }))}
                            fieldClassName="profiling-inline-select"
                          />
                        </div>

                        <div className="profiling-controls-right">
                          <AppButton
                            onClick={handleRequestProfiling}
                            disabled={!canRequestProfiling}
                          >
                            {isRequestingProfiling ? 'Requesting…' : 'Run Data Profiling'}
                          </AppButton>
                        </div>
                      </div>

                      <div className="preview-controls">
                        {showSampleToggleVisible ? (
                          <AppButton
                            variant="secondary"
                            onClick={() => setShowPreviewSample(prev => !prev)}
                          >
                            {showPreviewSample ? 'Hide Sample Data' : 'Show Sample Data'}
                          </AppButton>
                        ) : null}
                        {showProfiledToggleVisible ? (
                          <AppButton
                            variant="secondary"
                            onClick={() => setShowPreviewSuggestions(prev => !prev)}
                          >
                            {showPreviewSuggestions ? 'Hide Profiled Suggestions' : 'Show Profiled Suggestions'}
                          </AppButton>
                        ) : null}
                        {!selectedDataSourceId && !loadingDataSources && dataSources.length > 0 ? (
                          <div className="profiling-select-helper">Please choose a data source to enable profiling.</div>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  {profilingFeedback && (
                    <p className={`profiling-feedback profiling-feedback-${profilingFeedback.type}`}>
                      {profilingFeedback.text}
                      {isPollingProfilingStatus && (
                        <span className="profiling-polling-indicator" aria-live="polite">
                          <span className="profiling-polling-dot" aria-hidden="true"></span>
                          Checking status…
                        </span>
                      )}
                    </p>
                  )}
                </div>

                {showPreviewSample && previewSample && previewSample.length > 0 ? (
                  <div className="preview-sample-panel">
                    <h4>Sample Data (before profiling)</h4>
                    <pre className="preview-json">{JSON.stringify(previewSample, null, 2)}</pre>
                  </div>
                ) : null}

                {showPreviewSuggestions && previewSuggestions && previewSuggestions.length > 0 ? (
                  <div className="preview-suggestions-panel">
                    <h4>Profiled Suggestions (mock)</h4>
                    <pre className="preview-json">{JSON.stringify(previewSuggestions, null, 2)}</pre>
                  </div>
                ) : null}

                <div className="profiling-history-panel">
                  <div className="profiling-history-header">
                    <div>
                      <h4>Recent Profiling Requests</h4>
                      <p>
                        {selectedDataSourceId
                          ? `Showing your recent profiling requests for ${getDataSourceName(selectedDataSourceId)}.`
                          : 'Showing your recent profiling requests across data sources.'}
                      </p>
                    </div>
                    <AppButton variant="tertiary" onClick={() => void refreshProfilingRequests()}>
                      Refresh
                    </AppButton>
                  </div>

                  {loadingProfilingRequests ? (
                    <p className="profiling-history-empty">Loading profiling history...</p>
                  ) : profilingRequestsError ? (
                    <p className="profiling-history-empty profiling-history-error">{profilingRequestsError}</p>
                  ) : profilingRequests.length === 0 ? (
                    <p className="profiling-history-empty">
                      {selectedDataSourceId
                        ? 'No profiling requests found for the selected data source.'
                        : 'No profiling requests found yet.'}
                    </p>
                  ) : (
                    <div className="profiling-history-list">
                      {profilingRequests.map(request => (
                        <div key={request.id} className="profiling-history-item">
                          <div className="profiling-history-title-row">
                            <div>
                              <div className="profiling-history-source">{getDataSourceName(request.dataSourceId)}</div>
                              <div className="profiling-history-meta">
                                <span>Requested {getDateTimeLabel(request.requestedAt)}</span>
                                <span>Request {request.id}</span>
                                {request.jobId ? <span>Job {request.jobId}</span> : null}
                              </div>
                            </div>
                            <span className={`profiling-history-status ${getProfilingStatusClass(request.status)}`}>
                              {getProfilingStatusLabel(request.status)}
                            </span>
                          </div>

                          <div className="profiling-history-timestamps">
                            <span>Started {getDateTimeLabel(request.startedAt)}</span>
                            <span>Completed {getDateTimeLabel(request.completedAt)}</span>
                          </div>

                          {request.errorMessage ? (
                            <p className="profiling-history-error-text">{request.errorMessage}</p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {!loading && !error && !hasProfilingPermission && (
              <p className="profiling-permission-note">
                You don't currently have permission to request profiling.
              </p>
            )}

            {!loading && suggestions.length > 0 && (
              <div className="suggestions-list">
                <div className="suggestions-summary">
                  <p>{suggestions.length} suggestion{suggestions.length !== 1 ? 's' : ''} available</p>
                </div>
                {suggestions.map((suggestion: Suggestion) => (
                  <div key={suggestion.id} className="suggestion-card">
                    <div className="suggestion-header">
                      <div className="suggestion-title-group">
                        <span className="rule-type-icon"><AppIcon name={getRuleTypeIcon(suggestion.ruleType)} /></span>
                        <h3 className="suggestion-title">{suggestion.suggestedRule.name}</h3>
                      </div>
                      <div className="suggestion-badges">
                        {newSuggestionIds.has(suggestion.id) && (
                          <span className="new-badge">New</span>
                        )}
                        <span className={`confidence-badge ${getConfidenceBadgeClass(suggestion.confidenceScore)}`}>
                          {getConfidenceLabel(suggestion.confidenceScore)} ({(suggestion.confidenceScore * 100).toFixed(0)}%)
                        </span>
                        {suggestion.status !== 'pending' && (
                          <span className={`status-badge dq-status-badge status-${suggestion.status}`}>
                            {suggestion.status.charAt(0).toUpperCase() + suggestion.status.slice(1)}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="suggestion-body">
                      <div className="suggestion-context">
                        <div className="context-item">
                          <span className="context-label">Data Source</span>
                          <span className="context-value">{getDataSourceName(suggestion.dataSourceId)}</span>
                        </div>
                        <div className="context-item">
                          <span className="context-label">Attribute / Column</span>
                          <span className="context-value">{extractColumnName(suggestion.suggestedRule.expression, suggestion.suggestedRule.name)}</span>
                        </div>
                        <div className="context-item">
                          <span className="context-label">Dimension</span>
                          <span className="context-value">{suggestion.suggestedRule.dimension || 'Data Quality'}</span>
                        </div>
                      </div>

                      <div className="suggestion-section">
                        <label>Description</label>
                        <p>{suggestion.suggestedRule.description}</p>
                      </div>

                      {suggestion.reason && (
                        <div className="suggestion-section">
                          <label>Why this rule?</label>
                          <p>{suggestion.reason}</p>
                        </div>
                      )}

                      <div className="suggestion-details">
                        <div className="detail-item">
                          <span className="detail-label">Rule Type:</span>
                          <span className="detail-value">{suggestion.ruleType.replace(/_/g, ' ')}</span>
                        </div>
                        <div className="detail-item">
                          <span className="detail-label">Confidence:</span>
                          <span className="detail-value">{(suggestion.confidenceScore * 100).toFixed(0)}%</span>
                        </div>
                        <div className="detail-item">
                          <span className="detail-label">Created:</span>
                          <span className="detail-value">{getCreatedAtLabel(suggestion.createdAt)}</span>
                        </div>
                      </div>

                      {suggestion.suggestedRule.expression && (
                        <div className="suggestion-section">
                          <label>Expression</label>
                          <pre className="expression-block">{suggestion.suggestedRule.expression}</pre>
                        </div>
                      )}
                    </div>

                    <div className="suggestion-actions">
                      {suggestion.status === 'pending' && (
                        <div className="btn-action-group">
                          <AppButton
                            className="btn-action"
                            variant="secondary"
                            onClick={() => handleAccept(suggestion.id)}
                            disabled={Boolean(actionInProgress[suggestion.id])}
                          >
                            <AppIcon name="check" />
                            Accept
                          </AppButton>
                          <AppButton
                            className="btn-action"
                            variant="tertiary"
                            onClick={() => handleDismiss(suggestion.id)}
                            disabled={Boolean(actionInProgress[suggestion.id])}
                          >
                            <AppIcon name="times" />
                            Dismiss
                          </AppButton>
                        </div>
                      )}
                      {suggestion.status === 'accepted' && (
                        <div className="btn-action-group">
                          <AppButton
                            className="btn-action"
                            variant="tertiary"
                            onClick={() => handleDismiss(suggestion.id)}
                            disabled={Boolean(actionInProgress[suggestion.id])}
                          >
                            <AppIcon name="trash" />
                            Remove
                          </AppButton>
                        </div>
                      )}
                      {suggestion.status === 'applied' && (
                        <div className="applied-message">
                          <AppIcon name="check-circle" />
                          <span>Rule created from this suggestion</span>
                        </div>
                      )}
                      {suggestion.status === 'dismissed' && (
                        <div className="dismissed-message">
                          <AppIcon name="times-circle-fill" />
                          <span>Suggestion dismissed</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
        </section>

      </div>
    </AppPageShell>
  )
}

