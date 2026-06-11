import React, { useState } from 'react'
import { PrimaryButton } from './Button'
import { AppIcon } from './app-primitives'
import './DriftAlert.css'

export interface DriftAlertProps {
  ruleId: string
  ruleVersionId: string
  affectedAliases: string[]
  drifts: Array<{
    driftType: string
    aliasName: string
    resolvedTermName: string
    previousValue: string
    currentValue: string
    severity: string
  }>
  needsRevalidation: boolean
  onRevalidate: () => Promise<void>
  onDismiss: () => void
  onSubscribeToNotifications?: () => Promise<void>
}

/**
 * Component to display drift warnings to users
 *
 * Shows:
 * - Which business terms have changed in the catalog
 * - Severity of each change (critical vs warning)
 * - Option to revalidate the rule
 *
 * Usage:
 * <DriftAlert
 *   ruleId="rule-123"
 *   affectedAliases={['amount']}
 *   drifts={[{
 *     driftType: 'data_type_changed',
 *     aliasName: 'amount',
 *     previousValue: 'DECIMAL',
 *     currentValue: 'INTEGER'
 *   }]}
 *   needsRevalidation={true}
 *   onRevalidate={handleRevalidate}
 * />
 */
export const DriftAlert: React.FC<DriftAlertProps> = ({
  ruleId,
  ruleVersionId,
  affectedAliases,
  drifts,
  needsRevalidation,
  onRevalidate,
  onDismiss,
  onSubscribeToNotifications,
}) => {
  const [isRevalidating, setIsRevalidating] = useState(false)
  const [isSubscribing, setIsSubscribing] = useState(false)
  const [hasSubscribed, setHasSubscribed] = useState(false)

  const aliasLevelDrifts = drifts.filter((drift) => isAliasLevelDrift(drift.driftType))
  const attributeLevelDrifts = drifts.filter((drift) => !isAliasLevelDrift(drift.driftType))
  const criticalCount = drifts.filter(d => d.severity === 'critical').length
  const warningCount = drifts.filter(d => d.severity === 'warning').length
  const driftCount = drifts.length
  const aliasCount = affectedAliases.length

  if (driftCount === 0 && aliasCount === 0) {
    return null
  }

  const handleRevalidate = async () => {
    setIsRevalidating(true)
    try {
      await onRevalidate()
    } finally {
      setIsRevalidating(false)
    }
  }

  const handleSubscribe = async () => {
    if (!onSubscribeToNotifications) {
      return
    }

    setIsSubscribing(true)
    try {
      await onSubscribeToNotifications()
      setHasSubscribed(true)
    } catch (err) {
      console.error('Failed to subscribe workspace notifications:', err)
    } finally {
      setIsSubscribing(false)
    }
  }

  return (
    <div className={`drift-alert drift-alert-${needsRevalidation ? 'critical' : 'warning'}`}>
      <div className="drift-alert-header">
        <div className="drift-alert-title">
          <AppIcon name="warning" />
          <span>Business Term Changes Detected</span>
        </div>
        <button className="drift-alert-close" onClick={onDismiss} aria-label="Dismiss">
          <AppIcon name="close" />
        </button>
      </div>

      <div className="drift-alert-content">
        <p className="drift-alert-description">
          This view separates business term drift from technical attribute drift so both signals remain visible when they occur together.
        </p>

        <div className="drift-summary">
          <div className="summary-item">
            <span className="summary-label">Affected Business Terms:</span>
            <span className="summary-value">{aliasCount}</span>
          </div>
          {aliasLevelDrifts.length > 0 && (
            <div className="summary-item alias-level">
              <span className="summary-label">Business Term Drift:</span>
              <span className="summary-value">{aliasLevelDrifts.length}</span>
            </div>
          )}
          {attributeLevelDrifts.length > 0 && (
            <div className="summary-item attribute-level">
              <span className="summary-label">Technical Attribute Drift:</span>
              <span className="summary-value">{attributeLevelDrifts.length}</span>
            </div>
          )}
          {criticalCount > 0 && (
            <div className="summary-item critical">
              <span className="summary-label">Critical Changes:</span>
              <span className="summary-value">{criticalCount}</span>
            </div>
          )}
          {warningCount > 0 && (
            <div className="summary-item warning">
              <span className="summary-label">Warnings:</span>
              <span className="summary-value">{warningCount}</span>
            </div>
          )}
        </div>

        <div className="drift-details">
          {aliasLevelDrifts.length > 0 && (
            <div className="drift-group">
              <div className="drift-group-header">
                <span className="drift-group-title">Business Term Drift</span>
                <span className="drift-group-subtitle">Business term resolution and glossary mapping issues</span>
              </div>
              {aliasLevelDrifts.map((drift, idx) => renderDriftItem(drift, `alias-${idx}`, 'Business Term'))}
            </div>
          )}

          {attributeLevelDrifts.length > 0 && (
            <div className="drift-group">
              <div className="drift-group-header">
                <span className="drift-group-title">Technical Attribute Drift</span>
                <span className="drift-group-subtitle">Technical schema and data type changes on catalog attributes</span>
              </div>
              {attributeLevelDrifts.map((drift, idx) => renderDriftItem(drift, `attribute-${idx}`, 'Technical Attribute'))}
            </div>
          )}
        </div>

        {needsRevalidation && (
          <div className="drift-alert-warning">
            <AppIcon name="info-circle" />
            <span>
              This rule requires revalidation to ensure continued compatibility with the latest catalog definitions.
            </span>
          </div>
        )}
      </div>

      <div className="drift-alert-actions">
        {onSubscribeToNotifications && (
          <PrimaryButton
            onClick={handleSubscribe}
            disabled={isSubscribing || hasSubscribed}
            className="subscribe-notifications-button"
          >
            {hasSubscribed ? 'Subscribed' : isSubscribing ? 'Subscribing...' : 'Subscribe me to notifications'}
          </PrimaryButton>
        )}

        {needsRevalidation && (
          <PrimaryButton
            onClick={handleRevalidate}
            disabled={isRevalidating}
            className="revalidate-button"
          >
            {isRevalidating ? (
              <>
                <AppIcon name="arrow-circle-repeat" style={{ animation: 'spin 1s linear infinite' }} />
                Revalidating...
              </>
            ) : (
              <>
                <AppIcon name="arrow-circle-repeat" />
                Revalidate Rule
              </>
            )}
          </PrimaryButton>
        )}

        <button className="dismiss-button" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
    </div>
  )
}

const isAliasLevelDrift = (driftType: string): boolean => {
  const normalized = String(driftType || '').trim().toLowerCase()
  return normalized.startsWith('alias_')
}

const renderDriftItem = (
  drift: DriftAlertProps['drifts'][number],
  key: string,
  subjectLabel: string,
) => (
  <div key={key} className={`drift-item drift-${drift.severity.toLowerCase()}`}>
    <div className="drift-item-header">
      <span className={`drift-severity-badge ${drift.severity.toLowerCase()}`}>
        <AppIcon name={drift.severity === 'critical' ? 'warning' : 'info-circle'} /> {drift.severity.toUpperCase()}
      </span>
      <span className="drift-scope-badge">{isAliasLevelDrift(drift.driftType) ? 'BUSINESS TERM' : 'TECHNICAL ATTRIBUTE'}</span>
      <span className="drift-type-badge">{drift.driftType.toUpperCase().replace(/_/g, ' ')}</span>
    </div>

    <div className="drift-item-details">
      <div className="drift-alias">
        <span className="label">{subjectLabel}:</span>
        <strong>{drift.aliasName}</strong>
      </div>

      <div className="drift-term">
        <span className="label">Catalog Business Term:</span>
        <strong>{drift.resolvedTermName}</strong>
      </div>

      <div className="drift-change">
        <span className="label">Change:</span>
        <div className="change-values">
          <span className="previous-value">
            {drift.previousValue}
          </span>
          <span className="arrow-icon">→</span>
          <span className="current-value">
            {drift.currentValue}
          </span>
        </div>
      </div>
    </div>
  </div>
)

export default DriftAlert
