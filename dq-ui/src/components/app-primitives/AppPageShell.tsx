import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export interface AppPageShellProps extends React.HTMLAttributes<HTMLDivElement> {}

export const AppPageShell: React.FC<AppPageShellProps> = ({ className, children, ...shellProps }) => (
  <div {...shellProps} className={joinClassNames('app-page-shell', className)}>
    {children}
  </div>
)