import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export interface AppFieldProps {
  label: React.ReactNode
  htmlFor?: string
  required?: boolean
  hint?: React.ReactNode
  className?: string
  labelClassName?: string
  hintClassName?: string
  children: React.ReactNode
}

export const AppField: React.FC<AppFieldProps> = ({
  label,
  htmlFor,
  required = false,
  hint,
  className,
  labelClassName,
  hintClassName,
  children,
}) => {
  return (
    <div className={joinClassNames('app-field', className)}>
      <label className={joinClassNames('app-field__label', labelClassName)} htmlFor={htmlFor}>
        <span>{label}</span>
        {required ? <span className="app-field__required" aria-hidden="true">*</span> : null}
      </label>
      {children}
      {hint ? <div className={joinClassNames('app-field__hint', hintClassName)}>{hint}</div> : null}
    </div>
  )
}