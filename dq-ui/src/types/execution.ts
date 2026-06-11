/**
 * Execution results, metrics, and diagnostics types
 */

export type FailureClass =
  | 'value_mismatch'
  | 'actuality_date_drift'
  | 'null_or_missing_join_key'
  | 'other';

export interface FailureDiagnostic {
  failureClass: FailureClass;
  rowIdentifier?: string | null;
  details: string;
  affectedAttributes?: string[] | null;
}

export interface DiagnosticsSummary {
  failureClass: FailureClass;
  count: number;
  sampleFailures: FailureDiagnostic[];
  maxSampleSize: number;
}

export interface JoinConsistencyExecutionMetrics {
  matchCount: number;
  mismatchCount: number;
  eligibleJoinedRows: number;
  matchRate: number; // 0-100
  actualityDateMismatchCount: number;
  nullOrMissingJoinKeyCount: number;
}

export interface ExecutionMetricsView {
  checkType?: string | null;
  data?: Record<string, any> | null;
}

export interface TestProof {
  id: string;
  ruleId: string;
  testDate: string;
  coverage: number;
  status: string;
  recordsTestedCount: number;
  failuresFound: number;
  proofData: Record<string, any>;
  executionTrace?: ExecutionTraceView | null;
  metrics?: JoinConsistencyExecutionMetrics | null;
  diagnostics?: DiagnosticsSummary[] | null;
}

export interface ExecutionTraceView {
  executionId: string;
  correlationId?: string | null;
  executedAt?: string | null;
  resultStatus: string;
  artifactKey?: string | null;
  ruleVersionId?: string | null;
  ruleVersionNumber?: number | null;
  compilerVersion?: string | null;
  compilerRevision?: number | null;
  schemaVersion?: string | null;
}
