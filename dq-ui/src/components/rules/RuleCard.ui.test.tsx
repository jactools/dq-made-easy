/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RuleCard } from './RuleCard'
import { Rule } from '../../types/rules'

vi.mock('../../hooks/useContexts', () => ({
  useSettings: () => ({
    displaySettings: {
      compactMode: false,
    },
    applicationSettings: {},
  }),
  useSettingsOptional: () => ({
    displaySettings: {
      compactMode: false,
    },
    applicationSettings: {},
  }),
}))

vi.mock('../../hooks/useCatalogDrift', () => ({
  useCatalogDrift: () => ({
    checkRuleDrift: vi.fn(() => Promise.resolve(null)),
  }),
}))

vi.mock('../../hooks/useBatchRevalidation', () => ({
  useBatchRevalidation: () => ({
    startRevalidationJob: vi.fn(),
    getJobStatus: vi.fn(),
  }),
}))

vi.mock('../RuleVersioningContainer', () => ({
  RuleVersioningContainer: () => null,
}))

vi.mock('../DriftAlert', () => ({
  DriftAlert: () => null,
}))

vi.mock('../RevalidationProgress', () => ({
  RevalidationProgress: () => null,
}))

vi.mock('../TestResultsVisualization', () => ({
  TestResultsVisualization: () => null,
}))

afterEach(() => {
  cleanup()
})

const buildRule = (overrides?: Partial<Rule>): Rule => ({
  id: 'rule-1',
  workspace: 'workspace-1',
  name: 'Reusable asset rule',
  description: 'Rule with reusable assets',
  status: 'draft',
  createdAt: '2026-04-20T09:00:00Z',
  attributes: [],
  riskLevel: 'medium',
  reusableJoinId: 'join-17',
  reusableFilterIds: ['filter-a', 'filter-b'],
  currentVersionNumber: 2,
  ...overrides,
})

describe('RuleCard reusable asset summary', () => {
  it('shows reusable join and reusable filter action icons for a locked rule', () => {
    const onOpenActionModal = vi.fn()
    render(
      <RuleCard
        rule={buildRule({ status: 'approved' })}
        currentWorkspaceId="workspace-1"
        selectedRuleId="rule-1"
        selectedBulkRuleIds={new Set()}
        expandedRuleId={null}
        testNotice={null}
        compiledExpressionByRuleId={{}}
        latestCompiledInfoByRuleId={{}}
        attributeCatalog={{}}
        ruleAttributeMappings={{}}
        ruleAttributeThresholds={{}}
        onSelectRule={vi.fn()}
        onSelectRuleId={vi.fn()}
        onToggleBulkSelect={vi.fn()}
        onToggleExpand={vi.fn()}
        getExpandedTab={() => 'details'}
        onSetExpandedTab={vi.fn()}
        getEffectiveValidationState={() => null}
        getRuleActionButtons={() => []}
        canTransitionTo={() => false}
        getActionTitle={() => ''}
        getActionIcon={() => ''}
        onValidateRule={vi.fn()}
        onEditRule={vi.fn()}
        onOpenActionModal={onOpenActionModal}
        renderNoticeContent={vi.fn(() => null)}
        onCopyJoinExpression={vi.fn()}
        onCopyCompleteExpression={vi.fn()}
        toCurrentRuleVersion={(rule) => ({ id: `${rule.id}-v2`, versionNumber: rule.currentVersionNumber ?? 1 }) as any}
        onRollbackComplete={vi.fn()}
      />,
    )

    const reusableFilterButton = screen.getByTitle('View reusable filters (2)')
    const reusableJoinButton = screen.getByTitle('View reusable join')

    expect(reusableFilterButton).toBeTruthy()
    expect(reusableJoinButton).toBeTruthy()

    fireEvent.click(reusableFilterButton)
    fireEvent.click(reusableJoinButton)

    expect(onOpenActionModal).toHaveBeenCalledWith('rule-1', 'filter', true)
    expect(onOpenActionModal).toHaveBeenCalledWith('rule-1', 'reusable-join', true)
  })

  it('shows the defining workspace on the rule and its assigned attribute', () => {
    render(
      <RuleCard
        rule={buildRule({ workspace: 'retail-banking' })}
        currentWorkspaceId="corporate-banking"
        selectedRuleId="rule-1"
        selectedBulkRuleIds={new Set()}
        expandedRuleId={null}
        testNotice={null}
        compiledExpressionByRuleId={{}}
        latestCompiledInfoByRuleId={{}}
        attributeCatalog={{
          'attr-1': {
            id: 'attr-1',
            name: 'customer_id',
            workspaceId: 'retail-banking',
            datasetName: 'Customer & Order Management',
            dataObjectName: 'Customer',
          },
        }}
        ruleAttributeMappings={{
          'rule-1': ['attr-1'],
        }}
        ruleAttributeThresholds={{}}
        onSelectRule={vi.fn()}
        onSelectRuleId={vi.fn()}
        onToggleBulkSelect={vi.fn()}
        onToggleExpand={vi.fn()}
        getExpandedTab={() => 'details'}
        onSetExpandedTab={vi.fn()}
        getEffectiveValidationState={() => null}
        getRuleActionButtons={() => []}
        canTransitionTo={() => false}
        getActionTitle={() => ''}
        getActionIcon={() => ''}
        onValidateRule={vi.fn()}
        onEditRule={vi.fn()}
        onOpenActionModal={vi.fn()}
        renderNoticeContent={vi.fn(() => null)}
        onCopyJoinExpression={vi.fn()}
        onCopyCompleteExpression={vi.fn()}
        toCurrentRuleVersion={(rule) => ({ id: `${rule.id}-v2`, versionNumber: rule.currentVersionNumber ?? 1 }) as any}
        onRollbackComplete={vi.fn()}
      />,
    )

    expect(screen.getByText(/Retail Banking/)).toBeTruthy()
  })
})