/**
 * Future Features Index
 *
 * This module contains skeleton components for planned features.
 * Each feature can be toggled via feature flags in app-config.csv
 * and preview-stage features require user opt-in while still appearing in
 * their intended navigation area.
 *
 * Features:
 * - feature_rule_validation: Comprehensive rule validation engine
 * - feature_rule_lifecycle_management: Rule state and workflow management
 * - feature_rule_result_aggregation: Combine results from multiple rules
 * - feature_rule_suggestions: AI-powered rule improvement suggestions
 * - feature_exception_record_handling: Exception and exemption management
 * - feature_rule_execution_monitoring: Rule execution and performance monitoring
 */

import { useSettings } from '../../hooks/useContexts'
import type { AppIconName } from '../app-primitives'

export { RuleValidation } from './RuleValidation'
export { RuleLifecycleManagement } from './RuleLifecycleManagement'
export { RuleResultAggregation } from './RuleResultAggregation'
export { RuleSuggestions } from './RuleSuggestions'
export { ExceptionRecordHandling } from './ExceptionRecordHandling'
export { RuleExecutionMonitoring } from './RuleExecutionMonitoring'

/**
 * Feature metadata for discovery and documentation
 */
export const PREVIEW_FEATURES = {
  rule_validation: {
    key: 'feature_rule_validation',
    name: 'Rule Validation',
    description: 'Comprehensive rule syntax and logic validation',
    icon: 'check-circle' satisfies AppIconName,
    category: 'Development Tools',
  },
  rule_lifecycle_management: {
    key: 'feature_rule_lifecycle_management',
    name: 'Lifecycle & Approvals',
    description: 'Manage governance states, approval steps, and policy transitions',
    icon: 'link' satisfies AppIconName,
    category: 'Governance',
  },
  rule_result_aggregation: {
    key: 'feature_rule_result_aggregation',
    name: 'Aggregated Outcomes',
    description: 'Combine runtime results into operational summaries and KPIs',
    icon: 'info-circle' satisfies AppIconName,
    category: 'Operations',
  },
  rule_suggestions: {
    key: 'feature_rule_suggestions',
    name: 'Rule Suggestions',
    description: 'AI-powered recommendations for rule improvements',
    icon: 'lightbulb' satisfies AppIconName,
    category: 'AI & Automation',
  },
  exception_record_handling: {
    key: 'feature_exception_record_handling',
    name: 'Exception Records',
    description: 'View and manage policy-approved exception records and review flows',
    icon: 'padlock-closed' satisfies AppIconName,
    category: 'Governance',
  },
  rule_execution_monitoring: {
    key: 'feature_rule_execution_monitoring',
    name: 'Execution Monitoring',
    description: 'Monitor validation operations, performance, and queue activity',
    icon: 'play-circle' satisfies AppIconName,
    category: 'Operations',
  },
  business_terms_integration: {
    key: 'feature_aliases_business_terms',
    name: 'Business Terms Integration',
    description: 'Catalog integration for business terms and technical attribute mapping with provenance tracking',
    icon: 'book' satisfies AppIconName,
    category: 'Metadata Management',
  },
} as const

export type PreviewFeatureKey = keyof typeof PREVIEW_FEATURES

/**
 * Hook to check if a feature is enabled
 *
 * A feature is only enabled if BOTH conditions are met:
 * 1. Feature flag is enabled in app-config.csv
 * 2. User has opted in when the feature is in preview stage
 *
 * Usage:
 * const isValidationEnabled = useFeatureFlag('feature_rule_validation')
 * if (isValidationEnabled) {
 *   return <RuleValidation />
 * }
 */
export const useFeatureFlag = (featureName: string): boolean => {
  const settings = useSettings()
  
  // TODO: When settings context is fully implemented, check:
  // 1. Feature flag value from applicationSettings
  // 2. User preview opt-in status
  
  // Check if feature flag is enabled in app config
  const featureFlagEnabled = false // TODO: Read from settings.applicationSettings
  
  // Check if user has opted in to preview features
  const userOptedIn = false // TODO: Read from user/session context
  
  // Feature is only enabled if both conditions are met
  return featureFlagEnabled && userOptedIn
}
