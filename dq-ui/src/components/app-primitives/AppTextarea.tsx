import React from 'react'
import './AppPrimitives.css'
import { AppField } from './AppField'

export interface AppTextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: React.ReactNode
  hint?: React.ReactNode
  fieldClassName?: string
  labelClassName?: string
}

export const AppTextarea: React.FC<AppTextareaProps> = ({
  label,
  hint,
  fieldClassName,
  labelClassName,
  className,
  id,
  required,
  ...textareaProps
}) => {
  return (
    <AppField label={label} htmlFor={id} required={required} hint={hint} className={fieldClassName} labelClassName={labelClassName}>
      <textarea id={id} required={required} className={['app-control app-textarea', className].filter(Boolean).join(' ')} {...textareaProps} />
    </AppField>
  )
}