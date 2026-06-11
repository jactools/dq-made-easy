import { describe, expect, it } from 'vitest'

import { normalizeValidationUiText } from './validationTerminology'

describe('normalizeValidationUiText', () => {
  it('rewrites backend GX phrases without touching suite identifiers', () => {
    expect(
      normalizeValidationUiText(
        "Validation failed: GX run plan version contains an invalid execution contract snapshot for GX suite gx_suite_8f40b9ea"
      )
    ).toBe(
      "Validation failed: Validation run plan version contains an invalid execution contract snapshot for Validation suite gx_suite_8f40b9ea"
    )
  })

  it('rewrites lower-case backend error codes and reason phrases', () => {
    expect(normalizeValidationUiText('gx_suites_not_found: gx suite run scheduled')).toBe(
      'validation_suites_not_found: validation suite run scheduled'
    )
  })
})