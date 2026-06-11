/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

import { ExecutionMetricsPanel } from './ExecutionMetricsPanel'

afterEach(() => {
  cleanup()
})

describe('ExecutionMetricsPanel', () => {
  it('renders core metrics', () => {
    render(
      <ExecutionMetricsPanel
        passed={false}
        metrics={{
          matchCount: 81,
          mismatchCount: 19,
          eligibleJoinedRows: 100,
          matchRate: 81,
          actualityDateMismatchCount: 7,
          nullOrMissingJoinKeyCount: 3,
        }}
      />,
    )

    expect(screen.getByText('Execution Metrics ✗')).toBeTruthy()
    expect(screen.getByText('81.00%')).toBeTruthy()
    expect(screen.getByText('81')).toBeTruthy()
    expect(screen.getByText('19')).toBeTruthy()
    expect(screen.getByText('100')).toBeTruthy()
    expect(screen.getByText('7')).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy()
  })

  it('hides optional cards when counts are zero', () => {
    const { container } = render(
      <ExecutionMetricsPanel
        passed={true}
        metrics={{
          matchCount: 10,
          mismatchCount: 0,
          eligibleJoinedRows: 10,
          matchRate: 100,
          actualityDateMismatchCount: 0,
          nullOrMissingJoinKeyCount: 0,
        }}
      />,
    )

    expect(screen.queryByText('Actuality-Date Drift')).toBeNull()
    expect(screen.queryByText('Excluded (Null Keys)')).toBeNull()
    expect(container.querySelector('.metrics-success')).toBeTruthy()
  })
})
