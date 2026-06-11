import React from 'react'

import { AppBanner } from './app-primitives'

import { TertiaryButton } from './Button'
import { formatSupportReferenceId } from '../utils/supportReference'

type StatusBannerProps = {
  variant: 'success' | 'error' | 'info'
  message: string
  onDismiss: () => void
  secondaryAction?: React.ReactNode
  referenceId?: string | null
  className?: string
}

const bannerContentStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  width: '100%',
}

const bannerTextStyle: React.CSSProperties = {
  minWidth: 0,
}

const bannerActionsStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexShrink: 0,
  flexWrap: 'wrap',
  justifyContent: 'flex-end',
}

export const StatusBanner: React.FC<StatusBannerProps> = ({
  variant,
  message,
  onDismiss,
  secondaryAction,
  referenceId,
  className,
}) => (
  <AppBanner variant={variant} className={className}>
    <div style={bannerContentStyle}>
      <div style={bannerTextStyle}>
        <span>{message}</span>
        {referenceId && <div className="settings-hint">{formatSupportReferenceId(referenceId)}</div>}
      </div>
      <div style={bannerActionsStyle}>
        {secondaryAction}
        <TertiaryButton onClick={onDismiss}>Dismiss</TertiaryButton>
      </div>
    </div>
  </AppBanner>
)
