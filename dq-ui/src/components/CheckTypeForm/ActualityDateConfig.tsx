/**
 * Shared actuality-date configuration section for cross-object rule types.
 *
 * Used by CORRECT, RECONCILE, TRANSFER_MATCH, and JOIN_CONSISTENCY forms to
 * configure temporal-freshness guards between the two joined data deliveries.
 *
 * The component is fully controlled via props and emits a callback on every
 * change, matching the existing form pattern.
 */

import React, { useCallback, useMemo } from 'react'
import { AppSelect } from '../app-primitives'
import type { ActualityDateContract } from '../../types/rules'
import './ActualityDateConfig.css'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ActualityDateSide = 'left' | 'right'

export type ActualityDateToleranceSource =
  | 'DELIVERY_CONTRACT'
  | 'DELIVERY_METADATA'
  | 'EXPLICIT'

export type ActualityDateToleranceUnit = 'minutes' | 'hours' | 'days'

export interface ActualityDateFieldErrors {
  leftAttribute?: string
  rightAttribute?: string
  toleranceSource?: string
  contractId?: string
  resolvedToleranceValue?: string
  resolvedToleranceUnit?: string
  overrideToleranceValue?: string
  overrideToleranceUnit?: string
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ActualityDateConfigProps {
  /** Current contract state (partial is fine — form may be mid-edit). */
  value: Partial<ActualityDateContract> | undefined

  /** Called whenever the contract changes. */
  onChange: (contract: ActualityDateContract) => void

  /** Optional list of attribute options for the left side dropdown. */
  leftAttributes?: string[]

  /** Optional list of attribute options for the right side dropdown. */
  rightAttributes?: string[]

  /** Per-field validation errors. */
  fieldErrors?: ActualityDateFieldErrors

  /** When true the form is disabled (e.g. read-only view mode). */
  disabled?: boolean

  /** Optional prefix for HTML id attributes to avoid duplicates when
   *  multiple instances exist on the same page. Default: 'actuality-date'. */
  idPrefix?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TOLERANCE_SOURCES: { value: ActualityDateToleranceSource; label: string }[] = [
  { value: 'DELIVERY_CONTRACT', label: 'Delivery contract (OpenMetadata)' },
  { value: 'DELIVERY_METADATA', label: 'Delivery metadata (catalog note)' },
  { value: 'EXPLICIT', label: 'Explicit (author-supplied)' },
]

const TOLERANCE_UNITS: { value: ActualityDateToleranceUnit; label: string }[] = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
]

const defaultContract = (partial: Partial<ActualityDateContract>): ActualityDateContract => ({
  leftAttribute: partial.leftAttribute ?? '',
  rightAttribute: partial.rightAttribute ?? '',
  toleranceSource: partial.toleranceSource ?? 'DELIVERY_CONTRACT',
  contractId: partial.contractId ?? '',
  contractVersion: partial.contractVersion,
  resolvedToleranceValue: partial.resolvedToleranceValue,
  resolvedToleranceUnit: partial.resolvedToleranceUnit,
  overrideToleranceValue: partial.overrideToleranceValue,
  overrideToleranceUnit: partial.overrideToleranceUnit,
  overrideAllowed: partial.overrideAllowed,
  maxOverrideToleranceValue: partial.maxOverrideToleranceValue,
  maxOverrideToleranceUnit: partial.maxOverrideToleranceUnit,
  autoResolve: partial.autoResolve,
})

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const ActualityDateConfig: React.FC<ActualityDateConfigProps> = ({
  value,
  onChange,
  leftAttributes = [],
  rightAttributes = [],
  fieldErrors,
  disabled = false,
  idPrefix = 'actuality-date',
}) => {
  const contract = defaultContract(value ?? {})
  const overrideAllowed = contract.overrideAllowed === true
  const hasResolvedTolerance =
    contract.resolvedToleranceValue != null &&
    contract.resolvedToleranceValue !== undefined &&
    contract.resolvedToleranceUnit != null &&
    Boolean(contract.resolvedToleranceUnit)

  const overrideUnitOptions = useMemo(() => {
    if (contract.maxOverrideToleranceUnit) {
      return [contract.maxOverrideToleranceUnit]
    }
    return ['minutes', 'hours', 'days'] as ActualityDateToleranceUnit[]
  }, [contract.maxOverrideToleranceUnit])

  const emit = useCallback(
    (patch: Partial<ActualityDateContract>) => onChange({ ...contract, ...patch }),
    [contract, onChange],
  )

  // Derive whether the "explicit" section should show
  const isExplicitSource = contract.toleranceSource === 'EXPLICIT'
  const isContractSource = contract.toleranceSource === 'DELIVERY_CONTRACT'

  return (
    <div className="actuality-date-config">
      <div className="actuality-date-config__header">
        <span className="actuality-date-config__title">Actuality-date contract mapping</span>
        <span className="actuality-date-config__hint">
          Enforce a temporal-freshness guard between the two joined data deliveries.
        </span>
      </div>

      {/* Attribute pickers */}
      <div className="actuality-date-config__row">
        <div className="actuality-date-config__field actuality-date-config__field--half">
          <label className="check-type-form-label" htmlFor={`${idPrefix}-left-attribute`}>
            Left actuality attribute
          </label>
          <select
            id={`${idPrefix}-left-attribute`}
            className="modal-input"
            value={contract.leftAttribute}
            disabled={disabled}
            onChange={(e) => emit({ leftAttribute: e.target.value })}
          >
            <option value="">Select left actuality attribute</option>
            {leftAttributes.map((attr) => (
              <option key={attr} value={attr}>
                {attr}
              </option>
            ))}
          </select>
          {fieldErrors?.leftAttribute && (
            <span className="actuality-date-config__error">{fieldErrors.leftAttribute}</span>
          )}
        </div>

        <div className="actuality-date-config__field actuality-date-config__field--half">
          <label className="check-type-form-label" htmlFor={`${idPrefix}-right-attribute`}>
            Right actuality attribute
          </label>
          <select
            id={`${idPrefix}-right-attribute`}
            className="modal-input"
            value={contract.rightAttribute}
            disabled={disabled}
            onChange={(e) => emit({ rightAttribute: e.target.value })}
          >
            <option value="">Select right actuality attribute</option>
            {rightAttributes.map((attr) => (
              <option key={attr} value={attr}>
                {attr}
              </option>
            ))}
          </select>
          {fieldErrors?.rightAttribute && (
            <span className="actuality-date-config__error">{fieldErrors.rightAttribute}</span>
          )}
        </div>
      </div>

      {/* Tolerance source + contract ID / explicit tolerance */}
      <div className="actuality-date-config__row">
        <div className="actuality-date-config__field actuality-date-config__field--half">
          <label className="check-type-form-label" htmlFor={`${idPrefix}-tolerance-source`}>
            Tolerance source
          </label>
          <AppSelect
            id={`${idPrefix}-tolerance-source`}
            label=""
            value={contract.toleranceSource}
            disabled={disabled}
            onChange={(v) => emit({ toleranceSource: v as ActualityDateToleranceSource })}
            options={TOLERANCE_SOURCES}
          />
          {fieldErrors?.toleranceSource && (
            <span className="actuality-date-config__error">{fieldErrors.toleranceSource}</span>
          )}
        </div>

        {isContractSource && (
          <div className="actuality-date-config__field actuality-date-config__field--half">
            <label className="check-type-form-label" htmlFor={`${idPrefix}-contract-id`}>
              Contract ID
            </label>
            <input
              id={`${idPrefix}-contract-id`}
              type="text"
              className="modal-input"
              value={contract.contractId}
              disabled={disabled}
              placeholder="e.g. urn:dq:contract:demo-azure-payments-sql"
              onChange={(e) => emit({ contractId: e.target.value })}
            />
            {fieldErrors?.contractId && (
              <span className="actuality-date-config__error">{fieldErrors.contractId}</span>
            )}
          </div>
        )}
      </div>

      {/* Explicit tolerance section */}
      {isExplicitSource && (
        <div className="actuality-date-config__row">
          <div className="actuality-date-config__field actuality-date-config__field--half">
            <label className="check-type-form-label" htmlFor={`${idPrefix}-explicit-value`}>
              Tolerance value
            </label>
            <input
              id={`${idPrefix}-explicit-value`}
              type="number"
              className="modal-input"
              min={0}
              step={1}
              value={contract.resolvedToleranceValue ?? ''}
              disabled={disabled}
              onChange={(e) => {
                const raw = String(e.target.value || '').trim()
                if (!raw) {
                  emit({ resolvedToleranceValue: undefined, resolvedToleranceUnit: undefined })
                  return
                }
                const next = Number(raw)
                if (!Number.isFinite(next)) return
                emit({
                  resolvedToleranceValue: Math.max(0, Math.floor(next)),
                  resolvedToleranceUnit: contract.resolvedToleranceUnit ?? 'hours',
                })
              }}
            />
            {fieldErrors?.resolvedToleranceValue && (
              <span className="actuality-date-config__error">{fieldErrors.resolvedToleranceValue}</span>
            )}
          </div>

          <div className="actuality-date-config__field actuality-date-config__field--half">
            <label className="check-type-form-label" htmlFor={`${idPrefix}-explicit-unit`}>
              Tolerance unit
            </label>
            <select
              id={`${idPrefix}-explicit-unit`}
              className="modal-input"
              value={contract.resolvedToleranceUnit ?? ''}
              disabled={disabled}
              onChange={(e) => {
                const unit = e.target.value as ActualityDateToleranceUnit
                if (!unit) {
                  emit({ resolvedToleranceUnit: undefined, resolvedToleranceValue: undefined })
                  return
                }
                emit({ resolvedToleranceUnit: unit })
              }}
            >
              <option value="">Select unit</option>
              {TOLERANCE_UNITS.map((u) => (
                <option key={u.value} value={u.value}>
                  {u.label}
                </option>
              ))}
            </select>
            {fieldErrors?.resolvedToleranceUnit && (
              <span className="actuality-date-config__error">{fieldErrors.resolvedToleranceUnit}</span>
            )}
          </div>
        </div>
      )}

      {/* Resolved tolerance policy panel (read-only info) */}
      {(hasResolvedTolerance || isContractSource) && (
        <div className="actuality-date-config__policy-panel">
          <div className="actuality-date-config__policy-row">
            <span className="actuality-date-config__policy-label">Contract version</span>
            <span className="actuality-date-config__policy-value">
              {contract.contractVersion || 'Pending resolution'}
            </span>
          </div>
          <div className="actuality-date-config__policy-row">
            <span className="actuality-date-config__policy-label">Resolved tolerance</span>
            <span className="actuality-date-config__policy-value">
              {hasResolvedTolerance
                ? `${contract.resolvedToleranceValue} ${contract.resolvedToleranceUnit}`
                : 'Will be resolved by the backend on save'}
            </span>
          </div>
          <div className="actuality-date-config__policy-row">
            <span className="actuality-date-config__policy-label">Override policy</span>
            <span className="actuality-date-config__policy-value">
              {overrideAllowed ? 'Allowed' : 'Not allowed'}
            </span>
          </div>
          {overrideAllowed &&
            contract.maxOverrideToleranceValue != null &&
            contract.maxOverrideToleranceUnit && (
              <div className="actuality-date-config__policy-row">
                <span className="actuality-date-config__policy-label">Max override</span>
                <span className="actuality-date-config__policy-value">
                  {contract.maxOverrideToleranceValue} {contract.maxOverrideToleranceUnit}
                </span>
              </div>
            )}
        </div>
      )}

      {/* Override tolerance inputs (when policy allows) */}
      {overrideAllowed ? (
        <div className="actuality-date-config__row">
          <div className="actuality-date-config__field actuality-date-config__field--half">
            <label className="check-type-form-label" htmlFor={`${idPrefix}-override-value`}>
              Override tolerance value
            </label>
            <input
              id={`${idPrefix}-override-value`}
              type="number"
              className="modal-input"
              min={0}
              step={1}
              value={contract.overrideToleranceValue ?? ''}
              disabled={disabled}
              onChange={(e) => {
                const raw = String(e.target.value || '').trim()
                if (!raw) {
                  emit({ overrideToleranceValue: undefined, overrideToleranceUnit: undefined })
                  return
                }
                const next = Number(raw)
                if (!Number.isFinite(next)) return
                emit({
                  overrideToleranceValue: Math.max(0, Math.floor(next)),
                  overrideToleranceUnit:
                    contract.overrideToleranceUnit ||
                    contract.maxOverrideToleranceUnit ||
                    contract.resolvedToleranceUnit ||
                    'hours',
                })
              }}
            />
            {fieldErrors?.overrideToleranceValue && (
              <span className="actuality-date-config__error">{fieldErrors.overrideToleranceValue}</span>
            )}
          </div>

          <div className="actuality-date-config__field actuality-date-config__field--half">
            <label className="check-type-form-label" htmlFor={`${idPrefix}-override-unit`}>
              Override tolerance unit
            </label>
            <select
              id={`${idPrefix}-override-unit`}
              className="modal-input"
              value={contract.overrideToleranceUnit ?? ''}
              disabled={disabled}
              onChange={(e) => {
                const unit = e.target.value as ActualityDateToleranceUnit
                if (!unit) {
                  emit({ overrideToleranceUnit: undefined, overrideToleranceValue: undefined })
                  return
                }
                emit({ overrideToleranceUnit: unit })
              }}
            >
              <option value="">Select unit</option>
              {overrideUnitOptions.map((unit) => (
                <option key={unit} value={unit}>
                  {unit}
                </option>
              ))}
            </select>
            {fieldErrors?.overrideToleranceUnit && (
              <span className="actuality-date-config__error">{fieldErrors.overrideToleranceUnit}</span>
            )}
          </div>
        </div>
      ) : (
        <p className="actuality-date-config__hint">
          Contract policy currently disallows actuality-date override values. Resolved tolerance is authoritative.
        </p>
      )}

      <p className="actuality-date-config__hint">
        Resolved tolerance fields are populated by the backend contract resolver during create/update.
      </p>
    </div>
  )
}
