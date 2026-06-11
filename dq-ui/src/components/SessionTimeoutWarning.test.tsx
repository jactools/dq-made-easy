/** @vitest-environment jsdom */

import React from 'react'
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SessionTimeoutWarning } from './SessionTimeoutWarning'

const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()

vi.mock('../hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
}))

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
  localStorage.clear()
})

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-04-06T12:00:00.000Z'))
  mockUseAuth.mockReturnValue({ isAuthenticated: true })
  mockUseSettings.mockReturnValue({
    applicationSettings: {
      sessionTimeoutMinutes: 10,
      sessionTimeoutWarningMinutes: 3,
    },
  })
})

describe('SessionTimeoutWarning', () => {
  it('does not show immediately when warning lead equals idle timeout', () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        sessionTimeoutMinutes: 5,
        sessionTimeoutWarningMinutes: 5,
      },
    })

    // Just had activity (e.g. right after login)
    localStorage.setItem('dq-session-last-activity-at', String(new Date('2026-04-06T12:00:00.000Z').getTime()))

    const { container, unmount } = render(<SessionTimeoutWarning />)
    expect(container.textContent?.trim()).toBe('')

    // Simulate 60s of inactivity (remaining time now within the effective warning window).
    unmount()
    localStorage.setItem('dq-session-last-activity-at', String(new Date('2026-04-06T11:59:00.000Z').getTime()))
    render(<SessionTimeoutWarning />)
    expect(screen.getByText(/You will be logged off in/i)).toBeTruthy()
  })

  it('shows a live logoff countdown near timeout', () => {
    localStorage.setItem('dq-session-last-activity-at', String(new Date('2026-04-06T11:52:30.000Z').getTime()))

    render(<SessionTimeoutWarning />)

    expect(screen.getByText('You will be logged off in 2 minutes 30 seconds.')).toBeTruthy()
    expect(screen.getByText('Any activity will keep your session active.')).toBeTruthy()
  })

  it('stays hidden when the session is outside the warning window', () => {
    localStorage.setItem('dq-session-last-activity-at', String(new Date('2026-04-06T11:56:00.000Z').getTime()))

    const { container } = render(<SessionTimeoutWarning />)

    expect(container.textContent?.trim()).toBe('')
  })

  it('shows a live logoff countdown when the JWT is nearing expiry', () => {
    // Disable idle timeout so the JWT expiry becomes the active reason.
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        sessionTimeoutMinutes: 0,
        sessionTimeoutWarningMinutes: 5,
      },
    })

    const expSeconds = Math.floor(new Date('2026-04-06T12:02:30.000Z').getTime() / 1000)
    const payload = btoa(JSON.stringify({ exp: expSeconds }))
    localStorage.setItem('authToken', `x.${payload}.y`)

    render(<SessionTimeoutWarning />)

    expect(screen.getByText('You will be logged off in 2 minutes 30 seconds.')).toBeTruthy()
    expect(screen.getByText('You may need to sign in again soon to continue.')).toBeTruthy()
  })

  it('shows refresh unavailability when token refresh has failed', () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        sessionTimeoutMinutes: 0,
        sessionTimeoutWarningMinutes: 5,
      },
    })

    const expSeconds = Math.floor(new Date('2026-04-06T12:02:30.000Z').getTime() / 1000)
    const payload = btoa(JSON.stringify({ exp: expSeconds }))
    localStorage.setItem('authToken', `x.${payload}.y`)

    mockUseAuth.mockReturnValue({ isAuthenticated: true, refreshAuthToken: vi.fn(), refreshUnavailable: true })

    render(<SessionTimeoutWarning />)

    expect(screen.getByText('You will be logged off in 2 minutes 30 seconds.')).toBeTruthy()
    expect(screen.getByText(/Automatic refresh is unavailable/i)).toBeTruthy()
  })

  it('does not show immediately when token lifetime equals warning lead', () => {
    // Disable idle timeout so the JWT expiry becomes the active reason.
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        sessionTimeoutMinutes: 0,
        sessionTimeoutWarningMinutes: 5,
      },
    })

    // Token expires exactly 5 minutes from "now".
    const expSeconds = Math.floor(new Date('2026-04-06T12:05:00.000Z').getTime() / 1000)
    const payload = btoa(JSON.stringify({ exp: expSeconds }))
    localStorage.setItem('authToken', `x.${payload}.y`)
    localStorage.setItem('dq-auth-token-observed-at', String(new Date('2026-04-06T12:00:00.000Z').getTime()))

    const { container, unmount } = render(<SessionTimeoutWarning />)
    expect(container.textContent?.trim()).toBe('')

    // After 1 minute, remaining time is within the shrunk window and the warning can show.
    unmount()
    vi.setSystemTime(new Date('2026-04-06T12:01:00.000Z'))
    render(<SessionTimeoutWarning />)
    expect(screen.getByText(/You will be logged off in/i)).toBeTruthy()
  })

  it('treats activity as keep-alive when a refresh token exists', () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        sessionTimeoutMinutes: 0,
        sessionTimeoutWarningMinutes: 5,
      },
    })

    const expSeconds = Math.floor(new Date('2026-04-06T12:02:30.000Z').getTime() / 1000)
    const payload = btoa(JSON.stringify({ exp: expSeconds }))
    localStorage.setItem('authToken', `x.${payload}.y`)
    localStorage.setItem('refreshToken', 'test-refresh')

    mockUseAuth.mockReturnValue({ isAuthenticated: true, refreshAuthToken: vi.fn() })

    render(<SessionTimeoutWarning />)

    expect(screen.getByText('Any activity will keep your session active.')).toBeTruthy()
  })

  it('hides token-expiry warning on activity when no refresh token exists', async () => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        sessionTimeoutMinutes: 0,
        sessionTimeoutWarningMinutes: 5,
      },
    })

    vi.setSystemTime(new Date('2026-04-06T12:01:00.000Z'))

    const expSeconds = Math.floor(new Date('2026-04-06T12:05:00.000Z').getTime() / 1000)
    const payload = btoa(JSON.stringify({ exp: expSeconds }))
    localStorage.setItem('authToken', `x.${payload}.y`)
    localStorage.setItem('dq-auth-token-observed-at', String(new Date('2026-04-06T12:00:00.000Z').getTime()))

    const { container } = render(<SessionTimeoutWarning />)
    expect(container.textContent || '').toMatch(/You will be logged off in/i)

    // Allow effects to attach the window activity listeners.
    await act(async () => {})
    act(() => {
      window.dispatchEvent(new Event('click'))
    })
    expect(screen.queryByText(/You will be logged off in/i)).toBeNull()
  })
})