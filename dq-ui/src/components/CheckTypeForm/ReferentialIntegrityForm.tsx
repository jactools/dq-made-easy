import React, { useState } from 'react'
import { ReferentialIntegrityParams } from '../../types/rules'
import { ReferentialIntegrityPickerModal } from './ReferentialIntegrityPickerModal'
import { Button } from '../Button'
import { CheckTypeFieldErrors } from './checkTypeValidation'
import { AppIcon } from '../app-primitives'
import './ReferentialIntegrityForm.css'

interface ReferentialIntegrityFormProps {
  params: Partial<ReferentialIntegrityParams>
  onChange: (params: ReferentialIntegrityParams) => void
  fieldErrors?: CheckTypeFieldErrors
  catalogAttributeName?: string
}

export const ReferentialIntegrityForm: React.FC<ReferentialIntegrityFormProps> = ({ params, onChange, fieldErrors, catalogAttributeName }) => {
  const [isModalOpen, setIsModalOpen] = useState(false)

  const emit = (patch: Partial<ReferentialIntegrityParams>) =>
    onChange({
      checkType: 'REFERENTIAL_INTEGRITY',
      attribute: catalogAttributeName ?? params.attribute ?? '',
      refDataObjectId: params.refDataObjectId ?? '',
      refDataObjectVersionId: params.refDataObjectVersionId ?? '',
      refAttribute: params.refAttribute ?? '',
      refWorkspaceId: params.refWorkspaceId ?? '',
      ...patch,
    })

  const handleSelectReference = (selection: {
    refWorkspaceId: string
    refDataObjectId: string
    refDataObjectVersionId: string
    refAttribute: string
  }) => {
    emit(selection)
  }

  return (
    <>
      <div className="check-type-form referential-integrity-form">
        <div className="check-type-form-section">
          <div className="check-type-form-label-with-actions">
            <label className="check-type-form-label">Reference data object & attribute</label>
          </div>

          {params.refDataObjectId && params.refDataObjectVersionId && params.refAttribute ? (
            <div className="reference-selection-summary">
              <div className="summary-row">
                <span className="summary-label">Reference:</span>
                <span className="summary-value">{params.refDataObjectId} v{params.refDataObjectVersionId.split('-').pop()}</span>
              </div>
              <div className="summary-row">
                <span className="summary-label">Attribute:</span>
                <span className="summary-value">{params.refAttribute}</span>
              </div>
              <Button
                type="button"
                variant="secondary-default"
                className="btn-change-reference"
                onClick={() => setIsModalOpen(true)}
              >
                Change
              </Button>
            </div>
          ) : (
            <div className="reference-selection-empty">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setIsModalOpen(true)}
              >
                <AppIcon name="plus" />
                Browse Data Catalog
              </button>
            </div>
          )}
          {fieldErrors?.refDataObjectId && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.refDataObjectId}</span>
          )}
          {fieldErrors?.refDataObjectVersionId && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.refDataObjectVersionId}</span>
          )}
          {fieldErrors?.refAttribute && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.refAttribute}</span>
          )}
        </div>

        <div className="check-type-form-row">
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-ri-ref-workspace">
              Reference workspace ID (optional)
            </label>
            <input
              id="ct-ri-ref-workspace"
              type="text"
              className="modal-input"
              value={params.refWorkspaceId ?? ''}
              placeholder="e.g. retail-banking"
              onChange={(e) => emit({ refWorkspaceId: e.target.value })}
            />
          </div>

          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-ri-ref-object">
              Reference data object ID
            </label>
            <input
              id="ct-ri-ref-object"
              type="text"
              className="modal-input"
              value={params.refDataObjectId ?? ''}
              placeholder="e.g. obj_customers"
              onChange={(e) => emit({ refDataObjectId: e.target.value })}
            />
            {fieldErrors?.refDataObjectId && (
              <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.refDataObjectId}</span>
            )}
          </div>
        </div>

        <div className="check-type-form-row">
          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-ri-ref-version">
              Reference data object version ID
            </label>
            <input
              id="ct-ri-ref-version"
              type="text"
              className="modal-input"
              value={params.refDataObjectVersionId ?? ''}
              placeholder="e.g. dov-customers-v3"
              onChange={(e) => emit({ refDataObjectVersionId: e.target.value })}
            />
            {fieldErrors?.refDataObjectVersionId && (
              <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.refDataObjectVersionId}</span>
            )}
          </div>

          <div className="check-type-form-field check-type-form-field--half">
            <label className="check-type-form-label" htmlFor="ct-ri-ref-attribute">
              Reference attribute
            </label>
            <input
              id="ct-ri-ref-attribute"
              type="text"
              className="modal-input"
              value={params.refAttribute ?? ''}
              placeholder="e.g. id"
              onChange={(e) => emit({ refAttribute: e.target.value })}
            />
            {fieldErrors?.refAttribute && (
              <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.refAttribute}</span>
            )}
          </div>
        </div>
      </div>

      <ReferentialIntegrityPickerModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSelect={handleSelectReference}
        excludeCurrentAttribute={catalogAttributeName ?? params.attribute}
      />
    </>
  )
}
