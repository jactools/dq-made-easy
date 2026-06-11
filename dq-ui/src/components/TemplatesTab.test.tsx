/** @vitest-environment jsdom */

import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { TemplatesTab } from './Templates'

describe('TemplatesTab', () => {
  it('lets the user switch from my scope to all templates inline', () => {
    render(<TemplatesTab viewScope="my" onUseTemplate={vi.fn()} />)

    expect(screen.getByText(/no personal templates found yet/i)).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: /^all$/i }))

    expect(screen.getByText('NULL Value Check')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /use template/i }).length).toBeGreaterThan(0)
  })
})