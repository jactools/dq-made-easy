/**
 * ExecutionMetricsPanel - Display execution metrics from rule runs
 *
 * Shows match count, match rate, mismatch count, and other derived metrics
 * in a clear, scannable card format.
 */

import React from 'react';
import { JoinConsistencyExecutionMetrics } from '../types/execution';
import { AppIcon } from './app-primitives';
import './ExecutionMetricsPanel.css';

interface ExecutionMetricsPanelProps {
  metrics: JoinConsistencyExecutionMetrics;
  passed: boolean;
}

export const ExecutionMetricsPanel: React.FC<ExecutionMetricsPanelProps> = ({
  metrics,
  passed,
}) => {
  const getMatchRateColor = (rate: number): string => {
    if (rate >= 95) return 'metrics-success';
    if (rate >= 80) return 'metrics-warning';
    return 'metrics-danger';
  };

  return (
    <div className="execution-metrics-panel">
      <h3 className="metrics-title">
        Execution Metrics <AppIcon name={passed ? 'check-circle' : 'close-circle'} />
      </h3>

      <div className="metrics-grid">
        {/* Match Rate - Primary KPI */}
        <div className={`metric-card primary ${getMatchRateColor(metrics.matchRate)}`}>
          <div className="metric-label">Match Rate</div>
          <div className="metric-value">{metrics.matchRate.toFixed(2)}%</div>
          <div className="metric-description">
            {metrics.matchCount} / {metrics.eligibleJoinedRows}
          </div>
        </div>

        {/* Matches Count */}
        <div className="metric-card">
          <div className="metric-label">Matches</div>
          <div className="metric-value metric-success">
            {metrics.matchCount}
          </div>
          <div className="metric-description">rows passed all checks</div>
        </div>

        {/* Mismatches Count */}
        <div className="metric-card">
          <div className="metric-label">Mismatches</div>
          <div className="metric-value metric-danger">
            {metrics.mismatchCount}
          </div>
          <div className="metric-description">rows failed checks</div>
        </div>

        {/* Eligible Rows */}
        <div className="metric-card">
          <div className="metric-label">Eligible Rows</div>
          <div className="metric-value">{metrics.eligibleJoinedRows}</div>
          <div className="metric-description">joined after null cleanup</div>
        </div>

        {/* Actuality Date Mismatches */}
        {metrics.actualityDateMismatchCount > 0 && (
          <div className="metric-card">
            <div className="metric-label">Actuality-Date Drift</div>
            <div className="metric-value metric-warning">
              {metrics.actualityDateMismatchCount}
            </div>
            <div className="metric-description">tolerance exceeded</div>
          </div>
        )}

        {/* Null/Missing Join Keys */}
        {metrics.nullOrMissingJoinKeyCount > 0 && (
          <div className="metric-card">
            <div className="metric-label">Excluded (Null Keys)</div>
            <div className="metric-value">{metrics.nullOrMissingJoinKeyCount}</div>
            <div className="metric-description">rows not eligible</div>
          </div>
        )}
      </div>
    </div>
  );
};
