import React from 'react'
import { UniquenessParams } from '../../types/rules'
import { CheckTypeFieldErrors } from './checkTypeValidation'

interface UniquenessFormProps {
  params: Partial<UniquenessParams>
  onChange: (params: UniquenessParams) => void
  fieldErrors?: CheckTypeFieldErrors
}

const parseAttributes = (raw: string): string[] =>
  raw
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)

export const UniquenessForm: React.FC<UniquenessFormProps> = ({ params, onChange, fieldErrors }) => {
  const emit = (patch: Partial<UniquenessParams>) =>
    onChange({
      checkType: 'UNIQUENESS',
      attributes: params.attributes ?? [],
      ...patch,
    })

  return (
    <div className="check-type-form uniqueness-form">
      <div className="check-type-form-field">
        <label className="check-type-form-label" htmlFor="ct-uniq-attributes">
          Key attributes
        </label>
        <textarea
          id="ct-uniq-attributes"
          className="modal-input"
          rows={3}
          value={(params.attributes ?? []).join(', ')}
          placeholder="e.g. customer_id, order_date"
          onChange={(e) => emit({ attributes: parseAttributes(e.target.value) })}
        />
        <span className="check-type-form-hint">
          One or more columns that together must be unique.
        </span>
        {fieldErrors?.attributes && (
          <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.attributes}</span>
        )}
      </div>
    </div>
  )
}
