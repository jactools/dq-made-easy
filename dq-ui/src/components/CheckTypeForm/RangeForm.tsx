import React from 'react'
import { RangeParams } from '../../types/rules'
import { AppSelect } from '../app-primitives'
import { CheckTypeFieldErrors } from './checkTypeValidation'

interface RangeFormProps {
  params: Partial<RangeParams>
  onChange: (params: RangeParams) => void
  fieldErrors?: CheckTypeFieldErrors
  catalogAttributeName?: string
}

export const RangeForm: React.FC<RangeFormProps> = ({ params, onChange, fieldErrors, catalogAttributeName }) => {
  const emit = (patch: Partial<RangeParams>) =>
    onChange({
      checkType: 'RANGE',
      attribute: catalogAttributeName ?? params.attribute ?? '',
      minValue: params.minValue,
      maxValue: params.maxValue,
      inclusive: params.inclusive ?? true,
      ...patch,
    })

  return (
    <div className="check-type-form range-form">
      <div className="check-type-form-row">
        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-range-min">
            Minimum value (optional)
          </label>
          <input
            id="ct-range-min"
            type="text"
            className="modal-input"
            value={params.minValue ?? ''}
            placeholder="e.g. 0 or 2026-01-01"
            onChange={(e) => emit({ minValue: e.target.value || undefined })}
          />
          {fieldErrors?.minValue && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.minValue}</span>
          )}
        </div>

        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-range-max">
            Maximum value (optional)
          </label>
          <input
            id="ct-range-max"
            type="text"
            className="modal-input"
            value={params.maxValue ?? ''}
            placeholder="e.g. 100 or 2026-12-31"
            onChange={(e) => emit({ maxValue: e.target.value || undefined })}
          />
          {fieldErrors?.maxValue && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.maxValue}</span>
          )}
        </div>
      </div>

      <div className="check-type-form-field">
        <AppSelect
          id="ct-range-inclusive"
          label="Bounds mode"
          value={(params.inclusive ?? true) ? 'inclusive' : 'exclusive'}
          onChange={(value) => emit({ inclusive: value === 'inclusive' })}
          options={[
            { value: 'inclusive', label: 'Inclusive (min/max are valid)' },
            { value: 'exclusive', label: 'Exclusive (strictly inside range)' },
          ]}
        />
      </div>
    </div>
  )
}
