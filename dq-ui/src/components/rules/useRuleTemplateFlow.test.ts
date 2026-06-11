// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useRuleTemplateFlow } from './useRuleTemplateFlow'
import { Rule } from '../../types/rules'
import { RuleTemplate } from '../../types/templates'
import { classifyRuleSaveError } from './useRuleTemplateFlow'

describe('classifyRuleSaveError', () => {
  it('maps approved version conflicts to a version-locked message', () => {
    expect(classifyRuleSaveError('Failed to update rule (409): This rule version is approved and can no longer be changed.')).toEqual({
      kind: 'locked_version',
      message: 'This rule version is approved and can no longer be changed.',
    })
  })

  it('maps duplicate-name conflicts to the workspace uniqueness message', () => {
    expect(classifyRuleSaveError("Failed to create rule (409): A rule with name 'Customer Check' already exists in this workspace")).toEqual({
      kind: 'duplicate_name',
      message: 'Rule name must be unique within workspace.',
    })
  })

  it('returns null for non-conflict errors', () => {
    expect(classifyRuleSaveError('Failed to update rule (500): Internal Server Error')).toBeNull()
  })

  it('keeps edit saves inactive and preserves uniqueness attributes', async () => {
    const rule: Rule = {
      id: 'rule-1',
      workspace: 'default',
      name: 'Customer uniqueness',
      description: 'Existing description',
      status: 'deactivated',
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-02T00:00:00.000Z',
      attributes: [],
      riskLevel: 'medium',
      active: false,
      dimension: 'Uniqueness',
      checkType: 'UNIQUENESS',
      checkTypeParams: {
        checkType: 'UNIQUENESS',
        attributes: ['existing_attribute'],
      },
    }

    const template: RuleTemplate = {
      id: 'template-edit-rule',
      name: 'Edit Rule',
      description: 'Edit existing rule',
      dimension: 'uniqueness',
      category: 'Rule Edit',
      defaultRiskLevel: 'medium',
      ruleType: 'custom',
      templateRuleDefinition: {
        attributes: [],
      },
      exampleUse: 'Edit existing rule configuration',
    }

    const updateRule = vi.fn(async (_ruleId: string, updates: Partial<Rule>) => ({
      ...rule,
      ...updates,
      active: false,
    }))
    const createRule = vi.fn()
    const assignAttributesToRule = vi.fn(async () => undefined)
    const showNotice = vi.fn()
    const onRuleFocused = vi.fn()

    const { result } = renderHook(() =>
      useRuleTemplateFlow({
        authToken: null,
        apiBaseUrl: 'http://localhost:8000/api/v1',
        currentWorkspaceId: 'default',
        attributeCatalog: {
          'attr-1': { name: 'customer_id' },
        },
        ruleAttributeMappings: {
          'rule-1': ['attr-1'],
        },
        workspaceRules: [rule],
        fetchedRulesById: { 'rule-1': rule },
        createRule,
        updateRule,
        assignAttributesToRule,
        showNotice,
        onRuleFocused,
      }),
    )

    await act(async () => {
      result.current.openEditRuleWizard('rule-1')
    })

    await act(async () => {
      const outcome = await result.current.handleSelectTemplate(template, {
        name: 'Customer uniqueness',
        description: 'Updated description',
        riskLevel: 'medium',
        attributeIds: ['attr-1'],
        checkType: 'UNIQUENESS',
        checkTypeParams: {
          checkType: 'UNIQUENESS',
          attributes: ['attr-1'],
        },
      })

      expect(outcome).toEqual({ ok: true })
    })

    expect(updateRule).toHaveBeenCalledWith(
      'rule-1',
      expect.objectContaining({
        active: false,
        checkType: 'UNIQUENESS',
        checkTypeParams: expect.objectContaining({
          attributes: ['customer_id'],
        }),
      }),
    )
    expect(assignAttributesToRule).toHaveBeenCalledWith('rule-1', ['attr-1'])
    expect(onRuleFocused).toHaveBeenCalledWith('rule-1')
    expect(showNotice).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'success',
        ruleId: 'rule-1',
      }),
    )
    expect(createRule).not.toHaveBeenCalled()
  })
})
