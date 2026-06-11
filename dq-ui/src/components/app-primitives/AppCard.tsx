import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export interface AppCardProps extends React.HTMLAttributes<HTMLDivElement> {}

export const AppCard: React.FC<AppCardProps> = ({ className, children, ...cardProps }) => (
  <div {...cardProps} className={joinClassNames('app-card', className)}>
    {children}
  </div>
)

export interface AppCardContentProps extends React.HTMLAttributes<HTMLDivElement> {}

export const AppCardContent: React.FC<AppCardContentProps> = ({ className, children, ...contentProps }) => (
  <div {...contentProps} className={joinClassNames('app-card__content', className)}>
    {children}
  </div>
)