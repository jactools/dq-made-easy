import { describe, expect, it } from 'vitest'
import {
  getValidationBadgeMeta,
  resolveRuleAttributeDisplayName,
  resolveRuleThresholdBadgeContent,
  resolveRuleThresholdDisplayValue,
  shouldShowDeactivationRequestedBadge,
} from './RuleCard'

describe('shouldShowDeactivationRequestedBadge', () => {
  it('shows the badge when a deactivation request is pending and the rule is activated', () => {
    expect(shouldShowDeactivationRequestedBadge('activated', true)).toBe(true)
  })

  it('still shows the badge when a pending deactivation reloads as pending-approval', () => {
    expect(shouldShowDeactivationRequestedBadge('pending-approval', true)).toBe(true)
  })

  it('does not show the badge without a pending deactivation request', () => {
    expect(shouldShowDeactivationRequestedBadge('activated', false)).toBe(false)
  })
})

describe('getValidationBadgeMeta', () => {
  it('adds a compact validation date when one is available', () => {
    expect(getValidationBadgeMeta('valid', '2026-04-27T12:00:00Z')).toEqual({
      label: 'Validated Apr 27',
      title: 'Validated successfully on Apr 27',
    })
  })

  it('falls back to a status-only label when no validation date exists', () => {
    expect(getValidationBadgeMeta('invalid', null)).toEqual({
      label: 'Invalid',
      title: 'Validation failed',
    })
  })
})

describe('resolveRuleAttributeDisplayName', () => {
  it('prefers the resolved attribute name and never returns the raw id', () => {
    expect(
      resolveRuleAttributeDisplayName(
        {
          'attr-34': {
            id: 'attr-34',
            name: 'fee_amount',
            dataObjectName: 'Transaction',
            datasetName: 'Payments',
          },
        },
        'attr-34',
      ),
    ).toBe('Payments / Transaction – fee_amount')
  })

  it('uses an explicit unresolved label when the catalog entry is missing', () => {
    expect(resolveRuleAttributeDisplayName({}, 'attr-34')).toBe('Unresolved attribute')
  })
})

describe('resolveRuleThresholdDisplayValue', () => {
  it('shows app default with an application-default tooltip when the rule threshold is not explicit', () => {
    expect(
      resolveRuleThresholdBadgeContent(
        {
          id: '41',
          workspace: 'retail-banking',
          name: 'missing-default-threshold',
          description: 'Uses the application default threshold.',
          status: 'approved',
          createdAt: '2026-04-20T09:00:00Z',
          attributes: [],
          riskLevel: 'medium',
          checkType: 'THRESHOLD',
          checkTypeParams: {
            checkType: 'THRESHOLD',
            attribute: 'customer_name',
            metric: 'null_pct',
            operator: 'gte',
          },
        } as any,
        95,
      ),
    ).toEqual({
      label: 'app default',
      title: 'Rule threshold uses app default: 95%',
    })
  })

  it('uses the DSL threshold for quantile rules when the top-level rule is missing checkTypeParams', () => {
    expect(
      resolveRuleThresholdDisplayValue(
        {
          id: '36',
          workspace: 'retail-banking',
          name: 'transaction-fee-quantile-95',
          description: '95th percentile of transaction fee must stay under 50000',
          status: 'approved',
          createdAt: '2026-04-20T09:00:00Z',
          attributes: [],
          riskLevel: 'medium',
          dsl: {
            schemaVersion: '1',
            source: {
              kind: 'check_type',
              checkType: 'THRESHOLD',
              checkTypeParams: {
                checkType: 'THRESHOLD',
                attribute: 'fee_amount',
                metric: 'quantile',
                operator: 'lte',
                threshold: 50000,
                quantile: 0.95,
              },
            },
          },
        } as any,
        0,
      ),
    ).toBe('50000 (quantile 95%)')
  })

  it('renders raw aggregate metric thresholds without a percentage suffix', () => {
    expect(
      resolveRuleThresholdDisplayValue(
        {
          id: '38',
          workspace: 'retail-banking',
          name: 'average-transaction-amount',
          description: 'Average transaction amount must stay below the limit.',
          status: 'approved',
          createdAt: '2026-04-20T09:00:00Z',
          attributes: [],
          riskLevel: 'medium',
          checkType: 'THRESHOLD',
          checkTypeParams: {
            checkType: 'THRESHOLD',
            attribute: 'amount',
            metric: 'avg',
            operator: 'lte',
            threshold: 250.5,
          },
        } as any,
        0,
      ),
    ).toBe('250.5')
  })

  it.each([
    ['missing_count', '0 missing rows'],
    ['duplicate_count', '0 duplicate rows'],
    ['duplicate_percent', '0% duplicate rate'],
  ])('renders %s thresholds with zero-only labels', (metric, expected) => {
    expect(
      resolveRuleThresholdDisplayValue(
        {
          id: '40',
          workspace: 'retail-banking',
          name: `${metric}-threshold`,
          description: `Zero-only threshold for ${metric}`,
          status: 'approved',
          createdAt: '2026-04-20T09:00:00Z',
          attributes: [],
          riskLevel: 'medium',
          checkType: 'THRESHOLD',
          checkTypeParams: {
            checkType: 'THRESHOLD',
            attribute: 'customer_id',
            metric,
            operator: 'lte',
            threshold: 0,
          },
        } as any,
        0,
      ),
    ).toBe(expected)
  })

  it('renders distinct count thresholds as counts', () => {
    expect(
      resolveRuleThresholdDisplayValue(
        {
          id: '39',
          workspace: 'retail-banking',
          name: 'distinct-customer-types',
          description: 'Distinct customer type count must stay above the minimum.',
          status: 'approved',
          createdAt: '2026-04-20T09:00:00Z',
          attributes: [],
          riskLevel: 'medium',
          checkType: 'THRESHOLD',
          checkTypeParams: {
            checkType: 'THRESHOLD',
            attribute: 'customer_type',
            metric: 'distinct_count',
            operator: 'gte',
            threshold: 12,
          },
        } as any,
        0,
      ),
    ).toBe('12 distinct values')
  })

  it('renders direct row count thresholds as row counts', () => {
    expect(
      resolveRuleThresholdDisplayValue(
        {
          id: '37',
          workspace: 'retail-banking',
          name: 'row-count-check',
          description: 'Dataset row count should stay above the minimum.',
          status: 'approved',
          createdAt: '2026-04-20T09:00:00Z',
          attributes: [],
          riskLevel: 'medium',
          checkType: 'ROW_COUNT',
          checkTypeParams: {
            checkType: 'ROW_COUNT',
            operator: 'gte',
            threshold: 250,
          },
        } as any,
        0,
      ),
    ).toBe('>= 250 rows')
  })
})
