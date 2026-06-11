import type { AppIconName } from '../components/app-primitives'

export type DAMADimension = 'completeness' | 'accuracy' | 'consistency' | 'timeliness' | 'validity' | 'uniqueness'

export interface RuleTemplate {
  id: string
  name: string
  description: string
  dimension: DAMADimension
  category: string
  defaultRiskLevel: 'low' | 'medium' | 'high'
  ruleType: 'threshold' | 'regex' | 'range' | 'custom'
  templateRuleDefinition: {
    name?: string
    description?: string
    attributes?: string[]
    expectedValues?: Record<string, any>
    threshold?: number
    operator?: string
  }
  exampleUse: string
  icon?: AppIconName
}

export const DAMA_TEMPLATES: RuleTemplate[] = [
  // COMPLETENESS
  {
    id: 'template-completeness-1',
    name: 'NULL Value Check',
    description: 'Detect rows with NULL/missing values in critical columns',
    dimension: 'completeness',
    category: 'Data Presence',
    defaultRiskLevel: 'high',
    ruleType: 'threshold',
    templateRuleDefinition: {
      description: 'Check for missing values',
      attributes: [],
      threshold: 95,
      operator: 'percentage_over',
    },
    exampleUse: 'Ensure customer email addresses are always populated',
    icon: 'warning',
  },
  {
    id: 'template-completeness-2',
    name: 'Empty String Check',
    description: 'Detect empty strings that should contain data',
    dimension: 'completeness',
    category: 'Data Presence',
    defaultRiskLevel: 'medium',
    ruleType: 'threshold',
    templateRuleDefinition: {
      description: 'Check for empty strings',
      attributes: [],
      threshold: 97,
      operator: 'percentage_over',
    },
    exampleUse: 'Validate product descriptions are not blank',
    icon: 'dash-circle-fill',
  },
  {
    id: 'template-completeness-3',
    name: 'Default Value Detection',
    description: 'Identify data defaults that may indicate incomplete data entry',
    dimension: 'completeness',
    category: 'Data Presence',
    defaultRiskLevel: 'low',
    ruleType: 'threshold',
    templateRuleDefinition: {
      description: 'Check for default/placeholder values',
      attributes: [],
      expectedValues: { placeholder: 'N/A' },
      threshold: 90,
      operator: 'percentage_over',
    },
    exampleUse: 'Detect when house addresses are left as "Unknown"',
    icon: 'database',
  },

  // ACCURACY
  {
    id: 'template-accuracy-1',
    name: 'Format Validation',
    description: 'Verify data matches expected format/pattern',
    dimension: 'accuracy',
    category: 'Format Conformance',
    defaultRiskLevel: 'medium',
    ruleType: 'regex',
    templateRuleDefinition: {
      description: 'Pattern match validation',
      attributes: [],
      expectedValues: { pattern: '^[A-Z0-9]+$' },
    },
    exampleUse: 'Ensure customer IDs match pattern (e.g., CUST-12345)',
    icon: 'check-circle',
  },
  {
    id: 'template-accuracy-2',
    name: 'Email Format Check',
    description: 'Validate email addresses follow RFC standard format',
    dimension: 'accuracy',
    category: 'Format Conformance',
    defaultRiskLevel: 'high',
    ruleType: 'regex',
    templateRuleDefinition: {
      description: 'Email format validation',
      attributes: [],
      expectedValues: { pattern: '^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$' },
    },
    exampleUse: 'Ensure all contact emails are valid formats',
    icon: 'envelope',
  },
  {
    id: 'template-accuracy-3',
    name: 'Phone Number Validation',
    description: 'Verify phone numbers conform to expected format',
    dimension: 'accuracy',
    category: 'Format Conformance',
    defaultRiskLevel: 'medium',
    ruleType: 'regex',
    templateRuleDefinition: {
      description: 'Phone format validation',
      attributes: [],
      expectedValues: { pattern: '^\\+?[0-9]{10,}$' },
    },
    exampleUse: 'Validate phone numbers have correct digit count',
    icon: 'phone',
  },
  {
    id: 'template-accuracy-4',
    name: 'Allowlist Validation',
    description: 'Check values exist in a predefined set',
    dimension: 'accuracy',
    category: 'Value Validation',
    defaultRiskLevel: 'high',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Allowlist/whitelist validation',
      attributes: [],
      expectedValues: { allowlist: ['value1', 'value2', 'value3'] },
    },
    exampleUse: 'Ensure order status is one of: Pending, Shipped, Delivered, Cancelled',
    icon: 'list',
  },

  // CONSISTENCY
  {
    id: 'template-consistency-1',
    name: 'Referential Integrity',
    description: 'Verify foreign key references exist in parent table',
    dimension: 'consistency',
    category: 'Cross-Table Consistency',
    defaultRiskLevel: 'high',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check referential integrity',
      attributes: [],
      expectedValues: { parentTable: 'parent_table', foreignKey: 'parent_id' },
    },
    exampleUse: 'Ensure all order.customer_id values exist in customers.id',
    icon: 'link',
  },
  {
    id: 'template-consistency-2',
    name: 'Cross Dataset Integrity',
    description: 'Compare aligned fields across related datasets and flag divergence',
    dimension: 'consistency',
    category: 'Cross-System Comparison',
    defaultRiskLevel: 'high',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check cross-dataset integrity',
      attributes: [],
      expectedValues: {
        joinKeys: [{ leftAttribute: 'customer_id', rightAttribute: 'customer_id' }],
        comparisonColumns: [{ leftAttribute: 'status', rightAttribute: 'status', mode: 'exact' }],
      },
    },
    exampleUse: 'Verify account status stays aligned between operational and reporting datasets',
    icon: 'link',
  },
  {
    id: 'template-consistency-3',
    name: 'Case Standardization',
    description: 'Detect inconsistent casing in categorical fields',
    dimension: 'consistency',
    category: 'Format Consistency',
    defaultRiskLevel: 'low',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check case consistency',
      attributes: [],
      expectedValues: { caseStandard: 'UPPERCASE' },
    },
    exampleUse: 'Ensure country codes are consistently uppercase (US, UK, DE)',
    icon: 'check-alt',
  },
  {
    id: 'template-consistency-4',
    name: 'Whitespace Normalization',
    description: 'Identify inconsistent whitespace in text fields',
    dimension: 'consistency',
    category: 'Format Consistency',
    defaultRiskLevel: 'low',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check whitespace consistency',
      attributes: [],
    },
    exampleUse: 'Detect leading/trailing spaces in customer names',
    icon: 'eye-open',
  },
  {
    id: 'template-reconciliation-1',
    name: 'Reconciliation Blueprint',
    description: 'Reusable left/right comparison contract for Data Assets and rules',
    dimension: 'consistency',
    category: 'Cross-System Comparison',
    defaultRiskLevel: 'high',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Reusable reconciliation definition',
      leftDataObjectVersionId: 'ledger-left-v1',
      rightDataObjectVersionId: 'ledger-right-v1',
      joinKeys: [{ leftAttribute: 'account_id', rightAttribute: 'account_id' }],
      comparisons: [
        { leftAttribute: 'status', rightAttribute: 'status', mode: 'exact' },
        { leftAttribute: 'balance_amount', rightAttribute: 'balance_amount', mode: 'numeric_tolerance', tolerance: 0.01 },
      ],
      reusableTargets: ['rules', 'data_assets'],
    },
    exampleUse: 'Reuse the same left/right comparison blueprint in rule authoring and Data Asset policy docs.',
    icon: 'link',
  },

  // TIMELINESS
  {
    id: 'template-timeliness-1',
    name: 'Freshness Check',
    description: 'Verify data is updated within expected time window',
    dimension: 'timeliness',
    category: 'Data Currency',
    defaultRiskLevel: 'high',
    ruleType: 'range',
    templateRuleDefinition: {
      description: 'Check data freshness',
      attributes: ['updated_at'],
      expectedValues: { maxDaysOld: 7 },
    },
    exampleUse: 'Ensure customer records are updated at least weekly',
    icon: 'clock',
  },
  {
    id: 'template-timeliness-2',
    name: 'Processing Lag Detection',
    description: 'Monitor delay between data creation and processing',
    dimension: 'timeliness',
    category: 'Data Currency',
    defaultRiskLevel: 'medium',
    ruleType: 'range',
    templateRuleDefinition: {
      description: 'Check processing lag',
      attributes: ['created_at', 'processed_at'],
      expectedValues: { maxHoursLag: 24 },
    },
    exampleUse: 'Ensure transactions are processed within 24 hours',
    icon: 'warning',
  },
  {
    id: 'template-timeliness-3',
    name: 'Future Date Detection',
    description: 'Flag records with dates in the future',
    dimension: 'timeliness',
    category: 'Date Validity',
    defaultRiskLevel: 'high',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check for future dates',
      attributes: ['event_date'],
    },
    exampleUse: 'Detect orders with ship dates in the future',
    icon: 'bookmark',
  },

  // VALIDITY
  {
    id: 'template-validity-1',
    name: 'Range Check',
    description: 'Verify numeric values fall within acceptable range',
    dimension: 'validity',
    category: 'Value Range',
    defaultRiskLevel: 'medium',
    ruleType: 'range',
    templateRuleDefinition: {
      description: 'Check value range',
      attributes: [],
      expectedValues: { minValue: 0, maxValue: 100 },
    },
    exampleUse: 'Ensure discount percentages are between 0 and 100',
    icon: 'info-circle',
  },
  {
    id: 'template-validity-2',
    name: 'Age Validation',
    description: 'Check calculated age falls within reasonable bounds',
    dimension: 'validity',
    category: 'Calculated Fields',
    defaultRiskLevel: 'medium',
    ruleType: 'range',
    templateRuleDefinition: {
      description: 'Validate age calculation',
      attributes: ['age'],
      expectedValues: { minAge: 0, maxAge: 150 },
    },
    exampleUse: 'Ensure calculated customer ages are between 0 and 150',
    icon: 'person',
  },
  {
    id: 'template-validity-3',
    name: 'Outlier Detection',
    description: 'Identify statistical outliers in numeric fields',
    dimension: 'validity',
    category: 'Statistical Validity',
    defaultRiskLevel: 'medium',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check for statistical outliers',
      attributes: [],
      expectedValues: { method: 'zscore', threshold: 3 },
    },
    exampleUse: 'Flag transaction amounts that are significantly different from average',
    icon: 'receipt',
  },
  {
    id: 'template-validity-4',
    name: 'Distribution Drift',
    description: 'Detect shifts in a value distribution against a historical baseline',
    dimension: 'validity',
    category: 'Statistical Validity',
    defaultRiskLevel: 'medium',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check distribution drift',
      attributes: ['amount'],
      expectedValues: { baselineWindow: '30d', distributionMetric: 'psi', driftThreshold: 0.2 },
    },
    exampleUse: 'Flag unexpected shifts in transaction amounts after a release',
    icon: 'warning',
  },
  {
    id: 'template-validity-5',
    name: 'Entropy Drift',
    description: 'Track entropy changes that indicate categorical instability',
    dimension: 'validity',
    category: 'Statistical Validity',
    defaultRiskLevel: 'medium',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check entropy drift',
      attributes: ['status'],
      expectedValues: { baselineWindow: '14d', entropyThreshold: 0.15 },
    },
    exampleUse: 'Detect sudden label churn in workflow statuses',
    icon: 'receipt',
  },
  {
    id: 'template-validity-6',
    name: 'Probabilistic Threshold',
    description: 'Validate probabilistic scores stay above an agreed confidence floor',
    dimension: 'validity',
    category: 'Statistical Validity',
    defaultRiskLevel: 'high',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check probabilistic threshold',
      attributes: ['risk_score'],
      expectedValues: { confidenceLevel: 0.99, minimumProbability: 0.95 },
    },
    exampleUse: 'Only publish records when classifier confidence is high enough',
    icon: 'check-alt',
  },
  {
    id: 'template-validity-7',
    name: 'Seasonality Stability',
    description: 'Ensure repeating seasonal patterns stay within the expected variation band',
    dimension: 'validity',
    category: 'Statistical Validity',
    defaultRiskLevel: 'medium',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check seasonality stability',
      attributes: ['sales_amount'],
      expectedValues: { baselineWindow: '28d', maxDeviation: 0.1, seasonalPeriod: '7d' },
    },
    exampleUse: 'Detect week-over-week spikes that break the normal weekly pattern',
    icon: 'calendar',
  },

  // UNIQUENESS
  {
    id: 'template-uniqueness-1',
    name: 'Primary Key Check',
    description: 'Verify all values in primary key field are unique',
    dimension: 'uniqueness',
    category: 'Identity Validation',
    defaultRiskLevel: 'high',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check primary key uniqueness',
      attributes: [],
    },
    exampleUse: 'Ensure customer IDs are unique across all records',
    icon: 'padlock-closed',
  },
  {
    id: 'template-uniqueness-2',
    name: 'Duplicate Detection',
    description: 'Identify exact or near-duplicate rows',
    dimension: 'uniqueness',
    category: 'Duplicate Detection',
    defaultRiskLevel: 'high',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check for duplicates',
      attributes: [],
      expectedValues: { columns: ['field1', 'field2'], allowDuplicates: false },
    },
    exampleUse: 'Detect duplicate customer records (same name + email)',
    icon: 'copy',
  },
  {
    id: 'template-uniqueness-3',
    name: 'Email Uniqueness',
    description: 'Ensure email addresses appear only once in table',
    dimension: 'uniqueness',
    category: 'Unique Value Check',
    defaultRiskLevel: 'high',
    ruleType: 'custom',
    templateRuleDefinition: {
      description: 'Check email uniqueness',
      attributes: ['email'],
    },
    exampleUse: 'Verify no customer has duplicate email addresses',
    icon: 'envelope',
  },
]
