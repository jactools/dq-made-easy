import React from 'react'
import { getAuthToken } from '../contexts/AuthContext'
import { useSettings } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import { AppButton, AppIcon, AppModal } from './app-primitives'
import { statusLabels } from './rules/ruleDisplayUtils'
import { RuleStatusHistoryEntry } from '../types/rules'
import { camelToSnake, snakeToCamel } from '../utils/caseConverters'
import { normalizeValidationUiText } from '../utils/validationTerminology'
import './RuleDetailsModal.css'

type JsonRecord = Record<string, any>

interface NormalizedTestProof {
  id: string
  status: 'passed' | 'failed' | 'pending'
  testDate: string | null
  coverage: number
  recordsTestedCount: number
  failuresFound: number
  failureDetails?: string
  proofData: JsonRecord
  executionContext: JsonRecord | null
  executionTrace: JsonRecord | null
  metrics: any
  diagnostics: any[] | null
}

interface FailurePresentation {
  category: 'technical' | 'data' | 'unknown' | 'passed' | 'pending'
  categoryLabel: string
  code: string | null
  reason: string | null
  interpretation: string | null
}

interface RuleDetailsModalProps {
  isOpen: boolean
  onClose: () => void
  ruleId: string | null
  ruleName?: string | null
  statusText?: string | null
  approvalText?: string | null
  versionHint?: number | null
}

interface RuleDetailsModalData {
  rule: any | null
  latestVersion: any | null
  activeCompilerArtifact: any | null
  latestProof: NormalizedTestProof | null
  allProofs: NormalizedTestProof[]
}

interface RuleStatusHistoryApiEntry {
  id: string
  rule_id: string
  action: string
  from_status?: string | null
  to_status: string
  changed_by?: string | null
  changed_at: string
  reason?: string | null
  details?: Record<string, unknown> | null
}

const HISTORY_STATUS_LABELS: Record<string, string> = statusLabels as Record<string, string>

const toRecord = (value: unknown): JsonRecord => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  return value as JsonRecord
}

const toOptionalString = (...values: unknown[]): string | null => {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }
  return null
}

const toFiniteNumber = (value: unknown, fallback = 0): number => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

const normalizeProofStatus = (value: unknown): NormalizedTestProof['status'] => {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'passed' || normalized === 'failed' || normalized === 'pending') {
    return normalized
  }
  if (normalized === 'running') {
    return 'pending'
  }
  return 'failed'
}

const looksLikeTechnicalFailure = (value: string | null): boolean => {
  if (!value) return false
  const normalized = value.toLowerCase()
  return normalized.includes('timed out')
    || normalized.includes('timeout')
    || normalized.includes('queue')
    || normalized.includes('generation failed')
    || normalized.includes('not executable')
    || normalized.includes('upstream')
    || normalized.includes('unavailable')
    || normalized.includes('exception')
    || normalized.includes('error')
    || normalized.includes('not found')
    || normalized.includes('failed to load')
}

const normalizeFailureCode = (value: string | null, reason: string | null): string | null => {
  const raw = value || reason
  if (!raw) return null
  const normalized = raw.trim().toLowerCase()
  if (!normalized) return null
  if (/^[a-z0-9_\-]+$/.test(normalized)) {
    return normalized
  }
  if (normalized.includes('timed out') || normalized.includes('timeout')) {
    return 'timeout'
  }
  if (normalized.includes('not executable')) {
    return 'expression_not_executable'
  }
  if (normalized.includes('queue')) {
    return 'queued_test_data_generation_failed'
  }
  return normalized.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || null
}

const normalizeTestProof = (proof: any): NormalizedTestProof => {
  const proofData = toRecord(proof?.proofData ?? proof?.proof_data)
  const executionContext = toRecord(
    proof?.executionContext
    ?? proof?.execution_context
    ?? proofData.executionContext
    ?? proofData.execution_context,
  )
  const executionTrace = toRecord(
    proof?.executionTrace
    ?? proof?.execution_trace
    ?? proofData.executionTrace
    ?? proofData.execution_trace,
  )
  const failureDetails = toOptionalString(
    proof?.failureDetails,
    proof?.failure_details,
    proofData.error,
    proofData.requestMessage,
    proofData.request_message,
  )

  return {
    id: String(proof?.id || ''),
    status: normalizeProofStatus(proof?.status),
    testDate: toOptionalString(proof?.testDate, proof?.test_date),
    coverage: toFiniteNumber(proof?.coverage, 0),
    recordsTestedCount: toFiniteNumber(proof?.recordsTestedCount ?? proof?.records_tested_count, 0),
    failuresFound: toFiniteNumber(proof?.failuresFound ?? proof?.failures_found, 0),
    failureDetails: failureDetails || undefined,
    proofData,
    executionContext: Object.keys(executionContext).length > 0 ? executionContext : null,
    executionTrace: Object.keys(executionTrace).length > 0 ? executionTrace : null,
    metrics: proof?.metrics ?? null,
    diagnostics: Array.isArray(proof?.diagnostics) ? proof.diagnostics : null,
  }
}

const getFailurePresentation = (proof: NormalizedTestProof | null): FailurePresentation => {
  if (!proof) {
    return {
      category: 'unknown',
      categoryLabel: 'Unknown',
      code: null,
      reason: null,
      interpretation: null,
    }
  }

  if (proof.status === 'passed') {
    return {
      category: 'passed',
      categoryLabel: 'Passed',
      code: null,
      reason: null,
      interpretation: null,
    }
  }

  if (proof.status === 'pending') {
    return {
      category: 'pending',
      categoryLabel: 'Running',
      code: null,
      reason: null,
      interpretation: 'This test run is still in progress.',
    }
  }

  const proofData = toRecord(proof.proofData)
  const executionContext = toRecord(proof?.executionContext ?? proofData.executionContext ?? proofData.execution_context)
  const errorCode = normalizeFailureCode(
    toOptionalString(proofData.errorType, proofData.error_type, executionContext.reason),
    toOptionalString(proof.failureDetails, proofData.error, executionContext.message, proofData.requestMessage, proofData.request_message),
  )
  const reason = toOptionalString(
    proof.failureDetails,
    proofData.error,
    executionContext.message,
    proofData.requestMessage,
    proofData.request_message,
  )
  const isTechnicalFailure = Boolean(
    toOptionalString(proofData.errorType, proofData.error_type, executionContext.reason)
    || (proof.recordsTestedCount === 0 && proof.failuresFound === 0 && reason)
    || looksLikeTechnicalFailure(reason),
  )

  if (isTechnicalFailure) {
    return {
      category: 'technical',
      categoryLabel: 'Technical execution issue',
      code: errorCode,
      reason: reason,
      interpretation: proof.recordsTestedCount === 0 && proof.failuresFound === 0
        ? 'No records were evaluated, so this does not indicate the data failed the rule.'
        : 'The rule run failed for a technical reason rather than because the sampled data violated the rule.',
    }
  }

  if (proof.failuresFound > 0) {
    return {
      category: 'data',
      categoryLabel: 'Data did not comply with the rule',
      code: errorCode,
      reason: reason || `${proof.failuresFound.toLocaleString()} tested record${proof.failuresFound === 1 ? '' : 's'} did not satisfy the rule conditions.`,
      interpretation: 'This failure reflects the evaluated data, not a technical execution problem.',
    }
  }

  return {
    category: 'unknown',
    categoryLabel: 'Failed without a clear reason',
    code: errorCode,
    reason: reason,
    interpretation: 'The run ended in a failed state, but the available proof does not clearly distinguish a technical issue from a rule failure.',
  }
}

const formatDateTime = (value: string | null): string => {
  if (!value) return 'N/A'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'N/A'
  return parsed.toLocaleString()
}

const formatHistoryStatus = (value: string | null | undefined): string => {
  const normalized = String(value || '').trim().toLowerCase()
  if (!normalized) {
    return 'Initial state'
  }

  return HISTORY_STATUS_LABELS[normalized] || normalized.replace(/[-_]+/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase())
}

const formatHistoryAction = (value: string | null | undefined): string => {
  const normalized = String(value || '').trim().replace(/[_-]+/g, ' ')
  if (!normalized) {
    return 'Transition'
  }
  return normalized.replace(/\b\w/g, (character) => character.toUpperCase())
}

const normalizeStatusHistoryEntry = (entry: RuleStatusHistoryApiEntry): RuleStatusHistoryEntry | null => {
  const normalized = snakeToCamel(entry) as Partial<RuleStatusHistoryEntry>
  const ruleId = toOptionalString(normalized.ruleId)
  const toStatus = toOptionalString(normalized.toStatus)
  const changedAt = toOptionalString(normalized.changedAt)

  if (!ruleId || !toStatus || !changedAt) {
    return null
  }

  return {
    id: toOptionalString(normalized.id) || `${ruleId}-${changedAt}-${toStatus}`,
    ruleId,
    action: toOptionalString(normalized.action) || 'transition',
    fromStatus: toOptionalString(normalized.fromStatus),
    toStatus,
    changedBy: toOptionalString(normalized.changedBy),
    changedAt,
    reason: toOptionalString(normalized.reason),
    details: normalized.details && typeof normalized.details === 'object' && !Array.isArray(normalized.details)
      ? (normalized.details as Record<string, unknown>)
      : null,
  }
}

export const RuleDetailsModal: React.FC<RuleDetailsModalProps> = ({
  isOpen,
  onClose,
  ruleId,
  ruleName,
  statusText,
  approvalText,
  versionHint,
}) => {
  const settings = useSettings()
  const apiBase = React.useMemo(
    () => toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl),
    [settings.applicationSettings?.apiBaseUrl]
  )

  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [data, setData] = React.useState<RuleDetailsModalData | null>(null)
  const [copiedSection, setCopiedSection] = React.useState<string | null>(null)
  const [showTestExplanation, setShowTestExplanation] = React.useState(false)
  const [showBusinessReport, setShowBusinessReport] = React.useState(false)
  const [businessReportMarkdown, setBusinessReportMarkdown] = React.useState('')
  const [businessReportLoading, setBusinessReportLoading] = React.useState(false)
  const [businessReportError, setBusinessReportError] = React.useState<string | null>(null)
  const [statusHistory, setStatusHistory] = React.useState<RuleStatusHistoryEntry[]>([])
  const [statusHistoryLoading, setStatusHistoryLoading] = React.useState(false)
  const [statusHistoryError, setStatusHistoryError] = React.useState<string | null>(null)
  const [ruleCommentsDraft, setRuleCommentsDraft] = React.useState('')
  const [ruleCommentsSaving, setRuleCommentsSaving] = React.useState(false)
  const [ruleCommentsError, setRuleCommentsError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!isOpen) {
      setShowTestExplanation(false)
      setShowBusinessReport(false)
      setBusinessReportMarkdown('')
      setBusinessReportLoading(false)
      setBusinessReportError(null)
      setStatusHistory([])
      setStatusHistoryLoading(false)
      setStatusHistoryError(null)
      setRuleCommentsDraft('')
      setRuleCommentsSaving(false)
      setRuleCommentsError(null)
    }
  }, [isOpen, ruleId])

  React.useEffect(() => {
    if (!data?.rule) return
    setRuleCommentsDraft(String(data.rule.comments || ''))
    setRuleCommentsError(null)
  }, [data?.rule])

  const copyToClipboard = async (label: string, value: string) => {
    const text = String(value || '')
    if (!text) return

    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const textarea = document.createElement('textarea')
        textarea.value = text
        textarea.setAttribute('readonly', '')
        textarea.style.position = 'absolute'
        textarea.style.left = '-9999px'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
      }
      setCopiedSection(label)
      window.setTimeout(() => setCopiedSection((current) => (current === label ? null : current)), 1500)
    } catch {
      // Ignore clipboard failures to keep modal interaction uninterrupted.
    }
  }

  const downloadLatestTestReport = async (format: 'markdown' | 'pdf') => {
    if (!ruleId || !data?.latestProof?.id) return
    const token = getAuthToken()
    if (!token) return

    try {
      const proofId = encodeURIComponent(String(data.latestProof.id))
      const url = `${apiBase}/test-proofs/${encodeURIComponent(ruleId)}/report?format=${format}&proof_id=${proofId}`
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) return

      const blob = await response.blob()
      const href = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = href
      anchor.download = `test-report-${ruleId}-${data.latestProof.id}.${format === 'pdf' ? 'pdf' : 'md'}`
      anchor.click()
      URL.revokeObjectURL(href)
    } catch {
      // Keep modal usable even if export fails.
    }
  }

  const toggleBusinessReportPreview = async () => {
    const nextOpen = !showBusinessReport
    setShowBusinessReport(nextOpen)

    if (!nextOpen) return
    if (businessReportMarkdown || businessReportLoading) return
    if (!ruleId || !data?.latestProof?.id) return

    const token = getAuthToken()
    if (!token) return

    setBusinessReportLoading(true)
    setBusinessReportError(null)
    try {
      const proofId = encodeURIComponent(String(data.latestProof.id))
      const url = `${apiBase}/test-proofs/${encodeURIComponent(ruleId)}/report?format=markdown&proof_id=${proofId}`
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) {
        setBusinessReportError('Could not load business report preview.')
        return
      }
      const markdown = await response.text()
      setBusinessReportMarkdown(markdown)
    } catch {
      setBusinessReportError('Could not load business report preview.')
    } finally {
      setBusinessReportLoading(false)
    }
  }

  const saveRuleComments = async () => {
    if (!ruleId || !data?.rule) {
      setRuleCommentsError('Load a rule before saving comments.')
      return
    }

    const token = getAuthToken()
    if (!token) {
      setRuleCommentsError('Sign in to update rule comments.')
      return
    }

    const normalizedComments = ruleCommentsDraft.trim()
    const currentComments = String(data.rule.comments || '').trim()
    if (normalizedComments === currentComments) {
      setRuleCommentsError(null)
      return
    }

    setRuleCommentsSaving(true)
    setRuleCommentsError(null)

    try {
      const response = await fetch(`${apiBase}/rules/${encodeURIComponent(ruleId)}`, {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(camelToSnake({
          name: data.rule.name,
          description: data.rule.description,
          comments: normalizedComments || null,
          dimension: data.rule.dimension,
          active: data.rule.active,
          generated: data.rule.generated,
          workspace: data.rule.workspace,
          dsl: data.rule.dsl,
        })),
      })

      if (!response.ok) {
        const message = await response.text().catch(() => '')
        throw new Error(message || `Unable to update comments for rule '${ruleId}'.`)
      }

      const updatedRule = snakeToCamel(await response.json().catch(() => ({}))) as Record<string, any>
      const nextComments = String(updatedRule.comments ?? normalizedComments ?? '')
      setData((current) => current ? {
        ...current,
        rule: {
          ...current.rule,
          comments: nextComments || null,
        },
      } : current)
      setRuleCommentsDraft(nextComments)
    } catch (error) {
      setRuleCommentsError(error instanceof Error ? normalizeValidationUiText(error.message) : `Unable to update comments for rule '${ruleId}'.`)
    } finally {
      setRuleCommentsSaving(false)
    }
  }

  React.useEffect(() => {
    const load = async () => {
      if (!isOpen || !ruleId) return

      const token = getAuthToken()
      if (!token) {
        setLoading(false)
        setError('Sign in to load full rule details.')
        setData(null)
        return
      }

      const headers: HeadersInit = { Authorization: `Bearer ${token}` }
      setLoading(true)
      setError(null)
      setData(null)
      setStatusHistory([])
      setStatusHistoryLoading(true)
      setStatusHistoryError(null)

      try {
        const [ruleResponse, versionsResponse, proofsResponse] = await Promise.all([
          fetch(`${apiBase}/rules/${encodeURIComponent(ruleId)}`, { headers }),
          fetch(`${apiBase}/rules/${encodeURIComponent(ruleId)}/versions?limit=1&offset=0`, { headers }),
          fetch(`${apiBase}/test-proofs/${encodeURIComponent(ruleId)}`, { headers }),
        ])

        if (!ruleResponse.ok) {
          throw new Error('Failed to load rule details')
        }

        const [ruleBody, versionsBody, proofsBody] = await Promise.all([
          ruleResponse.json(),
          versionsResponse.ok ? versionsResponse.json() : Promise.resolve(null),
          proofsResponse.ok ? proofsResponse.json() : Promise.resolve([]),
        ])

        const latestVersion = Array.isArray(versionsBody?.versions) ? versionsBody.versions[0] || null : null

        let activeCompilerArtifact: any = null
        if (latestVersion?.id) {
          const activeArtifactResponse = await fetch(
            `${apiBase}/rules/${encodeURIComponent(ruleId)}/versions/${encodeURIComponent(String(latestVersion.id))}/compiler-artifacts/active`,
            { headers }
          )
          if (activeArtifactResponse.ok) {
            activeCompilerArtifact = await activeArtifactResponse.json()
          }
        }

        const proofs = Array.isArray(proofsBody) ? proofsBody.map(normalizeTestProof) : []
        const latestProof = proofs
          .slice()
          .sort((left, right) => {
            const leftTime = Date.parse(String(left?.testDate || ''))
            const rightTime = Date.parse(String(right?.testDate || ''))
            return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
          })[0] || null

        setData({
          rule: ruleBody,
          latestVersion,
          activeCompilerArtifact,
          latestProof,
          allProofs: proofs,
        })
        setLoading(false)

        void (async () => {
          try {
            const statusHistoryResponse = await fetch(`${apiBase}/rules/${encodeURIComponent(ruleId)}/status-history`, {
              headers,
            })

            if (!statusHistoryResponse.ok) {
              throw new Error('Failed to load status history')
            }

            const historyBody = await statusHistoryResponse.json()
            const resolvedHistory = Array.isArray(historyBody)
              ? historyBody
                  .map((entry) => normalizeStatusHistoryEntry(entry as RuleStatusHistoryApiEntry))
                  .filter((entry): entry is RuleStatusHistoryEntry => entry !== null)
                  .sort((left, right) => {
                    const rightTime = Date.parse(String(right.changedAt || ''))
                    const leftTime = Date.parse(String(left.changedAt || ''))
                    return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
                  })
              : []

            setStatusHistory(resolvedHistory)
          } catch {
            setStatusHistoryError('Could not load status history.')
            setStatusHistory([])
          } finally {
            setStatusHistoryLoading(false)
          }
        })()
      } catch {
        setError('Could not load full details for this rule.')
        setLoading(false)
        setStatusHistoryLoading(false)
      }
    }

    void load()
  }, [isOpen, ruleId, apiBase])

  const compiledCode = React.useMemo(() => {
    const payload = data?.activeCompilerArtifact?.artifactPayload
    if (!payload || typeof payload !== 'object') return ''
    const normalized = (payload as any)?.filter?.normalized
    if (typeof normalized === 'string' && normalized.trim()) return normalized
    return JSON.stringify(payload, null, 2)
  }, [data])

  const testExplanation = React.useMemo(() => {
    const latestProof = data?.latestProof
    const proofPayload = toRecord(latestProof?.proofData)
    const executionTrace = toRecord(
      latestProof?.executionTrace
      ?? proofPayload.executionTrace
      ?? proofPayload.execution_trace,
    )
    const executionContext = toRecord(latestProof?.executionContext ?? proofPayload.executionContext ?? proofPayload.execution_context)
    const runRuleDetails = toRecord(proofPayload.ruleDetails ?? proofPayload.rule_details)

    const recordsTested = Number(
      latestProof?.recordsTestedCount ?? (proofPayload as any)?.totalTests ?? 0
    )
    const failuresFound = Number(
      latestProof?.failuresFound ?? (proofPayload as any)?.failedCount ?? 0
    )
    const passedCount = Number(
      (proofPayload as any)?.passedCount ?? Math.max(0, recordsTested - failuresFound)
    )
    const coverageRaw = Number(latestProof?.coverage ?? 0)
    const coveragePct = coverageRaw > 0 && coverageRaw <= 1 ? coverageRaw * 100 : coverageRaw
    const successRatePct = recordsTested > 0
      ? (passedCount / recordsTested) * 100
      : Number((proofPayload as any)?.successRate ?? 0)

    const executionSource = String(executionContext?.executedExpressionSource || executionContext?.executed_expression_source || 'rule-expression')
    const executionDescriptor = executionSource === 'compiled-artifact'
      ? 'a pre-compiled version of this rule'
      : 'the current rule expression'

    const dataSource = String((proofPayload as any)?.testDataSource || (proofPayload as any)?.test_data_source || 'generated test data')
    const sourceRuleExpression = String(executionContext?.sourceRuleExpression || executionContext?.source_rule_expression || '').trim()
    const executedExpression = String(executionContext?.executedExpression || executionContext?.executed_expression || '').trim()
    const versionNumber = executionTrace?.ruleVersionNumber || executionTrace?.rule_version_number || executionContext?.ruleVersionNumber || executionContext?.rule_version_number
    const artifactKey = String(executionTrace?.artifactKey || executionTrace?.artifact_key || executionContext?.artifactKey || executionContext?.artifact_key || '').trim()
    const dimension = String(runRuleDetails?.dimension || data?.rule?.dimension || '').trim()
    const executionReason = String(executionContext?.reason || '').trim()
    const executionMessage = String(
      executionContext?.message || runRuleDetails?.evaluationWarning || runRuleDetails?.evaluation_warning || latestProof?.failureDetails || ''
    ).trim()
    const selectedAttributes = Array.isArray((proofPayload as any)?.selectedAttributes)
      ? (proofPayload as any).selectedAttributes
          .map((attribute: any) => String(attribute?.name || attribute?.id || '').trim())
          .filter(Boolean)
      : []

    const failedRows = Array.isArray((proofPayload as any)?.results)
      ? (proofPayload as any).results.filter((row: any) => row && row.passed === false)
      : []

    const explicitReasons = Array.isArray((proofPayload as any)?.failureReasons)
      ? (proofPayload as any).failureReasons
          .map((reason: any) => String(reason || '').trim())
          .filter(Boolean)
      : []

    const diagnosticReasons = Array.isArray((proofPayload as any)?.diagnostics)
      ? (proofPayload as any).diagnostics
          .map((diagnostic: any) => String(diagnostic?.message || '').trim())
          .filter(Boolean)
      : []

    const failureAnalysis: string[] = []
    if (failuresFound > 0) {
      for (const reason of [...explicitReasons, ...diagnosticReasons]) {
        if (!failureAnalysis.includes(reason)) {
          failureAnalysis.push(reason)
        }
        if (failureAnalysis.length >= 2) break
      }

      if (failureAnalysis.length < 2 && failedRows.length > 0) {
        const failedRowsList = failedRows as Array<{ data?: unknown }>
        const nullOrEmptyByField = failedRowsList.reduce<Record<string, number>>((acc, row) => {
          const payload = row?.data && typeof row.data === 'object' ? row.data : {}
          Object.entries(payload).forEach(([key, value]) => {
            if (value === null || value === undefined || String(value).trim() === '') {
              acc[key] = (acc[key] || 0) + 1
            }
          })
          return acc
        }, {})

        const hotspotFields = Object.entries(nullOrEmptyByField)
          .sort((left, right) => right[1] - left[1])
          .slice(0, 2)

        if (hotspotFields.length > 0) {
          failureAnalysis.push(
            `Likely cause: the following field${hotspotFields.length === 1 ? ' was' : 's were'} blank or missing in most failing records: ${hotspotFields.map(([field]) => `"${field}"`).join(', ')}.`
          )
        }

        const firstFailed = failedRows[0]
        const samplePayload = firstFailed?.data && typeof firstFailed.data === 'object' ? firstFailed.data : {}
        const samplePairs = Object.entries(samplePayload)
          .slice(0, 2)
          .map(([key, value]) => `"${key}": ${String(value)}`)
        if (samplePairs.length > 0) {
          failureAnalysis.push(`For reference, one failing record contained: ${samplePairs.join(', ')}.`)
        }
      }

      if (failureAnalysis.length === 0) {
        failureAnalysis.push('Some records did not pass, but no specific cause could be identified. Consider reviewing the rule expression against a sample of the source data.')
      }
    }

    return {
      recordsTested,
      failuresFound,
      passedCount,
      coveragePct,
      successRatePct,
      executionDescriptor,
      dataSource,
      sourceRuleExpression,
      executedExpression,
      versionNumber,
      artifactKey,
      dimension,
      executionReason,
      executionMessage,
      selectedAttributes,
      failureAnalysis,
    }
  }, [data])

  const supportDiagnosticPayload = React.useMemo(() => {
    if (testExplanation.executionReason !== 'expression-not-executable') return ''

    return JSON.stringify(
      {
        ruleId: data?.rule?.id || ruleId || null,
        ruleName: data?.rule?.name || ruleName || null,
        proofId: data?.latestProof?.id || null,
        reason: testExplanation.executionReason,
        message: testExplanation.executionMessage || null,
        expression: String(data?.rule?.expression || ''),
        testedAt: data?.latestProof?.testDate || null,
      },
      null,
      2
    )
  }, [data, ruleId, ruleName, testExplanation.executionMessage, testExplanation.executionReason])

  const handleOpenInRules = () => {
    if (!ruleId) return
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('dq-open-rule', {
          detail: { ruleId },
        })
      )
    }
    onClose()
  }

  const modalFooter = (
    <>
      <AppButton variant="secondary" onClick={onClose}>
        Close
      </AppButton>
      <AppButton onClick={handleOpenInRules} disabled={!ruleId}>
        Open in Rules
      </AppButton>
    </>
  )

  const manualOverrideBy = toOptionalString(
    data?.rule?.manualOverrideBy,
    data?.rule?.manual_override_by,
  ) ?? ''
  const manualOverrideAt = toOptionalString(
    data?.rule?.manualOverrideAt,
    data?.rule?.manual_override_at,
  ) ?? ''
  const hasManualOverrideAudit = Boolean(manualOverrideBy || manualOverrideAt)
  const latestProofStatus = data?.latestProof?.status || 'failed'
  const latestProofStatusLabel = latestProofStatus === 'passed'
    ? 'Passed'
    : latestProofStatus === 'pending'
      ? 'Running'
      : 'Failed'
  const ruleTaxonomy = toRecord(data?.rule?.taxonomy)
  const ruleOwner = toOptionalString(ruleTaxonomy.owner)
  const ruleDataSteward = toOptionalString(ruleTaxonomy.dataSteward)
  const ruleDomainOwner = toOptionalString(ruleTaxonomy.domainOwner)
  const ruleTechnicalOwner = toOptionalString(ruleTaxonomy.technicalOwner)
  const ruleCommentsCurrent = String(data?.rule?.comments || '').trim()
  const ruleCommentsDirty = ruleCommentsDraft.trim() !== ruleCommentsCurrent
  const failurePresentation = React.useMemo(
    () => getFailurePresentation(data?.latestProof || null),
    [data?.latestProof],
  )

  return (
    <AppModal
      isOpen={isOpen}
      onClose={onClose}
      title={ruleName ? `Rule Details - ${ruleName}` : 'Rule Details'}
      size="xl"
      footer={modalFooter}
    >
      {loading && (
        <div className="rule-details-modal-loading">Loading full details...</div>
      )}

      {!loading && error && (
        <div className="rule-details-modal-error">{error}</div>
      )}

      {!loading && !error && data && (
        <div className="rule-details-modal-content">
          <div className="rule-details-modal-summary-grid">
            <div><strong>Rule ID:</strong> {data.rule?.id || ruleId || 'N/A'}</div>
            <div><strong>Status:</strong> {statusText || 'N/A'}</div>
            <div><strong>Version:</strong> V{data.latestVersion?.versionNumber || versionHint || 1}</div>
            <div><strong>Approval:</strong> {approvalText || data.rule?.last_approval_status || 'not submitted'}</div>
            <div>
              <strong>Manual mapping:</strong>{' '}
              {hasManualOverrideAudit
                ? `Yes${manualOverrideBy ? ` by ${manualOverrideBy}` : ''}${manualOverrideAt ? ` on ${formatDateTime(manualOverrideAt)}` : ''}`
                : 'No'}
            </div>
            <div><strong>Evidence records:</strong> {data.allProofs.length}</div>
            <div><strong>Last tested:</strong> {formatDateTime(data.latestProof?.testDate || null)}</div>
          </div>

          <div className="rule-details-modal-comments-section">
            <div className="rule-details-modal-section-head">
              <h4 className="rule-details-modal-section-title">Rule Comments</h4>
              <button
                type="button"
                className="rule-details-modal-info-btn"
                onClick={() => { void saveRuleComments() }}
                disabled={ruleCommentsSaving || !ruleCommentsDirty}
              >
                {ruleCommentsSaving ? 'Saving…' : 'Save comments'}
              </button>
            </div>
            <label className="rule-details-modal-comments-label" htmlFor="rule-details-comments">
              Comments
            </label>
            <textarea
              id="rule-details-comments"
              className="rule-details-modal-comments-input"
              value={ruleCommentsDraft}
              onChange={(event) => setRuleCommentsDraft(event.target.value)}
              placeholder="Add context, assumptions, or review notes for this rule"
              rows={5}
            />
            <div className="rule-details-modal-comments-hint">
              {ruleCommentsDirty ? 'Unsaved changes' : (ruleCommentsCurrent ? 'Comment saved' : 'No comments yet')}
            </div>
            {ruleCommentsError && <div className="rule-details-modal-error">{ruleCommentsError}</div>}
          </div>

          <div>
            <div className="rule-details-modal-section-head">
              <h4 className="rule-details-modal-section-title">Status History</h4>
              <span className="rule-details-modal-section-note">Most recent change first</span>
            </div>
            {statusHistoryLoading && (
              <div className="rule-details-modal-loading">Loading status history...</div>
            )}
            {!statusHistoryLoading && statusHistoryError && (
              <div className="rule-details-modal-error">{statusHistoryError}</div>
            )}
            {!statusHistoryLoading && !statusHistoryError && statusHistory.length === 0 && (
              <div className="rule-details-modal-empty-state">No change history recorded yet.</div>
            )}
            {!statusHistoryLoading && !statusHistoryError && statusHistory.length > 0 && (
              <ol className="rule-details-modal-history-list">
                {statusHistory.map((entry) => (
                  <li key={entry.id} className="rule-details-modal-history-item">
                    <div className="rule-details-modal-history-badge" aria-hidden="true" />
                    <div className="rule-details-modal-history-card">
                      <div className="rule-details-modal-history-rail">
                        <span className="rule-details-modal-history-status-pill">
                          {formatHistoryStatus(entry.fromStatus)}
                        </span>
                        <span className="rule-details-modal-history-arrow">→</span>
                        <span className="rule-details-modal-history-status-pill rule-details-modal-history-status-pill-to">
                          {formatHistoryStatus(entry.toStatus)}
                        </span>
                      </div>
                      <div className="rule-details-modal-history-meta">
                        <span>{formatDateTime(entry.changedAt)}</span>
                        <span>Action: {formatHistoryAction(entry.action)}</span>
                        {entry.changedBy && <span>By {entry.changedBy}</span>}
                      </div>
                      {entry.reason && (
                        <div className="rule-details-modal-history-reason">{normalizeValidationUiText(entry.reason)}</div>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>

          <div>
            <div className="rule-details-modal-section-head">
              <h4 className="rule-details-modal-section-title">Ownership</h4>
            </div>
            <div className="rule-details-modal-summary-grid">
              <div><strong>Owner:</strong> {ruleOwner || 'N/A'}</div>
              <div><strong>Data steward:</strong> {ruleDataSteward || 'N/A'}</div>
              <div><strong>Domain owner:</strong> {ruleDomainOwner || 'N/A'}</div>
              <div><strong>Technical owner:</strong> {ruleTechnicalOwner || 'N/A'}</div>
            </div>
          </div>

          <div>
            <div className="rule-details-modal-section-head">
              <h4 className="rule-details-modal-section-title">Rule Expression</h4>
              <button
                type="button"
                className="rule-details-modal-copy-btn"
                onClick={() => { void copyToClipboard('expression', String(data.rule?.expression || '')) }}
                aria-label="Copy rule expression"
                title={copiedSection === 'expression' ? 'Copied' : 'Copy expression'}
              >
                <AppIcon name={copiedSection === 'expression' ? 'check' : 'copy'} />
              </button>
            </div>
            <pre className="rule-details-modal-code">{String(data.rule?.expression || 'N/A')}</pre>
          </div>

          <div>
            <div className="rule-details-modal-section-head">
              <h4 className="rule-details-modal-section-title">Compiled Code / Artifact Payload</h4>
              <button
                type="button"
                className="rule-details-modal-copy-btn"
                onClick={() => { void copyToClipboard('compiled', compiledCode || '') }}
                aria-label="Copy compiled code"
                title={copiedSection === 'compiled' ? 'Copied' : 'Copy compiled code'}
              >
                <AppIcon name={copiedSection === 'compiled' ? 'check' : 'copy'} />
              </button>
            </div>
            <pre className="rule-details-modal-code">{compiledCode || 'No active compiler artifact found for latest version.'}</pre>
          </div>

          <div>
            <div className="rule-details-modal-section-head">
              <h4 className="rule-details-modal-section-title">Latest Business Evidence</h4>
              <button
                type="button"
                className="rule-details-modal-info-btn"
                onClick={() => { void downloadLatestTestReport('markdown') }}
                title="Download business evidence report as Markdown"
                disabled={!data.latestProof}
              >
                Export MD
              </button>
              <button
                type="button"
                className="rule-details-modal-info-btn"
                onClick={() => { void downloadLatestTestReport('pdf') }}
                title="Download business evidence report as PDF"
                disabled={!data.latestProof}
              >
                Export PDF
              </button>
              <button
                type="button"
                className="rule-details-modal-info-btn"
                onClick={() => { void toggleBusinessReportPreview() }}
                title={showBusinessReport ? 'Hide business report preview' : 'Preview business report'}
                disabled={!data.latestProof}
              >
                {showBusinessReport ? 'Hide report' : 'Preview report'}
              </button>
              <button
                type="button"
                className="rule-details-modal-info-btn"
                onClick={() => setShowTestExplanation((current) => !current)}
                title={showTestExplanation ? 'Hide plain-language explanation' : 'Show plain-language explanation'}
              >
                {showTestExplanation ? 'Hide explanation' : 'What does this mean?'}
              </button>
              <button
                type="button"
                className="rule-details-modal-copy-btn"
                onClick={() => { void copyToClipboard('proof', JSON.stringify(data.latestProof || null, null, 2)) }}
                aria-label="Copy latest business evidence"
                title={copiedSection === 'proof' ? 'Copied' : 'Copy latest business evidence'}
              >
                <AppIcon name={copiedSection === 'proof' ? 'check' : 'copy'} />
              </button>
            </div>

            {showBusinessReport && (
              <div className="rule-details-modal-report-wrap">
                <div className="rule-details-modal-section-head">
                  <h5 className="rule-details-modal-section-title">Business Evidence Report Preview (Markdown)</h5>
                  <button
                    type="button"
                    className="rule-details-modal-copy-btn"
                    onClick={() => { void copyToClipboard('businessReport', businessReportMarkdown) }}
                    aria-label="Copy business evidence report markdown"
                    title={copiedSection === 'businessReport' ? 'Copied' : 'Copy business evidence report markdown'}
                    disabled={!businessReportMarkdown}
                  >
                    <AppIcon name={copiedSection === 'businessReport' ? 'check' : 'copy'} />
                  </button>
                </div>
                {businessReportLoading && (
                  <div className="rule-details-modal-loading">Loading business report preview...</div>
                )}
                {!businessReportLoading && businessReportError && (
                  <div className="rule-details-modal-error">{businessReportError}</div>
                )}
                {!businessReportLoading && !businessReportError && businessReportMarkdown && (
                  <pre className="rule-details-modal-code">{businessReportMarkdown}</pre>
                )}
              </div>
            )}

            {showTestExplanation && (
              <div className="rule-details-modal-explainer">
                <p>
                  This quality check ran <strong>{Math.max(0, testExplanation.recordsTested).toLocaleString()}</strong> test record{Math.max(0, testExplanation.recordsTested) === 1 ? '' : 's'} using <strong>{testExplanation.executionDescriptor}</strong>.
                </p>
                <p>
                  Outcome: <strong>{Math.max(0, testExplanation.passedCount).toLocaleString()}</strong> record{Math.max(0, testExplanation.passedCount) === 1 ? '' : 's'} passed and <strong>{Math.max(0, testExplanation.failuresFound).toLocaleString()}</strong> failed — a success rate of <strong>{Number.isFinite(testExplanation.successRatePct) ? testExplanation.successRatePct.toFixed(2) : '0.00'}%</strong> (DQ Score: <strong>{Number.isFinite(testExplanation.coveragePct) ? testExplanation.coveragePct.toFixed(2) : '0.00'}%</strong>).
                </p>
                <p>
                  Test data: <strong>{testExplanation.dataSource}</strong>
                  {testExplanation.dimension ? <> · Quality dimension: <strong>{testExplanation.dimension}</strong></> : null}
                  {testExplanation.versionNumber ? <> · Rule version: <strong>V{testExplanation.versionNumber}</strong></> : null}
                  {testExplanation.artifactKey ? <> · Rule build: <strong>{testExplanation.artifactKey}</strong></> : null}.
                </p>
                {testExplanation.selectedAttributes.length > 0 && (
                  <p>
                    Tested against attribute{testExplanation.selectedAttributes.length === 1 ? '' : 's'}: <strong>{testExplanation.selectedAttributes.join(', ')}</strong>.
                  </p>
                )}
                {testExplanation.failuresFound > 0 && (
                  <div>
                    <p><strong>Likely reasons records did not pass:</strong></p>
                    <ul className="rule-details-modal-explainer-list">
                      {testExplanation.failureAnalysis.map((reason: string, index: number) => (
                        <li key={`${index}-${reason}`}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <div className="rule-details-modal-proof-summary">
              <p>
                <strong>Proof ID:</strong> {data.latestProof?.id || 'N/A'}
              </p>
              <p>
                <strong>Result:</strong> {latestProofStatusLabel}
              </p>
              {(failurePresentation.category === 'technical' || failurePresentation.category === 'data' || failurePresentation.category === 'unknown') && (
                <div className={`rule-details-modal-failure-panel rule-details-modal-failure-panel-${failurePresentation.category}`}>
                  <p>
                    <strong>Failure type:</strong> {failurePresentation.categoryLabel}
                  </p>
                  {failurePresentation.code && (
                    <p>
                      <strong>Failure code:</strong> <code>{failurePresentation.code}</code>
                    </p>
                  )}
                  {failurePresentation.reason && (
                    <p>
                      <strong>Reason:</strong> {failurePresentation.reason}
                    </p>
                  )}
                  {failurePresentation.interpretation && (
                    <p>
                      <strong>Interpretation:</strong> {failurePresentation.interpretation}
                    </p>
                  )}
                </div>
              )}
              <p>
                <strong>Records tested:</strong> {Math.max(0, testExplanation.recordsTested).toLocaleString()} · <strong>Failed:</strong> {Math.max(0, testExplanation.failuresFound).toLocaleString()}
              </p>
              <p>
                <strong>DQ Score:</strong> {Number.isFinite(testExplanation.coveragePct) ? testExplanation.coveragePct.toFixed(2) : '0.00'}% · <strong>Success rate:</strong> {Number.isFinite(testExplanation.successRatePct) ? testExplanation.successRatePct.toFixed(2) : '0.00'}%
              </p>
              {testExplanation.sourceRuleExpression && (
                <p>
                  <strong>Source rule expression snapshot:</strong> {testExplanation.sourceRuleExpression}
                </p>
              )}
              {testExplanation.executedExpression && testExplanation.executedExpression !== testExplanation.sourceRuleExpression && (
                <p>
                  <strong>Executed expression snapshot:</strong> {testExplanation.executedExpression}
                </p>
              )}
              {testExplanation.selectedAttributes.length > 0 && (
                <p>
                  <strong>Attributes tested:</strong> {testExplanation.selectedAttributes.join(', ')}
                </p>
              )}
              {testExplanation.executionReason === 'expression-not-executable' && (
                <div className="rule-details-modal-support-warning">
                  <span>
                    <strong>Execution warning:</strong> {testExplanation.executionMessage || 'Expression is not executable by test evaluator.'}
                  </span>
                  <button
                    type="button"
                    className="rule-details-modal-copy-btn rule-details-modal-copy-btn-sm"
                    onClick={() => { void copyToClipboard('supportDiagnostic', supportDiagnosticPayload) }}
                    aria-label="Copy support diagnostics"
                    title={copiedSection === 'supportDiagnostic' ? 'Copied' : 'Copy diagnostic for support'}
                  >
                    <AppIcon name={copiedSection === 'supportDiagnostic' ? 'check' : 'copy'} />
                  </button>
                </div>
              )}
              {testExplanation.failuresFound > 0 && testExplanation.failureAnalysis.length > 0 && (
                <div>
                  <p><strong>Failure highlights:</strong></p>
                  <ul className="rule-details-modal-explainer-list">
                    {testExplanation.failureAnalysis.map((reason: string, index: number) => (
                      <li key={`summary-${index}-${reason}`}>{reason}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </AppModal>
  )
}
