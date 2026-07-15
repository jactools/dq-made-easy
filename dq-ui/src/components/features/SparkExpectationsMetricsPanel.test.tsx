/** @vitest-environment jsdom */

import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SparkExpectationsMetricsPanel } from './SparkExpectationsMetricsPanel'

describe('SparkExpectationsMetricsPanel', () => {
  it('renders the persisted failure envelope metrics', () => {
    const { container } = render(
      <SparkExpectationsMetricsPanel
        resultSummary={{
          engine_type: 'spark_expectations',
          result: 'failed',
          passed_count: 2,
          failed_count: 1,
          failure_code: 'DQ_EXECUTION_ERROR',
          failure_message: 'row-level expectation failed',
          failed_check: {
            check_name: 'not_null',
            reason: 'customer_id cannot be null',
            failure_stage: 'execute',
          },
          failure_metrics: {
            rule_family: 'row',
            failure_stage: 'execute',
            failed_check_count: 1,
            failed_row_count: 1,
          },
          trace: {
            exception_type: 'ValueError',
            message: 'row-level expectation failed',
          },
          observability_summary: {
            engine_type: 'spark_expectations',
            result: 'failed',
            passed_count: 2,
            failed_count: 1,
          },
        }}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Spark Expectations metrics' })).toBeTruthy()
    expect(screen.getByText('DQ_EXECUTION_ERROR')).toBeTruthy()
    expect(screen.getAllByText('row-level expectation failed').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('not_null')).toBeTruthy()
    expect(container.textContent).toContain('failed_row_count')
    expect(screen.getByText('ValueError')).toBeTruthy()
  })
})