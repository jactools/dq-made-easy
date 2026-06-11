/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { ExecutionDiagnosticsPanel } from './ExecutionDiagnosticsPanel'

afterEach(() => {
  cleanup()
})

describe('ExecutionDiagnosticsPanel', () => {
  it('renders no-failure state', () => {
    render(<ExecutionDiagnosticsPanel diagnostics={[]} />)

    expect(screen.getByText('Execution Diagnostics')).toBeTruthy()
    expect(screen.getByText('No failures detected')).toBeTruthy()
  })

  it('renders grouped diagnostics and expands samples', () => {
    render(
      <ExecutionDiagnosticsPanel
        diagnostics={[
          {
            failureClass: 'actuality_date_drift',
            count: 2,
            maxSampleSize: 5,
            sampleFailures: [
              {
                failureClass: 'actuality_date_drift',
                rowIdentifier: 'id=42',
                details: 'Actuality-date delta exceeds contract tolerance',
                affectedAttributes: ['updated_at'],
              },
            ],
          },
        ]}
      />,
    )

    expect(screen.getByText('Execution Diagnostics (2 failures)')).toBeTruthy()
    const headerButton = screen.getByRole('button', { name: /Actuality-Date Drift/i })
    fireEvent.click(headerButton)

    expect(screen.getByText('Sample failures (up to 5):')).toBeTruthy()
    expect(screen.getByText('Actuality-date delta exceeds contract tolerance')).toBeTruthy()
    expect(screen.getByText('Row: id=42')).toBeTruthy()
    expect(screen.getByText('Attributes: updated_at')).toBeTruthy()
  })
})
