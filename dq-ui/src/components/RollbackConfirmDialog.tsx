import React, { useState } from 'react'
import { RuleVersion } from '../types/rules'
import { PrimaryButton, SecondaryButton } from './Button'
import { AppIcon, AppTextarea } from './app-primitives'
import './RollbackConfirmDialog.css'

interface RollbackConfirmDialogProps {
  isOpen: boolean
  ruleName: string
  targetVersion: RuleVersion | null
  currentVersion: RuleVersion | null
  onConfirm: (reason: string) => Promise<void>
  onCancel: () => void
}

export const RollbackConfirmDialog: React.FC<RollbackConfirmDialogProps> = ({
  isOpen,
  ruleName,
  targetVersion,
  currentVersion,
  onConfirm,
  onCancel,
}) => {
  const [reason, setReason] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleConfirm = async () => {
    if (!reason.trim()) {
      setError('Please provide a reason for the rollback')
      return
    }

    setIsLoading(true)
    setError(null)
    
    try {
      await onConfirm(reason)
      setReason('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Rollback failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCancel = () => {
    if (!isLoading) {
      setReason('')
      setError(null)
      onCancel()
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  if (!isOpen || !targetVersion || !currentVersion) return null

  return (
    <div className="rollback-dialog-overlay" onClick={handleCancel}>
      <div className="rollback-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="rollback-dialog-header">
          <div className="rollback-icon-large"><AppIcon name="arrow-circle-repeat" /></div>
          <h2>Confirm Rollback</h2>
          <button 
            className="rollback-dialog-close" 
            onClick={handleCancel}
            disabled={isLoading}
          >
            ×
          </button>
        </div>

        <div className="rollback-dialog-body">
          <div className="rollback-warning-box">
            <span className="warning-icon"><AppIcon name="warning" /></span>
            <div>
              <strong>Important: This action creates a new version</strong>
              <p>
                Rolling back does not delete history. Instead, it creates a new version 
                with the content from version {targetVersion.versionNumber}. 
                You can always roll forward again if needed.
              </p>
            </div>
          </div>

          <div className="rollback-details-section">
            <h3>Rollback Details</h3>
            
            <div className="rollback-rule-name">
              <label>Rule</label>
              <div className="rule-name-value">{ruleName}</div>
            </div>

            <div className="rollback-versions-info">
              <div className="version-info-box current">
                <div className="version-box-label">Current Version</div>
                <div className="version-box-number">v{currentVersion.versionNumber}</div>
                <div className="version-box-date">{formatDate(currentVersion.createdAt)}</div>
                <div className="version-box-author">By {currentVersion.createdBy}</div>
              </div>

              <div className="rollback-arrow-icon"><AppIcon name="arrow-right" /></div>

              <div className="version-info-box target">
                <div className="version-box-label">Rollback Target</div>
                <div className="version-box-number">v{targetVersion.versionNumber}</div>
                <div className="version-box-date">{formatDate(targetVersion.createdAt)}</div>
                <div className="version-box-author">By {targetVersion.createdBy}</div>
              </div>
            </div>

            <div className="rollback-reason-input">
              <label htmlFor="rollback-reason">
                Reason for Rollback <span className="required">*</span>
              </label>
              <AppTextarea
                label="Reason for Rollback"
                id="rollback-reason"
                placeholder="Explain why you're rolling back to this version (e.g., 'Critical bug in expression', 'Incorrect business logic', etc.)"
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value || '')
                  setError(null)
                }}
                disabled={isLoading}
                rows={3}
              />
              {error && <div className="rollback-error">{error}</div>}
            </div>
          </div>

          <div className="rollback-impact-section">
            <h4>What will happen?</h4>
            <ul className="rollback-impact-list">
              <li>
                <span className="impact-icon"><AppIcon name="document" /></span>
                A new version (v{currentVersion.versionNumber + 1}) will be created
              </li>
              <li>
                <span className="impact-icon">↩️</span>
                The new version will contain the exact state from v{targetVersion.versionNumber}
              </li>
              <li>
                <span className="impact-icon"><AppIcon name="line-chart" /></span>
                All version history will be preserved (no data loss)
              </li>
              <li>
                <span className="impact-icon"><AppIcon name="search" /></span>
                An audit entry will record this rollback action
              </li>
            </ul>
          </div>
        </div>

        <div className="rollback-dialog-footer">
          <SecondaryButton onClick={handleCancel} disabled={isLoading}>
            Cancel
          </SecondaryButton>
          <PrimaryButton 
            onClick={handleConfirm} 
            disabled={isLoading || !reason.trim()}
            className="rollback-confirm-button"
          >
            {isLoading ? (
              <>
                <span className="spinner-small"></span>
                Rolling Back...
              </>
            ) : (
              <>Confirm Rollback</>
            )}
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}
