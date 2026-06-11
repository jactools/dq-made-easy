/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SessionExpired } from './SessionExpired'
import { mockButtonModule } from './test-support/appOwnedUiTestMocks'

vi.mock('./Button', () => mockButtonModule())

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

beforeEach(() => {
  vi.useFakeTimers()
})

describe('SessionExpired', () => {
  it('explains that the user was logged out because the session timed out', () => {
    const onOpenLogin = vi.fn()
    render(<SessionExpired onOpenLogin={onOpenLogin} />)

    expect(screen.getByText('Signed out after session timeout')).toBeTruthy()
    expect(
      screen.getByText('You were logged out because your session timed out due to inactivity. Please sign in again.')
    ).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Open Login' })).toBeTruthy()
  })
})
