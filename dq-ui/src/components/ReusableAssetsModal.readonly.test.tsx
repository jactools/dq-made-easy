/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ReusableFiltersModal } from './ReusableFiltersModal'
import { ReusableJoinsModal } from './ReusableJoinsModal'

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => ({
    applicationSettings: {
      apiBaseUrl: 'http://example.test',
    },
  }),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-1',
}))

vi.mock('./app-primitives', async () => {
  const actual = await vi.importActual<typeof import('./app-primitives')>('./app-primitives')
  return {
    ...actual,
    AppModal: ({ isOpen, title, children, footer }: any) =>
      isOpen ? <div><h1>{title}</h1>{children}{footer}</div> : null,
  }
})

vi.mock('./UnsavedChangesDialog', () => ({
  UnsavedChangesDialog: () => null,
}))

vi.mock('../hooks/useUnsavedChangesConfirmation', () => ({
  useUnsavedChangesConfirmation: () => ({
    showConfirmation: false,
    handleCloseWithConfirmation: vi.fn(),
    handleConfirmClose: vi.fn(),
    handleCancelConfirmation: vi.fn(),
  }),
}))


const fetchMock = vi.fn()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  fetchMock.mockReset()
})

describe('ReusableFiltersModal read-only mode', () => {
  it('shows only assigned filters without the available list', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ([
        {
          id: 'retail-banking_active_customers',
          name: 'Active Customers',
          description: 'Reusable filter for active customers only',
          filter_expression: "customer_status = 'active'",
        },
      ]),
    })

    render(
      <ReusableFiltersModal
        isOpen={true}
        onClose={vi.fn()}
        workspaceId="retail-banking"
        ruleName="Customer account consistency"
        currentFilterIds={['retail-banking_active_customers']}
        readOnly={true}
      />,
    )

    expect(screen.getByText('Reusable Filters (Read-only)')).toBeTruthy()
    expect(await screen.findAllByText('Active Customers')).toHaveLength(1)
    expect(screen.queryByText('Available reusable filters')).toBeNull()
    expect(screen.queryByText('Create reusable filter')).toBeNull()
    expect(screen.queryByText('Delete')).toBeNull()
  })

  it('uses API-backed search after the shared threshold is met', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ([
        {
          id: 'retail-banking_active_customers',
          name: 'Active Customers',
          description: 'Reusable filter for active customers only',
          filter_expression: "customer_status = 'active'",
        },
      ]),
    })

    render(
      <ReusableFiltersModal
        isOpen={true}
        onClose={vi.fn()}
        workspaceId="retail-banking"
        ruleName="Customer account consistency"
        currentFilterIds={[]}
        onAssignToRule={vi.fn()}
      />,
    )

    expect(await screen.findAllByText('Active Customers')).toHaveLength(2)
    fireEvent.change(screen.getByPlaceholderText('Name, description, or expression'), {
      target: { value: 'ac' },
    })

    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('q=ac'), expect.anything())

    fireEvent.change(screen.getByPlaceholderText('Name, description, or expression'), {
      target: { value: 'active customers' },
    })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/reusable-filters?workspace=retail-banking&q=active+customers'),
        expect.anything(),
      )
    })
  })
})

describe('ReusableJoinsModal read-only mode', () => {
  it('shows only the assigned join without the available list', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ([
        {
          id: 'retail-banking_customer_accounts',
          name: 'Customer Accounts Join',
          description: 'Join customers to their accounts on customer_id',
          join_definition: JSON.stringify([
            {
              joinType: 'inner',
              conditions: [
                {
                  leftDataObjectId: 'customers',
                  leftAttributeId: 'customer_id',
                  rightDataObjectId: 'accounts',
                  rightAttributeId: 'customer_id',
                  operator: '=',
                },
              ],
            },
          ]),
        },
      ]),
    })

    render(
      <ReusableJoinsModal
        isOpen={true}
        onClose={vi.fn()}
        workspaceId="retail-banking"
        ruleName="Customer account consistency"
        currentJoinId="retail-banking_customer_accounts"
        readOnly={true}
      />,
    )

    expect(screen.getByText('Reusable Joins (Read-only)')).toBeTruthy()
    expect(await screen.findAllByText('Customer Accounts Join')).toHaveLength(1)
    expect(screen.queryByText('Available reusable joins')).toBeNull()
    expect(screen.queryByText('Apply to Rule')).toBeNull()
    expect(screen.queryByText('Delete')).toBeNull()
  })
})