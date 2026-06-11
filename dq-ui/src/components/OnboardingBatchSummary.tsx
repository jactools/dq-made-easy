import React, { useState } from 'react'
import { AppBanner, AppButton, AppModal, AppStack } from './app-primitives'
import { snakeToCamel } from '../utils/caseConverters'
import { useRules } from '../hooks/useContexts'
import './OnboardingBatchSummary.css'

export interface BatchRuleOutcome {
  proposalId: string
  status: 'created' | 'skipped' | 'failed'
  ruleId: string | null
  reason: string | null
}

export interface OnboardingBatchResponse {
  batchId: string
  workspaceId: string
  totalAccepted: number
  created: number
  skipped: number
  failed: number
  outcomes: BatchRuleOutcome[]
  createdAt: string
}

interface OnboardingBatchSummaryProps {
  isOpen: boolean
  response: OnboardingBatchResponse | Record<string, unknown> | null
  isCreatingBatch?: boolean
  onClose: () => void
  onGoToRules: (batchId: string) => void
}

const normalizeResponse = (
  response: OnboardingBatchResponse | Record<string, unknown> | null,
): OnboardingBatchResponse | null => {
  if (!response) return null
  const normalized = snakeToCamel<any>(response)
  return {
    batchId: String(normalized.batchId ?? ''),
    workspaceId: String(normalized.workspaceId ?? ''),
    totalAccepted: Number(normalized.totalAccepted ?? 0),
    created: Number(normalized.created ?? 0),
    skipped: Number(normalized.skipped ?? 0),
    failed: Number(normalized.failed ?? 0),
    outcomes: Array.isArray(normalized.outcomes)
      ? normalized.outcomes.map((o: any) => ({
          proposalId: String(o.proposalId ?? ''),
          status: o.status as BatchRuleOutcome['status'],
          ruleId: o.ruleId ? String(o.ruleId) : null,
          reason: o.reason ? String(o.reason) : null,
        }))
      : [],
    createdAt: String(normalized.createdAt ?? ''),
  }
}

export const OnboardingBatchSummary: React.FC<OnboardingBatchSummaryProps> = ({
  isOpen,
  response,
  isCreatingBatch = false,
  onClose,
  onGoToRules,
}) => {
  const { submitForApproval } = useRules()
  const [isSubmittingApprovals, setIsSubmittingApprovals] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitSuccessCount, setSubmitSuccessCount] = useState<number | null>(null)
  const [failedExpanded, setFailedExpanded] = useState(false)

  const batchResponse = normalizeResponse(response)

  const createdRuleIds: string[] = batchResponse
    ? batchResponse.outcomes
        .filter((o) => o.status === 'created' && o.ruleId)
        .map((o) => o.ruleId as string)
    : []

  const failedOutcomes: BatchRuleOutcome[] = batchResponse
    ? batchResponse.outcomes.filter((o) => o.status === 'failed')
    : []

  const handleGoToRules = () => {
    if (batchResponse?.batchId) {
      onGoToRules(batchResponse.batchId)
    }
  }

  const handleSubmitForApproval = async () => {
    if (createdRuleIds.length === 0) return
    setIsSubmittingApprovals(true)
    setSubmitError(null)
    setSubmitSuccessCount(null)

    let successCount = 0
    const errors: string[] = []

    for (const ruleId of createdRuleIds) {
      try {
        await submitForApproval(ruleId)
        successCount += 1
      } catch (err) {
        errors.push(ruleId)
      }
    }

    setIsSubmittingApprovals(false)
    setSubmitSuccessCount(successCount)
    if (errors.length > 0) {
      setSubmitError(
        `${errors.length} rule${errors.length !== 1 ? 's' : ''} could not be submitted for approval.`,
      )
    }
  }

  const modalFooter = (
    <div className="onboarding-batch-summary__footer">
      <AppButton variant="secondary" onClick={onClose} disabled={isSubmittingApprovals}>
        Close
      </AppButton>
      {batchResponse && createdRuleIds.length > 0 && submitSuccessCount === null && (
        <AppButton
          variant="primary"
          onClick={() => void handleSubmitForApproval()}
          disabled={isSubmittingApprovals || isCreatingBatch}
        >
          {isSubmittingApprovals
            ? 'Submitting…'
            : `Submit ${createdRuleIds.length} Draft${createdRuleIds.length !== 1 ? 's' : ''} for Approval`}
        </AppButton>
      )}
      {batchResponse && (
        <AppButton
          variant="primary"
          onClick={handleGoToRules}
          disabled={isSubmittingApprovals || isCreatingBatch}
        >
          Go to Rules
        </AppButton>
      )}
    </div>
  )

  return (
    <AppModal
      isOpen={isOpen}
      title="Batch Rule Creation Summary"
      onClose={onClose}
      footer={modalFooter}
    >
      <AppStack gap="md">
        {isCreatingBatch && (
          <div className="onboarding-batch-summary__progress" role="status" aria-live="polite">
            <div className="onboarding-batch-summary__progress-bar" aria-label="Creating rules…" />
            <span className="onboarding-batch-summary__progress-label">Creating rules, please wait…</span>
          </div>
        )}

        {!isCreatingBatch && !batchResponse && (
          <AppBanner variant="info">No batch result available.</AppBanner>
        )}

        {batchResponse && (
          <>
            <div className="onboarding-batch-summary__meta">
              <span className="onboarding-batch-summary__batch-id">
                Batch: <code>{batchResponse.batchId}</code>
              </span>
            </div>

            <div className="onboarding-batch-summary__counts" role="region" aria-label="Batch result counts">
              <div className="onboarding-batch-summary__count onboarding-batch-summary__count--created">
                <span className="onboarding-batch-summary__count-value">{batchResponse.created}</span>
                <span className="onboarding-batch-summary__count-label">Created</span>
              </div>
              <div className="onboarding-batch-summary__count onboarding-batch-summary__count--skipped">
                <span className="onboarding-batch-summary__count-value">{batchResponse.skipped}</span>
                <span className="onboarding-batch-summary__count-label">Skipped (already covered)</span>
              </div>
              <div className="onboarding-batch-summary__count onboarding-batch-summary__count--failed">
                <span className="onboarding-batch-summary__count-value">{batchResponse.failed}</span>
                <span className="onboarding-batch-summary__count-label">Failed</span>
              </div>
            </div>

            {failedOutcomes.length > 0 && (
              <div className="onboarding-batch-summary__failed-section">
                <button
                  type="button"
                  className="onboarding-batch-summary__failed-toggle"
                  aria-expanded={failedExpanded}
                  onClick={() => setFailedExpanded((prev) => !prev)}
                >
                  {failedExpanded ? '▾' : '▸'} {failedOutcomes.length} failure reason{failedOutcomes.length !== 1 ? 's' : ''}
                </button>
                {failedExpanded && (
                  <ul className="onboarding-batch-summary__failed-list">
                    {failedOutcomes.map((o) => (
                      <li key={o.proposalId} className="onboarding-batch-summary__failed-item">
                        <span className="onboarding-batch-summary__failed-proposal">{o.proposalId}</span>
                        {o.reason && (
                          <span className="onboarding-batch-summary__failed-reason"> — {o.reason}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {submitSuccessCount !== null && (
              <AppBanner variant="success">
                {submitSuccessCount} rule{submitSuccessCount !== 1 ? 's' : ''} submitted for approval.
              </AppBanner>
            )}

            {submitError && (
              <AppBanner variant="error">{submitError}</AppBanner>
            )}
          </>
        )}
      </AppStack>
    </AppModal>
  )
}

export default OnboardingBatchSummary
