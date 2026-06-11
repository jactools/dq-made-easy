// @vitest-environment jsdom

import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useRuleAttributeCatalog } from './useRuleAttributeCatalog'

const mockFetch = vi.fn()

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

describe('useRuleAttributeCatalog partial enrichment', () => {
  it('keeps attribute names when lineage fetches fail', async () => {
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

      if (url.includes('/data-sets') || url.includes('/data-products')) {
        throw new Error('lineage service unavailable')
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
    })
  })
})