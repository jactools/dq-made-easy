import React from 'react'
import { useRules, useAuth } from '../hooks/useContexts'
import { DataQualityMetrics } from './DataQualityMetrics'
import './Metrics.css'

export const Metrics: React.FC = () => {
  const { rules } = useRules()
  const auth = useAuth()

  // Filter rules for current workspace, matching Dashboard behavior
  const workspaceRules = React.useMemo(() => {
    return rules.filter(r => r.workspace === auth.currentWorkspaceId)
  }, [rules, auth.currentWorkspaceId])

  const handleRuleClick = (ruleId: string) => {
    console.log('Navigating to rule:', ruleId)
    // In a full implementation, would navigate to rule details
  }

  return (
    <div className="metrics-container">
      <DataQualityMetrics 
        rules={workspaceRules} 
        onRuleClick={handleRuleClick}
      />
    </div>
  )
}
