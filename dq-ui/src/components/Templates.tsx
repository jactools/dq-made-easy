import React, { useMemo, useState, useEffect, useRef } from 'react'
import { RuleTemplate, DAMA_TEMPLATES, DAMADimension } from '../types/templates'
import { RuleCheckType, RuleCheckTypeParams } from '../types/rules'
import { AppSelect } from './app-primitives'
import { Button } from './Button'
import { AppIcon, type AppIconName } from './app-primitives'
import { CheckTypeForm } from './CheckTypeForm'
import { TemplateAttributeCatalogPickerModal } from './TemplateAttributeCatalogPickerModal'
import { WorkspaceScopeSegmentedControl } from './WorkspaceScopeSegmentedControl'
import { useAuth } from '../hooks/useKeycloak'
import { useSettings } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { snakeToCamel } from '../utils/caseConverters'
import {
  mapJoinConsistencyBackendError,
} from './CheckTypeForm/joinConsistencyValidation'
import { CheckTypeFieldErrors } from './CheckTypeForm/checkTypeValidation'
import './Templates.css'

const CHECK_TYPE_OPTIONS: Array<{ value: RuleCheckType; label: string }> = [
  { value: 'THRESHOLD', label: 'Threshold (Completeness)' },
  { value: 'ROW_COUNT', label: 'Row Count (Aggregate)' },
  { value: 'REGEX', label: 'Regex (Accuracy)' },
  { value: 'RANGE', label: 'Range (Validity/Timeliness)' },
  { value: 'ALLOWLIST', label: 'Allowlist (Accuracy/Validity)' },
  { value: 'BLOCKLIST', label: 'Blocklist (Accuracy/Validity)' },
  { value: 'UNIQUENESS', label: 'Uniqueness' },
  { value: 'REFERENTIAL_INTEGRITY', label: 'Referential Integrity' },
  { value: 'FRESHNESS', label: 'Freshness (Timeliness)' },
  { value: 'LAG', label: 'Lag (Timeliness)' },
  { value: 'FUTURE_DATE', label: 'Future Date (Timeliness)' },
  { value: 'PRESENT', label: 'Present (Completeness)' },
  { value: 'CORRECT', label: 'Correct (Accuracy)' },
  { value: 'RECONCILE', label: 'Reconcile (Consistency)' },
  { value: 'PLAUSIBLE', label: 'Plausible (Validity)' },
  { value: 'TRANSFER_MATCH', label: 'Transfer Match (Consistency)' },
  { value: 'JOIN_CONSISTENCY', label: 'Join Consistency (Consistency)' },
]

const SINGLE_ATTRIBUTE_CHECK_TYPES = new Set<RuleCheckType>([
  'THRESHOLD',
  'REGEX',
  'RANGE',
  'ALLOWLIST',
  'BLOCKLIST',
  'REFERENTIAL_INTEGRITY',
  'FRESHNESS',
  'FUTURE_DATE',
  'PRESENT',
  'PLAUSIBLE',
])

const ATTRIBUTE_REQUIRED_CHECK_TYPES = new Set<RuleCheckType>([
  'THRESHOLD',
  'REGEX',
  'RANGE',
  'ALLOWLIST',
  'BLOCKLIST',
  'UNIQUENESS',
  'REFERENTIAL_INTEGRITY',
  'FRESHNESS',
  'LAG',
  'FUTURE_DATE',
  'PRESENT',
  'CORRECT',
  'RECONCILE',
  'PLAUSIBLE',
  'TRANSFER_MATCH',
  'JOIN_CONSISTENCY',
])

const COMPLETENESS_THRESHOLD_METRICS = new Set(['null_pct', 'empty_pct', 'default_val_pct'])
const RAW_AGGREGATE_THRESHOLD_METRICS = new Set(['min', 'max', 'avg', 'sum', 'stddev'])
const DISTINCT_COUNT_THRESHOLD_METRICS = new Set(['distinct_count'])
const THRESHOLD_OPERATOR_LABELS: Record<string, string> = {
  gt: 'greater than',
  gte: 'greater than or equal to',
  lt: 'less than',
  lte: 'less than or equal to',
}
const AGGREGATE_METRIC_LABELS: Record<string, string> = {
  missing_count: 'missing rows',
  duplicate_count: 'duplicate rows',
  duplicate_percent: 'duplicate rate',
  min: 'minimum',
  max: 'maximum',
  avg: 'average',
  sum: 'sum',
  stddev: 'standard deviation',
  distinct_count: 'distinct value count',
}

type AssistantPreviewSupport = {
  engine: string
  support: 'native' | 'partial' | 'sql' | 'custom' | 'no'
  supportedSubsets: string[]
  compilerBehavior: string
  notes: string
}

type AssistantPreviewResponse = {
  checkType: RuleCheckType
  constructFamily: string
  capabilitySummary: string
  compilerHint: string
  support: AssistantPreviewSupport[]
}

const quoteLiteral = (value: string | number) => {
  if (typeof value === 'number') return String(value)
  const trimmed = String(value).trim()
  if (trimmed !== '' && Number.isFinite(Number(trimmed))) return trimmed
  return `'${trimmed.replace(/'/g, "''")}'`
}

const renderCrossObjectComparison = (comparison: any, rhsPrefix = 'rhs.') => {
  const leftAttribute = String(comparison?.leftAttribute || '').trim()
  const rightAttribute = String(comparison?.rightAttribute || '').trim()
  const mode = String(comparison?.mode || 'exact')

  if (!leftAttribute || !rightAttribute) return ''
  if (mode === 'case_insensitive') {
    return `LOWER(${leftAttribute}) = LOWER(${rhsPrefix}${rightAttribute})`
  }
  if (mode === 'numeric_tolerance') {
    const tolerance = Number(comparison?.tolerance)
    return `ABS(${leftAttribute} - ${rhsPrefix}${rightAttribute}) <= ${Number.isFinite(tolerance) ? tolerance : 0}`
  }
  return `${leftAttribute} = ${rhsPrefix}${rightAttribute}`
}

const defaultParamsForCheckType = (
  checkType: RuleCheckType,
  firstAttribute: string,
): Partial<RuleCheckTypeParams> => {
  switch (checkType) {
    case 'THRESHOLD':
      return {
        checkType: 'THRESHOLD',
        attribute: firstAttribute,
        metric: 'null_pct',
        operator: 'gte',
        threshold: 95,
      }
    case 'ROW_COUNT':
      return {
        checkType: 'ROW_COUNT',
        operator: 'gte',
        threshold: 1,
      }
    case 'REGEX':
      return {
        checkType: 'REGEX',
        attribute: firstAttribute,
        pattern: '.*',
        flags: '',
      }
    case 'RANGE':
      return {
        checkType: 'RANGE',
        attribute: firstAttribute,
        inclusive: true,
      }
    case 'ALLOWLIST':
      return {
        checkType: 'ALLOWLIST',
        attribute: firstAttribute,
        allowedValues: [],
        caseSensitive: false,
      }
    case 'BLOCKLIST':
      return {
        checkType: 'BLOCKLIST',
        attribute: firstAttribute,
        blockedValues: [],
        caseSensitive: false,
      }
    case 'UNIQUENESS':
      return {
        checkType: 'UNIQUENESS',
        attributes: firstAttribute ? [firstAttribute] : [],
      }
    case 'REFERENTIAL_INTEGRITY':
      return {
        checkType: 'REFERENTIAL_INTEGRITY',
        attribute: firstAttribute,
        refWorkspaceId: '',
        refDataObjectId: '',
        refDataObjectVersionId: '',
        refAttribute: '',
      }
    case 'FRESHNESS':
      return {
        checkType: 'FRESHNESS',
        attribute: firstAttribute,
        maxDaysOld: 7,
        anchor: 'now',
      }
    case 'LAG':
      return {
        checkType: 'LAG',
        startAttribute: firstAttribute,
        endAttribute: '',
        maxHours: 24,
      }
    case 'FUTURE_DATE':
      return {
        checkType: 'FUTURE_DATE',
        attribute: firstAttribute,
      }
    case 'PRESENT':
      return {
        checkType: 'PRESENT',
        attribute: firstAttribute,
        blockedValues: [],
        caseSensitive: false,
      }
    case 'CORRECT':
      return {
        checkType: 'CORRECT',
        sourceDataObjectVersionId: '',
        referenceDataObjectVersionId: '',
        joinKeys: [{ leftAttribute: firstAttribute, rightAttribute: '' }],
        comparison: {
          leftAttribute: firstAttribute,
          rightAttribute: '',
          mode: 'exact',
        },
      }
    case 'RECONCILE':
      return {
        checkType: 'RECONCILE',
        leftDataObjectVersionId: '',
        rightDataObjectVersionId: '',
        joinKeys: [{ leftAttribute: firstAttribute, rightAttribute: '' }],
        comparisons: [{ leftAttribute: firstAttribute, rightAttribute: '', mode: 'exact' }],
      }
    case 'PLAUSIBLE':
      return {
        checkType: 'PLAUSIBLE',
        mode: 'contextual_range',
        attribute: firstAttribute,
        contextAttribute: '',
        ranges: [],
        allowlists: [],
      }
    case 'TRANSFER_MATCH':
      return {
        checkType: 'TRANSFER_MATCH',
        mode: 'row_value_match',
        leftDataObjectVersionId: '',
        rightDataObjectVersionId: '',
        joinKeys: [{ leftAttribute: firstAttribute, rightAttribute: '' }],
        comparisons: [{ leftAttribute: firstAttribute, rightAttribute: '', mode: 'exact' }],
      }
    case 'JOIN_CONSISTENCY':
      return {
        checkType: 'JOIN_CONSISTENCY',
        leftDataObjectVersionId: '',
        rightDataObjectVersionId: '',
        joinKeys: [{ leftAttribute: firstAttribute, rightAttribute: '' }],
        comparisons: [{ leftAttribute: firstAttribute, rightAttribute: '', mode: 'exact' }],
        actualityDate: {
          leftAttribute: '',
          rightAttribute: '',
          toleranceSource: 'DELIVERY_CONTRACT',
          contractId: '',
        },
        minMatchRate: 100,
      }
    default:
      return {}
  }
}

const deriveDefaultCheckType = (
  template: RuleTemplate,
  firstAttribute: string,
): { checkType: RuleCheckType; checkTypeParams: Partial<RuleCheckTypeParams> } | null => {
  const fallbackAttribute = firstAttribute || 'value'

  if (template.ruleType === 'threshold') {
    const metric = template.id === 'template-completeness-2'
      ? 'empty_pct'
      : template.id === 'template-completeness-3'
      ? 'default_val_pct'
      : 'null_pct'

    return {
      checkType: 'THRESHOLD',
      checkTypeParams: {
        checkType: 'THRESHOLD',
        attribute: fallbackAttribute,
        metric,
          operator: 'gte',
        threshold: Number(template.templateRuleDefinition?.threshold ?? 5),
      },
    }
  }

  if (template.ruleType === 'regex') {
    return {
      checkType: 'REGEX',
      checkTypeParams: {
        checkType: 'REGEX',
        attribute: fallbackAttribute,
        pattern: String(template.templateRuleDefinition?.expectedValues?.pattern || '.*'),
        flags: '',
      },
    }
  }

  if (template.id === 'template-timeliness-1') {
    return {
      checkType: 'FRESHNESS',
      checkTypeParams: {
        checkType: 'FRESHNESS',
        attribute: fallbackAttribute,
        maxDaysOld: Number(template.templateRuleDefinition?.expectedValues?.maxDaysOld ?? 7),
        anchor: 'now',
      },
    }
  }

  if (template.id === 'template-timeliness-2') {
    return {
      checkType: 'LAG',
      checkTypeParams: {
        checkType: 'LAG',
        startAttribute: String(template.templateRuleDefinition?.attributes?.[0] || 'created_at'),
        endAttribute: String(template.templateRuleDefinition?.attributes?.[1] || 'processed_at'),
        maxHours: Number(template.templateRuleDefinition?.expectedValues?.maxHoursLag ?? 24),
      },
    }
  }

  if (template.id === 'template-timeliness-3') {
    return {
      checkType: 'FUTURE_DATE',
      checkTypeParams: {
        checkType: 'FUTURE_DATE',
        attribute: fallbackAttribute,
      },
    }
  }

  if (template.id === 'template-accuracy-4') {
    return {
      checkType: 'ALLOWLIST',
      checkTypeParams: {
        checkType: 'ALLOWLIST',
        attribute: fallbackAttribute,
        allowedValues: Array.isArray(template.templateRuleDefinition?.expectedValues?.allowlist)
          ? template.templateRuleDefinition.expectedValues.allowlist.map((value) => String(value || ''))
          : ['value1', 'value2'],
        caseSensitive: false,
      },
    }
  }

  if (template.id === 'template-consistency-1') {
    return {
      checkType: 'REFERENTIAL_INTEGRITY',
      checkTypeParams: {
        checkType: 'REFERENTIAL_INTEGRITY',
        attribute: fallbackAttribute,
        refWorkspaceId: '',
        refDataObjectId: String(template.templateRuleDefinition?.expectedValues?.parentTable || 'reference_table'),
        refDataObjectVersionId: '',
        refAttribute: String(template.templateRuleDefinition?.expectedValues?.foreignKey || 'id'),
      },
    }
  }

  if (template.id === 'template-consistency-2') {
    const joinKeys = Array.isArray(template.templateRuleDefinition?.expectedValues?.joinKeys)
      ? template.templateRuleDefinition.expectedValues.joinKeys
      : [{ leftAttribute: fallbackAttribute, rightAttribute: fallbackAttribute }]
    const comparisons = Array.isArray(template.templateRuleDefinition?.expectedValues?.comparisonColumns)
      ? template.templateRuleDefinition.expectedValues.comparisonColumns
      : [{ leftAttribute: fallbackAttribute, rightAttribute: fallbackAttribute, mode: 'exact' }]

    return {
      checkType: 'JOIN_CONSISTENCY',
      checkTypeParams: {
        checkType: 'JOIN_CONSISTENCY',
        leftDataObjectVersionId: '',
        rightDataObjectVersionId: '',
        joinKeys: joinKeys.map((item: any) => ({
          leftAttribute: String(item?.leftAttribute || fallbackAttribute),
          rightAttribute: String(item?.rightAttribute || fallbackAttribute),
        })),
        comparisons: comparisons.map((item: any) => ({
          leftAttribute: String(item?.leftAttribute || fallbackAttribute),
          rightAttribute: String(item?.rightAttribute || fallbackAttribute),
          mode: String(item?.mode || 'exact') === 'case_insensitive' ? 'case_insensitive' : 'exact',
        })),
        actualityDate: {
          leftAttribute: '',
          rightAttribute: '',
          toleranceSource: 'DELIVERY_CONTRACT',
          contractId: '',
        },
        minMatchRate: 100,
      },
    }
  }

  if (template.id === 'template-validity-2' || template.id === 'template-validity-3') {
    return {
      checkType: 'RANGE',
      checkTypeParams: {
        checkType: 'RANGE',
        attribute: fallbackAttribute,
        minValue: Number(template.templateRuleDefinition?.expectedValues?.minValue ?? template.templateRuleDefinition?.expectedValues?.minAge ?? 0),
        maxValue: Number(template.templateRuleDefinition?.expectedValues?.maxValue ?? template.templateRuleDefinition?.expectedValues?.maxAge ?? 100),
        inclusive: true,
      },
    }
  }

  if (template.ruleType === 'range') {
    return {
      checkType: 'RANGE',
      checkTypeParams: {
        checkType: 'RANGE',
        attribute: fallbackAttribute,
        minValue: template.templateRuleDefinition?.expectedValues?.minValue,
        maxValue: template.templateRuleDefinition?.expectedValues?.maxValue,
        inclusive: true,
      },
    }
  }

  if (template.dimension === 'uniqueness') {
    return {
      checkType: 'UNIQUENESS',
      checkTypeParams: {
        checkType: 'UNIQUENESS',
        attributes: [fallbackAttribute],
      },
    }
  }

  return null
}

interface TemplatesSelectorModalProps {
  isOpen: boolean
  onClose: () => void
  onSelectTemplate: (
    template: RuleTemplate,
    customizations: {
      name: string
      description: string
      comments?: string
      riskLevel: 'low' | 'medium' | 'high'
      attributeIds: string[]
      checkType?: RuleCheckType
      checkTypeParams?: RuleCheckTypeParams
      templateInputs?: {
        pattern?: string
        flags?: string
        threshold?: number
        expressionOverride?: string
        useAdvancedExpression?: boolean
        manualOverrideConfirmed?: boolean
      }
    }
  ) =>
    | Promise<{ ok: boolean; message?: string } | boolean | void>
    | { ok: boolean; message?: string }
    | boolean
    | void
  initialTemplate?: RuleTemplate
  initialCustomizations?: {
    name: string
    description: string
    comments?: string
    riskLevel: 'low' | 'medium' | 'high'
    attributeIds: string[]
    checkType?: RuleCheckType
    checkTypeParams?: RuleCheckTypeParams
    templateInputs?: {
      pattern?: string
      flags?: string
      threshold?: number
      expressionOverride?: string
      useAdvancedExpression?: boolean
      manualOverrideConfirmed?: boolean
    }
  }
  attributeOptions?: Array<{
    id: string
    name: string
    dataObjectName?: string
    versionId?: string
    dataObjectVersion?: string
  }>
  existingRuleNames?: string[]
  isEditMode?: boolean
  validateCheckTypeDraft: (
    checkType: RuleCheckType,
    checkTypeParams: Partial<RuleCheckTypeParams>,
  ) => Promise<{
    valid: boolean
    message: string | null
    fieldErrors: CheckTypeFieldErrors
    normalizedCheckTypeParams: RuleCheckTypeParams | null
  }>
}

export const TemplatesSelectorModal: React.FC<TemplatesSelectorModalProps> = ({
  isOpen,
  onClose,
  onSelectTemplate,
  initialTemplate,
  initialCustomizations,
  attributeOptions = [],
  existingRuleNames = [],
  isEditMode = false,
  validateCheckTypeDraft,
}) => {
  const [selectedDimension, setSelectedDimension] = useState<DAMADimension | null>(null)
  const [selectedTemplate, setSelectedTemplate] = useState<RuleTemplate | null>(null)
  const [previewName, setPreviewName] = useState('')
  const [previewDescription, setPreviewDescription] = useState('')
  const [previewComments, setPreviewComments] = useState('')
  const [previewRiskLevel, setPreviewRiskLevel] = useState<'low' | 'medium' | 'high'>('medium')
  const [selectedAttributeIds, setSelectedAttributeIds] = useState<Set<string>>(new Set())
  const [attributeSearchQuery, setAttributeSearchQuery] = useState('')
  const [templatePatternInput, setTemplatePatternInput] = useState('')
  const [templateFlagsInput, setTemplateFlagsInput] = useState('')
  const [templateThresholdInput, setTemplateThresholdInput] = useState<number | ''>('')
  const [selectedCheckType, setSelectedCheckType] = useState<RuleCheckType | ''>('')
  const [checkTypeParams, setCheckTypeParams] = useState<Partial<RuleCheckTypeParams>>({})
  const [useAdvancedExpression, setUseAdvancedExpression] = useState(false)
  const [expressionOverrideInput, setExpressionOverrideInput] = useState('')
  const [nameValidationMessage, setNameValidationMessage] = useState<string>('')
  const [checkTypeFieldErrors, setCheckTypeFieldErrors] = useState<CheckTypeFieldErrors>({})
  const [selectedWizardStep, setSelectedWizardStep] = useState<3 | 4>(3)
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false)
  const [isAttributeCatalogPickerOpen, setIsAttributeCatalogPickerOpen] = useState(false)
  const [assistantPreview, setAssistantPreview] = useState<AssistantPreviewResponse | null>(null)
  const [assistantPreviewLoading, setAssistantPreviewLoading] = useState(false)
  const [assistantPreviewError, setAssistantPreviewError] = useState<string | null>(null)
  const assistantPreviewRequestIdRef = useRef(0)
  const auth = useAuth()
  const settings = useSettings()
  const initialFormSnapshotRef = useRef<string>('')
  const assistantCheckType = selectedCheckType || (checkTypeParams as any)?.checkType || ''
  const assistantPayloadPreview = JSON.stringify(
    {
      ai_output: true,
      name: String(previewName || selectedTemplate?.name || '').trim(),
      description: String(previewDescription || selectedTemplate?.description || '').trim(),
      comments: String(previewComments || '').trim(),
      riskLevel: previewRiskLevel,
      attributeIds: Array.from(selectedAttributeIds).sort(),
      checkType: assistantCheckType,
      checkTypeParams: checkTypeParams || {},
      templateInputs: {
        pattern: String(templatePatternInput || '').trim(),
        flags: String(templateFlagsInput || '').trim(),
        threshold: templateThresholdInput === '' ? '' : Number(templateThresholdInput),
        useAdvancedExpression,
        expressionOverride: useAdvancedExpression ? String(expressionOverrideInput || '').trim() : '',
      },
    },
    null,
    2,
  )

  useEffect(() => {
    if (!isOpen || !selectedTemplate) {
      setAssistantPreview(null)
      setAssistantPreviewLoading(false)
      setAssistantPreviewError(null)
      return
    }

    if (!assistantCheckType) {
      setAssistantPreview(null)
      setAssistantPreviewLoading(false)
      setAssistantPreviewError('Select a check type to load the assistant guidance.')
      return
    }

    if (!auth.isAuthenticated || !auth.currentWorkspaceId) {
      setAssistantPreview(null)
      setAssistantPreviewLoading(false)
      setAssistantPreviewError('Select a workspace to load the assistant guidance.')
      return
    }

    const requestId = assistantPreviewRequestIdRef.current + 1
    assistantPreviewRequestIdRef.current = requestId
    setAssistantPreviewLoading(true)
    setAssistantPreviewError(null)

    const controller = new AbortController()
    const apiBase = toApiGroupV1Base('data-catalog', settings.applicationSettings?.apiBaseUrl)
    const query = new URLSearchParams({
      check_type: String(assistantCheckType),
      current_workspace_id: auth.currentWorkspaceId,
    })

    void fetch(`${apiBase}/suggestions/dq7-dsl-assistant?${query.toString()}`, {
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
      },
    })
      .then(async (response) => {
        const body = await response.json().catch(() => null)
        if (!response.ok) {
          throw new Error(String((body as Record<string, unknown> | null)?.message || 'Unable to load assistant guidance.'))
        }
        return snakeToCamel<AssistantPreviewResponse>(body)
      })
      .then((payload) => {
        if (assistantPreviewRequestIdRef.current !== requestId) {
          return
        }
        setAssistantPreview(payload)
      })
      .catch((error) => {
        if (assistantPreviewRequestIdRef.current !== requestId) {
          return
        }
        setAssistantPreview(null)
        setAssistantPreviewError(error instanceof Error ? error.message : 'Unable to load assistant guidance.')
      })
      .finally(() => {
        if (assistantPreviewRequestIdRef.current === requestId) {
          setAssistantPreviewLoading(false)
        }
      })

    return () => {
      controller.abort()
    }
  }, [assistantCheckType, auth.currentWorkspaceId, auth.isAuthenticated, isOpen, selectedTemplate, settings.applicationSettings?.apiBaseUrl])

  const buildFormSnapshot = () => {
    const sortedAttributeIds = Array.from(selectedAttributeIds).sort()
    return JSON.stringify({
      name: String(previewName || '').trim(),
      description: String(previewDescription || '').trim(),
        comments: String(previewComments || '').trim(),
      riskLevel: previewRiskLevel,
      attributeIds: sortedAttributeIds,
      pattern: String(templatePatternInput || '').trim(),
      flags: String(templateFlagsInput || '').trim(),
      threshold: templateThresholdInput === '' ? '' : Number(templateThresholdInput),
      checkType: selectedCheckType || '',
      checkTypeParams: checkTypeParams || {},
      useAdvancedExpression,
      expressionOverride: useAdvancedExpression ? String(expressionOverrideInput || '').trim() : '',
    })
  }

  const hasUnsavedChanges = () => {
    if (!selectedTemplate) return false
    return buildFormSnapshot() !== initialFormSnapshotRef.current
  }

  // Auto-select initial template when modal opens
  useEffect(() => {
    if (isOpen && initialTemplate) {
      setSelectedTemplate(initialTemplate)
      setPreviewName(String(initialCustomizations?.name || initialTemplate.name || ''))
      setPreviewDescription(String(initialCustomizations?.description || initialTemplate.description || ''))
      setPreviewComments(String(initialCustomizations?.comments || ''))
      setPreviewRiskLevel(initialCustomizations?.riskLevel || initialTemplate.defaultRiskLevel)
      setSelectedAttributeIds(new Set(initialCustomizations?.attributeIds || []))

      const derivedCheckType = deriveDefaultCheckType(initialTemplate, 'value')
      const checkType = initialCustomizations?.checkType || derivedCheckType?.checkType || ''
      const checkParams = initialCustomizations?.checkTypeParams || derivedCheckType?.checkTypeParams || {}
      setSelectedCheckType(checkType)
      setCheckTypeParams(checkParams)

      setTemplatePatternInput(
        String(
          initialCustomizations?.templateInputs?.pattern
            ?? (checkParams as any)?.pattern
            ?? initialTemplate.templateRuleDefinition?.expectedValues?.pattern
            ?? ''
        )
      )
      setTemplateFlagsInput(
        String(
          initialCustomizations?.templateInputs?.flags
            ?? (checkParams as any)?.flags
            ?? ''
        )
      )
      const thresholdCandidate =
        initialCustomizations?.templateInputs?.threshold
        ?? Number((checkParams as any)?.threshold)
        ?? Number(initialTemplate.templateRuleDefinition?.threshold)
      setTemplateThresholdInput(Number.isFinite(Number(thresholdCandidate)) ? Number(thresholdCandidate) : '')
      setUseAdvancedExpression(Boolean(initialCustomizations?.templateInputs?.useAdvancedExpression))
      setExpressionOverrideInput(String(initialCustomizations?.templateInputs?.expressionOverride || ''))
      setNameValidationMessage('')
      setSelectedWizardStep(3)
      setShowTechnicalDetails(false)

      const initialAttributeIds = Array.from(new Set(initialCustomizations?.attributeIds || [])).sort()
      initialFormSnapshotRef.current = JSON.stringify({
        name: String(initialCustomizations?.name || initialTemplate.name || '').trim(),
        description: String(initialCustomizations?.description || initialTemplate.description || '').trim(),
        comments: String(initialCustomizations?.comments || '').trim(),
        riskLevel: initialCustomizations?.riskLevel || initialTemplate.defaultRiskLevel,
        attributeIds: initialAttributeIds,
        pattern: String(
          initialCustomizations?.templateInputs?.pattern
            ?? (initialCustomizations?.checkTypeParams as any)?.pattern
            ?? initialTemplate.templateRuleDefinition?.expectedValues?.pattern
            ?? ''
        ).trim(),
        flags: String(
          initialCustomizations?.templateInputs?.flags
            ?? (initialCustomizations?.checkTypeParams as any)?.flags
            ?? ''
        ).trim(),
        threshold: (() => {
          const t =
            initialCustomizations?.templateInputs?.threshold
            ?? Number((initialCustomizations?.checkTypeParams as any)?.threshold)
            ?? Number(initialTemplate.templateRuleDefinition?.threshold)
          return Number.isFinite(Number(t)) ? Number(t) : ''
        })(),
        checkType: String(initialCustomizations?.checkType || derivedCheckType?.checkType || ''),
        checkTypeParams: initialCustomizations?.checkTypeParams || derivedCheckType?.checkTypeParams || {},
        useAdvancedExpression: Boolean(initialCustomizations?.templateInputs?.useAdvancedExpression),
        expressionOverride: Boolean(initialCustomizations?.templateInputs?.useAdvancedExpression)
          ? String(initialCustomizations?.templateInputs?.expressionOverride || '').trim()
          : '',
      })
    }
  }, [isOpen, initialTemplate, initialCustomizations])

  useEffect(() => {
    if (!isOpen) {
      setSelectedAttributeIds(new Set())
      setAttributeSearchQuery('')
      setTemplatePatternInput('')
      setTemplateFlagsInput('')
      setTemplateThresholdInput('')
      setSelectedCheckType('')
      setCheckTypeParams({})
      setUseAdvancedExpression(false)
      setExpressionOverrideInput('')
      setNameValidationMessage('')
      setCheckTypeFieldErrors({})
      setSelectedWizardStep(3)
      setShowTechnicalDetails(false)
      setIsAttributeCatalogPickerOpen(false)
      setPreviewComments('')
      initialFormSnapshotRef.current = ''
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen || !selectedTemplate) {
      setIsAttributeCatalogPickerOpen(false)
    }
  }, [isOpen, selectedTemplate])

  useEffect(() => {
    const handleEscClose = (event: KeyboardEvent) => {
      if (!isOpen) return
      if (event.key !== 'Escape') return

      event.preventDefault()
      event.stopPropagation()

      if (hasUnsavedChanges()) {
        const confirmed = window.confirm('Discard your changes and close this dialog?')
        if (!confirmed) {
          return
        }
      }

      onClose()
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', handleEscClose)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('keydown', handleEscClose)
      }
    }
  }, [isOpen, onClose, selectedTemplate, previewName, previewDescription, previewComments, previewRiskLevel, selectedAttributeIds, templatePatternInput, templateFlagsInput, templateThresholdInput, selectedCheckType, checkTypeParams, useAdvancedExpression, expressionOverrideInput])

  const toggleAttribute = (attributeId: string) => {
    setSelectedAttributeIds((prev) => {
      if (requiresSingleSelectedAttribute) {
        if (prev.has(attributeId) && prev.size === 1) {
          return new Set<string>()
        }
        return new Set<string>([attributeId])
      }

      const next = new Set(prev)
      if (next.has(attributeId)) {
        next.delete(attributeId)
      } else {
        next.add(attributeId)
      }
      return next
    })
  }

  const existingNamesLower = useMemo(
    () => new Set(existingRuleNames.map((name) => String(name || '').trim().toLowerCase()).filter(Boolean)),
    [existingRuleNames],
  )

  const dimensions: DAMADimension[] = ['completeness', 'accuracy', 'consistency', 'timeliness', 'validity', 'uniqueness']
  const dimensionLabels: Record<DAMADimension, string> = {
    completeness: 'Completeness',
    accuracy: 'Accuracy',
    consistency: 'Consistency',
    timeliness: 'Timeliness',
    validity: 'Validity',
    uniqueness: 'Uniqueness',
  }

  const dimensionIcons: Record<DAMADimension, AppIconName> = {
    completeness: 'exclamation-circle',
    accuracy: 'check-circle',
    consistency: 'link',
    timeliness: 'clock',
    validity: 'info-circle',
    uniqueness: 'padlock-closed',
  }

  const filteredTemplates = useMemo(() => {
    if (!selectedDimension) return DAMA_TEMPLATES
    return DAMA_TEMPLATES.filter(t => t.dimension === selectedDimension)
  }, [selectedDimension])

  const filteredAttributeOptions = useMemo(() => {
    const query = attributeSearchQuery.trim().toLowerCase()
    if (!query) return attributeOptions

    return attributeOptions.filter((attribute) => {
      const name = String(attribute.name || '').toLowerCase()
      const objectName = String(attribute.dataObjectName || '').toLowerCase()
      return name.includes(query) || objectName.includes(query)
    })
  }, [attributeOptions, attributeSearchQuery])

  const selectedAttributeSummaries = useMemo(() => {
    const selectedIds = Array.from(selectedAttributeIds)
    const optionsById = attributeOptions.reduce<Record<string, (typeof attributeOptions)[number]>>((acc, item) => {
      acc[item.id] = item
      return acc
    }, {})

    return selectedIds.map((id) => {
      const attribute = optionsById[id]
      if (!attribute) {
        return {
          id,
          name: '',
          dataObjectName: '',
          dataObjectVersion: '',
          versionId: '',
        }
      }

      return {
        id: attribute.id,
        name: String(attribute.name || '').trim(),
        dataObjectName: attribute.dataObjectName || '',
        dataObjectVersion: attribute.dataObjectVersion || '',
        versionId: attribute.versionId || '',
      }
    })
  }, [attributeOptions, selectedAttributeIds])

  const firstSelectedAttributeName = useMemo(() => {
    const firstSelectedId = Array.from(selectedAttributeIds)[0]
    if (!firstSelectedId) return 'value'
    return String(attributeOptions.find((option) => option.id === firstSelectedId)?.name || '').trim() || 'value'
  }, [attributeOptions, selectedAttributeIds])

  const templateDerivedCheckConfig = useMemo(
    () => (selectedTemplate ? deriveDefaultCheckType(selectedTemplate, firstSelectedAttributeName) : null),
    [selectedTemplate, firstSelectedAttributeName],
  )

  const effectiveSelectedCheckType = (selectedCheckType || (checkTypeParams as any)?.checkType || templateDerivedCheckConfig?.checkType) as RuleCheckType | undefined
  const requiresSingleSelectedAttribute = Boolean(effectiveSelectedCheckType && SINGLE_ATTRIBUTE_CHECK_TYPES.has(effectiveSelectedCheckType))
  const requiresAttributeSelection = Boolean(effectiveSelectedCheckType && ATTRIBUTE_REQUIRED_CHECK_TYPES.has(effectiveSelectedCheckType))

  const normalizeSelectedAttributeIds = (attributeIds: string[]) => {
    if (!requiresSingleSelectedAttribute) return attributeIds
    return attributeIds.length > 0 ? [attributeIds[0]] : []
  }

  useEffect(() => {
    if (!requiresSingleSelectedAttribute || selectedAttributeIds.size <= 1) {
      return
    }

    setSelectedAttributeIds((prev) => new Set(normalizeSelectedAttributeIds(Array.from(prev))))
  }, [normalizeSelectedAttributeIds, requiresSingleSelectedAttribute, selectedAttributeIds])

  const buildEffectiveTemplateCheckConfig = () => {
    const effectiveCheckType = selectedCheckType || (checkTypeParams as any)?.checkType || templateDerivedCheckConfig?.checkType
    const sourceParams = selectedCheckType || (checkTypeParams as any)?.checkType
      ? checkTypeParams
      : (templateDerivedCheckConfig?.checkTypeParams || checkTypeParams)

    if (!effectiveCheckType) {
      return {
        checkType: undefined,
        checkTypeParams: undefined,
      }
    }

    const normalized = {
      ...defaultParamsForCheckType(effectiveCheckType, firstSelectedAttributeName),
      ...(sourceParams as any),
      checkType: effectiveCheckType,
    } as any

    if (Array.isArray(normalized.attributes)) {
      normalized.attributes = selectedAttributeIds.size > 0
        ? Array.from(selectedAttributeIds).map((id) => String(attributeOptions.find((opt) => opt.id === id)?.name || '').trim())
        : normalized.attributes
    } else if (typeof normalized.attribute === 'string') {
      normalized.attribute = firstSelectedAttributeName
    }

    if (effectiveCheckType === 'THRESHOLD') {
      normalized.metric = String(normalized.metric || 'null_pct')
      normalized.operator = String(normalized.operator || 'gte')
      normalized.threshold = Number(normalized.threshold ?? 95)
    }

    if (effectiveCheckType === 'ROW_COUNT') {
      normalized.operator = String(normalized.operator || 'gte')
      if (normalized.operator === 'between') {
        normalized.minValue = Number(normalized.minValue ?? normalized.threshold ?? 1)
        normalized.maxValue = Number(normalized.maxValue ?? normalized.threshold ?? 1)
      } else {
        normalized.threshold = Number(normalized.threshold ?? 1)
      }
    }

    if (effectiveCheckType === 'REGEX') {
      normalized.pattern = String(normalized.pattern || '.*')
      normalized.flags = String(normalized.flags || '')
    }

    return {
      checkType: effectiveCheckType,
      checkTypeParams: normalized as RuleCheckTypeParams,
    }
  }

  const validateCheckTypeConfiguration = async () => {
    const { checkType, checkTypeParams } = buildEffectiveTemplateCheckConfig()
    const params: any = checkTypeParams || {}

    if (!checkType) {
      return 'Select a check type before continuing.'
    }

    const result = await validateCheckTypeDraft(checkType, params)
    setCheckTypeFieldErrors(result.fieldErrors)
    return result.message
  }

  const validateStep3Inputs = async () => {
    if (!selectedTemplate) return null

    const normalizedName = String(previewName || selectedTemplate.name).trim()
    if (!normalizedName) {
      setNameValidationMessage('Rule name is required.')
      return null
    }

    if (existingNamesLower.has(normalizedName.toLowerCase())) {
      setNameValidationMessage('Rule name must be unique in this workspace.')
      return null
    }

    if (selectedTemplate.ruleType === 'regex' && !String(templatePatternInput || '').trim()) {
      setNameValidationMessage('Regex pattern is required for this template.')
      return null
    }

    if (requiresAttributeSelection && selectedAttributeIds.size === 0) {
      setNameValidationMessage('Select at least one technical attribute before continuing to the summary.')
      return null
    }

    const checkTypeValidationMessage = await validateCheckTypeConfiguration()
    if (checkTypeValidationMessage) {
      setNameValidationMessage(checkTypeValidationMessage)
      return null
    }

    if (useAdvancedExpression && !String(expressionOverrideInput || '').trim()) {
      setNameValidationMessage('Manual expression override cannot be empty.')
      return null
    }

    setNameValidationMessage('')
    setCheckTypeFieldErrors({})
    return normalizedName
  }

  const buildGeneratedExpressionPreview = () => {
    const checkType = effectiveTemplateCheckConfig.checkType
    const params = effectiveTemplateCheckConfig.checkTypeParams as any
    if (!checkType || !params) return '1 = 1'

    switch (checkType) {
      case 'THRESHOLD': {
        const attribute = String(params.attribute || firstSelectedAttributeName || 'value')
        const metric = String(params.metric || 'null_pct').toLowerCase()
        const thresholdValue = Number(params.threshold ?? 0)
        const operator = String(params.operator || 'gte')
        const operatorSymbols: Record<string, string> = {
          gt: '>',
          gte: '>=',
          lt: '<',
          lte: '<=',
        }

        if (metric === 'quantile') {
          const quantileValue = Number(params.quantile ?? 0.95)
          const quantile = Number.isFinite(quantileValue) ? quantileValue : 0.95
          return `PERCENTILE_CONT(${quantile}) WITHIN GROUP (ORDER BY ${attribute}) ${operatorSymbols[operator] || '>='} ${Number.isFinite(thresholdValue) ? thresholdValue : 0}`
        }

        if (metric === 'missing_count') {
          return `${attribute} IS NOT NULL`
        }

        if (metric === 'duplicate_count' || metric === 'duplicate_percent') {
          return `COUNT(*) OVER (PARTITION BY ${attribute}) = 1`
        }

        if (COMPLETENESS_THRESHOLD_METRICS.has(metric)) {
          return `${attribute} IS NOT NULL`
        }

        if (DISTINCT_COUNT_THRESHOLD_METRICS.has(metric)) {
          return `COUNT(DISTINCT ${attribute}) ${operatorSymbols[operator] || '>='} ${Number.isFinite(thresholdValue) ? thresholdValue : 0}`
        }

        if (RAW_AGGREGATE_THRESHOLD_METRICS.has(metric)) {
          return `${metric.toUpperCase()}(${attribute}) ${operatorSymbols[operator] || '>='} ${Number.isFinite(thresholdValue) ? thresholdValue : 0}`
        }

        return `${attribute} IS NOT NULL`
      }
      case 'ROW_COUNT': {
        const operatorLabels: Record<string, string> = {
          gt: '>',
          gte: '>=',
          lt: '<',
          lte: '<=',
        }
        const operator = String(params.operator || 'gte')
        if (operator === 'between') {
          const minValue = Number(params.minValue ?? params.threshold ?? 1)
          const maxValue = Number(params.maxValue ?? params.threshold ?? 1)
          return `COUNT(*) BETWEEN ${Number.isFinite(minValue) ? minValue : 1} AND ${Number.isFinite(maxValue) ? maxValue : 1}`
        }
        const threshold = Number(params.threshold ?? 1)
        return `COUNT(*) ${operatorLabels[operator] || '>='} ${Number.isFinite(threshold) ? threshold : 1}`
      }
      case 'REGEX': {
        const attribute = String(params.attribute || firstSelectedAttributeName || 'value')
        const pattern = String(params.pattern || '.*').replace(/'/g, "''")
        const flags = String(params.flags || '').trim()
        return flags
          ? `REGEXP_MATCHES(${attribute}, '${pattern}', '${flags}')`
          : `REGEXP_MATCHES(${attribute}, '${pattern}')`
      }
      case 'RANGE': {
        const attribute = String(params.attribute || firstSelectedAttributeName || 'value')
        const minValue = String(params.minValue ?? '').trim()
        const maxValue = String(params.maxValue ?? '').trim()
        if (minValue && maxValue) return `${attribute} BETWEEN ${minValue} AND ${maxValue}`
        if (minValue) return `${attribute} >= ${minValue}`
        if (maxValue) return `${attribute} <= ${maxValue}`
        return `${attribute} IS NOT NULL`
      }
      case 'ALLOWLIST': {
        const attribute = String(params.attribute || firstSelectedAttributeName || 'value')
        const values = Array.isArray(params.allowedValues) ? params.allowedValues : []
        const rendered = values.map((value: string) => `'${String(value || '').replace(/'/g, "''")}'`).join(', ')
        return rendered ? `${attribute} IN (${rendered})` : `${attribute} IS NOT NULL`
      }
      case 'BLOCKLIST': {
        const attribute = String(params.attribute || firstSelectedAttributeName || 'value')
        const values = Array.isArray(params.blockedValues) ? params.blockedValues : []
        const rendered = values.map((value: string) => `'${String(value || '').replace(/'/g, "''")}'`).join(', ')
        return rendered ? `${attribute} NOT IN (${rendered})` : `${attribute} IS NOT NULL`
      }
      case 'UNIQUENESS': {
        const attrs = Array.isArray(params.attributes) ? params.attributes.filter(Boolean) : []
        return attrs.length > 0
          ? `COUNT(*) OVER (PARTITION BY ${attrs.join(', ')}) = 1`
          : 'COUNT(*) OVER (PARTITION BY value) = 1'
      }
      case 'REFERENTIAL_INTEGRITY': {
        const attribute = String(params.attribute || firstSelectedAttributeName || 'value')
        const refAttribute = String(params.refAttribute || 'id')
        const refDataObjectId = String(params.refDataObjectId || 'reference_table')
        return `${attribute} IN (SELECT ${refAttribute} FROM ${refDataObjectId})`
      }
      case 'FRESHNESS': {
        const attribute = String(params.attribute || firstSelectedAttributeName || 'value')
        const maxDaysOld = Number(params.maxDaysOld ?? 7)
        return `DATEDIFF(now(), ${attribute}) <= ${Number.isFinite(maxDaysOld) ? maxDaysOld : 7}`
      }
      case 'LAG': {
        const startAttribute = String(params.startAttribute || firstSelectedAttributeName || 'created_at')
        const endAttribute = String(params.endAttribute || 'processed_at')
        const maxHours = Number(params.maxHours ?? 24)
        return `TIMESTAMPDIFF(HOUR, ${startAttribute}, ${endAttribute}) <= ${Number.isFinite(maxHours) ? maxHours : 24}`
      }
      case 'FUTURE_DATE': {
        const attribute = String(params.attribute || firstSelectedAttributeName || 'value')
        const referenceDate = String(params.referenceDate || 'now()')
        return `${attribute} <= ${referenceDate}`
      }
      case 'PRESENT': {
        const attribute = String(params.attribute || firstSelectedAttributeName || 'value')
        const blockedValues = Array.isArray(params.blockedValues) ? params.blockedValues.filter(Boolean) : []
        const caseSensitive = Boolean(params.caseSensitive)
        const normalizedAttribute = caseSensitive ? `TRIM(${attribute})` : `LOWER(TRIM(${attribute}))`
        const base = [`${attribute} IS NOT NULL`, `TRIM(${attribute}) != ''`]
        if (blockedValues.length > 0) {
          const rendered = blockedValues.map((value: string) => quoteLiteral(caseSensitive ? String(value) : String(value).toLowerCase())).join(', ')
          base.push(`${normalizedAttribute} NOT IN (${rendered})`)
        }
        return base.join(' AND ')
      }
      case 'CORRECT': {
        const joins = Array.isArray(params.joinKeys) ? params.joinKeys : []
        const joinSegment = joins
          .map((item: any) => `${String(item.leftAttribute || '')} = rhs.${String(item.rightAttribute || '')}`)
          .filter(Boolean)
          .join(' AND ')
        const comparisonSegment = renderCrossObjectComparison(params.comparison)
        return [joinSegment, comparisonSegment].filter(Boolean).join(' AND ') || '1 = 1'
      }
      case 'RECONCILE': {
        const joins = Array.isArray(params.joinKeys) ? params.joinKeys : []
        const comparisons = Array.isArray(params.comparisons) ? params.comparisons : []
        const joinSegment = joins
          .map((item: any) => `${String(item.leftAttribute || '')} = rhs.${String(item.rightAttribute || '')}`)
          .filter(Boolean)
          .join(' AND ')
        const comparisonSegment = comparisons
          .map((item: any) => renderCrossObjectComparison(item))
          .filter(Boolean)
          .join(' AND ')
        return [joinSegment, comparisonSegment].filter(Boolean).join(' AND ') || '1 = 1'
      }
      case 'PLAUSIBLE': {
        const attribute = String(params.attribute || firstSelectedAttributeName || 'value')
        const contextAttribute = String(params.contextAttribute || 'context_value')
        const mode = String(params.mode || 'contextual_range')
        if (mode === 'conditional_allowlist') {
          const allowlists = Array.isArray(params.allowlists) ? params.allowlists : []
          const segments = allowlists.map((item: any) => {
            const values = Array.isArray(item.allowedValues) ? item.allowedValues.filter(Boolean) : []
            const caseSensitive = Boolean(item.caseSensitive)
            const attrExpr = caseSensitive ? attribute : `LOWER(${attribute})`
            const rendered = values.map((value: string) => quoteLiteral(caseSensitive ? String(value) : String(value).toLowerCase())).join(', ')
            return rendered
              ? `(${contextAttribute} = ${quoteLiteral(String(item.contextValue || ''))} AND ${attrExpr} IN (${rendered}))`
              : ''
          }).filter(Boolean)
          return segments.join(' OR ') || '1 = 1'
        }
        const ranges = Array.isArray(params.ranges) ? params.ranges : []
        const segments = ranges.map((item: any) => {
          const inclusive = item.inclusive !== false
          const predicates = [`${contextAttribute} = ${quoteLiteral(String(item.contextValue || ''))}`]
          if (item.minValue !== undefined && item.minValue !== '') {
            predicates.push(`${attribute} ${inclusive ? '>=' : '>'} ${quoteLiteral(item.minValue)}`)
          }
          if (item.maxValue !== undefined && item.maxValue !== '') {
            predicates.push(`${attribute} ${inclusive ? '<=' : '<'} ${quoteLiteral(item.maxValue)}`)
          }
          return `(${predicates.join(' AND ')})`
        })
        return segments.join(' OR ') || '1 = 1'
      }
      case 'TRANSFER_MATCH': {
        const joins = Array.isArray(params.joinKeys) ? params.joinKeys : []
        const joinSegment = joins
          .map((item: any) => `${String(item.leftAttribute || '')} = rhs.${String(item.rightAttribute || '')}`)
          .filter(Boolean)
          .join(' AND ')
        if (String(params.mode || 'row_value_match') === 'payload_hash_match') {
          const hashSegment = String(params.leftHashAttribute || '').trim() && String(params.rightHashAttribute || '').trim()
            ? `${String(params.leftHashAttribute)} = rhs.${String(params.rightHashAttribute)}`
            : ''
          return [joinSegment, hashSegment].filter(Boolean).join(' AND ') || '1 = 1'
        }
        const comparisonSegment = (Array.isArray(params.comparisons) ? params.comparisons : [])
          .map((item: any) => renderCrossObjectComparison(item))
          .filter(Boolean)
          .join(' AND ')
        return [joinSegment, comparisonSegment].filter(Boolean).join(' AND ') || '1 = 1'
      }
      case 'JOIN_CONSISTENCY': {
        const joins = Array.isArray(params.joinKeys) ? params.joinKeys : []
        const comparisons = Array.isArray(params.comparisons) ? params.comparisons : []
        const joinSegment = joins
          .map((item: any) => `l.${String(item.leftAttribute || '')} = r.${String(item.rightAttribute || '')}`)
          .join(' AND ')
        const cmpSegment = comparisons
          .map((item: any) => {
            if (String(item.mode || 'exact') === 'case_insensitive') {
              return `LOWER(l.${String(item.leftAttribute || '')}) = LOWER(r.${String(item.rightAttribute || '')})`
            }
            return `l.${String(item.leftAttribute || '')} = r.${String(item.rightAttribute || '')}`
          })
          .join(' AND ')
        return `JOIN_CONSISTENCY(left=${String(params.leftDataObjectVersionId || '')}, right=${String(params.rightDataObjectVersionId || '')}, on=${joinSegment || 'n/a'}, compare=${cmpSegment || 'n/a'})`
      }
      default:
        return '1 = 1'
    }
  }

  const buildTemplateCustomizations = (normalizedName: string) => {
    const { checkType: effectiveCheckType, checkTypeParams: effectiveCheckTypeParams } =
      buildEffectiveTemplateCheckConfig()

    return {
      name: normalizedName,
      description: previewDescription || selectedTemplate?.description || '',
      comments: previewComments || undefined,
      riskLevel: previewRiskLevel,
      attributeIds: Array.from(selectedAttributeIds),
      checkType: effectiveCheckType,
      checkTypeParams: effectiveCheckTypeParams,
      templateInputs: {
        pattern: String(templatePatternInput || '').trim() || undefined,
        flags: String(templateFlagsInput || '').trim() || undefined,
        threshold: templateThresholdInput === '' ? undefined : Number(templateThresholdInput),
        expressionOverride: useAdvancedExpression ? String(expressionOverrideInput || '').trim() : undefined,
        useAdvancedExpression,
        manualOverrideConfirmed: false as boolean | undefined,
      },
    }
  }

  const effectiveTemplateCheckConfig = buildEffectiveTemplateCheckConfig()

  const userFriendlyCheckSummary = useMemo(() => {
    const checkType = effectiveTemplateCheckConfig.checkType
    const params = effectiveTemplateCheckConfig.checkTypeParams as any

    if (!checkType || !params) return [] as string[]

    switch (checkType) {
      case 'THRESHOLD': {
        const metric = String(params.metric || 'null_pct').toLowerCase()
        const operatorLabel = THRESHOLD_OPERATOR_LABELS[String(params.operator || 'gte')] || 'greater than or equal to'
        const thresholdValue = Number(params.threshold ?? 0)
        const quantileValue = Number(params.quantile ?? 0.95)
        const quantilePercent = Number.isNaN(quantileValue) ? '95%' : `${Math.round(quantileValue * 1000) / 10}%`
        const metricLabels: Record<string, string> = {
          null_pct: 'NULL values',
          empty_pct: 'empty values',
          default_val_pct: 'default or placeholder values',
        }
        if (metric === 'quantile') {
          return [
            `Checks the ${quantilePercent} quantile for each selected attribute.`,
            `Requires comparison value ${operatorLabel} ${Number.isFinite(thresholdValue) ? thresholdValue : 0}.`,
            `Quantile target: ${quantilePercent}.`,
          ]
        }

        if (metric === 'missing_count') {
          return [
            `Checks missing rows for each selected attribute.`,
            `Requires missing rows to stay at 0.`,
            `Current runtime lowers this to non-null semantics.`,
          ]
        }

        if (metric === 'duplicate_count') {
          return [
            `Checks duplicate rows for each selected attribute.`,
            `Requires duplicate rows to stay at 0.`,
            `Current runtime lowers this to uniqueness semantics.`,
          ]
        }

        if (metric === 'duplicate_percent') {
          return [
            `Checks duplicate rate for each selected attribute.`,
            `Requires duplicate rate to stay at 0%.`,
            `Current runtime lowers this to uniqueness semantics.`,
          ]
        }

        if (COMPLETENESS_THRESHOLD_METRICS.has(metric) || !metric) {
          const goodThreshold = Number.isFinite(thresholdValue) ? thresholdValue : 0
          return [
            `Checks ${metricLabels[metric] || 'values'} for each selected attribute.`,
            `Requires at least ${goodThreshold}% good values for this rule.`,
            `Comparison operator: ${operatorLabel}.`,
          ]
        }

        if (DISTINCT_COUNT_THRESHOLD_METRICS.has(metric)) {
          const countValue = Number.isFinite(thresholdValue) ? thresholdValue : 0
          return [
            `Checks distinct values for each selected attribute.`,
            `Requires distinct count ${operatorLabel} ${countValue}.`,
            `Comparison operator: ${operatorLabel}.`,
          ]
        }

        if (RAW_AGGREGATE_THRESHOLD_METRICS.has(metric)) {
          const aggregateLabel = AGGREGATE_METRIC_LABELS[metric] || 'selected aggregate'
          const value = Number.isFinite(thresholdValue) ? thresholdValue : 0
          return [
            `Checks the ${aggregateLabel} for each selected attribute.`,
            `Requires a comparison value ${operatorLabel} ${value}.`,
            `Comparison operator: ${operatorLabel}.`,
          ]
        }

        const goodThreshold = Number.isFinite(thresholdValue) ? thresholdValue : 0
        return [
          `Checks values for each selected attribute.`,
          `Requires at least ${goodThreshold} good values for this rule.`,
          `Comparison operator: ${operatorLabel}.`,
        ]
      }
      case 'ROW_COUNT': {
        const operatorLabels: Record<string, string> = {
          gt: 'greater than',
          gte: 'greater than or equal to',
          lt: 'less than',
          lte: 'less than or equal to',
        }
        const operator = String(params.operator || 'gte')
        if (operator === 'between') {
          const minValue = Number(params.minValue ?? params.threshold ?? 1)
          const maxValue = Number(params.maxValue ?? params.threshold ?? 1)
          return [
            'Checks total row count for the dataset.',
            `Requires row count between ${Number.isFinite(minValue) ? minValue : 1} and ${Number.isFinite(maxValue) ? maxValue : 1}.`,
          ]
        }
        const threshold = Number(params.threshold ?? 1)
        return [
          'Checks total row count for the dataset.',
          `Requires row count ${operatorLabels[operator] || 'greater than or equal to'} ${Number.isFinite(threshold) ? threshold : 1}.`,
        ]
      }
      case 'REGEX': {
        const flags = String(params.flags || '').trim()
        return [
          `Checks each selected attribute value against pattern: ${String(params.pattern || '')}`,
          flags ? `Uses regex flags: ${flags}` : 'No regex flags are applied.',
        ]
      }
      case 'RANGE':
        return [
          `Checks values are within range ${String(params.minValue ?? '-∞')} to ${String(params.maxValue ?? '+∞')}.`,
          `Bounds mode: ${(params.inclusive ?? true) ? 'inclusive' : 'exclusive'}.`,
        ]
      case 'ALLOWLIST':
        return [
          `Checks values are in the allowed list (${Array.isArray(params.allowedValues) ? params.allowedValues.length : 0} values).`,
          `Case sensitivity: ${params.caseSensitive ? 'case-sensitive' : 'case-insensitive'}.`,
        ]
      case 'BLOCKLIST':
        return [
          `Checks values are not in the blocked list (${Array.isArray(params.blockedValues) ? params.blockedValues.length : 0} values).`,
          `Case sensitivity: ${params.caseSensitive ? 'case-sensitive' : 'case-insensitive'}.`,
        ]
      case 'UNIQUENESS':
        return [
          `Checks selected attribute combination is unique.`,
        ]
      case 'REFERENTIAL_INTEGRITY':
        return [
          `Checks values exist in reference object '${String(params.refDataObjectId || '')}'.`,
          `Reference object version: ${String(params.refDataObjectVersionId || '')}.`,
          params.refWorkspaceId
            ? `Reference workspace scope: ${String(params.refWorkspaceId)}.`
            : 'Reference workspace scope: current or cross-workspace (as resolved by backend).',
          `Reference attribute: ${String(params.refAttribute || '')}.`,
        ]
      case 'FRESHNESS':
        return [
          `Checks records are not older than ${String(params.maxDaysOld ?? '')} day(s).`,
          `Anchor: ${String(params.anchor || 'now')}.`,
        ]
      case 'LAG':
        return [
          `Checks lag between '${String(params.startAttribute || '')}' and '${String(params.endAttribute || '')}'.`,
          `Maximum lag: ${String(params.maxHours ?? '')} hour(s).`,
        ]
      case 'FUTURE_DATE':
        return [
          `Checks date is not in the future${params.referenceDate ? ` relative to ${String(params.referenceDate)}` : ''}.`,
        ]
      case 'PRESENT':
        return [
          `Checks '${String(params.attribute || '')}' is populated with non-blank values.`,
          Array.isArray(params.blockedValues) && params.blockedValues.length > 0
            ? `Treats ${params.blockedValues.length} placeholder value(s) as missing.`
            : 'No additional placeholder values are configured.',
          `Comparison mode: ${params.caseSensitive ? 'case-sensitive' : 'case-insensitive'}.`,
        ]
      case 'CORRECT':
        return [
          `Checks '${String(params.comparison?.leftAttribute || '')}' against '${String(params.comparison?.rightAttribute || '')}' using reference version '${String(params.referenceDataObjectVersionId || '')}'.`,
          `Join key mappings: ${Array.isArray(params.joinKeys) ? params.joinKeys.length : 0}.`,
          `Comparison mode: ${String(params.comparison?.mode || 'exact')}${params.comparison?.tolerance != null ? ` (tolerance ${String(params.comparison.tolerance)})` : ''}.`,
        ]
      case 'RECONCILE':
        return [
          `Reconciles left version '${String(params.leftDataObjectVersionId || '')}' with right version '${String(params.rightDataObjectVersionId || '')}'.`,
          `Join key mappings: ${Array.isArray(params.joinKeys) ? params.joinKeys.length : 0}.`,
          `Comparison mappings: ${Array.isArray(params.comparisons) ? params.comparisons.length : 0}.`,
        ]
      case 'PLAUSIBLE':
        return [
          `Checks '${String(params.attribute || '')}' in the context of '${String(params.contextAttribute || '')}'.`,
          String(params.mode || 'contextual_range') === 'conditional_allowlist'
            ? `Conditional allowlist rules: ${Array.isArray(params.allowlists) ? params.allowlists.length : 0}.`
            : `Contextual ranges: ${Array.isArray(params.ranges) ? params.ranges.length : 0}.`,
        ]
      case 'TRANSFER_MATCH':
        return [
          `Checks transfer alignment between '${String(params.leftDataObjectVersionId || '')}' and '${String(params.rightDataObjectVersionId || '')}'.`,
          `Join key mappings: ${Array.isArray(params.joinKeys) ? params.joinKeys.length : 0}.`,
          String(params.mode || 'row_value_match') === 'payload_hash_match'
            ? `Payload hash attributes: ${String(params.leftHashAttribute || '')} -> ${String(params.rightHashAttribute || '')}.`
            : `Row value comparisons: ${Array.isArray(params.comparisons) ? params.comparisons.length : 0}.`,
        ]
      case 'JOIN_CONSISTENCY':
        return [
          `Compares left version '${String(params.leftDataObjectVersionId || '')}' against right version '${String(params.rightDataObjectVersionId || '')}'.`,
          `Join key mappings: ${Array.isArray(params.joinKeys) ? params.joinKeys.length : 0}.`,
          `Comparison mappings: ${Array.isArray(params.comparisons) ? params.comparisons.length : 0}.`,
          `Actuality-date contract: ${String(params.actualityDate?.contractId || '')}.`,
          `Minimum match rate: ${String(params.minMatchRate ?? '')}%.`,
        ]
      default:
        return [] as string[]
    }
  }, [effectiveTemplateCheckConfig])

  const businessCheckTypeLabel = useMemo(() => {
    if (!selectedTemplate) return 'Quality Check'

    const byTemplateId: Record<string, string> = {
      'template-completeness-1': 'Completeness Check (NULL values)',
      'template-completeness-2': 'Completeness Check (empty values)',
      'template-completeness-3': 'Completeness Check (default/placeholder values)',
      'template-accuracy-4': 'Accuracy Check (allowed values)',
      'template-consistency-1': 'Consistency Check (referential integrity)',
      'template-consistency-2': 'Consistency Check (cross-dataset integrity)',
      'template-consistency-3': 'Consistency Check (case standardization)',
      'template-consistency-4': 'Consistency Check (whitespace normalization)',
      'template-timeliness-1': 'Timeliness Check (freshness)',
      'template-timeliness-2': 'Timeliness Check (lag)',
      'template-timeliness-3': 'Timeliness Check (future date)',
      'template-validity-2': 'Validity Check (age validation)',
      'template-validity-3': 'Validity Check (outlier detection)',
      'template-validity-4': 'Validity Check (distribution drift)',
      'template-validity-5': 'Validity Check (entropy drift)',
      'template-validity-6': 'Validity Check (probabilistic threshold)',
      'template-validity-7': 'Validity Check (seasonality stability)',
    }

    return byTemplateId[selectedTemplate.id] || `${selectedTemplate.dimension.charAt(0).toUpperCase()}${selectedTemplate.dimension.slice(1)} Check`
  }, [selectedTemplate])

  const handleConfirmCreate = async () => {
    if (!selectedTemplate) return

    const normalizedName = await validateStep3Inputs()
    if (!normalizedName) return

    let manualOverrideConfirmed = false
    if (useAdvancedExpression) {
      manualOverrideConfirmed = window.confirm(
        'Confirm manual expression override. This will bypass automatic expression generation and will be audited with your user and timestamp. Continue?'
      )
      if (!manualOverrideConfirmed) {
        return
      }
    }

    const customizations = buildTemplateCustomizations(normalizedName)
    customizations.templateInputs = {
      ...(customizations.templateInputs || {}),
      manualOverrideConfirmed,
    }

    const applyJoinConsistencyBackendErrors = (message: string) => {
      if (customizations.checkType !== 'JOIN_CONSISTENCY') {
        return
      }
      const mapped = mapJoinConsistencyBackendError(message)
      setCheckTypeFieldErrors(mapped.fieldErrors)
    }

    const outcome = await onSelectTemplate(selectedTemplate, customizations)

    if (outcome === false) {
      setNameValidationMessage('Rule name must be unique within workspace.')
      return
    }

    if (outcome && typeof outcome === 'object' && 'ok' in outcome && outcome.ok === false) {
      const message = String(outcome.message || 'Rule name must be unique within workspace.')
      setNameValidationMessage(message)
      applyJoinConsistencyBackendErrors(message)
      return
    }

    setSelectedTemplate(null)
    setSelectedWizardStep(3)
    setPreviewName('')
    setPreviewDescription('')
    setPreviewComments('')
    setPreviewRiskLevel('medium')
    setSelectedAttributeIds(new Set())
    setNameValidationMessage('')
    setCheckTypeFieldErrors({})
    onClose()
  }

  if (!isOpen) return null

  // Show preview form if a template is selected
  if (selectedTemplate) {
    return (
      <>
        <div className="modal-overlay templates-overlay" onClick={onClose}>
          <div className="templates-modal" onClick={(e) => e.stopPropagation()}>
          <div className="templates-header">
            <h2>{selectedWizardStep === 3 ? 'Step 3 of 4: Configure Rule' : `Step 4 of 4: Review & Confirm ${isEditMode ? 'Update' : 'Create'}`}</h2>
            <button className="modal-close" onClick={() => setSelectedTemplate(null)} aria-label="Back">
              ←
            </button>
          </div>

          <div className="wizard-steps" aria-label="New rule wizard progress">
            <span className="wizard-step wizard-step-done">1. DAMA</span>
            <span className="wizard-step wizard-step-done">2. Template</span>
            <span className={`wizard-step ${selectedWizardStep === 3 ? 'wizard-step-active' : 'wizard-step-done'}`}>
              3. Configure
            </span>
            <span className={`wizard-step ${selectedWizardStep === 4 ? 'wizard-step-active' : ''}`}>
              4. Summary
            </span>
          </div>

          <div className="templates-content template-preview">
            <div className="preview-card">
              <div className="preview-icon">
                <AppIcon name={selectedTemplate.icon || 'document'} />
              </div>
              <p className="preview-template-name">{selectedTemplate.name}</p>
              <p className="preview-template-desc">{selectedTemplate.description}</p>
            </div>

            <div className="preview-form">
              {selectedWizardStep === 3 ? (
                <>
                  <div className="form-group">
                    <label htmlFor="preview-name">Rule Name</label>
                    <input
                      id="preview-name"
                      type="text"
                      value={previewName}
                      onChange={(e) => setPreviewName(e.target.value)}
                      placeholder="Enter rule name"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="preview-description">Description</label>
                    <textarea
                      id="preview-description"
                      value={previewDescription}
                      onChange={(e) => setPreviewDescription(e.target.value)}
                      placeholder="Enter rule description"
                      rows={4}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="preview-comments">Comments</label>
                    <textarea
                      id="preview-comments"
                      value={previewComments}
                      onChange={(e) => setPreviewComments(e.target.value)}
                      placeholder="Optional comments for this rule entry"
                      rows={3}
                    />
                  </div>

                  <div className="form-group">
                    <AppSelect
                      id="preview-risk"
                      label="Risk Level"
                      value={previewRiskLevel}
                      onChange={(value) => setPreviewRiskLevel(value as 'low' | 'medium' | 'high')}
                      options={[
                        { value: 'low', label: 'Low' },
                        { value: 'medium', label: 'Medium' },
                        { value: 'high', label: 'High' },
                      ]}
                    />
                  </div>

                  <div className="form-group" style={{ marginTop: '0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', marginBottom: '8px' }}>
                      <label style={{ margin: 0 }}>
                        {requiresSingleSelectedAttribute ? 'Step 3: Select attribute from catalog' : 'Step 3: Select attributes'}
                      </label>
                      <Button
                        type="button"
                        variant="secondary-default"
                        onClick={() => setIsAttributeCatalogPickerOpen(true)}
                      >
                        Browse Data Catalog
                      </Button>
                    </div>
                    <input
                      type="text"
                      className="modal-input"
                      value={attributeSearchQuery}
                      onChange={(e) => setAttributeSearchQuery(e.target.value)}
                      placeholder="Search attributes by name or data object"
                      style={{ marginBottom: '8px' }}
                    />
                    <p className="wizard-attribute-search-meta">
                      Showing {filteredAttributeOptions.length} of {attributeOptions.length} attributes
                    </p>
                    <div style={{ maxHeight: '180px', overflowY: 'auto', border: '1px solid var(--app-border-subtle)', borderRadius: '6px', padding: '8px' }}>
                      {attributeOptions.length === 0 ? (
                        <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--app-text-secondary)' }}>
                          No attributes available. You can assign attributes later.
                        </p>
                      ) : filteredAttributeOptions.length === 0 ? (
                        <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--app-text-secondary)' }}>
                          No attributes match your search.
                        </p>
                      ) : (
                        filteredAttributeOptions.map((attribute) => {
                          const checked = selectedAttributeIds.has(attribute.id)
                          const label = attribute.dataObjectName
                            ? `${attribute.dataObjectName} - ${attribute.name}`
                            : attribute.name
                          return (
                            <label
                              key={attribute.id}
                              style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.875rem', marginBottom: '6px' }}
                            >
                              <input
                                type={requiresSingleSelectedAttribute ? 'radio' : 'checkbox'}
                                name={requiresSingleSelectedAttribute ? 'template-primary-attribute' : undefined}
                                checked={checked}
                                onChange={() => toggleAttribute(attribute.id)}
                              />
                              <span>{label}</span>
                            </label>
                          )
                        })
                      )}
                    </div>
                  </div>

                  <div className="form-group" style={{ marginTop: '0.75rem' }}>
                    <AppSelect
                      id="template-check-type"
                      label="Step 3: Select business check type"
                      value={selectedCheckType || (checkTypeParams as any)?.checkType || ''}
                      onChange={(value) => {
                        const nextCheckType = String(value || '').trim().toUpperCase() as RuleCheckType
                        if (!nextCheckType) {
                          setSelectedCheckType('')
                          setCheckTypeParams({})
                          setCheckTypeFieldErrors({})
                          return
                        }

                        setSelectedCheckType(nextCheckType)
                        if (nextCheckType === 'ROW_COUNT') {
                          setSelectedAttributeIds(new Set())
                        } else if (SINGLE_ATTRIBUTE_CHECK_TYPES.has(nextCheckType) && selectedAttributeIds.size > 1) {
                          setSelectedAttributeIds((prev) => new Set(Array.from(prev).slice(0, 1)))
                        }
                        setCheckTypeParams(defaultParamsForCheckType(nextCheckType, firstSelectedAttributeName))
                        setNameValidationMessage('')
                        setCheckTypeFieldErrors({})
                                        {requiresAttributeSelection ? (
                                          <div className="form-group" style={{ marginTop: '0.75rem' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', marginBottom: '8px' }}>
                                              <label style={{ margin: 0 }}>
                                                {requiresSingleSelectedAttribute ? 'Step 3: Select attribute from catalog' : 'Step 3: Select attributes'}
                                              </label>
                                              <Button
                                                type="button"
                                                variant="secondary-default"
                                                onClick={() => setIsAttributeCatalogPickerOpen(true)}
                                              >
                                                Browse Data Catalog
                                              </Button>
                                            </div>
                                            <input
                                              type="text"
                                              className="modal-input"
                                              value={attributeSearchQuery}
                                              onChange={(e) => setAttributeSearchQuery(e.target.value)}
                                              placeholder="Search attributes by name or data object"
                                              style={{ marginBottom: '8px' }}
                                            />
                                            <p className="wizard-attribute-search-meta">
                                              Showing {filteredAttributeOptions.length} of {attributeOptions.length} attributes
                                            </p>
                                            <div style={{ maxHeight: '180px', overflowY: 'auto', border: '1px solid var(--app-border-subtle)', borderRadius: '6px', padding: '8px' }}>
                                              {attributeOptions.length === 0 ? (
                                                <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--app-text-secondary)' }}>
                                                  No attributes available. You can assign attributes later.
                                                </p>
                                              ) : filteredAttributeOptions.length === 0 ? (
                                                <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--app-text-secondary)' }}>
                                                  No attributes match your search.
                                                </p>
                                              ) : (
                                                filteredAttributeOptions.map((attribute) => {
                                                  const checked = selectedAttributeIds.has(attribute.id)
                                                  const label = attribute.dataObjectName
                                                    ? `${attribute.dataObjectName} - ${attribute.name}`
                                                    : attribute.name
                                                  return (
                                                    <label
                                                      key={attribute.id}
                                                      style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.875rem', marginBottom: '6px' }}
                                                    >
                                                      <input
                                                        type={requiresSingleSelectedAttribute ? 'radio' : 'checkbox'}
                                                        name={requiresSingleSelectedAttribute ? 'template-primary-attribute' : undefined}
                                                        checked={checked}
                                                        onChange={() => toggleAttribute(attribute.id)}
                                                      />
                                                      <span>{label}</span>
                                                    </label>
                                                  )
                                                })
                                              )}
                                            </div>
                                          </div>
                                        ) : (
                                          <div className="form-group" style={{ marginTop: '0.75rem' }}>
                                            <p className="template-input-guidance-text" style={{ margin: 0 }}>
                                              Row count checks apply to the whole dataset and do not require catalog attributes.
                                            </p>
                                          </div>
                                        )}
                      }}
                      options={CHECK_TYPE_OPTIONS}
                       placeholderLabel="Choose a check type"
                    />
                    <p className="template-input-guidance-text" style={{ margin: '0.25rem 0 0 0' }}>
                      You can keep the template-recommended check type or choose another typed check.
                    </p>
                  </div>

                  {effectiveSelectedCheckType && (
                    <div className="form-group" style={{ marginTop: '0.75rem' }}>
                      <label className="check-type-form-label">Step 3: Configure check parameters</label>
                      <CheckTypeForm
                        checkType={effectiveSelectedCheckType}
                        params={checkTypeParams}
                        catalogAttributeName={firstSelectedAttributeName === 'value' ? '' : firstSelectedAttributeName}
                          fieldErrors={checkTypeFieldErrors}
                        onChange={(params) => {
                          setCheckTypeParams(params)
                            setCheckTypeFieldErrors({})
                          if (params.checkType === 'REGEX') {
                            const p = params as any
                            setTemplatePatternInput(String(p.pattern || ''))
                            setTemplateFlagsInput(String(p.flags || ''))
                          }
                          if (params.checkType === 'THRESHOLD' || params.checkType === 'ROW_COUNT') {
                            const p = params as any
                            setTemplateThresholdInput(
                              Number.isFinite(Number(p.threshold)) ? Number(p.threshold) : ''
                            )
                          }
                        }}
                      />
                    </div>
                  )}

                  {effectiveSelectedCheckType && (
                    <div className="form-group" style={{ marginTop: '0.75rem' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input
                          type="checkbox"
                          checked={useAdvancedExpression}
                          onChange={(event) => {
                            const enabled = event.target.checked
                            setUseAdvancedExpression(enabled)
                            if (enabled && !String(expressionOverrideInput || '').trim()) {
                              setExpressionOverrideInput(buildGeneratedExpressionPreview())
                            }
                          }}
                        />
                        <span>Use manual expression override (advanced)</span>
                      </label>
                      <p className="template-input-guidance-text" style={{ margin: '0.25rem 0 0 0' }}>
                        When enabled, this expression is sent as-is. The selected check type remains as structured metadata.
                      </p>
                      {useAdvancedExpression && (
                        <textarea
                          value={expressionOverrideInput}
                          onChange={(event) => setExpressionOverrideInput(event.target.value)}
                          placeholder="Enter custom expression"
                          rows={4}
                          style={{ marginTop: '8px' }}
                        />
                      )}
                    </div>
                  )}

                  {!effectiveSelectedCheckType && (
                    <p className="check-type-form-hint" style={{ marginTop: '0.25rem' }}>
                      Select a business check type to configure typed rule parameters.
                    </p>
                  )}

                  <aside className="wizard-assistant-panel template-input-guidance" role="complementary" aria-label="Read-only assistant">
                    <p className="template-input-guidance-title">Read-only assistant</p>
                    <p className="template-input-guidance-text">
                      This helper explains the current draft and previews the payload shape. It never saves or owns the contract.
                    </p>
                    {assistantPreviewLoading && !assistantPreview && (
                      <p className="template-input-guidance-text" style={{ marginTop: '6px' }}>
                        Loading assistant guidance...
                      </p>
                    )}
                    {assistantPreviewError && !assistantPreview && (
                      <p className="template-input-guidance-text" style={{ marginTop: '6px' }}>
                        {assistantPreviewError}
                      </p>
                    )}
                    {assistantPreview && (
                      <>
                        <p className="template-input-guidance-text" style={{ marginTop: '6px' }}>
                          <strong>Capability family:</strong> {assistantPreview.constructFamily}
                        </p>
                        <p className="template-input-guidance-text">
                          <strong>Shape:</strong> {assistantPreview.capabilitySummary}
                        </p>
                        <p className="template-input-guidance-text">
                          <strong>Compiler hint:</strong> {assistantPreview.compilerHint}
                        </p>
                        <div className="wizard-assistant-support-list">
                          {assistantPreview.support.map((item) => (
                            <p key={`${item.engine}-${item.support}`} className="template-input-guidance-text wizard-assistant-support-item">
                              <strong>{item.engine}:</strong> {item.support.toUpperCase()} — {item.notes}
                              {item.supportedSubsets.length > 0 && (
                                <span>{` Supported subsets: ${item.supportedSubsets.join(', ')}`}</span>
                              )}
                              {item.compilerBehavior ? <span>{` Compiler behavior: ${item.compilerBehavior}`}</span> : null}
                            </p>
                          ))}
                        </div>
                      </>
                    )}
                    <p className="template-input-guidance-text" style={{ marginTop: '8px' }}>
                      <strong>Draft payload preview:</strong>
                    </p>
                    <pre className="wizard-assistant-json">{assistantPayloadPreview}</pre>
                  </aside>
                </>
              ) : (
                <div className="template-input-guidance" role="note" aria-live="polite">
                  <p className="template-input-guidance-title">Summary</p>
                  <p className="template-input-guidance-text"><strong>Name:</strong> {String(previewName || selectedTemplate.name).trim() || '-'}</p>
                  <p className="template-input-guidance-text"><strong>Description:</strong> {String(previewDescription || selectedTemplate.description || '-')}</p>
                  <p className="template-input-guidance-text"><strong>Comments:</strong> {String(previewComments || '-')}</p>
                  <p className="template-input-guidance-text"><strong>Risk:</strong> {previewRiskLevel}</p>
                  <p className="template-input-guidance-text"><strong>Attributes selected:</strong> {selectedAttributeIds.size}</p>
                  {selectedAttributeSummaries.length > 0 && (
                    <div style={{ marginTop: '8px', paddingLeft: '12px' }}>
                      {selectedAttributeSummaries.map((attribute) => (
                        <p key={attribute.id} className="template-input-guidance-text" style={{ margin: '4px 0' }}>
                          • {attribute.name}
                          {attribute.dataObjectName ? ` (${attribute.dataObjectName})` : ''}
                          {attribute.dataObjectVersion
                            ? ` - v${attribute.dataObjectVersion}`
                            : attribute.versionId
                            ? ` - versionId ${attribute.versionId}`
                            : ''}
                        </p>
                      ))}
                    </div>
                  )}
                  <p className="template-input-guidance-text">
                    <strong>Template:</strong> {selectedTemplate.name}
                  </p>
                  <p className="template-input-guidance-text">
                    <strong>Selected check type:</strong> {effectiveTemplateCheckConfig.checkType || '-'}
                  </p>
                  <p className="template-input-guidance-text">
                    <strong>Manual expression override:</strong> {useAdvancedExpression ? 'Enabled' : 'Disabled'}
                  </p>
                  {useAdvancedExpression && (
                    <p className="template-input-guidance-text">
                      <strong>Expression:</strong> {String(expressionOverrideInput || '-').trim() || '-'}
                    </p>
                  )}
                  {userFriendlyCheckSummary.length > 0 && (
                    <div style={{ marginTop: '8px', paddingLeft: '12px' }}>
                      {userFriendlyCheckSummary.map((line, index) => (
                        <p key={`check-summary-${index}`} className="template-input-guidance-text" style={{ margin: '4px 0' }}>
                          • {line}
                        </p>
                      ))}
                    </div>
                  )}
                  {effectiveTemplateCheckConfig.checkType && effectiveTemplateCheckConfig.checkTypeParams && (
                    <>
                      <button
                        type="button"
                        className="technical-details-toggle"
                        onClick={() => setShowTechnicalDetails((prev) => !prev)}
                        aria-expanded={showTechnicalDetails}
                      >
                        <AppIcon name="document" />
                        <span>{showTechnicalDetails ? 'Hide advanced details' : 'Show advanced details'}</span>
                      </button>
                      {showTechnicalDetails && (
                        <div className="technical-details-panel">
                          <p className="template-input-guidance-text" style={{ marginBottom: '6px' }}>
                            <strong>Business check type:</strong> {businessCheckTypeLabel}
                          </p>
                          <p className="template-input-guidance-text" style={{ marginBottom: '6px' }}>
                            <strong>Engine mapping:</strong> {effectiveTemplateCheckConfig.checkType}
                          </p>
                          <p className="template-input-guidance-text" style={{ marginBottom: '6px' }}>
                            <strong>Attribute context:</strong>
                          </p>
                          {selectedAttributeSummaries.length > 0 ? (
                            <div style={{ marginBottom: '8px', paddingLeft: '12px' }}>
                              {selectedAttributeSummaries.map((attribute) => (
                                <p key={`technical-attribute-${attribute.id}`} className="template-input-guidance-text" style={{ margin: '3px 0' }}>
                                  • {attribute.name}
                                  {attribute.dataObjectName ? ` | object: ${attribute.dataObjectName}` : ''}
                                  {attribute.dataObjectVersion
                                    ? ` | version: ${attribute.dataObjectVersion}`
                                    : attribute.versionId
                                    ? ` | versionId: ${attribute.versionId}`
                                    : ''}
                                </p>
                              ))}
                            </div>
                          ) : (
                            <p className="template-input-guidance-text" style={{ marginBottom: '8px' }}>
                              No attributes selected.
                            </p>
                          )}
                          <pre className="technical-details-json">{JSON.stringify(effectiveTemplateCheckConfig.checkTypeParams, null, 2)}</pre>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              <div className="preview-actions">
                <Button
                  className="preview-action-btn"
                  variant="secondary-default"
                  onClick={() => {
                    if (selectedWizardStep === 4) {
                      setSelectedWizardStep(3)
                      return
                    }
                    setSelectedTemplate(null)
                    setSelectedWizardStep(3)
                  }}
                >
                  <AppIcon slot="icon" name="arrow-left" />
                  {selectedWizardStep === 4 ? 'Back to Step 3' : 'Back to Templates'}
                </Button>

                <Button
                  className="preview-action-btn"
                  variant="primary-default"
                  disabled={selectedWizardStep === 3 && requiresAttributeSelection && selectedAttributeIds.size === 0}
                  onClick={async () => {
                    if (selectedWizardStep === 3) {
                      const normalizedName = await validateStep3Inputs()
                      if (!normalizedName) return
                      setSelectedWizardStep(4)
                      return
                    }
                    await handleConfirmCreate()
                  }}
                >
                  <AppIcon slot="icon" name={selectedWizardStep === 3 ? 'arrow-right' : 'check'} />
                  {selectedWizardStep === 3 ? 'Continue to Summary' : (isEditMode ? 'Confirm & Update Rule' : 'Confirm & Create Rule')}
                </Button>
              </div>

              {nameValidationMessage && (
                <p className="check-type-form-hint" style={{ color: 'var(--dq-status-error-text, #c62828)', marginTop: '0.5rem' }}>
                  {nameValidationMessage}
                </p>
              )}
            </div>
          </div>
        </div>
        </div>

        <TemplateAttributeCatalogPickerModal
          isOpen={isAttributeCatalogPickerOpen}
          onClose={() => setIsAttributeCatalogPickerOpen(false)}
          attributeOptions={attributeOptions}
          selectedAttributeIds={Array.from(selectedAttributeIds)}
          onApply={(attributeIds) => {
            setSelectedAttributeIds(new Set(normalizeSelectedAttributeIds(attributeIds)))
            setNameValidationMessage('')
          }}
        />
      </>
    )
  }

  // Show template selection grid
  return (
    <div className="modal-overlay templates-overlay" onClick={onClose}>
      <div className="templates-modal" onClick={(e) => e.stopPropagation()}>
        <div className="templates-header">
          <h2>{isEditMode ? 'Edit Rule Wizard' : 'New Rule Wizard'}</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="wizard-steps" aria-label="New rule wizard progress">
          <span className="wizard-step wizard-step-active">1. DAMA</span>
          <span className="wizard-step wizard-step-active">2. Template</span>
          <span className="wizard-step">3. Attributes & {isEditMode ? 'Update' : 'Create'}</span>
        </div>

        <div className="templates-content">
          <p className="wizard-step-hint">Step 1: Choose a DAMA dimension</p>
          <div className="dimension-filters">
            <button
              className={`dimension-btn ${selectedDimension === null ? 'active' : ''}`}
              onClick={() => setSelectedDimension(null)}
            >
              All Dimensions
            </button>
            {dimensions.map(dim => (
              <button
                key={dim}
                className={`dimension-btn ${selectedDimension === dim ? 'active' : ''}`}
                onClick={() => setSelectedDimension(dim)}
              >
                <AppIcon name={dimensionIcons[dim]} />
                <span>{dimensionLabels[dim]}</span>
              </button>
            ))}
          </div>

          <p className="wizard-step-hint">Step 2: Select a template</p>
          <div className="templates-grid">
            {filteredTemplates.map(template => (
              <div
                key={template.id}
                className="template-card"
                onClick={() => {
                  setSelectedTemplate(template)
                  setPreviewName(template.name)
                  setPreviewDescription(template.description)
                  setPreviewRiskLevel(template.defaultRiskLevel)
                  setTemplatePatternInput(String(template.templateRuleDefinition?.expectedValues?.pattern || ''))
                  setTemplateFlagsInput('')
                  setTemplateThresholdInput(Number(template.templateRuleDefinition?.threshold ?? ''))
                  const derivedCheckType = deriveDefaultCheckType(template, 'value')
                  setSelectedCheckType(derivedCheckType?.checkType || '')
                  setCheckTypeParams(derivedCheckType?.checkTypeParams || {})
                  setNameValidationMessage('')
                  setCheckTypeFieldErrors({})
                  setSelectedWizardStep(3)
                  setShowTechnicalDetails(false)
                }}
              >
                <div className="template-icon">
                  <AppIcon name={template.icon || 'document'} />
                </div>
                <div className="template-content">
                  <h3>{template.name}</h3>
                  <p className="template-description">{template.description}</p>
                  <div className="template-meta">
                    <span className="template-dimension">{dimensionLabels[template.dimension]}</span>
                    <span className={`template-risk risk-${template.defaultRiskLevel}`}>
                      {template.defaultRiskLevel.toUpperCase()}
                    </span>
                  </div>
                  <p className="template-example">
                    <strong>Example:</strong> {template.exampleUse}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

interface TemplatesTabProps {
  onUseTemplate: (template: RuleTemplate) => void
  viewScope?: 'my' | 'team' | 'all' | 'global'
}

export const TemplatesTab: React.FC<TemplatesTabProps> = ({ onUseTemplate, viewScope = 'my' }) => {
  const [selectedDimension, setSelectedDimension] = useState<DAMADimension | null>(null)
  const [selectedViewScope, setSelectedViewScope] = useState<'my' | 'team' | 'all' | 'global'>(viewScope)

  useEffect(() => {
    setSelectedViewScope(viewScope)
  }, [viewScope])

  const dimensions: DAMADimension[] = ['completeness', 'accuracy', 'consistency', 'timeliness', 'validity', 'uniqueness']
  const dimensionLabels: Record<DAMADimension, string> = {
    completeness: 'Completeness',
    accuracy: 'Accuracy',
    consistency: 'Consistency',
    timeliness: 'Timeliness',
    validity: 'Validity',
    uniqueness: 'Uniqueness',
  }

  const dimensionIcons: Record<DAMADimension, AppIconName> = {
    completeness: 'exclamation-circle',
    accuracy: 'check-circle',
    consistency: 'link',
    timeliness: 'clock',
    validity: 'info-circle',
    uniqueness: 'padlock-closed',
  }

  const scopeDescription: Record<'my' | 'team' | 'all' | 'global', string> = {
    my: 'No personal templates found yet. Shared templates are available under All Templates.',
    team: 'No team templates found yet. Shared templates are available under All Templates.',
    all: 'Showing all templates available in this workspace.',
    global: 'Showing templates shared across all workspaces.',
  }

  const scopedTemplates = useMemo(() => {
    if (selectedViewScope === 'my' || selectedViewScope === 'team') {
      return [] as RuleTemplate[]
    }

    return DAMA_TEMPLATES
  }, [selectedViewScope])

  const filteredTemplates = useMemo(() => {
    if (!selectedDimension) return scopedTemplates
    return scopedTemplates.filter((t) => t.dimension === selectedDimension)
  }, [selectedDimension, scopedTemplates])

  return (
    <div className="templates-tab-content">
      <div className="templates-header">
        <h2>Rule Templates (DAMA Dimensions)</h2>
        <p className="templates-description">
          Explore pre-built rule templates based on data quality dimensions. Use these as a starting point for your custom rules.
        </p>
        <WorkspaceScopeSegmentedControl
          value={selectedViewScope}
          onChange={setSelectedViewScope}
          ariaLabel="Templates scope"
          label="Show:"
          className="templates-scope-group"
          controlClassName="templates-scope-control"
        />
      </div>

      <div className="dimension-filters">
        <button
          className={`dimension-btn ${selectedDimension === null ? 'active' : ''}`}
          onClick={() => setSelectedDimension(null)}
        >
          All Dimensions
        </button>
        {dimensions.map(dim => (
          <button
            key={dim}
            className={`dimension-btn ${selectedDimension === dim ? 'active' : ''}`}
            onClick={() => setSelectedDimension(dim)}
          >
            <AppIcon name={dimensionIcons[dim]} />
            <span>{dimensionLabels[dim]}</span>
          </button>
        ))}
      </div>

      {filteredTemplates.length === 0 ? (
        <div className="templates-empty-state">
          <p>{scopeDescription[selectedViewScope]}</p>
        </div>
      ) : (
        <div className="templates-grid">
          {filteredTemplates.map(template => (
            <div key={template.id} className="template-card">
              <div className="template-icon">
                <AppIcon name={template.icon || 'document'} />
              </div>
              <div className="template-content">
                <h3>{template.name}</h3>
                <p className="template-description">{template.description}</p>
                <div className="template-meta">
                  <span className="template-category">{template.category}</span>
                  <span className={`template-risk risk-${template.defaultRiskLevel}`}>
                    {template.defaultRiskLevel.toUpperCase()}
                  </span>
                </div>
                <p className="template-example">
                  <strong>Example:</strong> {template.exampleUse}
                </p>
                <button
                  className="template-use-btn"
                  onClick={() => {
                    onUseTemplate(template)
                  }}
                >
                  Use Template
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
