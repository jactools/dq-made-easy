/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { TemplatesSelectorModal } from './Templates'
import { CheckTypeForm } from './CheckTypeForm'
import { ThresholdForm } from './CheckTypeForm/ThresholdForm'
import { DAMA_TEMPLATES } from '../types/templates'
import { PerformanceMonitoringProvider } from '../contexts/PerformanceMonitoringContext'
import { DataProductProvider } from '../contexts/DataProductContext'
import { SettingsProvider } from '../contexts/SettingsContext'
import { AuthProvider } from '../contexts/AuthContext'
import { mockButtonModule } from './test-support/appOwnedUiTestMocks'

vi.mock('./Button', () => mockButtonModule())

const baseAttributeOptions = [
  {
    id: 'attr-1',
    name: 'customer_name',
    dataObjectName: 'customers',
    versionId: 'ver-1',
    dataObjectVersion: '1',
  },
]

const getTemplate = (templateId: string) => {
  const template = DAMA_TEMPLATES.find((item) => item.id === templateId)

  if (!template) {
    throw new Error(`Expected template ${templateId} to exist`)
  }

  return template
}

const getEnabledContinueButton = () => {
  const continueButtons = screen.getAllByText('Continue to Summary')
  const enabledContinueButton = continueButtons
    .map((element) => element.closest('button'))
    .find((button): button is HTMLButtonElement => Boolean(button && !button.disabled))

  if (!enabledContinueButton) {
    throw new Error('Expected an enabled Continue to Summary button')
  }

  return enabledContinueButton
}

const renderWithProviders = (ui: React.ReactNode) => {
  return render(
    <PerformanceMonitoringProvider>
      <SettingsProvider>
        <AuthProvider>
          <DataProductProvider>{ui}</DataProductProvider>
        </AuthProvider>
      </SettingsProvider>
    </PerformanceMonitoringProvider>,
  )
}

const createJsonResponse = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

const createValidCheckTypeValidationResult = async () => ({
  valid: true,
  message: null,
  fieldErrors: {},
  normalizedCheckTypeParams: null,
})

const renderTemplatesSelectorModal = (
  props: Partial<React.ComponentProps<typeof TemplatesSelectorModal>>,
  validateCheckTypeDraft: React.ComponentProps<typeof TemplatesSelectorModal>['validateCheckTypeDraft'] =
    vi.fn(createValidCheckTypeValidationResult),
) => renderWithProviders(
  <TemplatesSelectorModal
    isOpen={true}
    onClose={() => undefined}
    onSelectTemplate={vi.fn(async () => ({ ok: true }))}
    validateCheckTypeDraft={validateCheckTypeDraft}
    existingRuleNames={[]}
    {...props}
  />,
)

beforeEach(() => {
  localStorage.setItem('authToken', 'test-token')
  localStorage.setItem(
    'authState',
    JSON.stringify({
      user: {
        id: 'user-1',
        email: 'tester@example.com',
        name: 'Test User',
        workspaceRoles: [
          {
            workspaceId: 'default',
            role: 'analyst',
            joinedAt: '2025-01-01T00:00:00.000Z',
          },
        ],
        createdAt: '2025-01-01T00:00:00.000Z',
        isActive: true,
      },
      currentWorkspaceId: 'default',
      isAuthenticated: true,
      isLoading: false,
      error: null,
    }),
  )
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)

      if (url.includes('/attribute-rule-counts')) {
        return createJsonResponse({})
      }

      if (url.includes('/data-catalog/v1/data-sets?standalone=true')) {
        return createJsonResponse({ data: [] })
      }

      if (url.includes('/data-catalog/v1/data-products')) {
        return createJsonResponse({
          data: [
            {
              id: 'prod-1',
              name: 'Retail Banking',
              workspace_id: 'default',
            },
          ],
        })
      }

      if (url.includes('/data-catalog/v1/suggestions/dq7-dsl-assistant')) {
        return createJsonResponse({
          success: true,
          check_type: 'PRESENT',
          construct_family: 'row_assertion',
          capability_summary: 'Row-level predicate checks over one or more selected attributes.',
          compiler_hint: 'Current implemented runtime: GX predicate lowering with fail-fast validation.',
          support: [
            {
              engine: 'GX',
              support: 'native',
              supported_subsets: ['present checks', 'row predicates'],
              compiler_behavior: 'Native predicate lowering',
              notes: 'Implemented through the GX lowerer for supported row predicates and evidence policy.',
            },
          ],
        })
      }

      if (url.includes('/data-catalog/v1/data-sets?productId=prod-1')) {
        return createJsonResponse({
          data: [
            {
              id: 'ds-1',
              product_id: 'prod-1',
              name: 'Customer 360',
              workspace_id: 'default',
            },
          ],
        })
      }

      if (url.includes('/data-catalog/v1/data-objects-catalog?dataSetId=ds-1')) {
        return createJsonResponse({
          data: [
            {
              id: 'obj-1',
              dataset_id: 'ds-1',
              name: 'customers',
              latest_version_id: 'ver-1',
            },
          ],
        })
      }

      if (url.includes('/data-catalog/v1/data-object-versions?objectId=obj-1')) {
        return createJsonResponse({
          data: [
            {
              id: 'ver-1',
              data_object_id: 'obj-1',
              version: '1',
              created_at: '2025-01-01T00:00:00Z',
            },
          ],
        })
      }

      if (url.includes('/data-deliveries')) {
        return createJsonResponse({ data: [] })
      }

      if (url.includes('/data-catalog/v1/attributes-catalog?versionId=ver-1')) {
        return createJsonResponse({
          data: [
            {
              id: 'attr-1',
              version_id: 'ver-1',
              name: 'customer_id',
              type: 'integer',
              nullable: false,
            },
          ],
        })
      }

      return createJsonResponse({ data: [] })
    }),
  )
})

afterEach(() => {
  cleanup()
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('TemplatesSelectorModal Join Consistency flow', () => {
  it('renders completeness template without entering a render loop', async () => {
    const completenessTemplate = DAMA_TEMPLATES.find((item) => item.id === 'template-completeness-1')

    if (!completenessTemplate) {
      throw new Error('Expected completeness template to exist')
    }

    renderTemplatesSelectorModal({
      initialTemplate: completenessTemplate,
      attributeOptions: [
        {
          id: 'attr-1',
          name: 'customer_id',
          dataObjectName: 'orders',
          versionId: 'dov-orders-v1',
          dataObjectVersion: '1',
        },
      ],
    })

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Step 3 of 4: Configure Rule' })).toBeTruthy()
      expect(screen.getByDisplayValue(completenessTemplate.name)).toBeTruthy()
    })
  })

  it('allows Step 3 attributes to be selected from the data catalog browser', async () => {
    const user = userEvent.setup()
    const completenessTemplate = DAMA_TEMPLATES.find((item) => item.id === 'template-completeness-1')

    if (!completenessTemplate) {
      throw new Error('Expected completeness template to exist')
    }

    renderTemplatesSelectorModal({
      initialTemplate: completenessTemplate,
      attributeOptions: [
        {
          id: 'attr-1',
          name: 'customer_id',
          dataObjectName: 'customers',
          versionId: 'ver-1',
          dataObjectVersion: '1',
        },
      ],
    })

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: 'Browse Data Catalog' }).length).toBeGreaterThan(0)
    })

    await user.click(screen.getAllByRole('button', { name: 'Browse Data Catalog' })[0])

    await waitFor(() => {
      expect(screen.getByText('Select Attributes From Data Catalog')).toBeTruthy()
    })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Retail Banking/i })).toBeTruthy()
    })

    await user.click(screen.getByRole('button', { name: /Retail Banking/i }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Customer 360/i })).toBeTruthy()
    })

    await user.click(screen.getByRole('button', { name: /Customer 360/i }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /customers/i })).toBeTruthy()
    })

    await user.click(screen.getByRole('button', { name: /customers/i }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /v1/i })).toBeTruthy()
    })

    await user.click(screen.getByRole('button', { name: /v1/i }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /customer_id/i })).toBeTruthy()
    })

    await user.click(screen.getByRole('button', { name: /customer_id/i }))
    await waitFor(() => {
      const applyButton = screen.getByRole('button', { name: 'Apply Selection' }) as HTMLButtonElement
      expect(applyButton.disabled).toBe(false)
    })

    await user.click(screen.getByRole('button', { name: 'Apply Selection' }))

    await waitFor(() => {
      expect(screen.queryByText('Select Attributes From Data Catalog')).toBeNull()
      const continueButtons = screen.getAllByText('Continue to Summary')
      const enabledContinueButton = continueButtons
        .map((element) => element.closest('button'))
        .find((button): button is HTMLButtonElement => Boolean(button && !button.disabled))
      expect(Boolean(enabledContinueButton)).toBe(true)
    })
  })

  it('shows the resolved attribute name in the review summary', async () => {
    const user = userEvent.setup()
    const completenessTemplate = DAMA_TEMPLATES.find((item) => item.id === 'template-completeness-1')

    if (!completenessTemplate) {
      throw new Error('Expected completeness template to exist')
    }

    renderTemplatesSelectorModal({
      initialTemplate: completenessTemplate,
      initialCustomizations: {
        name: 'Review summary attribute name',
        description: 'Checks summary display.',
        riskLevel: 'medium',
        attributeIds: ['attr-1'],
        checkType: 'THRESHOLD',
        checkTypeParams: {
          checkType: 'THRESHOLD',
          attribute: 'customer_name',
          metric: 'null_pct',
          operator: 'gte',
          threshold: 95,
        },
      },
      attributeOptions: baseAttributeOptions,
    })

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Step 3 of 4: Configure Rule' })).toBeTruthy()
    })

    await user.click(getEnabledContinueButton())

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Step 4 of 4: Review & Confirm Create' })).toBeTruthy()
      expect(screen.getByText(/customer_name \(customers\) - v1/)).toBeTruthy()
      expect(screen.queryByText('attr-1')).toBeNull()
    })
  })

  it('shows zero-only aggregate semantics in the review summary', async () => {
    const user = userEvent.setup()
    const completenessTemplate = DAMA_TEMPLATES.find((item) => item.id === 'template-completeness-1')

    if (!completenessTemplate) {
      throw new Error('Expected completeness template to exist')
    }

    renderTemplatesSelectorModal({
      initialTemplate: completenessTemplate,
      initialCustomizations: {
        name: 'Duplicate count summary',
        description: 'Checks summary display.',
        riskLevel: 'medium',
        attributeIds: ['attr-1'],
        checkType: 'THRESHOLD',
        checkTypeParams: {
          checkType: 'THRESHOLD',
          attribute: 'customer_name',
          metric: 'duplicate_count',
          operator: 'lte',
          threshold: 0,
        },
      },
      attributeOptions: baseAttributeOptions,
    })

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Step 3 of 4: Configure Rule' })).toBeTruthy()
    })

    await user.click(getEnabledContinueButton())

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Step 4 of 4: Review & Confirm Create' })).toBeTruthy()
      expect(screen.getByText(/Checks duplicate rows for each selected attribute\./)).toBeTruthy()
      expect(screen.getByText(/Requires duplicate rows to stay at 0\./)).toBeTruthy()
      expect(screen.getByText(/Current runtime lowers this to uniqueness semantics\./)).toBeTruthy()
    })
  })

  it.each([
    {
      metric: 'missing_count' as const,
      label: 'Threshold (count)',
      step: '1',
      hint: /missing rows.*only supports 0/i,
    },
    {
      metric: 'duplicate_percent' as const,
      label: 'Threshold (%)',
      step: '0.01',
      hint: /duplicate rate.*only supports 0%/i,
    },
  ])('supports zero-only aggregate threshold metric $metric in the threshold form', async ({ metric, label, step, hint }) => {
    renderWithProviders(
      <ThresholdForm
        params={{
          checkType: 'THRESHOLD',
          attribute: 'amount',
          metric,
          operator: 'lte',
          threshold: 0,
        }}
        catalogAttributeName="amount"
        onChange={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('Missing rows')).toBeTruthy()
      expect(screen.getByText('Duplicate rows')).toBeTruthy()
      expect(screen.getByText('Duplicate rate')).toBeTruthy()
      expect(screen.getByLabelText('Condition').getAttribute('aria-disabled')).toBe('true')
    })

    const thresholdInput = screen.getByLabelText(label) as HTMLInputElement
    expect(thresholdInput.min).toBe('0')
    expect(thresholdInput.max).toBe('0')
    expect(thresholdInput.step).toBe(step)
    expect(thresholdInput.value).toBe('0')
    expect(screen.getByText(hint)).toBeTruthy()
  })

  it('renders the row count check type form and emits row count params', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <CheckTypeForm
        checkType="ROW_COUNT"
        params={{ checkType: 'ROW_COUNT', operator: 'gte', threshold: 500 }}
        onChange={onChange}
      />,
    )

    expect(screen.getByLabelText('Row count')).toBeTruthy()

    const thresholdInput = screen.getByLabelText('Row count') as HTMLInputElement
    fireEvent.change(thresholdInput, { target: { value: '750' } })

    await waitFor(() => {
      expect(onChange).toHaveBeenCalled()
    })

    const lastCall = onChange.mock.calls.at(-1)?.[0]
    expect(lastCall).toMatchObject({
      checkType: 'ROW_COUNT',
      operator: 'gte',
      threshold: 750,
    })
  })

  it('supports raw aggregate threshold metrics in the threshold form', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    renderWithProviders(
      <ThresholdForm
        params={{
          checkType: 'THRESHOLD',
          attribute: 'amount',
          metric: 'avg',
          operator: 'lte',
          threshold: 250.5,
        }}
        catalogAttributeName="amount"
        onChange={onChange}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('Minimum')).toBeTruthy()
      expect(screen.getByText('Maximum')).toBeTruthy()
      expect(screen.getByText('Average')).toBeTruthy()
      expect(screen.getByText('Sum')).toBeTruthy()
      expect(screen.getByText('Standard deviation')).toBeTruthy()
      expect(screen.getByText('Distinct count')).toBeTruthy()
    })

    const thresholdInput = screen.getByLabelText('Threshold (value)') as HTMLInputElement
    expect(thresholdInput.max).toBe('')

    fireEvent.change(thresholdInput, { target: { value: '321.5' } })

    await waitFor(() => {
      expect(onChange).toHaveBeenCalled()
    })

    expect(onChange.mock.calls.at(-1)?.[0]).toMatchObject({
      checkType: 'THRESHOLD',
      attribute: 'amount',
      metric: 'avg',
      operator: 'lte',
      threshold: 321.5,
    })
  })

  it('shows inline join consistency field errors when continuing with invalid required mappings', async () => {
    const user = userEvent.setup()
    const consistencyTemplate = DAMA_TEMPLATES.find((item) => item.id === 'template-consistency-1')

    if (!consistencyTemplate) {
      throw new Error('Expected consistency template to exist')
    }

    const validateCheckTypeDraft = vi.fn(async () => ({
      valid: false,
      message: 'Complete all required Join Consistency fields before continuing.',
      fieldErrors: {
        leftDataObjectVersionId: 'Select a left data object version.',
        rightDataObjectVersionId: 'Select a right data object version.',
        joinKeys: 'Add at least one join key mapping.',
        comparisons: 'Add at least one comparison mapping.',
        actualityLeftAttribute: 'Select a left actuality-date attribute.',
        actualityRightAttribute: 'Select a right actuality-date attribute.',
        contractId: 'Provide a delivery contract ID.',
      },
      normalizedCheckTypeParams: null,
    }))

    renderTemplatesSelectorModal({
      initialTemplate: consistencyTemplate,
      initialCustomizations: {
        name: 'Join consistency wizard validation',
        description: 'Test payload',
        riskLevel: 'medium',
        attributeIds: ['attr-1'],
        checkType: 'JOIN_CONSISTENCY',
        checkTypeParams: {
          checkType: 'JOIN_CONSISTENCY',
          leftDataObjectVersionId: '',
          rightDataObjectVersionId: '',
          joinKeys: [],
          comparisons: [],
          actualityDate: {
            leftAttribute: '',
            rightAttribute: '',
            toleranceSource: 'DELIVERY_CONTRACT',
            contractId: '',
          },
          minMatchRate: 95,
        },
      },
      attributeOptions: [
        {
          id: 'attr-1',
          name: 'customer_id',
          dataObjectName: 'orders',
          versionId: 'dov-orders-v1',
          dataObjectVersion: '1',
        },
      ],
    }, validateCheckTypeDraft)

    await waitFor(() => {
      expect(screen.getAllByText('Step 3 of 4: Configure Rule').length).toBeGreaterThan(0)
    })

    const continueButtons = screen.getAllByText('Continue to Summary')
    const enabledContinueButton = continueButtons
      .map((element) => element.closest('button'))
      .find((button): button is HTMLButtonElement => Boolean(button && !button.disabled))

    if (!enabledContinueButton) {
      throw new Error('Expected an enabled Continue to Summary button')
    }

    await user.click(enabledContinueButton)

    await waitFor(() => {
      expect(
        screen.getByText('Complete all required Join Consistency fields before continuing.'),
      ).toBeTruthy()
      expect(screen.getByText('Select a left data object version.')).toBeTruthy()
      expect(screen.getByText('Select a right data object version.')).toBeTruthy()
      expect(screen.getByText('Add at least one join key mapping.')).toBeTruthy()
      expect(screen.getByText('Add at least one comparison mapping.')).toBeTruthy()
      expect(screen.getByText('Select a left actuality-date attribute.')).toBeTruthy()
      expect(screen.getByText('Select a right actuality-date attribute.')).toBeTruthy()
      expect(screen.getByText('Provide a delivery contract ID.')).toBeTruthy()
    })
  })
})

describe('TemplatesSelectorModal extended check type flow', () => {
  it('shows inline range field errors when no bounds are provided', async () => {
    const user = userEvent.setup()

    const validateCheckTypeDraft = vi.fn(async () => ({
      valid: false,
      message: 'Range check requires at least a minimum or maximum value.',
      fieldErrors: {
        minValue: 'Provide at least one range boundary.',
        maxValue: 'Provide at least one range boundary.',
      },
      normalizedCheckTypeParams: null,
    }))

    renderTemplatesSelectorModal({
      initialTemplate: getTemplate('template-validity-1'),
      initialCustomizations: {
        name: 'Range bounds required',
        description: 'Checks range validation.',
        riskLevel: 'medium',
        attributeIds: ['attr-1'],
        checkType: 'RANGE',
        checkTypeParams: {
          checkType: 'RANGE',
          attribute: 'customer_name',
          inclusive: true,
        },
      },
      attributeOptions: baseAttributeOptions,
    }, validateCheckTypeDraft)

    await waitFor(() => {
      expect(screen.getByLabelText('Minimum value (optional)')).toBeTruthy()
      expect(screen.getByLabelText('Maximum value (optional)')).toBeTruthy()
    })

    await user.click(getEnabledContinueButton())

    await waitFor(() => {
      expect(screen.getByText('Range check requires at least a minimum or maximum value.')).toBeTruthy()
      expect(screen.getAllByText('Provide at least one range boundary.').length).toBe(2)
      expect(screen.getByRole('heading', { name: 'Step 3 of 4: Configure Rule' })).toBeTruthy()
    })
  })

  it('builds a PRESENT manual override preview from the configured form values', async () => {
    const user = userEvent.setup()

    renderTemplatesSelectorModal({
      initialTemplate: getTemplate('template-completeness-1'),
      initialCustomizations: {
        name: 'Present customer name',
        description: 'Checks customer names are populated.',
        riskLevel: 'medium',
        attributeIds: ['attr-1'],
        checkType: 'PRESENT',
        checkTypeParams: {
          checkType: 'PRESENT',
          attribute: 'customer_name',
          blockedValues: ['UNKNOWN'],
          caseSensitive: false,
        },
      },
      attributeOptions: baseAttributeOptions,
    })

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Step 3 of 4: Configure Rule' })).toBeTruthy()
      expect(screen.getAllByRole('button', { name: 'Browse Data Catalog' }).length).toBeGreaterThan(0)
    })

    const placeholderValues = screen.getByLabelText('Placeholder values (optional)') as HTMLTextAreaElement
    fireEvent.change(placeholderValues, { target: { value: 'UNKNOWN, N/A' } })

    await user.click(screen.getByLabelText('Use manual expression override (advanced)'))

    await waitFor(() => {
      const expressionInput = screen.getByPlaceholderText('Enter custom expression') as HTMLTextAreaElement
      expect(expressionInput.value).toContain("customer_name IS NOT NULL")
      expect(expressionInput.value).toContain("TRIM(customer_name) != ''")
      expect(expressionInput.value).toContain("LOWER(TRIM(customer_name)) NOT IN")
      expect(expressionInput.value).toContain("unknown")
      expect(expressionInput.value).toContain("n/a")
    })

    await waitFor(() => {
      expect(screen.getByRole('complementary', { name: 'Read-only assistant' })).toBeTruthy()
      expect(screen.getByText('row_assertion')).toBeTruthy()
      expect(screen.getByText(/Row-level predicate checks over one or more selected attributes/)).toBeTruthy()
      expect(screen.getByText(/GX:/)).toBeTruthy()
      expect(screen.getByText(/Implemented through the GX lowerer for supported row predicates and evidence policy/)).toBeTruthy()
      expect(screen.getByText(/Draft payload preview:/)).toBeTruthy()
      expect(screen.getByText(/"ai_output": true/)).toBeTruthy()
      expect(screen.getByText(/"checkType": "PRESENT"/)).toBeTruthy()
    })

    await user.click(getEnabledContinueButton())

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Step 4 of 4: Review & Confirm Create' })).toBeTruthy()
      expect(screen.getByText(/Selected check type:/)).toBeTruthy()
      expect(screen.getByText(/Checks 'customer_name' is populated with non-blank values\./)).toBeTruthy()
      expect(screen.getByText(/Treats 2 placeholder value\(s\) as missing\./)).toBeTruthy()
      expect(screen.getByText(/Comparison mode: case-insensitive\./)).toBeTruthy()
      expect(screen.getByText(/customer_name IS NOT NULL AND TRIM\(customer_name\) != '' AND LOWER\(TRIM\(customer_name\)\) NOT IN \('unknown', 'n\/a'\)/)).toBeTruthy()
    })
  })

  it('keeps assistant output out of the submitted rule customizations', async () => {
    const user = userEvent.setup()
    const onSelectTemplate = vi.fn(async () => ({ ok: true }))

    renderTemplatesSelectorModal({
      initialTemplate: getTemplate('template-completeness-1'),
      initialCustomizations: {
        name: 'Present customer name',
        description: 'Checks customer names are populated.',
        riskLevel: 'medium',
        attributeIds: ['attr-1'],
        checkType: 'PRESENT',
        checkTypeParams: {
          checkType: 'PRESENT',
          attribute: 'customer_name',
          blockedValues: ['UNKNOWN'],
          caseSensitive: false,
        },
      },
      attributeOptions: baseAttributeOptions,
      onSelectTemplate,
    })

    await waitFor(() => {
      expect(screen.getByRole('complementary', { name: 'Read-only assistant' })).toBeTruthy()
      expect(screen.getByText(/"ai_output": true/)).toBeTruthy()
      expect(screen.getByText('row_assertion')).toBeTruthy()
    })

    await user.click(getEnabledContinueButton())

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Step 4 of 4: Review & Confirm Create' })).toBeTruthy()
    })

    await user.click(screen.getByRole('button', { name: 'Confirm & Create Rule' }))

    await waitFor(() => {
      expect(onSelectTemplate).toHaveBeenCalledTimes(1)
    })

    const customizations = (
      onSelectTemplate.mock.calls as unknown as Array<[unknown, Record<string, unknown>]>
    )[0][1]
    expect(customizations).not.toHaveProperty('ai_output')
    expect(customizations).not.toHaveProperty('aiOutput')
    expect(customizations).not.toHaveProperty('capabilitySummary')
    expect(customizations).not.toHaveProperty('support')
    expect(customizations.templateInputs).not.toHaveProperty('ai_output')
    expect(customizations.templateInputs).not.toHaveProperty('aiOutput')
  })

  it('fails fast when the assistant suggestions service is unavailable', async () => {
    const defaultFetch = global.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)

        if (url.includes('/data-catalog/v1/suggestions/dq7-dsl-assistant')) {
          return new Response(
            JSON.stringify({
              error: 'suggestions_service_unavailable',
              message: 'Suggestions service is unavailable.',
              status: 503,
            }),
            {
              status: 503,
              headers: { 'Content-Type': 'application/json' },
            },
          )
        }

        return defaultFetch(input, init)
      }),
    )

    renderTemplatesSelectorModal({
      initialTemplate: getTemplate('template-completeness-1'),
      initialCustomizations: {
        name: 'Present customer name',
        description: 'Checks customer names are populated.',
        riskLevel: 'medium',
        attributeIds: ['attr-1'],
        checkType: 'PRESENT',
        checkTypeParams: {
          checkType: 'PRESENT',
          attribute: 'customer_name',
          blockedValues: ['UNKNOWN'],
          caseSensitive: false,
        },
      },
      attributeOptions: baseAttributeOptions,
    })

    await waitFor(() => {
      expect(screen.getByRole('complementary', { name: 'Read-only assistant' })).toBeTruthy()
      expect(screen.getByText('Suggestions service is unavailable.')).toBeTruthy()
      expect(screen.queryByText('row_assertion')).toBeNull()
      expect(screen.queryByText(/Implemented through the GX lowerer for supported row predicates and evidence policy/)).toBeNull()
      expect(screen.getByText(/"ai_output": true/)).toBeTruthy()
    })
  })

  it('blocks CORRECT numeric tolerance mode when the wizard does not have a tolerance value', async () => {
    const user = userEvent.setup()

    const validateCorrectDraft = vi.fn(async () => ({
      valid: false,
      message: 'Correct check requires a numeric tolerance when using numeric_tolerance mode.',
      fieldErrors: {
        comparisonTolerance: 'Provide a numeric tolerance for numeric_tolerance mode.',
      },
      normalizedCheckTypeParams: null,
    }))

    renderTemplatesSelectorModal({
      initialTemplate: getTemplate('template-completeness-1'),
      initialCustomizations: {
        name: 'Correct price check',
        description: 'Checks source prices against reference prices.',
        riskLevel: 'high',
        attributeIds: ['attr-1'],
        checkType: 'CORRECT',
        checkTypeParams: {
          checkType: 'CORRECT',
          sourceDataObjectVersionId: 'prices-v1',
          referenceDataObjectVersionId: 'exchange-v2',
          joinKeys: [{ leftAttribute: 'trade_id', rightAttribute: 'trade_id' }],
          comparison: {
            leftAttribute: 'closing_price',
            rightAttribute: 'reference_price',
            mode: 'numeric_tolerance',
          },
        },
      },
      attributeOptions: baseAttributeOptions,
    }, validateCorrectDraft)

    await waitFor(() => {
      expect(screen.getByLabelText('Tolerance (numeric mode only)')).toBeTruthy()
    })

    await user.click(getEnabledContinueButton())

    await waitFor(() => {
      expect(screen.getByText('Correct check requires a numeric tolerance when using numeric_tolerance mode.')).toBeTruthy()
      expect(screen.getByText('Provide a numeric tolerance for numeric_tolerance mode.')).toBeTruthy()
      expect(screen.getByRole('heading', { name: 'Step 3 of 4: Configure Rule' })).toBeTruthy()
    })
  })

  it('renders TRANSFER_MATCH payload hash details in the summary after editing the form', async () => {
    const user = userEvent.setup()

    renderTemplatesSelectorModal({
      initialTemplate: getTemplate('template-consistency-1'),
      initialCustomizations: {
        name: 'Transfer match payload hash',
        description: 'Checks landing and warehouse payload hashes match.',
        riskLevel: 'medium',
        attributeIds: ['attr-1'],
        checkType: 'TRANSFER_MATCH',
        checkTypeParams: {
          checkType: 'TRANSFER_MATCH',
          mode: 'payload_hash_match',
          leftDataObjectVersionId: 'landing-v1',
          rightDataObjectVersionId: 'warehouse-v2',
          joinKeys: [{ leftAttribute: 'file_name', rightAttribute: 'file_name' }],
          leftHashAttribute: 'payload_hash',
          rightHashAttribute: 'target_payload_hash',
        },
      },
      attributeOptions: baseAttributeOptions,
    })

    await waitFor(() => {
      expect(screen.getByLabelText('Left hash attribute')).toBeTruthy()
      expect(screen.getByLabelText('Right hash attribute')).toBeTruthy()
    })

    const rightHashAttribute = screen.getByLabelText('Right hash attribute') as HTMLInputElement
    await user.clear(rightHashAttribute)
    await user.type(rightHashAttribute, 'target_payload_hash_v2')

    await user.click(getEnabledContinueButton())

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Step 4 of 4: Review & Confirm Create' })).toBeTruthy()
      expect(screen.getByText(/Selected check type:/)).toBeTruthy()
      expect(screen.getByText(/Checks transfer alignment between 'landing-v1' and 'warehouse-v2'\./)).toBeTruthy()
      expect(screen.getByText(/Join key mappings: 1\./)).toBeTruthy()
      expect(screen.getByText(/Payload hash attributes: payload_hash -> target_payload_hash_v2\./)).toBeTruthy()
    })
  })
})
