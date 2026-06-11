/** @vitest-environment jsdom */

import React from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PolicyDocumentsPage } from './PolicyDocumentsPage'

const createDefaultAuth = () => ({
  user: {
    name: 'Governance Steward',
    workspaceRoles: [
      { workspaceId: 'retail-banking', role: 'governance-admin', joinedAt: new Date('2026-01-01') },
      { workspaceId: 'corporate-banking', role: 'governance-editor', joinedAt: new Date('2026-01-15') },
    ],
  },
  currentWorkspaceId: 'retail-banking',
  canEditGovernance: () => true,
  canApproveGovernance: () => true,
})

let mockAuth: any = createDefaultAuth()

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => mockAuth,
}))

vi.mock('./Button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>
      {children}
    </button>
  ),
  PrimaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>
      {children}
    </button>
  ),
  SecondaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>
      {children}
    </button>
  ),
  TertiaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>
      {children}
    </button>
  ),
}))

describe('PolicyDocumentsPage', () => {
  beforeEach(() => {
    mockAuth = createDefaultAuth()
  })

  const clickEnabledButton = (name: string) => {
    const button = screen
      .getAllByRole('button', { name })
      .find((candidate) => !(candidate as HTMLButtonElement).disabled) as HTMLButtonElement | undefined

    expect(button).toBeTruthy()
    fireEvent.click(button!)
  }

  it('renders a policy document preview and supports review acknowledgement', () => {
    render(<PolicyDocumentsPage />)

    expect(screen.getByText('Policy Documents')).toBeTruthy()
    expect(screen.getByText('Freshness Check')).toBeTruthy()
    expect(screen.getByText('Draft', { selector: '.policy-status-banner' })).toBeTruthy()
    expect(screen.getByRole('region', { name: /Policy library sharing/i })).toBeTruthy()
    expect(screen.getByRole('region', { name: /Policy reuse controls/i })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Freshness Check/i }))
    expect(screen.getByText(/Workspace scope: Current workspace only/i)).toBeTruthy()
    expect(screen.getByText(/# Quality standard: Freshness Check/i)).toBeTruthy()

    const librarySharing = screen.getByRole('region', { name: /Policy library sharing/i })
    fireEvent.click(within(librarySharing).getByRole('button', { name: /Selected workspaces/i }))
    const corporateWorkspaceCheckbox = within(librarySharing).getByRole('checkbox', { name: /Workspace CORPORATE-BANKING/i }) as HTMLInputElement
    fireEvent.click(corporateWorkspaceCheckbox)
    expect(corporateWorkspaceCheckbox.checked).toBe(true)
    expect(
      within(librarySharing).getByText((_, element) => element?.textContent === 'Sharing scope: Selected workspaces'),
    ).toBeTruthy()
    expect(
      within(librarySharing).getByText((_, element) =>
        element?.textContent === 'Shared workspaces: Workspace RETAIL-BANKING, Workspace CORPORATE-BANKING',
      ),
    ).toBeTruthy()
    expect(screen.getByText(/Workspace scope: Current workspace only/i)).toBeTruthy()
    expect(screen.getByText(/Asset targets: Rules/i)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Mark Reviewed' }))
    expect(screen.getByText('Reviewed', { selector: '.policy-status-banner' })).toBeTruthy()
    expect(screen.getByText('Governance Steward')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))
    expect(screen.getByText('Acknowledged', { selector: '.policy-status-banner' })).toBeTruthy()
    expect(
      within(librarySharing).getByText((_, element) =>
        element?.textContent === 'Shared workspaces: Workspace RETAIL-BANKING, Workspace CORPORATE-BANKING',
      ),
    ).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /^Monitor definition$/i }))
    expect(screen.getByText(/# Monitor definition: Freshness Check/i)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /^Reconciliation definition$/i }))
    expect(screen.getByText(/# Reconciliation definition: Freshness Check/i)).toBeTruthy()
    expect(screen.getByText(/Reuse this reconciliation definition wherever the same pairwise comparison contract must stay aligned across rules and Data Assets\./i)).toBeTruthy()
  })

  it('supports submitting policy changes for approval and reviewer decisions', () => {
    render(<PolicyDocumentsPage />)

    const proposedChangeInput = screen.getAllByPlaceholderText('Describe what is changing and why it should be approved.')[0] as HTMLTextAreaElement
    const reviewNoteInput = screen.getAllByPlaceholderText('Add approval comments or a rejection reason.')[0] as HTMLTextAreaElement

    fireEvent.change(proposedChangeInput, {
      target: { value: 'Tighten freshness checks from 7 days to 3 days.' },
    })
    clickEnabledButton('Submit for Approval')

    expect(screen.getByText(/Approval: Pending review/i)).toBeTruthy()
    expect(screen.getByText(/Current approval status: Pending review/i)).toBeTruthy()

    fireEvent.change(reviewNoteInput, {
      target: { value: 'Approved for the retail-banking rollout.' },
    })
    clickEnabledButton('Approve Change')

    expect(screen.getByText(/Approval: Approved/i)).toBeTruthy()
    expect(screen.getByText(/Approved for the retail-banking rollout\./i, { selector: '.policy-review-summary span' })).toBeTruthy()

    clickEnabledButton('Clear Review Draft')
    fireEvent.change(proposedChangeInput, {
      target: { value: 'Reject the broad workspace expansion until controls are updated.' },
    })
    clickEnabledButton('Submit for Approval')
    fireEvent.change(reviewNoteInput, {
      target: { value: 'Rejected until workspace-scoped controls are confirmed.' },
    })
    clickEnabledButton('Reject Change')

    expect(screen.getByText(/Approval: Rejected/i)).toBeTruthy()
    expect(screen.getByText(/Rejected until workspace-scoped controls are confirmed\./i, { selector: '.policy-review-summary span' })).toBeTruthy()
  })

  it('lets governance editors draft changes but not approve them', () => {
    mockAuth = {
      user: {
        name: 'Governance Editor',
        workspaceRoles: [
          { workspaceId: 'retail-banking', role: 'governance-editor', joinedAt: new Date('2026-01-01') },
        ],
      },
      currentWorkspaceId: 'retail-banking',
      canEditGovernance: () => true,
      canApproveGovernance: () => false,
    }

    render(<PolicyDocumentsPage />)

    const submitButton = screen
      .getAllByRole('button', { name: 'Submit for Approval' })
      .find((candidate) => !(candidate as HTMLButtonElement).disabled)

    const clearDraftButton = screen
      .getAllByRole('button', { name: 'Clear Review Draft' })
      .find((candidate) => !(candidate as HTMLButtonElement).disabled)

    expect(submitButton).toBeTruthy()
    expect(clearDraftButton).toBeTruthy()

    const approveButtons = screen.getAllByRole('button', { name: 'Approve Change' }) as HTMLButtonElement[]
    const rejectButtons = screen.getAllByRole('button', { name: 'Reject Change' }) as HTMLButtonElement[]

    expect(approveButtons.every((button) => button.disabled)).toBe(true)
    expect(rejectButtons.every((button) => button.disabled)).toBe(true)
  })
})