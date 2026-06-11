import React from 'react'
import { PresentParams } from '../../types/rules'
import { AppSelect } from '../app-primitives'
import { CheckTypeFieldErrors } from './checkTypeValidation'

interface PresentFormProps {
  params: Partial<PresentParams>
  onChange: (params: PresentParams) => void
  fieldErrors?: CheckTypeFieldErrors
  catalogAttributeName?: string
}

const parseValues = (raw: string): string[] =>
  raw
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)

export const PresentForm: React.FC<PresentFormProps> = ({ params, onChange, fieldErrors, catalogAttributeName }) => {
  const emit = (patch: Partial<PresentParams>) =>
    onChange({
      checkType: 'PRESENT',
      attribute: catalogAttributeName ?? params.attribute ?? '',
      blockedValues: params.blockedValues ?? [],
      caseSensitive: params.caseSensitive ?? false,
      ...patch,
    })

  return (
    <div className="check-type-form present-form">
      <div className="check-type-form-field">
        <label className="check-type-form-label" htmlFor="ct-present-blocked-values">
          Placeholder values (optional)
        </label>
        <textarea
          id="ct-present-blocked-values"
          className="modal-input"
          rows={3}
          value={(params.blockedValues ?? []).join(', ')}
          placeholder="e.g. UNKNOWN, N/A"
          onChange={(e) => emit({ blockedValues: parseValues(e.target.value) })}
        />
        <span className="check-type-form-hint">
          Values that should be treated as missing in addition to NULL and blank strings.
        </span>
        {fieldErrors?.blockedValues && (
          <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.blockedValues}</span>
        )}
      </div>

      <div className="check-type-form-field">
        <AppSelect
          id="ct-present-case-sensitive"
          label="Placeholder comparison"
          value={(params.caseSensitive ?? false) ? 'yes' : 'no'}
          onChange={(value) => emit({ caseSensitive: value === 'yes' })}
          options={[
            { value: 'no', label: 'Case-insensitive' },
            { value: 'yes', label: 'Case-sensitive' },
          ]}
        />
      </div>
    </div>
  )
}