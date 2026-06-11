import React from 'react'
import { RuleVersion } from '../types/rules'
import { SecondaryButton, PrimaryButton } from './Button'
import { AppIcon, type AppIconName } from './app-primitives'
import './RuleVersionDetails.css'

interface RuleVersionDetailsProps {
  version: RuleVersion | null
  isOpen: boolean
  onClose: () => void
  onRollback?: (version: RuleVersion) => void
  onCompareWithCurrent?: (version: RuleVersion) => void
  isCurrentVersion?: boolean
}

export const RuleVersionDetails: React.FC<RuleVersionDetailsProps> = ({
  version,
  isOpen,
  onClose,
  onRollback,
  onCompareWithCurrent,
  isCurrentVersion = false,
}) => {
  if (!isOpen || !version) return null

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const getChangeTypeIcon = (changeType: string): AppIconName => {
    const icons: Record<string, AppIconName> = {
      created: 'plus',
      expression_updated: 'pencil',
      metadata_updated: 'document',
      status_changed: 'arrow-circle-repeat',
      rollback: 'arrow-circle-repeat',
      approval_applied: 'check-circle',
      test_proof_attached: 'shield-check',
    }
    return icons[changeType] || 'document'
  }

  const getChangeTypeLabel = (changeType: string) => {
    return changeType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  }

  const getDimensionColor = (dimension?: string) => {
    const colors: Record<string, string> = {
      Completeness: '#2196f3',
      Accuracy: '#4caf50',
      Consistency: '#ff9800',
      Timeliness: '#9c27b0',
      Validity: '#f44336',
      Uniqueness: '#00bcd4',
    }
    return dimension ? colors[dimension] || '#757575' : '#757575'
  }

  return (
    <div className="version-details-overlay" onClick={onClose}>
      <div className="version-details-modal" onClick={(e) => e.stopPropagation()}>
        <div className="version-details-header">
          <div className="version-details-title">
            <h2>
              Version {version.versionNumber}
              {isCurrentVersion && <span className="current-version-badge">Current</span>}
            </h2>
            <p className="version-details-subtitle">{formatDate(version.createdAt)}</p>
          </div>
          <button className="version-details-close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="version-details-body">
          {/* Change Information */}
          <div className="version-section">
            <h3 className="version-section-title">Change Information</h3>
            <div className="version-info-grid">
              <div className="version-info-item">
                <label>Change Type</label>
                <div className="version-change-badge">
                  <span className="version-change-icon"><AppIcon name={getChangeTypeIcon(version.changeType)} /></span>
                  <span>{getChangeTypeLabel(version.changeType)}</span>
                </div>
              </div>
              <div className="version-info-item">
                <label>Created By</label>
                <div className="version-author-info">
                  <span className="author-avatar">{version.createdBy.charAt(0).toUpperCase()}</span>
                  <span>{version.createdBy}</span>
                </div>
              </div>
              {version.validationStatus && (
                <div className="version-info-item">
                  <label>Validation</label>
                  <div className="version-author-info">
                    <span>
                      {version.validationStatus === 'valid' ? 'Valid' : version.validationStatus}
                      {' · '}
                      {version.validatedBy || version.validatedByUserId || 'unknown'}
                      {version.validatedAt ? ` · ${formatDate(version.validatedAt)}` : ''}
                    </span>
                  </div>
                </div>
              )}
              {version.changeDescription && (
                <div className="version-info-item full-width">
                  <label>Description</label>
                  <p className="version-change-description">{version.changeDescription}</p>
                </div>
              )}
            </div>
          </div>

          {/* Rule Snapshot */}
          <div className="version-section">
            <h3 className="version-section-title">Rule Snapshot at This Version</h3>
            
            <div className="version-snapshot">
              <div className="snapshot-field">
                <label>Rule Name</label>
                <div className="snapshot-value">{version.name}</div>
              </div>

              <div className="snapshot-field">
                <label>Description</label>
                <div className="snapshot-value">{version.description || '(No description)'}</div>
              </div>

              <div className="snapshot-field">
                <label>Expression</label>
                <div className="snapshot-value expression-code">
                  <code>{version.expression}</code>
                </div>
              </div>

              <div className="snapshot-field-grid">
                {version.dimension && (
                  <div className="snapshot-field">
                    <label>Dimension</label>
                    <div 
                      className="snapshot-dimension-badge"
                      style={{ backgroundColor: getDimensionColor(version.dimension) }}
                    >
                      {version.dimension}
                    </div>
                  </div>
                )}

                <div className="snapshot-field">
                  <label>Status</label>
                  <div className={`snapshot-status-badge ${version.active ? 'active' : 'inactive'}`}>
                    {version.active ? '✓ Active' : '○ Inactive'}
                  </div>
                </div>

                {version.isTemplate && (
                  <div className="snapshot-field">
                    <label>Template</label>
                    <div className="snapshot-template-badge">
                      📋 Template Rule
                    </div>
                  </div>
                )}
              </div>

              {version.tags && version.tags.length > 0 && (
                <div className="snapshot-field">
                  <label>Tags</label>
                  <div className="snapshot-tags">
                    {version.tags.map((tag, index) => (
                      <span key={index} className="snapshot-tag">{tag}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Warnings */}
          {version.markedForRollback && (
            <div className="version-warning-section">
              <div className="version-warning">
                <span className="warning-icon">⚠️</span>
                <div>
                  <strong>Marked for Rollback</strong>
                  <p>This version has been flagged for potential rollback due to issues.</p>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="version-details-footer">
          <SecondaryButton onClick={onClose}>
            Close
          </SecondaryButton>
          <div className="version-details-actions">
            {!isCurrentVersion && onCompareWithCurrent && (
              <SecondaryButton onClick={() => onCompareWithCurrent(version)}>
                Compare with Current
              </SecondaryButton>
            )}
            {!isCurrentVersion && onRollback && (
              <PrimaryButton onClick={() => onRollback(version)}>
                Rollback to This Version
              </PrimaryButton>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
