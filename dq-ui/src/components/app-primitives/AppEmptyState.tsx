import React, { useId } from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export interface AppEmptyStateProps extends React.HTMLAttributes<HTMLElement> {
  title: React.ReactNode
  description?: React.ReactNode
  icon?: React.ReactNode
  actions?: React.ReactNode
}

export const AppEmptyState: React.FC<AppEmptyStateProps> = ({
  title,
  description,
  icon,
  actions,
  className,
  children,
  ...emptyStateProps
}) => {
  const titleId = useId()
  const descriptionId = useId()

  return (
    <section
      {...emptyStateProps}
      role="status"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      className={joinClassNames('app-empty-state', className)}
    >
      {icon && <div className="app-empty-state__icon">{icon}</div>}
      <h2 id={titleId} className="app-empty-state__title">
        {title}
      </h2>
      {description && (
        <p id={descriptionId} className="app-empty-state__description">
          {description}
        </p>
      )}
      {children}
      {actions && <div className="app-empty-state__actions">{actions}</div>}
    </section>
  )
}