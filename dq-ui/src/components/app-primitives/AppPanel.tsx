import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export type AppPanelTone = 'default' | 'muted' | 'elevated'
export type AppPanelTag = 'div' | 'section' | 'article'

export interface AppPanelProps extends React.HTMLAttributes<HTMLElement> {
  as?: AppPanelTag
  tone?: AppPanelTone
  eyebrow?: React.ReactNode
  title?: React.ReactNode
  titleAs?: 'h2' | 'h3'
  description?: React.ReactNode
  actions?: React.ReactNode
  bodyClassName?: string
}

export const AppPanel: React.FC<AppPanelProps> = ({
  as: PanelTag = 'section',
  tone = 'default',
  eyebrow,
  title,
  titleAs: TitleTag = 'h2',
  description,
  actions,
  bodyClassName,
  className,
  children,
  ...panelProps
}) => {
  const panelClassName = joinClassNames(
    'app-panel',
    tone !== 'default' ? `app-panel--${tone}` : undefined,
    className,
  )

  const hasHeader = eyebrow || title || description || actions

  return (
    <PanelTag {...panelProps} className={panelClassName}>
      {hasHeader && (
        <div className="app-panel__header">
          <div className="app-panel__heading-group">
            {eyebrow && <span className="app-meta-label">{eyebrow}</span>}
            {title && <TitleTag className="app-panel__title">{title}</TitleTag>}
            {description && <p className="app-panel__description">{description}</p>}
          </div>
          {actions && <div className="app-action-row">{actions}</div>}
        </div>
      )}
      {children && <div className={joinClassNames('app-panel__body', bodyClassName)}>{children}</div>}
    </PanelTag>
  )
}