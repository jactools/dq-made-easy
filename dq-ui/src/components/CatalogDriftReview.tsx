import React, { useEffect, useState } from 'react'
import { useCatalogDrift, DriftSummary, RuleDriftInfo } from '../hooks/useCatalogDrift'
import { useBatchRevalidation } from '../hooks/useBatchRevalidation'
import { DriftAlert } from './DriftAlert'
import { RevalidationProgress } from './RevalidationProgress'
import { PrimaryButton } from './Button'
import { AppIcon } from './app-primitives'
import './AccessRequestsDashboard.css'

const isAliasLevelDrift = (driftType: string): boolean => String(driftType || '').trim().toLowerCase().startsWith('alias_')

export const CatalogDriftReview: React.FC = () => {
  const { checkRuleDrift, getDriftSummary, loading: driftLoading } = useCatalogDrift()
  const { startRevalidationJob, recordDriftReview, getJobStatus } = useBatchRevalidation()

  const [driftSummary, setDriftSummary] = useState<DriftSummary | null>(null)
  const [driftDetails, setDriftDetails] = useState<RuleDriftInfo[]>([])
  const [selectedDrift, setSelectedDrift] = useState<RuleDriftInfo | null>(null)
  const [revalidationJobId, setRevalidationJobId] = useState<string | null>(null)
  const [showRevalidationProgress, setShowRevalidationProgress] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  const aliasLevelCount = Object.entries(driftSummary?.byDriftType || {}).reduce(
    (count, [driftType, driftCount]) => (isAliasLevelDrift(driftType) ? count + Number(driftCount || 0) : count),
    0,
  )
  const attributeLevelCount = Object.entries(driftSummary?.byDriftType || {}).reduce(
    (count, [driftType, driftCount]) => (!isAliasLevelDrift(driftType) ? count + Number(driftCount || 0) : count),
    0,
  )

  useEffect(() => {
    const loadDriftSummary = async () => {
      setSummaryError(null)
      try {
        const summary = await getDriftSummary()
        setDriftSummary(summary)
        const affectedRulesWithVersions = (summary.affectedRules || []).filter(
          (rule) => Boolean(rule.ruleVersionId)
        )
        if (affectedRulesWithVersions.length > 0) {
          const details = await Promise.all(
            affectedRulesWithVersions.map((rule) =>
              checkRuleDrift(rule.ruleId, rule.ruleVersionId).catch(() => null)
            )
          )
          setDriftDetails(details.filter((detail): detail is RuleDriftInfo => detail !== null))
        } else {
          setDriftDetails([])
        }
      } catch (err) {
        console.error('Failed to load catalog drift summary:', err)
        setSummaryError(err instanceof Error ? err.message : 'Failed to load catalog drift summary')
      }
    }

    loadDriftSummary()
  }, [getDriftSummary, checkRuleDrift])

  const handleRevalidateAll = async () => {
    if (!driftSummary || driftSummary.affectedRules.length === 0) return

    try {
      await recordDriftReview(driftSummary.affectedRules)
      const ruleVersionIds = driftSummary.affectedRules.map((rule) => rule.ruleVersionId)
      const result = await startRevalidationJob(ruleVersionIds)
      setRevalidationJobId(result.jobId)
      setShowRevalidationProgress(true)
    } catch (err) {
      console.error('Failed to start batch revalidation:', err)
    }
  }

  const handleRevalidateRule = async (drift: RuleDriftInfo) => {
    try {
      await recordDriftReview([drift])
      const result = await startRevalidationJob([drift.ruleVersionId])
      setRevalidationJobId(result.jobId)
      setShowRevalidationProgress(true)
      setSelectedDrift(null)
    } catch (err) {
      console.error('Failed to start revalidation:', err)
    }
  }

  if (summaryError) {
    return (
      <div className="governance-dashboard-error">
        <div className="error-icon"><AppIcon name="warning" /></div>
        <h2>Unable to load Catalog Drift</h2>
        <p>{summaryError}</p>
      </div>
    )
  }

  if (driftSummary && (!driftSummary.byDriftType || typeof driftSummary.byDriftType !== 'object')) {
    return (
      <div className="governance-dashboard-error">
        <div className="error-icon"><AppIcon name="warning" /></div>
        <h2>Unable to load Catalog Drift</h2>
        <p>Unexpected drift summary payload: missing byDriftType.</p>
      </div>
    )
  }

  return (
    <div className="governance-dashboard catalog-drift-review">
      <div className="governance-header">
        <div className="governance-title">
          <h1>
            <AppIcon name="warning" />
            Catalog Drift
          </h1>
          <p className="governance-subtitle">
            Inspect affected rules, compare drifted fields, and run revalidation from the Rule Quality workspace.
          </p>
        </div>
      </div>

      <div className="governance-summary">
        <div className="summary-card summary-primary">
          <div className="card-icon"><AppIcon name="line-chart" /></div>
          <div className="card-content">
            <div className="card-label">Rules with Drift</div>
            <div className="card-value">{driftSummary?.rulesWithDrift || 0}</div>
            <div className="card-subtitle">of {driftSummary?.totalRulesChecked || 0} total rules</div>
          </div>
        </div>

        <div className="summary-card summary-warning">
          <div className="card-icon"><AppIcon name="warning" /></div>
          <div className="card-content">
            <div className="card-label">Total Drifts Detected</div>
            <div className="card-value">{driftSummary?.totalDriftsDetected || 0}</div>
            <div className="card-critical">{driftSummary?.criticalDrifts || 0} critical</div>
          </div>
        </div>

        <div className="summary-card summary-info">
          <div className="card-icon"><AppIcon name="info-circle" /></div>
          <div className="card-content">
            <div className="card-label">Drift Layers</div>
            <div className="card-value">{aliasLevelCount + attributeLevelCount}</div>
            <div className="card-subtitle">
              Business term {aliasLevelCount}, technical field {attributeLevelCount}
            </div>
          </div>
        </div>
      </div>

      {driftSummary && driftSummary.rulesWithDrift > 0 && (
        <div className="governance-actions">
          <div className="action-info">
            <span className="action-icon"><AppIcon name="arrow-circle-repeat" /></span>
            <span className="action-text">
              {driftSummary.rulesWithDrift} rule{driftSummary.rulesWithDrift > 1 ? 's' : ''} need revalidation
            </span>
          </div>
          <PrimaryButton onClick={handleRevalidateAll}>
            Revalidate All Affected Rules
          </PrimaryButton>
        </div>
      )}

      <div className="governance-content">
        <div className="governance-section">
          <h2 className="section-title">
            <AppIcon name="warning" />
            Affected Rules
          </h2>

          {driftDetails.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><AppIcon name="check-circle" /></div>
              <h3>No drift detected</h3>
              <p>All rules are aligned with the current catalog definitions.</p>
            </div>
          ) : (
            <div className="drift-list">
              {driftDetails.map((drift) => (
                <div
                  key={drift.ruleId}
                  className={`drift-item ${selectedDrift?.ruleId === drift.ruleId ? 'selected' : ''}`}
                  onClick={() => setSelectedDrift(selectedDrift?.ruleId === drift.ruleId ? null : drift)}
                >
                  <div className="drift-item-header">
                    <div className="drift-item-title">
                      <span className="drift-rule-name">{drift.ruleName}</span>
                      <span className="drift-version">v{drift.versionNumber}</span>
                    </div>
                    <div className="drift-item-badges">
                      {drift.drifts.some((item) => isAliasLevelDrift(item.driftType)) && (
                        <span className="badge badge-info">Business term drift</span>
                      )}
                      {drift.drifts.some((item) => !isAliasLevelDrift(item.driftType)) && (
                        <span className="badge badge-success">Technical field drift</span>
                      )}
                      {drift.drifts.some((item) => item.severity === 'critical') && (
                        <span className="badge badge-critical"><AppIcon name="warning" /> Critical</span>
                      )}
                      <span className="badge badge-count">
                        {drift.totalDrifts} issue{drift.totalDrifts > 1 ? 's' : ''}
                      </span>
                    </div>
                  </div>

                  {selectedDrift?.ruleId === drift.ruleId && (
                    <div className="drift-item-expanded">
                      <DriftAlert
                        ruleId={drift.ruleId}
                        ruleVersionId={drift.ruleVersionId}
                        affectedAliases={drift.affectedAliases}
                        drifts={drift.drifts}
                        needsRevalidation={drift.needsRevalidation}
                        onRevalidate={() => handleRevalidateRule(drift)}
                        onDismiss={() => setSelectedDrift(null)}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {driftSummary && Object.keys(driftSummary.byDriftType || {}).length > 0 && (
          <div className="governance-section">
            <h2 className="section-title">
              <AppIcon name="line-chart" />
              Drift Signal Breakdown
            </h2>
            <div className="drift-type-breakdown">
              {Object.entries(driftSummary.byDriftType || {}).map(([driftType, count]) => (
                <div key={driftType} className="drift-type-item">
                  <div className="drift-type-name">{driftType.replace(/_/g, ' ')}</div>
                  <div className="drift-type-bar">
                    <div
                      className="drift-type-bar-fill"
                      style={{
                        width: `${((count as number) / Math.max(...Object.values(driftSummary.byDriftType || { [driftType]: count as number }))) * 100}%`,
                      }}
                    />
                  </div>
                  <div className="drift-type-count">{count}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <RevalidationProgress
        isOpen={showRevalidationProgress}
        jobId={revalidationJobId || ''}
        ruleCount={driftSummary?.rulesWithDrift || 0}
        onClose={() => setShowRevalidationProgress(false)}
        onGetStatus={getJobStatus}
      />

      {driftLoading && (
        <div className="governance-loading">
          <div className="spinner" />
          <p>Loading catalog drift data...</p>
        </div>
      )}
    </div>
  )
}