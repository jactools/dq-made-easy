import React from 'react'
import './AppPrimitives.css'
import { joinClassNames } from './joinClassNames'

export type AppButtonVariant = 'primary' | 'secondary' | 'tertiary'

export interface AppButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: AppButtonVariant
  destructive?: boolean
  isLoading?: boolean
}

export const AppButton: React.FC<AppButtonProps> = ({
  variant = 'primary',
  destructive = false,
  isLoading = false,
  type = 'button',
  className,
  children,
  disabled,
  ...buttonProps
}) => {
  return (
    <button
      type={type}
      disabled={disabled || isLoading}
      aria-busy={isLoading}
      className={joinClassNames(
        'app-button',
        `app-button--${variant}`,
        destructive ? 'app-button--destructive' : undefined,
        isLoading ? 'app-button--loading' : undefined,
        className,
      )}
      {...buttonProps}
    >
      {children}
    </button>
  )
}