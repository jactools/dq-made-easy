/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { DriftAlert } from './DriftAlert'
import { mockButtonModule } from './test-support/appOwnedUiTestMocks'

vi.mock('./Button', () => mockButtonModule())

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('DriftAlert', () => {
  it('separates alias-level drift from attribute-level drift', () => {
    render(
      <DriftAlert
        ruleId="rule-1"
        ruleVersionId="rv-1"
        affectedAliases={['amount', 'amount_alias']}
        drifts={[
          {
            driftType: 'alias_unresolved',
            aliasName: 'amount_alias',
            resolvedTermName: 'amount_alias',
            previousValue: 'mapped',
            currentValue: 'unresolved',
            severity: 'warning',
          },
          {
            driftType: 'data_type_changed',
            aliasName: 'amount',
            resolvedTermName: 'amount',
            previousValue: 'DECIMAL',
            currentValue: 'INTEGER',
            severity: 'critical',
          },
        ]}
        needsRevalidation={true}
        onRevalidate={vi.fn().mockResolvedValue(undefined)}
        onDismiss={vi.fn()}
      />,
    )

    expect(screen.getByText('Business Term Drift')).toBeTruthy()
    expect(screen.getByText('Technical Attribute Drift')).toBeTruthy()
    expect(screen.getByText('Business term resolution and glossary mapping issues')).toBeTruthy()
    expect(screen.getByText('Technical schema and data type changes on catalog attributes')).toBeTruthy()
    expect(screen.getByText('Business Term Drift:')).toBeTruthy()
    expect(screen.getByText('Technical Attribute Drift:')).toBeTruthy()
  })

  it('shows a subscribe action for monitor notifications', async () => {
    const onSubscribeToNotifications = vi.fn().mockResolvedValue(undefined)

    render(
      <DriftAlert
        ruleId="rule-1"
        ruleVersionId="rv-1"
        affectedAliases={['amount']}
        drifts={[
          {
            driftType: 'alias_unresolved',
            aliasName: 'amount',
            resolvedTermName: 'amount',
            previousValue: 'mapped',
            currentValue: 'unresolved',
            severity: 'warning',
          },
        ]}
        needsRevalidation={false}
        onRevalidate={vi.fn().mockResolvedValue(undefined)}
        onDismiss={vi.fn()}
        onSubscribeToNotifications={onSubscribeToNotifications}
      />,
    )

    const subscribeButton = screen.getByRole('button', { name: 'Subscribe me to notifications' })
    fireEvent.click(subscribeButton)

    await waitFor(() => {
      expect(onSubscribeToNotifications).toHaveBeenCalledTimes(1)
      expect(screen.getByRole('button', { name: 'Subscribed' })).toBeTruthy()
    })
  })
})