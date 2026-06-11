import { useCallback, useState } from 'react'
import { Rule } from '../../types/rules'
import { RuleTemplate } from '../../types/templates'
import { toApiGroupV1Base } from '../../config/api'

const isRuleTemplate = (value: unknown): value is RuleTemplate => {
  if (!value || typeof value !== 'object') {
    return false
  }

  const candidate = value as any
  const dimension = String(candidate.dimension || '').trim()
  const allowedDimensions = new Set([
    'completeness',
    'accuracy',
    'consistency',
    'timeliness',
    'validity',
    'uniqueness',
  ])

  return (
    typeof candidate.id === 'string' &&
    typeof candidate.name === 'string' &&
    typeof candidate.description === 'string' &&
    allowedDimensions.has(dimension)
  )
}

export const classifyRuleSaveError = (message: string): { message: string; kind: 'duplicate_name' | 'locked_version' } | null => {
  const normalizedMessage = String(message || '').toLowerCase()

  if (normalizedMessage.includes('409') && normalizedMessage.includes('approved')) {
    return {
      message: 'This rule version is approved and can no longer be changed.',
      kind: 'locked_version',
    }
  }

  if (normalizedMessage.includes('409') || normalizedMessage.includes('already exists')) {
    return {
      message: 'Rule name must be unique within workspace.',
      kind: 'duplicate_name',
    }
  }

  return null
}

export interface TemplateWizardCustomizations {
  name: string
  description: string
  comments?: string
  riskLevel: 'low' | 'medium' | 'high'
  attributeIds: string[]
  checkType?: Rule['checkType']
  checkTypeParams?: Rule['checkTypeParams']
  templateInputs?: {
    pattern?: string
    flags?: string
    threshold?: number
    expressionOverride?: string
    useAdvancedExpression?: boolean
    manualOverrideConfirmed?: boolean
  }
}

interface RuleNotice {
  type: 'success' | 'error'
  message: string
  ruleId?: string
}

interface UseRuleTemplateFlowParams {
  authToken: string | null
  apiBaseUrl?: string
  currentWorkspaceId: string | null
  attributeCatalog: Record<string, { name: string }>
  ruleAttributeMappings: Record<string, string[]>
  workspaceRules: Rule[]
  fetchedRulesById: Record<string, Rule>
  createRule: (rule: Omit<Rule, 'id' | 'createdAt' | 'updatedAt'>) => Promise<Rule>
  updateRule: (ruleId: string, updates: Partial<Rule>) => Promise<Rule>
  assignAttributesToRule: (ruleId: string, attributeIds: string[]) => Promise<void>
  showNotice: (notice: RuleNotice) => void
  onRuleFocused: (ruleId: string) => void
}

export const useRuleTemplateFlow = ({
  authToken,
  apiBaseUrl,
  currentWorkspaceId,
  attributeCatalog,
  ruleAttributeMappings,
  workspaceRules,
  fetchedRulesById,
  createRule,
  updateRule,
  assignAttributesToRule,
  showNotice,
  onRuleFocused,
}: UseRuleTemplateFlowParams) => {
  const [showTemplateSelector, setShowTemplateSelector] = useState(false)
  const [templatePreviewData, setTemplatePreviewData] = useState<RuleTemplate | null>(null)
  const [templateInitialCustomizations, setTemplateInitialCustomizations] = useState<TemplateWizardCustomizations | undefined>(undefined)
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null)

  const openCreateRuleWizard = useCallback((initialTemplate?: RuleTemplate | null) => {
    setEditingRuleId(null)
    setTemplateInitialCustomizations(undefined)

    // React click handlers will pass a MouseEvent as the first argument when the callback
    // is used directly as an `onClick` handler. We must ignore non-template values.
    const normalizedTemplate = isRuleTemplate(initialTemplate) ? initialTemplate : null
    setTemplatePreviewData(normalizedTemplate)
    setShowTemplateSelector(true)
  }, [])

  const closeTemplateWizard = useCallback(() => {
    setShowTemplateSelector(false)
    setTemplatePreviewData(null)
    setTemplateInitialCustomizations(undefined)
    setEditingRuleId(null)
  }, [])

  const handleSelectTemplate = useCallback(async (
    template: RuleTemplate,
    customizations?: TemplateWizardCustomizations
  ): Promise<{ ok: boolean; message?: string }> => {
    const ruleName = String(customizations?.name || template.name || '').trim()
    const ruleDescription = String(customizations?.description || template.description || '').trim()
    const selectedAttributeIds = Array.isArray(customizations?.attributeIds) ? customizations.attributeIds : []

    if (!ruleName) {
      showNotice({ type: 'error', message: 'Rule name is required.' })
      return { ok: false, message: 'Rule name is required.' }
    }

    const workspaceId = String(currentWorkspaceId || '').trim()
    if (!workspaceId) {
      const message = 'No active workspace selected. Please select a workspace and try again.'
      showNotice({ type: 'error', message })
      return { ok: false, message }
    }

    try {
      if (authToken) {
        const duplicateCheckParams = new URLSearchParams({
          page: '1',
          limit: '100',
          workspace: workspaceId,
          q: ruleName,
        })

        const duplicateCheckResponse = await fetch(
          `${toApiGroupV1Base('rulebuilder', apiBaseUrl)}/rules?${duplicateCheckParams.toString()}`,
          {
            headers: {
              Authorization: `Bearer ${authToken}`,
            },
          }
        )

        if (duplicateCheckResponse.ok) {
          const duplicateBody = await duplicateCheckResponse.json()
          const duplicateRows = Array.isArray(duplicateBody?.data)
            ? duplicateBody.data
            : (Array.isArray(duplicateBody) ? duplicateBody : [])
          const normalizedCandidate = ruleName.trim().toLowerCase()
          const hasDuplicate = duplicateRows.some((row: any) => {
            const isTemplateRow = Boolean(row?.is_template ?? row?.isTemplate)
            if (isTemplateRow) return false
            if (editingRuleId && String(row?.id || '') === String(editingRuleId)) return false
            const existingName = String(row?.name || '').trim().toLowerCase()
            return existingName === normalizedCandidate
          })

          if (hasDuplicate) {
            const message = 'Rule name must be unique within workspace.'
            showNotice({ type: 'error', message })
            return { ok: false, message }
          }
        }
      }
    } catch {
      // Ignore preflight failures; create endpoint remains source of truth.
    }

    const firstAttribute = selectedAttributeIds[0]
      ? String(attributeCatalog[selectedAttributeIds[0]]?.name || '').trim() || 'value'
      : 'value'

    let checkType: Rule['checkType'] | undefined
    let checkTypeParams: Rule['checkTypeParams'] | undefined
    let expression = '1 = 1'
    const useAdvancedExpression = Boolean(customizations?.templateInputs?.useAdvancedExpression)
    const manualOverrideConfirmed = Boolean(customizations?.templateInputs?.manualOverrideConfirmed)
    const expressionOverride = String(customizations?.templateInputs?.expressionOverride || '').trim()

    if (customizations?.checkType && customizations?.checkTypeParams) {
      checkType = customizations.checkType
      checkTypeParams = {
        ...customizations.checkTypeParams,
      } as Rule['checkTypeParams']

      if (Array.isArray((checkTypeParams as any)?.attributes)) {
        const mappedAttributes = selectedAttributeIds.length > 0
          ? selectedAttributeIds.map((id) => String(attributeCatalog[id]?.name || '').trim() || firstAttribute)
          : [(checkTypeParams as any).attributes?.[0] || firstAttribute]
        ;(checkTypeParams as any).attributes = mappedAttributes
      } else if (typeof (checkTypeParams as any)?.attribute === 'string') {
        ;(checkTypeParams as any).attribute = firstAttribute
      }
    }

    if (!checkType && template.ruleType === 'threshold') {
      const threshold = Number(customizations?.templateInputs?.threshold ?? template.templateRuleDefinition?.threshold ?? 95)
      checkType = 'THRESHOLD'
      checkTypeParams = {
        checkType: 'THRESHOLD',
        attribute: firstAttribute,
        metric: 'null_pct',
        operator: 'gte',
        threshold,
      }
      expression = `${firstAttribute} IS NOT NULL`
    } else if (!checkType && template.ruleType === 'regex') {
      const pattern = String(customizations?.templateInputs?.pattern || template.templateRuleDefinition?.expectedValues?.pattern || '.*')
      const flags = String(customizations?.templateInputs?.flags || '')
      checkType = 'REGEX'
      checkTypeParams = {
        checkType: 'REGEX',
        attribute: firstAttribute,
        pattern,
        flags,
      }
      expression = flags
        ? `REGEXP_MATCHES(${firstAttribute}, '${pattern}', '${flags}')`
        : `REGEXP_MATCHES(${firstAttribute}, '${pattern}')`
    }

    if (useAdvancedExpression && expressionOverride) {
      expression = expressionOverride
    }

    const damaToRuleDimension: Record<string, Rule['dimension']> = {
      completeness: 'Completeness',
      accuracy: 'Accuracy',
      consistency: 'Consistency',
      timeliness: 'Timeliness',
      validity: 'Validity',
      uniqueness: 'Uniqueness',
    }

    if (editingRuleId) {
      try {
        const updatePayload: Partial<Rule> = {
          name: ruleName,
          description: ruleDescription,
          comments: String(customizations?.comments || '').trim() || undefined,
          dimension: damaToRuleDimension[template.dimension] || 'Validity',
          active: false,
          generated: !useAdvancedExpression,
          manualOverrideConfirmed: useAdvancedExpression ? manualOverrideConfirmed : undefined,
          checkType,
          checkTypeParams,
        }

        if (useAdvancedExpression && expressionOverride) {
          updatePayload.expression = expressionOverride
        }

        const updatedRule = await updateRule(editingRuleId, {
          ...updatePayload,
        } as Partial<Rule>)

        onRuleFocused(updatedRule.id)
        setShowTemplateSelector(false)
        setTemplatePreviewData(null)
        setTemplateInitialCustomizations(undefined)
        setEditingRuleId(null)

        showNotice({ type: 'success', message: `Rule '${updatedRule.name}' updated.`, ruleId: updatedRule.id })

        if (selectedAttributeIds.length > 0) {
          try {
            await assignAttributesToRule(updatedRule.id, selectedAttributeIds)
          } catch {
            showNotice({
              type: 'error',
              message: 'Rule updated, but mapping business terms failed. You can map business terms from the rule details.',
            })
          }
        }

        return { ok: true }
      } catch (error: any) {
        const message = String(error?.message || '')
        const detailMessage = message
          .replace(/^Failed to update rule \(\d+\):\s*/i, '')
          .replace(/^Failed to create rule \(\d+\):\s*/i, '')
          .trim()
        const classifiedError = classifyRuleSaveError(detailMessage || message)
        if (classifiedError) {
          return { ok: false, message: classifiedError.message }
        }
        const failureMessage = detailMessage || 'Failed to update rule.'
        return { ok: false, message: failureMessage }
      }
    }

    try {
      const createdRule = await createRule({
        workspace: workspaceId,
        name: ruleName,
        description: ruleDescription,
        comments: String(customizations?.comments || '').trim() || undefined,
        expression,
        dimension: damaToRuleDimension[template.dimension] || 'Validity',
        active: false,
        generated: !useAdvancedExpression,
        manualOverrideConfirmed: useAdvancedExpression ? manualOverrideConfirmed : undefined,
        is_template: false,
        status: 'draft',
        attributes: [],
        riskLevel: customizations?.riskLevel || template.defaultRiskLevel,
        joinConditions: [],
        checkType,
        checkTypeParams,
      } as Omit<Rule, 'id' | 'createdAt' | 'updatedAt'>)

      onRuleFocused(createdRule.id)
      setShowTemplateSelector(false)
      setTemplatePreviewData(null)
      setTemplateInitialCustomizations(undefined)
      setEditingRuleId(null)

      showNotice({ type: 'success', message: `Rule '${createdRule.name}' created.`, ruleId: createdRule.id })

      if (selectedAttributeIds.length > 0) {
        try {
          await assignAttributesToRule(createdRule.id, selectedAttributeIds)
        } catch {
          showNotice({
            type: 'error',
            message: 'Rule created, but mapping business terms failed. You can map business terms from the rule details.',
          })
        }
      }
      return { ok: true }
    } catch (error: any) {
      const message = String(error?.message || '')
      const detailMessage = message
        .replace(/^Failed to update rule \(\d+\):\s*/i, '')
        .replace(/^Failed to create rule \(\d+\):\s*/i, '')
        .trim()
      const classifiedError = classifyRuleSaveError(detailMessage || message)
      if (classifiedError) {
        showNotice({ type: 'error', message: classifiedError.message })
        return { ok: false, message: classifiedError.message }
      }
      const failureMessage = detailMessage || 'Failed to create rule from template.'
      showNotice({ type: 'error', message: failureMessage })
      return { ok: false, message: failureMessage }
    }
  }, [
    editingRuleId,
    authToken,
    currentWorkspaceId,
    apiBaseUrl,
    attributeCatalog,
    updateRule,
    createRule,
    assignAttributesToRule,
    onRuleFocused,
    showNotice,
  ])

  const openEditRuleWizard = useCallback((ruleId: string) => {
    const targetRule = workspaceRules.find((item) => item.id === ruleId) || fetchedRulesById[ruleId]
    if (!targetRule) return

    const dimensionMap: Record<string, RuleTemplate['dimension']> = {
      completeness: 'completeness',
      accuracy: 'accuracy',
      consistency: 'consistency',
      timeliness: 'timeliness',
      validity: 'validity',
      uniqueness: 'uniqueness',
    }
    const normalizedDimension = String(targetRule.dimension || 'Validity').trim().toLowerCase()
    const templateDimension = dimensionMap[normalizedDimension] || 'validity'

    const normalizedCheckType = String(targetRule.checkType || '').trim().toUpperCase()
    const ruleType: RuleTemplate['ruleType'] =
      normalizedCheckType === 'THRESHOLD'
        ? 'threshold'
        : normalizedCheckType === 'REGEX'
        ? 'regex'
        : normalizedCheckType === 'RANGE'
        ? 'range'
        : 'custom'

    const editTemplate: RuleTemplate = {
      id: `template-edit-${targetRule.id}`,
      name: `Edit ${targetRule.name}`,
      description: targetRule.description || 'Edit existing rule',
      dimension: templateDimension,
      category: 'Rule Edit',
      defaultRiskLevel: targetRule.riskLevel || 'medium',
      ruleType,
      templateRuleDefinition: {
        description: targetRule.description || '',
        attributes: [],
      },
      exampleUse: 'Edit existing rule configuration',
      icon: 'document',
    }

    const attributeIds = Array.isArray(ruleAttributeMappings[targetRule.id])
      ? ruleAttributeMappings[targetRule.id]
      : []

    const params: any = targetRule.checkTypeParams || {}
    const initialCustomizations: TemplateWizardCustomizations = {
      name: targetRule.name,
      description: targetRule.description || '',
      riskLevel: targetRule.riskLevel || 'medium',
      attributeIds,
      checkType: targetRule.checkType,
      checkTypeParams: targetRule.checkTypeParams,
      templateInputs: {
        pattern: typeof params.pattern === 'string' ? params.pattern : undefined,
        flags: typeof params.flags === 'string' ? params.flags : undefined,
        threshold: typeof params.threshold === 'number' ? params.threshold : undefined,
      },
    }

    setEditingRuleId(targetRule.id)
    setTemplatePreviewData(editTemplate)
    setTemplateInitialCustomizations(initialCustomizations)
    setShowTemplateSelector(true)
  }, [workspaceRules, fetchedRulesById, ruleAttributeMappings])

  return {
    showTemplateSelector,
    templatePreviewData,
    templateInitialCustomizations,
    editingRuleId,
    openCreateRuleWizard,
    closeTemplateWizard,
    handleSelectTemplate,
    openEditRuleWizard,
  }
}
