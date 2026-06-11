import { useCallback, useMemo } from 'react'
import { Rule } from '../../types/rules'
import { ResolvedRuleAttribute } from './useRuleAttributeCatalog'
import {
  computeEntityEmptyMessage,
  computeEntityScopedItems,
  EntityViewScope,
  useEntityScope,
} from '../shared/useEntityScope'

type RulesViewScope = EntityViewScope

interface UseRulesScopeParams {
  rules: Rule[]
  fetchedRulesById: Record<string, Rule>
  ruleAttributeMappings: Record<string, string[]>
  attributeCatalog: Record<string, ResolvedRuleAttribute>
  getRulesByWorkspace: (workspaceId: string) => Rule[]
  currentWorkspaceId: string | null
  user: { id?: string; email?: string; name?: string } | null
  canReadAcrossWorkspaces: () => boolean
  viewScope: RulesViewScope
}

interface UseRulesScopeResult {
  workspaceRules: Rule[]
  scopedRules: Rule[]
  emptyRulesMessage: string
  canViewAllRules: boolean
}

interface ComputeScopedRulesParams {
  viewScope: RulesViewScope
  canViewAllRules: boolean
  allFetchedRules: Rule[]
  workspaceRules: Rule[]
  isRuleOwnedByCurrentUser: (rule: Rule) => boolean
  isRuleUsingCurrentWorkspaceAttributes: (rule: Rule) => boolean
}

interface ComputeEmptyRulesMessageParams {
  viewScope: RulesViewScope
  canViewAllRules: boolean
}

const isIdentityMatch = (rawIdentity: string, normalizedCurrentUserTokens: Set<string>): boolean => {
  const identity = rawIdentity.trim().toLowerCase()
  if (!identity) return false
  return normalizedCurrentUserTokens.has(identity)
}

export const computeScopedRules = ({
  viewScope,
  canViewAllRules,
  allFetchedRules,
  workspaceRules,
  isRuleOwnedByCurrentUser,
  isRuleUsingCurrentWorkspaceAttributes,
}: ComputeScopedRulesParams): Rule[] => {
  return computeEntityScopedItems({
    viewScope,
    canViewAllItems: canViewAllRules,
    allItems: allFetchedRules,
    workspaceItems: workspaceRules,
    isItemOwnedByCurrentUser: isRuleOwnedByCurrentUser,
    matchesAllScope: isRuleUsingCurrentWorkspaceAttributes,
  })
}

export const computeEmptyRulesMessage = ({
  viewScope,
  canViewAllRules,
}: ComputeEmptyRulesMessageParams): string => {
  return computeEntityEmptyMessage({
    viewScope,
    canViewAllItems: canViewAllRules,
    messages: {
      my: 'No rules found for you in this workspace.',
      team: "No team rules found in this workspace.",
      all: 'No rules found that use data object versions in this workspace.',
      global: 'No rules found across workspaces.',
    },
  })
}

export const useRulesScope = ({
  rules,
  fetchedRulesById,
  ruleAttributeMappings,
  attributeCatalog,
  getRulesByWorkspace,
  currentWorkspaceId,
  user,
  canReadAcrossWorkspaces,
  viewScope,
}: UseRulesScopeParams): UseRulesScopeResult => {
  const workspaceRules = useMemo(() => {
    if (!currentWorkspaceId) return []
    const listedRules = getRulesByWorkspace(currentWorkspaceId)
    const fetchedRules = Object.values(fetchedRulesById).filter((rule) => rule.workspace === currentWorkspaceId)
    const existingIds = new Set(listedRules.map((rule) => rule.id))
    const merged = [...listedRules]
    for (const fetchedRule of fetchedRules) {
      if (!existingIds.has(fetchedRule.id)) {
        merged.push(fetchedRule)
      }
    }
    return merged
  }, [getRulesByWorkspace, currentWorkspaceId, fetchedRulesById])

  const normalizedCurrentUserTokens = useMemo(() => {
    return new Set(
      [user?.id, user?.email, user?.name]
        .map((value) => String(value || '').trim().toLowerCase())
        .filter(Boolean)
    )
  }, [user?.id, user?.email, user?.name])

  const isRuleOwnedByCurrentUser = useCallback((rule: Rule): boolean => {
    return isIdentityMatch(rule.createdBy ?? '', normalizedCurrentUserTokens)
  }, [normalizedCurrentUserTokens])

  const canViewAllRules = canReadAcrossWorkspaces()

  const allFetchedRules = useMemo(() => {
    const listedRules = Array.isArray(rules) ? rules : []
    const fetchedRules = Object.values(fetchedRulesById)
    const existingIds = new Set(listedRules.map((rule) => rule.id))
    const merged = [...listedRules]
    for (const fetchedRule of fetchedRules) {
      if (!existingIds.has(fetchedRule.id)) {
        merged.push(fetchedRule)
      }
    }
    return merged
  }, [rules, fetchedRulesById])

  const isRuleUsingCurrentWorkspaceAttributes = useCallback((rule: Rule): boolean => {
    if (!currentWorkspaceId) {
      return false
    }

    if (rule.workspace === currentWorkspaceId) {
      return true
    }

    const attributeIds = ruleAttributeMappings[String(rule.id)] || []
    if (!Array.isArray(attributeIds) || attributeIds.length === 0) {
      return false
    }

    return attributeIds.some((attributeId) => {
      const workspaceId = String(attributeCatalog[String(attributeId)]?.workspaceId || '').trim()
      return workspaceId === currentWorkspaceId
    })
  }, [currentWorkspaceId, ruleAttributeMappings, attributeCatalog])

  const { scopedItems: scopedRules, emptyMessage: emptyRulesMessage } = useEntityScope({
    viewScope,
    canViewAllItems: canViewAllRules,
    allItems: allFetchedRules,
    workspaceItems: workspaceRules,
    isItemOwnedByCurrentUser: isRuleOwnedByCurrentUser,
    matchesAllScope: isRuleUsingCurrentWorkspaceAttributes,
    messages: {
      my: 'No rules found for you in this workspace.',
      team: "No team rules found in this workspace.",
      all: 'No rules found that use data object versions in this workspace.',
      global: 'No rules found across workspaces.',
    },
  })

  return {
    workspaceRules,
    scopedRules,
    emptyRulesMessage,
    canViewAllRules,
  }
}
