/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SupportRequestFooter } from './SupportRequestFooter'

const recordedBodies: Array<Record<string, unknown>> = []

vi.mock('./SupportRequestFlow', () => ({
  SupportRequestFlow: ({ buttonLabel, createRequestBody }: any) => (
    <button
      type="button"
      onClick={() => {
        recordedBodies.push(createRequestBody())
      }}
    >
      {buttonLabel}
    </button>
  ),
}))

vi.mock('./StatusBanner', () => ({
  StatusBanner: ({ message, onDismiss }: any) => (
    <div>
      <div>{message}</div>
      <button type="button" onClick={onDismiss}>Dismiss</button>
    </div>
  ),
}))

describe('SupportRequestFooter', () => {
  beforeEach(() => {
    cleanup()
    window.localStorage.clear()
    recordedBodies.splice(0, recordedBodies.length)
    vi.restoreAllMocks()
  })

  it('builds a support request with the current page context', async () => {
    const user = userEvent.setup()

    render(
      <SupportRequestFooter
        apiBaseUrl="http://api.local/api"
        pageId="approvals-my"
        workspaceId="retail-banking"
      />
    )

    expect(screen.getByRole('heading', { name: 'Request assistance' })).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Request assistance' }))

    expect(recordedBodies).toHaveLength(1)
    expect(recordedBodies[0]).toMatchObject({
      title: 'Application assistance: My Approval Queue',
      message: 'I need help with the My Approval Queue page in dq-made-easy.',
      source: 'app-footer',
      workspaceId: 'retail-banking',
      details: {
        page_id: 'approvals-my',
        page_label: 'My Approval Queue',
      },
    })
  })

  it('remembers when the footer is minimized and restores it from the icon launcher', async () => {
    const user = userEvent.setup()

    const { rerender } = render(
      <SupportRequestFooter
        apiBaseUrl="http://api.local/api"
        pageId="approvals-my"
        workspaceId="retail-banking"
      />
    )

    await user.click(screen.getByRole('button', { name: 'Minimize request assistance' }))

    expect(screen.queryByRole('heading', { name: 'Request assistance' })).toBeNull()
    const openButton = screen.getByRole('button', { name: 'Open request assistance' })
    expect(openButton).toBeTruthy()
    expect(openButton.textContent?.trim()).toBe('?')

    rerender(
      <SupportRequestFooter
        apiBaseUrl="http://api.local/api"
        pageId="approvals-my"
        workspaceId="retail-banking"
      />
    )

    expect(screen.queryByRole('heading', { name: 'Request assistance' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Open request assistance' })).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Open request assistance' }))

    expect(screen.getByRole('heading', { name: 'Request assistance' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Request assistance' })).toBeTruthy()
  })
})