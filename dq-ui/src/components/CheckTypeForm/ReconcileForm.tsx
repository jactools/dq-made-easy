import React from 'react'
import {
  CrossObjectComparison,
  CrossObjectComparisonMode,
  CrossObjectJoinKey,
  ReconcileParams,
} from '../../types/rules'
import { CheckTypeFieldErrors } from './checkTypeValidation'

interface ReconcileFormProps {
  params: Partial<ReconcileParams>
  onChange: (params: ReconcileParams) => void
  fieldErrors?: CheckTypeFieldErrors
}

const parseJoinKeys = (raw: string): CrossObjectJoinKey[] =>
  raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [leftAttribute, rightAttribute] = line.split('=').map((value) => value.trim())
      return { leftAttribute: leftAttribute || '', rightAttribute: rightAttribute || '' }
    })

const parseComparisons = (raw: string): CrossObjectComparison[] =>
  raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [pairPart, modePart, tolerancePart] = line.split('|').map((value) => value.trim())
      const [leftAttribute, rightAttribute] = String(pairPart || '').split('=').map((value) => value.trim())
      const mode = (modePart || 'exact') as CrossObjectComparisonMode
      const tolerance = tolerancePart ? Number(tolerancePart) : undefined
      return {
        leftAttribute: leftAttribute || '',
        rightAttribute: rightAttribute || '',
        mode,
        tolerance: Number.isFinite(tolerance as number) ? tolerance : undefined,
      }
    })

export const ReconcileForm: React.FC<ReconcileFormProps> = ({ params, onChange, fieldErrors }) => {
  const emit = (patch: Partial<ReconcileParams>) =>
    onChange({
      checkType: 'RECONCILE',
      leftDataObjectVersionId: params.leftDataObjectVersionId ?? '',
      rightDataObjectVersionId: params.rightDataObjectVersionId ?? '',
      joinKeys: params.joinKeys ?? [],
      comparisons: params.comparisons ?? [],
      ...patch,
    })

  return (
    <div className="check-type-form reconcile-form">
      <div className="check-type-form-row">
        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-reconcile-left-version">
            Left data object version
          </label>
          <input
            id="ct-reconcile-left-version"
            type="text"
            className="modal-input"
            value={params.leftDataObjectVersionId ?? ''}
            placeholder="e.g. ledger-v1"
            onChange={(e) => emit({ leftDataObjectVersionId: e.target.value })}
          />
          {fieldErrors?.leftDataObjectVersionId && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.leftDataObjectVersionId}</span>
          )}
        </div>

        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-reconcile-right-version">
            Right data object version
          </label>
          <input
            id="ct-reconcile-right-version"
            type="text"
            className="modal-input"
            value={params.rightDataObjectVersionId ?? ''}
            placeholder="e.g. reporting-v4"
            onChange={(e) => emit({ rightDataObjectVersionId: e.target.value })}
          />
          {fieldErrors?.rightDataObjectVersionId && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.rightDataObjectVersionId}</span>
          )}
        </div>
      </div>

      <div className="check-type-form-field">
        <label className="check-type-form-label" htmlFor="ct-reconcile-join-keys">
          Join keys
        </label>
        <textarea
          id="ct-reconcile-join-keys"
          className="modal-input"
          rows={3}
          value={(params.joinKeys ?? []).map((item) => `${item.leftAttribute}=${item.rightAttribute}`).join('\n')}
          placeholder={'account_id=account_id'}
          onChange={(e) => emit({ joinKeys: parseJoinKeys(e.target.value) })}
        />
        {fieldErrors?.joinKeys && (
          <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.joinKeys}</span>
        )}
      </div>

      <div className="check-type-form-field">
        <label className="check-type-form-label" htmlFor="ct-reconcile-comparisons">
          Reconciliation comparisons
        </label>
        <textarea
          id="ct-reconcile-comparisons"
          className="modal-input"
          rows={4}
          value={(params.comparisons ?? []).map((item) => [
            `${item.leftAttribute}=${item.rightAttribute}`,
            item.mode,
            item.tolerance != null ? String(item.tolerance) : '',
          ].filter(Boolean).join('|')).join('\n')}
          placeholder={'balance_amount=reported_balance|numeric_tolerance|0.01\ncurrency_code=currency_code|exact'}
          onChange={(e) => emit({ comparisons: parseComparisons(e.target.value) })}
        />
        <span className="check-type-form-hint">
          Enter one comparison per line as left=right|mode|tolerance. Tolerance is only used for numeric_tolerance.
        </span>
        <span className="check-type-form-hint">
          Large reconciliation runs are expected to execute through a PySpark worker path when this workflow is implemented; other engine targets can be added later.
        </span>
        {fieldErrors?.comparisons && (
          <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.comparisons}</span>
        )}
        {fieldErrors?.comparisonTolerance && (
          <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.comparisonTolerance}</span>
        )}
      </div>
    </div>
  )
}