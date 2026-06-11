/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { JoinConditionsModal } from './JoinConditionsModal'

vi.mock('../hooks/useContexts', () => ({
  useSettings: () => ({
    applicationSettings: {
      apiBaseUrl: 'http://example.test',
    },
  }),
  useSettingsOptional: () => ({
    applicationSettings: {
      apiBaseUrl: 'http://example.test',
    },
  }),
}))

vi.mock('../contexts/AuthContext', () => ({
  getAuthToken: () => null,
}))

vi.mock('./Button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  PrimaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  SecondaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
  TertiaryButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" {...props}>{children}</button>
  ),
}))

vi.mock('./ModalShell', () => ({
  ModalShell: ({ isOpen, title, children, footer }: any) => (
    isOpen ? <div><h1>{title}</h1><div>{children}</div><div>{footer}</div></div> : null
  ),
}))

vi.mock('./UnsavedChangesDialog', () => ({
  UnsavedChangesDialog: () => null,
}))

vi.mock('../hooks/useUnsavedChangesConfirmation', () => ({
  useUnsavedChangesConfirmation: ({ onClose }: any) => ({
    showConfirmation: false,
    handleCloseWithConfirmation: onClose,
    handleConfirmClose: onClose,
    handleCancelConfirmation: vi.fn(),
  }),
}))


afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('JoinConditionsModal', () => {
  it('routes the legacy join creation action to Data Assets', () => {
    vi.stubGlobal('fetch', vi.fn())

    const onClose = vi.fn()
    const onOpenDataAssets = vi.fn()

    render(
      <JoinConditionsModal
        isOpen={true}
        onClose={onClose}
        onOpenDataAssets={onOpenDataAssets}
        ruleName="Customer consistency"
        currentJoinConditions={[]}
        onSave={vi.fn(async () => undefined)}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Open Data Assets' }))

    expect(onClose).toHaveBeenCalled()
    expect(onOpenDataAssets).toHaveBeenCalled()
  })
})
