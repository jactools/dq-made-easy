import { useState, useCallback } from 'react'
import { useSettings } from './useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { camelToSnake } from '../utils/caseConverters'

export interface ResolvedAliasInfo {
  aliasName: string
  source: 'catalog' | 'manual' | 'unresolved'
  resolvedTermKey?: string
  resolvedTermName?: string
  resolvedDataType?: string
  domain?: string
  confidence: number
}

export interface UseEnrichedValidationReturn {
  enrichValidation: (params: {
    ruleId: string
    ruleVersionId: string
    expression: string
    detectedAliases: string[]
    unresolvedAliases: string[]
    issues: string[]
    manualAliasMappings?: Record<string, string>
  }) => Promise<EnrichedValidationResult>
  resolveAliases: (aliases: string[], manualMappings?: Record<string, string>) => Promise<Record<string, ResolvedAliasInfo>>
  loading: boolean
  error: string | null
}

export interface EnrichedValidationResult {
  ruleId: string
  ruleVersionId: string
  isValid: boolean
  unresolvedAliases: string[]
  issues: string[]
  diagnostics: Record<string, AliasDiagnostic>
  catalogAvailable: boolean
  lastSync?: string
  stats: {
    catalogSourcedAliases: number
    manualSourcedAliases: number
    unresolvedCount: number
  }
}

export interface AliasDiagnostic {
  resolutionStatus: 'resolved' | 'unresolved' | 'fuzzy_match'
  source: 'catalog' | 'manual' | 'unresolved'
  resolvedTermName?: string
  resolvedDataType?: string
  domain?: string
  confidence: number
  warning?: 'fuzzy_match' | 'unresolved'
}

/**
 * Hook for enriched rule validation with catalog metadata and provenance
 * 
 * Usage:
 * const { enrichValidation } = useEnrichedValidation()
 * const result = await enrichValidation({
 *   ruleId: 'rule-123',
 *   ruleVersionId: 'v1',
 *   detectedAliases: ['amount', 'customer'],
 *   unresolvedAliases: ['amount'],
 *   manualAliasMappings: { customer: 'attr-456' }
 * })
 * 
 * result.diagnostics['amount'].source === 'catalog'  // Resolved from catalog
 * result.stats.catalogSourcedAliases === 1
 */
export const useEnrichedValidation = (): UseEnrichedValidationReturn => {
  const settings = useSettings()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const enrichValidation = useCallback(
    async (params: {
      ruleId: string
      ruleVersionId: string
      expression: string
      detectedAliases: string[]
      unresolvedAliases: string[]
      issues: string[]
      manualAliasMappings?: Record<string, string>
    }): Promise<EnrichedValidationResult> => {
      setLoading(true)
      setError(null)

      try {
        const normalizedRuleId = String(params.ruleId || '').trim()
        const normalizedRuleVersionId = String(params.ruleVersionId || '').trim()
        if (!normalizedRuleId) {
          throw new Error('ruleId is required for enriched validation')
        }
        if (!normalizedRuleVersionId) {
          throw new Error('ruleVersionId is required for enriched validation')
        }

        const authToken = getAuthToken()
        if (!authToken) {
          throw new Error('Not authenticated')
        }

        const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
        const response = await fetch(
          `${apiBase}/rules/${normalizedRuleId}/validate/enriched`,
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${authToken}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(
              camelToSnake({
                ruleVersionId: normalizedRuleVersionId,
                expression: params.expression,
                detectedAliases: params.detectedAliases,
                unresolvedAliases: params.unresolvedAliases,
                issues: params.issues,
                manualAliasMappings: params.manualAliasMappings || {},
              })
            ),
          }
        )

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.error || `Validation failed: ${response.status}`)
        }

        const data = await response.json()
        return data as EnrichedValidationResult
      } catch (err: any) {
        const message = err?.message || 'Failed to enrich validation'
        setError(message)
        console.error('Enriched validation error:', err)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [settings.applicationSettings?.apiBaseUrl]
  )

  const resolveAliases = useCallback(
    async (
      aliases: string[],
      manualMappings?: Record<string, string>
    ): Promise<Record<string, ResolvedAliasInfo>> => {
      setLoading(true)
      setError(null)

      try {
        const authToken = getAuthToken()
        if (!authToken) {
          throw new Error('Not authenticated')
        }

        const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
        const response = await fetch(`${apiBase}/aliases/resolve`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(
            camelToSnake({
              aliases,
              manualMappings: manualMappings || {},
            })
          ),
        })

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.error || `Resolution failed: ${response.status}`)
        }

        const data = await response.json()
        return data.resolutions as Record<string, ResolvedAliasInfo>
      } catch (err: any) {
        const message = err?.message || 'Failed to resolve aliases'
        setError(message)
        console.error('Alias resolution error:', err)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [settings.applicationSettings?.apiBaseUrl]
  )

  return {
    enrichValidation,
    resolveAliases,
    loading,
    error,
  }
}
