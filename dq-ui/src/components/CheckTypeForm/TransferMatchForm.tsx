import React from 'react'
import {
  CrossObjectComparison,
  CrossObjectComparisonMode,
  CrossObjectJoinKey,
  TransferMatchMode,
  TransferMatchParams,
} from '../../types/rules'
import { AppSelect } from '../app-primitives'
import { CheckTypeFieldErrors } from './checkTypeValidation'

interface TransferMatchFormProps {
  params: Partial<TransferMatchParams>
  onChange: (params: TransferMatchParams) => void
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

const parseComparisons = (raw: string): CrossObjectComparison[] =>
  raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [pairPart, modePart, tolerancePart] = line.split('|').map((value) => value.trim())
      const [leftAttribute, rightAttribute] = String(pairPart || '').split('=').map((value) => value.trim())
      const mode = (modePart || 'exact') as CrossObjectComparisonMode
      const tolerance = tolerancePart ? Number(tolerancePart) : undefined
      return {
        leftAttribute: leftAttribute || '',
        rightAttribute: rightAttribute || '',
        mode,
        tolerance: Number.isFinite(tolerance as number) ? tolerance : undefined,
      }
    })

export const TransferMatchForm: React.FC<TransferMatchFormProps> = ({ params, onChange, fieldErrors }) => {
  const emit = (patch: Partial<TransferMatchParams>) =>
    onChange({
      checkType: 'TRANSFER_MATCH',
      mode: params.mode ?? 'row_value_match',
      leftDataObjectVersionId: params.leftDataObjectVersionId ?? '',
      rightDataObjectVersionId: params.rightDataObjectVersionId ?? '',
      joinKeys: params.joinKeys ?? [],
      comparisons: params.comparisons ?? [],
      leftHashAttribute: params.leftHashAttribute,
      rightHashAttribute: params.rightHashAttribute,
      ...patch,
    })

  const mode = params.mode ?? 'row_value_match'

  return (
    <div className="check-type-form transfer-match-form">
      <div className="check-type-form-field">
        <AppSelect
          id="ct-transfer-match-mode"
          label="Transfer match mode"
          value={mode}
          onChange={(value) => {
            const nextMode = value as TransferMatchMode
            emit({
              mode: nextMode,
              comparisons: nextMode === 'row_value_match' ? params.comparisons ?? [] : [],
              leftHashAttribute: nextMode === 'payload_hash_match' ? params.leftHashAttribute : undefined,
              rightHashAttribute: nextMode === 'payload_hash_match' ? params.rightHashAttribute : undefined,
            })
          }}
          options={[
            { value: 'row_value_match', label: 'Row value match' },
            { value: 'payload_hash_match', label: 'Payload hash match' },
          ]}
        />
      </div>

      <div className="check-type-form-row">
        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-transfer-left-version">
            Left data object version
          </label>
          <input
            id="ct-transfer-left-version"
            type="text"
            className="modal-input"
            value={params.leftDataObjectVersionId ?? ''}
            placeholder="e.g. landing-v1"
            onChange={(e) => emit({ leftDataObjectVersionId: e.target.value })}
          />
          {fieldErrors?.leftDataObjectVersionId && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.leftDataObjectVersionId}</span>
          )}
        </div>

        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-transfer-right-version">
            Right data object version
          </label>
          <input
            id="ct-transfer-right-version"
            type="text"
            className="modal-input"
            value={params.rightDataObjectVersionId ?? ''}
            placeholder="e.g. warehouse-v2"
            onChange={(e) => emit({ rightDataObjectVersionId: e.target.value })}
          />
          {fieldErrors?.rightDataObjectVersionId && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.rightDataObjectVersionId}</span>
          )}
        </div>
      </div>

      <div className="check-type-form-field">
        <label className="check-type-form-label" htmlFor="ct-transfer-join-keys">
          Join keys
        </label>
        <textarea
          id="ct-transfer-join-keys"
          className="modal-input"
          rows={3}
          value={(params.joinKeys ?? []).map((item) => `${item.leftAttribute}=${item.rightAttribute}`).join('\n')}
          placeholder={'file_name=file_name'}
          onChange={(e) => emit({ joinKeys: parseJoinKeys(e.target.value) })}
        />
        {fieldErrors?.joinKeys && (
          <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.joinKeys}</span>
        )}
      </div>

      {mode === 'row_value_match' ? (
        <div className="check-type-form-field">
          <label className="check-type-form-label" htmlFor="ct-transfer-comparisons">
            Compared attributes
          </label>
          <textarea
            id="ct-transfer-comparisons"
            className="modal-input"
            rows={4}
            value={(params.comparisons ?? []).map((item) => [
              `${item.leftAttribute}=${item.rightAttribute}`,
              item.mode,
              item.tolerance != null ? String(item.tolerance) : '',
            ].filter(Boolean).join('|')).join('\n')}
            placeholder={'row_hash=row_hash|exact\nrow_count=row_count|numeric_tolerance|1'}
            onChange={(e) => emit({ comparisons: parseComparisons(e.target.value) })}
          />
          {fieldErrors?.comparisons && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.comparisons}</span>
          )}
          {fieldErrors?.comparisonTolerance && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.comparisonTolerance}</span>
          )}
        </div>
      ) : (
        <div className="check-type-form-row">
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-transfer-left-hash">
              Left hash attribute
            </label>
            <input
              id="ct-transfer-left-hash"
              type="text"
              className="modal-input"
              value={params.leftHashAttribute ?? ''}
              placeholder="e.g. payload_hash"
              onChange={(e) => emit({ leftHashAttribute: e.target.value, comparisons: [] })}
            />
            {fieldErrors?.leftHashAttribute && (
              <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.leftHashAttribute}</span>
            )}
          </div>

          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-transfer-right-hash">
              Right hash attribute
            </label>
            <input
              id="ct-transfer-right-hash"
              type="text"
              className="modal-input"
              value={params.rightHashAttribute ?? ''}
              placeholder="e.g. target_payload_hash"
              onChange={(e) => emit({ rightHashAttribute: e.target.value, comparisons: [] })}
            />
            {fieldErrors?.rightHashAttribute && (
              <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.rightHashAttribute}</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}