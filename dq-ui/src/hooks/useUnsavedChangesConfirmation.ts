import { useState, useCallback, useMemo, useEffect } from 'react'

export interface UseUnsavedChangesConfirmationProps {
  isOpen: boolean
  hasChanges: boolean | (() => boolean)
  onClose: () => void
}

export interface UseUnsavedChangesConfirmationReturn {
  showConfirmation: boolean
  hasModifications: boolean
  handleCloseWithConfirmation: () => void
  handleConfirmClose: () => void
  handleCancelConfirmation: () => void
  handleEscapeKey: () => void
}

/**
 * Custom hook for managing unsaved changes confirmation dialogs across the app.
 * 
 * @param isOpen - Whether the parent modal is open
 * @param hasChanges - Boolean or function that returns whether form has unsaved changes
 * @param onClose - Callback to close the parent modal
 * @returns Object with confirmation state and handlers
 * 
 * @example
 * const { showConfirmation, handleCloseWithConfirmation, handleConfirmClose, handleCancelConfirmation } = useUnsavedChangesConfirmation({
 *   isOpen,
 *   hasChanges: modification,
 *   onClose
 * })
 */
export const useUnsavedChangesConfirmation = ({
  isOpen,
  hasChanges,
  onClose,
}: UseUnsavedChangesConfirmationProps): UseUnsavedChangesConfirmationReturn => {
  const [showConfirmation, setShowConfirmation] = useState(false)

  // Resolve hasChanges - can be boolean or function
  const hasModifications = useMemo(() => {
    return typeof hasChanges === 'function' ? hasChanges() : hasChanges
  }, [hasChanges])

  const handleCloseWithConfirmation = useCallback(() => {
    if (hasModifications) {
      setShowConfirmation(true)
    } else {
      onClose()
    }
  }, [hasModifications, onClose])

  const handleConfirmClose = useCallback(() => {
    setShowConfirmation(false)
    onClose()
  }, [onClose])

  const handleCancelConfirmation = useCallback(() => {
    setShowConfirmation(false)
  }, [])

  const handleEscapeKey = useCallback(() => {
    handleCloseWithConfirmation()
  }, [handleCloseWithConfirmation])

  // Setup escape key listener
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleEscapeKey()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, handleEscapeKey])

  return {
    showConfirmation,
    hasModifications,
    handleCloseWithConfirmation,
    handleConfirmClose,
    handleCancelConfirmation,
    handleEscapeKey,
  }
}
