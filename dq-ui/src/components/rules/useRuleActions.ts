import { useCallback } from 'react'
import { Rule, RuleApproval, RuleJoinDefinition } from '../../types/rules'
import { useAsyncRequests } from '../../hooks/useAsyncRequests'

export interface RuleActionHandlers {
  handleSubmitForApproval: (comments?: string) => Promise<void>
  handleDeactivateRule: () => Promise<void>
  handleApproval: (comments?: string) => Promise<void>
  handleRejection: (comments: string) => Promise<void>
  handleActivateRule: () => Promise<void>
  handleSaveTemplate: (name: string, description: string) => Promise<void>
  handleAssignAttributes: (
    attributeIds: string[],
    aliasMappings?: Record<string, { attributeId: string; expectedDataType?: string; actualDataType?: string; compatible?: boolean }>,
    thresholdOverrides?: Record<string, number | undefined>
  ) => Promise<void>
  handleAssignReusableFilter: (filterIds: string[]) => Promise<void>
  handleAssignReusableJoin: (joinId: string | null) => Promise<void>
  handleSaveJoinConditions: (joinConditions: RuleJoinDefinition[]) => Promise<void>
  handleCopyJoinExpression: (ruleId: string, expression: string) => Promise<void>
  handleCopyCompleteExpression: (ruleId: string, expression: string) => Promise<void>
  handleTestRule: (request: {
    sampleCount: number
    versionId: string
    semanticMatching?: {
      enabled: boolean
      fieldAliasMappings?: Record<string, string>
      activeSynonyms?: string[]
      inactiveSynonyms?: string[]
    }
    selectedAttributes: Array<{
      id: string
      name: string
      versionId?: string | null
      dataObjectName?: string
    }>
  }) => Promise<{ taskId: string }>
  handleValidateRule: (ruleId: string) => Promise<void>
  handleToggleBulkSelect: (ruleId: string) => void
  handleBulkApprove: () => Promise<void>
  handleBulkActivate: () => Promise<void>
}

interface BulkActionResult {
  processed: string[]
  skipped: string[]
  failed: Array<{ ruleId: string; reason: string }>
}

interface UseRuleActionsProps {
  rules: Rule[]
  approvals: RuleApproval[]
  activeModalRule: string | null
  activeRule: Rule | undefined
  selectedBulkRuleIds: Set<string>
  bulkApproveRuleIds?: string[]
  bulkActivateRuleIds?: string[]
  submitForApproval: (ruleId: string, comments?: string) => Promise<void>
  requestRuleDeactivation: (ruleId: string, comments?: string) => Promise<void>
  approveRule: (ruleId: string, comments?: string) => Promise<void>
  rejectRule: (ruleId: string, comments: string) => Promise<void>
  activateRule: (ruleId: string) => Promise<void>
  updateRule: (ruleId: string, updates: any) => Promise<any>
  logTestAction: (ruleId: string, testData: any) => Promise<void>
  saveRuleAsTemplate: (ruleId: string, name: string, description: string) => Promise<void>
  assignAttributesToRule: (ruleId: string, attributeIds: string[], thresholdOverrides?: Record<string, number | undefined>) => Promise<void>
  validateRuleComposition: (ruleId: string) => Promise<any>
  onModalClose: () => void
  setSelectedBulkRuleIds: (ids: Set<string>) => void
  showNotice: (notice: {
    type: 'success' | 'error'
    message: string
    ruleId?: string
    details?: string[]
    context?: 'test' | 'validation' | 'copy' | 'general'
  }) => void
  setValidationStateByRuleId: (updater: (prev: Record<string, 'valid' | 'invalid' | 'upstream-error'>) => Record<string, 'valid' | 'invalid' | 'upstream-error'>) => void
  setCompiledExpressionByRuleId: (updater: (prev: Record<string, string>) => Record<string, string>) => void
  setValidationDiagnosticsModal: (modal: { result: any; ruleName: string } | null) => void
  settings: any
}

const errorMessage = (error: unknown): string => {
  if (error instanceof Error && error.message) return error.message
  return String(error || 'Unknown error')
}

const summarizeBulkAction = (label: string, result: BulkActionResult): string => {
  return `${label}: ${result.processed.length} processed, ${result.skipped.length} skipped, ${result.failed.length} failed.`
}

const copyTextToClipboard = async (value: string) => {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value)
    return
  }

  const textArea = document.createElement('textarea')
  textArea.value = value
  textArea.setAttribute('readonly', '')
  textArea.style.position = 'fixed'
  textArea.style.opacity = '0'
  document.body.appendChild(textArea)
  textArea.select()
  const copied = document.execCommand('copy')
  document.body.removeChild(textArea)

  if (!copied) {
    throw new Error('Copy failed')
  }
}

const hasUpstreamValidationIssue = (result: any): boolean => {
  const diagnostics = Array.isArray(result?.diagnostics) ? result.diagnostics : []
  return diagnostics.some((d: any) => {
    const msg = String(d?.message || '').toLowerCase()
    return msg.includes('invalid response was received from the upstream server')
      || msg.includes('upstream server')
      || msg.includes('econnrefused')
      || msg.includes('enotfound')
      || msg.includes('timed out')
  })
}

export const useRuleActions = (props: UseRuleActionsProps): RuleActionHandlers => {
  const {
    activeModalRule,
    activeRule,
    approvals,
    selectedBulkRuleIds,
    bulkApproveRuleIds = [],
    bulkActivateRuleIds = [],
    submitForApproval,
    requestRuleDeactivation,
    approveRule,
    rejectRule,
    activateRule,
    updateRule,
    logTestAction,
    saveRuleAsTemplate,
    assignAttributesToRule,
    validateRuleComposition,
    onModalClose,
    setSelectedBulkRuleIds,
    showNotice,
    setValidationStateByRuleId,
    setCompiledExpressionByRuleId,
    setValidationDiagnosticsModal,
    settings,
  } = props
  const { startRuleTest } = useAsyncRequests()

  const getPendingApprovalForActiveRule = useCallback((): RuleApproval | undefined => {
    if (!activeModalRule) return undefined

    const pendingForRule = approvals.filter(
      (a) => String(a.ruleId) === String(activeModalRule) && a.status === 'pending'
    )

    if (pendingForRule.length === 0) return undefined

    // Prefer approvals from the same workspace when both sides expose it.
    const workspaceMatched = activeRule?.workspace
      ? pendingForRule.filter((a) => String(a.workspaceId) === String(activeRule.workspace))
      : pendingForRule

    const candidates = workspaceMatched.length > 0 ? workspaceMatched : pendingForRule

    // If multiple pending approvals exist, use the most recently requested one.
    return [...candidates].sort(
      (a, b) => new Date(b.requestedAt).getTime() - new Date(a.requestedAt).getTime()
    )[0]
  }, [activeModalRule, approvals, activeRule])

  const handleSubmitForApproval = useCallback(
    async (comments?: string) => {
      if (!activeModalRule) return
      try {
        await submitForApproval(activeModalRule, comments)
        onModalClose()
      } catch (error) {
        console.error('Submit for approval failed:', error)
      }
    },
    [activeModalRule, submitForApproval, onModalClose]
  )

  const handleApproval = useCallback(
    async (comments?: string) => {
      if (!activeModalRule) return
      const pendingApproval = getPendingApprovalForActiveRule()
      if (!pendingApproval) {
        showNotice({ type: 'error', message: 'No pending approval found for this rule. Please refresh and try again.' })
        throw new Error('No pending approval found')
      }
      await approveRule(pendingApproval.id, comments)
      onModalClose()
    },
    [activeModalRule, getPendingApprovalForActiveRule, approveRule, onModalClose, showNotice]
  )

  const handleDeactivateRule = useCallback(
    async () => {
      if (!activeModalRule) return
      try {
        await requestRuleDeactivation(activeModalRule)
        onModalClose()
        showNotice({
          type: 'success',
          message: 'Deactivation request submitted. Awaiting approval.',
          ruleId: activeModalRule,
        })
      } catch (error) {
        console.error('Deactivate rule failed:', error)
        showNotice({
          type: 'error',
          message: 'Failed to request rule deactivation.',
          ruleId: activeModalRule,
        })
      }
    },
    [activeModalRule, requestRuleDeactivation, onModalClose, showNotice]
  )

  const handleRejection = useCallback(
    async (comments: string) => {
      if (!activeModalRule) return
      const pendingApproval = getPendingApprovalForActiveRule()
      if (!pendingApproval) {
        showNotice({ type: 'error', message: 'No pending approval found for this rule. Please refresh and try again.' })
        throw new Error('No pending approval found')
      }
      await rejectRule(pendingApproval.id, comments)
      onModalClose()
    },
    [activeModalRule, getPendingApprovalForActiveRule, rejectRule, onModalClose, showNotice]
  )

  const handleActivateRule = useCallback(
    async () => {
      if (!activeModalRule) return
      try {
        await activateRule(activeModalRule)
        onModalClose()
      } catch (error) {
        console.error('Activate rule failed:', error)
      }
    },
    [activeModalRule, activateRule, onModalClose]
  )

  const handleSaveTemplate = useCallback(
    async (name: string, description: string) => {
      if (!activeModalRule) return
      try {
        await saveRuleAsTemplate(activeModalRule, name, description)
        onModalClose()
      } catch (error) {
        console.error('Save template failed:', error)
      }
    },
    [activeModalRule, saveRuleAsTemplate, onModalClose]
  )

  const handleAssignAttributes = useCallback(
    async (
      attributeIds: string[],
      aliasMappings?: Record<string, { attributeId: string; expectedDataType?: string; actualDataType?: string; compatible?: boolean }>,
      thresholdOverrides?: Record<string, number | undefined>
    ) => {
      if (!activeModalRule) return
      try {
        await assignAttributesToRule(activeModalRule, attributeIds, thresholdOverrides)
        if (aliasMappings) {
          await updateRule(activeModalRule, { aliasMappings })
        }
        onModalClose()
        showNotice({
          type: 'success',
          message: 'Technical attributes and business-term mappings saved.',
          ruleId: activeModalRule,
        })
      } catch (error) {
        console.error('Assign attributes failed:', error)
        showNotice({
          type: 'error',
          message: 'Failed to save technical attributes and business terms.',
          ruleId: activeModalRule,
        })
      }
    },
    [activeModalRule, assignAttributesToRule, updateRule, onModalClose, showNotice]
  )

  const handleAssignReusableFilter = useCallback(
    async (filterIds: string[]) => {
      if (!activeModalRule) return
      try {
        await updateRule(activeModalRule, { reusableFilterIds: filterIds })
        onModalClose()
        showNotice({
          type: 'success',
          message: filterIds.length > 0
            ? `Reusable filters assigned to rule (${filterIds.length})`
            : 'Reusable filters removed from rule',
          ruleId: activeModalRule,
        })
      } catch (error) {
        console.error('Assign reusable filter failed:', error)
        showNotice({
          type: 'error',
          message: 'Failed to assign reusable filters',
          ruleId: activeModalRule,
        })
      }
    },
    [activeModalRule, updateRule, onModalClose, showNotice]
  )

  const handleAssignReusableJoin = useCallback(
    async (joinId: string | null) => {
      if (!activeModalRule) return
      try {
        await updateRule(activeModalRule, { reusableJoinId: joinId })
        onModalClose()
        showNotice({
          type: 'success',
          message: joinId ? 'Reusable join assigned to rule' : 'Reusable join removed from rule',
          ruleId: activeModalRule,
        })
      } catch (error) {
        console.error('Assign reusable join failed:', error)
        showNotice({
          type: 'error',
          message: 'Failed to assign reusable join',
          ruleId: activeModalRule,
        })
      }
    },
    [activeModalRule, updateRule, onModalClose, showNotice]
  )

  const handleSaveJoinConditions = useCallback(
    async (joinConditions: RuleJoinDefinition[]) => {
      if (!activeModalRule) return
      try {
        await updateRule(activeModalRule, { joinConditions })
        onModalClose()
        const totalConditions = joinConditions.reduce(
          (count, definition) => count + (Array.isArray(definition.conditions) ? definition.conditions.length : 0),
          0
        )
        showNotice({
          type: 'success',
          message:
            joinConditions.length > 0
              ? `Join conditions updated (${joinConditions.length} join${joinConditions.length === 1 ? '' : 's'}, ${totalConditions} condition${totalConditions === 1 ? '' : 's'})`
              : 'Join conditions cleared',
          ruleId: activeModalRule,
        })
      } catch (error) {
        console.error('Save join conditions failed:', error)
        showNotice({
          type: 'error',
          message: 'Failed to save join conditions',
          ruleId: activeModalRule,
        })
      }
    },
    [activeModalRule, updateRule, onModalClose, showNotice]
  )

  const handleCopyJoinExpression = useCallback(
    async (ruleId: string, expression: string) => {
      if (!expression) return
      try {
        await copyTextToClipboard(expression)
        showNotice({ type: 'success', message: 'Join expression copied to clipboard.', ruleId })
      } catch {
        showNotice({ type: 'error', message: 'Failed to copy join expression.', ruleId })
      }
    },
    [showNotice]
  )

  const handleCopyCompleteExpression = useCallback(
    async (ruleId: string, expression: string) => {
      if (!expression) return
      try {
        await copyTextToClipboard(expression)
        showNotice({ type: 'success', message: 'Complete rule expression copied to clipboard.', ruleId })
      } catch {
        showNotice({ type: 'error', message: 'Failed to copy complete rule expression.', ruleId })
      }
    },
    [showNotice]
  )

  const handleTestRule = useCallback(
    async (request: {
      sampleCount: number
      versionId: string
      semanticMatching?: {
        enabled: boolean
        fieldAliasMappings?: Record<string, string>
        activeSynonyms?: string[]
        inactiveSynonyms?: string[]
      }
      selectedAttributes: Array<{
        id: string
        name: string
        versionId?: string | null
        dataObjectName?: string
      }>
    }) => {
      if (!activeModalRule) {
        throw new Error('No active rule selected for testing.')
      }

      try {
        const sampleCount = Number(request?.sampleCount || 0)
        const selectedVersionId = String(request?.versionId || '').trim()
        const semanticMatching = request?.semanticMatching
        const selectedAttributes = Array.isArray(request?.selectedAttributes) ? request.selectedAttributes : []

        if (!selectedVersionId) {
          throw new Error('No data-object version resolved from selected attributes.')
        }

        const taskId = await startRuleTest({
          ruleId: activeModalRule,
          ruleName: activeRule?.name || activeModalRule,
          versionId: selectedVersionId,
          sampleCount,
          semanticMatching,
          selectedAttributes,
        })

        return { taskId }
      } catch (error: any) {
        console.error('Test rule failed:', error)
        throw error
      }
    },
    [activeModalRule, activeRule?.name, startRuleTest]
  )

  const handleValidateRule = useCallback(
    async (ruleId: string) => {
      const ruleName = props.rules.find(r => r.id === ruleId)?.name || ruleId
      try {
        const result = await validateRuleComposition(ruleId)
        const compiledExpression = typeof result?.compiledExpression === 'string' ? result.compiledExpression : ''

        if (compiledExpression) {
          setCompiledExpressionByRuleId(prev => ({ ...prev, [ruleId]: compiledExpression }))
        }

        const errors = Number(result?.summary?.errors || 0)
        const warnings = Number(result?.summary?.warnings || 0)
        const upstreamIssue = hasUpstreamValidationIssue(result)

        setValidationStateByRuleId(prev => ({
          ...prev,
          [ruleId]: errors === 0 ? 'valid' : upstreamIssue ? 'upstream-error' : 'invalid',
        }))

        if (errors === 0 && warnings === 0) {
          showNotice({ type: 'success', message: 'Validation passed. Rule composition is valid.', ruleId })
          return
        }

        setValidationDiagnosticsModal({ result, ruleName })
      } catch (error: any) {
        setValidationStateByRuleId(prev => ({ ...prev, [ruleId]: 'upstream-error' }))
        setValidationDiagnosticsModal({
          ruleName,
          result: {
            valid: false,
            summary: { errors: 1, warnings: 0 },
            diagnostics: [{ scope: 'rule', severity: 'error', message: error?.message || 'Unknown error' }],
          },
        })
      }
    },
    [props.rules, validateRuleComposition, setCompiledExpressionByRuleId, setValidationStateByRuleId, setValidationDiagnosticsModal, showNotice]
  )

  const handleToggleBulkSelect = useCallback(
    (ruleId: string) => {
      const newSelected = new Set(selectedBulkRuleIds)
      if (newSelected.has(ruleId)) {
        newSelected.delete(ruleId)
      } else {
        newSelected.add(ruleId)
      }
      setSelectedBulkRuleIds(newSelected)
    },
    [selectedBulkRuleIds, setSelectedBulkRuleIds]
  )

  const handleBulkApprove = useCallback(
    async () => {
      const selectedIds = Array.from(selectedBulkRuleIds)
      const targetIds = bulkApproveRuleIds.filter((ruleId) => selectedBulkRuleIds.has(ruleId))
      const skipped = selectedIds.filter((ruleId) => !targetIds.includes(ruleId))

      if (targetIds.length === 0) {
        showNotice({
          type: 'error',
          message: 'Bulk approval blocked: no selected rules are eligible for approval.',
          details: skipped.length > 0 ? [`${skipped.length} selected rule${skipped.length === 1 ? '' : 's'} skipped by eligibility policy.`] : undefined,
        })
        return
      }

      const result: BulkActionResult = { processed: [], skipped, failed: [] }
      for (const ruleId of targetIds) {
        try {
          await approveRule(ruleId)
          result.processed.push(ruleId)
        } catch (error) {
          result.failed.push({ ruleId, reason: errorMessage(error) })
        }
      }

      const remainingSelected = new Set([...result.skipped, ...result.failed.map((item) => item.ruleId)])
      setSelectedBulkRuleIds(remainingSelected)
      showNotice({
        type: result.failed.length > 0 ? 'error' : 'success',
        message: summarizeBulkAction('Bulk approval completed', result),
        details: [
          ...result.skipped.map((ruleId) => `${ruleId}: skipped because approval is not available for the current status or role.`),
          ...result.failed.map((item) => `${item.ruleId}: ${item.reason}`),
        ],
      })
    },
    [selectedBulkRuleIds, bulkApproveRuleIds, approveRule, setSelectedBulkRuleIds, showNotice]
  )

  const handleBulkActivate = useCallback(
    async () => {
      const selectedIds = Array.from(selectedBulkRuleIds)
      const targetIds = bulkActivateRuleIds.filter((ruleId) => selectedBulkRuleIds.has(ruleId))
      const skipped = selectedIds.filter((ruleId) => !targetIds.includes(ruleId))

      if (targetIds.length === 0) {
        showNotice({
          type: 'error',
          message: 'Bulk activation blocked: no selected rules are eligible for activation.',
          details: skipped.length > 0 ? [`${skipped.length} selected rule${skipped.length === 1 ? '' : 's'} skipped by eligibility policy.`] : undefined,
        })
        return
      }

      const result: BulkActionResult = { processed: [], skipped, failed: [] }
      for (const ruleId of targetIds) {
        try {
          await activateRule(ruleId)
          result.processed.push(ruleId)
        } catch (error) {
          result.failed.push({ ruleId, reason: errorMessage(error) })
        }
      }

      const remainingSelected = new Set([...result.skipped, ...result.failed.map((item) => item.ruleId)])
      setSelectedBulkRuleIds(remainingSelected)
      showNotice({
        type: result.failed.length > 0 ? 'error' : 'success',
        message: summarizeBulkAction('Bulk activation completed', result),
        details: [
          ...result.skipped.map((ruleId) => `${ruleId}: skipped because activation is not available for the current status or role.`),
          ...result.failed.map((item) => `${item.ruleId}: ${item.reason}`),
        ],
      })
    },
    [selectedBulkRuleIds, bulkActivateRuleIds, activateRule, setSelectedBulkRuleIds, showNotice]
  )

  return {
    handleSubmitForApproval,
    handleDeactivateRule,
    handleApproval,
    handleRejection,
    handleActivateRule,
    handleSaveTemplate,
    handleAssignAttributes,
    handleAssignReusableFilter,
    handleAssignReusableJoin,
    handleSaveJoinConditions,
    handleCopyJoinExpression,
    handleCopyCompleteExpression,
    handleTestRule,
    handleValidateRule,
    handleToggleBulkSelect,
    handleBulkApprove,
    handleBulkActivate,
  }
}
