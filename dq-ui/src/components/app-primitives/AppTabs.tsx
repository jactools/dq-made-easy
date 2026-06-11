import React from 'react'
import './AppPrimitives.css'
import { AppIcon } from './AppIcon'
import { joinClassNames } from './joinClassNames'

export interface AppTabItem<T extends string = string> {
  value: T
  label: string
  iconName?: React.ComponentProps<typeof AppIcon>['name']
  title?: string
  disabled?: boolean
}

export interface AppTabsProps<T extends string = string> {
  ariaLabel: string
  value: T
  onChange: (value: T) => void
  tabs: Array<AppTabItem<T>>
  className?: string
}

export const AppTabs = <T extends string,>({ ariaLabel, value, onChange, tabs, className }: AppTabsProps<T>) => {
  return (
    <div className={joinClassNames('app-tabs', className)} role="tablist" aria-label={ariaLabel}>
      {tabs.map((tab) => {
        const selected = tab.value === value
        return (
          <button
            key={tab.value}
            type="button"
            className="app-tabs__button"
            role="tab"
            aria-selected={selected}
            title={tab.title || tab.label}
            disabled={tab.disabled}
            onClick={() => {
              if (!tab.disabled) {
                onChange(tab.value)
              }
            }}
          >
            {tab.iconName ? <AppIcon className="app-tabs__icon" name={tab.iconName} decorative /> : null}
            <span>{tab.label}</span>
          </button>
        )
      })}
    </div>
  )
}