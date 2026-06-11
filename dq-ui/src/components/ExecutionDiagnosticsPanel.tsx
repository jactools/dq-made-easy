/**
 * ExecutionDiagnosticsPanel - Display failure diagnostics from rule execution
 *
 * Shows aggregated failures classified by type (value mismatch, actuality-date drift, etc)
 * with sample failures from each class for user inspection and RCA.
 */

import React, { useState } from 'react';
import { DiagnosticsSummary, FailureDiagnostic } from '../types/execution';
import './ExecutionDiagnosticsPanel.css';

interface ExecutionDiagnosticsPanelProps {
  diagnostics: DiagnosticsSummary[];
}

const getFailureClassLabel = (failureClass: string): string => {
  const labels: Record<string, string> = {
    value_mismatch: 'Value Mismatch',
    actuality_date_drift: 'Actuality-Date Drift',
    null_or_missing_join_key: 'Null/Missing Join Key',
    other: 'Other',
  };
  return labels[failureClass] || failureClass;
};

const getFailureClassIcon = (failureClass: string): string => {
  const icons: Record<string, string> = {
    value_mismatch: '≠',
    actuality_date_drift: '⏱',
    null_or_missing_join_key: '∅',
    other: '?',
  };
  return icons[failureClass] || '•';
};

const DiagnosticsSummaryItem: React.FC<{
  summary: DiagnosticsSummary;
}> = ({ summary }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="diagnostics-summary-item">
      <button
        className="diagnostics-header"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span className={`failure-icon failure-${summary.failureClass}`}>
          {getFailureClassIcon(summary.failureClass)}
        </span>
        <span className="failure-label">
          {getFailureClassLabel(summary.failureClass)}
        </span>
        <span className="failure-count">{summary.count} instance(s)</span>
        <span className={`expand-icon ${expanded ? 'expanded' : ''}`}>
          ▼
        </span>
      </button>

      {expanded && summary.sampleFailures.length > 0 && (
        <div className="diagnostics-samples">
          <div className="samples-label">
            Sample failures (up to {summary.maxSampleSize}):
          </div>
          <ul className="samples-list">
            {summary.sampleFailures.map((failure: FailureDiagnostic, idx: number) => (
              <li key={idx} className="sample-item">
                <div className="sample-details">
                  {failure.details && (
                    <div className="sample-description">{failure.details}</div>
                  )}
                  {failure.rowIdentifier && (
                    <div className="sample-row-id">Row: {failure.rowIdentifier}</div>
                  )}
                  {failure.affectedAttributes && failure.affectedAttributes.length > 0 && (
                    <div className="sample-attributes">
                      Attributes: {failure.affectedAttributes.join(', ')}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export const ExecutionDiagnosticsPanel: React.FC<ExecutionDiagnosticsPanelProps> = ({
  diagnostics,
}) => {
  if (!diagnostics || diagnostics.length === 0) {
    return (
      <div className="execution-diagnostics-panel">
        <h3 className="diagnostics-title">Execution Diagnostics</h3>
        <div className="no-failures">
          <div className="success-icon">✓</div>
          <p>No failures detected</p>
        </div>
      </div>
    );
  }

  const totalFailures = diagnostics.reduce((sum, d) => sum + d.count, 0);

  return (
    <div className="execution-diagnostics-panel">
      <h3 className="diagnostics-title">
        Execution Diagnostics ({totalFailures} failures)
      </h3>

      <div className="diagnostics-list">
        {diagnostics.map((summary) => (
          <DiagnosticsSummaryItem
            key={summary.failureClass}
            summary={summary}
          />
        ))}
      </div>
    </div>
  );
};
