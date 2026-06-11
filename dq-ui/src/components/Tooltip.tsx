import React from 'react'
import './Tooltip.css'

interface TooltipProps {
  content: string
  children: React.ReactNode
  disabled?: boolean
}

export const Tooltip: React.FC<TooltipProps> = ({ content, children, disabled = false }) => {
  const shouldSkipForButtons = () => {
    if (!React.isValidElement(children)) {
      return false
    }

    if (typeof children.type !== 'string') {
      return false
    }

    const tagName = children.type.toLowerCase()
    return tagName === 'button' || tagName.includes('button')
  }

  if (disabled || shouldSkipForButtons()) {
    return <>{children}</>
  }

  return (
    <span className="app-tooltip-wrapper">
      {children}
      <span className="app-tooltip" role="tooltip" aria-hidden="true">
        {content}
      </span>
    </span>
  )
}
