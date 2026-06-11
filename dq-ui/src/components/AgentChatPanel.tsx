import React, { useEffect, useMemo, useState } from 'react'
import { Button } from './Button'
import { useAgentHarness, type AgentRunResponse } from '../hooks/useAgentHarness'

const formatAgentLabel = (agentType: string) => {
  return agentType
    .replace(/^dq_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

type AgentChatPanelProps = {
  defaultAgentType?: string
  defaultPrompt?: string
  title?: string
  description?: string
}

export const AgentChatPanel: React.FC<AgentChatPanelProps> = ({
  defaultAgentType = 'general',
  defaultPrompt = '',
  title = 'Try the dq-llm agent harness',
  description = 'Send a prompt to the agent runtime directly and review the response, sessions, and tool calls returned by the dq-llm service.',
}) => {
  const { agents, loadingAgents, error, runAgent } = useAgentHarness()
  const [prompt, setPrompt] = useState(defaultPrompt)
  const [selectedAgentType, setSelectedAgentType] = useState(defaultAgentType)
  const [response, setResponse] = useState<AgentRunResponse | null>(null)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    setPrompt(defaultPrompt)
  }, [defaultPrompt])

  useEffect(() => {
    setSelectedAgentType(defaultAgentType)
  }, [defaultAgentType])

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentType) ?? agents[0] ?? null,
    [agents, selectedAgentType],
  )

  const handleRunAgent = async () => {
    const trimmedPrompt = prompt.trim()
    if (!trimmedPrompt) {
      return
    }

    setRunning(true)
    setResponse(null)

    const result = await runAgent({
      prompt: trimmedPrompt,
      agentType: selectedAgentType,
    })

    setRunning(false)
    if (result) {
      setResponse(result)
    }
  }

  return (
    <section className="agent-chat-panel" aria-labelledby="agent-chat-title">
      <div className="ai-recommendation-header">
        <div>
          <p className="policy-documents-eyebrow">Agent chat</p>
          <h3 id="agent-chat-title">{title}</h3>
          <p>{description}</p>
        </div>
        <div className="ai-recommendation-workspace-callout">
          <span className="ai-recommendation-workspace-label">Status</span>
          <strong>{loadingAgents ? 'Loading agents…' : `${agents.length} agents available`}</strong>
        </div>
      </div>

      <div className="agent-chat-grid">
        <div className="agent-chat-card">
          <label className="ai-recommendation-field" htmlFor="agent-chat-agent">
            <span className="ai-recommendation-label">Agent</span>
            <select
              id="agent-chat-agent"
              className="agent-chat-select"
              value={selectedAgentType}
              onChange={(event) => setSelectedAgentType(event.target.value)}
            >
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                </option>
              ))}
              {!agents.length && <option value="general">General DQ Assistant</option>}
            </select>
          </label>

          {selectedAgent && (
            <p className="agent-chat-description">{selectedAgent.description}</p>
          )}

          <label className="ai-recommendation-field" htmlFor="agent-chat-prompt">
            <span className="ai-recommendation-label">Prompt</span>
            <textarea
              id="agent-chat-prompt"
              className="ai-recommendation-textarea"
              rows={5}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Ask the agent to inspect metadata, draft rules, or explain governance actions."
            />
          </label>

          <div className="ai-recommendation-actions">
            <Button
              type="button"
              onClick={() => void handleRunAgent()}
              disabled={running || !prompt.trim()}
            >
              {running ? 'Running…' : 'Run agent'}
            </Button>
          </div>

          {error && (
            <div className="ai-recommendation-alert error" role="alert">{error}</div>
          )}
        </div>

        <div className="agent-chat-card">
          <h4>Agent response</h4>
          {response ? (
            <>
              <p className="agent-chat-response">{response.response}</p>
              <div className="agent-chat-meta-row">
                <span><strong>Session:</strong> {response.session_id}</span>
                <span><strong>Agent:</strong> {formatAgentLabel(selectedAgentType)}</span>
              </div>
              {response.tool_calls?.length ? (
                <div className="agent-chat-tool-list">
                  {response.tool_calls.map((toolCall, index) => (
                    <article key={`${toolCall.tool_name}-${index}`} className="agent-chat-tool-card">
                      <strong>{toolCall.tool_name}</strong>
                      <p>{toolCall.success ? 'Tool call completed successfully.' : 'Tool call returned an error.'}</p>
                      <pre>{JSON.stringify(toolCall.parameters, null, 2)}</pre>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="agent-chat-empty">No tool calls were required for this interaction.</p>
              )}
            </>
          ) : (
            <p className="agent-chat-empty">Run a prompt to see the dq-llm response, tool calls, and session details here.</p>
          )}
        </div>
      </div>
    </section>
  )
}
