/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OnboardingRuleReview, type OnboardingReviewResponse } from './OnboardingRuleReview'

vi.mock('./app-primitives', () => ({
  AppModal: ({ isOpen, title, children, footer }: any) =>
    isOpen ? (
      <div role="dialog" aria-label={title}>
        <h2>{title}</h2>
        {children}
        {footer}
      </div>
    ) : null,
  AppButton: ({ children, onClick, disabled }: any) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  AppInput: ({ label, value, onChange, id, placeholder }: any) => (
    <label>
      <span>{label}</span>
      <input id={id} value={value} onChange={onChange} placeholder={placeholder} />
    </label>
  ),
  AppSelect: ({ label, value, onChange, options, id }: any) => (
    <label>
      <span>{label}</span>
      <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option: { value: string; label: string }) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  ),
  AppStack: ({ children }: any) => <div>{children}</div>,
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const baseResponse: OnboardingReviewResponse = {
  scopeType: 'workspace',
  scopeId: 'ws-1',
  totalAttributes: 4,
  totalProposals: 7,
  generatedAt: '2026-05-31T12:00:00Z',
  proposals: [
    {
      templateId: 'template-completeness-1',
      templateName: 'NULL Value Check',
      dimension: 'completeness',
      checkType: 'THRESHOLD',
      totalCount: 4,
      byDataset: {
        'dataset-1': [
          {
            dataObjectVersionId: 'objv-1',
            objectName: 'customer',
            datasetName: 'customer_data',
            count: 2,
            attributes: [
              {
                attributeId: 'attr-1',
                name: 'customer_id',
                dataType: 'string',
                alreadyCovered: false,
              },
              {
                attributeId: 'attr-2',
                name: 'email',
                dataType: 'string',
                alreadyCovered: true,
              },
            ],
          },
        ],
        'dataset-2': [
          {
            dataObjectVersionId: 'objv-2',
            objectName: 'order',
            datasetName: 'order_data',
            count: 1,
            attributes: [
              {
                attributeId: 'attr-3',
                name: 'order_id',
                dataType: 'string',
                alreadyCovered: false,
              },
            ],
          },
        ],
      },
    },
    {
      templateId: 'template-validity-1',
      templateName: 'Range Check',
      dimension: 'validity',
      checkType: 'RANGE',
      totalCount: 1,
      byDataset: {
        'dataset-1': [
          {
            dataObjectVersionId: 'objv-1',
            objectName: 'customer',
            datasetName: 'customer_data',
            count: 1,
            attributes: [
              {
                attributeId: 'attr-4',
                name: 'age',
                dataType: 'numeric',
                alreadyCovered: false,
              },
            ],
          },
        ],
      },
    },
  ],
}

const renderReview = (overrides: Partial<React.ComponentProps<typeof OnboardingRuleReview>> = {}) => {
  const props: React.ComponentProps<typeof OnboardingRuleReview> = {
    isOpen: true,
    response: baseResponse,
    onClose: vi.fn(),
    onCreateDraftRules: vi.fn(),
    ...overrides,
  }

  return render(<OnboardingRuleReview {...props} />)
}

const expandFirstTreePath = () => {
  fireEvent.click(screen.getAllByLabelText('Expand template group')[0])
  fireEvent.click(screen.getAllByLabelText('Expand dataset group')[0])
  fireEvent.click(screen.getAllByLabelText('Expand object group')[0])
}

describe('OnboardingRuleReview', () => {
  it('renders filter bar and summary', () => {
    renderReview()

    expect(screen.getByText('Review Suggested Rules')).toBeTruthy()
    expect(screen.getByText('Dimension')).toBeTruthy()
    expect(screen.getByText('Template')).toBeTruthy()
    expect(screen.getByText('Dataset Search')).toBeTruthy()
    expect(screen.getByTestId('onboarding-review-summary')).toBeTruthy()
  })

  it('shows already covered count and default selected count', () => {
    renderReview()

    expect(screen.getByText('1 already covered')).toBeTruthy()
    expect(screen.getByText('3 rules selected')).toBeTruthy()
  })

  it('expands template and dataset and object groups', async () => {
    renderReview()

    expandFirstTreePath()

    await waitFor(() => {
      expect(screen.getByText('customer_id')).toBeTruthy()
      expect(screen.getByText('email')).toBeTruthy()
    })
  })

  it('renders already covered attributes as disabled with badge', async () => {
    renderReview()

    expandFirstTreePath()

    await waitFor(() => {
      const checkbox = screen.getByLabelText('Select attribute email') as HTMLInputElement
      expect(checkbox.disabled).toBe(true)
      expect(screen.getByText('already covered')).toBeTruthy()
    })
  })

  it('supports bulk deselect/select on template level', async () => {
    renderReview()

    fireEvent.click(screen.getAllByLabelText('Expand template group')[0])
    const templateCheckbox = screen.getByLabelText('Select template NULL Value Check') as HTMLInputElement

    fireEvent.click(templateCheckbox)

    await waitFor(() => {
      expect(screen.getByText('1 rules selected')).toBeTruthy()
    })

    fireEvent.click(templateCheckbox)

    await waitFor(() => {
      expect(screen.getByText('3 rules selected')).toBeTruthy()
    })
  })

  it('applies status filter for already covered', async () => {
    renderReview()

    fireEvent.change(screen.getByLabelText('Status') as HTMLSelectElement, {
      target: { value: 'already-covered' },
    })

    expandFirstTreePath()

    await waitFor(() => {
      expect(screen.getByText('email')).toBeTruthy()
      expect(screen.queryByText('customer_id')).toBeNull()
    })
  })

  it('applies dataset search filter', async () => {
    renderReview()

    fireEvent.change(screen.getByPlaceholderText('Search dataset'), {
      target: { value: 'order' },
    })

    fireEvent.click(screen.getAllByLabelText('Expand template group')[0])
    fireEvent.click(screen.getAllByLabelText('Expand dataset group')[0])
    fireEvent.click(screen.getAllByLabelText('Expand object group')[0])

    await waitFor(() => {
      expect(screen.getByText('order_id')).toBeTruthy()
      expect(screen.queryByText('customer_id')).toBeNull()
    })
  })

  it('calls onCreateDraftRules with selected ids', () => {
    const onCreateDraftRules = vi.fn()
    renderReview({ onCreateDraftRules })

    fireEvent.click(screen.getByRole('button', { name: 'Create 3 draft rules' }))

    expect(onCreateDraftRules).toHaveBeenCalledTimes(1)
    const selected = onCreateDraftRules.mock.calls[0][0]
    expect(Array.isArray(selected)).toBe(true)
    expect(selected).toHaveLength(3)
  })

  it('invokes lazy-load callback when opening large object groups', async () => {
    const onRequestObjectAttributes = vi.fn().mockResolvedValue(undefined)

    renderReview({
      onRequestObjectAttributes,
      response: {
        ...baseResponse,
        proposals: [
          {
            ...baseResponse.proposals[0],
            byDataset: {
              'dataset-1': [
                {
                  ...baseResponse.proposals[0].byDataset['dataset-1'][0],
                  count: 60,
                  attributes: [
                    {
                      attributeId: 'attr-1',
                      name: 'customer_id',
                      dataType: 'string',
                      alreadyCovered: false,
                    },
                  ],
                },
              ],
            },
          },
        ],
      },
    })

    fireEvent.click(screen.getAllByLabelText('Expand template group')[0])
    fireEvent.click(screen.getAllByLabelText('Expand dataset group')[0])
    fireEvent.click(screen.getAllByLabelText('Expand object group')[0])

    await waitFor(() => {
      expect(onRequestObjectAttributes).toHaveBeenCalledWith({
        templateId: 'template-completeness-1',
        datasetId: 'dataset-1',
        dataObjectVersionId: 'objv-1',
      })
    })
  })
})
