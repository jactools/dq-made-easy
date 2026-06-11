/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { DeliveryInventory } from './DeliveryInventory'
import { mockButtonModule } from './test-support/appOwnedUiTestMocks'

const mockUseAuth = vi.fn()
const mockUseSettings = vi.fn()

vi.mock('../hooks/useContexts', () => ({
  useAuth: () => mockUseAuth(),
  useSettings: () => mockUseSettings(),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => 'test-token',
}))

vi.mock('./Button', () => mockButtonModule())

vi.mock('./WorkspaceSelector', () => ({
  getWorkspaceDisplayName: (workspaceId: string) => (workspaceId === 'retail-banking' ? 'Retail Banking' : workspaceId),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('DeliveryInventory', () => {
  it('renders workspace deliveries and AIStor presence without exposing file contents', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      getCurrentUserRole: () => 'auditor',
      hasAnyScope: () => true,
    })
    mockUseSettings.mockReturnValue({
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1' },
    })

    const fetchMock = (vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: [
            {
              id: 'del-31',
              data_object_version_id: 'dov-1',
              version: 1,
              delivered_at: '2026-02-21T15:30:00Z',
              delivery_location: 's3a://analytics/Customer/v1/LOAD_DTS=20260221T153000000Z',
              storage_exists: true,
              storage_object_count: 3,
            },
          ],
          pagination: {
            total: 1,
            page: 1,
            limit: 100,
            total_pages: 1,
            has_next: false,
            has_previous: false,
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'note-del-31',
          data_delivery_id: 'del-31',
          data_object_id: 'Customer',
          data_object_version_id: 'dov-1',
          version: 1,
          delivered_at: '2026-02-21T15:30:00Z',
          timestamp: '2026-02-21T15:30:00Z',
          delivery_location: 's3a://analytics/Customer/v1/LOAD_DTS=20260221T153000000Z',
          delivery_status: 'completed',
            delivery_format: 'hudi',
            delivery_format_warning: 'Unsupported file format: hudi. The delivery note states a format this runtime cannot seed.',
          record_count: 142900,
          size_bytes: 45200000,
          attributes_count: 10,
          file_count: 3,
          ingestor_name: 'data-ingestor',
          ingestor_run_id: 'ing-20260221-1530',
          source_system: 'crm',
          source_snapshot_id: 'snap-20260221-1530',
          checksum: 'b2f3d8c2e1f4',
          checksum_algorithm: 'sha256',
          metadata_json: {
            workspace_id: 'retail-banking',
            batch_id: '20260221-1530',
            notes: ['validated', 'published'],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'note-del-31',
          data_delivery_id: 'del-31',
          data_object_id: 'Customer',
          data_object_version_id: 'dov-1',
          version: 1,
          delivered_at: '2026-02-21T15:30:00Z',
          timestamp: '2026-02-21T15:30:00Z',
          delivery_location: 's3a://analytics/Customer/v1/LOAD_DTS=20260221T153000000Z',
          delivery_status: 'completed',
            delivery_format: 'hudi',
            delivery_format_warning: 'Unsupported file format: hudi. The delivery note states a format this runtime cannot seed.',
          record_count: 142900,
          size_bytes: 45200000,
          attributes_count: 10,
          file_count: 3,
          file_names: ['part-0000.parquet', 'part-0001.parquet', '_SUCCESS'],
          storage_exists: true,
          storage_object_count: 3,
          ingestor_name: 'data-ingestor',
          ingestor_run_id: 'ing-20260221-1530',
          source_system: 'crm',
          source_snapshot_id: 'snap-20260221-1530',
          checksum: 'b2f3d8c2e1f4',
          checksum_algorithm: 'sha256',
          metadata_json: {
            workspace_id: 'retail-banking',
            batch_id: '20260221-1530',
            notes: ['validated', 'published'],
          },
        }),
      })) as unknown as typeof fetch

    vi.stubGlobal('fetch', fetchMock)

    render(<DeliveryInventory />)

    await waitFor(() => {
      expect(screen.getByText('del-31')).toBeTruthy()
    })

    expect(screen.getByRole('heading', { name: /deliveries in retail banking/i })).toBeTruthy()
    expect(screen.getByText('Present on AIStor')).toBeTruthy()
    expect(screen.getByText('V1')).toBeTruthy()
    expect(screen.getByText('s3a://analytics/Customer/v1/LOAD_DTS=20260221T153000000Z')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /view note/i }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /del-31/i })).toBeTruthy()
    })

    expect(screen.getByText('hudi')).toBeTruthy()
    expect(screen.getByText(/unsupported file format: hudi/i)).toBeTruthy()
    expect(screen.getByText('data-ingestor')).toBeTruthy()
    expect(screen.getByText('sha256')).toBeTruthy()
    expect(screen.queryByText('Storage details')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /load storage details/i }))

    await waitFor(() => {
      expect(screen.getByText('Storage details')).toBeTruthy()
    })

    expect(screen.getByText('Present on storage')).toBeTruthy()
    expect(screen.getByText('Storage object count')).toBeTruthy()
    expect(screen.getByText('part-0000.parquet, part-0001.parquet, _SUCCESS')).toBeTruthy()
    expect(screen.getByText(/workspaceId/i)).toBeTruthy()
  })

  it('blocks users without the required workspace role', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      currentWorkspaceId: 'retail-banking',
      getCurrentUserRole: () => 'analyst',
      hasAnyScope: () => false,
    })
    mockUseSettings.mockReturnValue({
      applicationSettings: { apiBaseUrl: 'http://localhost:8000/v1' },
    })

    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<DeliveryInventory />)

    expect(screen.getByRole('heading', { name: /access restricted/i })).toBeTruthy()
    expect(screen.getByText(/data catalog read access/i)).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})