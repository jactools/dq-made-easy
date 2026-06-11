import React from 'react'
import { RuleRollback, RuleVersion } from '../types/rules'
import './RollbackHistory.css'

interface RollbackHistoryProps {
  rollbacks: RuleRollback[]
  versions: RuleVersion[]
}

export const RollbackHistory: React.FC<RollbackHistoryProps> = ({
  rollbacks,
  versions,
}) => {
  if (rollbacks.length === 0) {
    return null
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

  return (
    <div className="rollback-history-section">
      <h4>Rollback History</h4>
      <div className="rollback-list">
        {rollbacks.map(rollback => (
          <div key={rollback.id} className="rollback-item">
            <div className="rollback-icon">⏪</div>
            <div className="rollback-details">
              <p className="rollback-action">
                Rolled back from <strong>v{versions.find(v => v.id === rollback.fromVersionId)?.versionNumber}</strong> to{' '}
                <strong>v{versions.find(v => v.id === rollback.toVersionId)?.versionNumber}</strong>
              </p>
              <p className="rollback-meta">
                {formatDate(rollback.rolledBackAt)} by {rollback.rolledBackBy}
              </p>
              {rollback.reason && (
                <p className="rollback-reason">Reason: {rollback.reason}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
