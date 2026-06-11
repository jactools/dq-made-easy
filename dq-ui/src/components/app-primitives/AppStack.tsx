import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export type AppStackGap = 'xs' | 'sm' | 'md' | 'lg'

export interface AppStackProps extends React.HTMLAttributes<HTMLDivElement> {
  gap?: AppStackGap
}

export const AppStack: React.FC<AppStackProps> = ({ gap = 'md', className, children, ...stackProps }) => (
  <div {...stackProps} className={joinClassNames('app-stack', `app-stack--${gap}`, className)}>
    {children}
  </div>
)