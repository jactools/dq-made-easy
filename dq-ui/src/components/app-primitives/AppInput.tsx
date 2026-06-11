import React from 'react'
import './AppPrimitives.css'
import { AppField } from './AppField'

export interface AppInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: React.ReactNode
  hint?: React.ReactNode
  fieldClassName?: string
  labelClassName?: string
}

export const AppInput: React.FC<AppInputProps> = ({
  label,
  hint,
  fieldClassName,
  labelClassName,
  className,
  id,
  required,
  ...inputProps
}) => {
  return (
    <AppField label={label} htmlFor={id} required={required} hint={hint} className={fieldClassName} labelClassName={labelClassName}>
      <input id={id} required={required} className={['app-control app-input', className].filter(Boolean).join(' ')} {...inputProps} />
    </AppField>
  )
}