import React, { useEffect, useState } from 'react'
import { toApiGroupV1Base } from '../config/api'
import { useVersionCatalog } from '../hooks/useVersionCatalog'
import { useSettings } from '../hooks/useContexts'
import { AppBanner, AppButton, AppIcon, AppModal, AppPanel, AppStack } from './app-primitives'

declare const __BUILD_DATE__: string

interface SystemInfo {
  api: {
    version: string
    buildDate: string
  }
  database: {
    schemaVersion: string
    schemaUpdated: string | null
    schemaGitCommit: string | null
  }
  deployment: {
    deploymentVerificationDate: string | null
    deploymentVerifiedBy: string | null
  }
  versions: {
    apps: {
      ui: string
      api: string
    }
    components: Record<string, string>
  }
}

interface VersionInfoModalProps {
  isOpen: boolean
  onClose: () => void
}

const formatDateTimeValue = (value: string | null): string => {
  if (!value) {
    return 'Not set'
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleString()
}

const formatDateValue = (value: string | null): string => {
  if (!value) {
    return 'Not set'
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleDateString()
}

export const VersionInfoModal: React.FC<VersionInfoModalProps> = ({ isOpen, onClose }) => {
  const settings = useSettings()
  const { versionCatalog } = useVersionCatalog(isOpen)
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen) {
      fetchSystemInfo()
    }
  }, [isOpen])

  const fetchSystemInfo = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`${toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)}/system-info`)
      
      if (!response.ok) {
        throw new Error('Failed to fetch system information')
      }

      const data = await response.json()

      setSystemInfo({
        api: data.api,
        database: data.database,
        deployment: data.deployment,
        versions: {
          apps: {
            ui: String(data?.versions?.apps?.ui || versionCatalog.apps.ui || 'unknown'),
            api: String(data?.versions?.apps?.api || data?.api?.version || 'unknown')
          },
          components: typeof data?.versions?.components === 'object' && data?.versions?.components !== null
            ? data.versions.components
            : versionCatalog.components
        }
      })
    } catch (err) {
      console.error('Error fetching system info:', err)
      setError('Unable to retrieve complete system information')
      
      // Provide at least UI version info
      setSystemInfo({
        api: {
          version: versionCatalog.apps.api || 'unavailable',
          buildDate: 'unavailable'
        },
        database: {
          schemaVersion: 'unavailable',
          schemaUpdated: null,
          schemaGitCommit: null,
        },
        deployment: {
          deploymentVerificationDate: null,
          deploymentVerifiedBy: null,
        },
        versions: {
          apps: {
            ui: versionCatalog.apps.ui || 'unknown',
            api: versionCatalog.apps.api || 'unknown'
          },
          components: versionCatalog.components
        }
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <AppModal
      isOpen={isOpen}
      onClose={onClose}
      title="System Information"
      size="md"
      dialogClassName="version-modal"
      bodyClassName="version-modal-body"
      footerClassName="version-modal-footer"
      footer={<AppButton variant="primary" type="button" onClick={onClose}>Close</AppButton>}
    >
      {loading ? (
        <AppPanel as="section" tone="muted" className="loading-state" bodyClassName="loading-state__body">
          <AppStack gap="sm" className="loading-state__stack">
            <div className="spinner" />
            <p>Loading system information...</p>
          </AppStack>
        </AppPanel>
      ) : (
        <>
          {error && (
            <AppBanner variant="error">
              <AppIcon name="exclamation-circle" />
              <span>{error}</span>
            </AppBanner>
          )}

          {systemInfo && (
            <AppStack gap="lg" className="version-sections">
              <AppPanel
                title={<span className="version-section-title"><AppIcon name="info-circle" />User Interface</span>}
                titleAs="h3"
                bodyClassName="version-details"
              >
                <div className="version-row">
                  <span className="version-label">Version:</span>
                  <span className="version-value">{systemInfo.versions.apps.ui}</span>
                </div>
                <div className="version-row">
                  <span className="version-label">Build Date:</span>
                  <span className="version-value">{__BUILD_DATE__}</span>
                </div>
              </AppPanel>

              <AppPanel
                title={<span className="version-section-title"><AppIcon name="info-circle" />API Backend</span>}
                titleAs="h3"
                bodyClassName="version-details"
              >
                <div className="version-row">
                  <span className="version-label">Version:</span>
                  <span className="version-value">{systemInfo.versions.apps.api || systemInfo.api.version}</span>
                </div>
                <div className="version-row">
                  <span className="version-label">Build Date:</span>
                  <span className="version-value">{systemInfo.api.buildDate}</span>
                </div>
              </AppPanel>

              <AppPanel
                title={<span className="version-section-title"><AppIcon name="database" />Database</span>}
                titleAs="h3"
                bodyClassName="version-details"
              >
                <div className="version-row">
                  <span className="version-label">Schema Version:</span>
                  <span className="version-value">{systemInfo.database.schemaVersion}</span>
                </div>
                {systemInfo.database.schemaUpdated && (
                  <div className="version-row">
                    <span className="version-label">Last Updated:</span>
                    <span className="version-value">
                      {formatDateValue(systemInfo.database.schemaUpdated)}
                    </span>
                  </div>
                )}
                {systemInfo.database.schemaGitCommit && systemInfo.database.schemaGitCommit !== 'initial' && (
                  <div className="version-row">
                    <span className="version-label">Git Commit:</span>
                    <span className="version-value" title={systemInfo.database.schemaGitCommit}>
                      {systemInfo.database.schemaGitCommit}
                    </span>
                  </div>
                )}
              </AppPanel>

              <AppPanel
                title={<span className="version-section-title"><AppIcon name="check-circle" />Deployment Verification</span>}
                titleAs="h3"
                bodyClassName="version-details"
              >
                <div className="version-row">
                  <span className="version-label">Verification Date:</span>
                  <span className="version-value">
                    {formatDateTimeValue(systemInfo.deployment.deploymentVerificationDate)}
                  </span>
                </div>
                <div className="version-row">
                  <span className="version-label">Verified By:</span>
                  <span className="version-value">{systemInfo.deployment.deploymentVerifiedBy || 'Not set'}</span>
                </div>
              </AppPanel>

              {Object.keys(systemInfo.versions.components || {}).length > 0 && (
                <AppPanel
                  title={<span className="version-section-title"><AppIcon name="package" />Component Versions</span>}
                  titleAs="h3"
                  bodyClassName="version-details"
                >
                  {Object.entries(systemInfo.versions.components).map(([componentName, componentVersion]) => (
                    <div className="version-row" key={componentName}>
                      <span className="version-label">{componentName}:</span>
                      <span className="version-value">{componentVersion}</span>
                    </div>
                  ))}
                </AppPanel>
              )}
            </AppStack>
          )}
        </>
      )}
    </AppModal>
  )
}
