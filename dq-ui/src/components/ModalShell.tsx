import React, { useEffect, useId } from 'react'
import './ModalShell.css'

type ModalShellSize = 'sm' | 'md' | 'lg' | 'xl'

interface ModalShellProps {
  isOpen: boolean
  onClose: () => void
  title: React.ReactNode
  children: React.ReactNode
  footer?: React.ReactNode
  size?: ModalShellSize
  dialogClassName?: string
  bodyClassName?: string
  footerClassName?: string
  titleAs?: React.ElementType
  closeLabel?: string
  closeOnEscape?: boolean
}

const joinClassNames = (...classNames: Array<string | undefined | false>) =>
  classNames.filter(Boolean).join(' ')

export const ModalShell: React.FC<ModalShellProps> = ({
  isOpen,
  onClose,
  title,
  children,
  footer,
  size = 'md',
  dialogClassName,
  bodyClassName,
  footerClassName,
  titleAs: TitleTag = 'h2',
  closeLabel = 'Close',
  closeOnEscape = true,
}) => {
  const titleId = useId()

  useEffect(() => {
    if (!isOpen || !closeOnEscape) {
      return
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [closeOnEscape, isOpen, onClose])

  if (!isOpen) {
    return null
  }

  const handleBackdropClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) {
      onClose()
    }
  }

  return (
    <div className="modal-shell-backdrop" onClick={handleBackdropClick}>
      <div
        className={joinClassNames('modal-shell', `modal-shell--${size}`, dialogClassName)}
        onClick={event => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="modal-shell__header">
          <TitleTag id={titleId} className="modal-shell__title">{title}</TitleTag>
          <button className="modal-shell__close" onClick={onClose} aria-label={closeLabel}>
            ×
          </button>
        </div>

        <div className={joinClassNames('modal-shell__body', bodyClassName)}>
          {children}
        </div>

        {footer && (
          <div className={joinClassNames('modal-shell__footer', footerClassName)}>
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}