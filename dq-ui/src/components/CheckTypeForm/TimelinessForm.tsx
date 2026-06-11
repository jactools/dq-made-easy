import React from 'react'
import { FreshnessParams, FutureDateParams, LagParams, RuleCheckType } from '../../types/rules'
import { AppSelect } from '../app-primitives'
import { CheckTypeFieldErrors } from './checkTypeValidation'

type TimelinessCheckType = Extract<RuleCheckType, 'FRESHNESS' | 'LAG' | 'FUTURE_DATE'>
type TimelinessParams = FreshnessParams | LagParams | FutureDateParams

interface TimelinessFormProps {
  checkType: TimelinessCheckType
  params: Partial<TimelinessParams>
  onChange: (params: TimelinessParams) => void
  fieldErrors?: CheckTypeFieldErrors
  catalogAttributeName?: string
}

export const TimelinessForm: React.FC<TimelinessFormProps> = ({ checkType, params, onChange, fieldErrors, catalogAttributeName }) => {
  const emit = (patch: Partial<TimelinessParams>) => {
    if (checkType === 'FRESHNESS') {
      const base: FreshnessParams = {
        checkType: 'FRESHNESS',
        attribute: catalogAttributeName ?? (params as Partial<FreshnessParams>).attribute ?? '',
        maxDaysOld: (params as Partial<FreshnessParams>).maxDaysOld ?? 1,
        anchor: (params as Partial<FreshnessParams>).anchor ?? 'now',
      }
      onChange({ ...base, ...(patch as Partial<FreshnessParams>) })
      return
    }

    if (checkType === 'LAG') {
      const base: LagParams = {
        checkType: 'LAG',
        startAttribute: (params as Partial<LagParams>).startAttribute ?? '',
        endAttribute: (params as Partial<LagParams>).endAttribute ?? '',
        maxHours: (params as Partial<LagParams>).maxHours ?? 24,
      }
      onChange({ ...base, ...(patch as Partial<LagParams>) })
      return
    }

    const base: FutureDateParams = {
      checkType: 'FUTURE_DATE',
      attribute: catalogAttributeName ?? (params as Partial<FutureDateParams>).attribute ?? '',
      referenceDate: (params as Partial<FutureDateParams>).referenceDate,
    }
    onChange({ ...base, ...(patch as Partial<FutureDateParams>) })
  }

  if (checkType === 'FRESHNESS') {
    const freshness = params as Partial<FreshnessParams>
    return (
      <div className="check-type-form timeliness-form freshness-form">
        <div className="check-type-form-row">
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-fresh-days">Max days old</label>
            <input
              id="ct-fresh-days"
              type="number"
              min={0}
              className="modal-input"
              value={freshness.maxDaysOld ?? ''}
              onChange={(e) => emit({ maxDaysOld: Number(e.target.value) || 0 })}
            />
            {fieldErrors?.maxDaysOld && (
              <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.maxDaysOld}</span>
            )}
          </div>
          <div className="check-type-form-field check-type-form-field--half">
            <AppSelect
              id="ct-fresh-anchor"
              label="Anchor"
              value={freshness.anchor ?? 'now'}
              onChange={(value) => emit({ anchor: value as FreshnessParams['anchor'] })}
              options={[
                { value: 'now', label: 'Now' },
                { value: 'processing_date', label: 'Processing date' },
              ]}
            />
          </div>
        </div>
      </div>
    )
  }

  if (checkType === 'LAG') {
    const lag = params as Partial<LagParams>
    return (
      <div className="check-type-form timeliness-form lag-form">
        <div className="check-type-form-row">
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-lag-start">Start attribute</label>
            <input
              id="ct-lag-start"
              type="text"
              className="modal-input"
              value={lag.startAttribute ?? ''}
              placeholder="e.g. created_at"
              onChange={(e) => emit({ startAttribute: e.target.value })}
            />
            {fieldErrors?.startAttribute && (
              <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.startAttribute}</span>
            )}
          </div>
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-lag-end">End attribute</label>
            <input
              id="ct-lag-end"
              type="text"
              className="modal-input"
              value={lag.endAttribute ?? ''}
              placeholder="e.g. processed_at"
              onChange={(e) => emit({ endAttribute: e.target.value })}
            />
            {fieldErrors?.endAttribute && (
              <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.endAttribute}</span>
            )}
          </div>
        </div>

        <div className="check-type-form-field">
          <label className="check-type-form-label" htmlFor="ct-lag-hours">Max lag (hours)</label>
          <input
            id="ct-lag-hours"
            type="number"
            min={0}
            className="modal-input"
            value={lag.maxHours ?? ''}
            onChange={(e) => emit({ maxHours: Number(e.target.value) || 0 })}
          />
          {fieldErrors?.maxHours && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.maxHours}</span>
          )}
        </div>
      </div>
    )
  }

  const future = params as Partial<FutureDateParams>
  return (
    <div className="check-type-form timeliness-form future-date-form">
      <div className="check-type-form-field">
        <label className="check-type-form-label" htmlFor="ct-future-reference-date">
          Reference date (optional)
        </label>
        <input
          id="ct-future-reference-date"
          type="text"
          className="modal-input"
          value={future.referenceDate ?? ''}
          placeholder="e.g. 2026-03-20"
          onChange={(e) => emit({ referenceDate: e.target.value || undefined })}
        />
        <span className="check-type-form-hint">
          Leave empty to compare with current timestamp.
        </span>
      </div>
    </div>
  )
}
