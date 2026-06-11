import { useEffect, useMemo, useState } from 'react'
import { toApiGroupV1Base } from '../../config/api'

interface StatusModelResponse {
  entity: string
  statuses?: GovernanceStatusValue[]
  transitions?: GovernanceStatusTransition[]
  allowedTransitionsByStatus?: Record<string, string[]>
}

export interface GovernanceStatusValue {
  value: string
  label: string
  description?: string | null
  isInitial?: boolean
  isTerminal?: boolean
}

export interface GovernanceStatusTransition {
  fromStatus: string
  toStatus: string
  label: string
  requiredAnyScopes: string[]
}

export interface GovernanceStatusModel {
  entity: string
  statuses: GovernanceStatusValue[]
  transitions: GovernanceStatusTransition[]
  allowedTransitionsByStatus: Record<string, string[]>
}

interface UseRuleStatusGovernanceParams {
  authToken: string | null
  apiBaseUrl?: string
  entity?: string
}

export const useRuleStatusGovernance = ({ authToken, apiBaseUrl, entity = 'rule' }: UseRuleStatusGovernanceParams) => {
  const [allowedTransitionsByStatus, setAllowedTransitionsByStatus] = useState<Record<string, string[]> | null>(null)
  const [statusModel, setStatusModel] = useState<GovernanceStatusModel | null>(null)

  useEffect(() => {
    const loadStatusModel = async () => {
      if (!authToken) {
        setAllowedTransitionsByStatus(null)
        setStatusModel(null)
        return
      }

      try {
        const response = await fetch(`${toApiGroupV1Base('rulebuilder', apiBaseUrl)}/governance/status-models/${encodeURIComponent(entity)}`, {
          headers: {
            Authorization: `Bearer ${authToken}`,
          },
        })

        if (!response.ok) {
          setAllowedTransitionsByStatus(null)
          setStatusModel(null)
          return
        }

        const body = (await response.json()) as StatusModelResponse
        const transitions = body?.allowedTransitionsByStatus
        const statuses = Array.isArray(body?.statuses) ? body.statuses : []
        const transitionList = Array.isArray(body?.transitions) ? body.transitions : []
        const allowed = transitions && typeof transitions === 'object' ? transitions : {}

        setAllowedTransitionsByStatus(allowed)
        setStatusModel({
          entity: String(body?.entity || entity),
          statuses,
          transitions: transitionList,
          allowedTransitionsByStatus: allowed,
        })
      } catch {
        setAllowedTransitionsByStatus(null)
        setStatusModel(null)
      }
    }

    void loadStatusModel()
  }, [apiBaseUrl, authToken, entity])

  const isLoaded = useMemo(() => allowedTransitionsByStatus !== null, [allowedTransitionsByStatus])

  return {
    allowedTransitionsByStatus,
    statusModel,
    isLoaded,
  }
}
