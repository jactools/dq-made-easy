/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SupportRequestSubmitButton } from './SupportRequestSubmitButton'
import { mockButtonModule } from './test-support/appOwnedUiTestMocks'

vi.mock('./Button', () => mockButtonModule())

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))

describe('SupportRequestSubmitButton', () => {
  beforeEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('posts support requests to the canonical system support endpoint', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        reference_id: 'SUP-TEST123456',
        correlation_id: 'corr-test-1',
        delivery_modes: ['itsm'],
        message: 'Assistance request sent to Zammad ticket ZAM-4321.',
        ticket_number: 'ZAM-4321',
        ticket_system: 'Zammad',
        ticket_url: 'http://zammad.example.com/tickets/4321',
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const onSuccess = vi.fn()
    const onError = vi.fn()
    const user = userEvent.setup()

    render(
      <SupportRequestSubmitButton
        apiBaseUrl="http://api.local/api"
        buttonLabel="Request assistance"
        createRequestBody={() => ({ source: 'example-page' })}
        onSuccess={onSuccess}
        onError={onError}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Request assistance' }))

    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.local/api/system/v1/support/requests',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer token-123',
        }),
      })
    )
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(onError).not.toHaveBeenCalled()
  })
})