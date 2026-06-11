const VALIDATION_UI_TERM_REPLACEMENTS: Array<[RegExp, string]> = [
  [/Great Expectations/g, 'validation'],
  [/GX execution status history/g, 'Validation run status history'],
  [/gx execution status history/g, 'validation run status history'],
  [/GX execution run/g, 'Validation run'],
  [/gx execution run/g, 'validation run'],
  [/GX exception analytics/g, 'Validation exception analytics'],
  [/gx exception analytics/g, 'validation exception analytics'],
  [/GX queue status/g, 'Validation queue status'],
  [/gx queue status/g, 'validation queue status'],
  [/GX run plan version/g, 'Validation run plan version'],
  [/gx run plan version/g, 'validation run plan version'],
  [/GX run plans/g, 'Validation run plans'],
  [/gx run plans/g, 'validation run plans'],
  [/GX run plan/g, 'Validation run plan'],
  [/gx run plan/g, 'validation run plan'],
  [/GX run id/g, 'Validation run id'],
  [/gx run id/g, 'validation run id'],
  [/GX suites/g, 'Validation suites'],
  [/gx suites/g, 'validation suites'],
  [/GX suite/g, 'Validation suite'],
  [/gx suite/g, 'validation suite'],
  [/GX runs/g, 'Validation runs'],
  [/gx runs/g, 'validation runs'],
  [/GX run/g, 'Validation run'],
  [/gx run/g, 'validation run'],
  [/GX Expectation/g, 'Validation Expectation'],
  [/gx expectation/g, 'validation expectation'],
  [/gx_suites_not_found/g, 'validation_suites_not_found'],
]

export const normalizeValidationUiText = (value: string | null | undefined): string => {
  const text = String(value || '')
  if (!text) {
    return ''
  }

  return VALIDATION_UI_TERM_REPLACEMENTS.reduce(
    (normalized, [pattern, replacement]) => normalized.replace(pattern, replacement),
    text,
  )
}