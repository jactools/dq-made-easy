import React from 'react'
import { useAuth } from '../hooks/useKeycloak'
import { AppSelect } from './app-primitives'

// Workspace display names mapping
const workspaceNames: Record<string, string> = {
  'retail-banking': 'Retail Banking',
  'corporate-banking': 'Corporate Banking',
  'investment-banking': 'Investment Banking',
  'risk-compliance': 'Risk & Compliance',
  'treasury': 'Treasury',
  'wealth-management': 'Wealth Management',
  'payments': 'Payments',
  'operations': 'Operations',
  'technology': 'Technology & IT',
  'human-resources': 'Human Resources',
  'global': 'Global',
}

export const getWorkspaceDisplayName = (workspaceId: string): string => {
  const normalizedWorkspaceId = String(workspaceId || '').trim()
  if (!normalizedWorkspaceId) {
    return ''
  }

  return workspaceNames[normalizedWorkspaceId] || normalizedWorkspaceId
}

interface WorkspaceSelectorProps {
  onWorkspaceSelected?: (workspaceId: string) => void
}

export const WorkspaceSelector: React.FC<WorkspaceSelectorProps> = ({ onWorkspaceSelected }) => {
  const auth = useAuth()

  // Only show workspace selector if user has more than one workspace
  if (!auth.user || auth.user.workspaceRoles.length <= 1) {
    return null
  }

  const handleWorkspaceChange = (value: string) => {
    auth.switchWorkspace(value)
    onWorkspaceSelected?.(value)
  }

  return (
    <div className="workspace-selector">
      <AppSelect
        id="workspace-select"
        label="Workspace:"
        value={auth.currentWorkspaceId || ''}
        onChange={handleWorkspaceChange}
        options={auth.user.workspaceRoles.map(wr => ({
          value: wr.workspaceId,
          label: `${getWorkspaceDisplayName(wr.workspaceId)} (${wr.role})`,
        }))}
      />
    </div>
  )
}
