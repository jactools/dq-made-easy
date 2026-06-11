import React from 'react'
import { getWorkspaceDisplayName } from '../WorkspaceSelector'
import { ResolvedRuleAttribute } from './ruleDisplayUtils'

interface AttributeCardProps {
  attribute: ResolvedRuleAttribute
  /** Rendered below the name line (e.g. a threshold badge). Optional. */
  badge?: React.ReactNode
  /** Extra CSS class names to add to the outer .rule-attribute-item div. */
  className?: string
}

/**
 * Displays an attribute with its full lineage:
 *   Dataset / DataObject – AttributeName   (bold top line)
 *   Data-object version                    (secondary, when present)
 *   Data product name                      (secondary, when present)
 */
export const AttributeCard: React.FC<AttributeCardProps> = ({ attribute, badge, className }) => {
  const sourceParts = [attribute.datasetName, attribute.dataObjectName].filter(Boolean)
  const sourceLabel = sourceParts.length > 0 ? sourceParts.join(' / ') : null
  const attributeName = String(attribute.name || '').trim()
  const displayName = attributeName
    ? (sourceLabel ? `${sourceLabel} – ${attributeName}` : attributeName)
    : (sourceLabel || 'Unresolved attribute')
  const workspaceLabel = String(attribute.workspaceId || '').trim()

  return (
    <div className={`rule-attribute-item${className ? ` ${className}` : ''}`}>
      <span className="rule-attribute-name">{displayName}</span>
      {badge}
      {workspaceLabel && (
        <span className="rule-attribute-source" title={`Workspace: ${workspaceLabel}`}>
          Workspace: {getWorkspaceDisplayName(workspaceLabel)}
        </span>
      )}
      {attribute.dataObjectVersion && (
        <span className="rule-attribute-source">
          Version: {attribute.dataObjectVersion}
        </span>
      )}
      {attribute.dataProductName && (
        <span className="rule-attribute-source">{attribute.dataProductName}</span>
      )}
    </div>
  )
}
