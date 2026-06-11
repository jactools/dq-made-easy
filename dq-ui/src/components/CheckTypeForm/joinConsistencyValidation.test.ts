import { describe, expect, it } from 'vitest'

import {
  mapJoinConsistencyBackendError,
  validateJoinConsistencyForWizard,
} from './joinConsistencyValidation'

describe('validateJoinConsistencyForWizard', () => {
  it('returns targeted field errors for missing required fields', () => {
    const result = validateJoinConsistencyForWizard({
      checkType: 'JOIN_CONSISTENCY',
      leftDataObjectVersionId: '',
      rightDataObjectVersionId: '',
      joinKeys: [],
      comparisons: [],
      actualityDate: {
        leftAttribute: '',
        rightAttribute: '',
        contractId: '',
      },
      minMatchRate: 95,
    })

    expect(result.message).toContain('Complete all required Join Consistency fields')
    expect(result.fieldErrors.leftDataObjectVersionId).toContain('left data object version')
    expect(result.fieldErrors.rightDataObjectVersionId).toContain('right data object version')
    expect(result.fieldErrors.joinKeys).toContain('join key')
    expect(result.fieldErrors.comparisons).toContain('comparison')
    expect(result.fieldErrors.actualityLeftAttribute).toContain('left actuality-date')
    expect(result.fieldErrors.actualityRightAttribute).toContain('right actuality-date')
    expect(result.fieldErrors.contractId).toContain('delivery contract')
  })

  it('returns no errors for a valid payload', () => {
    const result = validateJoinConsistencyForWizard({
      checkType: 'JOIN_CONSISTENCY',
      leftDataObjectVersionId: 'left-version-id',
      rightDataObjectVersionId: 'right-version-id',
      joinKeys: [{ leftAttribute: 'id', rightAttribute: 'id' }],
      comparisons: [{ leftAttribute: 'status', rightAttribute: 'status' }],
      actualityDate: {
        leftAttribute: 'updated_at',
        rightAttribute: 'updated_at',
        contractId: 'urn:dq:contract:demo',
      },
      minMatchRate: 98,
    })

    expect(result.message).toBeNull()
    expect(result.fieldErrors).toEqual({})
  })
})

describe('mapJoinConsistencyBackendError', () => {
  it('maps dataset scope mismatch to both version fields', () => {
    const message = "JOIN_CONSISTENCY requires left and right versions to belong to the same dataset-level contract scope (left dataset 'ds-left', right dataset 'ds-right')"
    const result = mapJoinConsistencyBackendError(message)

    expect(result.message).toBe(message)
    expect(result.fieldErrors.leftDataObjectVersionId).toBe(message)
    expect(result.fieldErrors.rightDataObjectVersionId).toBe(message)
  })

  it('maps override policy violations to override controls', () => {
    const message = "JOIN_CONSISTENCY contract 'urn:dq:contract:demo' does not allow actuality-date tolerance overrides"
    const result = mapJoinConsistencyBackendError(message)

    expect(result.fieldErrors.overrideToleranceValue).toBe(message)
    expect(result.fieldErrors.overrideToleranceUnit).toBe(message)
  })
})
