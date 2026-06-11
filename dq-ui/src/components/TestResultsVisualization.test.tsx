/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { TestResultsVisualization } from './TestResultsVisualization'
import { Rule } from '../types/rules'

afterEach(() => {
  cleanup()
})

const buildRule = (overrides?: Partial<Rule>): Rule => ({
  id: 'rule-1',
  workspace: 'ws-1',
  name: 'Join consistency rule',
  description: 'Checks consistency between two datasets',
  status: 'tested',
  createdAt: '2026-03-28T09:00:00Z',
  attributes: ['left.id', 'right.id'],
  riskLevel: 'medium',
  testResults: {
    id: 'proof-1',
    ruleId: 'rule-1',
    testDate: '2026-03-28T10:00:00Z',
    status: 'failed',
    coverage: 98,
    recordsTestedCount: 1000,
    failuresFound: 42,
    proofData: {},
    metrics: {
      matchCount: 958,
      mismatchCount: 42,
      eligibleJoinedRows: 1000,
      matchRate: 95.8,
      actualityDateMismatchCount: 5,
      nullOrMissingJoinKeyCount: 17,
    },
    diagnostics: [
      {
        failureClass: 'value_mismatch',
        count: 30,
        maxSampleSize: 3,
        sampleFailures: [
          {
            failureClass: 'value_mismatch',
            rowIdentifier: 'row-123',
            details: 'left.amount did not equal right.amount',
            affectedAttributes: ['left.amount', 'right.amount'],
          },
        ],
      },
    ],
  },
  ...overrides,
})

describe('TestResultsVisualization', () => {
  it('renders execution metrics and diagnostics when present', () => {
    render(<TestResultsVisualization rule={buildRule()} isExpanded={false} />)

    expect(screen.getByText('Execution Metrics ✗')).toBeTruthy()
    expect(screen.getByText('Execution Diagnostics (30 failures)')).toBeTruthy()
  })

  it('does not render execution panels when metrics and diagnostics are missing', () => {
    const rule = buildRule({
      testResults: {
        ...buildRule().testResults!,
        metrics: null,
        diagnostics: [],
      },
    })

    render(<TestResultsVisualization rule={rule} isExpanded={false} />)

    expect(screen.queryByText(/Execution Metrics/)).toBeNull()
    expect(screen.queryByText(/Execution Diagnostics/)).toBeNull()
  })
})
