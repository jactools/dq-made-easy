/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { AttributeCard } from './AttributeCard'

afterEach(() => {
  cleanup()
})

describe('AttributeCard', () => {
  it('shows the originating workspace label for an attribute', () => {
    render(
      <AttributeCard
        attribute={{
          id: 'attr-1',
          name: 'customer_id',
          datasetName: 'Customer & Order Management',
          dataObjectName: 'Customer',
          workspaceId: 'retail-banking',
        }}
      />,
    )

    expect(screen.getByText(/Workspace: Retail Banking/)).toBeTruthy()
  })
})// @vitest-environment jsdom

import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AttributeCard } from './AttributeCard'

describe('AttributeCard', () => {
  it('shows the attribute name and hides the catalog id', () => {
    render(
      <AttributeCard
        attribute={{
          id: 'attr-34',
          name: 'fee_amount',
          dataObjectName: 'Transaction',
          datasetName: 'Payments',
          dataObjectVersion: 'dov-9',
          dataProductName: 'Retail Banking',
        }}
      />,
    )

    expect(screen.getByText('Payments / Transaction – fee_amount')).toBeTruthy()
    expect(screen.getByText('Version: dov-9')).toBeTruthy()
    expect(screen.getByText('Retail Banking')).toBeTruthy()
    expect(screen.queryByText('attr-34')).toBeNull()
  })
})