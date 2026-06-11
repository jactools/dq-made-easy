import React from 'react'
import { CorrectParams, CrossObjectComparisonMode, CrossObjectJoinKey } from '../../types/rules'
import { AppSelect } from '../app-primitives'
import { CheckTypeFieldErrors } from './checkTypeValidation'

interface CorrectFormProps {
  params: Partial<CorrectParams>
  onChange: (params: CorrectParams) => void
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

export const CorrectForm: React.FC<CorrectFormProps> = ({ params, onChange, fieldErrors }) => {
  const emit = (patch: Partial<CorrectParams>) =>
    onChange({
      checkType: 'CORRECT',
      sourceDataObjectVersionId: params.sourceDataObjectVersionId ?? '',
      referenceDataObjectVersionId: params.referenceDataObjectVersionId ?? '',
      joinKeys: params.joinKeys ?? [],
      comparison: params.comparison ?? {
        leftAttribute: '',
        rightAttribute: '',
        mode: 'exact',
      },
      ...patch,
    })

  const comparison = params.comparison ?? {
    leftAttribute: '',
    rightAttribute: '',
    mode: 'exact' as CrossObjectComparisonMode,
  }

  return (
    <div className="check-type-form correct-form">
      <div className="check-type-form-row">
        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-correct-source-version">
            Source data object version
          </label>
          <input
            id="ct-correct-source-version"
            type="text"
            className="modal-input"
            value={params.sourceDataObjectVersionId ?? ''}
            placeholder="e.g. prices-v1"
            onChange={(e) => emit({ sourceDataObjectVersionId: e.target.value })}
          />
          {fieldErrors?.sourceDataObjectVersionId && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.sourceDataObjectVersionId}</span>
          )}
        </div>

        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-correct-reference-version">
            Reference data object version
          </label>
          <input
            id="ct-correct-reference-version"
            type="text"
            className="modal-input"
            value={params.referenceDataObjectVersionId ?? ''}
            placeholder="e.g. exchange-v2"
            onChange={(e) => emit({ referenceDataObjectVersionId: e.target.value })}
          />
          {fieldErrors?.referenceDataObjectVersionId && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.referenceDataObjectVersionId}</span>
          )}
        </div>
      </div>

      <div className="check-type-form-field">
        <label className="check-type-form-label" htmlFor="ct-correct-join-keys">
          Join keys
        </label>
        <textarea
          id="ct-correct-join-keys"
          className="modal-input"
          rows={3}
          value={(params.joinKeys ?? []).map((item) => `${item.leftAttribute}=${item.rightAttribute}`).join('\n')}
          placeholder={'trade_id=trade_id'}
          onChange={(e) => emit({ joinKeys: parseJoinKeys(e.target.value) })}
        />
        <span className="check-type-form-hint">
          Enter one key mapping per line as left_attribute=right_attribute.
        </span>
        {fieldErrors?.joinKeys && (
          <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.joinKeys}</span>
        )}
      </div>

      <div className="check-type-form-row">
        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-correct-left-attribute">
            Source attribute
          </label>
          <input
            id="ct-correct-left-attribute"
            type="text"
            className="modal-input"
            value={comparison.leftAttribute}
            placeholder="e.g. closing_price"
            onChange={(e) => emit({ comparison: { ...comparison, leftAttribute: e.target.value } })}
          />
          {fieldErrors?.comparisonLeftAttribute && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.comparisonLeftAttribute}</span>
          )}
        </div>

        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-correct-right-attribute">
            Reference attribute
          </label>
          <input
            id="ct-correct-right-attribute"
            type="text"
            className="modal-input"
            value={comparison.rightAttribute}
            placeholder="e.g. reference_price"
            onChange={(e) => emit({ comparison: { ...comparison, rightAttribute: e.target.value } })}
          />
          {fieldErrors?.comparisonRightAttribute && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.comparisonRightAttribute}</span>
          )}
        </div>
      </div>

      <div className="check-type-form-row">
        <div className="check-type-form-field check-type-form-field--half">
          <AppSelect
            id="ct-correct-mode"
            label="Comparison mode"
            value={comparison.mode}
            onChange={(value) => emit({ comparison: { ...comparison, mode: value as CrossObjectComparisonMode } })}
            options={[
              { value: 'exact', label: 'Exact match' },
              { value: 'case_insensitive', label: 'Case-insensitive match' },
              { value: 'numeric_tolerance', label: 'Numeric tolerance' },
            ]}
          />
        </div>

        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-correct-tolerance">
            Tolerance (numeric mode only)
          </label>
          <input
            id="ct-correct-tolerance"
            type="number"
            className="modal-input"
            step={0.0001}
            value={comparison.tolerance ?? ''}
            onChange={(e) => emit({ comparison: { ...comparison, tolerance: e.target.value === '' ? undefined : Number(e.target.value) } })}
          />
          {fieldErrors?.comparisonTolerance && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.comparisonTolerance}</span>
          )}
        </div>
      </div>
    </div>
  )
}