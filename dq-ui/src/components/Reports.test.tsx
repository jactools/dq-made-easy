/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Rule } from '../types/rules'
import { Reports } from './Reports'

const mockUseRules = vi.fn()
const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()
const mockGetUiTelemetryConnectionState = vi.fn()
const mockSubscribeUiTelemetryConnectionState = vi.fn()

vi.mock('../hooks/useContexts', () => ({
  useRules: () => mockUseRules(),
  useAuth: () => mockUseAuth(),
  useSettings: () => mockUseSettings(),
  useSettingsOptional: () => mockUseSettings(),
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

vi.mock('./HealthScorecards', () => ({
  HealthScorecards: () => <div data-testid="health-scorecards" />,
}))

vi.mock('./DataQualityMetrics', () => ({
  DataQualityMetrics: () => <div data-testid="data-quality-metrics" />,
}))

vi.mock('./ExecutionResultExplorer', () => ({
  ExecutionResultExplorer: () => <div data-testid="execution-result-explorer" />,
}))

vi.mock('./RuleDetailsModal', () => ({
  RuleDetailsModal: () => null,
}))

vi.mock('./ReconciliationWorkbench', () => ({
  ReconciliationWorkbench: () => <div data-testid="reconciliation-workbench" />,
}))

vi.mock('./discussion/DiscussionPanel', () => ({
  DiscussionPanel: () => null,
  normalizeDiscussionEntries: (entries: unknown) => entries,
}))

vi.mock('../telemetry', () => ({
  getUiTelemetryConnectionState: () => mockGetUiTelemetryConnectionState(),
  subscribeUiTelemetryConnectionState: (listener: (state: string) => void) => mockSubscribeUiTelemetryConnectionState(listener),
}))

const mockRules: Rule[] = []

beforeEach(() => {
  mockUseRules.mockReturnValue({ rules: mockRules })
  mockUseAuth.mockReturnValue({ currentWorkspaceId: 'retail-banking' })
  mockUseSettings.mockReturnValue({ applicationSettings: { apiBaseUrl: 'http://api.local' } })
  mockGetUiTelemetryConnectionState.mockReturnValue('disabled')
  mockSubscribeUiTelemetryConnectionState.mockReturnValue(() => undefined)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('Reports', () => {
  it('renders the shared operations shell and view tabs', () => {
    render(<Reports initialTab="metrics" />)

    expect(screen.getByRole('heading', { name: 'Operations' })).toBeTruthy()
    expect(screen.getByRole('tablist', { name: 'Operations views' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Health Dashboard' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Result Explorer' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Validation Test Results' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Incidents' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Reconciliation' })).toBeTruthy()
    expect(screen.getByTestId('health-scorecards')).toBeTruthy()
    expect(screen.getByTestId('data-quality-metrics')).toBeTruthy()
  })

  it('shows a telemetry warning banner when observability is unavailable', () => {
    mockGetUiTelemetryConnectionState.mockReturnValue('unavailable')

    render(<Reports initialTab="metrics" />)

    expect(screen.getByRole('status')).toBeTruthy()
    expect(screen.getByText(/observability is temporarily unavailable/i)).toBeTruthy()
  })
})
