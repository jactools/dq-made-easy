import React, { useState, useEffect } from 'react'
import { RuleVersion, RuleVersionComparison as RuleVersionComparisonData } from '../types/rules'
import { useSettings } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import { SecondaryButton } from './Button'
import { getAuthToken } from '../contexts/AuthContext'
import './RuleVersionComparison.css'

interface RuleVersionComparisonProps {
  version1: RuleVersion
  version2: RuleVersion
  isOpen: boolean
  onClose: () => void
}

export const RuleVersionComparison: React.FC<RuleVersionComparisonProps> = ({
  version1,
  version2,
  isOpen,
  onClose,
}) => {
  const settings = useSettings()
  const apiBaseUrl = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  const [comparison, setComparison] = useState<RuleVersionComparisonData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen && version1 && version2) {
      fetchComparison()
    }
  }, [isOpen, version1, version2])

  const fetchComparison = async () => {
    try {
      setLoading(true)
      setError(null)
      const headers: Record<string, string> = {}
      const token = getAuthToken()
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }
      const response = await fetch(
        `${apiBaseUrl}/rules/${version1.ruleId}/versions/${version1.id}/compare/${version2.id}`,
        {
          headers,
        }
      )
      if (!response.ok) throw new Error('Failed to fetch comparison')
      const data = await response.json()
      setComparison(data.comparison || null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to compare versions')
    } finally {
      setLoading(false)
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

  const getFieldLabel = (field: string): string => {
    const labels: Record<string, string> = {
      name: 'Rule Name',
      description: 'Description',
      expression: 'Expression',
      dimension: 'Dimension',
      active: 'Status',
      isTemplate: 'Template',
      templateId: 'Template ID',
      tags: 'Tags',
    }
    return labels[field] || field
  }

  const formatValue = (field: string, value: any): string => {
    if (value === null || value === undefined) return '(not set)'
    if (typeof value === 'boolean') {
      if (field === 'active') return value ? 'Active' : 'Inactive'
      if (field === 'isTemplate') return value ? 'Yes' : 'No'
      return value ? 'True' : 'False'
    }
    if (Array.isArray(value)) {
      return value.length > 0 ? value.join(', ') : '(none)'
    }
    return String(value)
  }

  const getChangeTypeColor = (changeType: string): string => {
    switch (changeType) {
      case 'added':
        return 'var(--app-status-success-text)'
      case 'removed':
        return 'var(--app-status-error-text)'
      case 'modified':
        return 'var(--app-status-warning-text)'
      default:
        return 'var(--app-text-secondary)'
    }
  }

  const getChangeTypeIcon = (changeType: string): string => {
    switch (changeType) {
      case 'added':
        return '+'
      case 'removed':
        return '−'
      case 'modified':
        return '~'
      default:
        return '•'
    }
  }

  const isSignificantField = (field: string): boolean => {
    return ['expression', 'name', 'active'].includes(field)
  }

  if (!isOpen) return null

  return (
    <div className="version-comparison-overlay" onClick={onClose}>
      <div className="version-comparison-modal" onClick={(e) => e.stopPropagation()}>
        <div className="version-comparison-header">
          <h2>Version Comparison</h2>
          <button className="version-comparison-close" onClick={onClose}>
            ×
          </button>
        </div>

        {loading ? (
          <div className="version-comparison-loading">
            <div className="spinner"></div>
            <p>Comparing versions...</p>
          </div>
        ) : error ? (
          <div className="version-comparison-error">
            <p>❌ {error}</p>
            <SecondaryButton onClick={fetchComparison}>Retry</SecondaryButton>
          </div>
        ) : comparison ? (
          <>
            <div className="version-comparison-body">
              {/* Version Headers */}
              <div className="comparison-versions-header">
                <div className="comparison-version-card">
                  <div className="version-card-label">Version {version1.versionNumber}</div>
                  <div className="version-card-date">{formatDate(version1.createdAt)}</div>
                  <div className="version-card-author">By {version1.createdBy}</div>
                </div>
                
                <div className="comparison-arrow">→</div>
                
                <div className="comparison-version-card">
                  <div className="version-card-label">Version {version2.versionNumber}</div>
                  <div className="version-card-date">{formatDate(version2.createdAt)}</div>
                  <div className="version-card-author">By {version2.createdBy}</div>
                </div>
              </div>

              {/* Significance Alert */}
              {comparison.significantChanges && (
                <div className="comparison-alert significant">
                  <span className="alert-icon">⚠️</span>
                  <div>
                    <strong>Significant Changes Detected</strong>
                    <p>Critical fields like expression or rule name were modified.</p>
                  </div>
                </div>
              )}

              {/* No Changes */}
              {comparison.differences.length === 0 && (
                <div className="comparison-alert info">
                  <span className="alert-icon">ℹ️</span>
                  <div>
                    <strong>No Differences</strong>
                    <p>These versions are identical.</p>
                  </div>
                </div>
              )}

              {/* Differences List */}
              {comparison.differences.length > 0 && (
                <div className="comparison-differences">
                  <h3 className="differences-title">
                    Changes ({comparison.differences.length})
                  </h3>
                  
                  <div className="differences-list">
                    {comparison.differences.map((diff, index) => (
                      <div
                        key={index}
                        className={`difference-item ${diff.changeType} ${
                          isSignificantField(diff.field) ? 'significant' : ''
                        }`}
                      >
                        <div className="difference-header">
                          <div className="difference-field-name">
                            <span
                              className="change-indicator"
                              style={{ color: getChangeTypeColor(diff.changeType) }}
                            >
                              {getChangeTypeIcon(diff.changeType)}
                            </span>
                            <span className="field-label">
                              {getFieldLabel(diff.field)}
                            </span>
                            {isSignificantField(diff.field) && (
                              <span className="significant-badge">Critical</span>
                            )}
                          </div>
                          <span
                            className="change-type-badge"
                            style={{ borderColor: getChangeTypeColor(diff.changeType) }}
                          >
                            {diff.changeType}
                          </span>
                        </div>

                        <div className="difference-values">
                          {diff.changeType !== 'added' && (
                            <div className="value-panel old-value">
                              <label>Version {version1.versionNumber}</label>
                              <div className="value-content">
                                {diff.field === 'expression' ? (
                                  <pre className="expression-value">{formatValue(diff.field, diff.oldValue)}</pre>
                                ) : (
                                  <div className="simple-value">{formatValue(diff.field, diff.oldValue)}</div>
                                )}
                              </div>
                            </div>
                          )}

                          {diff.changeType !== 'removed' && (
                            <div className="value-panel new-value">
                              <label>Version {version2.versionNumber}</label>
                              <div className="value-content">
                                {diff.field === 'expression' ? (
                                  <pre className="expression-value">{formatValue(diff.field, diff.newValue)}</pre>
                                ) : (
                                  <div className="simple-value">{formatValue(diff.field, diff.newValue)}</div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="version-comparison-footer">
              <SecondaryButton onClick={onClose}>Close</SecondaryButton>
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}
