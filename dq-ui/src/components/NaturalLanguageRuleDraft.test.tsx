/** @vitest-environment jsdom */

import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { NaturalLanguageRuleDraftPreview } from './NaturalLanguageRuleDraft'
import { mockButtonModule } from './test-support/appOwnedUiTestMocks'

vi.mock('../hooks/useCatalogTerms', () => ({
  useCatalogTerms: (searchQuery = '') => {
    const terms = [
      {
        termKey: 'discount_percent',
        termName: 'Discount Percent',
        description: 'Business term for discount percentage values',
        matchScorePct: 80,
      },
      {
        termKey: 'phone_number',
        termName: 'Phone Number',
        description: 'Business term for customer contact phone numbers',
        matchScorePct: 41,
      },
      {
        termKey: 'customer_id',
        termName: 'Customer ID',
        description: 'Business term for the unique customer identifier',
        matchScorePct: 35,
      },
      {
        termKey: 'email_address',
        termName: 'Email Address',
        description: 'Business term for the customer email address',
        matchScorePct: 31,
      },
    ]

    const stopWords = new Set(['a', 'an', 'and', 'are', 'as', 'at', 'be', 'been', 'being', 'but', 'by', 'can', 'could', 'did', 'do', 'does', 'for', 'from', 'had', 'has', 'have', 'if', 'in', 'into', 'is', 'it', 'must', 'of', 'on', 'or', 'should', 'that', 'the', 'their', 'then', 'there', 'these', 'this', 'to', 'under', 'up', 'was', 'were', 'when', 'where', 'which', 'with', 'within', 'would', 'you', 'your'])

    const normalize = (value: string) => value
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter(Boolean)
      .filter((token) => !stopWords.has(token))
      .join(' ')

    const queryTokens = normalize(searchQuery).split(/\s+/).filter(Boolean)
    const visibleTerms = queryTokens.length === 0
      ? terms
      : terms.filter((term) => {
          const searchable = normalize([term.termName, term.termKey, term.description].filter(Boolean).join(' '))
          return queryTokens.some((token) => searchable.includes(token))
        })

    return {
      terms: visibleTerms,
      loading: false,
      error: null,
      lastSync: null,
      isEnabled: true,
      searchTerms: (query: string) => {
        const normalizedQuery = normalize(query)
        const tokens = normalizedQuery.split(/\s+/).filter(Boolean)
        return terms.filter((term) => {
          if (!normalizedQuery) return true
          const searchable = normalize([term.termName, term.termKey, term.description].filter(Boolean).join(' '))
          return tokens.some((token) => searchable.includes(token))
        })
      },
      refetch: vi.fn(),
    }
  },
}))

vi.mock('./Button', () => mockButtonModule())

let mockRequests: Record<string, any> = {}
const mockTrackNaturalLanguageDraftRequest = vi.fn(() => 'preview-task-1')

vi.mock('../hooks/useAsyncRequests', () => ({
  useAsyncRequests: () => ({
    requests: mockRequests,
    trackNaturalLanguageDraftRequest: mockTrackNaturalLanguageDraftRequest,
  }),
  useTrackedAsyncRequest: () => null,
}))

const buildPreviewResult = () => ({
  success: true as const,
  message: 'Preview generated.',
  preview: {
    targetTerms: ['customer_id'],
    searchScope: 'current' as const,
    requiresStewardConfirmation: true,
    draftRulePreview: {
      name: 'Uniqueness draft for customer_id',
      workspaceId: 'retail-banking',
      dimension: 'Uniqueness',
      summary: 'Select one or more candidate attributes to create a uniqueness draft suggestion.',
      dsl: {
        schemaVersion: '2.0.0' as const,
        rule: {
          kind: 'metric_threshold',
          scope: {
            dataset: {
              dataObjectId: 'object-retail',
            },
          },
          measure: {
            type: 'metric',
            metric: 'duplicate_count',
            subject: {
              columns: ['customer_id'],
            },
          },
          expectation: {
            type: 'threshold',
            operator: 'lte',
            value: 0,
            unit: 'count',
          },
          evidence: {
            failedRows: {
              mode: 'sample',
              limit: 25,
              includeRowIdentifier: true,
              includePrimaryKey: true,
            },
            emitCompiledArtifact: true,
            emitGeneratedSql: false,
          },
          operations: {
            severity: 'critical',
            preferredEngines: ['gx', 'sql'],
            failIfNotNative: false,
          },
        },
      },
    },
    candidateAttributes: [
      {
        attributeId: 'attr-retail-customer-id',
        attributeName: 'customer_id',
        versionId: 'version-retail',
        dataObjectId: 'object-retail',
        dataObjectName: 'customer_master',
        dataSetId: 'dataset-retail',
        dataSetName: 'Retail Core',
        dataProductId: 'product-retail',
        dataProductName: 'Customer',
        workspaceId: 'retail-banking',
        parentPath: ['Customer', 'Retail Core', 'customer_master'],
        confidenceScore: 0.92,
        matchReasons: ['Exact attribute-name match'],
        currentContext: true,
        matchRoles: ['target'],
      },
    ],
  },
})

const buildConditionalPreviewResult = () => ({
  success: true as const,
  message: 'Preview generated.',
  preview: {
    targetTerms: ['email'],
    searchScope: 'current' as const,
    parsedCondition: {
      attributeTerm: 'status',
      operator: 'equals',
      value: 'active',
      sameVersionRequired: true,
    },
    requiresStewardConfirmation: true,
    draftRulePreview: {
      name: 'Format / Regex draft for email',
      workspaceId: 'retail-banking',
      dimension: 'Validity',
      summary: 'Select one target attribute and one condition attribute from the same data object version to create a conditional format / regex draft suggestion.',
      dsl: {
        schemaVersion: '2.0.0' as const,
        rule: {
          kind: 'row_assertion',
          scope: {
            dataset: {
              dataObjectId: 'object-retail',
            },
          },
          measure: {
            type: 'row_predicate',
            predicate: {
              kind: 'row_predicate',
              language: 'dq_predicate',
              expression: "(customer_status = 'active' AND (email_address IS NOT NULL AND TRIM(email_address) != '' AND REGEXP_MATCHES(email_address, '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'))) OR NOT (customer_status = 'active')",
            },
          },
          expectation: {
            type: 'threshold',
            operator: 'gte',
            value: 100,
            unit: 'percent',
          },
          evidence: {
            failedRows: {
              mode: 'sample',
              limit: 25,
              includeRowIdentifier: true,
              includePrimaryKey: true,
            },
            emitCompiledArtifact: true,
            emitGeneratedSql: false,
          },
          operations: {
            severity: 'critical',
            preferredEngines: ['gx', 'sql'],
            failIfNotNative: false,
          },
        },
      },
    },
    candidateAttributes: [
      {
        attributeId: 'attr-retail-status',
        attributeName: 'customer_status',
        versionId: 'version-retail',
        dataObjectId: 'object-retail',
        dataObjectName: 'customer_master',
        dataSetId: 'dataset-retail',
        dataSetName: 'Retail Core',
        dataProductId: 'product-retail',
        dataProductName: 'Customer',
        workspaceId: 'retail-banking',
        parentPath: ['Customer', 'Retail Core', 'customer_master'],
        confidenceScore: 0.88,
        matchReasons: ['Exact attribute-name match'],
        currentContext: true,
        matchRoles: ['condition'],
      },
      {
        attributeId: 'attr-retail-email',
        attributeName: 'email_address',
        versionId: 'version-retail',
        dataObjectId: 'object-retail',
        dataObjectName: 'customer_master',
        dataSetId: 'dataset-retail',
        dataSetName: 'Retail Core',
        dataProductId: 'product-retail',
        dataProductName: 'Customer',
        workspaceId: 'retail-banking',
        parentPath: ['Customer', 'Retail Core', 'customer_master'],
        confidenceScore: 0.94,
        matchReasons: ['Semantic synonym match'],
        currentContext: true,
        matchRoles: ['target'],
      },
    ],
  },
})

afterEach(() => {
  cleanup()
  mockRequests = {}
  vi.clearAllMocks()
})

describe('NaturalLanguageRuleDraftPreview', () => {
  it('does not render for users who cannot create rules', () => {
    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={false}
        currentWorkspaceId="retail-banking"
        accessibleWorkspaceIds={['retail-banking']}
        generatePreview={vi.fn().mockResolvedValue(buildPreviewResult())}
        createDraftSuggestion={vi.fn().mockResolvedValue({ success: true, message: 'Draft suggestion created.' })}
      />,
    )

    expect(screen.queryByRole('heading', { name: /describe a rule draft/i })).toBeNull()
  })

  it('renders the cross-workspace scope option when multiple workspaces are accessible', () => {
    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={true}
        currentWorkspaceId="retail-banking"
        accessibleWorkspaceIds={['retail-banking', 'corporate-banking']}
        generatePreview={vi.fn().mockResolvedValue(buildPreviewResult())}
        createDraftSuggestion={vi.fn().mockResolvedValue({ success: true, message: 'Draft suggestion created.' })}
      />,
    )

    expect(screen.getByRole('heading', { name: /describe a rule draft/i })).toBeTruthy()
    expect(screen.getAllByText(/all across workspaces/i).length).toBeGreaterThan(0)
    expect(screen.getByLabelText(/analysis engine/i)).toBeTruthy()
    expect(screen.getByText(/text you enter here will be stored/i)).toBeTruthy()
  })

  it('lets the steward choose the llm analysis engine', async () => {
    const generatePreview = vi.fn().mockResolvedValue(buildPreviewResult())

    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={true}
        currentWorkspaceId="retail-banking"
        accessibleWorkspaceIds={['retail-banking', 'corporate-banking']}
        generatePreview={generatePreview}
        createDraftSuggestion={vi.fn().mockResolvedValue({ success: true, message: 'Draft suggestion created.' })}
      />,
    )

    fireEvent(
      screen.getByLabelText(/analysis engine/i),
      new CustomEvent('rdsChange', {
        detail: { value: 'llm' },
        bubbles: true,
      }),
    )

    fireEvent.change(screen.getByLabelText(/what rule do you want/i), {
      target: { value: 'I want a uniqueness rule for attribute customer_id' },
    })

    fireEvent.click(screen.getByText(/generate preview/i))

    expect(generatePreview).toHaveBeenCalledWith(expect.objectContaining({ analysisProvider: 'llm' }))
  })

  it('queues llm previews and shows the recent analysis request history', async () => {
    const generatePreview = vi.fn().mockResolvedValue({
      success: true,
      message: 'LLM preview request started.',
      queued: true,
      requestId: 'preview-request-1',
    })

    mockRequests = {
      'preview-task-1': {
        id: 'preview-task-1',
        kind: 'natural-language-draft',
        requestId: 'preview-request-1',
        status: 'completed',
        title: 'Natural-language preview',
        relatedId: 'preview-request-1',
        sourceId: 'retail-banking',
        sourceName: 'retail-banking',
        message: 'Preview request completed.',
        startedAt: '2026-05-10T00:00:00.000Z',
        updatedAt: '2026-05-10T00:00:01.000Z',
        metadata: {
          analysisProvider: 'llm',
          analysisType: 'preview',
        },
        result: {
          result: buildPreviewResult().preview,
        },
      },
    }

    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={true}
        currentWorkspaceId="retail-banking"
        accessibleWorkspaceIds={['retail-banking', 'corporate-banking']}
        generatePreview={generatePreview}
        createDraftSuggestion={vi.fn().mockResolvedValue({ success: true, message: 'Draft suggestion created.' })}
      />,
    )

    fireEvent(
      screen.getByLabelText(/analysis engine/i),
      new CustomEvent('rdsChange', {
        detail: { value: 'llm' },
        bubbles: true,
      }),
    )

    fireEvent.change(screen.getByLabelText(/what rule do you want/i), {
      target: { value: 'I want a uniqueness rule for attribute customer_id' },
    })

    fireEvent.click(screen.getByText(/generate preview/i))

    expect(generatePreview).toHaveBeenCalledWith(expect.objectContaining({ analysisProvider: 'llm' }))
    await waitFor(() => {
      expect(mockTrackNaturalLanguageDraftRequest).toHaveBeenCalledWith({
        requestId: 'preview-request-1',
        workspaceId: 'retail-banking',
        workspaceName: 'retail banking',
        analysisProvider: 'llm',
        analysisType: 'preview',
      })
    })
    expect(await screen.findByText(/recent llm analysis requests/i)).toBeTruthy()
    expect(await screen.findByText(/natural-language preview/i)).toBeTruthy()
    expect(await screen.findByText(/preview request completed/i)).toBeTruthy()
    expect(await screen.findByText(/metric threshold/i)).toBeTruthy()
  })

  it('keeps a business term match visible when the prompt gets longer', async () => {
    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={true}
        currentWorkspaceId="retail-banking"
        accessibleWorkspaceIds={['retail-banking']}
        generatePreview={vi.fn().mockResolvedValue(buildPreviewResult())}
        createDraftSuggestion={vi.fn().mockResolvedValue({ success: true, message: 'Draft suggestion created.' })}
      />,
    )

    fireEvent.change(screen.getByLabelText(/what rule do you want/i), {
      target: { value: 'percent' },
    })

    expect(await screen.findByText(/Key: discount_percent/)).toBeTruthy()

    fireEvent.change(screen.getByLabelText(/what rule do you want/i), {
      target: { value: 'percent must be' },
    })

    expect(await screen.findByText(/Key: discount_percent/)).toBeTruthy()
    expect(screen.getByText(/Match score: 80%/)).toBeTruthy()
    expect(screen.getByTitle(/term value/i)).toBeTruthy()
    expect(screen.getByTitle(/key value/i)).toBeTruthy()
    expect(screen.getByTitle(/catalog attribute description value/i)).toBeTruthy()
  })

  it('generates a uniqueness preview and persists a draft suggestion', async () => {
    const generatePreview = vi.fn().mockResolvedValue(buildPreviewResult())
    const createDraftSuggestion = vi.fn().mockResolvedValue({
      success: true,
      message: 'Draft suggestion created.',
      suggestion: {
        id: 'nl-suggestion-1',
      },
    })

    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={true}
        currentWorkspaceId="retail-banking"
        accessibleWorkspaceIds={['retail-banking', 'corporate-banking']}
        generatePreview={generatePreview}
        createDraftSuggestion={createDraftSuggestion}
      />,
    )

    fireEvent.change(screen.getByLabelText(/what rule do you want/i), {
      target: { value: 'I want a uniqueness rule for attribute customer_id' },
    })

    fireEvent.click(screen.getByText(/generate preview/i))

    expect(generatePreview).toHaveBeenCalledWith({
      prompt: 'I want a uniqueness rule for attribute customer_id',
      searchScope: 'current',
      currentWorkspaceId: 'retail-banking',
      analysisProvider: 'rapidfuzz',
    })
    expect(await screen.findByText('Matching Business Terms')).toBeTruthy()
    expect(await screen.findByText('Customer ID')).toBeTruthy()
    expect(await screen.findByText('Metric Threshold')).toBeTruthy()
    expect(screen.getByText(/Customer\.Retail Core\.customer_master -> customer_id/i)).toBeTruthy()

    fireEvent.click(screen.getByLabelText(/Customer\.Retail Core\.customer_master -> customer_id/i))
    expect(await screen.findByText('2.0.0')).toBeTruthy()
    fireEvent.click(screen.getByText(/create draft suggestion/i))

    expect(createDraftSuggestion).toHaveBeenCalledTimes(1)
    expect(createDraftSuggestion).toHaveBeenCalledWith({
      currentWorkspaceId: 'retail-banking',
      prompt: 'I want a uniqueness rule for attribute customer_id',
      searchScope: 'current',
      analysisProvider: 'rapidfuzz',
      selectedAttributeIds: ['attr-retail-customer-id'],
    })
    expect(await screen.findByText(/draft suggestion created/i)).toBeTruthy()
  })

  it('requires a current workspace before preview generation', () => {
    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={true}
        currentWorkspaceId={null}
        accessibleWorkspaceIds={[]}
        generatePreview={vi.fn().mockResolvedValue(buildPreviewResult())}
        createDraftSuggestion={vi.fn().mockResolvedValue({ success: true, message: 'Draft suggestion created.' })}
      />,
    )

    fireEvent.change(screen.getByLabelText(/what rule do you want/i), {
      target: { value: 'I want a uniqueness rule for attribute customer_id' },
    })
    fireEvent.click(screen.getByText(/generate preview/i))

    expect(screen.getByText(/select a workspace before using this preview flow/i)).toBeTruthy()
  })

  it('requires a non-blank prompt before preview generation', () => {
    const generatePreview = vi.fn().mockResolvedValue(buildPreviewResult())

    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={true}
        currentWorkspaceId="retail-banking"
        accessibleWorkspaceIds={['retail-banking']}
        generatePreview={generatePreview}
        createDraftSuggestion={vi.fn().mockResolvedValue({ success: true, message: 'Draft suggestion created.' })}
      />,
    )

    fireEvent.click(screen.getByText(/generate preview/i))

    expect(generatePreview).not.toHaveBeenCalled()
    expect(screen.getByText(/describe the rule you want in one sentence/i)).toBeTruthy()
  })

  it('hides the cross-workspace scope option when only one workspace is accessible', () => {
    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={true}
        currentWorkspaceId="retail-banking"
        accessibleWorkspaceIds={['retail-banking']}
        generatePreview={vi.fn().mockResolvedValue(buildPreviewResult())}
        createDraftSuggestion={vi.fn().mockResolvedValue({ success: true, message: 'Draft suggestion created.' })}
      />,
    )

    expect(screen.queryByText(/^All Across Workspaces$/)).toBeNull()
  })

  it('surfaces preview failure messages from the API', async () => {
    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={true}
        currentWorkspaceId="retail-banking"
        accessibleWorkspaceIds={['retail-banking']}
        generatePreview={vi.fn().mockResolvedValue({ success: false, message: 'Preview metadata dependencies are unavailable.' })}
        createDraftSuggestion={vi.fn().mockResolvedValue({ success: true, message: 'Draft suggestion created.' })}
      />,
    )

    fireEvent.change(screen.getByLabelText(/what rule do you want/i), {
      target: { value: 'I want a uniqueness rule for attribute customer_id' },
    })
    fireEvent.click(screen.getByText(/generate preview/i))

    expect(await screen.findByText(/preview metadata dependencies are unavailable/i)).toBeTruthy()
  })

  it('shows conditional role badges and same-version guidance for conditional previews', async () => {
    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={true}
        currentWorkspaceId="retail-banking"
        accessibleWorkspaceIds={['retail-banking']}
        generatePreview={vi.fn().mockResolvedValue(buildConditionalPreviewResult())}
        createDraftSuggestion={vi.fn().mockResolvedValue({ success: true, message: 'Draft suggestion created.' })}
      />,
    )

    fireEvent.change(screen.getByLabelText(/what rule do you want/i), {
      target: { value: 'When a customer is active, a valid email address must be filled in' },
    })
    fireEvent.click(screen.getByText(/generate preview/i))

    expect(await screen.findByText(/status = active/i)).toBeTruthy()
    expect(screen.getAllByText('Condition').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Target').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/same data object version/i).length).toBeGreaterThan(0)
    expect(screen.getByText('Row Assertion')).toBeTruthy()
  })

  it('records selection and cancel telemetry for the current preview flow', async () => {
    const recordTelemetry = vi.fn().mockResolvedValue(true)

    render(
      <NaturalLanguageRuleDraftPreview
        canCreateRule={true}
        currentWorkspaceId="retail-banking"
        accessibleWorkspaceIds={['retail-banking']}
        generatePreview={vi.fn().mockResolvedValue(buildPreviewResult())}
        createDraftSuggestion={vi.fn().mockResolvedValue({ success: true, message: 'Draft suggestion created.' })}
        recordTelemetry={recordTelemetry}
      />,
    )

    fireEvent.change(screen.getByLabelText(/what rule do you want/i), {
      target: { value: 'I want a uniqueness rule for attribute customer_id' },
    })
    fireEvent.click(screen.getByText(/generate preview/i))
    expect(await screen.findByText('Metric Threshold')).toBeTruthy()

    fireEvent.click(screen.getByLabelText(/Customer\.Retail Core\.customer_master -> customer_id/i))
    expect(recordTelemetry).toHaveBeenCalledWith({
      action: 'attributes_selected',
      currentWorkspaceId: 'retail-banking',
      selectedAttributeCount: 1,
    })

    fireEvent.click(screen.getByText(/reset/i))
    expect(recordTelemetry).toHaveBeenCalledWith({
      action: 'preview_cancelled',
      currentWorkspaceId: 'retail-banking',
      selectedAttributeCount: 1,
    })
  })
})
