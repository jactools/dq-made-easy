// @vitest-environment jsdom

import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useRuleActions } from './useRuleActions'
import { useAsyncRequests } from '../../hooks/useAsyncRequests'
import type { Rule, RuleApproval } from '../../types/rules'

vi.mock('../../hooks/useAsyncRequests', () => ({
  useAsyncRequests: vi.fn(),
}))

describe('useRuleActions', () => {
  it('requests deactivation through the API-backed flow', async () => {
    const requestRuleDeactivation = vi.fn(async () => undefined)
    const onModalClose = vi.fn()
    const showNotice = vi.fn()

    vi.mocked(useAsyncRequests).mockReturnValue({
      startRuleTest: vi.fn(),
    } as any)

    const rule: Rule = {
      id: 'rule-1',
      workspace: 'default',
      name: 'Customer uniqueness',
      description: 'Rule description',
      status: 'activated',
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-02T00:00:00.000Z',
      attributes: [],
      riskLevel: 'medium',
      active: true,
    }

    const { result } = renderHook(() =>
      useRuleActions({
        rules: [rule],
        approvals: [] as RuleApproval[],
        activeModalRule: 'rule-1',
        activeRule: rule,
        selectedBulkRuleIds: new Set<string>(),
        submitForApproval: vi.fn(),
        requestRuleDeactivation,
        approveRule: vi.fn(),
        rejectRule: vi.fn(),
        activateRule: vi.fn(),
        updateRule: vi.fn(),
        logTestAction: vi.fn(),
        saveRuleAsTemplate: vi.fn(),
        assignAttributesToRule: vi.fn(),
        validateRuleComposition: vi.fn(),
        onModalClose,
        setSelectedBulkRuleIds: vi.fn(),
        showNotice,
        setValidationStateByRuleId: vi.fn(),
        setCompiledExpressionByRuleId: vi.fn(),
        setValidationDiagnosticsModal: vi.fn(),
        settings: {},
      }),
    )

    await act(async () => {
      await result.current.handleDeactivateRule()
    })

    expect(requestRuleDeactivation).toHaveBeenCalledWith('rule-1')
    expect(onModalClose).toHaveBeenCalled()
    expect(showNotice).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'success',
        message: 'Deactivation request submitted. Awaiting approval.',
        ruleId: 'rule-1',
      }),
    )
  })

  it('forwards Validate Rule to the backend and reflects invalid results', async () => {
    const validateRuleComposition = vi.fn(async () => ({
      compiledExpression: '',
      summary: { errors: 1, warnings: 0 },
      diagnostics: [{ scope: 'rule', severity: 'error', message: 'Rule has no resolvable assigned attributes.' }],
    }))
    const onModalClose = vi.fn()
    const showNotice = vi.fn()
    const setValidationStateByRuleId = vi.fn()
    const setValidationDiagnosticsModal = vi.fn()

    vi.mocked(useAsyncRequests).mockReturnValue({
      startRuleTest: vi.fn(),
    } as any)

    const rule: Rule = {
      id: 'rule-1',
      workspace: 'default',
      name: 'Customer uniqueness',
      description: 'Rule description',
      status: 'activated',
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-02T00:00:00.000Z',
      attributes: [],
      riskLevel: 'medium',
      active: true,
    }

    const { result } = renderHook(() =>
      useRuleActions({
        rules: [rule],
        approvals: [] as RuleApproval[],
        activeModalRule: 'rule-1',
        activeRule: rule,
        selectedBulkRuleIds: new Set<string>(),
        submitForApproval: vi.fn(),
        requestRuleDeactivation: vi.fn(),
        approveRule: vi.fn(),
        rejectRule: vi.fn(),
        activateRule: vi.fn(),
        updateRule: vi.fn(),
        logTestAction: vi.fn(),
        saveRuleAsTemplate: vi.fn(),
        assignAttributesToRule: vi.fn(),
        validateRuleComposition,
        onModalClose,
        setSelectedBulkRuleIds: vi.fn(),
        showNotice,
        setValidationStateByRuleId,
        setCompiledExpressionByRuleId: vi.fn(),
        setValidationDiagnosticsModal,
        settings: {},
      }),
    )

    await act(async () => {
      await result.current.handleValidateRule('rule-1')
    })

    expect(validateRuleComposition).toHaveBeenCalledWith('rule-1')
    expect(setValidationStateByRuleId).toHaveBeenCalled()
    expect(setValidationDiagnosticsModal).toHaveBeenCalledWith(
      expect.objectContaining({
        ruleName: 'Customer uniqueness',
      }),
    )
    expect(onModalClose).not.toHaveBeenCalled()
  })

  it('bulk approval reports processed skipped and failed rules explicitly', async () => {
    const approveRule = vi.fn(async (ruleId: string) => {
      if (ruleId === 'rule-2') {
        throw new Error('approval failed')
      }
    })
    const setSelectedBulkRuleIds = vi.fn()
    const showNotice = vi.fn()

    vi.mocked(useAsyncRequests).mockReturnValue({
      startRuleTest: vi.fn(),
    } as any)

    const { result } = renderHook(() =>
      useRuleActions({
        rules: [] as Rule[],
        approvals: [] as RuleApproval[],
        activeModalRule: null,
        activeRule: undefined,
        selectedBulkRuleIds: new Set(['rule-1', 'rule-2', 'rule-3']),
        bulkApproveRuleIds: ['rule-1', 'rule-2'],
        submitForApproval: vi.fn(),
        requestRuleDeactivation: vi.fn(),
        approveRule,
        rejectRule: vi.fn(),
        activateRule: vi.fn(),
        updateRule: vi.fn(),
        logTestAction: vi.fn(),
        saveRuleAsTemplate: vi.fn(),
        assignAttributesToRule: vi.fn(),
        validateRuleComposition: vi.fn(),
        onModalClose: vi.fn(),
        setSelectedBulkRuleIds,
        showNotice,
        setValidationStateByRuleId: vi.fn(),
        setCompiledExpressionByRuleId: vi.fn(),
        setValidationDiagnosticsModal: vi.fn(),
        settings: {},
      }),
    )

    await act(async () => {
      await result.current.handleBulkApprove()
    })

    expect(approveRule).toHaveBeenCalledTimes(2)
    expect(approveRule).toHaveBeenCalledWith('rule-1')
    expect(approveRule).toHaveBeenCalledWith('rule-2')
    expect(Array.from(setSelectedBulkRuleIds.mock.calls[0][0] as Set<string>).sort()).toEqual(['rule-2', 'rule-3'])
    expect(showNotice).toHaveBeenCalledWith(expect.objectContaining({
      type: 'error',
      message: 'Bulk approval completed: 1 processed, 1 skipped, 1 failed.',
      details: expect.arrayContaining([
        'rule-3: skipped because approval is not available for the current status or role.',
        'rule-2: approval failed',
      ]),
    }))
  })

  it('bulk activation fails closed when no selected rules are eligible', async () => {
    const activateRule = vi.fn()
    const showNotice = vi.fn()

    vi.mocked(useAsyncRequests).mockReturnValue({
      startRuleTest: vi.fn(),
    } as any)

    const { result } = renderHook(() =>
      useRuleActions({
        rules: [] as Rule[],
        approvals: [] as RuleApproval[],
        activeModalRule: null,
        activeRule: undefined,
        selectedBulkRuleIds: new Set(['rule-1']),
        bulkActivateRuleIds: [],
        submitForApproval: vi.fn(),
        requestRuleDeactivation: vi.fn(),
        approveRule: vi.fn(),
        rejectRule: vi.fn(),
        activateRule,
        updateRule: vi.fn(),
        logTestAction: vi.fn(),
        saveRuleAsTemplate: vi.fn(),
        assignAttributesToRule: vi.fn(),
        validateRuleComposition: vi.fn(),
        onModalClose: vi.fn(),
        setSelectedBulkRuleIds: vi.fn(),
        showNotice,
        setValidationStateByRuleId: vi.fn(),
        setCompiledExpressionByRuleId: vi.fn(),
        setValidationDiagnosticsModal: vi.fn(),
        settings: {},
      }),
    )

    await act(async () => {
      await result.current.handleBulkActivate()
    })

    expect(activateRule).not.toHaveBeenCalled()
    expect(showNotice).toHaveBeenCalledWith(expect.objectContaining({
      type: 'error',
      message: 'Bulk activation blocked: no selected rules are eligible for activation.',
    }))
  })
})