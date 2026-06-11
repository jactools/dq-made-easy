import { CheckTypeFieldErrors } from './checkTypeValidation'

export interface JoinConsistencyFieldErrors extends CheckTypeFieldErrors {
  leftDataObjectVersionId?: string
  rightDataObjectVersionId?: string
  joinKeys?: string
  comparisons?: string
  actualityLeftAttribute?: string
  actualityRightAttribute?: string
  contractId?: string
  overrideToleranceValue?: string
  overrideToleranceUnit?: string
}

export interface JoinConsistencyValidationResult {
  message: string | null
  fieldErrors: JoinConsistencyFieldErrors
}

const emptyErrors = (): JoinConsistencyFieldErrors => ({})

export const validateJoinConsistencyForWizard = (params: any): JoinConsistencyValidationResult => {
  const fieldErrors = emptyErrors()

  if (!String(params?.leftDataObjectVersionId || '').trim()) {
    fieldErrors.leftDataObjectVersionId = 'Select a left data object version.'
  }

  if (!String(params?.rightDataObjectVersionId || '').trim()) {
    fieldErrors.rightDataObjectVersionId = 'Select a right data object version.'
  }

  if (!Array.isArray(params?.joinKeys) || params.joinKeys.length === 0) {
    fieldErrors.joinKeys = 'Add at least one join key mapping.'
  } else if (
    params.joinKeys.some(
      (item: any) => !String(item?.leftAttribute || '').trim() || !String(item?.rightAttribute || '').trim(),
    )
  ) {
    fieldErrors.joinKeys = 'Each join key mapping requires both left and right attributes.'
  }

  if (!Array.isArray(params?.comparisons) || params.comparisons.length === 0) {
    fieldErrors.comparisons = 'Add at least one comparison mapping.'
  } else if (
    params.comparisons.some(
      (item: any) => !String(item?.leftAttribute || '').trim() || !String(item?.rightAttribute || '').trim(),
    )
  ) {
    fieldErrors.comparisons = 'Each comparison mapping requires both left and right attributes.'
  }

  if (!String(params?.actualityDate?.leftAttribute || '').trim()) {
    fieldErrors.actualityLeftAttribute = 'Select a left actuality-date attribute.'
  }

  if (!String(params?.actualityDate?.rightAttribute || '').trim()) {
    fieldErrors.actualityRightAttribute = 'Select a right actuality-date attribute.'
  }

  if (!String(params?.actualityDate?.contractId || '').trim()) {
    fieldErrors.contractId = 'Provide a delivery contract ID.'
  }

  if (!Number.isFinite(Number(params?.minMatchRate))) {
    return {
      message: 'Join consistency check requires a valid min match rate.',
      fieldErrors,
    }
  }

  const hasErrors = Object.values(fieldErrors).some(Boolean)
  return {
    message: hasErrors ? 'Complete all required Join Consistency fields before continuing.' : null,
    fieldErrors,
  }
}

export const mapJoinConsistencyBackendError = (rawMessage: string): JoinConsistencyValidationResult => {
  const message = String(rawMessage || '').trim()
  const normalized = message.toLowerCase()
  const fieldErrors = emptyErrors()

  if (!normalized.includes('join_consistency')) {
    return { message, fieldErrors }
  }

  if (normalized.includes('left data object version') && normalized.includes('was not found')) {
    fieldErrors.leftDataObjectVersionId = message
  }
  if (normalized.includes('right data object version') && normalized.includes('was not found')) {
    fieldErrors.rightDataObjectVersionId = message
  }
  if (normalized.includes('same dataset-level contract scope')) {
    fieldErrors.leftDataObjectVersionId = message
    fieldErrors.rightDataObjectVersionId = message
  }
  if (normalized.includes('requires at least one entry in') && normalized.includes('joinkeys')) {
    fieldErrors.joinKeys = message
  }
  if (normalized.includes('requires at least one entry in') && normalized.includes('comparisons')) {
    fieldErrors.comparisons = message
  }
  if (normalized.includes('left attribute') && normalized.includes('was not found')) {
    fieldErrors.joinKeys = message
  }
  if (normalized.includes('right attribute') && normalized.includes('was not found')) {
    fieldErrors.joinKeys = message
  }
  if (normalized.includes('left actuality-date attribute')) {
    fieldErrors.actualityLeftAttribute = message
  }
  if (normalized.includes('right actuality-date attribute')) {
    fieldErrors.actualityRightAttribute = message
  }
  if (normalized.includes("requires 'contractid'")) {
    fieldErrors.contractId = message
  }
  if (normalized.includes('does not allow actuality-date tolerance overrides')) {
    fieldErrors.overrideToleranceValue = message
    fieldErrors.overrideToleranceUnit = message
  }
  if (normalized.includes('override exceeds contract policy bound')) {
    fieldErrors.overrideToleranceValue = message
    fieldErrors.overrideToleranceUnit = message
  }
  if (normalized.includes("requires both 'overridetolerancevalue' and 'overridetoleranceunit'")) {
    fieldErrors.overrideToleranceValue = message
    fieldErrors.overrideToleranceUnit = message
  }

  const hasMappedFieldErrors = Object.values(fieldErrors).some(Boolean)
  return {
    message,
    fieldErrors: hasMappedFieldErrors ? fieldErrors : {},
  }
}
