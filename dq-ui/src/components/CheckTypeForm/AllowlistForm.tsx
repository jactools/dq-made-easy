import React from 'react'
import { AllowlistParams, BlocklistParams, RuleCheckType } from '../../types/rules'
import { AppSelect } from '../app-primitives'
import { CheckTypeFieldErrors } from './checkTypeValidation'

type ListParams = AllowlistParams | BlocklistParams

interface AllowlistFormProps {
  checkType: Extract<RuleCheckType, 'ALLOWLIST' | 'BLOCKLIST'>
  params: Partial<ListParams>
  onChange: (params: ListParams) => void
  fieldErrors?: CheckTypeFieldErrors
  catalogAttributeName?: string
}

const parseValues = (raw: string): string[] =>
  raw
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)

export const AllowlistForm: React.FC<AllowlistFormProps> = ({ checkType, params, onChange, fieldErrors, catalogAttributeName }) => {
  const values = checkType === 'ALLOWLIST'
    ? ((params as Partial<AllowlistParams>).allowedValues ?? [])
    : ((params as Partial<BlocklistParams>).blockedValues ?? [])

  const emit = (patch: Partial<ListParams>) => {
    const baseCommon = {
      attribute: catalogAttributeName ?? params.attribute ?? '',
      caseSensitive: params.caseSensitive ?? false,
    }

    if (checkType === 'ALLOWLIST') {
      const base: AllowlistParams = {
        checkType: 'ALLOWLIST',
        ...baseCommon,
        allowedValues: (params as Partial<AllowlistParams>).allowedValues ?? [],
      }
      onChange({ ...base, ...(patch as Partial<AllowlistParams>) })
      return
    }

    const base: BlocklistParams = {
      checkType: 'BLOCKLIST',
      ...baseCommon,
      blockedValues: (params as Partial<BlocklistParams>).blockedValues ?? [],
    }
    onChange({ ...base, ...(patch as Partial<BlocklistParams>) })
  }

  return (
    <div className="check-type-form allowlist-form">
      <div className="check-type-form-field">
        <label className="check-type-form-label" htmlFor="ct-list-values">
          {checkType === 'ALLOWLIST' ? 'Allowed values' : 'Blocked values'}
        </label>
        <textarea
          id="ct-list-values"
          className="modal-input"
          rows={4}
          value={values.join(', ')}
          placeholder="e.g. US, NL, DE"
          onChange={(e) => {
            const parsed = parseValues(e.target.value)
            if (checkType === 'ALLOWLIST') {
              emit({ allowedValues: parsed } as Partial<AllowlistParams>)
            } else {
              emit({ blockedValues: parsed } as Partial<BlocklistParams>)
            }
          }}
        />
        <span className="check-type-form-hint">
          Enter a comma-separated list of literals.
        </span>
        {checkType === 'ALLOWLIST' && fieldErrors?.allowedValues && (
          <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.allowedValues}</span>
        )}
        {checkType === 'BLOCKLIST' && fieldErrors?.blockedValues && (
          <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.blockedValues}</span>
        )}
      </div>

      <div className="check-type-form-field">
        <AppSelect
          id="ct-list-case-sensitive"
          label="Case sensitivity"
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
