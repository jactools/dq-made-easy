/**
 * Rule lifecycle and approval workflow types
 */

import type {
  DiagnosticsSummary,
  JoinConsistencyExecutionMetrics,
} from './execution'

export type RuleStatus = 
  | 'draft'          // Rule created, not yet tested
  | 'testing'        // Tests are running
  | 'tested'         // Tests completed/passed
  | 'pending-approval' // Awaiting approval from reviewer
  | 'approved'       // Approved, ready to activate
  | 'activated'      // Active in production
  | 'deactivated'    // Deactivated after approval
  | 'rejected';      // Rejected by reviewer

export type RuleCheckType =
  | 'THRESHOLD'
  | 'ROW_COUNT'
  | 'REGEX'
  | 'RANGE'
  | 'ALLOWLIST'
  | 'BLOCKLIST'
  | 'UNIQUENESS'
  | 'REFERENTIAL_INTEGRITY'
  | 'FRESHNESS'
  | 'LAG'
  | 'FUTURE_DATE'
  | 'CORRECT'
  | 'PRESENT'
  | 'RECONCILE'
  | 'PLAUSIBLE'
  | 'TRANSFER_MATCH'
  | 'JOIN_CONSISTENCY';

export type ThresholdMetric = 'null_pct' | 'empty_pct' | 'default_val_pct' | 'missing_count' | 'duplicate_count' | 'duplicate_percent' | 'quantile' | 'min' | 'max' | 'avg' | 'sum' | 'stddev' | 'distinct_count';
export type ComparisonOperator = 'gt' | 'gte' | 'lt' | 'lte';
export type RowCountOperator = ComparisonOperator | 'between';
export type CrossObjectComparisonMode = 'exact' | 'case_insensitive' | 'numeric_tolerance';
export type PlausibilityMode = 'contextual_range' | 'conditional_allowlist';
export type TransferMatchMode = 'row_value_match' | 'payload_hash_match';

export interface ThresholdParams   { checkType: 'THRESHOLD';             attribute: string; metric: ThresholdMetric; operator: ComparisonOperator; threshold: number; quantile?: number; }
export interface RowCountParams    { checkType: 'ROW_COUNT';             operator: RowCountOperator; threshold?: number; minValue?: number; maxValue?: number; }
export interface RegexParams        { checkType: 'REGEX';                  attribute: string; pattern: string; flags?: string; }
export interface RangeParams        { checkType: 'RANGE';                  attribute: string; minValue?: number | string; maxValue?: number | string; inclusive?: boolean; }
export interface AllowlistParams    { checkType: 'ALLOWLIST';              attribute: string; allowedValues: string[]; caseSensitive?: boolean; }
export interface BlocklistParams    { checkType: 'BLOCKLIST';              attribute: string; blockedValues: string[]; caseSensitive?: boolean; }
export interface UniquenessParams   { checkType: 'UNIQUENESS';             attributes: string[]; }
export interface ReferentialIntegrityParams {
  checkType: 'REFERENTIAL_INTEGRITY';
  attribute: string;
  refDataObjectId: string;
  refDataObjectVersionId: string;
  refAttribute: string;
  refWorkspaceId?: string;
}
export interface FreshnessParams    { checkType: 'FRESHNESS';              attribute: string; maxDaysOld: number; anchor?: 'now' | 'processing_date'; }
export interface LagParams          { checkType: 'LAG';                    startAttribute: string; endAttribute: string; maxHours: number; }
export interface FutureDateParams   { checkType: 'FUTURE_DATE';            attribute: string; referenceDate?: string; }
export interface CrossObjectJoinKey {
  leftAttribute: string;
  rightAttribute: string;
}
export interface CrossObjectComparison {
  leftAttribute: string;
  rightAttribute: string;
  mode: CrossObjectComparisonMode;
  tolerance?: number;
}
export interface PresentParams {
  checkType: 'PRESENT';
  attribute: string;
  blockedValues: string[];
  caseSensitive?: boolean;
}
export interface CorrectParams {
  checkType: 'CORRECT';
  sourceDataObjectVersionId: string;
  referenceDataObjectVersionId: string;
  joinKeys: CrossObjectJoinKey[];
  comparison: CrossObjectComparison;
  actualityDate?: ActualityDateContract;
}
export interface ReconcileParams {
  checkType: 'RECONCILE';
  leftDataObjectVersionId: string;
  rightDataObjectVersionId: string;
  joinKeys: CrossObjectJoinKey[];
  comparisons: CrossObjectComparison[];
  actualityDate?: ActualityDateContract;
}
export interface PlausibleContextualRange {
  contextValue: string;
  minValue?: number | string;
  maxValue?: number | string;
  inclusive?: boolean;
}
export interface PlausibleConditionalAllowlist {
  contextValue: string;
  allowedValues: string[];
  caseSensitive?: boolean;
}
export interface PlausibleParams {
  checkType: 'PLAUSIBLE';
  mode: PlausibilityMode;
  attribute: string;
  contextAttribute: string;
  ranges?: PlausibleContextualRange[];
  allowlists?: PlausibleConditionalAllowlist[];
}
export interface TransferMatchParams {
  checkType: 'TRANSFER_MATCH';
  mode: TransferMatchMode;
  leftDataObjectVersionId: string;
  rightDataObjectVersionId: string;
  joinKeys: CrossObjectJoinKey[];
  comparisons?: CrossObjectComparison[];
  leftHashAttribute?: string;
  rightHashAttribute?: string;
  actualityDate?: ActualityDateContract;
}
export interface JoinConsistencyJoinKey {
  leftAttribute: string;
  rightAttribute: string;
}
export interface JoinConsistencyComparison {
  leftAttribute: string;
  rightAttribute: string;
  mode: 'exact' | 'case_insensitive';
}
// Shared across CORRECT, RECONCILE, TRANSFER_MATCH, and JOIN_CONSISTENCY.
// Matches backend ActualityDateContract Pydantic model.
export type ActualityDateToleranceSource = 'DELIVERY_CONTRACT' | 'DELIVERY_METADATA' | 'EXPLICIT';
export type ActualityDateToleranceUnit = 'minutes' | 'hours' | 'days';

export interface ActualityDateContract {
  leftAttribute: string;
  rightAttribute: string;
  toleranceSource: ActualityDateToleranceSource;
  contractId: string;
  contractVersion?: string;
  resolvedToleranceValue?: number;
  resolvedToleranceUnit?: ActualityDateToleranceUnit;
  overrideToleranceValue?: number;
  overrideToleranceUnit?: ActualityDateToleranceUnit;
  overrideAllowed?: boolean;
  maxOverrideToleranceValue?: number;
  maxOverrideToleranceUnit?: ActualityDateToleranceUnit;
  autoResolve?: boolean;
}

/** @deprecated use ActualityDateContract; kept for backward-compat with persisted rules. */
export type JoinConsistencyActualityDate = ActualityDateContract;
export interface JoinConsistencyParams {
  checkType: 'JOIN_CONSISTENCY';
  leftDataObjectVersionId: string;
  rightDataObjectVersionId: string;
  joinKeys: JoinConsistencyJoinKey[];
  comparisons: JoinConsistencyComparison[];
  actualityDate: JoinConsistencyActualityDate;
  minMatchRate: number;
}

export type RuleCheckTypeParams =
  | ThresholdParams
  | RowCountParams
  | RegexParams
  | RangeParams
  | AllowlistParams
  | BlocklistParams
  | UniquenessParams
  | ReferentialIntegrityParams
  | FreshnessParams
  | LagParams
  | FutureDateParams
  | PresentParams
  | CorrectParams
  | ReconcileParams
  | PlausibleParams
  | TransferMatchParams
  | JoinConsistencyParams;

/**
 * A single rule-to-attribute assignment, optionally carrying a per-attribute
 * threshold override that supersedes the rule-level threshold for THRESHOLD checks.
 */
export interface RuleAttributeEntry {
  ruleId: string;
  attributeId: string;
  /** When set, overrides the rule-level threshold for this specific attribute. */
  thresholdOverride?: number;
}

/** ruleId → attributeId → override threshold */
export type RuleAttributeThresholds = Record<string, Record<string, number | undefined>>;

export type AuditAction = 
  | 'created'
  | 'tested'
  | 'submitted-for-approval'
  | 'approved'
  | 'rejected'
  | 'activated'
  | 'deactivated'
  | 'modified'
  | 'drift-reviewed'
  | 'profiling.requested'
  | 'suggestion.accepted'
  | 'suggestion.dismissed'
  | 'suggestion.applied'
  | 'validation_run_plan.replayed'
  | 'notification.contract_change';

export interface RuleJoinCondition {
  leftDataObjectId: string;
  leftAttributeId: string;
  rightDataObjectId: string;
  rightAttributeId: string;
  operator: '=' | '!=' | '>' | '>=' | '<' | '<=';
}

export interface RuleJoinDefinition {
  joinType: 'inner' | 'left' | 'right' | 'full';
  conditions: RuleJoinCondition[];
}

export interface ReusableFilter {
  id: string;
  name: string;
  description?: string;
  expression: string;
  workspace?: string;
  active?: boolean;
}

export interface ReusableJoin {
  id: string;
  name: string;
  description?: string;
  joinDefinition: RuleJoinDefinition[];
  workspace?: string;
  active?: boolean;
}

export interface RuleAliasMapping {
  attributeId: string;
  expectedDataType?: string;
  actualDataType?: string;
  compatible?: boolean;
}

export interface RuleManualExpressionOverride {
  expression: string;
  confirmed: boolean;
}

export interface FilterExpressionRuleDslSource {
  kind: 'filter_expression';
  expression: string;
  joinConditions?: RuleJoinDefinition[];
  aliasMappings?: Record<string, RuleAliasMapping>;
  reusableJoinId?: string | null;
  reusableFilterIds?: string[];
}

export interface CheckTypeRuleDslSource {
  kind: 'check_type';
  checkType: RuleCheckType | string;
  checkTypeParams: RuleCheckTypeParams | Record<string, unknown>;
  joinConditions?: RuleJoinDefinition[];
  aliasMappings?: Record<string, RuleAliasMapping>;
  reusableJoinId?: string | null;
  reusableFilterIds?: string[];
  manualExpressionOverride?: RuleManualExpressionOverride;
}

export type RuleDslSource = FilterExpressionRuleDslSource | CheckTypeRuleDslSource;

export interface RuleDslContract {
  schemaVersion: string;
  source: RuleDslSource;
}

export interface Rule {
  id: string;
  workspace: string;
  name: string;
  description: string;
  comments?: string;
  expression?: string;
  dimension?: 'Completeness' | 'Accuracy' | 'Consistency' | 'Timeliness' | 'Validity' | 'Uniqueness';
  active?: boolean;
  generated?: boolean;
  manualOverrideConfirmed?: boolean;
  manual_override_by?: string;
  manual_override_at?: string;
  manualOverrideBy?: string;
  manualOverrideAt?: string;
  is_template?: boolean;
  template_id?: string;
  createdBy?: string;
  last_approval_by?: string;
  last_approval_status?: string;
  last_approval_at?: string;
  deleted_on?: string;
  deleted_by?: string;
  suggestionId?: string; // ID of the suggestion this rule was created from
  createdFromSuggestion?: boolean; // Indicator that rule was created from a suggestion
  // Computed/required properties
  status: RuleStatus;
  createdAt: string;
  updatedAt?: string;
  testResults?: RuleTestResult;
  testResultsHistory?: RuleTestResult[];
  attributes: string[]; // data quality attribute IDs
  riskLevel: 'low' | 'medium' | 'high';
  joinConditions?: RuleJoinDefinition[];
  reusableFilterIds?: string[];
  reusableFilters?: ReusableFilter[];
  reusableJoinId?: string | null;
  reusableJoin?: ReusableJoin;
  aliasMappings?: Record<string, RuleAliasMapping>;
  validationStatus?: 'valid' | 'invalid' | null;
  validatedAt?: string | null;
  currentVersionNumber?: number;
  pendingDeactivationRequested?: boolean;
  checkType?: RuleCheckType;
  checkTypeParams?: RuleCheckTypeParams;
  dsl?: RuleDslContract;
}

export interface RuleTestResult {
  id: string;
  ruleId: string;
  testDate: string;
  status: 'passed' | 'failed' | 'pending';
  coverage: number; // percentage of test cases passed
  failureDetails?: string;
  recordsTestedCount: number;
  failuresFound: number;
  proofData?: any;
  metrics?: JoinConsistencyExecutionMetrics | null;
  diagnostics?: DiagnosticsSummary[] | null;
}

export interface ApprovalComment {
  id: string;
  authorId: string;
  authorName: string;
  content: string;
  type: 'note' | 'concern' | 'question' | 'general';
  createdAt: string;
  state?: 'new' | 'acknowledged_by_owner' | 'voted_up' | 'resolved' | 'reopened' | 'locked';
  locked?: boolean;
  removed?: boolean;
  removedAt?: string;
  removedBy?: string;
  removedReason?: string;
  edited?: boolean;
  editedAt?: string;
  editedBy?: string;
  editCount?: number;
  voteCount?: number;
  acknowledgedAt?: string;
  acknowledgedBy?: string;
  resolvedAt?: string;
  resolvedBy?: string;
  reopenedAt?: string;
  reopenedBy?: string;
}

export interface ApprovalHistoryEvent {
  id: string;
  eventType: 'requested' | 'commented' | 'approved' | 'rejected' | 'escalated';
  userId: string;
  userName: string;
  timestamp: string;
  details?: {
    comment?: string;
    reason?: string;
    previousStatus?: string;
    escalationReason?: string;
  };
}

export interface EmailNotification {
  id: string;
  recipientId: string;
  recipientEmail: string;
  recipientName: string;
  eventType: 'submitted' | 'commented' | 'approved' | 'rejected' | 'escalated';
  subject: string;
  sentAt: string;
  status: 'sent' | 'failed' | 'pending';
}

export interface TeamsNotification {
  id: string;
  recipientId: string;
  recipientName: string;
  teamsChannelId: string;
  teamsChannelName: string;
  eventType: 'submitted' | 'commented' | 'approved' | 'rejected' | 'escalated';
  message: string;
  sentAt: string;
  status: 'sent' | 'failed' | 'pending';
}

export interface ApprovalDelegation {
  id: string;
  delegatedFromId: string;
  delegatedFromName: string;
  delegatedToId: string;
  delegatedToName: string;
  delegatedAt: string;
  delegationReason?: string;
  validUntil?: string; // Optional expiration
  status: 'active' | 'expired' | 'revoked';
}

export interface RuleApproval {
  id: string;
  ruleId: string;
  gxRunPlanId?: string;
  gxRunPlanVersionId?: string;
  effectiveStatus?: 'activated' | 'deactivated' | null;
  requesterId: string;
  requesterName?: string;
  requesterDisplayName?: string;
  requestedBy?: string;
  requestedByName?: string;
  requestedByDisplayName?: string;
  requestedAt: string;
  reviewedBy?: string;
  reviewedAt?: string;
  status: 'pending' | 'approved' | 'rejected';
  requestType?: 'activation' | 'deactivation' | 'gx_suite_repair';
  comments?: string;
  commentThread?: ApprovalComment[];
  commentsLocked?: boolean;
  removedCommentCount?: number;
  history?: ApprovalHistoryEvent[];
  emailNotifications?: EmailNotification[];
  teamsNotifications?: TeamsNotification[];
  delegation?: ApprovalDelegation; // If approval is delegated
  workspaceId: string;
}

export interface RuleStatusHistoryEntry {
  id: string;
  ruleId: string;
  action: string;
  fromStatus?: string | null;
  toStatus: string;
  changedBy?: string | null;
  changedAt: string;
  reason?: string | null;
  details?: Record<string, any> | null;
}

export interface AuditLogEntry {
  id: string;
  ruleId: string;
  action: AuditAction;
  userId: string;
  userName: string;
  timestamp: string;
  details: {
    previousStatus?: RuleStatus;
    newStatus?: RuleStatus;
    comments?: string;
    testResults?: {
      coverage: number;
      passed: boolean;
    };
    [key: string]: any;
  };
  workspaceId: string;
}

export interface RuleStats {
  total: number;
  byStatus: Record<RuleStatus, number>;
  awaitingApproval: number;
  recentlyActivated: number;
  failedTests: number;
}

export type SuggestionStatus = 'pending' | 'accepted' | 'dismissed' | 'applied';
export type RuleType =
  | 'NOT_NULL'
  | 'UNIQUE'
  | 'FORMAT_VALIDATION'
  | 'RANGE_CHECK'
  | 'REFERENTIAL_INTEGRITY'
  | 'UNIQUENESS'
  | 'PRESENT'
  | 'REGEX'
  | 'RANGE'
  | 'ALLOWLIST'
  | 'FRESHNESS';

export interface SuggestedAttributeSnapshot {
  attributeId: string;
  attributeName: string;
  versionId?: string;
  dataObjectId?: string;
  dataObjectName?: string;
  dataSetId?: string;
  dataSetName?: string;
  dataProductId?: string;
  dataProductName?: string;
  workspaceId?: string;
  parentPath: string[];
  confidenceScore?: number;
  matchReasons?: string[];
  currentContext?: boolean;
  matchRoles?: string[];
}

export interface SuggestedRuleCondition {
  attributeTerm: string;
  operator: string;
  value: string;
  sameVersionRequired?: boolean;
}

export interface SuggestedRule {
  name: string;
  description: string;
  expression?: string;
  ruleType: RuleType;
  dimension?: 'Completeness' | 'Accuracy' | 'Consistency' | 'Timeliness' | 'Validity' | 'Uniqueness';
  checkType?: RuleCheckType;
  checkTypeParams?: Record<string, unknown>;
  workspaceId?: string;
  targetTerms?: string[];
  searchScope?: string;
  selectedAttributeIds?: string[];
  selectedAttributes?: SuggestedAttributeSnapshot[];
  draftSummary?: string;
  parsedCondition?: SuggestedRuleCondition;
  dsl?: {
    schemaVersion: '2.0.0';
    rule: {
      kind: string;
      scope: Record<string, unknown>;
      measure: Record<string, unknown>;
      expectation: Record<string, unknown>;
      evidence: Record<string, unknown>;
      operations: Record<string, unknown>;
      reusableJoinId?: string | null;
      reusableFilterIds?: string[];
    };
  };
  prompt?: string;
  originalPromptText?: string;
}

export interface Suggestion {
  id: string;
  userId: string;
  dataSourceId: string;
  suggestedRule: SuggestedRule;
  confidenceScore: number;
  reason: string;
  ruleType: RuleType;
  createdFromProfilingRequestId?: string;
  status: SuggestionStatus;
  createdAt: string;
  expiresAt?: string;
}

export interface SuggestionInteraction {
  id: string;
  suggestionId: string;
  userId: string;
  action: 'viewed' | 'accepted' | 'dismissed' | 'applied';
  ruleCreatedFromSuggestionId?: string;
  createdAt: string;
}

// Rule Versioning Types
export type VersionChangeType = 
  | 'created'
  | 'expression_updated'
  | 'metadata_updated'
  | 'status_changed'
  | 'rollback'
  | 'approval_applied'
  | 'test_proof_attached';

export interface RuleVersion {
  id: string;
  ruleId: string;
  versionNumber: number;
  createdAt: string;
  createdBy: string;
  changeType: VersionChangeType;
  changeDescription?: string;
  validationStatus?: 'valid' | 'invalid' | 'upstream-error' | null;
  validatedAt?: string | null;
  validatedBy?: string;
  validatedByUserId?: string | null;
  // Snapshot of rule state at this version
  name: string;
  description: string;
  expression: string;
  dimension?: string;
  active: boolean;
  isTemplate: boolean;
  templateId?: string;
  tags: string[];
  markedForRollback: boolean;
}

export interface RuleVersionDiff {
  field: string;
  oldValue: any;
  newValue: any;
  changeType: 'added' | 'removed' | 'modified';
}

export interface RuleVersionComparison {
  version1: RuleVersion;
  version2: RuleVersion;
  differences: RuleVersionDiff[];
  significantChanges: boolean; // true if expression or critical fields changed
}

export interface RuleRollback {
  id: string;
  ruleId: string;
  fromVersionId: string;
  toVersionId: string;
  rolledBackBy: string;
  rolledBackAt: string;
  reason: string;
  newVersionCreatedId: string; // Version created by the rollback
  fromVersionNumber: number;
  toVersionNumber: number;
  newVersionNumber: number;
}

export interface RuleVersionRelationship {
  id: string;
  ruleVersionId: string;
  relatedType: 'approval' | 'test_proof' | 'suggestion';
  relatedId: string;
  createdAt: string;
}

export interface VersionStatistics {
  totalVersions: number;
  totalRollbacks: number;
  averageVersionsPerRule: number;
  mostVersionedRules: Array<{
    ruleId: string;
    ruleName: string;
    versionCount: number;
  }>;
  recentRollbacks: RuleRollback[];
}

