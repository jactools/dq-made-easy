/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GxSuitesAdmin } from './GxSuitesAdmin'

vi.mock('./GxSuiteScopePickerModal', () => ({
  GxSuiteScopePickerModal: ({ isOpen, onClose, onSelect }: any) => {
    if (!isOpen) {
      return null
    }

    return (
      <div>
        <button
          type="button"
          onClick={() => {
            onSelect({
              kind: 'data_object_version',
              dataObjectId: 'object-orders',
              dataObjectName: 'Orders',
              dataObjectVersionId: 'dov-777',
            })
          }}
        >
          Pick Orders scope
        </button>
        <button type="button" onClick={onClose}>Close scope picker</button>
      </div>
    )
  },
}))

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => ({
    applicationSettings: {
      apiBaseUrl: 'http://api.local',
    },
  }),
  useSettingsOptional: () => ({
    applicationSettings: {
      apiBaseUrl: 'http://api.local',
    },
  }),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'token-123',
}))


const buildJsonResponse = (body: any, ok = true, status = ok ? 200 : 500) => ({
  ok,
  status,
  json: async () => body,
  text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
})

describe('GxSuitesAdmin', () => {
  beforeEach(() => {
    cleanup()

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/gx/suites?dataObjectVersionId=dov-777')) {
        return buildJsonResponse([
          {
            suite_id: 'gx_suite_8f40b9ea',
            suite_version: 3,
            artifact_version: 'v1',
            assignment_scope: {
              data_object_id: 'object-orders',
              dataset_id: 'dataset-orders',
              data_product_id: 'odcs.dp.orders',
            },
            resolved_execution_scope: {
              data_object_version_ids: ['dov-777', 'dov-778'],
            },
            compiled_from: {
              rule_ids: ['rule-1'],
              compiler_version: 'compiler-42',
              generated_at: '2026-04-10T07:00:00Z',
            },
            execution_contract: {
              engine_target: 'pyspark',
              execution_shape: 'join_pair',
              traceability: {
                rule_id: 'rule-1',
                rule_version_id: 'rule-version-1',
                gx_suite_id: 'gx_suite_8f40b9ea',
                gx_suite_version: 3,
                data_object_version_id: 'dov-777',
                source_rule_expression: 'customer_address IS NOT NULL',
                compiled_expression: 'customer_address IS NOT NULL',
                artifact_key: 'artifact-abc-123',
              },
            },
          },
        ])
      }

      if (url.includes('/rules/rule-1/versions/rule-version-1')) {
        return buildJsonResponse({
          id: 'rule-version-1',
          ruleId: 'rule-1',
          versionNumber: 7,
          name: 'Customer Address Match',
        })
      }

      return buildJsonResponse({ detail: 'Unexpected request' }, false, 404)
    })

    vi.stubGlobal('fetch', fetchMock)
  })

  it('shows summary-first validation suite rows with IDs in secondary context', async () => {
    const user = userEvent.setup()

    render(<GxSuitesAdmin />)

    await user.click(screen.getByRole('button', { name: 'Browse data catalog' }))
    await user.click(await screen.findByRole('button', { name: 'Pick Orders scope' }))
    await user.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('Validation suite v3')).toBeTruthy()
    expect(await screen.findByText('Assignment: Data product, Dataset, Data object')).toBeTruthy()
    expect(await screen.findByText('Compiled from 1 rule')).toBeTruthy()
    expect(await screen.findByText('Traceability: Customer Address Match v7')).toBeTruthy()
    expect(await screen.findByText('Rule build: artifact-abc-123')).toBeTruthy()
    expect(await screen.findByText('Source expression: customer_address IS NOT NULL')).toBeTruthy()
    expect(await screen.findByText('Compiled expression: customer_address IS NOT NULL')).toBeTruthy()
    expect(await screen.findByText('2 object versions')).toBeTruthy()
  })
})
