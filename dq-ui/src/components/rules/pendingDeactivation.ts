import type { RuleApproval } from '../../types/rules'

const normalizeRuleId = (value: unknown): string => String(value || '').trim()

const parseApprovalTimestamp = (value: unknown): number => {
  const text = String(value || '').trim()
  if (!text) {
    return Number.NEGATIVE_INFINITY
  }

  const parsed = Date.parse(text)
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY
}

export const collectPendingDeactivationRuleIds = (
  approvals: RuleApproval[],
): Record<string, boolean> => {
  const latestDeactivationByRule = new Map<string, { timestamp: number; approvalId: string; isPending: boolean }>()

  for (const approval of approvals) {
    if (approval.requestType !== 'deactivation') {
      continue
    }

    const ruleId = normalizeRuleId(approval.ruleId)
    if (!ruleId) {
      continue
    }

    const timestamp = parseApprovalTimestamp((approval as any).requestedAt ?? (approval as any).requested_at)
    const approvalId = normalizeRuleId(approval.id)
    const current = latestDeactivationByRule.get(ruleId)
    if (!current || timestamp > current.timestamp || (timestamp === current.timestamp && approvalId >= current.approvalId)) {
      latestDeactivationByRule.set(ruleId, {
        timestamp,
        approvalId,
        isPending: approval.status === 'pending',
      })
    }
  }

  return Array.from(latestDeactivationByRule.entries()).reduce<Record<string, boolean>>((acc, [ruleId, entry]) => {
    if (entry.isPending) {
      acc[ruleId] = true
    }
    return acc
  }, {})
}