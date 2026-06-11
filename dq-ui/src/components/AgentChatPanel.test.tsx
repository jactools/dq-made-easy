/** @vitest-environment jsdom */

import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { AgentChatPanel } from './AgentChatPanel'

const mockRunAgent = vi.fn()

vi.mock('../hooks/useAgentHarness', () => ({
  useAgentHarness: () => ({
    agents: [
      { id: 'general', name: 'General DQ Assistant', description: 'General helper', capabilities: [], tools: [], status: 'available' },
      { id: 'dq_rule', name: 'Rule Engineer Agent', description: 'Rule helper', capabilities: [], tools: [], status: 'available' },
    ],
    loadingAgents: false,
    error: null,
    runAgent: mockRunAgent,
  }),
}))

describe('AgentChatPanel', () => {
  beforeEach(() => {
    mockRunAgent.mockReset()
  })

  it('runs the selected agent and renders the returned response', async () => {
    mockRunAgent.mockResolvedValue({
      response: 'I can help with that.',
      session_id: 'agent_123',
      tool_calls: [{ tool_name: 'dq_rule', parameters: { prompt: 'draft rule' }, result: {}, duration_ms: 1, success: true }],
      metadata: {},
    })

    render(<AgentChatPanel />)

    fireEvent.change(screen.getByLabelText(/prompt/i), { target: { value: 'Draft a validation rule for email.' } })
    fireEvent.click(screen.getByRole('button', { name: /run agent/i }))

    expect(mockRunAgent).toHaveBeenCalledWith({
      prompt: 'Draft a validation rule for email.',
      agentType: 'general',
    })

    expect(await screen.findByText('I can help with that.')).toBeTruthy()
    expect(screen.getByText('agent_123')).toBeTruthy()
  })
})
