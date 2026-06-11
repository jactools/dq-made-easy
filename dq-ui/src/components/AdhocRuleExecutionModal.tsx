import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AppBanner, AppInput, AppSelect } from './app-primitives'
import { ModalShell } from './ModalShell'
import { Button } from './Button'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { useAuth, useNotifications, useSettings } from '../hooks/useContexts'
import { GxSuiteScopePickerModal, type GxSuiteScopeSelection } from './GxSuiteScopePickerModal'
import { createSupportReferenceId, formatSupportReferenceId } from '../utils/supportReference'
import { normalizeValidationUiText } from '../utils/validationTerminology'

type Mode = 'data_object_version' | 'rule'

type MinimalSuiteEnvelope = {
  suiteId: string
  suiteVersion: number
  compiledFrom?: { ruleIds?: string[] }
  executionContract?: { traceability?: { ruleId?: string } }
  resolvedExecutionScope?: { dataObjectVersionIds?: string[] }
}

type MaterializationRecord = {
  requestId: string
  status: string
  outputUri: string
  outputFormat: string
  errorMessage?: string | null
  result?: MaterializationResult | null
}

type MaterializationDeliverySummary = {
  targetCount?: number
  dataDeliveryCount?: number
  totalRowCount?: number
  reusedExisting?: boolean
  dataDeliveryIds?: string[]
  deliveryLocations?: string[]
  outputFormats?: string[]
}

type MaterializationTargetResult = {
  dataObjectVersionId?: string
  rowCount?: number
  outputUri?: string
  outputFormat?: string
  reusedExisting?: boolean
  dataDeliveryId?: string
  deliveryNote?: {
    deliveryLocation?: string
  } | null
}

type MaterializationResult = {
  outputUri?: string
  outputFormat?: string
  reusedExisting?: boolean
  deliverySummary?: MaterializationDeliverySummary | null
  targetResults?: MaterializationTargetResult[] | null
}

type DispatchHandoff = {
  runId: string
  suiteId: string
  suiteVersion: number
  scheduledAt: string
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

const uniq = (values: string[]) => Array.from(new Set(values))

const normalizeTextList = (values: unknown): string[] => {
  if (!Array.isArray(values)) return []
  return values.map((value) => String(value || '').trim()).filter(Boolean)
}

const getSelectValue = (event: any): string => {
  return event?.detail?.value ?? event?.target?.value ?? ''
}

export interface AdhocRuleExecutionModalProps {
  isOpen: boolean
  onClose: () => void
  mode: Mode
  dataObjectVersionId?: string
  dataObjectVersionLabel?: string
  ruleId?: string
  ruleLabel?: string
}

export const AdhocRuleExecutionModal: React.FC<AdhocRuleExecutionModalProps> = ({
  isOpen,
  onClose,
  mode,
  dataObjectVersionId,
  dataObjectVersionLabel,
  ruleId,
  ruleLabel,
}) => {
  const settings = useSettings()
  const auth = useAuth()
  const { addNotification } = useNotifications()
  const apiBase = useMemo(
    () => toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl),
    [settings.applicationSettings?.apiBaseUrl]
  )

  const [loadingSuites, setLoadingSuites] = useState(false)
  const [suites, setSuites] = useState<MinimalSuiteEnvelope[]>([])
  const [error, setError] = useState<string | null>(null)

  const [selectedRuleIds, setSelectedRuleIds] = useState<Set<string>>(new Set())
  const [selectedDovId, setSelectedDovId] = useState<string | null>(null)
  const [selectedAttributeName, setSelectedAttributeName] = useState<string | null>(null)
  const [selectedScope, setSelectedScope] = useState<GxSuiteScopeSelection | null>(null)
  const [isScopePickerOpen, setIsScopePickerOpen] = useState(false)
  const errorReferenceId = useMemo(() => (error ? createSupportReferenceId() : null), [error])

  const [sampleCount, setSampleCount] = useState(1000)
  const [outputFormat, setOutputFormat] = useState<'parquet' | 'delta'>('parquet')
  const [refreshTestData, setRefreshTestData] = useState(false)

  const [materialization, setMaterialization] = useState<MaterializationRecord | null>(null)
  const [materializing, setMaterializing] = useState(false)

  const [dispatching, setDispatching] = useState(false)
  const [dispatchResults, setDispatchResults] = useState<DispatchHandoff[] | null>(null)

  const [requestingSuiteRepair, setRequestingSuiteRepair] = useState(false)

  const isMountedRef = useRef(false)

  const effectiveDovId = mode === 'data_object_version'
    ? (dataObjectVersionId || null)
    : selectedDovId

  const attachedDovIds = useMemo(() => {
    const ids: string[] = []
    for (const suite of suites) {
      for (const id of (suite.resolvedExecutionScope?.dataObjectVersionIds || [])) {
        if (id) ids.push(id)
      }
    }
    return new Set(ids)
  }, [suites])

  const derivedRuleIds = useMemo(() => {
    if (mode === 'rule') {
      return ruleId ? [ruleId] : []
    }

    const ids: string[] = []
    for (const suite of suites) {
      const traceRuleId = suite.executionContract?.traceability?.ruleId
      if (traceRuleId) {
        ids.push(traceRuleId)
        continue
      }
      for (const id of (suite.compiledFrom?.ruleIds || [])) {
        if (id) ids.push(id)
      }
    }
    return uniq(ids).sort()
  }, [mode, ruleId, suites])

  useEffect(() => {
    isMountedRef.current = true
    return () => { isMountedRef.current = false }
  }, [])

  const resetState = useCallback(() => {
    setSuites([])
    setSelectedRuleIds(new Set())
    setSelectedDovId(null)
    setSelectedAttributeName(null)
    setSelectedScope(null)
    setError(null)
    setMaterialization(null)
    setMaterializing(false)
    setDispatching(false)
    setDispatchResults(null)
    setRequestingSuiteRepair(false)
    setRefreshTestData(false)
    setSampleCount(1000)
    setOutputFormat('parquet')
  }, [])

  useEffect(() => {
    if (!isOpen) {
      resetState()
      return
    }

    setError(null)
    setDispatchResults(null)

    // Preselect all rules in DOV mode after suites load.
    if (mode === 'data_object_version') {
      if (dataObjectVersionId) {
        setSelectedDovId(null)
      }
    }
  }, [dataObjectVersionId, isOpen, mode, resetState])

  const fetchSuites = useCallback(async () => {
    setError(null)
    setLoadingSuites(true)

    try {
      const token = getAuthToken()
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}

      let url = ''
      if (mode === 'data_object_version') {
        if (!dataObjectVersionId) throw new Error('Missing dataObjectVersionId')
        const params = new URLSearchParams({ dataObjectVersionId, status: 'active', latestOnly: 'true' })
        url = `${apiBase}/gx/suites?${params.toString()}`
      } else {
        if (!ruleId) throw new Error('Missing ruleId')
        const params = new URLSearchParams({ status: 'active', latestOnly: 'true' })
        url = `${apiBase}/gx/suites/by-rule/${encodeURIComponent(ruleId)}?${params.toString()}`
      }

      const response = await fetch(url, { headers })
      if (!response.ok) {
        throw new Error(`Failed to load validation suites (${response.status})`)
      }

      const payload = snakeToCamel<any>(await response.json())
      const parsedSuites: MinimalSuiteEnvelope[] = Array.isArray(payload) ? payload : []

      setSuites(parsedSuites)

      if (mode === 'data_object_version') {
        const ids: string[] = []
        for (const suite of parsedSuites) {
          const traceRuleId = suite.executionContract?.traceability?.ruleId
          if (traceRuleId) {
            ids.push(traceRuleId)
            continue
          }
          for (const id of (suite.compiledFrom?.ruleIds || [])) {
            if (id) ids.push(id)
          }
        }
        setSelectedRuleIds(new Set(uniq(ids)))
      }
    } catch (e) {
      console.error('Failed to fetch suites:', e)
      setError(e instanceof Error ? normalizeValidationUiText(e.message) : 'Failed to load validation suites')
    } finally {
      setLoadingSuites(false)
    }
  }, [apiBase, dataObjectVersionId, mode, ruleId])

  useEffect(() => {
    if (!isOpen) return
    void fetchSuites()
  }, [fetchSuites, isOpen])

  const canGenerateTestData = Boolean(effectiveDovId)
    && !materializing
    && (
      mode !== 'rule'
      || !effectiveDovId
      || attachedDovIds.size === 0
      || attachedDovIds.has(effectiveDovId)
    )

  const canDispatch = useMemo(() => {
    if (dispatching) return false
    if (!effectiveDovId) return false

    const materializationStatus = String(materialization?.status || '').trim().toLowerCase()
    if (materializationStatus !== 'completed') return false

    const outputUri = materialization?.result?.outputUri || materialization?.outputUri || null
    if (!outputUri) return false

    if (mode === 'data_object_version') {
      return selectedRuleIds.size > 0
    }

    if (!ruleId) return false
    // Rule mode requires at least one active suite; otherwise the backend will 404 with gx_suites_not_found.
    if (!loadingSuites && suites.length === 0) return false
    if (attachedDovIds.size > 0 && effectiveDovId && !attachedDovIds.has(effectiveDovId)) return false
    return true
  }, [attachedDovIds, dispatching, effectiveDovId, loadingSuites, materialization, mode, ruleId, selectedRuleIds.size, suites.length])

  const materializationResult = materialization?.result || null
  const deliverySummary = materializationResult?.deliverySummary || null
  const targetResults = Array.isArray(materializationResult?.targetResults)
    ? materializationResult.targetResults
    : []
  const deliveryLocations = normalizeTextList(deliverySummary?.deliveryLocations)
  const outputFormats = normalizeTextList(deliverySummary?.outputFormats)
  const effectiveTargetCount = deliverySummary?.targetCount || targetResults.length || 1
  const effectiveReusedExisting = Boolean(deliverySummary?.reusedExisting ?? materializationResult?.reusedExisting)
  const materializationDispatchTargetIds = useMemo(() => {
    const targetIds = targetResults
      .map((target) => String(target.dataObjectVersionId || '').trim())
      .filter(Boolean)
    return targetIds.length > 0 ? uniq(targetIds) : [effectiveDovId].filter(Boolean) as string[]
  }, [effectiveDovId, targetResults])

  const requestSuiteRepair = useCallback(async () => {
    if (mode !== 'rule') return
    if (!ruleId) {
      setError('Missing ruleId')
      return
    }

    const scope = selectedScope
    if (!scope || (scope.kind !== 'data_object_version' && scope.kind !== 'attribute')) {
      setError('Select a data object version (or attribute) first')
      return
    }

    const dataObjectVersionId = scope.dataObjectVersionId
    const dataObjectId = scope.dataObjectId
    const datasetId = scope.datasetId
    const dataProductId = scope.dataProductId

    if (!dataObjectVersionId) {
      setError('Select a data object version (or attribute) first')
      return
    }

    setError(null)
    setRequestingSuiteRepair(true)
    try {
      const token = getAuthToken()
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      }

      const workspaceId = auth.currentWorkspaceId || scope.workspaceId || 'default'

      // IMPORTANT: approvals API contract is snake_case; avoid relying on automatic conversion.
      const body = {
        rule_id: ruleId,
        workspace_id: workspaceId,
        request_type: 'gx_suite_repair',
        comments: 'Repair validation suite requested from ad-hoc execution.',
        suite_repair: {
          data_object_id: dataObjectId || null,
          dataset_id: datasetId || null,
          data_product_id: dataProductId || null,
          data_object_version_ids: [dataObjectVersionId],
          primary_key_fields: [],
        },
      }

      const response = await fetch(`${apiBase}/approvals`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      })
      if (!response.ok) {
        const contentType = String(response.headers.get('content-type') || '')
        let message = `Failed to request suite repair (${response.status})`
        let correlationId: string | null = null

        if (contentType.includes('json')) {
          const json = await response.json().catch(() => null)
          if (json && typeof json === 'object') {
            const detail = (json as any).detail
            correlationId = String((json as any).correlation_id || '').trim() || null
            if (typeof detail === 'string' && detail.trim()) {
              message = detail.trim()
            } else if (detail && typeof detail === 'object') {
              const detailMessage = String((detail as any).message || '').trim()
              if (detailMessage) {
                message = detailMessage
              }
            }
          }
        } else {
          const text = await response.text().catch(() => '')
          const trimmed = String(text || '').trim()
          if (trimmed) {
            message = trimmed
          }
        }

        const display = normalizeValidationUiText(correlationId ? `${message} (correlation_id: ${correlationId})` : message)
        addNotification({
          type: 'error',
          title: 'Suite Repair Request Failed',
          message: display,
        })
        setError(display)
        return
      }

      addNotification({
        type: 'success',
        title: 'Suite Repair Requested',
        message: 'Suite repair request submitted for approval.',
      })
      setError(null)
    } catch (e) {
      console.error('Failed to request suite repair:', e)
      const message = e instanceof Error ? normalizeValidationUiText(e.message) : 'Failed to request suite repair'
      addNotification({
        type: 'error',
        title: 'Suite Repair Request Failed',
        message,
      })
      setError(message)
    } finally {
      setRequestingSuiteRepair(false)
    }
  }, [addNotification, apiBase, auth.currentWorkspaceId, mode, ruleId, selectedScope])

  const startMaterialization = useCallback(async () => {
    if (!effectiveDovId) {
      setError('Select a data object version first')
      return
    }

    if (mode === 'rule' && attachedDovIds.size > 0 && !attachedDovIds.has(effectiveDovId)) {
      setError('Selected data object version is not attached to this rule')
      return
    }

    setError(null)
    setDispatchResults(null)
    setMaterializing(true)

    try {
      const token = getAuthToken()
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      }

      const body = camelToSnake({
        dataObjectVersionId: effectiveDovId,
        sampleCount,
        outputFormat,
        refresh: refreshTestData,
        selectedAttributeNames: selectedAttributeName ? [selectedAttributeName] : [],
      })

      const response = await fetch(`${apiBase}/test-data/materializations`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      })

      const json = snakeToCamel<any>(await response.json().catch(() => ({})))
      if (!response.ok) {
        const detail = json?.detail ? JSON.stringify(json.detail) : ''
        throw new Error(normalizeValidationUiText(`Test data materialization failed (${response.status}) ${detail}`))
      }

      const record: MaterializationRecord = {
        requestId: String(json.requestId || ''),
        status: String(json.status || ''),
        outputUri: String(json.outputUri || ''),
        outputFormat: String(json.outputFormat || ''),
        errorMessage: json.errorMessage,
        result: json.result,
      }

      setMaterialization(record)

      const requestId = record.requestId
      if (!requestId) {
        throw new Error('Materialization request is missing requestId')
      }

      // Poll until completion.
      while (isMountedRef.current) {
        const pollResp = await fetch(`${apiBase}/test-data/materializations/${encodeURIComponent(requestId)}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })

        const pollJson = snakeToCamel<any>(await pollResp.json().catch(() => ({})))
        if (!pollResp.ok) {
          const detail = pollJson?.detail ? JSON.stringify(pollJson.detail) : ''
          throw new Error(normalizeValidationUiText(`Failed to poll materialization (${pollResp.status}) ${detail}`))
        }

        const nextRecord: MaterializationRecord = {
          requestId: String(pollJson.requestId || ''),
          status: String(pollJson.status || ''),
          outputUri: String(pollJson.outputUri || ''),
          outputFormat: String(pollJson.outputFormat || ''),
          errorMessage: pollJson.errorMessage,
          result: pollJson.result,
        }

        setMaterialization(nextRecord)

        const status = String(nextRecord.status || '').toLowerCase()
        if (status === 'completed') break
        if (status === 'failed') {
          throw new Error(nextRecord.errorMessage || 'Test data materialization failed')
        }

        await sleep(800)
      }
    } catch (e) {
      console.error('Failed to materialize test data:', e)
      setError(e instanceof Error ? normalizeValidationUiText(e.message) : 'Failed to materialize test data')
    } finally {
      setMaterializing(false)
    }
  }, [apiBase, attachedDovIds, effectiveDovId, mode, outputFormat, refreshTestData, sampleCount, selectedAttributeName])

  const dispatchRuns = useCallback(async () => {
    if (!effectiveDovId) {
      setError('Select a data object version first')
      return
    }

    setError(null)
    setDispatchResults(null)

    const outputUri = materialization?.result?.outputUri || materialization?.outputUri || null
    if (!outputUri) {
      setError('Generate (or reuse) test data first')
      return
    }

    setDispatching(true)

    try {
      const token = getAuthToken()
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      }

      const resolvedFormat = (materialization?.result?.outputFormat || materialization?.outputFormat || null) as any
      const sourceOverrideOptions: Record<string, unknown> = {
        materializationRequestId: materialization.requestId,
      }
      if (deliverySummary) {
        sourceOverrideOptions.deliverySummary = deliverySummary
      }
      if (targetResults.length > 0) {
        sourceOverrideOptions.targetResults = targetResults
      }

      const payload: any = {
        dataObjectVersionId: mode === 'data_object_version' ? effectiveDovId : undefined,
        ruleId: mode === 'rule' ? ruleId : undefined,
        ruleIds: mode === 'data_object_version' ? Array.from(selectedRuleIds) : undefined,
        targetDataObjectVersionIds: materializationDispatchTargetIds,
        sourceOverrideUri: outputUri,
        sourceOverrideFormat: resolvedFormat || outputFormat,
        sourceOverrideOptions,
      }

      const response = await fetch(`${apiBase}/gx/runs/adhoc`, {
        method: 'POST',
        headers,
        body: JSON.stringify(camelToSnake(payload)),
      })

      const json = snakeToCamel<any>(await response.json().catch(() => ({})))
      if (!response.ok) {
        const detail = json?.detail ? JSON.stringify(json.detail) : ''
        throw new Error(normalizeValidationUiText(`Failed to enqueue validation runs (${response.status}) ${detail}`))
      }

      const handoffs: DispatchHandoff[] = Array.isArray(json)
        ? json.map((item: any) => ({
          runId: String(item.runId || ''),
          suiteId: String(item.suiteId || ''),
          suiteVersion: Number(item.suiteVersion || 0),
          scheduledAt: String(item.scheduledAt || ''),
        }))
        : []

      setDispatchResults(handoffs)
    } catch (e) {
      console.error('Failed to dispatch runs:', e)
      setError(e instanceof Error ? normalizeValidationUiText(e.message) : 'Failed to enqueue validation runs')
    } finally {
      setDispatching(false)
    }
  }, [apiBase, deliverySummary, effectiveDovId, materialization, materializationDispatchTargetIds, mode, outputFormat, ruleId, selectedRuleIds, targetResults])

  const title = mode === 'data_object_version'
    ? `Run Rules for ${dataObjectVersionLabel || dataObjectVersionId || 'Data Object Version'}`
    : `Run Rule ${ruleLabel || ruleId || ''}`

  const footer = (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
      <Button variant="secondary-default" onClick={onClose}>
        Close
      </Button>
      <Button variant="secondary-default" onClick={startMaterialization} disabled={!canGenerateTestData}>
        {materializing ? 'Generating…' : 'Generate / Reuse Test Data'}
      </Button>
      <Button variant="primary-default" onClick={dispatchRuns} disabled={!canDispatch}>
        {dispatching ? 'Enqueuing…' : 'Run Rules'}
      </Button>
    </div>
  )

  return (
    <>
      <ModalShell
        isOpen={isOpen}
        onClose={onClose}
        title={title}
        size="lg"
        footer={footer}
      >
        {error && (
          <AppBanner variant="error" role="alert" style={{ marginBottom: 12 }}>
            {error}
            {errorReferenceId && (
              <>
                <br />
                {formatSupportReferenceId(errorReferenceId)}
              </>
            )}
          </AppBanner>
        )}

        {loadingSuites ? (
          <div>Loading validation suites…</div>
        ) : (
          <>
            {mode === 'rule' && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                  <Button variant="secondary-default" onClick={() => setIsScopePickerOpen(true)}>
                    Select Data Object Version / Attribute
                  </Button>
                  <span>
                    {effectiveDovId
                      ? `Selected data_object_version_id: ${effectiveDovId}`
                      : 'No data object version selected'}
                    {selectedAttributeName ? ` (attribute: ${selectedAttributeName})` : ''}
                  </span>
                </div>

                {suites.length === 0 && (
                  <div style={{ marginTop: 8 }}>
                    No active validation suites found for this rule. Ad-hoc execution requires at least one active suite.
                    <div style={{ marginTop: 8 }}>
                      <Button
                        variant="secondary-default"
                        onClick={requestSuiteRepair}
                        disabled={requestingSuiteRepair || !effectiveDovId}
                      >
                        {requestingSuiteRepair ? 'Requesting…' : 'Request suite repair (requires approval)'}
                      </Button>
                    </div>
                  </div>
                )}

                {effectiveDovId && attachedDovIds.size > 0 && !attachedDovIds.has(effectiveDovId) && (
                  <div style={{ marginTop: 8 }}>
                    Selected version is not attached to this rule’s validation suites.
                  </div>
                )}
              </div>
            )}

            {mode === 'data_object_version' && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ marginBottom: 6 }}>Select rule(s) to run:</div>
                {derivedRuleIds.length === 0 ? (
                  <div className="muted">No rules found for this version.</div>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 6 }}>
                    {derivedRuleIds.map((rid) => (
                      <label key={rid} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <input
                          type="checkbox"
                          checked={selectedRuleIds.has(rid)}
                          onChange={(e) => {
                            setSelectedRuleIds((prev) => {
                              const next = new Set(prev)
                              if (e.target.checked) next.add(rid)
                              else next.delete(rid)
                              return next
                            })
                          }}
                        />
                        <span>{rid}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div style={{ paddingTop: 12 }}>
              <div style={{ marginBottom: 8, fontWeight: 600 }}>Reusable test data</div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <label htmlFor="adhoc-rule-execution-sample-count">Sample count</label>
                  <AppInput
                    id="adhoc-rule-execution-sample-count"
                    label="Sample count"
                    type="number"
                    value={String(sampleCount)}
                    onChange={(event: any) => setSampleCount(Number(getSelectValue(event) || 0))}
                    onInput={(event: any) => setSampleCount(Number(getSelectValue(event) || 0))}
                    style={{ width: 140 }}
                  />
                </div>

                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <label htmlFor="adhoc-rule-execution-output-format">Format</label>
                  <AppSelect
                    id="adhoc-rule-execution-output-format"
                    label="Format"
                    value={outputFormat}
                    onChange={(value) => setOutputFormat(value as any)}
                    placeholderLabel=""
                    options={[
                      { value: 'parquet', label: 'parquet' },
                      { value: 'delta', label: 'delta' },
                    ]}
                  />
                </div>

                <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={refreshTestData}
                    onChange={(e) => setRefreshTestData(Boolean(e.target.checked))}
                  />
                  Refresh (overwrite)
                </label>
              </div>

              {materialization && (
                <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
                  <div>Status: {materialization.status}</div>
                  <div>Output: {materialization.result?.outputUri || materialization.outputUri}</div>
                  {effectiveReusedExisting ? (
                    <div className="muted">Reused existing output (no refresh).</div>
                  ) : null}

                  {deliverySummary && (
                    <div>
                      <div style={{ marginBottom: 6, fontWeight: 600 }}>Delivery summary</div>
                      <div>Targets: {effectiveTargetCount}</div>
                      <div>Data deliveries: {deliverySummary.dataDeliveryCount || targetResults.length || 0}</div>
                      <div>Total rows: {deliverySummary.totalRowCount || 0}</div>
                      <div>Materialization mode: {effectiveReusedExisting ? 'Reused existing outputs' : 'New outputs created'}</div>
                      {outputFormats.length > 0 && (
                        <div>Output formats: {outputFormats.join(', ')}</div>
                      )}
                      {deliveryLocations.length > 0 && (
                        <div>
                          <div style={{ marginTop: 6 }}>Delivery locations:</div>
                          <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
                            {deliveryLocations.map((location) => (
                              <li key={location}>{location}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {targetResults.length > 0 && (
                    <div>
                      <div style={{ marginBottom: 6, fontWeight: 600 }}>Target deliveries</div>
                      <div style={{ display: 'grid', gap: 8 }}>
                        {targetResults.map((target, index) => {
                          const targetId = String(target.dataObjectVersionId || '').trim() || `target-${index + 1}`
                          const targetLocation = String(target.deliveryNote?.deliveryLocation || target.outputUri || '').trim()
                          const targetFormat = String(target.outputFormat || '').trim()
                          return (
                            <div key={`${targetId}-${index}`} style={{ border: '1px solid var(--app-border-subtle)', borderRadius: 8, padding: 10 }}>
                              <div><strong>Data object version:</strong> {targetId}</div>
                              <div><strong>Rows:</strong> {Number(target.rowCount || 0)}</div>
                              {target.dataDeliveryId && <div><strong>Delivery ID:</strong> {target.dataDeliveryId}</div>}
                              {targetFormat && <div><strong>Format:</strong> {targetFormat}</div>}
                              {targetLocation && <div><strong>Location:</strong> {targetLocation}</div>}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {dispatchResults && (
              <div style={{ paddingTop: 12, marginTop: 12 }}>
                <div style={{ marginBottom: 8, fontWeight: 600 }}>Enqueued runs</div>
                {dispatchResults.length === 0 ? (
                  <div className="muted">No runs returned.</div>
                ) : (
                  <div style={{ display: 'grid', gap: 6 }}>
                    {dispatchResults.map((item) => (
                      <div key={item.runId} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                        <div>
                          Run {item.runId} (suite {item.suiteId} v{item.suiteVersion})
                        </div>
                        <div className="muted">{item.scheduledAt}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </ModalShell>

      <GxSuiteScopePickerModal
        isOpen={isScopePickerOpen}
        onClose={() => setIsScopePickerOpen(false)}
        onSelect={(selection: GxSuiteScopeSelection) => {
          setIsScopePickerOpen(false)
          setSelectedScope(selection)

          if (selection.kind === 'data_object_version') {
            setSelectedDovId(selection.dataObjectVersionId)
            setSelectedAttributeName(null)
          } else if (selection.kind === 'attribute') {
            setSelectedDovId(selection.dataObjectVersionId)
            setSelectedAttributeName(selection.attributeName)
          } else {
            setError('Select a data object version or attribute')
          }
        }}
      />
    </>
  )
}
