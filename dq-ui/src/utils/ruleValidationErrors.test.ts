import { describe, expect, it } from 'vitest'

import { buildRuleValidationFailureResult } from './ruleValidationErrors'

describe('buildRuleValidationFailureResult', () => {
  it('turns unresolved attribute validation failures into a readable invalid result', () => {
    const result = buildRuleValidationFailureResult({
      type: 'about:blank',
      title: 'HTTP Error',
      status: 400,
      detail: {
        error: 'unresolved_rule_attributes',
        message: 'Rule has no resolvable assigned attributes.',
        rule_id: '019e0488-9a55-771d-afc7-6a0f362aa455',
        assigned_attribute_ids: ['attr-21', 'attr-26'],
        unresolved_attribute_ids: ['attr-21', 'attr-26'],
      },
      correlation_id: '104256a7-0d33-40bd-b31c-fe9a2abfed2c',
    })

    expect(result).toEqual({
      valid: false,
      summary: { errors: 1, warnings: 0 },
      diagnostics: [
        {
          scope: 'rule',
          severity: 'error',
          code: 'unresolved_rule_attributes',
          reference: 'correlation_id: 104256a7-0d33-40bd-b31c-fe9a2abfed2c',
          message: 'This rule references attributes that are no longer available. Reassign the missing attributes and validate again. Missing attribute IDs: attr-21, attr-26.',
        },
      ],
    })
  })
})