import React from 'react'
import { RegexParams } from '../../types/rules'
import { AppSelect } from '../app-primitives'
import { CheckTypeFieldErrors } from './checkTypeValidation'

interface RegexFormProps {
  params: Partial<RegexParams>
  onChange: (params: RegexParams) => void
  fieldErrors?: CheckTypeFieldErrors
  catalogAttributeName?: string
}

const FLAG_OPTIONS = [
  { value: '', label: 'None' },
  { value: 'i', label: 'i (case-insensitive)' },
  { value: 'm', label: 'm (multi-line)' },
  { value: 's', label: 's (dot matches newline)' },
  { value: 'im', label: 'im (case-insensitive + multi-line)' },
]

export const RegexForm: React.FC<RegexFormProps> = ({ params, onChange, fieldErrors, catalogAttributeName }) => {
  const emit = (patch: Partial<RegexParams>) =>
    onChange({
      checkType: 'REGEX',
      attribute: catalogAttributeName ?? params.attribute ?? '',
      pattern: params.pattern ?? '',
      flags: params.flags ?? '',
      ...patch,
    })

  return (
    <div className="check-type-form regex-form">
      <div className="check-type-form-field">
        <label className="check-type-form-label" htmlFor="ct-regex-pattern">
          Regex pattern
        </label>
        <input
          id="ct-regex-pattern"
          type="text"
          className="modal-input"
          value={params.pattern ?? ''}
          placeholder="e.g. ^[^@]+@[^@]+\\.[^@]+$"
          onChange={(e) => emit({ pattern: e.target.value })}
        />
        <span className="check-type-form-hint">
          Use a raw regex pattern without surrounding slashes.
        </span>
        {fieldErrors?.pattern && (
          <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.pattern}</span>
        )}
      </div>

      <div className="check-type-form-field">
        <AppSelect
          id="ct-regex-flags"
          label="Regex flags (optional)"
          value={params.flags ?? ''}
          onChange={(value) => emit({ flags: value })}
          options={FLAG_OPTIONS}
        />
      </div>
    </div>
  )
}
