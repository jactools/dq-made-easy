import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export interface AppTableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  className?: string
  wrapClassName?: string
}

export const AppTable: React.FC<AppTableProps> = ({ className, wrapClassName, children, ...tableProps }) => {
  return (
    <div className={joinClassNames('app-table__wrap', wrapClassName)}>
      <table className={joinClassNames('app-table', className)} {...tableProps}>
        {children}
      </table>
    </div>
  )
}