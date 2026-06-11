import React from 'react'
import { ComparisonOperator, RowCountOperator, RowCountParams } from '../../types/rules'
import { AppSelect } from '../app-primitives'
import { CheckTypeFieldErrors } from './checkTypeValidation'

interface RowCountFormProps {
  params: Partial<RowCountParams>
  onChange: (params: RowCountParams) => void
  fieldErrors?: CheckTypeFieldErrors
}

const OPERATORS: { value: RowCountOperator; label: string }[] = [
  { value: 'gt', label: 'greater than (>)' },
  { value: 'gte', label: 'greater than or equal (≥)' },
  { value: 'lt', label: 'less than (<)' },
  { value: 'lte', label: 'less than or equal (≤)' },
  { value: 'between', label: 'between' },
]

const isComparisonOperator = (value: RowCountOperator): value is ComparisonOperator => value !== 'between'

export const RowCountForm: React.FC<RowCountFormProps> = ({ params, onChange, fieldErrors }) => {
  const selectedOperator = params.operator ?? 'gte'
  const selectedThreshold = params.threshold ?? 1

  const emit = (patch: Partial<RowCountParams>) => {
    const nextOperator = patch.operator ?? selectedOperator
    const nextParams: RowCountParams = {
      checkType: 'ROW_COUNT',
      operator: nextOperator,
    }

    if (nextOperator === 'between') {
      nextParams.minValue = patch.minValue ?? params.minValue ?? selectedThreshold
      nextParams.maxValue = patch.maxValue ?? params.maxValue ?? selectedThreshold
    } else if (isComparisonOperator(nextOperator)) {
      nextParams.threshold = patch.threshold ?? params.threshold ?? selectedThreshold
    }

    onChange(nextParams)
  }

  return (
    <div className="check-type-form threshold-form">
      <div className="check-type-form-field">
        <AppSelect
          id="ct-row-count-operator"
          label="Condition"
          value={selectedOperator}
          onChange={(value) => emit({ operator: value as RowCountOperator })}
          options={OPERATORS}
        />
      </div>

      {selectedOperator === 'between' ? (
        <div className="check-type-form-row">
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-row-count-min">
              Minimum row count
            </label>
            <input
              id="ct-row-count-min"
              type="number"
              className="modal-input"
              min={0}
              step={1}
              value={params.minValue ?? ''}
              placeholder="e.g. 100"
              onChange={(event) => emit({ minValue: event.target.value === '' ? undefined : parseInt(event.target.value, 10) })}
            />
            <span className="check-type-form-hint">
              Lower bound for the total number of rows.
            </span>
            {fieldErrors?.minValue && (
              <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.minValue}</span>
            )}
          </div>

          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-row-count-max">
              Maximum row count
            </label>
            <input
              id="ct-row-count-max"
              type="number"
              className="modal-input"
              min={0}
              step={1}
              value={params.maxValue ?? ''}
              placeholder="e.g. 1000"
              onChange={(event) => emit({ maxValue: event.target.value === '' ? undefined : parseInt(event.target.value, 10) })}
            />
            <span className="check-type-form-hint">
              Upper bound for the total number of rows.
            </span>
            {fieldErrors?.maxValue && (
              <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.maxValue}</span>
            )}
          </div>
        </div>
      ) : (
        <div className="check-type-form-field">
          <label className="check-type-form-label" htmlFor="ct-row-count-threshold">
            Row count
          </label>
          <input
            id="ct-row-count-threshold"
            type="number"
            className="modal-input"
            min={0}
            step={1}
            value={params.threshold ?? ''}
            placeholder="e.g. 1000"
            onChange={(event) => emit({ threshold: event.target.value === '' ? undefined : parseInt(event.target.value, 10) })}
          />
          <span className="check-type-form-hint">
            Total number of rows in the dataset.
          </span>
          {fieldErrors?.threshold && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.threshold}</span>
          )}
        </div>
      )}
    </div>
  )
}