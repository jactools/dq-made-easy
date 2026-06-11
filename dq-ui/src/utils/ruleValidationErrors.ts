import { normalizeValidationUiText } from './validationTerminology'

interface RuleValidationDiagnostic {
  scope: 'rule'
  severity: 'error'
  message: string
  code?: string
  reference?: string
}

export interface RuleValidationFailureResult {
  valid: false
  summary: { errors: number; warnings: number }
  diagnostics: RuleValidationDiagnostic[]
}

const FRIENDLY_ERROR_MESSAGES: Record<string, string> = {
  unresolved_rule_attributes: 'This rule references attributes that are no longer available. Reassign the missing attributes and validate again.',
}

const toTrimmedText = (value: unknown): string => {
  if (typeof value === 'string') {
    return value.trim()
  }

  return String(value ?? '').trim()
}

const toIdList = (value: unknown): string => {
  if (!Array.isArray(value)) {
    return ''
  }

  return value
    .map((item) => toTrimmedText(item))
    .filter(Boolean)
    .join(', ')
}

export const buildRuleValidationFailureResult = (body: unknown): RuleValidationFailureResult | null => {
  if (!body || typeof body !== 'object') {
    return null
  }

  const payload = body as Record<string, unknown>
  const detail = payload.detail
  if (!detail || typeof detail !== 'object') {
    return null
  }

  const detailRecord = detail as Record<string, unknown>
  const errorCode = toTrimmedText(detailRecord.error || detailRecord.code)
  const backendMessage = toTrimmedText(detailRecord.message || detailRecord.title)
  const correlationId = toTrimmedText(payload.correlation_id)
  const assignedAttributeIds = toIdList(detailRecord.assigned_attribute_ids)
  const unresolvedAttributeIds = toIdList(detailRecord.unresolved_attribute_ids)

  let message = backendMessage || toTrimmedText(payload.message) || toTrimmedText(payload.error)

  if (errorCode === 'unresolved_rule_attributes') {
    message = FRIENDLY_ERROR_MESSAGES.unresolved_rule_attributes
    const missingAttributeIds = unresolvedAttributeIds || assignedAttributeIds
    if (missingAttributeIds) {
      message = `${message} Missing attribute IDs: ${missingAttributeIds}.`
    }
  }

  if (!message) {
    message = FRIENDLY_ERROR_MESSAGES[errorCode] || 'Validation failed.'
  }

  const diagnostics: RuleValidationDiagnostic[] = [
    {
      scope: 'rule',
      severity: 'error',
      message: normalizeValidationUiText(message),
      ...(errorCode ? { code: errorCode } : {}),
      ...(correlationId ? { reference: `correlation_id: ${correlationId}` } : {}),
    },
  ]

  return {
    valid: false,
    summary: { errors: 1, warnings: 0 },
    diagnostics,
  }
}