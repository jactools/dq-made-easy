import React, { useMemo } from 'react'
import { Rule } from '../types/rules'
import { ExecutionMetricsPanel } from './ExecutionMetricsPanel'
import { ExecutionDiagnosticsPanel } from './ExecutionDiagnosticsPanel'
import './TestResultsVisualization.css'

interface TestResultsVisualizationProps {
  rule: Rule
  isExpanded?: boolean
}

export const TestResultsVisualization: React.FC<TestResultsVisualizationProps> = ({ rule, isExpanded = false }) => {
  const testResult = rule.testResults
  if (!testResult) {
    return (
      <div className="test-results-empty">
        <p>No test results yet. Run a test to see detailed analytics.</p>
      </div>
    )
  }

  const failureRate = testResult.recordsTestedCount > 0 
    ? ((testResult.failuresFound / testResult.recordsTestedCount) * 100).toFixed(2)
    : '0.00'

  const successRate = (100 - parseFloat(failureRate)).toFixed(2)

  // Calculate trend data (simulated - in production would come from historical data)
  const trendData = useMemo(() => {
    return [
      { date: '5d ago', coverage: testResult.coverage - 3, failures: testResult.failuresFound + 500 },
      { date: '4d ago', coverage: testResult.coverage - 2, failures: testResult.failuresFound + 300 },
      { date: '3d ago', coverage: testResult.coverage - 1, failures: testResult.failuresFound + 150 },
      { date: '2d ago', coverage: testResult.coverage, failures: testResult.failuresFound + 75 },
      { date: 'Today', coverage: testResult.coverage, failures: testResult.failuresFound },
    ]
  }, [testResult])

  return (
    <div className="test-results-visualization">
      <div className="results-header">
        <h3>Test Results Analytics</h3>
        <span className={`test-status status-${testResult.status}`}>
          {testResult.status.toUpperCase()}
        </span>
      </div>

      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-label">DQ Score</div>
          <div className="metric-value">{testResult.coverage}%</div>
          <div className="metric-bar">
            <div 
              className="metric-bar-fill coverage-fill" 
              style={{ width: `${testResult.coverage}%` }}
            />
          </div>
          <div className="metric-note">of data tested</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Success Rate</div>
          <div className="metric-value">{successRate}%</div>
          <div className="metric-bar">
            <div 
              className="metric-bar-fill success-fill" 
              style={{ width: `${successRate}%` }}
            />
          </div>
          <div className="metric-note">records passing</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Records Tested</div>
          <div className="metric-value">{(testResult.recordsTestedCount / 1000).toFixed(1)}K</div>
          <div className="metric-bar">
            <div className="metric-bar-fill tested-fill" style={{ width: '100%' }} />
          </div>
          <div className="metric-note">{testResult.recordsTestedCount.toLocaleString()} total</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Failures Found</div>
          <div className="metric-value" style={{ color: failureRate !== '0.00' ? 'var(--app-status-error-text)' : 'var(--app-status-success-text)' }}>
            {testResult.failuresFound.toLocaleString()}
          </div>
          <div className="metric-bar">
            <div 
              className="metric-bar-fill failure-fill" 
              style={{ width: `${parseFloat(failureRate)}%` }}
            />
          </div>
          <div className="metric-note">{failureRate}% failure rate</div>
        </div>
      </div>

      <div className="details-grid">
        <div className="detail-box">
          <h4>Record Summary</h4>
          <div className="summary-stats">
            <div className="summary-row">
              <span>Total Tested</span>
              <span className="value">{testResult.recordsTestedCount.toLocaleString()}</span>
            </div>
            <div className="summary-row">
              <span>Passed</span>
              <span className="value passed">
                {(testResult.recordsTestedCount - testResult.failuresFound).toLocaleString()}
              </span>
            </div>
            <div className="summary-row">
              <span>Failed</span>
              <span className="value failed">
                {testResult.failuresFound.toLocaleString()}
              </span>
            </div>
          </div>
        </div>

        <div className="detail-box">
          <h4>Quality Score</h4>
          <div className="quality-circle">
            <svg viewBox="0 0 100 100" width="120" height="120">
              <circle cx="50" cy="50" r="45" fill="none" stroke="var(--app-border-subtle)" strokeWidth="8" />
              <circle
                cx="50"
                cy="50"
                r="45"
                fill="none"
                stroke={parseFloat(successRate) >= 90 ? 'var(--app-status-success-text)' : parseFloat(successRate) >= 75 ? 'var(--app-status-warning-text)' : 'var(--app-status-error-text)'}
                strokeWidth="8"
                strokeDasharray={`${(parseFloat(successRate) / 100) * (Math.PI * 90)} ${Math.PI * 90}`}
                strokeLinecap="round"
              />
              <text x="50" y="55" textAnchor="middle" fontSize="20" fontWeight="bold" fill="currentColor">
                {successRate}%
              </text>
            </svg>
          </div>
          <p className="quality-label">
            {parseFloat(successRate) >= 90 ? 'Excellent' : parseFloat(successRate) >= 75 ? 'Good' : 'Fair'}
          </p>
        </div>
      </div>

      {testResult.metrics && (
        <ExecutionMetricsPanel
          metrics={testResult.metrics}
          passed={testResult.status === 'passed'}
        />
      )}

      {testResult.diagnostics && testResult.diagnostics.length > 0 && (
        <ExecutionDiagnosticsPanel diagnostics={testResult.diagnostics} />
      )}

      {isExpanded && (
        <div className="trend-section">
          <h4>DQ Score Trend (Last 5 Days)</h4>
          <div className="trend-chart">
            <svg viewBox="0 0 500 200" width="100%" height="200">
              {/* Grid lines */}
              {[0, 25, 50, 75, 100].map((val) => (
                <line
                  key={`grid-${val}`}
                  x1="40"
                  y1={200 - (val / 100) * 160 - 20}
                  x2="490"
                  y2={200 - (val / 100) * 160 - 20}
                  stroke="var(--app-border-subtle)"
                  strokeWidth="1"
                  strokeDasharray="2,2"
                />
              ))}

              {/* DQ Score line */}
              <polyline
                points={trendData.map((d, i) => `${40 + (i * 90)},${200 - (d.coverage / 100) * 160 - 20}`).join(' ')}
                fill="none"
                stroke="var(--app-brand-primary)"
                strokeWidth="2"
              />

              {/* Data points */}
              {trendData.map((d, i) => (
                <circle
                  key={`point-${i}`}
                  cx={40 + i * 90}
                  cy={200 - (d.coverage / 100) * 160 - 20}
                  r="4"
                  fill="var(--app-brand-primary)"
                />
              ))}

              {/* Y-axis labels */}
              {[0, 25, 50, 75, 100].map((val) => (
                <text
                  key={`y-label-${val}`}
                  x="25"
                  y={200 - (val / 100) * 160 - 20 + 4}
                  textAnchor="end"
                  fontSize="11"
                  fill="var(--app-text-secondary)"
                >
                  {val}%
                </text>
              ))}

              {/* X-axis labels */}
              {trendData.map((d, i) => (
                <text
                  key={`x-label-${i}`}
                  x={40 + i * 90}
                  y="190"
                  textAnchor="middle"
                  fontSize="11"
                  fill="var(--app-text-secondary)"
                >
                  {d.date}
                </text>
              ))}
            </svg>
          </div>
        </div>
      )}

      <div className="test-timestamp">
        <small>
          Last tested: {new Date(testResult.testDate).toLocaleString()}
        </small>
      </div>
    </div>
  )
}
