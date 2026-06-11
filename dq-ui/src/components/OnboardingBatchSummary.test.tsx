/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OnboardingBatchSummary, type OnboardingBatchResponse } from './OnboardingBatchSummary'

// ---- mock app-primitives ----
vi.mock('./app-primitives', () => ({
  AppModal: ({ isOpen, title, children, footer }: any) =>
    isOpen ? (
      <div role="dialog" aria-label={title}>
        <h2>{title}</h2>
        {children}
        {footer}
      </div>
    ) : null,
  AppButton: ({ children, onClick, disabled }: any) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  AppBanner: ({ children, variant }: any) => <div data-variant={variant}>{children}</div>,
  AppStack: ({ children }: any) => <div>{children}</div>,
}))

// ---- mock hooks/useContexts ----
const mockSubmitForApproval = vi.fn()
vi.mock('../hooks/useContexts', () => ({
  useRules: () => ({
    submitForApproval: mockSubmitForApproval,
  }),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const baseResponse: OnboardingBatchResponse = {
  batchId: 'batch-001',
  workspaceId: 'ws-1',
  totalAccepted: 5,
  created: 3,
  skipped: 1,
  failed: 1,
  outcomes: [
    { proposalId: 'template-1::obj-1::attr-1', status: 'created', ruleId: 'rule-1', reason: null },
    { proposalId: 'template-1::obj-1::attr-2', status: 'created', ruleId: 'rule-2', reason: null },
    { proposalId: 'template-1::obj-1::attr-3', status: 'created', ruleId: 'rule-3', reason: null },
    { proposalId: 'template-1::obj-1::attr-4', status: 'skipped', ruleId: null, reason: 'attribute already has equivalent rule' },
    { proposalId: 'template-1::obj-1::attr-5', status: 'failed', ruleId: null, reason: 'rule name conflict' },
  ],
  createdAt: '2026-06-01T10:00:00Z',
}

describe('OnboardingBatchSummary', () => {
  it('does not render when isOpen is false', () => {
    render(
      <OnboardingBatchSummary
        isOpen={false}
        response={baseResponse}
        onClose={vi.fn()}
        onGoToRules={vi.fn()}
      />,
    )
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('renders the modal when isOpen is true', () => {
    render(
      <OnboardingBatchSummary
        isOpen={true}
        response={baseResponse}
        onClose={vi.fn()}
        onGoToRules={vi.fn()}
      />,
    )
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByText('Batch Rule Creation Summary')).toBeTruthy()
  })

  it('displays the batch id', () => {
    render(
      <OnboardingBatchSummary
        isOpen={true}
        response={baseResponse}
        onClose={vi.fn()}
        onGoToRules={vi.fn()}
      />,
    )
    expect(screen.getByText('batch-001')).toBeTruthy()
  })

  it('displays correct created, skipped, and failed counts', () => {
    render(
      <OnboardingBatchSummary
        isOpen={true}
        response={baseResponse}
        onClose={vi.fn()}
        onGoToRules={vi.fn()}
      />,
    )
    // All three numeric values should be visible
    const countValues = screen.getAllByText(/^\d+$/)
    const numbers = countValues.map((el) => el.textContent)
    expect(numbers).toContain('3')
    expect(numbers).toContain('1')
  })

  it('shows progress indicator when isCreatingBatch is true', () => {
    render(
      <OnboardingBatchSummary
        isOpen={true}
        response={null}
        isCreatingBatch={true}
        onClose={vi.fn()}
        onGoToRules={vi.fn()}
      />,
    )
    expect(screen.getByRole('status')).toBeTruthy()
    expect(screen.getByText('Creating rules, please wait…')).toBeTruthy()
  })

  it('shows fallback banner when not loading and no response', () => {
    render(
      <OnboardingBatchSummary
        isOpen={true}
        response={null}
        isCreatingBatch={false}
        onClose={vi.fn()}
        onGoToRules={vi.fn()}
      />,
    )
    expect(screen.getByText('No batch result available.')).toBeTruthy()
  })

  it('calls onGoToRules with batchId when "Go to Rules" is clicked', () => {
    const mockGoToRules = vi.fn()
    render(
      <OnboardingBatchSummary
        isOpen={true}
        response={baseResponse}
        onClose={vi.fn()}
        onGoToRules={mockGoToRules}
      />,
    )
    fireEvent.click(screen.getByText('Go to Rules'))
    expect(mockGoToRules).toHaveBeenCalledWith('batch-001')
  })

  it('calls submitForApproval for each created rule when "Submit for Approval" is clicked', async () => {
    mockSubmitForApproval.mockResolvedValue(undefined)
    render(
      <OnboardingBatchSummary
        isOpen={true}
        response={baseResponse}
        onClose={vi.fn()}
        onGoToRules={vi.fn()}
      />,
    )
    const submitButton = screen.getByText('Submit 3 Drafts for Approval')
    fireEvent.click(submitButton)
    await waitFor(() => {
      expect(mockSubmitForApproval).toHaveBeenCalledTimes(3)
    })
    expect(mockSubmitForApproval).toHaveBeenCalledWith('rule-1')
    expect(mockSubmitForApproval).toHaveBeenCalledWith('rule-2')
    expect(mockSubmitForApproval).toHaveBeenCalledWith('rule-3')
  })

  it('shows success banner after all approvals submitted', async () => {
    mockSubmitForApproval.mockResolvedValue(undefined)
    render(
      <OnboardingBatchSummary
        isOpen={true}
        response={baseResponse}
        onClose={vi.fn()}
        onGoToRules={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByText('Submit 3 Drafts for Approval'))
    await waitFor(() => {
      expect(screen.getByText('3 rules submitted for approval.')).toBeTruthy()
    })
  })

  it('shows error banner when some approvals fail', async () => {
    mockSubmitForApproval
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce(undefined)
    render(
      <OnboardingBatchSummary
        isOpen={true}
        response={baseResponse}
        onClose={vi.fn()}
        onGoToRules={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByText('Submit 3 Drafts for Approval'))
    await waitFor(() => {
      expect(screen.getByText('1 rule could not be submitted for approval.')).toBeTruthy()
    })
  })

  it('expands failed reasons list when toggle is clicked', () => {
    render(
      <OnboardingBatchSummary
        isOpen={true}
        response={baseResponse}
        onClose={vi.fn()}
        onGoToRules={vi.fn()}
      />,
    )
    const toggle = screen.getByText(/1 failure reason/)
    fireEvent.click(toggle)
    expect(screen.getByText(/rule name conflict/)).toBeTruthy()
  })

  it('normalizes snake_case response at the UI boundary', () => {
    const snakeCaseResponse = {
      batch_id: 'batch-snake',
      workspace_id: 'ws-2',
      total_accepted: 2,
      created: 2,
      skipped: 0,
      failed: 0,
      outcomes: [
        { proposal_id: 'tpl::obj::a1', status: 'created', rule_id: 'r-1', reason: null },
        { proposal_id: 'tpl::obj::a2', status: 'created', rule_id: 'r-2', reason: null },
      ],
      created_at: '2026-06-01T11:00:00Z',
    }
    render(
      <OnboardingBatchSummary
        isOpen={true}
        response={snakeCaseResponse as any}
        onClose={vi.fn()}
        onGoToRules={vi.fn()}
      />,
    )
    expect(screen.getByText('batch-snake')).toBeTruthy()
    expect(screen.getByText('Submit 2 Drafts for Approval')).toBeTruthy()
  })
})
