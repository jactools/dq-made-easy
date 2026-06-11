import type { DiagnosticsSummary, FailureClass, FailureDiagnostic, JoinConsistencyExecutionMetrics } from '../types/execution'
import type { CrossObjectComparison, CrossObjectJoinKey, ReconcileParams } from '../types/rules'

export interface ReconciliationWorkflowRow extends Record<string, unknown> {}

export interface ReconciliationWorkflowResult {
  metrics: JoinConsistencyExecutionMetrics
  diagnostics: DiagnosticsSummary[]
  summary: ReconciliationSummary
  matchedRows: number
  mismatchedRows: number
  missingLeftRows: number
  missingRightRows: number
  nullOrMissingJoinKeyRows: number
}

export interface ReconciliationSummary {
  rowCounts: ReconciliationRowCountsSummary
  keySummary: ReconciliationKeySummary
  aggregateSummary: ReconciliationAggregateSummary[]
  payloadSummary: ReconciliationPayloadSummary
}

export interface ReconciliationRowCountsSummary {
  leftRows: number
  rightRows: number
  matchedPairs: number
  mismatchedPairs: number
  missingLeftRows: number
  missingRightRows: number
  nullOrMissingJoinKeyRows: number
}

export interface ReconciliationKeySummary {
  distinctLeftJoinKeys: number
  distinctRightJoinKeys: number
  sharedJoinKeys: number
  leftOnlyJoinKeys: number
  rightOnlyJoinKeys: number
  duplicateJoinKeyRowsLeft: number
  duplicateJoinKeyRowsRight: number
}

export interface ReconciliationAggregateSummary {
  comparisonLabel: string
  mode: CrossObjectComparison['mode']
  comparedRows: number
  leftTotal: number
  rightTotal: number
  delta: number
  absoluteDelta: number
}

export interface ReconciliationPayloadSummary {
  comparedPairs: number
  matchedPairs: number
  mismatchedPairs: number
  sampleMismatches: Array<{
    joinKey: string
    mismatchedAttributes: string[]
    leftPayload: string
    rightPayload: string
  }>
}

interface RowEntry {
  row: ReconciliationWorkflowRow
  rowIdentifier: string
}

const MAX_SAMPLE_FAILURES = 3
const MAX_SAMPLE_PAYLOAD_MISMATCHES = 5

const isBlankValue = (value: unknown): boolean => {
  return value === null || value === undefined || (typeof value === 'string' && value.trim().length === 0)
}

const formatScalarValue = (value: unknown): string => {
  if (isBlankValue(value)) {
    return '∅'
  }

  if (typeof value === 'string') {
    return value
  }

  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value)
  }

  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

const buildRowIdentifier = (row: ReconciliationWorkflowRow, joinKeys: CrossObjectJoinKey[]): string => {
  if (joinKeys.length === 0) {
    return 'unkeyed-row'
  }

  return joinKeys
    .map((joinKey) => `${joinKey.leftAttribute}=${formatScalarValue(row[joinKey.leftAttribute])}`)
    .join(' | ')
}

const buildJoinKey = (row: ReconciliationWorkflowRow, joinKeys: CrossObjectJoinKey[]): string | null => {
  const parts: string[] = []

  for (const joinKey of joinKeys) {
    const leftValue = row[joinKey.leftAttribute]
    if (isBlankValue(leftValue)) {
      return null
    }

    parts.push(`${joinKey.leftAttribute}=${formatScalarValue(leftValue)}`)
  }

  return parts.join(' | ')
}

const compareValues = (
  leftValue: unknown,
  rightValue: unknown,
  comparison: CrossObjectComparison,
): { passed: boolean; details?: string } => {
  switch (comparison.mode) {
    case 'case_insensitive': {
      const left = formatScalarValue(leftValue).toLowerCase()
      const right = formatScalarValue(rightValue).toLowerCase()

      if (left === right) {
        return { passed: true }
      }

      return { passed: false, details: `${comparison.leftAttribute} / ${comparison.rightAttribute} did not match case-insensitively (${formatScalarValue(leftValue)} vs ${formatScalarValue(rightValue)})` }
    }
    case 'numeric_tolerance': {
      const tolerance = Number(comparison.tolerance ?? 0)
      const leftNumber = Number(leftValue)
      const rightNumber = Number(rightValue)

      if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && Math.abs(leftNumber - rightNumber) <= tolerance) {
        return { passed: true }
      }

      return {
        passed: false,
        details: `${comparison.leftAttribute} / ${comparison.rightAttribute} exceeded tolerance ${tolerance} (${formatScalarValue(leftValue)} vs ${formatScalarValue(rightValue)})`,
      }
    }
    case 'exact':
    default: {
      if (Object.is(leftValue, rightValue)) {
        return { passed: true }
      }

      if (String(leftValue) === String(rightValue)) {
        return { passed: true }
      }

      return { passed: false, details: `${comparison.leftAttribute} / ${comparison.rightAttribute} differed (${formatScalarValue(leftValue)} vs ${formatScalarValue(rightValue)})` }
    }
  }
}

const addFailure = (
  bucketMap: Map<FailureClass, { count: number; sampleFailures: FailureDiagnostic[] }>,
  failureClass: FailureClass,
  details: string,
  rowIdentifier?: string | null,
  affectedAttributes?: string[] | null,
) => {
  const bucket = bucketMap.get(failureClass) || { count: 0, sampleFailures: [] }
  bucket.count += 1

  if (bucket.sampleFailures.length < MAX_SAMPLE_FAILURES) {
    bucket.sampleFailures.push({
      failureClass,
      details,
      rowIdentifier: rowIdentifier ?? null,
      affectedAttributes: affectedAttributes ?? null,
    })
  }

  bucketMap.set(failureClass, bucket)
}

const toDiagnostics = (
  bucketMap: Map<FailureClass, { count: number; sampleFailures: FailureDiagnostic[] }>,
): DiagnosticsSummary[] => {
  return Array.from(bucketMap.entries())
    .filter(([, bucket]) => bucket.count > 0)
    .map(([failureClass, bucket]) => ({
      failureClass,
      count: bucket.count,
      sampleFailures: bucket.sampleFailures,
      maxSampleSize: MAX_SAMPLE_FAILURES,
    }))
}

const buildRowGroups = (rows: ReconciliationWorkflowRow[], joinKeys: CrossObjectJoinKey[]): { invalidRows: RowEntry[]; keyedRows: Map<string, RowEntry[]> } => {
  const invalidRows: RowEntry[] = []
  const keyedRows = new Map<string, RowEntry[]>()

  rows.forEach((row, index) => {
    const rowIdentifier = `${buildRowIdentifier(row, joinKeys)} #${index + 1}`
    const joinKey = buildJoinKey(row, joinKeys)

    if (!joinKey) {
      invalidRows.push({ row, rowIdentifier })
      return
    }

    const existingRows = keyedRows.get(joinKey) || []
    existingRows.push({ row, rowIdentifier })
    keyedRows.set(joinKey, existingRows)
  })

  return { invalidRows, keyedRows }
}

const isNumericValue = (value: unknown): value is number => {
  return typeof value === 'number' && Number.isFinite(value)
}

const formatPayload = (row: ReconciliationWorkflowRow): string => {
  try {
    return JSON.stringify(row, null, 2)
  } catch {
    return String(row)
  }
}

const toRowArray = (value: unknown): ReconciliationWorkflowRow[] => {
  if (!Array.isArray(value)) {
    throw new Error('Sample reconciliation data must be provided as an array of objects.')
  }

  return value.map((item, index) => {
    if (item === null || typeof item !== 'object' || Array.isArray(item)) {
      throw new Error(`Row ${index + 1} must be an object.`)
    }

    return item as ReconciliationWorkflowRow
  })
}

export const parseReconciliationRows = (rawRows: string): ReconciliationWorkflowRow[] => {
  if (!rawRows.trim()) {
    return []
  }

  return toRowArray(JSON.parse(rawRows))
}

export const runReconciliationPreview = (
  params: ReconcileParams,
  leftRows: ReconciliationWorkflowRow[],
  rightRows: ReconciliationWorkflowRow[],
): ReconciliationWorkflowResult => {
  if (!params.joinKeys || params.joinKeys.length === 0) {
    throw new Error('Reconciliation preview requires at least one join key.')
  }

  if (!params.comparisons || params.comparisons.length === 0) {
    throw new Error('Reconciliation preview requires at least one comparison.')
  }

  const diagnostics = new Map<FailureClass, { count: number; sampleFailures: FailureDiagnostic[] }>()
  const aggregateTotals = new Map<
    string,
    {
      comparisonLabel: string
      mode: CrossObjectComparison['mode']
      comparedRows: number
      leftTotal: number
      rightTotal: number
    }
  >()
  const samplePayloadMismatches: ReconciliationPayloadSummary['sampleMismatches'] = []
  const { invalidRows: invalidLeftRows, keyedRows: leftGroups } = buildRowGroups(leftRows, params.joinKeys)
  const { invalidRows: invalidRightRows, keyedRows: rightGroups } = buildRowGroups(rightRows, params.joinKeys)

  let matchedRows = 0
  let mismatchedRows = 0
  let missingLeftRows = 0
  let missingRightRows = 0
  const nullOrMissingJoinKeyRows = invalidLeftRows.length + invalidRightRows.length

  for (const invalidRow of invalidLeftRows) {
    addFailure(
      diagnostics,
      'null_or_missing_join_key',
      'Left source row is missing at least one join key field.',
      invalidRow.rowIdentifier,
      params.joinKeys.map((joinKey) => joinKey.leftAttribute),
    )
  }

  for (const invalidRow of invalidRightRows) {
    addFailure(
      diagnostics,
      'null_or_missing_join_key',
      'Right source row is missing at least one join key field.',
      invalidRow.rowIdentifier,
      params.joinKeys.map((joinKey) => joinKey.rightAttribute),
    )
  }

  const allJoinKeys = new Set([...leftGroups.keys(), ...rightGroups.keys()])

  for (const joinKey of allJoinKeys) {
    const leftGroup = leftGroups.get(joinKey) || []
    const rightGroup = rightGroups.get(joinKey) || []
    const pairCount = Math.min(leftGroup.length, rightGroup.length)

    for (let index = 0; index < pairCount; index += 1) {
      const leftEntry = leftGroup[index]
      const rightEntry = rightGroup[index]
      let pairMatches = true
      const affectedAttributes: string[] = []
      const comparisonFailures: string[] = []

      for (const comparison of params.comparisons) {
        const leftValue = leftEntry.row[comparison.leftAttribute]
        const rightValue = rightEntry.row[comparison.rightAttribute]
        const comparisonResult = compareValues(
          leftValue,
          rightValue,
          comparison,
        )

        if (isNumericValue(leftValue) && isNumericValue(rightValue)) {
          const aggregateKey = `${comparison.leftAttribute}::${comparison.rightAttribute}::${comparison.mode}`
          const bucket = aggregateTotals.get(aggregateKey) || {
            comparisonLabel: `${comparison.leftAttribute} ↔ ${comparison.rightAttribute}`,
            mode: comparison.mode,
            comparedRows: 0,
            leftTotal: 0,
            rightTotal: 0,
          }

          bucket.comparedRows += 1
          bucket.leftTotal += leftValue
          bucket.rightTotal += rightValue
          aggregateTotals.set(aggregateKey, bucket)
        }

        if (!comparisonResult.passed) {
          pairMatches = false
          comparisonFailures.push(comparisonResult.details || `${comparison.leftAttribute} / ${comparison.rightAttribute} did not match.`)
          affectedAttributes.push(comparison.leftAttribute, comparison.rightAttribute)
        }
      }

      if (pairMatches) {
        matchedRows += 1
        continue
      }

      if (samplePayloadMismatches.length < MAX_SAMPLE_PAYLOAD_MISMATCHES) {
        samplePayloadMismatches.push({
          joinKey,
          mismatchedAttributes: Array.from(new Set(affectedAttributes)),
          leftPayload: formatPayload(leftEntry.row),
          rightPayload: formatPayload(rightEntry.row),
        })
      }

      mismatchedRows += 1
      addFailure(
        diagnostics,
        'value_mismatch',
        comparisonFailures.join('; '),
        leftEntry.rowIdentifier || rightEntry.rowIdentifier,
        Array.from(new Set(affectedAttributes)),
      )
    }

    if (leftGroup.length > pairCount) {
      const extraRows = leftGroup.slice(pairCount)
      missingRightRows += extraRows.length
      extraRows.forEach((entry) => {
        addFailure(
          diagnostics,
          'other',
          `No matching right-side row was found for join key ${joinKey}.`,
          entry.rowIdentifier,
          params.joinKeys.map((joinKeyEntry) => joinKeyEntry.leftAttribute),
        )
      })
    }

    if (rightGroup.length > pairCount) {
      const extraRows = rightGroup.slice(pairCount)
      missingLeftRows += extraRows.length
      extraRows.forEach((entry) => {
        addFailure(
          diagnostics,
          'other',
          `No matching left-side row was found for join key ${joinKey}.`,
          entry.rowIdentifier,
          params.joinKeys.map((joinKeyEntry) => joinKeyEntry.rightAttribute),
        )
      })
    }
  }

  const leftJoinKeySet = new Set(leftGroups.keys())
  const rightJoinKeySet = new Set(rightGroups.keys())
  const sharedJoinKeys = Array.from(leftJoinKeySet).filter((joinKey) => rightJoinKeySet.has(joinKey)).length
  const leftOnlyJoinKeys = Array.from(leftJoinKeySet).filter((joinKey) => !rightJoinKeySet.has(joinKey)).length
  const rightOnlyJoinKeys = Array.from(rightJoinKeySet).filter((joinKey) => !leftJoinKeySet.has(joinKey)).length
  const duplicateJoinKeyRowsLeft = Array.from(leftGroups.values()).reduce((total, group) => total + Math.max(group.length - 1, 0), 0)
  const duplicateJoinKeyRowsRight = Array.from(rightGroups.values()).reduce((total, group) => total + Math.max(group.length - 1, 0), 0)

  const aggregateSummary = Array.from(aggregateTotals.values()).map((bucket) => ({
    comparisonLabel: bucket.comparisonLabel,
    mode: bucket.mode,
    comparedRows: bucket.comparedRows,
    leftTotal: Number(bucket.leftTotal.toFixed(2)),
    rightTotal: Number(bucket.rightTotal.toFixed(2)),
    delta: Number((bucket.leftTotal - bucket.rightTotal).toFixed(2)),
    absoluteDelta: Number(Math.abs(bucket.leftTotal - bucket.rightTotal).toFixed(2)),
  }))

  const payloadSummary: ReconciliationPayloadSummary = {
    comparedPairs: matchedRows + mismatchedRows,
    matchedPairs: matchedRows,
    mismatchedPairs: mismatchedRows,
    sampleMismatches: samplePayloadMismatches,
  }

  const eligibleJoinedRows = matchedRows + mismatchedRows
  const matchRate = eligibleJoinedRows > 0 ? Number(((matchedRows / eligibleJoinedRows) * 100).toFixed(2)) : 0

  return {
    metrics: {
      matchCount: matchedRows,
      mismatchCount: mismatchedRows,
      eligibleJoinedRows,
      matchRate,
      actualityDateMismatchCount: 0,
      nullOrMissingJoinKeyCount: nullOrMissingJoinKeyRows,
    },
    diagnostics: toDiagnostics(diagnostics),
    summary: {
      rowCounts: {
        leftRows: leftRows.length,
        rightRows: rightRows.length,
        matchedPairs: matchedRows,
        mismatchedPairs: mismatchedRows,
        missingLeftRows,
        missingRightRows,
        nullOrMissingJoinKeyRows,
      },
      keySummary: {
        distinctLeftJoinKeys: leftJoinKeySet.size,
        distinctRightJoinKeys: rightJoinKeySet.size,
        sharedJoinKeys,
        leftOnlyJoinKeys,
        rightOnlyJoinKeys,
        duplicateJoinKeyRowsLeft,
        duplicateJoinKeyRowsRight,
      },
      aggregateSummary,
      payloadSummary,
    },
    matchedRows,
    mismatchedRows,
    missingLeftRows,
    missingRightRows,
    nullOrMissingJoinKeyRows,
  }
}
