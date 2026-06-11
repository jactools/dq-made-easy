import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export type AppToolbarAlignment = 'between' | 'start' | 'end'

export interface AppToolbarProps extends React.HTMLAttributes<HTMLDivElement> {
  align?: AppToolbarAlignment
}

export const AppToolbar: React.FC<AppToolbarProps> = ({ align = 'between', className, children, ...toolbarProps }) => (
  <div
    {...toolbarProps}
    className={joinClassNames(
      'app-toolbar',
      align === 'start' ? 'app-toolbar--start' : undefined,
      align === 'end' ? 'app-toolbar--end' : undefined,
      className,
    )}
  >
    {children}
  </div>
)