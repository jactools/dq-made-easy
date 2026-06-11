import React, { useCallback, useMemo, useState } from 'react'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { useSettings } from '../hooks/useContexts'
import { PrimaryButton, SecondaryButton } from './Button'
import { AdminPageHeader } from './AdminPageHeader'
import { snakeToCamel } from '../utils/caseConverters'
import { GxSuiteScopePickerModal, type GxSuiteScopeSelection } from './GxSuiteScopePickerModal'
import { AppSelect, AppIcon, AppPageShell } from './app-primitives'
import { createSupportReferenceId, formatSupportReferenceId } from '../utils/supportReference'
import { normalizeValidationUiText } from '../utils/validationTerminology'
import './Settings.css'

type GxSuiteStatus = 'active' | 'deprecated' | 'disabled'

type TraceabilityLookupState = {
  status: 'loading' | 'resolved' | 'unavailable'
  ruleName?: string
  ruleVersionNumber?: number | null
}

type GxSuiteEnvelope = {
  suiteId: string
  suiteVersion: number
  artifactVersion: string
  assignmentScope: {
    dataObjectId: string | null
    datasetId: string | null
    dataProductId: string | null
  }
  resolvedExecutionScope: {
    dataObjectVersionIds: string[]
  }
  compiledFrom: {
    ruleIds: string[]
    compilerVersion: string
    generatedAt: string
  }
  executionContract?: {
    engineTarget: string
    executionShape: string
    traceability: {
      ruleId: string
      ruleVersionId: string
      gxSuiteId: string
      gxSuiteVersion: number
      dataObjectVersionId?: string | null
      sourceRuleExpression?: string | null
      compiledExpression?: string | null
      artifactKey?: string | null
    }
  } | null
  savedBy?: string | null
  sourcePipeline?: string | null
}

const STATUS_OPTIONS: Array<{ value: GxSuiteStatus; label: string }> = [
  { value: 'active', label: 'Active' },
  { value: 'deprecated', label: 'Deprecated' },
  { value: 'disabled', label: 'Disabled' },
]

const STATUS_SELECT_OPTIONS = STATUS_OPTIONS.map((item) => ({ value: item.value, label: item.label }))

const formatCompactId = (value: string | null | undefined): string => {
  const raw = String(value || '').trim()
  if (!raw) return 'n/a'
  if (raw.length <= 18) return raw
  return `${raw.slice(0, 10)}…${raw.slice(-6)}`
}

const formatAssignmentScope = (scope: GxSuiteEnvelope['assignmentScope'] | undefined): string => {
  if (!scope) return 'n/a'

  const parts = [
    scope.dataProductId ? 'Data product' : null,
    scope.datasetId ? 'Dataset' : null,
    scope.dataObjectId ? 'Data object' : null,
  ].filter(Boolean)

  return parts.length ? parts.join(', ') : 'n/a'
}

const formatAssignmentScopeTitle = (scope: GxSuiteEnvelope['assignmentScope'] | undefined): string => {
  if (!scope) return 'n/a'

  const parts = [
    scope.dataProductId ? `dataProductId=${scope.dataProductId}` : null,
    scope.datasetId ? `datasetId=${scope.datasetId}` : null,
    scope.dataObjectId ? `dataObjectId=${scope.dataObjectId}` : null,
  ].filter(Boolean)

  return parts.length ? parts.join(', ') : 'n/a'
}

const describeCompiledFrom = (ruleIds: string[] | undefined): string => {
  const normalized = (ruleIds || []).map((ruleId) => String(ruleId || '').trim()).filter(Boolean)
  if (normalized.length === 0) {
    return 'Compiled from 0 rules'
  }
  return `Compiled from ${normalized.length} rule${normalized.length === 1 ? '' : 's'}`
}

const describeCompiledFromTitle = (ruleIds: string[] | undefined): string => {
  const normalized = (ruleIds || []).map((ruleId) => String(ruleId || '').trim()).filter(Boolean)
  return normalized.length > 0 ? `ruleIds: ${normalized.map(formatCompactId).join(', ')}` : 'ruleIds: n/a'
}

const describeTraceability = (traceability: GxSuiteEnvelope['executionContract'] | null | undefined): string => {
  if (!traceability?.traceability) {
    return 'Traceability not available'
  }

  return `Traceability: ruleId ${formatCompactId(traceability.traceability.ruleId)}, ruleVersionId ${formatCompactId(traceability.traceability.ruleVersionId)}`
}

const describeTraceabilityTitle = (traceability: NonNullable<GxSuiteEnvelope['executionContract']>['traceability'] | undefined): string => {
  if (!traceability) {
    return 'n/a'
  }
  const parts = [
    `ruleId=${traceability.ruleId}`,
    `ruleVersionId=${traceability.ruleVersionId}`,
    traceability.artifactKey ? `artifactKey=${traceability.artifactKey}` : null,
  ].filter(Boolean)
  return parts.join(', ')
}

const describeSelectedScope = (selection: GxSuiteScopeSelection | null): string => {
  if (!selection) {
    return 'No scope selected.'
  }

  if (selection.kind === 'data_object_version') {
    const obj = selection.dataObjectName || selection.dataObjectId || 'unknown object'
    return `Data object version (${obj}, version ${selection.dataObjectVersionId})`
  }

  if (selection.kind === 'data_object') {
    return `Data object ${selection.dataObjectName} (${selection.dataObjectId})`
  }

  if (selection.kind === 'dataset') {
    return `Dataset ${selection.datasetName} (${selection.datasetId})`
  }

  return `Data product ${selection.dataProductName} (${selection.dataProductId})`
}

export const GxSuitesAdmin: React.FC = () => {
  const settings = useSettings()

  const apiBaseUrl = useMemo(() => {
    return toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  }, [settings.applicationSettings?.apiBaseUrl])

  const [isScopePickerOpen, setIsScopePickerOpen] = useState(false)
  const [scopeSelection, setScopeSelection] = useState<GxSuiteScopeSelection | null>(null)
  const [status, setStatus] = useState<GxSuiteStatus>('active')
  const [latestOnly, setLatestOnly] = useState<boolean>(true)

  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [suites, setSuites] = useState<GxSuiteEnvelope[]>([])
  const [traceabilityLookupByKey, setTraceabilityLookupByKey] = useState<Record<string, TraceabilityLookupState>>({})
  const errorReferenceId = useMemo(() => (error ? createSupportReferenceId() : null), [error])

  const buildTraceabilityKey = (ruleId: string, ruleVersionId: string): string => `${ruleId}:${ruleVersionId}`

  const resetResults = useCallback(() => {
    setSuites([])
    setError(null)
  }, [])

  const resetAll = useCallback(() => {
    setScopeSelection(null)
    setSuites([])
    setError(null)
  }, [])

  const buildQueryFromSelection = (selection: GxSuiteScopeSelection): { key: string; value: string } => {
    if (selection.kind === 'data_product') {
      return { key: 'dataProductId', value: selection.dataProductId }
    }
    if (selection.kind === 'dataset') {
      return { key: 'datasetId', value: selection.datasetId }
    }
    if (selection.kind === 'data_object') {
      return { key: 'dataObjectId', value: selection.dataObjectId }
    }
    if (selection.kind === 'data_object_version') {
      return { key: 'dataObjectVersionId', value: selection.dataObjectVersionId }
    }

    // Attribute selection scopes validation suites to the selected data object version.
    return { key: 'dataObjectVersionId', value: selection.dataObjectVersionId }
  }

  const loadTraceabilityLookups = useCallback(async (nextSuites: GxSuiteEnvelope[]) => {
    const traceabilityEntries = nextSuites
      .map((suite) => suite.executionContract?.traceability)
      .filter((traceability): traceability is NonNullable<typeof traceability> => Boolean(traceability))

    if (traceabilityEntries.length === 0) {
      setTraceabilityLookupByKey({})
      return
    }

    const uniqueEntries = Array.from(
      new Map(traceabilityEntries.map((traceability) => [buildTraceabilityKey(traceability.ruleId, traceability.ruleVersionId), traceability] as const)).entries(),
    )

    const loadingState = uniqueEntries.reduce<Record<string, TraceabilityLookupState>>((acc, [key]) => {
      acc[key] = { status: 'loading' }
      return acc
    }, {})
    setTraceabilityLookupByKey(loadingState)

    const token = getAuthToken()
    const settled = await Promise.allSettled(
      uniqueEntries.map(async ([key, traceability]) => {
        const response = await fetch(
          `${apiBaseUrl}/rules/${encodeURIComponent(traceability.ruleId)}/versions/${encodeURIComponent(traceability.ruleVersionId)}`,
          {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          },
        )

        let payload: unknown = null
        try {
          payload = await response.json()
        } catch {
          payload = null
        }

        if (!response.ok) {
          const detail = (payload as any)?.detail
          const message =
            typeof detail === 'string'
              ? detail
              : typeof detail?.message === 'string'
                ? detail.message
                : typeof (payload as any)?.message === 'string'
                  ? (payload as any).message
                  : `Failed to load validation rule version details (${response.status})`
          throw new Error(normalizeValidationUiText(message))
        }

        const normalized = snakeToCamel<Record<string, any>>(payload)
        const ruleName = String(normalized.name || '').trim()
        const versionNumber = Number(normalized.versionNumber ?? normalized.version_number ?? 0)

        return [key, {
          status: 'resolved',
          ruleName: ruleName || undefined,
          ruleVersionNumber: Number.isFinite(versionNumber) && versionNumber > 0 ? versionNumber : null,
        }] as const
      }),
    )

    const nextLookup = uniqueEntries.reduce<Record<string, TraceabilityLookupState>>((acc, [key]) => {
      acc[key] = { status: 'unavailable' }
      return acc
    }, {})

    settled.forEach((result, index) => {
      const [key] = uniqueEntries[index]
      if (result.status === 'fulfilled') {
        nextLookup[key] = result.value[1]
      }
    })

    setTraceabilityLookupByKey(nextLookup)
  }, [apiBaseUrl])

  const loadSuites = useCallback(async () => {
    if (!scopeSelection) {
      setError('Please select a catalog scope first.')
      setSuites([])
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      const token = getAuthToken()
      const params = new URLSearchParams()
      const query = buildQueryFromSelection(scopeSelection)
      params.set(query.key, query.value)
      params.set('status', status)
      params.set('latestOnly', latestOnly ? 'true' : 'false')

      const response = await fetch(`${apiBaseUrl}/gx/suites?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })

      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        payload = null
      }

      if (!response.ok) {
        const detail = (payload as any)?.detail
        const message =
          typeof detail === 'string'
            ? detail
            : typeof detail?.message === 'string'
              ? detail.message
              : typeof (payload as any)?.message === 'string'
                ? (payload as any).message
                : `Failed to load validation suites (${response.status})`
        throw new Error(normalizeValidationUiText(message))
      }

      if (!Array.isArray(payload)) {
        throw new Error('Unexpected response shape from validation suites API.')
      }

      const normalized = snakeToCamel<GxSuiteEnvelope[]>(payload)
      setSuites(normalized)
      void loadTraceabilityLookups(normalized)
    } catch (exc) {
      setSuites([])
      setTraceabilityLookupByKey({})
      setError(exc instanceof Error ? normalizeValidationUiText(exc.message) : 'Failed to load validation suites')
    } finally {
      setIsLoading(false)
    }
  }, [apiBaseUrl, buildQueryFromSelection, latestOnly, loadTraceabilityLookups, scopeSelection, status])

  const describeTraceability = (traceability: GxSuiteEnvelope['executionContract'] | null | undefined): string => {
    if (!traceability?.traceability) {
      return 'Traceability not available'
    }

    const key = buildTraceabilityKey(traceability.traceability.ruleId, traceability.traceability.ruleVersionId)
    const lookup = traceabilityLookupByKey[key]
    if (lookup?.status === 'resolved' && lookup.ruleName) {
      return `Traceability: ${lookup.ruleName}${lookup.ruleVersionNumber ? ` v${lookup.ruleVersionNumber}` : ''}`
    }
    if (lookup?.status === 'loading') {
      return 'Traceability: loading rule details...'
    }
    return 'Traceability details unavailable'
  }

  const describeTraceabilityTitle = (traceability: GxSuiteEnvelope['executionContract'] | null | undefined): string => {
    if (!traceability?.traceability) {
      return 'n/a'
    }

    const key = buildTraceabilityKey(traceability.traceability.ruleId, traceability.traceability.ruleVersionId)
    const lookup = traceabilityLookupByKey[key]
    if (lookup?.status === 'resolved' && lookup.ruleName) {
      const parts = [
        `ruleId=${traceability.traceability.ruleId}`,
        `ruleVersionId=${traceability.traceability.ruleVersionId}`,
        `ruleName=${lookup.ruleName}`,
        `ruleVersionNumber=${lookup.ruleVersionNumber ?? 'n/a'}`,
        traceability.traceability.artifactKey ? `artifactKey=${traceability.traceability.artifactKey}` : null,
      ].filter(Boolean)
      return parts.join(', ')
    }
    return 'Traceability details unavailable'
  }

  return (
    <AppPageShell className="settings-container">
      <AdminPageHeader
        title="Validation Suites"
        subtitle="List compiled validation suites for a selected scope."
      />
      <div className="settings-content">
        <div className="settings-panel">
          <div className="settings-section">
            <h3>Scope</h3>
            <p className="settings-subtitle">{describeSelectedScope(scopeSelection)}</p>
            <div className="settings-actions">
              <PrimaryButton onClick={() => setIsScopePickerOpen(true)} disabled={isLoading}>
                Browse data catalog
              </PrimaryButton>
            </div>
          </div>

          <div className="settings-section">
            <AppSelect
              id="gxSuiteStatus"
              label="Suite Status"
              value={status}
              onChange={(value) => {
                setStatus(value as GxSuiteStatus)
                resetResults()
              }}
              options={STATUS_SELECT_OPTIONS}
              placeholderLabel="Choose status"
            />
          </div>

          <div className="settings-section">
            <div className="form-group checkbox">
              <input
                id="gxSuiteLatestOnly"
                type="checkbox"
                checked={latestOnly}
                onChange={(event) => {
                  setLatestOnly(event.target.checked)
                  resetResults()
                }}
              />
              <label htmlFor="gxSuiteLatestOnly">Latest only</label>
            </div>
          </div>

          <div className="settings-actions">
            <PrimaryButton onClick={() => void loadSuites()} disabled={isLoading}>
              {isLoading ? 'Loading…' : 'Search'}
            </PrimaryButton>
            <SecondaryButton onClick={resetAll} disabled={isLoading}>
              Clear
            </SecondaryButton>
          </div>

          {error && (
            <div className="settings-message error" style={{ marginTop: 16 }}>
              <AppIcon name="warning" />
              <span>
                {error}
                {errorReferenceId && (
                  <>
                    <br />
                    {formatSupportReferenceId(errorReferenceId)}
                  </>
                )}
              </span>
              <button onClick={() => setError(null)}>Dismiss</button>
            </div>
          )}

          <div className="settings-section" style={{ marginTop: 20 }}>
            <h3>Results</h3>

            {!isLoading && suites.length === 0 && !error && (
              <p className="settings-subtitle">No results loaded.</p>
            )}

            <div className="admin-users">
              {suites.map((suite) => {
                const traceability = suite.executionContract?.traceability
                return (
                  <div key={`${suite.suiteId}:${suite.suiteVersion}`} className="admin-user-row">
                    <div className="admin-user-info">
                      <span className="admin-user-name" title={`Suite ${suite.suiteId} v${suite.suiteVersion}`}>
                        Validation suite v{suite.suiteVersion}
                      </span>
                      <span className="admin-user-email" title={formatAssignmentScopeTitle(suite.assignmentScope)}>
                        Assignment: {formatAssignmentScope(suite.assignmentScope)}
                      </span>
                      <span className="admin-user-id" title={describeCompiledFromTitle(suite.compiledFrom?.ruleIds)}>
                        {describeCompiledFrom(suite.compiledFrom?.ruleIds)}
                      </span>
                      {traceability && (
                        <>
                          <span className="admin-user-id" title={describeTraceabilityTitle(suite.executionContract)}>
                              {describeTraceability(suite.executionContract)}
                          </span>
                          <span className="admin-user-id" title={traceability.artifactKey || 'Rule build not recorded'}>
                            Rule build: {traceability.artifactKey || 'Not recorded'}
                          </span>
                          <span className="admin-user-id" title={traceability.sourceRuleExpression || 'Source rule expression not recorded'}>
                            Source expression: {traceability.sourceRuleExpression || 'Not recorded'}
                          </span>
                          <span className="admin-user-id" title={traceability.compiledExpression || 'Compiled expression not recorded'}>
                            Compiled expression: {traceability.compiledExpression || 'Not recorded'}
                          </span>
                        </>
                      )}
                    </div>
                    <div className="admin-user-actions">
                      <span className="admin-user-id">{suite.resolvedExecutionScope?.dataObjectVersionIds?.length || 0} object versions</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <GxSuiteScopePickerModal
            isOpen={isScopePickerOpen}
            onClose={() => setIsScopePickerOpen(false)}
            onSelect={(selection) => {
              setScopeSelection(selection)
              resetResults()
            }}
          />
        </div>
      </div>
    </AppPageShell>
  )
}
