// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import { Rule } from '../../types/rules'
import { computeScopedRules } from './useRulesScope'
import { renderHook } from '@testing-library/react'
import { useRulesScope } from './useRulesScope'

const makeRule = (id: string, workspace: string, createdBy: string): Rule => ({
  id,
  workspace,
  name: id,
  description: `${id} description`,
  createdBy,
  status: 'draft',
  createdAt: '2026-01-01T00:00:00.000Z',
  attributes: [],
  riskLevel: 'medium',
})

describe('computeScopedRules', () => {
  const myRule = makeRule('rule-my-ws', 'ws-a', 'alice')
  const teamRule = makeRule('rule-team-ws', 'ws-a', 'bob')
  const externalUsingCurrentWorkspaceObjects = makeRule('rule-external-mapped', 'ws-b', 'carol')
  const externalUnrelated = makeRule('rule-external-unrelated', 'ws-c', 'dave')

  const workspaceRules = [myRule, teamRule]
  const allFetchedRules = [myRule, teamRule, externalUsingCurrentWorkspaceObjects, externalUnrelated]

  const isOwnedByCurrentUser = (rule: Rule): boolean => rule.createdBy === 'alice'

  const usesCurrentWorkspaceObjects = (rule: Rule): boolean =>
    rule.id === 'rule-my-ws' ||
    rule.id === 'rule-team-ws' ||
    rule.id === 'rule-external-mapped'

  it('shows only owned workspace rules for my scope', () => {
    const scoped = computeScopedRules({
      viewScope: 'my',
      canViewAllRules: true,
      allFetchedRules,
      workspaceRules,
      isRuleOwnedByCurrentUser: isOwnedByCurrentUser,
      isRuleUsingCurrentWorkspaceAttributes: usesCurrentWorkspaceObjects,
    })

    expect(scoped.map((rule) => rule.id)).toEqual(['rule-my-ws'])
  })

  it('shows only non-owned workspace rules for team scope', () => {
    const scoped = computeScopedRules({
      viewScope: 'team',
      canViewAllRules: true,
      allFetchedRules,
      workspaceRules,
      isRuleOwnedByCurrentUser: isOwnedByCurrentUser,
      isRuleUsingCurrentWorkspaceAttributes: usesCurrentWorkspaceObjects,
    })

    expect(scoped.map((rule) => rule.id)).toEqual(['rule-team-ws'])
  })

  it('shows rules from any workspace that use current workspace data objects for all scope', () => {
    const scoped = computeScopedRules({
      viewScope: 'all',
      canViewAllRules: true,
      allFetchedRules,
      workspaceRules,
      isRuleOwnedByCurrentUser: isOwnedByCurrentUser,
      isRuleUsingCurrentWorkspaceAttributes: usesCurrentWorkspaceObjects,
    })

    expect(scoped.map((rule) => rule.id)).toEqual([
      'rule-my-ws',
      'rule-team-ws',
      'rule-external-mapped',
    ])
  })

  it('shows every rule for global scope', () => {
    const scoped = computeScopedRules({
      viewScope: 'global',
      canViewAllRules: true,
      allFetchedRules,
      workspaceRules,
      isRuleOwnedByCurrentUser: isOwnedByCurrentUser,
      isRuleUsingCurrentWorkspaceAttributes: usesCurrentWorkspaceObjects,
    })

    expect(scoped.map((rule) => rule.id)).toEqual([
      'rule-my-ws',
      'rule-team-ws',
      'rule-external-mapped',
      'rule-external-unrelated',
    ])
  })

  it('treats createdBy string values as my rules', () => {
    const rawRule = makeRule('rule-snake-owner', 'ws-a', 'alice@example.com')

    const { result } = renderHook(() =>
      useRulesScope({
        rules: [rawRule],
        fetchedRulesById: {},
        ruleAttributeMappings: {},
        attributeCatalog: {},
        getRulesByWorkspace: () => [rawRule],
        currentWorkspaceId: 'ws-a',
        user: { id: 'u-1', email: 'alice@example.com', name: 'Alice' },
        canReadAcrossWorkspaces: () => true,
        viewScope: 'my',
      })
    )

    expect(result.current.scopedRules.map((rule) => rule.id)).toEqual(['rule-snake-owner'])
  })

  it('treats createdBy UUID values as my rules', () => {
    const objectOwnerRule = makeRule('rule-object-owner', 'ws-a', '8ad833f8-c989-407d-afd7-05d28733dc7d')

    const { result } = renderHook(() =>
      useRulesScope({
        rules: [objectOwnerRule],
        fetchedRulesById: {},
        ruleAttributeMappings: {},
        attributeCatalog: {},
        getRulesByWorkspace: () => [objectOwnerRule],
        currentWorkspaceId: 'ws-a',
        user: {
          id: '8ad833f8-c989-407d-afd7-05d28733dc7d',
          email: 'corp.admin@example.com',
          name: 'Corporate Admin',
        },
        canReadAcrossWorkspaces: () => true,
        viewScope: 'my',
      })
    )

    expect(result.current.scopedRules.map((rule) => rule.id)).toEqual(['rule-object-owner'])
  })

  it('treats createdBy field as canonical owner token', () => {
    const idOwnerRule = makeRule('rule-user-id-owner', 'ws-a', '8ad833f8-c989-407d-afd7-05d28733dc7d')

    const { result } = renderHook(() =>
      useRulesScope({
        rules: [idOwnerRule],
        fetchedRulesById: {},
        ruleAttributeMappings: {},
        attributeCatalog: {},
        getRulesByWorkspace: () => [idOwnerRule],
        currentWorkspaceId: 'ws-a',
        user: {
          id: '8ad833f8-c989-407d-afd7-05d28733dc7d',
          email: 'corp.admin@example.com',
          name: 'Corporate Admin',
        },
        canReadAcrossWorkspaces: () => true,
        viewScope: 'my',
      })
    )

    expect(result.current.scopedRules.map((rule) => rule.id)).toEqual(['rule-user-id-owner'])
  })
})
