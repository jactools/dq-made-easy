/** @vitest-environment jsdom */

import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { BulkActionsToolbar } from './BulkActionsToolbar'
import { mockButtonModule } from './test-support/appOwnedUiTestMocks'

vi.mock('./Button', () => mockButtonModule())

describe('BulkActionsToolbar', () => {
  it('shows eligibility counts and disables unavailable actions', () => {
    const approve = vi.fn()
    const activate = vi.fn()

    render(
      <BulkActionsToolbar
        selectedRuleIds={['rule-1', 'rule-2']}
        canApprove={true}
        canActivate={false}
        approveEligibleCount={1}
        activateEligibleCount={0}
        ruleValidationEligibleCount={2}
        blockedRules={[{ ruleId: 'rule-2', ruleName: 'Rule Two', reason: 'No approve or activate action is available for status activated.' }]}
        onApproveSelected={approve}
        onActivateSelected={activate}
        onClearSelection={vi.fn()}
      />,
    )

    expect(screen.getByText('1 approval-ready')).toBeTruthy()
    expect(screen.getByText('1 skipped for approval')).toBeTruthy()
    expect(screen.getByText('0 activation-ready')).toBeTruthy()
    expect(screen.getByText('2 skipped for activation')).toBeTruthy()
    expect(screen.getByText('2 validation-ready')).toBeTruthy()
    expect(screen.getByText('Rule Two: No approve or activate action is available for status activated.')).toBeTruthy()

    fireEvent.click(screen.getByText(/Approve/))
    fireEvent.click(screen.getByText(/Activate/))

    expect(approve).toHaveBeenCalledTimes(1)
    expect(activate).not.toHaveBeenCalled()
  })
})
