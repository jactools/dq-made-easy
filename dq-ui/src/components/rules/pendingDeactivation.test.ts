import { describe, expect, it } from 'vitest'
import { collectPendingDeactivationRuleIds } from './pendingDeactivation'

describe('pendingDeactivation helpers', () => {
  it('keeps the badge when the latest deactivation request is pending', () => {
    const result = collectPendingDeactivationRuleIds(
      [
        { id: 'a1', ruleId: 'rule-from-approval', requesterId: 'u1', requestedAt: '2026-04-12T00:00:00Z', status: 'approved', workspaceId: 'ws-a', requestType: 'deactivation' },
        { id: 'a2', ruleId: 'rule-from-approval', requesterId: 'u2', requestedAt: '2026-04-12T01:00:00Z', status: 'pending', workspaceId: 'ws-a', requestType: 'deactivation' },
        { id: 'a3', ruleId: 'rule-ignored', requesterId: 'u3', requestedAt: '2026-04-12T00:30:00Z', status: 'pending', workspaceId: 'ws-a', requestType: 'activation' },
      ] as any,
    )

    expect(result).toEqual({
      'rule-from-approval': true,
    })
  })

  it('ignores older pending requests when a later deactivation has already been reviewed', () => {
    const result = collectPendingDeactivationRuleIds(
      [
        { id: 'a1', ruleId: 'rule-from-approval', requesterId: 'u1', requestedAt: '2026-04-12T00:00:00Z', status: 'pending', workspaceId: 'ws-a', requestType: 'deactivation' },
        { id: 'a2', ruleId: 'rule-from-approval', requesterId: 'u2', requestedAt: '2026-04-12T01:00:00Z', status: 'approved', workspaceId: 'ws-a', requestType: 'deactivation' },
      ] as any,
    )

    expect(result).toEqual({})
  })
})
