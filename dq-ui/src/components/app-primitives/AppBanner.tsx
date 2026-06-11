import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export type AppBannerVariant = 'info' | 'success' | 'warning' | 'error'

export interface AppBannerProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'children'> {
  variant: AppBannerVariant
  children: React.ReactNode
}

export const AppBanner: React.FC<AppBannerProps> = ({ variant, children, className, role, ...bannerProps }) => {
  return (
    <div {...bannerProps} className={joinClassNames('app-banner', `app-banner--${variant}`, className)} role={role ?? (variant === 'error' ? 'alert' : 'status')}>
      <div className="app-banner__body">{children}</div>
    </div>
  )
}