import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { getAuthToken } from '../contexts/AuthContext'
import { useSettings } from '../hooks/useContexts'
import { Button, SecondaryButton } from './Button'
import { ReconcileForm } from './CheckTypeForm/ReconcileForm'
import { ExecutionDiagnosticsPanel } from './ExecutionDiagnosticsPanel'
import { ExecutionMetricsPanel } from './ExecutionMetricsPanel'
import type { ReconcileParams } from '../types/rules'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { parseReconciliationRows, runReconciliationPreview, type ReconciliationWorkflowResult, type ReconciliationWorkflowRow } from '../utils/reconciliationWorkflow'
import './ReconciliationWorkbench.css'

interface ReconciliationHistoryItem {
  id: string
  runAt: string
  status: string
  leftDatasourceId: string
  rightDatasourceId: string
  params: ReconcileParams
  result: ReconciliationWorkflowResult | null
}

const DEFAULT_PARAMS: ReconcileParams = {
  checkType: 'RECONCILE',
  leftDataObjectVersionId: 'ledger-left-v17',
  rightDataObjectVersionId: 'ledger-right-v17',
  joinKeys: [
    { leftAttribute: 'account_id', rightAttribute: 'account_id' },
  ],
  comparisons: [
    { leftAttribute: 'status', rightAttribute: 'status', mode: 'exact' },
    { leftAttribute: 'balance_amount', rightAttribute: 'balance_amount', mode: 'numeric_tolerance', tolerance: 0.01 },
    { leftAttribute: 'currency_code', rightAttribute: 'currency_code', mode: 'case_insensitive' },
  ],
}

const DEFAULT_LEFT_ROWS = [
  {
    account_id: 'acct-1001',
    status: 'active',
    balance_amount: 120.5,
    currency_code: 'USD',
  },
  {
    account_id: 'acct-1002',
    status: 'active',
    balance_amount: 80,
    currency_code: 'USD',
  },
  {
    account_id: 'acct-1003',
    status: 'hold',
    balance_amount: 12,
    currency_code: 'EUR',
  },
]

const DEFAULT_RIGHT_ROWS = [
  {
    account_id: 'acct-1001',
    status: 'active',
    balance_amount: 120.5,
    currency_code: 'usd',
  },
  {
    account_id: 'acct-1002',
    status: 'suspended',
    balance_amount: 80,
    currency_code: 'USD',
  },
  {
    account_id: 'acct-1004',
    status: 'active',
    balance_amount: 33,
    currency_code: 'GBP',
  },
]

const prettyPrintJson = (value: unknown): string => JSON.stringify(value, null, 2)

const formatSummaryValue = (value: number): string => value.toLocaleString(undefined, { maximumFractionDigits: 2 })

const buildApiBaseUrl = (apiBaseUrl: string): string => apiBaseUrl.replace(/\/$/, '')

const getAuthHeaders = (): Record<string, string> => {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const readResponseError = async (response: Response): Promise<string> => {
  try {
    const payload = await response.json()
    const detail = typeof payload?.detail === 'string' ? payload.detail : payload?.detail?.message
    return String(detail || payload?.message || response.statusText || 'Request failed')
  } catch {
    return response.statusText || 'Request failed'
  }
}

const toHistoryItem = (value: unknown): ReconciliationHistoryItem | null => {
  const run = snakeToCamel<Record<string, any>>(value)
  if (!run || typeof run !== 'object' || !run.id) {
    return null
  }

  const executionContract = run.executionContract || {}
  const leftDatasourceId = String(executionContract.leftDatasourceId || executionContract.left_datasource_id || '')
  const rightDatasourceId = String(executionContract.rightDatasourceId || executionContract.right_datasource_id || '')
  const params = executionContract.reconciliationParams || DEFAULT_PARAMS
  const result = run.resultSummary && Object.keys(run.resultSummary).length > 0 ? (run.resultSummary as ReconciliationWorkflowResult) : null

  return {
    id: String(run.id),
    runAt: String(run.submittedAt || run.createdAt || new Date().toISOString()),
    status: String(run.status || 'pending'),
    leftDatasourceId,
    rightDatasourceId,
    params,
    result,
  }
}

const toHistoryItems = (value: unknown): ReconciliationHistoryItem[] => {
  if (!Array.isArray(value)) {
    return []
  }

  return value.map(toHistoryItem).filter((item): item is ReconciliationHistoryItem => item !== null)
}

export const ReconciliationWorkbench: React.FC = () => {
  const settings = useSettings()
  const [params, setParams] = useState<ReconcileParams>(DEFAULT_PARAMS)
  const [leftRowsRaw, setLeftRowsRaw] = useState(() => prettyPrintJson(DEFAULT_LEFT_ROWS))
  const [rightRowsRaw, setRightRowsRaw] = useState(() => prettyPrintJson(DEFAULT_RIGHT_ROWS))
  const [result, setResult] = useState<ReconciliationWorkflowResult | null>(null)
  const [history, setHistory] = useState<ReconciliationHistoryItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [leftDatasourceId, setLeftDatasourceId] = useState('')
  const [rightDatasourceId, setRightDatasourceId] = useState('')
  const apiBaseUrl = settings.applicationSettings?.apiBaseUrl ? buildApiBaseUrl(settings.applicationSettings.apiBaseUrl) : ''
  const workspaceId = settings.workspaceSettings?.workspaceId ?? ''
  const currentUserId = settings.userSettings?.userId ?? null

  const configuredDatasources = useMemo(
    () => settings.workspaceSettings?.reconciliationDataSources || [],
    [settings.workspaceSettings?.reconciliationDataSources],
  )
  const allowedDatasourceTypes = useMemo(
    () => settings.applicationSettings?.allowedWorkspaceDataSourceTypes || [],
    [settings.applicationSettings?.allowedWorkspaceDataSourceTypes],
  )
  const leftDatasource = configuredDatasources.find((datasource) => datasource.id === leftDatasourceId) || null
  const rightDatasource = configuredDatasources.find((datasource) => datasource.id === rightDatasourceId) || null
  const activeDatasourceConflict = useMemo(() => {
    const selectedDatasourceIds = new Set([leftDatasourceId, rightDatasourceId].filter((value) => value))
    if (selectedDatasourceIds.size === 0) {
      return null
    }

    return history.find((item) => {
      if (item.status !== 'pending' && item.status !== 'running') {
        return false
      }

      return selectedDatasourceIds.has(item.leftDatasourceId) || selectedDatasourceIds.has(item.rightDatasourceId)
    }) || null
  }, [history, leftDatasourceId, rightDatasourceId])

  useEffect(() => {
    if (configuredDatasources.length === 0) {
      setLeftDatasourceId('')
      setRightDatasourceId('')
      return
    }

    setLeftDatasourceId((current) => {
      if (configuredDatasources.some((datasource) => datasource.id === current)) {
        return current
      }
      return configuredDatasources[0].id
    })

    setRightDatasourceId((current) => {
      if (configuredDatasources.some((datasource) => datasource.id === current)) {
        return current
      }
      return configuredDatasources[1]?.id || configuredDatasources[0].id
    })
  }, [configuredDatasources])

  const refreshHistory = useCallback(async () => {
    if (!apiBaseUrl || !workspaceId) {
      setHistory([])
      return
    }

    const tokenHeaders = getAuthHeaders()
    if (Object.keys(tokenHeaders).length === 0) {
      setHistory([])
      return
    }

    const response = await fetch(
      `${apiBaseUrl}/gx/runs/reconciliation?workspaceId=${encodeURIComponent(workspaceId)}&limit=10`,
      {
        headers: tokenHeaders,
      },
    )

    if (!response.ok) {
      throw new Error(await readResponseError(response))
    }

    const payload = await response.json()
    setHistory(toHistoryItems(payload))
  }, [apiBaseUrl, workspaceId])

  useEffect(() => {
    void refreshHistory().catch((refreshError) => {
      setError(refreshError instanceof Error ? refreshError.message : 'Unable to load reconciliation history.')
    })
  }, [refreshHistory])

  const summaryCards = useMemo(() => {
    if (!result) {
      return [
        { label: 'Matched rows', value: '0' },
        { label: 'Mismatched rows', value: '0' },
        { label: 'Missing from left', value: '0' },
        { label: 'Missing from right', value: '0' },
      ]
    }

    return [
      { label: 'Matched rows', value: String(result.matchedRows) },
      { label: 'Mismatched rows', value: String(result.mismatchedRows) },
      { label: 'Missing from left', value: String(result.missingLeftRows) },
      { label: 'Missing from right', value: String(result.missingRightRows) },
    ]
  }, [result])

  const selectedDatasourceSummary = useMemo(() => {
    if (!leftDatasource && !rightDatasource) {
      return 'No workspace datasources are configured yet.'
    }

    const leftSummary = leftDatasource ? `${leftDatasource.name} (${leftDatasource.sourceType})` : 'left source not selected'
    const rightSummary = rightDatasource ? `${rightDatasource.name} (${rightDatasource.sourceType})` : 'right source not selected'
    return `${leftSummary} vs ${rightSummary}`
  }, [leftDatasource, rightDatasource])

  const handleRun = async () => {
    setError(null)

    try {
      const parsedLeftRows = parseReconciliationRows(leftRowsRaw)
      const parsedRightRows = parseReconciliationRows(rightRowsRaw)
      const nextResult = runReconciliationPreview(params, parsedLeftRows as ReconciliationWorkflowRow[], parsedRightRows as ReconciliationWorkflowRow[])

      setResult(nextResult)

      if (!apiBaseUrl || !workspaceId) {
        throw new Error('Reconciliation history cannot be persisted without an active workspace and API base URL.')
      }

      const tokenHeaders = getAuthHeaders()
      if (Object.keys(tokenHeaders).length === 0) {
        throw new Error('Reconciliation history cannot be persisted without an authentication token.')
      }

      const createResponse = await fetch(`${apiBaseUrl}/gx/runs/reconciliation`, {
        method: 'POST',
        headers: {
          ...tokenHeaders,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(camelToSnake({
          workspaceId,
          leftDatasourceId,
          rightDatasourceId,
          leftDatasourceName: leftDatasource?.name ?? null,
          rightDatasourceName: rightDatasource?.name ?? null,
          leftDatasourceType: leftDatasource?.sourceType ?? null,
          rightDatasourceType: rightDatasource?.sourceType ?? null,
          reconciliationParams: params,
          previewLeftRows: parsedLeftRows,
          previewRightRows: parsedRightRows,
          requestedBy: currentUserId,
        })),
      })

      if (!createResponse.ok) {
        throw new Error(await readResponseError(createResponse))
      }

      const createdRun = snakeToCamel<{ id: string }>(await createResponse.json())
      const reportResponse = await fetch(`${apiBaseUrl}/gx/runs/${createdRun.id}/report`, {
        method: 'POST',
        headers: {
          ...tokenHeaders,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(camelToSnake({
          newStatus: 'succeeded',
          changedBy: currentUserId ?? 'system',
          reason: 'Reconciliation preview completed',
          details: {
            workflowType: 'reconciliation',
            workspaceId,
          },
          executionProgress: {
            percent: 100,
            label: 'Reconciliation completed',
            source: 'reconciliation-workbench',
          },
          resultSummary: nextResult,
          diagnostics: nextResult.diagnostics,
        })),
      })

      if (!reportResponse.ok) {
        throw new Error(await readResponseError(reportResponse))
      }

      await refreshHistory()
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : 'Unable to run reconciliation preview.')
    }
  }

  const handleResetExample = () => {
    setParams(DEFAULT_PARAMS)
    setLeftRowsRaw(prettyPrintJson(DEFAULT_LEFT_ROWS))
    setRightRowsRaw(prettyPrintJson(DEFAULT_RIGHT_ROWS))
    setResult(null)
    setError(null)
  }

  return (
    <div className="reconciliation-workbench">
      <div className="reconciliation-hero">
        <div className="reconciliation-hero-copy">
          <p className="reconciliation-kicker">DQ-17.1</p>
          <h2>Reconciliation Workbench</h2>
          <p className="reconciliation-description">
            Configure a left/right comparison, run the reconciliation against sample rows, and inspect the same match and diagnostic outputs the worker path will emit at scale.
          </p>
        </div>
        <div className="reconciliation-hero-actions">
          <Button type="button" onClick={handleRun} disabled={Boolean(activeDatasourceConflict)}>
            Run reconciliation
          </Button>
          <SecondaryButton type="button" onClick={handleResetExample}>Reset example</SecondaryButton>
        </div>
      </div>

      {activeDatasourceConflict && (
        <div className="reconciliation-error" role="alert">
          {`Datasource ${leftDatasourceId === activeDatasourceConflict.leftDatasourceId || leftDatasourceId === activeDatasourceConflict.rightDatasourceId ? leftDatasourceId : rightDatasourceId} is already part of active reconciliation run ${activeDatasourceConflict.id}.`}
        </div>
      )}

      {error && <div className="reconciliation-error" role="alert">{error}</div>}

      <div className="reconciliation-summary-grid" aria-label="Reconciliation summary">
        {summaryCards.map((card) => (
          <div key={card.label} className="reconciliation-summary-card">
            <span>{card.label}</span>
            <strong>{card.value}</strong>
          </div>
        ))}
      </div>

      <div className="reconciliation-layout">
        <section className="reconciliation-panel reconciliation-sources-panel">
          <div className="reconciliation-panel-header">
            <div>
              <p className="reconciliation-panel-kicker">Workspace datasources</p>
              <h3>Reconciliation hub sources</h3>
            </div>
            <p className="reconciliation-panel-note">
              {allowedDatasourceTypes.length > 0
                ? `App admins currently allow: ${allowedDatasourceTypes.join(', ')}`
                : 'No datasource type allowlist is configured yet.'}
            </p>
          </div>

          {configuredDatasources.length === 0 ? (
            <p className="reconciliation-empty-state">
              No workspace datasources are configured yet. Add them in Application Settings before running a reconciliation against real sources.
            </p>
          ) : (
            <div className="reconciliation-source-grid">
              <label className="reconciliation-field">
                <span>Left datasource</span>
                <select value={leftDatasourceId} onChange={(event) => setLeftDatasourceId(event.target.value)}>
                  {configuredDatasources.map((datasource) => (
                    <option key={datasource.id} value={datasource.id}>
                      {datasource.name} ({datasource.sourceType})
                    </option>
                  ))}
                </select>
              </label>

              <label className="reconciliation-field">
                <span>Right datasource</span>
                <select value={rightDatasourceId} onChange={(event) => setRightDatasourceId(event.target.value)}>
                  {configuredDatasources.map((datasource) => (
                    <option key={datasource.id} value={datasource.id}>
                      {datasource.name} ({datasource.sourceType})
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}

          <p className="reconciliation-panel-note">{selectedDatasourceSummary}</p>
        </section>

        <section className="reconciliation-panel reconciliation-config-panel">
          <div className="reconciliation-panel-header">
            <div>
              <p className="reconciliation-panel-kicker">Workflow config</p>
              <h3>Sources and comparison rules</h3>
            </div>
            <p className="reconciliation-panel-note">
              The form uses the canonical RECONCILE shape, so the same contract can later be sent to a PySpark worker for large runs.
            </p>
          </div>

          <ReconcileForm params={params} onChange={setParams} />
        </section>

        <section className="reconciliation-panel reconciliation-data-panel">
          <div className="reconciliation-panel-header">
            <div>
              <p className="reconciliation-panel-kicker">Sample rows</p>
              <h3>Left and right inputs</h3>
            </div>
            <p className="reconciliation-panel-note">
              Paste JSON arrays here to exercise the workflow against actual row data before wiring the same contract to a worker-backed execution.
            </p>
          </div>

          <div className="reconciliation-source-grid">
            <label className="reconciliation-field">
              <span>Left source rows</span>
              <textarea
                className="reconciliation-textarea"
                value={leftRowsRaw}
                onChange={(event) => setLeftRowsRaw(event.target.value)}
                spellCheck={false}
                aria-label="Left source rows"
              />
            </label>

            <label className="reconciliation-field">
              <span>Right source rows</span>
              <textarea
                className="reconciliation-textarea"
                value={rightRowsRaw}
                onChange={(event) => setRightRowsRaw(event.target.value)}
                spellCheck={false}
                aria-label="Right source rows"
              />
            </label>
          </div>
        </section>
      </div>

      <div className="reconciliation-results">
        <div className="reconciliation-panel">
          <div className="reconciliation-panel-header">
            <div>
              <p className="reconciliation-panel-kicker">Execution output</p>
              <h3>Match metrics and diagnostics</h3>
            </div>
            <p className="reconciliation-panel-note">
              The metrics panel and diagnostics panel are the same result surfaces used elsewhere in the app.
            </p>
          </div>

          {!result ? (
            <p className="reconciliation-empty-state">Run a reconciliation to see the latest execution output here.</p>
          ) : (
            <>
              <section className="reconciliation-summary-section" aria-label="Reconciliation summary details">
                <div className="reconciliation-summary-block">
                  <h4>Row counts</h4>
                  <div className="reconciliation-detail-grid">
                    <div className="reconciliation-detail-card"><span>Left rows</span><strong>{result.summary.rowCounts.leftRows}</strong></div>
                    <div className="reconciliation-detail-card"><span>Right rows</span><strong>{result.summary.rowCounts.rightRows}</strong></div>
                    <div className="reconciliation-detail-card"><span>Matched pairs</span><strong>{result.summary.rowCounts.matchedPairs}</strong></div>
                    <div className="reconciliation-detail-card"><span>Mismatched pairs</span><strong>{result.summary.rowCounts.mismatchedPairs}</strong></div>
                    <div className="reconciliation-detail-card"><span>Missing left</span><strong>{result.summary.rowCounts.missingLeftRows}</strong></div>
                    <div className="reconciliation-detail-card"><span>Missing right</span><strong>{result.summary.rowCounts.missingRightRows}</strong></div>
                    <div className="reconciliation-detail-card"><span>Missing join keys</span><strong>{result.summary.rowCounts.nullOrMissingJoinKeyRows}</strong></div>
                  </div>
                </div>

                <div className="reconciliation-summary-block">
                  <h4>Key coverage</h4>
                  <div className="reconciliation-detail-grid">
                    <div className="reconciliation-detail-card"><span>Distinct left keys</span><strong>{result.summary.keySummary.distinctLeftJoinKeys}</strong></div>
                    <div className="reconciliation-detail-card"><span>Distinct right keys</span><strong>{result.summary.keySummary.distinctRightJoinKeys}</strong></div>
                    <div className="reconciliation-detail-card"><span>Shared keys</span><strong>{result.summary.keySummary.sharedJoinKeys}</strong></div>
                    <div className="reconciliation-detail-card"><span>Left only</span><strong>{result.summary.keySummary.leftOnlyJoinKeys}</strong></div>
                    <div className="reconciliation-detail-card"><span>Right only</span><strong>{result.summary.keySummary.rightOnlyJoinKeys}</strong></div>
                    <div className="reconciliation-detail-card"><span>Duplicate left rows</span><strong>{result.summary.keySummary.duplicateJoinKeyRowsLeft}</strong></div>
                    <div className="reconciliation-detail-card"><span>Duplicate right rows</span><strong>{result.summary.keySummary.duplicateJoinKeyRowsRight}</strong></div>
                  </div>
                </div>

                <div className="reconciliation-summary-block">
                  <h4>Aggregate summaries</h4>
                  {result.summary.aggregateSummary.length === 0 ? (
                    <p className="reconciliation-empty-state">No numeric comparison fields were available for aggregation.</p>
                  ) : (
                    <div className="reconciliation-aggregate-list">
                      {result.summary.aggregateSummary.map((item) => (
                        <div key={`${item.comparisonLabel}-${item.mode}`} className="reconciliation-aggregate-card">
                          <div>
                            <strong>{item.comparisonLabel}</strong>
                            <span>{item.mode.replace('_', ' ')}</span>
                          </div>
                          <div className="reconciliation-aggregate-metrics">
                            <span>{formatSummaryValue(item.comparedRows)} compared</span>
                            <span>Left {formatSummaryValue(item.leftTotal)}</span>
                            <span>Right {formatSummaryValue(item.rightTotal)}</span>
                            <span>Delta {formatSummaryValue(item.delta)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="reconciliation-summary-block">
                  <h4>Payload summaries</h4>
                  <div className="reconciliation-detail-grid">
                    <div className="reconciliation-detail-card"><span>Compared pairs</span><strong>{result.summary.payloadSummary.comparedPairs}</strong></div>
                    <div className="reconciliation-detail-card"><span>Matched pairs</span><strong>{result.summary.payloadSummary.matchedPairs}</strong></div>
                    <div className="reconciliation-detail-card"><span>Mismatched pairs</span><strong>{result.summary.payloadSummary.mismatchedPairs}</strong></div>
                  </div>

                  {result.summary.payloadSummary.sampleMismatches.length === 0 ? (
                    <p className="reconciliation-empty-state">No payload mismatches were captured in the sample set.</p>
                  ) : (
                    <div className="reconciliation-payload-list">
                      {result.summary.payloadSummary.sampleMismatches.map((item, index) => (
                        <details key={`${item.joinKey}-${index}`} className="reconciliation-payload-item">
                          <summary>
                            <strong>{item.joinKey}</strong>
                            <span>{item.mismatchedAttributes.join(', ')}</span>
                          </summary>
                          <div className="reconciliation-payload-columns">
                            <pre>{item.leftPayload}</pre>
                            <pre>{item.rightPayload}</pre>
                          </div>
                        </details>
                      ))}
                    </div>
                  )}
                </div>
              </section>

              <ExecutionMetricsPanel passed={result.mismatchedRows === 0 && result.missingLeftRows === 0 && result.missingRightRows === 0 && result.nullOrMissingJoinKeyRows === 0} metrics={result.metrics} />
              <ExecutionDiagnosticsPanel diagnostics={result.diagnostics} />
            </>
          )}
        </div>

        <div className="reconciliation-panel">
          <div className="reconciliation-panel-header">
            <div>
              <p className="reconciliation-panel-kicker">Run history</p>
              <h3>Recent reconciliation runs</h3>
            </div>
          </div>

          {history.length === 0 ? (
            <p className="reconciliation-empty-state">No reconciliation runs yet.</p>
          ) : (
            <ul className="reconciliation-history-list">
              {history.map((item) => (
                <li key={item.id} className="reconciliation-history-item">
                  <div>
                    <strong>{item.params.leftDataObjectVersionId} → {item.params.rightDataObjectVersionId}</strong>
                    <span>{new Date(item.runAt).toLocaleString()}</span>
                  </div>
                  <div>
                    <span>{item.result ? 'Match rate' : 'Status'}</span>
                    <strong>{item.result ? `${item.result.metrics.matchRate.toFixed(2)}%` : item.status}</strong>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
