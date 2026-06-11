import React, { useMemo } from 'react'
import { Rule, AuditLogEntry } from '../types/rules'
import './RuleVersioning.css'

export interface RuleVersion extends Rule {
  versionNumber: number
  changedAt: string
  changedBy: string
  changeDescription: string
}

interface RuleVersioningProps {
  rule: Rule
  auditLog: AuditLogEntry[]
  onRestoreVersion?: (versionNumber: number) => void
}

export const RuleVersioning: React.FC<RuleVersioningProps> = ({
  rule,
  auditLog,
  onRestoreVersion,
}) => {
  const versions = useMemo((): RuleVersion[] => {
    const versionMap: Map<number, RuleVersion> = new Map()
    let versionCounter = 1

    // Add current version
    const currentVersion: RuleVersion = {
      ...rule,
      versionNumber: versionCounter,
      changedAt: rule.updatedAt ?? rule.createdAt,
      changedBy: rule.createdBy ?? '',
      changeDescription: 'Current version',
    }
    versionMap.set(versionCounter, currentVersion)

    // Build versions from audit log in reverse chronological order
    const sortedAudit = [...auditLog]
      .filter((entry) => entry.ruleId === rule.id)
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())

    const changeMap = new Map<string, string>()
    changeMap.set('created', 'Rule created')
    changeMap.set('modified', 'Rule modified')
    changeMap.set('tested', 'Test executed')
    changeMap.set('submitted', 'Submitted for approval')
    changeMap.set('approved', 'Approved')
    changeMap.set('rejected', 'Rejected')
    changeMap.set('activated', 'Activated')
    changeMap.set('deactivated', 'Deactivated')
    changeMap.set('deleted', 'Deleted')

    // Generate versions from audit trail
    sortedAudit.forEach((entry) => {
      versionCounter++
      const description = changeMap.get(entry.action) || entry.action
      const version: RuleVersion = {
        ...rule,
        versionNumber: versionCounter,
        changedAt: entry.timestamp,
        changedBy: entry.userId,
        changeDescription: description,
      }
      versionMap.set(versionCounter, version)
    })

    return Array.from(versionMap.values()).sort((a, b) => b.versionNumber - a.versionNumber)
  }, [rule, auditLog])

  const getActionBadge = (description: string) => {
    if (description.includes('created')) return 'version-created'
    if (description.includes('test') || description.includes('Test')) return 'version-tested'
    if (description.includes('Submitted')) return 'version-submitted'
    if (description.includes('Approved')) return 'version-approved'
    if (description.includes('Rejected')) return 'version-rejected'
    if (description.includes('Activated')) return 'version-activated'
    if (description.includes('modified')) return 'version-modified'
    return 'version-default'
  }

  return (
    <div className="rule-versioning">
      <div className="versioning-header">
        <h3>Version History</h3>
        <span className="version-count">{versions.length} versions</span>
      </div>

      <div className="timeline">
        {versions.map((version, index) => (
          <div key={version.versionNumber} className="timeline-item">
            <div className="timeline-marker">
              <div className="timeline-dot" />
              {index !== versions.length - 1 && <div className="timeline-line" />}
            </div>

            <div className="version-card">
              <div className="version-header">
                <div className="version-info">
                  <span className="version-number">
                    v{version.versionNumber}
                    {version.versionNumber === versions[0].versionNumber && (
                      <span className="current-badge">CURRENT</span>
                    )}
                  </span>
                  <span className={`version-badge ${getActionBadge(version.changeDescription)}`}>
                    {version.changeDescription}
                  </span>
                </div>
                {onRestoreVersion && version.versionNumber !== versions[0].versionNumber && (
                  <button
                    className="restore-btn"
                    onClick={() => onRestoreVersion(version.versionNumber)}
                    title="Restore this version"
                  >
                    ↻ Restore
                  </button>
                )}
              </div>

              <div className="version-details">
                <div className="detail-row">
                  <span className="detail-label">Changed:</span>
                  <span className="detail-value">
                    {new Date(version.changedAt).toLocaleString()}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Changed By:</span>
                  <span className="detail-value">{version.changedBy}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Status:</span>
                  <span className={`status-badge dq-status-badge status-${version.status}`}>
                    {version.status.toUpperCase()}
                  </span>
                </div>
              </div>

              <div className="version-diff">
                <div className="diff-section">
                  <span className="diff-label">Name:</span>
                  <span className="diff-value">{version.name}</span>
                </div>
                <div className="diff-section">
                  <span className="diff-label">Description:</span>
                  <span className="diff-value">{version.description}</span>
                </div>
                <div className="diff-section">
                  <span className="diff-label">Risk Level:</span>
                  <span className={`risk-badge risk-${version.riskLevel}`}>
                    {version.riskLevel.toUpperCase()}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {versions.length === 0 && (
        <div className="empty-versions">
          <p>No version history available</p>
        </div>
      )}
    </div>
  )
}
