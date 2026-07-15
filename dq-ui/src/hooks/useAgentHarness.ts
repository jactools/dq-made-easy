import { useCallback, useEffect, useState } from 'react'
import { getAuthToken } from '../contexts/AuthContext'
import { normalizeApiBaseUrl, toApiGroupV1Base } from '../config/api'
import { useSettings } from './useContexts'

export interface AgentCapabilitySummary {
  id: string
  name: string
  description: string
  capabilities: string[]
  tools: string[]
  status: string
}

export interface ToolCallSummary {
  tool_name: string
  parameters: Record<string, unknown>
  result: Record<string, unknown>
  duration_ms: number
  success: boolean
  error?: string | null
}

export interface AgentRunResponse {
  response: string
  session_id: string
  tool_calls: ToolCallSummary[]
  metadata: Record<string, unknown>
  error?: string | null
}

export const useAgentHarness = () => {
  const settings = useSettings()
  const [agents, setAgents] = useState<AgentCapabilitySummary[]>([])
  const [loadingAgents, setLoadingAgents] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const apiBaseUrl = normalizeApiBaseUrl(settings.applicationSettings?.apiBaseUrl)
  const agentApiBase = toApiGroupV1Base('agent', settings.applicationSettings?.apiBaseUrl)

  const buildAuthHeaders = useCallback((includeJsonContentType = false): HeadersInit => {
    const token = getAuthToken()
    if (!token) {
      return includeJsonContentType ? { 'Content-Type': 'application/json' } : {}
    }

    return includeJsonContentType
      ? {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        }
      : {
          Authorization: `Bearer ${token}`,
        }
  }, [])

  const listAgents = useCallback(async () => {
    setLoadingAgents(true)
    setError(null)

    try {
      const response = await fetch(`${agentApiBase}/agents`, {
        method: 'GET',
        headers: buildAuthHeaders(),
      })

      if (!response.ok) {
        throw new Error(`Unable to load agent catalog (${response.status})`)
      }

      const payload = (await response.json()) as AgentCapabilitySummary[]
      setAgents(Array.isArray(payload) ? payload : [])
      return payload
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Unable to load agent catalog.'
      setError(message)
      return []
    } finally {
      setLoadingAgents(false)
    }
  }, [agentApiBase, buildAuthHeaders])

  const runAgent = useCallback(async (request: {
    prompt: string
    agentType: string
    sessionId?: string
    context?: Record<string, unknown>
  }): Promise<AgentRunResponse | null> => {
    setError(null)

    try {
      const response = await fetch(`${agentApiBase}/run`, {
        method: 'POST',
        headers: buildAuthHeaders(true),
        body: JSON.stringify({
          prompt: request.prompt,
          agent_type: request.agentType,
          session_id: request.sessionId ?? null,
          context: request.context ?? {},
        }),
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        const message = payload?.detail || payload?.message || `Agent request failed (${response.status})`
        throw new Error(message)
      }

      return (await response.json()) as AgentRunResponse
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : 'Unable to run the selected agent.'
      setError(message)
      return null
    }
  }, [agentApiBase, buildAuthHeaders])

  useEffect(() => {
    void listAgents()
  }, [listAgents])

  return {
    apiBaseUrl,
    agents,
    loadingAgents,
    error,
    listAgents,
    runAgent,
  }
}
