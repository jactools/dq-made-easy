// @vitest-environment jsdom

import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useRuleAttributeCatalog } from './useRuleAttributeCatalog'

const mockFetch = vi.fn()

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

describe('useRuleAttributeCatalog', () => {
  it('retains historical attribute version ids for test selection', async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.includes('/attributes-catalog')) {
        return {
          ok: true,
          json: async () => ({
            data: [
              {
                id: 'attr-34',
                name: 'fee_amount',
                version_id: 'dov-9',
                data_object_id: 'do-4',
              },
            ],
            total: 1,
          }),
        }
      }

      if (url.includes('/data-objects-catalog')) {
        return {
          ok: true,
          json: async () => ({
            data: [
              {
                id: 'do-4',
                dataset_id: 'ds-3',
                latest_version_id: 'dov-32',
                name: 'Transaction',
              },
            ],
            total: 1,
          }),
        }
      }

      if (url.includes('/data-sets')) {
        return {
          ok: true,
          json: async () => ({
            data: [
              {
                id: 'ds-3',
                product_id: 'dp-1',
                name: 'Payments',
                workspace_id: 'retail-banking',
              },
            ],
            total: 1,
          }),
        }
      }

      if (url.includes('/data-products')) {
        return {
          ok: true,
          json: async () => ({
            data: [
              {
                id: 'dp-1',
                name: 'Retail Banking',
              },
            ],
            total: 1,
          }),
        }
      }

      throw new Error(`Unexpected fetch URL: ${url}`)
    })

    const { result } = renderHook(() =>
      useRuleAttributeCatalog({
        authToken: 'token-1',
        apiBaseUrl: 'http://example.test',
      }),
    )

    await waitFor(() => {
      expect(result.current.attributeCatalog['attr-34']).toBeTruthy()
    })

    expect(result.current.attributeCatalog['attr-34']).toMatchObject({
      id: 'attr-34',
      name: 'fee_amount',
      versionId: 'dov-9',
      dataObjectId: 'do-4',
      dataObjectName: 'Transaction',
      datasetName: 'Payments',
      dataProductName: 'Retail Banking',
      workspaceId: 'retail-banking',
    })
  })

  it('includes data asset fields as rule catalog entries', async () => {
    mockFetch.mockImplementation(async (url: string) => {
      if (url.includes('/attributes-catalog')) {
        return {
          ok: true,
          json: async () => ({
            data: [
              {
                id: 'data-asset::asset-1::asset-1-v1::source::field-1',
                name: 'customer_id',
                version_id: 'asset-1-v1',
                data_object_id: 'asset-1',
                workspace_id: 'ws-1',
                source_kind: 'data_asset',
                source_name: 'Customer health',
                source_version_label: 'v1',
              },
            ],
            total: 1,
          }),
        }
      }

      if (url.includes('/data-objects-catalog') || url.includes('/data-sets') || url.includes('/data-products')) {
        return {
          ok: true,
          json: async () => ({ data: [], total: 0 }),
        }
      }

      throw new Error(`Unexpected fetch URL: ${url}`)
    })

    const { result } = renderHook(() =>
      useRuleAttributeCatalog({
        authToken: 'token-1',
        apiBaseUrl: 'http://example.test',
      }),
    )

    await waitFor(() => {
      expect(result.current.attributeCatalog['data-asset::asset-1::asset-1-v1::source::field-1']).toBeTruthy()
    })

    expect(result.current.attributeCatalog['data-asset::asset-1::asset-1-v1::source::field-1']).toMatchObject({
      id: 'data-asset::asset-1::asset-1-v1::source::field-1',
      name: 'customer_id',
      versionId: 'asset-1-v1',
      dataObjectId: 'asset-1',
      dataObjectName: 'Customer health',
      workspaceId: 'ws-1',
      sourceKind: 'data_asset',
      sourceName: 'Customer health',
      sourceVersionLabel: 'v1',
    })
  })
})