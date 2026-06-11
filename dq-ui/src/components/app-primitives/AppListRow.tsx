import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export type AppListRowTag = 'div' | 'li' | 'article'

export interface AppListRowProps extends React.HTMLAttributes<HTMLElement> {
  as?: AppListRowTag
  title: React.ReactNode
  meta?: React.ReactNode
  actions?: React.ReactNode
  selected?: boolean
}

export const AppListRow: React.FC<AppListRowProps> = ({
  as: RowTag = 'div',
  title,
  meta,
  actions,
  selected = false,
  className,
  children,
  ...rowProps
}) => {
  const isListItem = RowTag === 'li'

  return (
    <RowTag
      {...rowProps}
      role={isListItem ? undefined : 'listitem'}
      aria-selected={selected || undefined}
      className={joinClassNames('app-list-row', selected ? 'app-list-row--selected' : undefined, className)}
    >
      <div className="app-list-row__content">
        <div className="app-list-row__title">{title}</div>
        {meta && <div className="app-list-row__meta">{meta}</div>}
        {children}
      </div>
      {actions && <div className="app-list-row__actions">{actions}</div>}
    </RowTag>
  )
}