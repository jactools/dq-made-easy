import { useState, useCallback } from 'react'
import { useSettings } from './useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  Object.prototype.toString.call(value) === '[object Object]'

const looksLikeSnakeCase = (value: unknown, keys: string[]): boolean => {
  if (!isPlainObject(value)) return false
  return keys.some((key) => key in value)
}

const assertValidDriftSummary = (value: unknown): DriftSummary => {
  if (
    looksLikeSnakeCase(value, [
      'total_rules_checked',
      'rules_with_drift',
      'total_drifts_detected',
      'by_drift_type',
      'affected_rules',
    ])
  ) {
    throw new Error(
      'Governance drift summary returned snake_case keys in UI code (telemetry fetch normalization not applied; common cause: OTEL fetch instrumentation wrapping order)'
    )
  }

  if (!isPlainObject(value)) {
    throw new Error('Governance drift summary payload is not an object')
  }

  const byDriftType = (value as any).byDriftType
  if (!byDriftType || typeof byDriftType !== 'object') {
    throw new Error('Governance drift summary payload missing byDriftType')
  }

  const affectedRules = (value as any).affectedRules
  if (!Array.isArray(affectedRules)) {
    throw new Error('Governance drift summary payload missing affectedRules')
  }

  return value as unknown as DriftSummary
}

const assertValidRuleDriftInfo = (value: unknown): RuleDriftInfo => {
  if (
    looksLikeSnakeCase(value, [
      'rule_id',
      'rule_name',
      'rule_version_id',
      'version_number',
      'affected_aliases',
      'total_drifts',
      'needs_revalidation',
    ])
  ) {
    throw new Error(
      'Rule drift response returned snake_case keys in UI code (telemetry fetch normalization not applied; common cause: OTEL fetch instrumentation wrapping order)'
    )
  }
  if (!isPlainObject(value)) {
    throw new Error('Rule drift payload is not an object')
  }

  const ruleId = (value as any).ruleId
  const ruleName = (value as any).ruleName
  const ruleVersionId = (value as any).ruleVersionId
  const versionNumber = (value as any).versionNumber
  const affectedAliases = (value as any).affectedAliases
  const drifts = (value as any).drifts
  const totalDrifts = (value as any).totalDrifts
  const needsRevalidation = (value as any).needsRevalidation
  const detectedAt = (value as any).detectedAt

  if (typeof ruleId !== 'string' || ruleId.length === 0) throw new Error('Rule drift payload missing ruleId')
  if (typeof ruleName !== 'string') throw new Error('Rule drift payload missing ruleName')
  if (typeof ruleVersionId !== 'string' || ruleVersionId.length === 0) {
    throw new Error('Rule drift payload missing ruleVersionId')
  }
  if (typeof versionNumber !== 'number') throw new Error('Rule drift payload missing versionNumber')
  if (!Array.isArray(affectedAliases)) throw new Error('Rule drift payload missing affectedAliases')
  if (!Array.isArray(drifts)) throw new Error('Rule drift payload missing drifts')
  if (typeof totalDrifts !== 'number') throw new Error('Rule drift payload missing totalDrifts')
  if (typeof needsRevalidation !== 'boolean') throw new Error('Rule drift payload missing needsRevalidation')
  if (typeof detectedAt !== 'string') throw new Error('Rule drift payload missing detectedAt')

  return value as unknown as RuleDriftInfo
}

const assertValidAffectedRulesPayload = (value: unknown): RuleDriftInfo[] => {
  if (looksLikeSnakeCase(value, ['affected_rules'])) {
    throw new Error(
      'Affected rules response returned snake_case keys in UI code (telemetry fetch normalization not applied; common cause: OTEL fetch instrumentation wrapping order)'
    )
  }
  if (!isPlainObject(value)) {
    throw new Error('Affected rules payload is not an object')
  }
  const affectedRules = (value as any).affectedRules
  if (!Array.isArray(affectedRules)) {
    throw new Error('Affected rules payload missing affectedRules')
  }
  return affectedRules as RuleDriftInfo[]
}

export interface TermDriftInfo {
  driftType: string
  aliasName: string
  resolvedTermName: string
  previousValue: string
  currentValue: string
  severity: string
  detectedAt: string
}

export interface RuleDriftInfo {
  ruleId: string
  ruleName: string
  ruleVersionId: string
  versionNumber: number
  affectedAliases: string[]
  drifts: TermDriftInfo[]
  totalDrifts: number
  needsRevalidation: boolean
  lastValidatedAt?: string
  detectedAt: string
}

export interface DriftSummary {
  totalRulesChecked: number
  rulesWithDrift: number
  totalDriftsDetected: number
  criticalDrifts: number
  warningDrifts: number
  byDriftType: Record<string, number>
  affectedRules: Array<{
    ruleId: string
    ruleName: string
    ruleVersionId: string
    versionNumber: number
    affectedAliases: string[]
    totalDrifts: number
    needsRevalidation: boolean
  }>
}

export interface UseCatalogDriftReturn {
  checkRuleDrift: (ruleId: string, versionId: string) => Promise<RuleDriftInfo | null>
  getDriftSummary: () => Promise<DriftSummary>
  getAffectedRules: (termId: string) => Promise<RuleDriftInfo[]>
  loading: boolean
  error: string | null
}

/**
 * Hook for detecting catalog term drift in rules
 *
 * Usage:
 * const { checkRuleDrift, getDriftSummary } = useCatalogDrift()
 *
 * // Check if specific rule has drift
 * const drift = await checkRuleDrift('rule-123', 'v1')
 * if (drift?.needsRevalidation) {
 *   // Show warning to user
 * }
 *
 * // Get overall drift summary
 * const summary = await getDriftSummary()
 * console.log(`${summary.rulesWithDrift} rules affected by drift`)
 */
export const useCatalogDrift = (): UseCatalogDriftReturn => {
  const settings = useSettings()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const checkRuleDrift = useCallback(
    async (ruleId: string, versionId: string): Promise<RuleDriftInfo | null> => {
      setLoading(true)
      setError(null)

      try {
        const authToken = getAuthToken()
        if (!authToken) {
          throw new Error('Not authenticated')
        }

        const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
        const response = await fetch(
          `${apiBase}/governance/drift/rules/${ruleId}/${versionId}`,
          {
            headers: {
              Authorization: `Bearer ${authToken}`,
              'Content-Type': 'application/json',
            },
          }
        )

        if (response.status === 204) {
          // No drift detected
          return null
        }

        if (!response.ok) {
          throw new Error(`Failed to check drift: ${response.statusText}`)
        }

        const data = assertValidRuleDriftInfo(await response.json())
        return data
      } catch (err: any) {
        const errorMsg = err.message || 'Failed to check drift'
        setError(errorMsg)
        console.error('Error checking drift:', err)
        return null
      } finally {
        setLoading(false)
      }
    },
    [settings]
  )

  const getDriftSummary = useCallback(
    async (): Promise<DriftSummary> => {
      setLoading(true)
      setError(null)

      try {
        const authToken = getAuthToken()
        if (!authToken) {
          throw new Error('Not authenticated')
        }

        const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
        const response = await fetch(`${apiBase}/governance/drift/summary`, {
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
        })

        if (!response.ok) {
          throw new Error(`Failed to get drift summary: ${response.statusText}`)
        }

        const payload = await response.json()
        return assertValidDriftSummary(payload)
      } catch (err: any) {
        const errorMsg = err.message || 'Failed to get drift summary'
        setError(errorMsg)
        console.error('Error getting drift summary:', err)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [settings]
  )

  const getAffectedRules = useCallback(
    async (termId: string): Promise<RuleDriftInfo[]> => {
      setLoading(true)
      setError(null)

      try {
        const authToken = getAuthToken()
        if (!authToken) {
          throw new Error('Not authenticated')
        }

        const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
        const response = await fetch(
          `${apiBase}/governance/drift/terms/${termId}/affected-rules`,
          {
            headers: {
              Authorization: `Bearer ${authToken}`,
              'Content-Type': 'application/json',
            },
          }
        )

        if (!response.ok) {
          throw new Error(`Failed to get affected rules: ${response.statusText}`)
        }

        return assertValidAffectedRulesPayload(await response.json())
      } catch (err: any) {
        const errorMsg = err.message || 'Failed to get affected rules'
        setError(errorMsg)
        console.error('Error getting affected rules:', err)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [settings]
  )

  return {
    checkRuleDrift,
    getDriftSummary,
    getAffectedRules,
    loading,
    error,
  }
}
