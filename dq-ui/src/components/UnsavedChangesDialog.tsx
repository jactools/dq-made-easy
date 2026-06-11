import React from 'react'
import { PrimaryButton, SecondaryButton } from '../components/Button'
import './UnsavedChangesDialog.css'

export interface UnsavedChangesDialogProps {
  isOpen: boolean
  onConfirm: () => void
  onCancel: () => void
  title?: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
}

/**
 * Reusable confirmation dialog component for unsaved changes across the app.
 * 
 * @param isOpen - Whether the dialog should be displayed
 * @param onConfirm - Callback when user confirms discard
 * @param onCancel - Callback when user cancels
 * @param title - Dialog title (default: "Discard Changes?")
 * @param message - Dialog message (default: "You have unsaved changes...")
 * @param confirmLabel - Confirm button label (default: "Discard Changes")
 * @param cancelLabel - Cancel button label (default: "Keep Editing")
 */
export const UnsavedChangesDialog: React.FC<UnsavedChangesDialogProps> = ({
  isOpen,
  onConfirm,
  onCancel,
  title = 'Discard Changes?',
  message = 'You have unsaved changes. Are you sure you want to close without saving?',
  confirmLabel = 'Discard Changes',
  cancelLabel = 'Keep Editing',
}) => {
  if (!isOpen) return null

  return (
    <div className="unsaved-changes-overlay" onClick={onCancel}>
      <div className="unsaved-changes-dialog" onClick={e => e.stopPropagation()}>
        <div className="unsaved-changes-header">
          <h2>{title}</h2>
        </div>
        <div className="unsaved-changes-body">
          <p>{message}</p>
        </div>
        <div className="unsaved-changes-footer">
          <SecondaryButton onClick={onCancel}>
            {cancelLabel}
          </SecondaryButton>
          <PrimaryButton onClick={onConfirm} className="unsaved-changes-confirm-btn">
            {confirmLabel}
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}
