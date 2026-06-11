import React from 'react'
import { ThresholdParams, ThresholdMetric, ComparisonOperator } from '../../types/rules'
import { useSettings } from '../../hooks/useContexts'
import { AppSelect } from '../app-primitives'
import { CheckTypeFieldErrors } from './checkTypeValidation'

interface ThresholdFormProps {
  params: Partial<ThresholdParams>
  onChange: (params: ThresholdParams) => void
  fieldErrors?: CheckTypeFieldErrors
  catalogAttributeName?: string
}

const METRICS: { value: ThresholdMetric; label: string }[] = [
  { value: 'null_pct',         label: 'NULL values (%)'     },
  { value: 'empty_pct',        label: 'Empty strings (%)'   },
  { value: 'default_val_pct',  label: 'Default / placeholder (%)'  },
  { value: 'missing_count',    label: 'Missing rows'        },
  { value: 'duplicate_count',  label: 'Duplicate rows'      },
  { value: 'duplicate_percent', label: 'Duplicate rate'     },
  { value: 'quantile',         label: 'Quantile'            },
  { value: 'min',              label: 'Minimum'             },
  { value: 'max',              label: 'Maximum'             },
  { value: 'avg',              label: 'Average'             },
  { value: 'sum',              label: 'Sum'                 },
  { value: 'stddev',           label: 'Standard deviation'  },
  { value: 'distinct_count',    label: 'Distinct count'      },
]

const COMPLETENESS_METRICS = new Set<ThresholdMetric>(['null_pct', 'empty_pct', 'default_val_pct'])
const MISSING_COUNT_METRICS = new Set<ThresholdMetric>(['missing_count'])
const DUPLICATE_COUNT_METRICS = new Set<ThresholdMetric>(['duplicate_count'])
const DUPLICATE_PERCENT_METRICS = new Set<ThresholdMetric>(['duplicate_percent'])
const DISTINCT_COUNT_METRICS = new Set<ThresholdMetric>(['distinct_count'])
const ZERO_ONLY_METRICS = new Set<ThresholdMetric>(['missing_count', 'duplicate_count', 'duplicate_percent'])

const QUANTILE_OPERATORS: { value: ComparisonOperator; label: string }[] = [
  { value: 'gte', label: 'greater than or equal (≥)'  },
  { value: 'lte', label: 'less than or equal (≤)'     },
]

const OPERATORS: { value: ComparisonOperator; label: string }[] = [
  { value: 'gt',  label: 'greater than (>)'           },
  { value: 'gte', label: 'greater than or equal (≥)'  },
  { value: 'lt',  label: 'less than (<)'              },
  { value: 'lte', label: 'less than or equal (≤)'     },
]

export const ThresholdForm: React.FC<ThresholdFormProps> = ({ params, onChange, fieldErrors, catalogAttributeName }) => {
  const settings = useSettings()
  const fallbackThreshold = Number(settings.applicationSettings?.defaultRuleThresholdPct ?? 0)
  const selectedMetric = params.metric ?? 'null_pct'
  const selectedMetricIsQuantile = selectedMetric === 'quantile'
  const selectedMetricIsCompleteness = COMPLETENESS_METRICS.has(selectedMetric)
  const selectedMetricIsMissingCount = MISSING_COUNT_METRICS.has(selectedMetric)
  const selectedMetricIsDuplicateCount = DUPLICATE_COUNT_METRICS.has(selectedMetric)
  const selectedMetricIsDuplicatePercent = DUPLICATE_PERCENT_METRICS.has(selectedMetric)
  const selectedMetricIsZeroOnly = ZERO_ONLY_METRICS.has(selectedMetric)
  const selectedMetricIsDistinctCount = DISTINCT_COUNT_METRICS.has(selectedMetric)
  const selectedOperatorOptions = selectedMetricIsQuantile
    ? QUANTILE_OPERATORS
    : selectedMetricIsZeroOnly
      ? [{ value: 'lte' as ComparisonOperator, label: 'less than or equal (≤)' }]
      : OPERATORS
  const selectedOperator = selectedMetricIsZeroOnly
    ? 'lte'
    : params.operator ?? (selectedMetricIsQuantile ? 'lte' : 'gt')
  const selectedThresholdLabel = selectedMetricIsQuantile
    ? 'Comparison value'
    : selectedMetricIsCompleteness
      ? 'Threshold (%)'
      : selectedMetricIsMissingCount || selectedMetricIsDuplicateCount
        ? 'Threshold (count)'
        : selectedMetricIsDuplicatePercent
          ? 'Threshold (%)'
          : selectedMetricIsDistinctCount
            ? 'Threshold (count)'
            : 'Threshold (value)'
  const selectedThresholdHint = selectedMetricIsQuantile
    ? 'GX compares the selected quantile against this value.'
    : selectedMetricIsCompleteness
      ? 'Percentage of rows allowed to fail this metric.'
      : selectedMetricIsMissingCount
        ? 'GX compares missing rows against this value. The current runtime only supports 0.'
        : selectedMetricIsDuplicateCount
          ? 'GX compares duplicate rows against this value. The current runtime only supports 0.'
          : selectedMetricIsDuplicatePercent
            ? 'GX compares the duplicate rate against this value. The current runtime only supports 0%.'
            : selectedMetricIsDistinctCount
              ? 'GX compares the distinct value count against this number.'
              : 'GX compares the selected aggregate against this value.'
  const selectedThresholdDefault = selectedMetricIsCompleteness
    || selectedMetricIsQuantile
    ? fallbackThreshold
    : selectedMetricIsZeroOnly
      ? 0
      : selectedMetricIsDistinctCount
      ? 1
      : 0
  const selectedThresholdValue = selectedMetricIsZeroOnly
    ? (params.threshold ?? selectedThresholdDefault)
    : (params.threshold ?? '')

  const nextThresholdValueForMetric = (metric: ThresholdMetric, patch: Partial<ThresholdParams>): number => {
    if (patch.threshold !== undefined) {
      return patch.threshold
    }

    if (metric !== selectedMetric) {
      if (ZERO_ONLY_METRICS.has(metric)) {
        return 0
      }
      if (COMPLETENESS_METRICS.has(metric) || metric === 'quantile') {
        return fallbackThreshold
      }
      if (DISTINCT_COUNT_METRICS.has(metric)) {
        return 1
      }
      return 0
    }

    if (params.threshold !== undefined) {
      return params.threshold
    }

    return selectedThresholdDefault
  }

  const emit = (patch: Partial<ThresholdParams>) => {
    const nextMetric = patch.metric ?? selectedMetric
    const nextOperator = ZERO_ONLY_METRICS.has(nextMetric)
      ? 'lte'
      : patch.operator ?? (nextMetric === 'quantile' ? 'lte' : (patch.metric && patch.metric !== selectedMetric ? 'gt' : selectedOperator))
    const nextParams: ThresholdParams = {
      checkType: 'THRESHOLD',
      attribute: catalogAttributeName ?? params.attribute ?? '',
      metric: nextMetric,
      operator: nextOperator,
      threshold: nextThresholdValueForMetric(nextMetric, patch),
    }
    if (nextMetric === 'quantile') {
      nextParams.quantile = patch.quantile ?? params.quantile ?? 0.95
    }
    onChange(nextParams)
  }

  return (
    <div className="check-type-form threshold-form">
      <div className="check-type-form-field">
        <AppSelect
          id="ct-metric"
          label="Metric"
          value={selectedMetric}
          onChange={(value) => emit({ metric: value as ThresholdMetric })}
          options={METRICS}
        />
      </div>

      <div className="check-type-form-row">
        <div className="check-type-form-field check-type-form-field--half">
          <AppSelect
            id="ct-operator"
            label="Condition"
            value={selectedOperator}
            disabled={selectedMetricIsZeroOnly}
            onChange={(value) => emit({ operator: value as ComparisonOperator })}
            options={selectedOperatorOptions}
          />
        </div>

        <div className="check-type-form-field check-type-form-field--half">
          <label className="check-type-form-label" htmlFor="ct-threshold">
            {selectedThresholdLabel}
          </label>
          <input
            id="ct-threshold"
            type="number"
            className="modal-input"
            min={selectedMetricIsCompleteness || selectedMetricIsDistinctCount || selectedMetricIsZeroOnly ? 0 : undefined}
            max={selectedMetricIsCompleteness ? 100 : selectedMetricIsZeroOnly ? 0 : undefined}
            step={selectedMetricIsDistinctCount || selectedMetricIsMissingCount || selectedMetricIsDuplicateCount ? 1 : selectedMetricIsDuplicatePercent ? 0.01 : 0.1}
            value={selectedThresholdValue}
            placeholder={`e.g. ${selectedThresholdDefault}`}
            onChange={(e) => emit({ threshold: parseFloat(e.target.value) || 0 })}
          />
          <span className="check-type-form-hint">
            {selectedThresholdHint}
          </span>
          {fieldErrors?.threshold && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.threshold}</span>
          )}
        </div>
      </div>

      {selectedMetric === 'quantile' && (
        <div className="check-type-form-field">
          <label className="check-type-form-label" htmlFor="ct-quantile">
            Quantile (0-1)
          </label>
          <input
            id="ct-quantile"
            type="number"
            className="modal-input"
            min={0}
            max={1}
            step={0.01}
            value={params.quantile ?? ''}
            placeholder="e.g. 0.95"
            onChange={(e) => emit({ quantile: e.target.value === '' ? undefined : parseFloat(e.target.value) })}
          />
          <span className="check-type-form-hint">
            Quantile target used by GX when evaluating the comparison value.
          </span>
          {fieldErrors?.quantile && (
            <span className="check-type-form-hint check-type-form-field-error">{fieldErrors.quantile}</span>
          )}
        </div>
      )}
    </div>
  )
}
