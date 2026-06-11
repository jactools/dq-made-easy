import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export type AppBadgeTone = 'neutral' | 'success' | 'info' | 'warning' | 'error'

export interface AppBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: AppBadgeTone
}

export const AppBadge: React.FC<AppBadgeProps> = ({ tone = 'neutral', className, children, ...badgeProps }) => (
  <span {...badgeProps} className={joinClassNames('app-status-chip', `app-status-chip--${tone}`, className)}>
    {children}
  </span>
)