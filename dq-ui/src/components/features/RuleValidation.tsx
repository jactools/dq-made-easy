import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSettings } from '../../hooks/useContexts'
import { useAuth } from '../../hooks/useKeycloak'
import { toApiGroupV1Base } from '../../config/api'
import { getAuthToken } from '../../contexts/AuthContext'
import { withUiSpan } from '../../telemetry'
import { AppButton, AppIcon, AppPageHeader, AppPageShell, AppInput, AppTabs, type AppIconName } from '../app-primitives'
import './features.css'
import './RuleValidation.css'

const RULE_VALIDATION_NAV_SELECTION_KEY = 'dq-rule-validation-navigation-selection'

// ── API types ────────────────────────────────────────────────────────────────

interface RuleSummary {
  id: string
  name: string
  workspace?: string
}

interface DiagnosticItem {
  checkId: string
  severity: string
  message: string
  location?: string
}

interface BatchResultItem {
  ruleId: string
  ruleName: string
  valid: boolean
  compiledExpression?: string
  artifactKey?: string
  compilerVersion?: string
  errors: number
  warnings: number
  diagnostics: DiagnosticItem[]
}

interface ConflictDiagnostic {
  ruleId: string
  conflictsWith: string
  conflictType: string
  message: string
}

interface BatchSummary {
  total: number
  valid: number
  invalid: number
  errors: number
  warnings: number
}

interface BatchValidationResponse {
  runId: string
  results: BatchResultItem[]
  conflicts: ConflictDiagnostic[]
  summary: BatchSummary
}

interface ValidationRunItem {
  ruleId: string
  ruleName: string
  ruleVersionNumber?: number | null
  valid: boolean
  errors: number
  warnings: number
  diagnostics: DiagnosticItem[]
}

interface ValidationRun {
  id: string
  workspace?: string
  triggeredBy?: string
  runAt: string
  total: number
  validCount: number
  invalidCount: number
  status: string
  items?: ValidationRunItem[]
}

interface ValidationRunsPage {
  data: ValidationRun[]
  pagination: { total: number; page: number; limit: number; totalPages: number }
}

interface CompilerVersionRow {
  ruleId: string
  ruleVersionNumber?: number | null
}

interface CompilerVersionsPage {
  data: CompilerVersionRow[]
  pagination?: { total: number; page: number; limit: number; totalPages: number }
}

// ── helpers ──────────────────────────────────────────────────────────────────

const severityIcon = (sev: string): AppIconName => {
  if (sev === 'error') return 'close-circle'
  if (sev === 'warning') return 'warning'
  return 'info-circle'
}

const severityClass = (sev: string) => {
  if (sev === 'error') return 'rv-sev-error'
  if (sev === 'warning') return 'rv-sev-warning'
  return 'rv-sev-info'
}

const fmtDate = (iso: string) => {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

// ── component ────────────────────────────────────────────────────────────────

export const RuleValidation: React.FC = () => {
  const settings = useSettings()
  const auth = useAuth()
  const apiV1 = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  const workspace =
    auth.currentWorkspaceId ||
    settings.workspaceSettings?.workspaceId ||
    settings.workspaceSettings?.name ||
    undefined

  const [availableRules, setAvailableRules] = useState<RuleSummary[]>([])
  const [ruleFilter, setRuleFilter] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [isValidating, setIsValidating] = useState(false)
  const [batchResult, setBatchResult] = useState<BatchValidationResponse | null>(null)
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [activeSection, setActiveSection] = useState<'select-rules' | 'results' | 'history'>('select-rules')

  const [runHistory, setRunHistory] = useState<ValidationRun[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [expandedRun, setExpandedRun] = useState<string | null>(null)
  const [runDetail, setRunDetail] = useState<ValidationRun | null>(null)
  const [ruleVersions, setRuleVersions] = useState<Record<string, number>>({})
  const selectRulesRef = useRef<HTMLElement | null>(null)
  const resultsRef = useRef<HTMLElement | null>(null)
  const historyRef = useRef<HTMLElement | null>(null)

  const authHeader = (): Record<string, string> => {
    const token = getAuthToken()
    return token ? { Authorization: `Bearer ${token}` } : {}
  }

  // Load rules list on mount
  useEffect(() => {
    const qs = workspace ? `?workspace=${encodeURIComponent(workspace)}` : ''
    const versionsQs = workspace
      ? `?workspace=${encodeURIComponent(workspace)}&limit=100`
      : '?limit=100'

    Promise.all([
      fetch(`${apiV1}/rules${qs}`, { headers: authHeader() }),
      fetch(`${apiV1}/rules/compiler-versions${versionsQs}`, { headers: authHeader() }),
    ])
      .then(async ([rulesResp, versionsResp]) => {
        if (!rulesResp.ok) throw new Error(rulesResp.statusText)
        const rulesData = await rulesResp.json()
        const rows: RuleSummary[] = (Array.isArray(rulesData?.data) ? rulesData.data : Array.isArray(rulesData) ? rulesData : [])
          .map((r: any) => ({ id: String(r.id), name: r.name || r.id, workspace: r.workspace }))
        setAvailableRules(rows)

        if (versionsResp.ok) {
          const versionsData: CompilerVersionsPage = await versionsResp.json()
          const nextVersions = (versionsData?.data || []).reduce<Record<string, number>>((acc, row) => {
            const versionNumber = Number(row?.ruleVersionNumber)
            if (row?.ruleId && Number.isFinite(versionNumber) && versionNumber > 0) {
              acc[String(row.ruleId)] = versionNumber
            }
            return acc
          }, {})
          setRuleVersions(nextVersions)
        }
      })
      .catch(() => { /* non-critical */ })
  }, [apiV1, workspace])

  useEffect(() => {
    if (availableRules.length === 0) {
      return
    }

    try {
      const raw = window.sessionStorage.getItem(RULE_VALIDATION_NAV_SELECTION_KEY)
      if (!raw) {
        return
      }

      const parsed = JSON.parse(raw) as { rule_ids?: unknown }
      const incomingRuleIds = Array.isArray(parsed?.rule_ids)
        ? parsed.rule_ids.map((value) => String(value || '').trim()).filter(Boolean)
        : []

      const availableRuleIds = new Set(availableRules.map((rule) => rule.id))
      const matchingRuleIds = incomingRuleIds.filter((ruleId) => availableRuleIds.has(ruleId))

      if (matchingRuleIds.length > 0) {
        setSelectedIds(new Set(matchingRuleIds))
      }
    } catch {
      // Ignore malformed handoff payloads.
    } finally {
      window.sessionStorage.removeItem(RULE_VALIDATION_NAV_SELECTION_KEY)
    }
  }, [availableRules])

  // Load run history
  const loadHistory = useCallback(() => {
    setHistoryLoading(true)
    const qs = workspace ? `?workspace=${encodeURIComponent(workspace)}&limit=10` : '?limit=10'
    fetch(`${apiV1}/rules/validation-runs${qs}`, { headers: authHeader() })
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then((data: ValidationRunsPage) => setRunHistory(data.data || []))
      .catch(() => setRunHistory([]))
      .finally(() => setHistoryLoading(false))
  }, [apiV1, workspace])

  useEffect(() => { loadHistory() }, [loadHistory])

  const toggleRule = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const filteredRules = useMemo(() => {
    const query = ruleFilter.trim().toLowerCase()
    if (!query) return availableRules
    return availableRules.filter(rule => {
      const version = ruleVersions[rule.id]
      return (
        String(rule.name || '').toLowerCase().includes(query) ||
        String(rule.id || '').toLowerCase().includes(query) ||
        (Number.isFinite(version) && `v${version}`.toLowerCase().includes(query))
      )
    })
  }, [availableRules, ruleFilter, ruleVersions])

  const selectAll = () => setSelectedIds(prev => {
    const next = new Set(prev)
    filteredRules.forEach(r => next.add(r.id))
    return next
  })
  const clearAll = () => setSelectedIds(new Set())

  const handleValidate = async () => {
    const idsToValidate = selectedIds.size > 0
      ? Array.from(selectedIds)
      : filteredRules.map(r => r.id)

    if (idsToValidate.length === 0) return

    setIsValidating(true)
    setErrorMsg(null)
    setBatchResult(null)
    try {
      await withUiSpan(
        'ui.validation.run',
        {
          'dq.validation.scope': selectedIds.size > 0 ? 'selection' : 'all_visible',
          'dq.validation.rule_count': idsToValidate.length,
        },
        async (span) => {
          // Keep UI selection in sync when user triggers "Validate All" without manual selection.
          if (selectedIds.size === 0) {
            setSelectedIds(new Set(idsToValidate))
          }

          const body: any = { ruleIds: Array.from(selectedIds) }
          if (workspace) body.workspace = workspace
          const resp = await fetch(`${apiV1}/rules/validate/batch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeader() },
            body: JSON.stringify({ ...body, ruleIds: idsToValidate }),
          })
          span.setAttribute('http.response.status_code', resp.status)

          if (!resp.ok) {
            const detail = await resp.json().catch(() => ({ detail: resp.statusText }))
            span.setAttribute('dq.validation.result', 'error')
            throw new Error(detail?.detail || resp.statusText)
          }

          const result: BatchValidationResponse = await resp.json()
          setBatchResult(result)
          loadHistory()
          setActiveSection('results')
          resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          span.setAttribute('dq.validation.result', 'success')
          span.setAttribute('dq.validation.conflicts', result.conflicts.length)
        }
      )
    } catch (err: any) {
      setErrorMsg(err?.message || 'Validation failed')
    } finally {
      setIsValidating(false)
    }
  }

  const handleExportRunCSV = async (runId: string) => {
    const resp = await fetch(`${apiV1}/rules/validation-runs/${runId}/export?format=csv`, {
      headers: authHeader(),
    })
    if (!resp.ok) return
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `validation-run-${runId}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const loadRunDetail = async (runId: string) => {
    if (expandedRun === runId) {
      setExpandedRun(null)
      setRunDetail(null)
      return
    }
    setExpandedRun(runId)
    setRunDetail(null)
    try {
      const resp = await fetch(`${apiV1}/rules/validation-runs/${runId}`, { headers: authHeader() })
      if (resp.ok) setRunDetail(await resp.json())
    } catch { /* silent */ }
  }

  const toggleRow = (id: string) => {
    setExpandedRows(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const scrollToSection = (ref: React.RefObject<HTMLElement | null>) => {
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const handleSectionChange = (section: 'select-rules' | 'results' | 'history', ref: React.RefObject<HTMLElement | null>) => {
    setActiveSection(section)
    scrollToSection(ref)
  }

  return (
    <AppPageShell className="rule-feature-container">
      <AppPageHeader
        className="feature-header"
        title="Rule Validation"
        titleAs="h2"
        description="Batch-validate rule syntax, logic, and cross-rule conflicts"
      />

      <div className="rv-header-tabs" aria-label="Rule validation sections">
        <div className="rv-header-tabs-scroll">
          <AppTabs
            ariaLabel="Rule validation sections"
            value={activeSection}
            onChange={(section) => {
              if (section === 'select-rules') {
                handleSectionChange('select-rules', selectRulesRef)
              } else if (section === 'results') {
                handleSectionChange('results', resultsRef)
              } else if (section === 'history') {
                handleSectionChange('history', historyRef)
              }
            }}
            className="rv-header-tabs-control"
            tabs={[
              { value: 'select-rules', label: 'Select Rules', title: 'Go to Select Rules' },
              { value: 'results', label: 'Results', title: 'Go to Results' },
              { value: 'history', label: 'Validation Run History', title: 'Go to Validation Run History' },
            ]}
          />
        </div>
      </div>

      <div className="feature-content">

        {/* ── Rule selection ─────────────────────────────────────────────── */}
        <section className="rv-section" ref={selectRulesRef} id="rv-select-rules">
          <div className="rv-section-header">
            <h3>Select Rules</h3>
            <div className="rv-section-actions">
              <AppButton variant="tertiary" type="button" className="rv-link-btn" onClick={selectAll}>Select visible</AppButton>
              <AppButton variant="tertiary" type="button" className="rv-link-btn" onClick={clearAll}>Clear</AppButton>
            </div>
          </div>

          <div className="rv-filter-row">
            <AppInput
              id="rv-filter-input"
              label="Search rules"
              labelClassName="sr-only"
              className="rv-filter-input"
              placeholder="Search rules by name, ID, or version (e.g. v3)"
              value={ruleFilter}
              onChange={e => setRuleFilter(e.target.value)}
              hint={null}
            />
            <span className="rv-filter-count">
              Showing {filteredRules.length} of {availableRules.length}
            </span>
          </div>

          {availableRules.length === 0 ? (
            <p className="rv-empty-hint">No rules found in the current workspace.</p>
          ) : filteredRules.length === 0 ? (
            <p className="rv-empty-hint">No rules match your search.</p>
          ) : (
            <div className="rv-rule-list">
              {filteredRules.map(r => (
                <label key={r.id} className="rv-rule-row">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(r.id)}
                    onChange={() => toggleRule(r.id)}
                  />
                  <span className="rv-rule-main">
                    <span className="rv-rule-name">{r.name}</span>
                    {ruleVersions[r.id] && <span className="rv-rule-version">v{ruleVersions[r.id]}</span>}
                  </span>
                  <span className="rv-rule-id">{r.id}</span>
                </label>
              ))}
            </div>
          )}

          <div className="rv-validate-bar">
            <button
              className="feature-button"
              disabled={isValidating || (selectedIds.size === 0 && filteredRules.length === 0)}
              onClick={handleValidate}
            >
              {isValidating
                ? <><AppIcon name="loading" className="rv-spin" /> Validating…</>
                : <><AppIcon name="check-circle" /> Validate {selectedIds.size > 0 ? `(${selectedIds.size})` : 'All'}</>
              }
            </button>
          </div>

          {errorMsg && (
            <div className="rv-error-banner">
              <AppIcon name="close-circle" /> {errorMsg}
            </div>
          )}
        </section>

        {/* ── Batch results ──────────────────────────────────────────────── */}
        {batchResult && (
          <section className="rv-section" ref={resultsRef} id="rv-results">
            <div className="rv-section-header">
              <h3>Results <span className="rv-run-id">run: {batchResult.runId}</span></h3>
            </div>

            {/* Summary pills */}
            <div className="rv-summary-bar">
              <span className="rv-pill rv-pill-total">{batchResult.summary.total} rules</span>
              <span className="rv-pill rv-pill-valid">{batchResult.summary.valid} valid</span>
              {batchResult.summary.invalid > 0 && (
                <span className="rv-pill rv-pill-invalid">{batchResult.summary.invalid} invalid</span>
              )}
              {batchResult.summary.errors > 0 && (
                <span className="rv-pill rv-pill-error">{batchResult.summary.errors} errors</span>
              )}
              {batchResult.summary.warnings > 0 && (
                <span className="rv-pill rv-pill-warn">{batchResult.summary.warnings} warnings</span>
              )}
            </div>

            {/* Per-rule rows */}
            <div className="rv-results-table">
              {batchResult.results.map(item => (
                <div key={item.ruleId} className={`rv-result-row ${item.valid ? 'rv-valid' : 'rv-invalid'}`}>
                  <div className="rv-result-summary" onClick={() => toggleRow(item.ruleId)}>
                      <AppIcon name={item.valid ? 'check-circle' : 'close-circle'} className={item.valid ? 'rv-icon-ok' : 'rv-icon-err'} />
                    <span className="rv-result-main">
                      <span className="rv-result-name">{item.ruleName}</span>
                      {ruleVersions[item.ruleId] && <span className="rv-rule-version">v{ruleVersions[item.ruleId]}</span>}
                    </span>
                    <span className="rv-result-id">{item.ruleId}</span>
                    <span className="rv-result-counts">
                      {item.errors > 0 && <span className="rv-count-err">{item.errors}E</span>}
                      {item.warnings > 0 && <span className="rv-count-warn">{item.warnings}W</span>}
                    </span>
                    <AppIcon name={expandedRows.has(item.ruleId) ? 'chevron-up' : 'chevron-down'} className="rv-chevron" />
                  </div>

                  {expandedRows.has(item.ruleId) && (
                    <div className="rv-result-detail">
                      {item.compiledExpression && (
                        <div className="rv-compiled">
                          <span className="rv-label">Compiled:</span>
                          <code>{item.compiledExpression}</code>
                        </div>
                      )}
                      {item.diagnostics.length === 0 ? (
                        <p className="rv-no-issues">No issues found.</p>
                      ) : (
                        <ul className="rv-diag-list">
                          {item.diagnostics.map((d, i) => (
                            <li key={i} className={`rv-diag-item ${severityClass(d.severity)}`}>
                              <AppIcon name={severityIcon(d.severity)} />
                              <span className="rv-diag-check">{d.checkId}</span>
                              <span className="rv-diag-msg">{d.message}</span>
                              {d.location && <span className="rv-diag-loc">{d.location}</span>}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Conflicts */}
            {batchResult.conflicts.length > 0 && (
              <div className="rv-conflicts">
                <h4 className="rv-conflicts-title">
                  <AppIcon name="warning" /> Cross-Rule Conflicts ({batchResult.conflicts.length})
                </h4>
                <ul className="rv-conflict-list">
                  {batchResult.conflicts.map((c, i) => (
                    <li key={i} className="rv-conflict-item">
                      <span className="rv-conflict-type">{c.conflictType}</span>
                      <span className="rv-conflict-msg">{c.message}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

        {/* ── Run history ────────────────────────────────────────────────── */}
        <section className="rv-section" ref={historyRef} id="rv-history">
          <div className="rv-section-header">
            <h3>Validation Run History</h3>
            <AppButton variant="tertiary" type="button" className="rv-link-btn" onClick={loadHistory} disabled={historyLoading}>
              {historyLoading ? 'Loading…' : 'Refresh'}
            </AppButton>
          </div>

          {runHistory.length === 0 && !historyLoading && (
            <p className="rv-empty-hint">No validation runs yet.</p>
          )}

          {runHistory.length > 0 && (
            <div className="rv-history-table">
              <div className="rv-history-header">
                <span>Run ID</span>
                <span>Date</span>
                <span>Total</span>
                <span>Valid</span>
                <span>Status</span>
                <span></span>
              </div>
              {runHistory.map(run => (
                <React.Fragment key={run.id}>
                  <div className="rv-history-row" onClick={() => loadRunDetail(run.id)}>
                    <span className="rv-mono">{run.id.slice(0, 8)}…</span>
                    <span>{fmtDate(run.runAt)}</span>
                    <span>{run.total}</span>
                    <span className={run.validCount === run.total ? 'rv-ok-text' : 'rv-warn-text'}>
                      {run.validCount}/{run.total}
                    </span>
                    <span className={`rv-status-badge rv-status-${run.status}`}>{run.status}</span>
                    <span className="rv-history-actions">
                      <button className="rv-icon-btn" title="Export CSV"
                        onClick={e => { e.stopPropagation(); handleExportRunCSV(run.id) }}>
                        <AppIcon name="download" />
                      </button>
                      <AppIcon name={expandedRun === run.id ? 'chevron-up' : 'chevron-down'} className="rv-chevron" />
                    </span>
                  </div>

                  {expandedRun === run.id && runDetail && runDetail.id === run.id && (
                    <div className="rv-run-detail">
                      {(runDetail.items || []).length === 0 ? (
                        <p className="rv-empty-hint">No item details stored.</p>
                      ) : (
                        <ul className="rv-run-items">
                          {(runDetail.items || []).map((item, i) => (
                            <li key={i} className={`rv-run-item ${item.valid ? '' : 'rv-run-item-invalid'}`}>
                                <AppIcon name={item.valid ? 'check-circle' : 'close-circle'} className={item.valid ? 'rv-icon-ok' : 'rv-icon-err'} />
                              <span className="rv-run-item-main">
                                <span>{item.ruleName}</span>
                                {item.ruleVersionNumber && <span className="rv-rule-version">v{item.ruleVersionNumber}</span>}
                              </span>
                              {item.errors > 0 && <span className="rv-count-err">{item.errors}E</span>}
                              {item.warnings > 0 && <span className="rv-count-warn">{item.warnings}W</span>}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </React.Fragment>
              ))}
            </div>
          )}
        </section>

      </div>
    </AppPageShell>
  )
}
