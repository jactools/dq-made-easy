import React from 'react'

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const formatJson = (value: unknown): string => JSON.stringify(value, null, 2)

const formatValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return 'n/a'
  }
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return formatJson(value)
}

interface SparkExpectationsMetricsPanelProps {
  resultSummary: unknown
}

export const SparkExpectationsMetricsPanel: React.FC<SparkExpectationsMetricsPanelProps> = ({ resultSummary }) => {
  if (!isRecord(resultSummary)) {
    return null
  }

  const observabilitySummary = isRecord(resultSummary.observability_summary) ? resultSummary.observability_summary : null
  const failureMetrics = isRecord(resultSummary.failure_metrics) ? resultSummary.failure_metrics : null
  const failedCheck = isRecord(resultSummary.failed_check) ? resultSummary.failed_check : null
  const trace = isRecord(resultSummary.trace) ? resultSummary.trace : null
  const engineType = String(observabilitySummary?.engine_type || resultSummary.engine_type || '').trim().toLowerCase()

  if (engineType !== 'spark_expectations' && !failureMetrics && !failedCheck && !trace) {
    return null
  }

  const result = String(observabilitySummary?.result || resultSummary.result || 'unknown')
  const passedCount = Number(observabilitySummary?.passed_count ?? resultSummary.passed_count ?? 0)
  const failedCount = Number(observabilitySummary?.failed_count ?? resultSummary.failed_count ?? 0)

  return (
    <div className="gx-monitor-materialization">
      <h5>Spark Expectations metrics</h5>
      <dl className="gx-monitor-dl gx-monitor-dl-compact">
        <div>
          <dt>Engine</dt>
          <dd>{engineType || 'spark_expectations'}</dd>
        </div>
        <div>
          <dt>Result</dt>
          <dd>{result}</dd>
        </div>
        <div>
          <dt>Passed / failed</dt>
          <dd>{`${passedCount} / ${failedCount}`}</dd>
        </div>
        <div>
          <dt>Failure code</dt>
          <dd className="gx-monitor-mono">{String(resultSummary.failure_code || 'None')}</dd>
        </div>
        <div>
          <dt>Failure message</dt>
          <dd>{String(resultSummary.failure_message || 'None')}</dd>
        </div>
      </dl>

      {failedCheck ? (
        <div className="gx-monitor-materialization">
          <h6>Failed check</h6>
          <dl className="gx-monitor-dl gx-monitor-dl-compact">
            <div>
              <dt>Check</dt>
              <dd className="gx-monitor-mono">{String(failedCheck.check_name || failedCheck.rule_type || 'unknown')}</dd>
            </div>
            <div>
              <dt>Reason</dt>
              <dd>{String(failedCheck.reason || 'n/a')}</dd>
            </div>
            <div>
              <dt>Failure stage</dt>
              <dd>{String(failedCheck.failure_stage || 'n/a')}</dd>
            </div>
          </dl>
        </div>
      ) : null}

      {failureMetrics ? (
        <div className="gx-monitor-materialization">
          <h6>Failure metrics</h6>
          <pre className="gx-monitor-json">{formatJson(failureMetrics)}</pre>
        </div>
      ) : null}

      {trace ? (
        <div className="gx-monitor-materialization">
          <h6>Trace</h6>
          <dl className="gx-monitor-dl gx-monitor-dl-compact">
            <div>
              <dt>Exception type</dt>
              <dd className="gx-monitor-mono">{formatValue(trace.exception_type)}</dd>
            </div>
            <div>
              <dt>Message</dt>
              <dd>{formatValue(trace.message)}</dd>
            </div>
          </dl>
          <pre className="gx-monitor-json">{formatJson(trace)}</pre>
        </div>
      ) : null}
    </div>
  )
}