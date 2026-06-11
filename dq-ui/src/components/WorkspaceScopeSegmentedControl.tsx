import React from 'react'
import { AppTabs, type AppIconName } from './app-primitives'
import './WorkspaceScopeSegmentedControl.css'

export type WorkspaceScope = 'my' | 'team' | 'all' | 'global'

export interface WorkspaceScopeOption {
  value: WorkspaceScope
  label: string
  icon: AppIconName
  title: string
  disabled?: boolean
  disabledTitle?: string
}

export const DEFAULT_WORKSPACE_SCOPE_OPTIONS: WorkspaceScopeOption[] = [
  {
    value: 'my',
    label: 'My',
    icon: 'person',
    title: 'Show data you own in current workspace',
  },
  {
    value: 'team',
    label: "My Team's",
    icon: 'people',
    title: 'Show data owned by your team in current workspace',
  },
  {
    value: 'all',
    label: 'All',
    icon: 'table',
    title: 'Show all data in current workspace',
  },
  {
    value: 'global',
    label: 'All Across',
    icon: 'globe',
    title: 'Show data across all workspaces',
  },
]

interface WorkspaceScopeSegmentedControlProps {
  value: WorkspaceScope
  onChange: (scope: WorkspaceScope) => void
  ariaLabel: string
  label?: string
  options?: WorkspaceScopeOption[]
  className?: string
  controlClassName?: string
  labelClassName?: string
  variant?: 'default' | 'emphasis'
}

const joinClassNames = (...values: Array<string | undefined>): string => values.filter(Boolean).join(' ')

export const WorkspaceScopeSegmentedControl: React.FC<WorkspaceScopeSegmentedControlProps> = ({
  value,
  onChange,
  ariaLabel,
  label,
  options = DEFAULT_WORKSPACE_SCOPE_OPTIONS,
  className,
  controlClassName,
  labelClassName,
  variant = 'emphasis',
}) => {
  return (
    <div className={joinClassNames('workspace-scope-segmented-control', className)}>
      {label ? <span className={joinClassNames('workspace-scope-segmented-control__label', labelClassName)}>{label}</span> : null}
      <AppTabs
        ariaLabel={ariaLabel}
        value={value}
        onChange={onChange}
        className={joinClassNames('workspace-scope-segmented-control__control', controlClassName, variant === 'emphasis' ? 'workspace-scope-segmented-control__control--emphasis' : undefined)}
        tabs={options.map((option) => ({
          value: option.value,
          label: option.label,
          iconName: option.icon,
          title: option.disabled ? option.disabledTitle || option.title : option.title,
          disabled: option.disabled,
        }))}
      />
    </div>
  )
}