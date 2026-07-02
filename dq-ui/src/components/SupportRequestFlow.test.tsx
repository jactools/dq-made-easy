/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SupportRequestFlow } from './SupportRequestFlow'
import { mockButtonModule } from './test-support/appOwnedUiTestMocks'

vi.mock('./Button', () => mockButtonModule())

let supportRequestSubmitResponse: Record<string, unknown> = {
  referenceId: 'SUP-TEST123456',
  deliveryModes: ['itsm'],
  message: 'Assistance request sent to Zammad ticket ZAM-4321.',
  correlationId: 'corr-test-1',
  ticketNumber: 'ZAM-4321',
  ticketSystem: 'Zammad',
  ticketUrl: 'http://zammad.example.com/tickets/4321',
}

vi.mock('./SupportRequestSubmitButton', () => ({
  SupportRequestSubmitButton: ({ buttonLabel, onSuccess }: any) => (
    <button
      type="button"
      onClick={() => onSuccess(supportRequestSubmitResponse)}
    >
      {buttonLabel}
    </button>
  ),
}))

vi.mock('./StatusBanner', () => ({
  StatusBanner: ({ message, referenceId, secondaryAction, onDismiss }: any) => (
    <div>
      <div>{message}</div>
      {referenceId && <div>Reference ID: {referenceId}</div>}
      {secondaryAction}
      <button type="button" onClick={onDismiss}>Dismiss</button>
    </div>
  ),
}))

describe('SupportRequestFlow', () => {
  beforeEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows the support success banner and ticket action for ITSM responses', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const user = userEvent.setup()

    supportRequestSubmitResponse = {
      referenceId: 'SUP-TEST123456',
      deliveryModes: ['itsm'],
      message: 'Assistance request sent to Zammad ticket ZAM-4321.',
      correlationId: 'corr-test-1',
      ticketNumber: 'ZAM-4321',
      ticketSystem: 'Zammad',
      ticketUrl: 'http://zammad.example.com/tickets/4321',
    }

    render(
      <SupportRequestFlow
        apiBaseUrl="http://api.local"
        buttonLabel="Request assistance"
        createRequestBody={() => ({ source: 'example-page' })}
        onError={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Request assistance' }))

    expect(await screen.findByText('Assistance request sent to Zammad ticket ZAM-4321.')).toBeTruthy()
    expect(screen.getByText('Reference ID: SUP-TEST123456')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Open ticket' }))
    expect(openSpy).toHaveBeenCalledWith('http://zammad.example.com/tickets/4321', '_blank', 'noopener,noreferrer')
  })

  it('opens the mailto draft for email responses', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const user = userEvent.setup()

    supportRequestSubmitResponse = {
      referenceId: 'SUP-TESTEMAIL01',
      deliveryModes: ['email'],
      message: 'Prepared email draft for prototype@jaccloud.nl. Reference ID: SUP-TESTEMAIL01',
      correlationId: 'corr-test-2',
      mailtoUrl: 'mailto:prototype@jaccloud.nl?subject=GX%20run%20plan%20validation%20assistance',
      recipientEmail: 'prototype@jaccloud.nl',
    }

    render(
      <SupportRequestFlow
        apiBaseUrl="http://api.local"
        buttonLabel="Request assistance"
        createRequestBody={() => ({ source: 'example-page' })}
        onError={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Request assistance' }))

    expect(openSpy).toHaveBeenCalledWith(
      'mailto:prototype@jaccloud.nl?subject=GX%20run%20plan%20validation%20assistance',
      '_blank',
      'noopener,noreferrer'
    )
    expect(await screen.findByText('Prepared email draft for prototype@jaccloud.nl. Reference ID: SUP-TESTEMAIL01')).toBeTruthy()
  })
})