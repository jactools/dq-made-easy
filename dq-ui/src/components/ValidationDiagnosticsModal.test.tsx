/** @vitest-environment jsdom */

import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import { ValidationDiagnosticsModal } from './ValidationDiagnosticsModal'

vi.mock('./app-primitives', async () => {
  const actual = await vi.importActual<typeof import('./app-primitives')>('./app-primitives')
  return {
    ...actual,
    AppModal: ({ isOpen, title, children, footer }: any) => {
      if (!isOpen) {
        return null
      }

      return (
        <div>
          <h2>{title}</h2>
          <div>{children}</div>
          <div>{footer}</div>
        </div>
      )
    },
    AppButton: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
      <button type={props.type || 'button'} {...props}>{children}</button>
    ),
    AppIcon: ({ name, ...props }: any) => <span data-icon={name} {...props} />,
  }
})

describe('ValidationDiagnosticsModal', () => {
  it('shows compiler metadata and diagnostic codes when validation returns compiler output', () => {
    render(
      <ValidationDiagnosticsModal
        isOpen
        ruleName="Customer email format"
        onClose={vi.fn()}
        result={{
          valid: false,
          compiledExpression: "customer_email RLIKE '^[^@]+@[^@]+\\.[^@]+$'",
          artifactKey: 'artifact.rule-1.v2.abc123',
          compilerVersion: 'dq-1.4.0',
          target: 'dsl',
          intermediateModel: {
            schemaVersion: '1.1.0',
            executionContract: {
              engineTarget: 'dq-engine',
            },
          },
          summary: { errors: 1, warnings: 1 },
          diagnostics: [
            {
              scope: 'rule',
              severity: 'error',
              code: 'DQ7_UNSUPPORTED_FUNCTION',
              message: 'Function UPPER is not supported by the current compiler target.',
            },
            {
              scope: 'rule',
              severity: 'warning',
              code: 'DQ7_ALIAS_INFERRED',
              message: 'Alias customer_email was inferred from the compiled expression.',
            },
          ],
        }}
      />,
    )

    expect(screen.getByText('Compiler Metadata')).toBeTruthy()
    expect(screen.getByText('artifact.rule-1.v2.abc123')).toBeTruthy()
    expect(screen.getByText('dq-1.4.0')).toBeTruthy()
    expect(screen.getByText('dq-engine')).toBeTruthy()
    expect(screen.getByText('DQ7_UNSUPPORTED_FUNCTION')).toBeTruthy()
    expect(screen.getByText('DQ7_ALIAS_INFERRED')).toBeTruthy()
    expect(screen.getByText('Function UPPER is not supported by the current compiler target.')).toBeTruthy()
  })
})