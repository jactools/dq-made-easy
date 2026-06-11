import React from 'react'
import {
  PlausibilityMode,
  PlausibleConditionalAllowlist,
  PlausibleContextualRange,
  PlausibleParams,
} from '../../types/rules'
import { AppSelect } from '../app-primitives'
import { CheckTypeFieldErrors } from './checkTypeValidation'

interface PlausibleFormProps {
  params: Partial<PlausibleParams>
  onChange: (params: PlausibleParams) => void
  fieldErrors?: CheckTypeFieldErrors
  catalogAttributeName?: string
}

const parseRanges = (raw: string): PlausibleContextualRange[] =>
  raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [contextValue, minValue, maxValue, inclusiveRaw] = line.split('|').map((value) => value.trim())
      const normalizeValue = (value: string | undefined): number | string | undefined => {
        if (!value) return undefined
        const numeric = Number(value)
        return Number.isFinite(numeric) ? numeric : value
      }
      return {
        contextValue: contextValue || '',
        minValue: normalizeValue(minValue),
        maxValue: normalizeValue(maxValue),
        inclusive: inclusiveRaw ? inclusiveRaw.toLowerCase() !== 'false' : true,
      }
    })

const parseAllowlists = (raw: string): PlausibleConditionalAllowlist[] =>
  raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [contextValue, valuesRaw, caseSensitiveRaw] = line.split('|').map((value) => value.trim())
      return {
        contextValue: contextValue || '',
        allowedValues: String(valuesRaw || '')
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean),
        caseSensitive: caseSensitiveRaw ? caseSensitiveRaw.toLowerCase() === 'true' : false,
      }
    })

export const PlausibleForm: React.FC<PlausibleFormProps> = ({ params, onChange, fieldErrors, catalogAttributeName }) => {
  const emit = (patch: Partial<PlausibleParams>) =>
    onChange({
      checkType: 'PLAUSIBLE',
      mode: params.mode ?? 'contextual_range',
      attribute: catalogAttributeName ?? params.attribute ?? '',
      contextAttribute: params.contextAttribute ?? '',
      ranges: params.ranges ?? [],
      allowlists: params.allowlists ?? [],
      ...patch,
    })

  const mode = params.mode ?? 'contextual_range'

  return (
    <div className="check-type-form plausible-form">
      <div className="check-type-form-field">
        <AppSelect
          id="ct-plausible-mode"
          label="Plausibility mode"
          value={mode}
          onChange={(value) => {
            const nextMode = value as PlausibilityMode
            emit({
              mode: nextMode,
              ranges: nextMode === 'contextual_range' ? params.ranges ?? [] : [],
              allowlists: nextMode === 'conditional_allowlist' ? params.allowlists ?? [] : [],
            })
          }}
          options={[
            { value: 'contextual_range', label: 'Contextual range' },
            { value: 'conditional_allowlist', label: 'Conditional allowlist' },
          ]}
        />
      </div>

      <div className="check-type-form-row">
        <div className="check-type-form-field check-type-form-field--half">
          <div className="check-type-form-field" />
        </div>

        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-plausible-context-attribute">
            Context attribute
          </label>
          <input
            id="ct-plausible-context-attribute"
            type="text"
            className="modal-input"
            value={params.contextAttribute ?? ''}
            placeholder="e.g. segment"
            onChange={(e) => emit({ contextAttribute: e.target.value })}
          />
          {fieldErrors?.contextAttribute && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.contextAttribute}</span>
          )}
        </div>
      </div>

      {mode === 'contextual_range' ? (
        <div className="check-type-form-field">
          <label className="check-type-form-label" htmlFor="ct-plausible-ranges">
            Context ranges
          </label>
          <textarea
            id="ct-plausible-ranges"
            className="modal-input"
            rows={4}
            value={(params.ranges ?? []).map((item) => [
              item.contextValue,
              item.minValue ?? '',
              item.maxValue ?? '',
              item.inclusive ?? true,
            ].join('|')).join('\n')}
            placeholder={'youth|18|25|true\nadult|26|70|true'}
            onChange={(e) => emit({ ranges: parseRanges(e.target.value), allowlists: [] })}
          />
          <span className="check-type-form-hint">
            Enter one rule per line as context|min|max|inclusive.
          </span>
          {fieldErrors?.ranges && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.ranges}</span>
          )}
        </div>
      ) : (
        <div className="check-type-form-field">
          <label className="check-type-form-label" htmlFor="ct-plausible-allowlists">
            Conditional allowlists
          </label>
          <textarea
            id="ct-plausible-allowlists"
            className="modal-input"
            rows={4}
            value={(params.allowlists ?? []).map((item) => [
              item.contextValue,
              (item.allowedValues ?? []).join(','),
              item.caseSensitive ?? false,
            ].join('|')).join('\n')}
            placeholder={'mortgage|gold,platinum|false'}
            onChange={(e) => emit({ allowlists: parseAllowlists(e.target.value), ranges: [] })}
          />
          <span className="check-type-form-hint">
            Enter one rule per line as context|value1,value2|caseSensitive.
          </span>
          {fieldErrors?.allowlists && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.allowlists}</span>
          )}
        </div>
      )}
    </div>
  )
}