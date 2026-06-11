import React from 'react'
import { AppButton, AppIcon, type AppIconName } from './app-primitives'

interface HierarchyTreePanelProps {
  title: string
  countLabel?: string
  headerBadge?: React.ReactNode
  children: React.ReactNode
}

interface HierarchyTreeRowProps {
  levelClass?: string
  isExpanded?: boolean
  onToggle?: () => void
  active?: boolean
  onSelect?: () => void
  iconClass?: string
  label: React.ReactNode
  badge?: React.ReactNode
  className?: string
  toggleTitleExpand?: string
  toggleTitleCollapse?: string
}

interface HierarchyTreeStatusProps {
  type: 'loading' | 'empty'
  label: string
}

const normalizeIconName = (iconClass: string): AppIconName => {
  const name = iconClass.startsWith('app-icon-') ? iconClass.slice('app-icon-'.length) : iconClass
  return name as AppIconName
}

export const HierarchyTreePanel: React.FC<HierarchyTreePanelProps> = ({
  title,
  countLabel,
  headerBadge,
  children,
}) => {
  return (
    <div className="tree-panel">
      <div className="tree-header">
        <div className="tree-header-main">
          <h3>{title}</h3>
          {headerBadge}
        </div>
        {countLabel && <span className="item-count">{countLabel}</span>}
      </div>

      <div className="tree-view">{children}</div>
    </div>
  )
}

export const HierarchyTreeRow: React.FC<HierarchyTreeRowProps> = ({
  levelClass,
  isExpanded,
  onToggle,
  active,
  onSelect,
  iconClass,
  label,
  badge,
  className,
  toggleTitleExpand = 'Expand',
  toggleTitleCollapse = 'Collapse',
}) => {
  const itemClassName = ['tree-item', levelClass, className].filter(Boolean).join(' ')
  return (
    <div className={itemClassName}>
      {onToggle ? (
        <AppButton
          className="tree-toggle"
          variant="tertiary"
          onClick={onToggle}
          title={isExpanded ? toggleTitleCollapse : toggleTitleExpand}
        >
          <AppIcon name={isExpanded ? 'chevron-down' : 'chevron-right'} />
        </AppButton>
      ) : (
        <span className="tree-toggle" aria-hidden="true"></span>
      )}
      <AppButton className={`tree-label ${active ? 'active' : ''}`.trim()} onClick={onSelect} variant="tertiary">
        {iconClass && <AppIcon name={normalizeIconName(iconClass)} />}
        <span>{label}</span>
        {badge}
      </AppButton>
    </div>
  )
}

export const HierarchyTreeStatus: React.FC<HierarchyTreeStatusProps> = ({ type, label }) => {
  if (type === 'loading') {
    return (
      <div className="tree-loading">
        <AppIcon name="arrow-circle-repeat" />
        <span>{label}</span>
      </div>
    )
  }

  return (
    <div className="tree-empty">
      <span>{label}</span>
    </div>
  )
}
