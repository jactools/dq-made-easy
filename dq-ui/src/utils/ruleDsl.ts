import type { Rule, RuleDslContract, RuleDslSource } from '../types/rules'

type RuleDslInput = Pick<
  Rule,
  'expression' | 'generated' | 'manualOverrideConfirmed' | 'joinConditions' | 'reusableFilterIds' | 'reusableJoinId' | 'aliasMappings' | 'checkType' | 'checkTypeParams'
>

export const buildRuleDslPayload = (rule: RuleDslInput): RuleDslContract => {
  const expression = String(rule.expression || '').trim()
  const joinConditions = Array.isArray(rule.joinConditions) ? rule.joinConditions : []
  const aliasMappings = rule.aliasMappings && typeof rule.aliasMappings === 'object' ? rule.aliasMappings : {}
  const reusableFilterIds = Array.isArray(rule.reusableFilterIds) ? rule.reusableFilterIds.filter(Boolean) : []
  const reusableJoinId = typeof rule.reusableJoinId === 'string' && rule.reusableJoinId.trim()
    ? rule.reusableJoinId.trim()
    : undefined

  const baseSource = {
    joinConditions,
    aliasMappings,
    reusableFilterIds,
    ...(reusableJoinId ? { reusableJoinId } : {}),
  }

  let source: RuleDslSource
  if (rule.checkType && rule.checkTypeParams) {
    source = {
      kind: 'check_type',
      checkType: rule.checkType,
      checkTypeParams: rule.checkTypeParams,
      ...baseSource,
    }
    if (rule.generated === false && expression) {
      source.manualExpressionOverride = {
        expression,
        confirmed: Boolean(rule.manualOverrideConfirmed),
      }
    }
  } else {
    source = {
      kind: 'filter_expression',
      expression,
      ...baseSource,
    }
  }

  return {
    schemaVersion: '1.0.0',
    source,
  }
}