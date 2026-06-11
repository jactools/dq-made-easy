/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RuleDetailsModal } from './RuleDetailsModal'

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => ({
    applicationSettings: {
      apiBaseUrl: 'http://api.local',
    },
  }),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))

vi.mock('./app-primitives', async () => {
  const actual = await vi.importActual<typeof import('./app-primitives')>('./app-primitives')
  return {
    ...actual,
    AppModal: ({ isOpen, title, children, footer }: any) =>
      !isOpen ? null : (
        <div>
          <h1>{title}</h1>
          {children}
          <div>{footer}</div>
        </div>
      ),
    AppButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
      <button type={props.type || 'button'} {...props}>{children}</button>
    ),
    AppIcon: ({ name, ...props }: any) => <span data-icon={name} {...props} />,
  }
})

const buildJsonResponse = (body: any, ok = true, status = ok ? 200 : 500) => ({
  ok,
  status,
  json: async () => body,
  text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  blob: async () => new Blob([typeof body === 'string' ? body : JSON.stringify(body)], { type: 'application/json' }),
})

describe('RuleDetailsModal', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = String(init?.method || 'GET').toUpperCase()

      if (url.endsWith('/rules/rule-1') && method === 'PUT') {
        const body = JSON.parse(String((init as RequestInit | undefined)?.body || '{}'))
        return buildJsonResponse({
          id: 'rule-1',
          name: body.name || 'Rule Under Test',
          comments: body.comments,
          expression: body.dsl?.source?.expression || 'status = active',
          dimension: body.dimension || 'Validity',
        })
      }

      if (url.endsWith('/rules/rule-1')) {
        return buildJsonResponse({
          id: 'rule-1',
          name: 'Rule Under Test',
          comments: 'Initial rule note',
          expression: 'status = active',
          dimension: 'Validity',
          taxonomy: {
            owner: 'owner@example.com',
            dataSteward: 'steward@example.com',
            domainOwner: 'domain-owner@example.com',
            technicalOwner: 'technical-owner@example.com',
          },
        })
      }

      if (url.includes('/rules/rule-1/versions?limit=1&offset=0')) {
        return buildJsonResponse({
          versions: [{ id: 'version-1', versionNumber: 4 }],
        })
      }

      if (url.includes('/rules/rule-1/versions/version-1/compiler-artifacts/active')) {
        return buildJsonResponse({ detail: 'Not found' }, false, 404)
      }

      if (url.includes('/rules/rule-1/status-history')) {
        return buildJsonResponse([
          {
            id: 'history-1',
            rule_id: 'rule-1',
            action: 'edit',
            from_status: 'draft',
            to_status: 'tested',
            changed_by: 'user-admin',
            changed_at: '2026-04-05T18:00:00Z',
            reason: 'Seeded rule transition',
          },
        ])
      }

      if (url.endsWith('/test-proofs/rule-1')) {
        return buildJsonResponse([
          {
            id: 'proof-943a74dbb13b',
            status: 'failed',
            test_date: '2026-04-05T17:25:18Z',
            coverage: 0,
            records_tested_count: 0,
            failures_found: 0,
            proof_data: {
              request_status: 'failed',
              request_message: 'Timed out waiting for queued test data generation',
              error: 'Timed out waiting for queued test data generation',
              error_type: 'queued_test_data_generation_failed',
              execution_context: {
                source_rule_expression: 'email contains "@"',
                executed_expression: 'email contains "@"',
              },
              execution_trace: {
                result_status: 'failed',
              },
            },
            execution_context: {
              source_rule_expression: 'email contains "@"',
              executed_expression: 'email contains "@"',
            },
            execution_trace: {
              result_status: 'failed',
            },
          },
        ])
      }

      return buildJsonResponse({ detail: 'Unexpected request' }, false, 404)
    }) as any)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows timeout failures as technical execution issues with code and reason', async () => {
    render(
      <RuleDetailsModal
        isOpen={true}
        onClose={() => {}}
        ruleId="rule-1"
        ruleName="Rule Under Test"
        statusText="testing"
        approvalText="approved"
        versionHint={4}
      />,
    )

    expect(await screen.findByText('Technical execution issue')).toBeTruthy()
    expect(screen.getByText('queued_test_data_generation_failed')).toBeTruthy()
    expect(screen.getAllByText('Timed out waiting for queued test data generation').length).toBeGreaterThan(0)
    expect(screen.getByText('No records were evaluated, so this does not indicate the data failed the rule.')).toBeTruthy()
    expect(screen.getByText('Source rule expression snapshot:')).toBeTruthy()
    expect(screen.getAllByText('email contains "@"').length).toBeGreaterThan(0)
    expect(await screen.findByText('Ownership')).toBeTruthy()
    expect(screen.getByText('owner@example.com')).toBeTruthy()
    expect(screen.getByText('steward@example.com')).toBeTruthy()
    expect(screen.getByText('domain-owner@example.com')).toBeTruthy()
    expect(screen.getByText('technical-owner@example.com')).toBeTruthy()
    expect(await screen.findByText('Status History')).toBeTruthy()
    expect(screen.getByText('Action: Edit')).toBeTruthy()
    expect(screen.getByText('Seeded rule transition')).toBeTruthy()
  })

  it('saves rule comments from the details modal', async () => {
    render(
      <RuleDetailsModal
        isOpen={true}
        onClose={() => {}}
        ruleId="rule-1"
        ruleName="Rule Under Test"
        statusText="testing"
        approvalText="approved"
        versionHint={4}
      />,
    )

    const commentsField = await screen.findByLabelText('Comments')
    expect((commentsField as HTMLTextAreaElement).value).toBe('Initial rule note')

    fireEvent.change(commentsField, { target: { value: 'Updated rule note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save comments' }))

    expect(await screen.findByText('Comment saved')).toBeTruthy()
    expect((commentsField as HTMLTextAreaElement).value).toBe('Updated rule note')
  })
})