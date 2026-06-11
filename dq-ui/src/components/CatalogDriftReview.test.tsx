/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { CatalogDriftReview } from './CatalogDriftReview'
import { mockButtonModule } from './test-support/appOwnedUiTestMocks'

const mockStartRevalidationJob = vi.fn().mockResolvedValue({ jobId: 'job-1', status: 'queued' })
const mockRecordDriftReview = vi.fn().mockResolvedValue({ reviewedCount: 1, reviewedAt: '2026-05-02T12:34:56Z' })
const mockGetJobStatus = vi.fn()
const mockCheckRuleDrift = vi.fn().mockResolvedValue({
  ruleId: 'rule-1',
  ruleName: 'Check Amount',
  ruleVersionId: 'rv-1',
  versionNumber: 5,
  affectedAliases: ['amount'],
  drifts: [
    {
      driftType: 'alias_unresolved',
      aliasName: 'transaction_amount_alias',
      resolvedTermName: 'transaction_amount_alias',
      previousValue: 'mapped',
      currentValue: 'unresolved',
      severity: 'warning',
      detectedAt: '2026-05-02T12:00:00Z',
    },
    {
      driftType: 'data_type_changed',
      aliasName: 'amount',
      resolvedTermName: 'transaction_amount',
      previousValue: 'DECIMAL',
      currentValue: 'INTEGER',
      severity: 'critical',
      detectedAt: '2026-05-02T12:00:00Z',
    },
  ],
  totalDrifts: 2,
  needsRevalidation: true,
  detectedAt: '2026-05-02T12:00:00Z',
})
const mockGetDriftSummary = vi.fn().mockResolvedValue({
  rulesWithDrift: 1,
  totalDriftsDetected: 2,
  criticalDrifts: 1,
  warningDrifts: 1,
  totalRulesChecked: 24,
  affectedRules: [
    {
      ruleId: 'rule-1',
      ruleName: 'Check Amount',
      ruleVersionId: 'rv-1',
      versionNumber: 5,
      affectedAliases: ['amount'],
      totalDrifts: 2,
      needsRevalidation: true,
    },
  ],
  byDriftType: { alias_unresolved: 1, data_type_changed: 1 },
})

vi.mock('./Button', () => mockButtonModule())

vi.mock('./DriftAlert', () => ({
  DriftAlert: () => <div>Drift alert</div>,
}))

vi.mock('./RevalidationProgress', () => ({
  RevalidationProgress: () => null,
}))

vi.mock('../hooks/useCatalogDrift', () => ({
  useCatalogDrift: () => ({
    checkRuleDrift: mockCheckRuleDrift,
    getDriftSummary: mockGetDriftSummary,
    loading: false,
    error: 'Failed to check drift: Not Found',
  }),
}))

vi.mock('../hooks/useBatchRevalidation', () => ({
  useBatchRevalidation: () => ({
    startRevalidationJob: mockStartRevalidationJob,
    recordDriftReview: mockRecordDriftReview,
    getJobStatus: mockGetJobStatus,
  }),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('CatalogDriftReview', () => {
  it('renders affected rules in Rule Quality', async () => {
    render(<CatalogDriftReview />)

    expect(await screen.findByText('Catalog Drift')).toBeTruthy()
    expect(await screen.findByText('Affected Rules')).toBeTruthy()
    expect(await screen.findByText('Check Amount')).toBeTruthy()
    expect(await screen.findByText('Alias-level drift')).toBeTruthy()
    expect(await screen.findByText('Attribute-level drift')).toBeTruthy()
    expect(await screen.findByText('Alias-level 1, attribute-level 1')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Revalidate All Affected Rules' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Revalidate All Affected Rules' }))

    await waitFor(() => {
      expect(mockRecordDriftReview).toHaveBeenCalledWith([
        {
          ruleId: 'rule-1',
          ruleName: 'Check Amount',
          ruleVersionId: 'rv-1',
          versionNumber: 5,
          affectedAliases: ['amount'],
          totalDrifts: 2,
          needsRevalidation: true,
        },
      ])
    })

    expect(mockStartRevalidationJob).toHaveBeenCalledWith(['rv-1'])
  })
})