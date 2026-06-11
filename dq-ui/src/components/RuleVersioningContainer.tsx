import React, { useState } from 'react'
import { useSettings } from '../hooks/useContexts'
import { RuleVersion } from '../types/rules'
import { RuleVersionHistory } from './RuleVersionHistory'
import { RuleVersionDetails } from './RuleVersionDetails'
import { RuleVersionComparison } from './RuleVersionComparison'
import { RollbackConfirmDialog } from './RollbackConfirmDialog'
import { VersionStatistics } from './VersionStatistics'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'

interface RuleVersioningContainerProps {
  ruleId: string
  ruleName: string
  currentVersion?: RuleVersion
  onRollbackComplete?: (newVersionId: string) => void
}

export const RuleVersioningContainer: React.FC<RuleVersioningContainerProps> = ({
  ruleId,
  ruleName,
  currentVersion,
  onRollbackComplete,
}) => {
  const settings = useSettings()
  const apiBaseUrl = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  const [resolvedCurrentVersion, setResolvedCurrentVersion] = useState<RuleVersion | null>(currentVersion || null)
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)
  const [selectedVersion, setSelectedVersion] = useState<RuleVersion | null>(null)
  const [compareVersion1, setCompareVersion1] = useState<RuleVersion | null>(null)
  const [compareVersion2, setCompareVersion2] = useState<RuleVersion | null>(null)
  const [rollbackVersion, setRollbackVersion] = useState<RuleVersion | null>(null)
  
  const [showVersionDetails, setShowVersionDetails] = useState(false)
  const [showComparison, setShowComparison] = useState(false)
  const [showRollbackDialog, setShowRollbackDialog] = useState(false)

  const effectiveCurrentVersion = currentVersion || resolvedCurrentVersion

  // Handle version selection from history
  const handleVersionSelect = (version: RuleVersion) => {
    setSelectedVersion(version)
    setShowVersionDetails(true)
  }

  // Handle compare request from history
  const handleCompareVersions = (v1: RuleVersion, v2: RuleVersion) => {
    setCompareVersion1(v1)
    setCompareVersion2(v2)
    setShowComparison(true)
  }

  // Handle compare with current from version details
  const handleCompareWithCurrent = (version: RuleVersion) => {
    if (effectiveCurrentVersion) {
      setCompareVersion1(effectiveCurrentVersion)
      setCompareVersion2(version)
      setShowVersionDetails(false)
      setShowComparison(true)
    }
  }

  // Handle rollback initiation
  const handleRollbackRequest = (targetVersion: RuleVersion) => {
    setRollbackVersion(targetVersion)
    setShowVersionDetails(false)
    setShowRollbackDialog(true)
  }

  // Execute rollback
  const handleRollbackConfirm = async (reason: string) => {
    if (!rollbackVersion) return

    try {
      const token = getAuthToken()
      const response = await fetch(`${apiBaseUrl}/rules/${ruleId}/versions/rollback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          toVersionId: rollbackVersion.id,
          reason,
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.message || 'Rollback failed')
      }

      const result = await response.json()
      const newVersionId = result.newVersionId || result.data?.newVersionId || ''
      
      setShowRollbackDialog(false)
      setRollbackVersion(null)
      
      // Notify parent component
      if (onRollbackComplete) {
        onRollbackComplete(newVersionId)
      }
      setHistoryRefreshKey(prev => prev + 1)
    } catch (error) {
      throw error // Let the dialog handle the error display
    }
  }

  return (
    <div className="rule-versioning-container">
      <RuleVersionHistory
        key={`${ruleId}-${historyRefreshKey}`}
        ruleId={ruleId}
        ruleName={ruleName}
        onVersionSelect={handleVersionSelect}
        onCompareVersions={handleCompareVersions}
        onRollback={handleRollbackRequest}
        onCurrentVersionDetected={setResolvedCurrentVersion}
      />

      <VersionStatistics ruleId={ruleId} refreshKey={historyRefreshKey} />

      <RuleVersionDetails
        version={selectedVersion}
        isOpen={showVersionDetails}
        onClose={() => {
          setShowVersionDetails(false)
          setSelectedVersion(null)
        }}
        onRollback={handleRollbackRequest}
        onCompareWithCurrent={handleCompareWithCurrent}
        isCurrentVersion={selectedVersion?.id === effectiveCurrentVersion?.id}
      />

      {compareVersion1 && compareVersion2 && (
        <RuleVersionComparison
          version1={compareVersion1}
          version2={compareVersion2}
          isOpen={showComparison}
          onClose={() => {
            setShowComparison(false)
            setCompareVersion1(null)
            setCompareVersion2(null)
          }}
        />
      )}

      <RollbackConfirmDialog
        isOpen={showRollbackDialog}
        ruleName={ruleName}
        targetVersion={rollbackVersion}
        currentVersion={effectiveCurrentVersion || null}
        onConfirm={handleRollbackConfirm}
        onCancel={() => {
          setShowRollbackDialog(false)
          setRollbackVersion(null)
        }}
      />
    </div>
  )
}
