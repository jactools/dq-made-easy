import { useEffect, useMemo, useState } from 'react'
import { useSettings } from './useContexts'
import { useAuth } from './useKeycloak'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { snakeToCamel } from '../utils/caseConverters'

export type FeatureLifecycleStage = 'off' | 'preview' | 'live'

export interface FeatureLifecycleState {
  enabled: boolean
  stage: FeatureLifecycleStage
}

export type FeatureLifecycleMap = Record<string, FeatureLifecycleState>

const normalizeStage = (value: unknown): FeatureLifecycleStage => {
  const normalized = String(value || 'preview').toLowerCase().trim()
  if (normalized === 'off' || normalized === 'live' || normalized === 'preview') {
    return normalized
  }
  return 'preview'
}

const defaultFeatureMap: FeatureLifecycleMap = {
  feature_rule_validation: { enabled: true, stage: 'live' },
  feature_rule_lifecycle_management: { enabled: true, stage: 'preview' },
  feature_rule_result_aggregation: { enabled: true, stage: 'preview' },
  feature_rule_suggestions: { enabled: true, stage: 'live' },
  feature_exception_record_handling: { enabled: true, stage: 'preview' },
  feature_rule_execution_monitoring: { enabled: true, stage: 'preview' },
  feature_aliases_business_terms: { enabled: true, stage: 'preview' },
}

export const useFeatureLifecycleConfig = () => {
  const settings = useSettings()
  const [featureMap, setFeatureMap] = useState<FeatureLifecycleMap>(defaultFeatureMap)
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken())
  const auth = useAuth()

  useEffect(() => {
    const syncTokenFromStorage = () => {
      setAuthToken(getAuthToken())
    }

    syncTokenFromStorage()
    if (typeof window !== 'undefined') {
      window.addEventListener('storage', syncTokenFromStorage)
      window.addEventListener('dq-auth-token-changed', syncTokenFromStorage)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('storage', syncTokenFromStorage)
        window.removeEventListener('dq-auth-token-changed', syncTokenFromStorage)
      }
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    const loadFeatureConfig = async () => {
      // Allow config fetch with credentials if authenticated, not just with a token
      const isSessionAuth = auth.isAuthenticated && !authToken
      if (!authToken && !isSessionAuth) {
        if (!cancelled) {
          setFeatureMap(defaultFeatureMap)
        }
        return
      }

      try {
        const apiBase = toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)
        const fetchOpts: RequestInit = authToken
          ? { headers: { Authorization: `Bearer ${authToken}` } }
          : { credentials: 'include' }
        const response = await fetch(`${apiBase}/app-config`, fetchOpts)
        if (!response.ok) return

        const config = snakeToCamel<Record<string, unknown>>(await response.json())
        if (cancelled) return

        const configRecord = (config || {}) as Record<string, unknown>

        setFeatureMap({
          feature_rule_validation: {
            enabled: Boolean(configRecord.featureRuleValidation ?? true),
            stage: normalizeStage(configRecord.featureRuleValidationStage),
          },
          feature_rule_lifecycle_management: {
            enabled: Boolean(configRecord.featureRuleLifecycleManagement ?? true),
            stage: normalizeStage(configRecord.featureRuleLifecycleManagementStage),
          },
          feature_rule_result_aggregation: {
            enabled: Boolean(configRecord.featureRuleResultAggregation ?? true),
            stage: normalizeStage(configRecord.featureRuleResultAggregationStage),
          },
          feature_rule_suggestions: {
            enabled: Boolean(configRecord.featureRuleSuggestions ?? true),
            stage: normalizeStage(configRecord.featureRuleSuggestionsStage),
          },
          feature_exception_record_handling: {
            enabled: Boolean(configRecord.featureExceptionRecordHandling ?? true),
            stage: normalizeStage(configRecord.featureExceptionRecordHandlingStage),
          },
          feature_rule_execution_monitoring: {
            enabled: Boolean(configRecord.featureRuleExecutionMonitoring ?? true),
            stage: normalizeStage(configRecord.featureRuleExecutionMonitoringStage),
          },
          feature_aliases_business_terms: {
            enabled: Boolean(configRecord.featureAliasesBusinessTerms ?? true),
            stage: normalizeStage(configRecord.featureAliasesBusinessTermsStage),
          },
        })
      } catch {
        if (!cancelled) {
          setFeatureMap(defaultFeatureMap)
        }
      }
    }

    loadFeatureConfig()

    return () => {
      cancelled = true
    }
  }, [settings.applicationSettings?.apiBaseUrl, authToken])

  return useMemo(() => ({
    featureMap,
    getFeatureState: (featureKey: string): FeatureLifecycleState =>
      featureMap[featureKey] || { enabled: false, stage: 'off' },
  }), [featureMap])
}
