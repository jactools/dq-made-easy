import React from 'react'
import { joinClassNames } from './joinClassNames'
import { APP_ICON_SHAPES, type AppIconName } from './appIconRegistry'
import { getLucideIconComponent } from './lucideAdapter'
import { getTablerIconComponent } from './tablerAdapter'
import { useSettingsOptional } from '../../hooks/useContexts'

export interface AppIconProps extends Omit<React.HTMLAttributes<HTMLSpanElement>, 'children'> {
  name: AppIconName
  decorative?: boolean
}

export const AppIcon: React.FC<AppIconProps> = ({ name, className, style, title, decorative = true, ...spanProps }) => {
  const settings = useSettingsOptional()
  const iconProvider = settings?.applicationSettings?.iconProvider || 'tabler'
  const providerIcon = iconProvider === 'lucide' ? getLucideIconComponent(name) : getTablerIconComponent(name)
  const ProviderIcon = providerIcon
  const ariaLabel = title && !decorative ? title : undefined
  return (
    <span {...spanProps} className={joinClassNames('app-icon', className)} style={style} aria-hidden={ariaLabel ? undefined : true} aria-label={ariaLabel} role={ariaLabel ? 'img' : undefined} title={title}>
      {ProviderIcon ? (
        <ProviderIcon size={24} aria-hidden={ariaLabel ? undefined : true} aria-label={ariaLabel} role={ariaLabel ? 'img' : undefined} title={title} strokeWidth={2} />
      ) : (
        <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
          {APP_ICON_SHAPES[name]}
        </svg>
      )}
    </span>
  )
}