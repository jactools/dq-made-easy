import { type Rule, type RuleJoinCondition, type RuleJoinDefinition, type RuleStatus } from '../../types/rules'

export interface ResolvedRuleAttribute {
  id: string
  name: string
  versionId?: string
  dataObjectVersion?: string
  dataObjectId?: string
  dataObjectName?: string
  datasetName?: string
  dataProductName?: string
  workspaceId?: string
}

export const hasResolvableAssignedAttributes = (
  attributeIds: string[] | undefined,
  attributeCatalog: Record<string, ResolvedRuleAttribute>,
): boolean => {
  if (!Array.isArray(attributeIds) || attributeIds.length === 0) {
    return false
  }

  return attributeIds.some((attributeId) => Boolean(String(attributeCatalog[attributeId]?.name || '').trim()))
}

export const statusColors: Record<RuleStatus, { bg: string; text: string }> = {
  draft: {
    bg: 'var(--dq-status-neutral-bg)',
    text: 'var(--dq-status-neutral-text)',
  },
  testing: {
    bg: 'var(--dq-status-warning-bg)',
    text: 'var(--dq-status-warning-text)',
  },
  tested: {
    bg: 'var(--dq-status-success-bg)',
    text: 'var(--dq-status-success-text)',
  },
  'pending-approval': {
    bg: 'var(--dq-status-warning-bg)',
    text: 'var(--dq-status-warning-text)',
  },
  approved: {
    bg: 'var(--dq-status-success-bg)',
    text: 'var(--dq-status-success-text)',
  },
  activated: {
    bg: 'var(--dq-status-success-bg)',
    text: 'var(--dq-status-success-text)',
  },
  deactivated: {
    bg: 'var(--dq-status-neutral-bg)',
    text: 'var(--dq-status-neutral-text)',
  },
  rejected: {
    bg: 'var(--dq-status-error-bg)',
    text: 'var(--dq-status-error-text)',
  },
}

export const statusLabels: Record<RuleStatus, string> = {
  draft: 'Draft',
  testing: 'Testing',
  tested: 'Ready',
  'pending-approval': 'Pending Review',
  approved: 'Approved',
  activated: 'Active',
  deactivated: 'Deactivated',
  rejected: 'Rejected',
}

const STATUS_BADGE_META: Record<RuleStatus, { icon: string }> = {
  draft: {
    icon: 'info-circle',
  },
  testing: {
    icon: 'clock',
  },
  tested: {
    icon: 'check-circle',
  },
  'pending-approval': {
    icon: 'clock',
  },
  approved: {
    icon: 'check-circle',
  },
  activated: {
    icon: 'check-circle',
  },
  deactivated: {
    icon: 'times-circle-fill',
  },
  rejected: {
    icon: 'exclamation-triangle',
  },
}

export const statusBadgeMeta = (status: RuleStatus) => STATUS_BADGE_META[status]

export const riskLevelLabels: Record<string, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
}

export const riskLevelBadgeStyle = (riskLevel: string) => ({
  low: {
    bg: 'var(--dq-status-success-bg)',
    color: 'var(--dq-status-success-text)',
    icon: 'check-circle',
  },
  medium: {
    bg: 'var(--dq-status-warning-bg)',
    color: 'var(--dq-status-warning-text)',
    icon: 'exclamation-circle',
  },
  high: {
    bg: 'var(--dq-status-error-bg)',
    color: 'var(--dq-status-error-text)',
    icon: 'exclamation-circle',
  },
}[riskLevel] || {
  bg: 'var(--dq-status-neutral-bg)',
  color: 'var(--dq-status-neutral-text)',
  icon: 'info-circle',
})

export const getJoinConditionCount = (rule: Rule) => {
  if (!Array.isArray(rule.joinConditions)) {
    return 0
  }

  return rule.joinConditions.reduce<number>((count: number, definition: RuleJoinDefinition) => {
    return count + (Array.isArray(definition.conditions) ? definition.conditions.length : 0)
  }, 0)
}

export const getAssignedAttributes = (rule: Rule, ruleAttributeMappings: Record<string, string[]>) => {
  const mappedAttributes = ruleAttributeMappings[rule.id]

  if (Array.isArray(mappedAttributes) && mappedAttributes.length > 0) {
    return mappedAttributes
  }

  return [] as string[]
}

export const getJoinDefinitionsWithConditions = (rule: Rule) => {
  if (!Array.isArray(rule.joinConditions)) {
    return [] as RuleJoinDefinition[]
  }

  return rule.joinConditions.filter(
    (definition: RuleJoinDefinition) => Array.isArray(definition.conditions) && definition.conditions.length > 0
  )
}

export const buildJoinExpression = (joinDefinitions: RuleJoinDefinition[]) => {
  const clauses = joinDefinitions
    .map((joinDefinition: RuleJoinDefinition) => {
      const completeConditions = joinDefinition.conditions.filter(
        (condition: RuleJoinCondition) =>
          condition.leftDataObjectId &&
          condition.leftAttributeId &&
          condition.rightDataObjectId &&
          condition.rightAttributeId &&
          condition.operator
      )

      if (completeConditions.length === 0) {
        return ''
      }

      const conditionExpression = completeConditions
        .map((condition: RuleJoinCondition) => {
          const leftOperand = `${condition.leftDataObjectId}.${condition.leftAttributeId}`
          const rightOperand = `${condition.rightDataObjectId}.${condition.rightAttributeId}`
          return `${leftOperand} ${condition.operator} ${rightOperand}`
        })
        .join(' AND ')

      return `${joinDefinition.joinType.toUpperCase()} JOIN ON ${conditionExpression}`
    })
    .filter(Boolean)

  return clauses.join('\n')
}

export const buildCompleteRuleExpression = (rule: Rule) => {
  const parts = [
    String(rule.expression || '').trim(),
    ...(Array.isArray(rule.reusableFilters)
      ? rule.reusableFilters
          .map((filter: any) => String(filter?.expression || filter?.filter_expression || '').trim())
          .filter(Boolean)
      : []),
  ].filter(Boolean)

  return parts.map(part => `(${part})`).join(' AND ')
}

export const buildExpressionWithReusableFilters = (rule: Rule, baseExpression?: string | null) => {
  const parts = [
    String(baseExpression || '').trim(),
    ...(Array.isArray(rule.reusableFilters)
      ? rule.reusableFilters
          .map((filter: any) => String(filter?.expression || filter?.filter_expression || '').trim())
          .filter(Boolean)
      : []),
  ].filter(Boolean)

  return parts.map(part => `(${part})`).join(' AND ')
}
