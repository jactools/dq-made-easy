import { useCallback } from 'react'
import type { MouseEvent, ReactNode } from 'react'
import { AppButton, type AppButtonVariant } from './app-primitives'

type RdsButtonVariant = 
  | 'primary-default'
  | 'primary-destructive'
  | 'secondary-default'
  | 'secondary-destructive'
  | 'tertiary-default'
  | 'tertiary-destructive'

interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'tertiary' | RdsButtonVariant
  destructive?: boolean
  disabled?: boolean
  title?: string
  onClick?: (e?: MouseEvent) => void
  type?: 'button' | 'submit' | 'reset'
  children: ReactNode
  className?: string
}

const toAppButtonVariant = (variant: ButtonProps['variant']): AppButtonVariant => {
  if (variant?.startsWith('secondary')) {
    return 'secondary'
  }
  if (variant?.startsWith('tertiary')) {
    return 'tertiary'
  }
  return 'primary'
}

export function Button({ 
  variant = 'primary', 
  destructive = false,
  children,
  disabled = false,
  onClick,
  ...buttonProps
}: ButtonProps) {
  const handleClick = useCallback(
    (event?: MouseEvent) => {
      if (disabled) {
        event?.preventDefault()
        event?.stopPropagation()
        return
      }
      onClick?.(event)
    },
    [disabled, onClick]
  )

  return (
    <AppButton
      variant={toAppButtonVariant(variant)}
      destructive={destructive || variant.endsWith('-destructive')}
      disabled={disabled}
      onClick={handleClick}
      {...buttonProps}
    >
      {children}
    </AppButton>
  )
}

/**
 * Primary action button (filled, prominent)
 */
export function PrimaryButton(props: Omit<ButtonProps, 'variant'>) {
  return <Button {...props} variant="primary" />
}

/**
 * Secondary action button (outlined, less prominent)
 */
export function SecondaryButton(props: Omit<ButtonProps, 'variant'>) {
  return <Button {...props} variant="secondary" />
}

/**
 * Tertiary action button (text only, minimal)
 */
export function TertiaryButton(props: Omit<ButtonProps, 'variant'>) {
  return <Button {...props} variant="tertiary" />
}
