import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export type AppPageHeaderTitleTag = 'h1' | 'h2' | 'h3'

export interface AppPageHeaderProps extends React.HTMLAttributes<HTMLElement> {
  eyebrow?: React.ReactNode
  title: React.ReactNode
  titleAs?: AppPageHeaderTitleTag
  description?: React.ReactNode
  actions?: React.ReactNode
}

export const AppPageHeader: React.FC<AppPageHeaderProps> = ({
  eyebrow,
  title,
  titleAs: TitleTag = 'h1',
  description,
  actions,
  className,
  children,
  ...headerProps
}) => (
  <header {...headerProps} className={joinClassNames('app-page-header', className)}>
    <div className="app-page-header__content">
      {eyebrow && <span className="app-meta-label">{eyebrow}</span>}
      <TitleTag className="app-page-title">{title}</TitleTag>
      {description && <p className="app-page-description">{description}</p>}
      {children}
    </div>
    {actions && <div className="app-page-header__actions">{actions}</div>}
  </header>
)