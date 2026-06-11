import React from 'react'
import './AppPrimitives.css'
import { AppField } from './AppField'

export type AppSelectOption = {
  value: string
  label: string
  disabled?: boolean
}

export interface AppSelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'value' | 'onChange'> {
  label: React.ReactNode
  value: string
  onChange: (value: string) => void
  options: AppSelectOption[]
  hint?: React.ReactNode
  placeholderLabel?: string
  fieldClassName?: string
  labelClassName?: string
}

export const AppSelect: React.FC<AppSelectProps> = ({
  label,
  value,
  onChange,
  options,
  hint,
  placeholderLabel = 'Choose an option',
  fieldClassName,
  labelClassName,
  className,
  id,
  required,
  ...selectProps
}) => {
  return (
    <AppField label={label} htmlFor={id} required={required} hint={hint} className={fieldClassName} labelClassName={labelClassName}>
      <select
        id={id}
        value={value}
        required={required}
        className={['app-control app-select', className].filter(Boolean).join(' ')}
        onChange={(event) => onChange(event.target.value)}
        {...selectProps}
      >
        {placeholderLabel && !value ? <option value="" disabled>{placeholderLabel}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
    </AppField>
  )
}