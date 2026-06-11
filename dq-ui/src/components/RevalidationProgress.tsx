import React, { useState, useEffect } from 'react'
import { AppIcon } from './app-primitives'
import './RevalidationProgress.css'

export interface RevalidationProgressProps {
  jobId: string
  isOpen: boolean
  ruleCount: number
  triggeredByTerm?: string
  onClose: () => void
  onGetStatus: (jobId: string) => Promise<any>
}

/**
 * Component to display batch revalidation progress
 *
 * Shows:
 * - Overall progress percentage
 * - Number of rules completed/failed
 * - Validation improvement metrics
 * - Real-time status updates
 *
 * Usage:
 * <RevalidationProgress
 *   jobId="job-123"
 *   isOpen={showProgress}
 *   ruleCount={25}
 *   onGetStatus={getJobStatus}
 *   onClose={handleClose}
 * />
 */
export const RevalidationProgress: React.FC<RevalidationProgressProps> = ({
  jobId,
  isOpen,
  ruleCount,
  triggeredByTerm,
  onClose,
  onGetStatus,
}) => {
  const [status, setStatus] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Poll for status updates
  useEffect(() => {
    if (!isOpen || !jobId) return

    const pollStatus = async () => {
      try {
        setLoading(true)
        const jobStatus = await onGetStatus(jobId)
        setStatus(jobStatus)
        setError(null)

        // Stop polling if job is completed
        if (jobStatus.status === 'completed' || jobStatus.status === 'failed') {
          setLoading(false)
        }
      } catch (err: any) {
        setError(err.message || 'Failed to get job status')
        console.error('Error polling job status:', err)
      } finally {
        setLoading(false)
      }
    }

    pollStatus()

    // Poll every 1 second if job is still running
    const interval = setInterval(pollStatus, 1000)
    return () => clearInterval(interval)
  }, [isOpen, jobId, onGetStatus])

  if (!isOpen || !status) {
    return null
  }

  const progressPercent = parseInt(status.progress.replace('%', '')) || 0
  const isComplete = status.status === 'completed'
  const isFailed = status.status === 'failed'

  return (
    <div className="revalidation-progress-overlay" onClick={onClose}>
      <div className="revalidation-progress-dialog" onClick={e => e.stopPropagation()}>
        <div className="progress-header">
          <h3>Batch Revalidation in Progress</h3>
          {isComplete && <span className="status-badge dq-status-badge completed">✓ Completed</span>}
          {isFailed && <span className="status-badge dq-status-badge failed">✗ Failed</span>}
          {!isComplete && !isFailed && <span className="status-badge dq-status-badge in-progress">⟳ Running</span>}
        </div>

        <div className="progress-content">
          {triggeredByTerm && (
            <div className="triggered-by">
              <span className="label">Triggered by catalog change:</span>
              <strong>{triggeredByTerm}</strong>
            </div>
          )}

          {/* Progress bar */}
          <div className="progress-section">
            <div className="progress-label">
              <span>Overall Progress</span>
              <span className="progress-percent">{progressPercent}%</span>
            </div>
            <div className="progress-bar-container">
              <div className="progress-bar" style={{ width: `${progressPercent}%` }}></div>
            </div>
          </div>

          {/* Statistics */}
          <div className="progress-stats">
            <div className="stat-box">
              <div className="stat-label">Queued</div>
              <div className="stat-value">{status.queued || ruleCount}</div>
            </div>

            <div className="stat-box">
              <div className="stat-label">Completed</div>
              <div className="stat-value completed">{status.completed}</div>
            </div>

            <div className="stat-box">
              <div className="stat-label">Failed</div>
              <div className="stat-value" style={{ color: status.failed > 0 ? '#d32f2f' : '#4caf50' }}>
                {status.failed}
              </div>
            </div>

            {status.duration_seconds && (
              <div className="stat-box">
                <div className="stat-label">Duration</div>
                <div className="stat-value">{Math.round(status.duration_seconds)}s</div>
              </div>
            )}
          </div>

          {/* Validation changes summary */}
          {isComplete && (
            <div className="validation-summary">
              <div className="summary-title">Validation Results</div>

              <div className="summary-metrics">
                {status.validation_improved > 0 && (
                  <div className="metric improved">
                    <AppIcon name="check-circle" />
                    <span>{status.validation_improved} rule{status.validation_improved !== 1 ? 's' : ''} improved</span>
                  </div>
                )}

                {status.validation_degraded > 0 && (
                  <div className="metric degraded">
                    <AppIcon name="exclamation-circle" />
                    <span>{status.validation_degraded} rule{status.validation_degraded !== 1 ? 's' : ''} degraded</span>
                  </div>
                )}

                {status.validation_unchanged > 0 && (
                  <div className="metric unchanged">
                    <AppIcon name="dash-circle-fill" />
                    <span>{status.validation_unchanged} rule{status.validation_unchanged !== 1 ? 's' : ''} unchanged</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {error && (
            <div className="error-message">
              <AppIcon name="exclamation-triangle" />
              <span>{error}</span>
            </div>
          )}

          {/* Loading indicator */}
          {loading && !isComplete && (
            <div className="loading-indicator">
              <AppIcon name="arrow-circle-repeat" style={{ animation: 'spin 1s linear infinite' }} />
              <span>Fetching latest status...</span>
            </div>
          )}

          {/* Results if completed */}
          {isComplete && status.results && status.results.length > 0 && (
            <div className="results-summary">
              <div className="results-title">Top Changes</div>
              <div className="results-list">
                {status.results.slice(0, 3).map((result: any, idx: number) => (
                  <div key={idx} className={`result-item result-${result.status}`}>
                    <div className="result-name">{result.ruleName}</div>
                    {result.validation_changed && (
                      <div className="result-status">
                        {result.was_valid && !result.now_valid && (
                          <span className="degraded">Now invalid</span>
                        )}
                        {!result.was_valid && result.now_valid && (
                          <span className="improved">Now valid</span>
                        )}
                        {result.new_issues?.length > 0 && (
                          <span className="new-issues">{result.new_issues.length} new issue{result.new_issues.length !== 1 ? 's' : ''}</span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="progress-footer">
          <button className="close-button" onClick={onClose} disabled={!isComplete && !isFailed}>
            {isComplete || isFailed ? 'Close' : 'Running...'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default RevalidationProgress
