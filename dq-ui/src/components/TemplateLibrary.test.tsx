/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { TemplateLibrary } from './TemplateLibrary'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('TemplateLibrary', () => {
  it('renders the shared shell and closes from the page header', () => {
    const onSelectTemplate = vi.fn()
    const onClose = vi.fn()

    render(<TemplateLibrary onSelectTemplate={onSelectTemplate} onClose={onClose} />)

    expect(screen.getByRole('heading', { name: 'Template Library' })).toBeTruthy()
    expect(screen.getByRole('button', { name: /close template library/i })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /close template library/i }))

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('keeps template selection and empty-state behavior working', () => {
    const onSelectTemplate = vi.fn()

    render(<TemplateLibrary onSelectTemplate={onSelectTemplate} />)

    fireEvent.click(screen.getAllByRole('button', { name: /^use template$/i })[0])

    expect(onSelectTemplate).toHaveBeenCalledTimes(1)

    fireEvent.change(screen.getByPlaceholderText('Search templates...'), {
      target: { value: 'does-not-exist' },
    })

    expect(screen.getByText(/no templates found matching your criteria/i)).toBeTruthy()
  })

  it('renders the advanced rule templates in the shared library', () => {
    const onSelectTemplate = vi.fn()

    render(<TemplateLibrary onSelectTemplate={onSelectTemplate} />)

    expect(screen.getByText('Cross Dataset Integrity')).toBeTruthy()
    expect(screen.getByText('Distribution Drift')).toBeTruthy()
    expect(screen.getByText('Seasonality Stability')).toBeTruthy()
  })
})