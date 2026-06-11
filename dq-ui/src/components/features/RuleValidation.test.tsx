/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { RuleValidation } from './RuleValidation'

const mockUseSettings = vi.fn()
const mockUseAuth = vi.fn()

vi.mock('../../hooks/useContexts', () => ({
  useSettings: () => mockUseSettings(),
  useSettingsOptional: () => mockUseSettings(),
}))

vi.mock('../../hooks/useKeycloak', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('../../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))

vi.mock('../../telemetry', () => ({
  withUiSpan: async (_name: string, _attributes: Record<string, unknown>, callback: (span: { setAttribute: (key: string, value: unknown) => void }) => Promise<unknown>) => {
    const span = { setAttribute: () => undefined }
    return callback(span)
  },
}))

const buildJsonResponse = (body: unknown, ok = true) => ({
  ok,
  status: ok ? 200 : 500,
  json: async () => body,
  text: async () => JSON.stringify(body),
})

const buildBlobResponse = (value: string, ok = true) => ({
  ok,
  status: ok ? 200 : 500,
  blob: async () => new Blob([value], { type: 'text/csv' }),
})

describe('RuleValidation', () => {
  beforeEach(() => {
    mockUseSettings.mockReturnValue({
      applicationSettings: {
        apiBaseUrl: 'http://api.local',
      },
      workspaceSettings: {
        workspaceId: 'workspace-alpha',
      },
    })
    mockUseAuth.mockReturnValue({
      currentWorkspaceId: 'workspace-alpha',
    })
    sessionStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    sessionStorage.clear()
  })

  it('hydrates selected rules from the Rules handoff payload', async () => {
    sessionStorage.setItem('dq-rule-validation-navigation-selection', JSON.stringify({
      rule_ids: ['rule-2'],
      source: 'rules',
    }))

    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/rules/compiler-versions')) {
        return buildJsonResponse({
          data: [{ ruleId: 'rule-1', ruleVersionNumber: 3 }, { ruleId: 'rule-2', ruleVersionNumber: 4 }],
        })
      }

      if (url.includes('/rules/validation-runs')) {
        return buildJsonResponse({
          data: [],
          pagination: { total: 0, page: 1, limit: 10, totalPages: 0 },
        })
      }

      if (url.includes('/rules?workspace=')) {
        return buildJsonResponse({
          data: [
            { id: 'rule-1', name: 'Customer Email Presence' },
            { id: 'rule-2', name: 'Order Amount Range' },
          ],
        })
      }

      throw new Error(`Unexpected fetch URL: ${url}`)
    }))

    render(<RuleValidation />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Validate \(1\)/i })).toBeTruthy()
    })

    const checkbox = screen.getByRole('checkbox', { name: /Order Amount Range/i }) as HTMLInputElement
    expect(checkbox.checked).toBe(true)
    expect(sessionStorage.getItem('dq-rule-validation-navigation-selection')).toBeNull()
  })

  it('keeps validation history, batch validation, and CSV export functional', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)

      if (url.includes('/rules/compiler-versions')) {
        return buildJsonResponse({
          data: [{ ruleId: 'rule-1', ruleVersionNumber: 3 }],
        })
      }

      if (url.includes('/rules/validation-runs/run-1/export?format=csv')) {
        return buildBlobResponse('rule_id,status\nrule-1,valid\n')
      }

      if (url.includes('/rules/validation-runs?workspace=')) {
        return buildJsonResponse({
          data: [
            {
              id: 'run-1',
              runAt: '2026-04-27T10:00:00Z',
              total: 1,
              validCount: 1,
              status: 'completed',
            },
          ],
          pagination: { total: 1, page: 1, limit: 10, totalPages: 1 },
        })
      }

      if (url.includes('/rules/validate/batch')) {
        expect(init?.method).toBe('POST')
        return buildJsonResponse({
          runId: 'run-2',
          results: [
            {
              ruleId: 'rule-1',
              ruleName: 'Customer Email Presence',
              valid: true,
              errors: 0,
              warnings: 0,
              diagnostics: [],
              compiledExpression: 'email IS NOT NULL',
            },
          ],
          conflicts: [],
          summary: {
            total: 1,
            valid: 1,
            invalid: 0,
            warnings: 0,
            errors: 0,
          },
        })
      }

      if (url.includes('/rules?workspace=')) {
        return buildJsonResponse({
          data: [
            { id: 'rule-1', name: 'Customer Email Presence' },
          ],
        })
      }

      throw new Error(`Unexpected fetch URL: ${url}`)
    })

    vi.stubGlobal('fetch', fetchMock)

    Object.defineProperty(URL, 'createObjectURL', {
      value: vi.fn(() => 'blob:validation-csv'),
      configurable: true,
      writable: true,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: vi.fn(() => undefined),
      configurable: true,
      writable: true,
    })
    const anchorClickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)

    render(<RuleValidation />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Validation Run History' })).toBeTruthy()
      expect(screen.getByText('run-1…')).toBeTruthy()
    })

    fireEvent.click(screen.getByRole('button', { name: /Validate All/i }))

    await waitFor(() => {
      expect(screen.getByText(/run: run-2/i)).toBeTruthy()
    })

    fireEvent.click(screen.getByTitle('Export CSV'))

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalled()
      expect(anchorClickSpy).toHaveBeenCalled()
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:validation-csv')
    })

    expect(
      fetchMock.mock.calls.some(([request]) => String(request).includes('/rules/validation-runs?workspace=workspace-alpha&limit=10'))
    ).toBe(true)
    expect(
      fetchMock.mock.calls.some(([request]) => String(request).includes('/rules/validate/batch'))
    ).toBe(true)
    expect(
      fetchMock.mock.calls.some(([request]) => String(request).includes('/rules/validation-runs/run-1/export?format=csv'))
    ).toBe(true)
  })
})