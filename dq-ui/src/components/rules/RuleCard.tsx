import React, { useState, useEffect } from 'react'
import { Button } from '../Button'
import { TestResultsVisualization } from '../TestResultsVisualization'
import { RuleVersioningContainer } from '../RuleVersioningContainer'
import { DriftAlert } from '../DriftAlert'
import { RevalidationProgress } from '../RevalidationProgress'
import { Rule, RuleAttributeThresholds, RuleStatus, RuleVersion } from '../../types/rules'
import { useCatalogDrift, RuleDriftInfo } from '../../hooks/useCatalogDrift'
import { useBatchRevalidation } from '../../hooks/useBatchRevalidation'
import { useMonitorNotifications } from '../../hooks/useMonitorNotifications'
import { useSettings } from '../../hooks/useContexts'
import { AppIcon } from '../app-primitives'
import { getWorkspaceDisplayName } from '../WorkspaceSelector'
import {
  ResolvedRuleAttribute,
  buildCompleteRuleExpression,
  buildExpressionWithReusableFilters,
  buildJoinExpression,
  getAssignedAttributes,
  getJoinConditionCount,
  getJoinDefinitionsWithConditions,
  riskLevelLabels,
  statusBadgeMeta,
  statusColors,
  statusLabels,
} from './ruleDisplayUtils'
import { AttributeCard } from './AttributeCard'

export interface RuleNotice {
  type: 'success' | 'error'
  message: string
  ruleId?: string
  details?: string[]
}

type RuleActionType = 'submit' | 'deactivate' | 'approve' | 'activate' | 'template' | 'assign' | 'join' | 'test' | 'filter' | 'reusable-join' | 'validate' | 'edit'
  | 'adhoc-run'
type DetailTab = 'details' | 'versions'

export const shouldShowDeactivationRequestedBadge = (
  ruleStatus: RuleStatus,
  pendingDeactivationRequested: boolean,
): boolean => {
  return pendingDeactivationRequested && (ruleStatus === 'activated' || ruleStatus === 'pending-approval')
}

export const resolveRuleAttributeDisplayName = (
  attributeCatalog: Record<string, ResolvedRuleAttribute>,
  attributeId: string,
): string => {
  const resolvedAttribute = attributeCatalog[attributeId]
  const attributeName = String(resolvedAttribute?.name || '').trim()
  const sourceLabel = [resolvedAttribute?.datasetName, resolvedAttribute?.dataObjectName].filter(Boolean).join(' / ')

  if (attributeName) {
    return sourceLabel ? `${sourceLabel} – ${attributeName}` : attributeName
  }

  return sourceLabel || 'Unresolved attribute'
}

const COMPLETENESS_METRICS = new Set(['null_pct', 'empty_pct', 'default_val_pct'])
const MISSING_COUNT_METRICS = new Set(['missing_count'])
const DUPLICATE_COUNT_METRICS = new Set(['duplicate_count'])
const DUPLICATE_PERCENT_METRICS = new Set(['duplicate_percent'])
const RAW_AGGREGATE_METRICS = new Set(['min', 'max', 'avg', 'sum', 'stddev'])
const DISTINCT_COUNT_METRICS = new Set(['distinct_count'])

export const resolveRuleThresholdDisplayValue = (
  rule: Rule,
  configuredDefaultThreshold: number,
): string | null => {
  const thresholdParams = (rule.checkTypeParams ?? (rule.dsl as any)?.source?.checkTypeParams ?? null) as any
  const normalizedCheckType = String(rule.checkType || (rule.dsl as any)?.source?.checkType || '').toUpperCase()
  const isRowCountRule = normalizedCheckType === 'ROW_COUNT'
  const metric = String(thresholdParams?.metric || '').toLowerCase()
  const hasThresholdParam = thresholdParams?.threshold != null
  const isThresholdRule = normalizedCheckType === 'THRESHOLD' || hasThresholdParam
  const isLegacyRuleWithoutCheckType = !normalizedCheckType

  if (!isThresholdRule && !isLegacyRuleWithoutCheckType && !isRowCountRule) {
    return null
  }

  if (isRowCountRule) {
    const operator = String(thresholdParams?.operator || 'gte')
    if (operator === 'between') {
      const minValue = Number(thresholdParams?.minValue)
      const maxValue = Number(thresholdParams?.maxValue)
      if (Number.isFinite(minValue) && Number.isFinite(maxValue)) {
        return `${minValue} to ${maxValue} rows`
      }
      return 'Not set'
    }

    const thresholdValue = Number(thresholdParams?.threshold)
    if (!Number.isFinite(thresholdValue)) {
      return 'Not set'
    }

    const operatorLabels: Record<string, string> = {
      gt: '>',
      gte: '>=',
      lt: '<',
      lte: '<=',
    }
    return `${operatorLabels[operator] || '>='} ${thresholdValue} rows`
  }

  const isQuantileThreshold = normalizedCheckType === 'THRESHOLD' && metric === 'quantile'
  const isCompletenessMetric = !metric || COMPLETENESS_METRICS.has(metric)
  const isMissingCountMetric = MISSING_COUNT_METRICS.has(metric)
  const isDuplicateCountMetric = DUPLICATE_COUNT_METRICS.has(metric)
  const isDuplicatePercentMetric = DUPLICATE_PERCENT_METRICS.has(metric)
  const isDistinctCountMetric = DISTINCT_COUNT_METRICS.has(metric)
  const isRawAggregateMetric = RAW_AGGREGATE_METRICS.has(metric)
  const quantileValue = Number(thresholdParams?.quantile)
  const quantilePercent = Number.isNaN(quantileValue) ? null : `${Math.round(quantileValue * 1000) / 10}%`
  const thresholdValue = Number(thresholdParams?.threshold)
  const hasExplicitRuleThreshold = Number.isFinite(thresholdValue)
  const ruleLevelThreshold = hasExplicitRuleThreshold
    ? thresholdValue
    : (isQuantileThreshold || (!isCompletenessMetric && !isLegacyRuleWithoutCheckType) ? null : configuredDefaultThreshold)

  if (ruleLevelThreshold == null) {
    return isQuantileThreshold && quantilePercent ? `Not set (quantile ${quantilePercent})` : 'Not set'
  }

  return isQuantileThreshold && quantilePercent
    ? `${ruleLevelThreshold} (quantile ${quantilePercent})`
    : isMissingCountMetric
      ? `${ruleLevelThreshold} missing rows`
      : isDuplicateCountMetric
        ? `${ruleLevelThreshold} duplicate rows`
        : isDuplicatePercentMetric
          ? `${ruleLevelThreshold}% duplicate rate`
    : isCompletenessMetric
      ? `${ruleLevelThreshold}%`
      : isDistinctCountMetric
        ? `${ruleLevelThreshold} distinct values`
        : isRawAggregateMetric
          ? `${ruleLevelThreshold}`
          : `${ruleLevelThreshold}%`
}

export const resolveRuleThresholdBadgeContent = (
  rule: Rule,
  configuredDefaultThreshold: number,
): { label: string; title: string } | null => {
  const thresholdDisplayValue = resolveRuleThresholdDisplayValue(rule, configuredDefaultThreshold)
  if (thresholdDisplayValue == null || String(thresholdDisplayValue).startsWith('Not set')) {
    return null
  }

  const thresholdParams = (rule.checkTypeParams ?? (rule.dsl as any)?.source?.checkTypeParams ?? {}) as any
  const normalizedCheckType = String(rule.checkType || (rule.dsl as any)?.source?.checkType || '').toUpperCase()
  const hasThresholdParam = thresholdParams?.threshold != null
  const isRowCountRule = normalizedCheckType === 'ROW_COUNT'
  const hasExplicitRuleThreshold = hasThresholdParam || isRowCountRule

  if (hasExplicitRuleThreshold) {
    return {
      label: thresholdDisplayValue,
      title: `Rule threshold: ${thresholdDisplayValue}`,
    }
  }

  return {
    label: 'app default',
    title: `Rule threshold uses app default: ${thresholdDisplayValue}`,
  }
}

const formatValidationBadgeDate = (value?: string | null): string | null => {
  if (!value) {
    return null
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return null
  }

  return parsed.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
}

export const getValidationBadgeMeta = (
  validationState: 'valid' | 'invalid' | 'upstream-error' | null,
  validatedAt?: string | null,
): { label: string; title: string } | null => {
  if (!validationState) {
    return null
  }

  const validationDateLabel = formatValidationBadgeDate(validatedAt)

  if (validationState === 'valid') {
    return {
      label: validationDateLabel ? `Validated ${validationDateLabel}` : 'Validated',
      title: validationDateLabel ? `Validated successfully on ${validationDateLabel}` : 'Validated successfully',
    }
  }

  if (validationState === 'upstream-error') {
    return {
      label: validationDateLabel ? `Validation Error ${validationDateLabel}` : 'Validation Error',
      title: validationDateLabel ? `Validation service error (upstream) on ${validationDateLabel}` : 'Validation service error (upstream)',
    }
  }

  return {
    label: validationDateLabel ? `Invalid ${validationDateLabel}` : 'Invalid',
    title: validationDateLabel ? `Validation failed on ${validationDateLabel}` : 'Validation failed',
  }
}

interface RuleCardAction {
  label: string
  type: RuleActionType
  show: boolean
  disabled?: boolean
  disabledTitle?: string
}

interface RuleCardProps {
  rule: Rule
  pendingDeactivationRequested?: boolean
  currentWorkspaceId: string | null
  selectedRuleId: string | null
  selectedBulkRuleIds: Set<string>
  expandedRuleId: string | null
  testNotice: RuleNotice | null
  compiledExpressionByRuleId: Record<string, string>
  latestCompiledInfoByRuleId: Record<string, {
    ruleVersionId: string | null
    ruleVersionNumber: number | null
    compiledExpression: string | null
    compilerVersion: string | null
    compilerRevision: number | null
    compileStatus: string | null
    compiledAt: string | null
  }>
  attributeCatalog: Record<string, ResolvedRuleAttribute>
  ruleAttributeMappings: Record<string, string[]>
  ruleAttributeThresholds: RuleAttributeThresholds
  onSelectRule?: (rule: Rule) => void
  onSelectRuleId: (ruleId: string) => void
  onToggleBulkSelect: (ruleId: string) => void
  onToggleExpand: (ruleId: string) => void
  getExpandedTab: (ruleId: string) => DetailTab
  onSetExpandedTab: (ruleId: string, tab: DetailTab) => void
  getEffectiveValidationState: (rule: Rule) => 'valid' | 'invalid' | 'upstream-error' | null
  getRuleActionButtons: (rule: Rule) => RuleCardAction[]
  canTransitionTo: (rule: Rule, targetStatus: RuleStatus) => boolean
  getActionTitle: (type: RuleActionType) => string
  getActionIcon: (type: RuleActionType) => string
  onValidateRule: (ruleId: string) => void
  onOpenRuleValidation?: () => void
  onEditRule: (ruleId: string) => void
  onOpenActionModal: (ruleId: string, type: Exclude<RuleActionType, 'validate'>, readOnly?: boolean) => void
  renderNoticeContent: (notice: RuleNotice) => React.ReactNode
  onCopyJoinExpression: (ruleId: string, expression: string) => void
  onCopyCompleteExpression: (ruleId: string, expression: string) => void
  toCurrentRuleVersion: (rule: Rule) => RuleVersion
  onRollbackComplete: (ruleId: string, newVersionId: string) => void
}

export const RuleCard: React.FC<RuleCardProps> = ({
  rule,
  pendingDeactivationRequested = false,
  currentWorkspaceId,
  selectedRuleId,
  selectedBulkRuleIds,
  expandedRuleId,
  testNotice,
  compiledExpressionByRuleId,
  latestCompiledInfoByRuleId,
  attributeCatalog,
  ruleAttributeMappings,
  ruleAttributeThresholds,
  onSelectRule,
  onSelectRuleId,
  onToggleBulkSelect,
  onToggleExpand,
  getExpandedTab,
  onSetExpandedTab,
  getEffectiveValidationState,
  getRuleActionButtons,
  canTransitionTo,
  getActionTitle,
  getActionIcon,
  onValidateRule,
  onOpenRuleValidation,
  onEditRule,
  onOpenActionModal,
  renderNoticeContent,
  onCopyJoinExpression,
  onCopyCompleteExpression,
  toCurrentRuleVersion,
  onRollbackComplete,
}) => {
  const settings = useSettings()
  const compactMode = settings.displaySettings?.compactMode ?? false
  const { checkRuleDrift } = useCatalogDrift()
  const { subscribeWorkspaceNotifications } = useMonitorNotifications()
  const { startRevalidationJob, getJobStatus } = useBatchRevalidation()
  const [ruleDrift, setRuleDrift] = useState<RuleDriftInfo | null>(null)
  const [driftLoading, setDriftLoading] = useState(false)
  const [revalidationJobId, setRevalidationJobId] = useState<string | null>(null)
  const [showRevalidationProgress, setShowRevalidationProgress] = useState(false)
  const [dismissedDrift, setDismissedDrift] = useState(false)

  // Check for drift when rule is expanded
  useEffect(() => {
    if (expandedRuleId === rule.id && !dismissedDrift) {
      const currentVersion = toCurrentRuleVersion(rule)
      if (currentVersion) {
        setDriftLoading(true)
        checkRuleDrift(rule.id, currentVersion.id)
          .then(drift => {
            setRuleDrift(drift)
            setDriftLoading(false)
          })
          .catch(err => {
            console.error('Failed to check drift:', err)
            setDriftLoading(false)
          })
      }
    }
  }, [expandedRuleId, rule.id, dismissedDrift, toCurrentRuleVersion, checkRuleDrift])

  // Handle revalidation
  const handleRevalidate = async () => {
    try {
      const currentVersion = toCurrentRuleVersion(rule)
      if (!currentVersion) return

      const result = await startRevalidationJob([currentVersion.id])
      setRevalidationJobId(result.jobId)
      setShowRevalidationProgress(true)
      
      // Reset drift after revalidation is triggered
      setDismissedDrift(true)
      setRuleDrift(null)
    } catch (err) {
      console.error('Failed to start revalidation:', err)
    }
  }

  const handleDriftDismiss = () => {
    setDismissedDrift(true)
    setRuleDrift(null)
  }

  const handleSubscribeToNotifications = async () => {
    const workspaceId = String(rule.workspace || currentWorkspaceId || '').trim()
    if (!workspaceId) {
      return
    }

    await subscribeWorkspaceNotifications(workspaceId)
  }

  const currentVersion = toCurrentRuleVersion(rule)
  const effectiveValidationState = getEffectiveValidationState(rule)
  const validationBadgeMeta = getValidationBadgeMeta(effectiveValidationState, rule.validatedAt)
  const statusMeta = statusBadgeMeta(rule.status)
  const riskLabel =
    riskLevelLabels[rule.riskLevel] ??
    rule.riskLevel.charAt(0).toUpperCase() + rule.riskLevel.slice(1)
  const assignedAttributes = getAssignedAttributes(rule, ruleAttributeMappings)
  const attributeThresholdOverrides = ruleAttributeThresholds[rule.id] || {}
  const thresholdOverrideCount = Object.values(attributeThresholdOverrides).filter(v => v != null).length
  const configuredDefaultThreshold = Number(settings.applicationSettings?.defaultRuleThresholdPct ?? 0)
  const thresholdDisplayValue = resolveRuleThresholdDisplayValue(rule, configuredDefaultThreshold)
  const thresholdBadgeContent = resolveRuleThresholdBadgeContent(rule, configuredDefaultThreshold)
  const normalizedCheckType = String(rule.checkType || (rule.dsl as any)?.source?.checkType || '').toUpperCase()
  const isRowCountRule = normalizedCheckType === 'ROW_COUNT'
  const thresholdParams = (rule.checkTypeParams ?? (rule.dsl as any)?.source?.checkTypeParams ?? {}) as any
  const metric = String(thresholdParams?.metric || '').toLowerCase()
  const hasThresholdParam = thresholdParams?.threshold != null
  const hasExplicitRuleThreshold = hasThresholdParam || isRowCountRule
  const isThresholdRule = normalizedCheckType === 'THRESHOLD' || hasThresholdParam
  const isLegacyRuleWithoutCheckType = !normalizedCheckType
  const hasThresholdBadge = thresholdBadgeContent != null
  const shouldShowThreshold = isThresholdRule || isRowCountRule || isLegacyRuleWithoutCheckType || thresholdOverrideCount > 0
  const isQuantileThreshold = normalizedCheckType === 'THRESHOLD' && metric === 'quantile'
  const quantileValue = Number(thresholdParams?.quantile)
  const quantilePercent = Number.isNaN(quantileValue) ? null : `${Math.round(quantileValue * 1000) / 10}%`
  const displayedAttributes = assignedAttributes.map((attributeId) => {
    const resolved = attributeCatalog[attributeId]
    return resolved || ({ id: attributeId, name: '' } as ResolvedRuleAttribute)
  })
  const joinConditionCount = getJoinConditionCount(rule)
  const reusableJoinId = String(rule.reusableJoinId || '').trim()
  const reusableFilterIds = Array.isArray(rule.reusableFilterIds)
    ? rule.reusableFilterIds.map((filterId) => String(filterId || '').trim()).filter(Boolean)
    : []
  const reusableFilterCount = reusableFilterIds.length
  const joinDefinitions = getJoinDefinitionsWithConditions(rule)
  const joinExpression = buildJoinExpression(joinDefinitions)
  const completeRuleExpression =
    compiledExpressionByRuleId[rule.id]
      ? buildExpressionWithReusableFilters(rule, compiledExpressionByRuleId[rule.id])
      : buildCompleteRuleExpression(rule)
  const latestCompiledInfo = latestCompiledInfoByRuleId[rule.id]
  const persistedCompiledExpression = latestCompiledInfo?.compiledExpression || null
  const latestCompiledExpressionSource =
    persistedCompiledExpression || compiledExpressionByRuleId[rule.id] || null
  const latestCompiledExpression = latestCompiledExpressionSource
    ? buildExpressionWithReusableFilters(rule, latestCompiledExpressionSource)
    : null
  const persistedVersionLabel =
    latestCompiledInfo?.ruleVersionNumber != null
      ? `V${latestCompiledInfo.ruleVersionNumber}`
      : `V${rule.currentVersionNumber ?? currentVersion?.versionNumber ?? 1}`
  const driftCount = Math.max(ruleDrift?.totalDrifts || 0, ruleDrift?.drifts?.length || 0)
  const hasDetectedDrift = Boolean(
    ruleDrift
      && (driftCount > 0 || (ruleDrift.affectedAliases?.length || 0) > 0)
  )
  const isVersionLocked = rule.status === 'approved' || rule.status === 'activated'
  const reusableAssetsReadOnly = isVersionLocked
  const ruleWorkspaceId = String(rule.workspace || '').trim()
  const ruleWorkspaceLabel = ruleWorkspaceId ? getWorkspaceDisplayName(ruleWorkspaceId) : ''

  const primaryLifecycleStages: Array<{ status: RuleStatus; label: string }> = [
    { status: 'draft', label: 'Draft' },
    { status: 'testing', label: 'Testing' },
    { status: 'tested', label: 'Tested' },
    { status: 'pending-approval', label: 'Pending Approval' },
    { status: 'approved', label: 'Approved' },
    { status: 'activated', label: 'Activated' },
  ]
  const allTransitionTargets: RuleStatus[] = [
    'draft',
    'testing',
    'tested',
    'pending-approval',
    'approved',
    'activated',
    'rejected',
  ]
  const compactStageLabels: Record<RuleStatus, string> = {
    draft: 'Draft',
    testing: 'Test',
    tested: 'Ready',
    'pending-approval': 'Review',
    approved: 'OK',
    activated: 'Live',
    deactivated: 'Retired',
    rejected: 'Rejected',
  }
  const timelineStatus = rule.status === 'deactivated' ? 'activated' : rule.status
  const currentPrimaryIndex = primaryLifecycleStages.findIndex((stage) => stage.status === timelineStatus)
  const nextStatuses = rule.status === 'activated' || rule.status === 'deactivated'
    ? []
    : allTransitionTargets.filter(
        (candidate) => candidate !== rule.status && canTransitionTo(rule, candidate)
      )
  const nextLabels = nextStatuses.map((status) => statusLabels[status])

  return (
    <div
      className={`rule-card ${selectedRuleId === rule.id ? 'selected' : ''}`}
      onClick={() => {
        onSelectRuleId(rule.id)
        onSelectRule?.(rule)
      }}
    >
      <div className="rule-header">
        <input
          type="checkbox"
          className="rule-checkbox"
          checked={selectedBulkRuleIds.has(rule.id)}
          onChange={(e) => {
            e.stopPropagation()
            onToggleBulkSelect(rule.id)
          }}
          aria-label={`Select ${rule.name}`}
        />
        <div className="rule-title-section">
          <h3>{rule.name}</h3>
          <div className="rule-badges">
            <span
              className="join-badge rule-badge-neutral rule-badge-neutral-compact"
              title={isVersionLocked
                ? 'Version locked after approval. Create a new version (rollback/reopen flow) to make changes.'
                : 'Version is editable.'}
              aria-label={isVersionLocked ? 'Version locked after approval' : 'Version editable'}
            >
              <AppIcon
                className="join-icon"
                name={isVersionLocked ? 'padlock-closed' : 'padlock-open'}
              />
            </span>
            <span
              className="status-badge dq-status-badge"
              title={`Rule lifecycle status: ${statusLabels[rule.status]}`}
              style={{
                backgroundColor: statusColors[rule.status].bg,
                color: statusColors[rule.status].text,
                padding: '4px 8px',
                borderRadius: '4px',
                fontSize: '12px',
                fontWeight: 'bold',
              }}
            >
              <AppIcon className="status-icon" name={statusMeta.icon} />
              {statusLabels[rule.status]}
            </span>
            {shouldShowDeactivationRequestedBadge(rule.status, pendingDeactivationRequested) && (
              <span
                className="join-badge rule-badge-neutral"
                title="Deactivation requested and awaiting approval"
                aria-label="Deactivation requested and awaiting approval"
                style={{
                  backgroundColor: 'rgba(245, 124, 0, 0.12)',
                  color: '#f57c00',
                  padding: '4px 8px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: 'bold',
                  border: '1px solid #f57c00',
                }}
              >
                <AppIcon className="join-icon" name="clock" />
                Deactivation Requested
              </span>
            )}
            <span
              className="risk-badge rule-badge-neutral"
              title={`Risk level: ${riskLabel}`}
            >
              <AppIcon className="risk-icon" name="exclamation-triangle" />
              {riskLabel}
            </span>
            {ruleWorkspaceLabel && (
              <span
                className="workspace-origin-badge rule-badge-neutral"
                title={`Defined in workspace: ${ruleWorkspaceLabel}`}
                aria-label={`Rule defined in workspace ${ruleWorkspaceLabel}`}
              >
                <AppIcon className="workspace-origin-icon" name="globe" />
                {ruleWorkspaceLabel}
              </span>
            )}
            {shouldShowThreshold && hasThresholdBadge && (
              <span
                className="threshold-badge dq-status-badge rule-badge-neutral"
                title={thresholdBadgeContent.title}
              >
                <AppIcon className="threshold-icon" name="line-chart" />
                Threshold {thresholdBadgeContent.label}
              </span>
            )}
            <span
              className="join-badge rule-badge-neutral"
              title={`Current rule version: V${rule.currentVersionNumber ?? 1}`}
            >
              <AppIcon className="join-icon" name="bookmark" />
              V{rule.currentVersionNumber ?? 1}
            </span>
            {assignedAttributes.length > 0 && (
              <span
                className="attributes-badge rule-badge-neutral"
                title={`${assignedAttributes.length} assigned attribute${assignedAttributes.length !== 1 ? 's' : ''} used by this rule`}
              >
                <AppIcon className="attributes-icon" name="list" />
                {assignedAttributes.length} attribute{assignedAttributes.length !== 1 ? 's' : ''}
              </span>
            )}
            {shouldShowThreshold && thresholdOverrideCount > 0 && (
              <span
                className="join-badge rule-badge-neutral"
                title={`${thresholdOverrideCount} attribute-level threshold override${thresholdOverrideCount === 1 ? '' : 's'}`}
              >
                <AppIcon className="join-icon" name="sliders" />
                {thresholdOverrideCount} threshold override{thresholdOverrideCount === 1 ? '' : 's'}
              </span>
            )}
            {joinConditionCount > 0 && (
              <span
                className="join-badge rule-badge-neutral"
                title={`${joinConditionCount} join condition${joinConditionCount !== 1 ? 's' : ''} included in this rule`}
              >
                <AppIcon className="join-icon" name="link" />
                {joinConditionCount} join condition{joinConditionCount !== 1 ? 's' : ''}
              </span>
            )}
            {reusableFilterCount > 0 && (
              <span
                className="join-badge rule-badge-neutral"
                title={`${reusableFilterCount} reusable filter${reusableFilterCount === 1 ? '' : 's'} linked to this rule`}
              >
                <AppIcon className="join-icon" name="filter" />
                {reusableFilterCount} reusable filter{reusableFilterCount === 1 ? '' : 's'}
              </span>
            )}
            {effectiveValidationState && validationBadgeMeta && (
              <span
                className="validation-state-badge dq-status-badge"
                title={validationBadgeMeta.title}
                style={{
                  backgroundColor: effectiveValidationState === 'valid'
                    ? 'var(--dq-status-success-bg, #e6f7e6)'
                    : effectiveValidationState === 'upstream-error'
                      ? 'rgba(245, 124, 0, 0.12)'
                      : 'rgba(211, 47, 47, 0.10)',
                  color: effectiveValidationState === 'valid'
                    ? 'var(--dq-status-success-text, #1f7a1f)'
                    : effectiveValidationState === 'upstream-error'
                      ? 'var(--dq-status-warning-text, #e65100)'
                      : 'var(--dq-status-error-text, #c62828)',
                  padding: '4px 8px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: 'bold',
                }}
              >
                <AppIcon
                  className="validation-state-icon"
                  name={effectiveValidationState === 'valid'
                    ? 'check-circle'
                    : effectiveValidationState === 'upstream-error'
                      ? 'exclamation-triangle'
                      : 'exclamation-circle'}
                />
                {validationBadgeMeta.label}
              </span>
            )}
            {rule.createdFromSuggestion && (
              <span
                className="suggestion-badge rule-badge-neutral"
                title={`Created from AI suggestion ${rule.suggestionId ? `(${rule.suggestionId})` : ''}`}
              >
                <AppIcon className="suggestion-icon" name="lightbulb" />
                AI Suggestion
              </span>
            )}
            {hasDetectedDrift && !dismissedDrift && (
              <span
                className="drift-badge"
                style={{
                  backgroundColor: ruleDrift!.drifts.some(d => d.severity === 'critical') ? 'rgba(211, 47, 47, 0.12)' : 'rgba(245, 124, 0, 0.12)',
                  color: ruleDrift!.drifts.some(d => d.severity === 'critical') ? '#d32f2f' : '#f57c00',
                  padding: '4px 8px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: 'bold',
                  border: `1px solid ${ruleDrift!.drifts.some(d => d.severity === 'critical') ? '#d32f2f' : '#f57c00'}`,
                }}
                title={`${driftCount} drift${driftCount > 1 ? 's' : ''} detected in business terms`}
              >
                <AppIcon className="drift-icon" name={ruleDrift!.drifts.some(d => d.severity === 'critical') ? 'exclamation-circle' : 'exclamation-triangle'} />
                {driftCount} Drift Issue{driftCount > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
        <button
          className="expand-btn"
          onClick={e => {
            e.stopPropagation()
            onToggleExpand(rule.id)
          }}
        >
          {expandedRuleId === rule.id ? '▼' : '▶'}
        </button>

        {selectedRuleId === rule.id && (
          <>
                <div className="rule-quick-actions" style={{
                  display: 'flex',
                  gap: '4px',
                  marginLeft: '8px',
                }}>
                  {getRuleActionButtons(rule).map(action => (
                    <button
                      key={action.type}
                      className="icon-action-btn"
                      title={action.disabled && action.disabledTitle ? action.disabledTitle : getActionTitle(action.type)}
                      onClick={(e: any) => {
                        e.stopPropagation()
                        if (action.type === 'validate') {
                          onValidateRule(rule.id)
                          return
                        }
                        if (action.type === 'edit') {
                          onEditRule(rule.id)
                          return
                        }
                        onOpenActionModal(rule.id, action.type, reusableAssetsReadOnly)
                      }}
                      disabled={action.disabled}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        padding: '4px 6px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        borderRadius: '4px',
                        color: 'var(--app-text-secondary)',
                        transition: 'all 0.2s ease',
                      }}
                      onMouseEnter={(e: any) => {
                        e.target.style.backgroundColor = 'var(--app-surface-secondary)'
                        e.target.style.color = 'var(--app-brand-primary)'
                      }}
                      onMouseLeave={(e: any) => {
                        e.target.style.backgroundColor = 'transparent'
                        e.target.style.color = 'var(--app-text-secondary)'
                      }}
                    >
                      <AppIcon name={getActionIcon(action.type)} />
                    </button>
                  ))}
                  {onOpenRuleValidation && (
                    <button
                      className="icon-action-btn"
                      title="Open this rule in Rule Validation"
                      onClick={(e: any) => {
                        e.stopPropagation()
                        onOpenRuleValidation()
                      }}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        padding: '4px 6px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        borderRadius: '4px',
                        color: 'var(--app-text-secondary)',
                        transition: 'all 0.2s ease',
                      }}
                      onMouseEnter={(e: any) => {
                        e.target.style.backgroundColor = 'var(--app-surface-secondary)'
                        e.target.style.color = 'var(--app-brand-primary)'
                      }}
                      onMouseLeave={(e: any) => {
                        e.target.style.backgroundColor = 'transparent'
                        e.target.style.color = 'var(--app-text-secondary)'
                      }}
                    >
                      <AppIcon name="check-circle" />
                    </button>
                  )}
                  {isVersionLocked && (
                    <>
                      <button
                        className="icon-action-btn"
                        title={`View reusable filters${reusableFilterCount > 0 ? ` (${reusableFilterCount})` : ''}`}
                        onClick={(e: any) => {
                          e.stopPropagation()
                          onOpenActionModal(rule.id, 'filter', true)
                        }}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          cursor: 'pointer',
                          padding: '4px 6px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          borderRadius: '4px',
                          color: 'var(--app-text-secondary)',
                          transition: 'all 0.2s ease',
                        }}
                        onMouseEnter={(e: any) => {
                          e.target.style.backgroundColor = 'var(--app-surface-secondary)'
                          e.target.style.color = 'var(--app-brand-primary)'
                        }}
                        onMouseLeave={(e: any) => {
                          e.target.style.backgroundColor = 'transparent'
                          e.target.style.color = 'var(--app-text-secondary)'
                        }}
                      >
                        <AppIcon name="filter" />
                      </button>
                      <button
                        className="icon-action-btn"
                        title={`View reusable join${reusableJoinId ? '' : ' (none)'}`}
                        onClick={(e: any) => {
                          e.stopPropagation()
                          onOpenActionModal(rule.id, 'reusable-join', true)
                        }}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          cursor: 'pointer',
                          padding: '4px 6px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          borderRadius: '4px',
                          color: 'var(--app-text-secondary)',
                          transition: 'all 0.2s ease',
                        }}
                        onMouseEnter={(e: any) => {
                          e.target.style.backgroundColor = 'var(--app-surface-secondary)'
                          e.target.style.color = 'var(--app-brand-primary)'
                        }}
                        onMouseLeave={(e: any) => {
                          e.target.style.backgroundColor = 'transparent'
                          e.target.style.color = 'var(--app-text-secondary)'
                        }}
                      >
                        <AppIcon name="link" />
                      </button>
                    </>
                  )}
                </div>
          </>
        )}
      </div>

      <p className="rule-description">{rule.description}</p>
      {rule.comments && (
        <p className="rule-description rule-comments"><strong>Comments:</strong> {rule.comments}</p>
      )}

      <div className="rule-stage-timeline" aria-label="Rule lifecycle progress">
        <div className="rule-stage-track">
          {primaryLifecycleStages.map((stage, index) => {
            const isCurrent = rule.status === stage.status
            const isCompleted = currentPrimaryIndex > -1 && index < currentPrimaryIndex
            const isNext = !isCurrent && nextStatuses.includes(stage.status)

            return (
              <div
                key={`${rule.id}-${stage.status}`}
                className={`rule-stage-item${isCompleted ? ' completed' : ''}${isCurrent ? ' current' : ''}${isNext ? ' next' : ''}`}
              >
                <span className="rule-stage-dot" />
                <span className="rule-stage-label">
                  {compactMode ? compactStageLabels[stage.status] : stage.label}
                </span>
              </div>
            )
          })}
        </div>
        <div className="rule-stage-summary">
          <span>
            Current: <strong>{statusLabels[rule.status]}</strong>
          </span>
          {nextLabels.length > 0 && (
            <span>
              Next: <strong>{nextLabels.join(', ')}</strong>
            </span>
          )}
        </div>
      </div>

      {testNotice?.ruleId === rule.id && (
        <div className={`rules-notice rule-inline-notice ${testNotice.type}`}>
          {renderNoticeContent(testNotice)}
        </div>
      )}

      {expandedRuleId === rule.id && (
        <div className="rule-expanded">
          <div className="rule-expanded-tabs">
            <button
              type="button"
              className={`rule-expanded-tab ${getExpandedTab(rule.id) === 'details' ? 'active' : ''}`}
              onClick={(e) => {
                e.stopPropagation()
                onSetExpandedTab(rule.id, 'details')
              }}
            >
              Details
            </button>
            <button
              type="button"
              className={`rule-expanded-tab ${getExpandedTab(rule.id) === 'versions' ? 'active' : ''}`}
              onClick={(e) => {
                e.stopPropagation()
                onSetExpandedTab(rule.id, 'versions')
              }}
            >
              Versions
            </button>
          </div>

          {getExpandedTab(rule.id) === 'details' ? (
            <>
              <div className="rule-details">
                <div className="detail-row">
                  <span className="detail-label">Current Version:</span>
                  <span className="detail-value">V{rule.currentVersionNumber ?? currentVersion?.versionNumber ?? 1}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Created by:</span>
                  <span className="detail-value">{rule.createdBy}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Created:</span>
                  <span className="detail-value">
                    {new Date(rule.createdAt).toLocaleDateString()}
                  </span>
                </div>
                {rule.testResults && (
                  <div className="detail-row">
                    <span className="detail-label">DQ Score:</span>
                    <span className="detail-value">{rule.testResults.coverage}%</span>
                  </div>
                )}
                <div className="detail-row">
                  <span className="detail-label">Reusable Join:</span>
                  <span className="detail-value">{reusableJoinId || 'None'}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Reusable Filters{reusableFilterCount > 0 ? ` (${reusableFilterCount})` : ''}:</span>
                  <div className="detail-value">
                    {Array.isArray(rule.reusableFilters) && rule.reusableFilters.length > 0 ? (
                      <div className="rule-attribute-summary">
                        {rule.reusableFilters.map(filter => (
                          <div key={`${rule.id}-filter-${filter.id}`} className="rule-attribute-item">
                            <span className="rule-attribute-name">{filter.name}</span>
                            {filter.description && (
                              <span className="rule-attribute-source">{filter.description}</span>
                            )}
                            <code className="rule-attribute-id">{filter.expression}</code>
                          </div>
                        ))}
                      </div>
                    ) : Array.isArray(rule.reusableFilterIds) && rule.reusableFilterIds.length > 0 ? (
                      <span>{rule.reusableFilterIds.join(', ')}</span>
                    ) : (
                      <span>None</span>
                    )}
                  </div>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Attributes:</span>
                  <div className="detail-value rule-attribute-summary">
                    {assignedAttributes.length > 0 ? (
                      displayedAttributes.map(attribute => {
                        const thresholdBadge = shouldShowThreshold && hasThresholdBadge
                          ? (
                            <span className="rule-attribute-source">
                              {attributeThresholdOverrides[attribute.id] != null
                                ? `Threshold override: ${attributeThresholdOverrides[attribute.id]}${isQuantileThreshold && quantilePercent ? ` (quantile ${quantilePercent})` : '%'}`
                                : `Rule threshold: ${thresholdBadgeContent?.label ?? thresholdDisplayValue}`}
                            </span>
                          )
                          : undefined
                        return (
                          <AttributeCard
                            key={`${rule.id}-${attribute.id}`}
                            attribute={attribute}
                            badge={thresholdBadge}
                          />
                        )
                      })
                    ) : (
                      <span>None</span>
                    )}
                  </div>
                </div>
                {shouldShowThreshold && hasThresholdBadge && (
                  <div className="detail-row">
                    <span className="detail-label">Rule Threshold:</span>
                    <span className="detail-value">{thresholdBadgeContent?.label ?? thresholdDisplayValue}</span>
                  </div>
                )}
                <div className="detail-row">
                  <span className="detail-label">Business Term Mappings:</span>
                  <div className="detail-value rule-attribute-summary">
                    {(rule as any).aliasMappings && Object.keys((rule as any).aliasMappings).length > 0 ? (
                      Object.entries((rule as any).aliasMappings).map(([alias, mapping]: any) => (
                        <div key={`${rule.id}-alias-${alias}`} className="rule-attribute-item">
                          <span className="rule-attribute-name">
                            {alias}{' -> '}{resolveRuleAttributeDisplayName(attributeCatalog, mapping.attributeId)}
                          </span>
                          {mapping.expectedDataType && (
                            <span className="rule-attribute-source">Expected: {mapping.expectedDataType}</span>
                          )}
                          {mapping.actualDataType && (
                            <span className="rule-attribute-source">Actual: {mapping.actualDataType}</span>
                          )}
                        </div>
                      ))
                    ) : (
                      <span>None</span>
                    )}
                  </div>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Join Definitions:</span>
                  <div className="detail-value join-definition-summary">
                    {joinDefinitions.length === 0 ? (
                      <span>None</span>
                    ) : (
                      joinDefinitions.map((definition, index) => {
                        const conditionCount = definition.conditions.length
                        return (
                          <span key={`${rule.id}-join-${index}`} className="join-definition-chip">
                            Join {index + 1}: {definition.joinType.toUpperCase()} ({conditionCount} condition{conditionCount === 1 ? '' : 's'})
                          </span>
                        )
                      })
                    )}
                  </div>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Generated Join Expression:</span>
                  <div className="detail-value rule-join-expression">
                    {joinExpression ? (
                      <div className="rule-join-expression-row">
                        <pre className="rule-join-expression-code">{joinExpression}</pre>
                        <Button
                          className="rule-join-expression-copy"
                          onClick={(e?: React.MouseEvent) => {
                            e?.stopPropagation()
                            onCopyJoinExpression(rule.id, joinExpression)
                          }}
                          aria-label="Copy generated join expression"
                        >
                          <AppIcon name="copy" />
                        </Button>
                      </div>
                    ) : (
                      <span>None</span>
                    )}
                  </div>
                </div>
                <div className="detail-row">
                  <span
                    className="detail-label"
                    title="Draft expression composed in the UI from the rule expression and linked reusable filters. This is not necessarily the latest persisted compiler artifact."
                  >
                    Generated Expression:
                  </span>
                  <div className="detail-value rule-join-expression">
                    {completeRuleExpression ? (
                      <div className="rule-join-expression-row">
                        <pre className="rule-join-expression-code">{completeRuleExpression}</pre>
                        <Button
                          className="rule-join-expression-copy"
                          onClick={(e?: React.MouseEvent) => {
                            e?.stopPropagation()
                            onCopyCompleteExpression(rule.id, completeRuleExpression)
                          }}
                          aria-label="Copy complete rule expression"
                        >
                          <AppIcon name="copy" />
                        </Button>
                      </div>
                    ) : (
                      <span>None</span>
                    )}
                  </div>
                </div>
                <div className="detail-row">
                  <span
                    className="detail-label"
                    title="Most recent compiler-normalized expression for this rule version, loaded from persisted compiler artifacts. Falls back to the latest local validate result if persisted data is not yet refreshed."
                  >
                    Latest Compiled ({persistedVersionLabel}):
                  </span>
                  <div className="detail-value rule-join-expression">
                    {latestCompiledExpression ? (
                      <div className="rule-join-expression-row">
                        <pre className="rule-join-expression-code">{latestCompiledExpression}</pre>
                        <Button
                          className="rule-join-expression-copy"
                          onClick={(e?: React.MouseEvent) => {
                            e?.stopPropagation()
                            onCopyCompleteExpression(rule.id, latestCompiledExpression)
                          }}
                          aria-label="Copy latest compiled expression"
                        >
                          <AppIcon name="copy" />
                        </Button>
                      </div>
                    ) : (
                      <span>Not compiled yet for this version.</span>
                    )}
                  </div>
                </div>
              </div>

              <TestResultsVisualization
                rule={rule}
                isExpanded={true}
              />

              {hasDetectedDrift && !dismissedDrift && (
                <div style={{ marginTop: '16px' }}>
                  <DriftAlert
                    ruleId={rule.id}
                    ruleVersionId={currentVersion?.id || ''}
                    affectedAliases={ruleDrift!.affectedAliases}
                    drifts={ruleDrift!.drifts}
                    needsRevalidation={ruleDrift!.needsRevalidation}
                    onRevalidate={handleRevalidate}
                    onDismiss={handleDriftDismiss}
                    onSubscribeToNotifications={handleSubscribeToNotifications}
                  />
                </div>
              )}
            </>
          ) : (
            <RuleVersioningContainer
              ruleId={rule.id}
              ruleName={rule.name}
              currentVersion={toCurrentRuleVersion(rule)}
              onRollbackComplete={(newVersionId) => onRollbackComplete(rule.id, newVersionId)}
            />
          )}

          <div className="rule-actions">
            {getRuleActionButtons(rule).map(action => (
              <Button
                key={action.type}
                variant="secondary"
                onClick={(e?: React.MouseEvent) => {
                  e?.stopPropagation()
                  if (action.type === 'validate') {
                    onValidateRule(rule.id)
                    return
                  }
                  if (action.type === 'edit') {
                    onEditRule(rule.id)
                    return
                  }
                  onOpenActionModal(rule.id, action.type)
                }}
                disabled={action.disabled}
              >
                {action.label}
              </Button>
            ))}
            {onOpenRuleValidation && (
              <Button
                variant="secondary"
                onClick={(e?: React.MouseEvent) => {
                  e?.stopPropagation()
                  onOpenRuleValidation()
                }}
              >
                Open in Rule Validation
              </Button>
            )}
          </div>
        </div>
      )}

      <RevalidationProgress
        isOpen={showRevalidationProgress}
        jobId={revalidationJobId || ''}
        ruleCount={1}
        onClose={() => setShowRevalidationProgress(false)}
        onGetStatus={getJobStatus}
      />
    </div>
  )
}
