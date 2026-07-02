import React, { useEffect, useMemo, useState } from 'react'
import { useSettings } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { AppIcon, AppPageShell, AppSelect } from './app-primitives'
import { PrimaryButton, SecondaryButton } from './Button'
import { AdminPageHeader } from './AdminPageHeader'
import { DEFAULT_STYLE_PACKAGE, getStylePackageOptions, type StyleRegistryStyle } from '../contexts/styleThemeCatalog'
import type { StylePackageName, IconProviderName } from '../types/settings'
import { createSupportReferenceId, formatSupportReferenceId } from '../utils/supportReference'
import { DEFAULT_ICON_PROVIDER, getAppIconProviderOptions, type RegistryComponentBundle } from './app-primitives/appIconProviders'
import { IconGallery } from './IconGallery'
import './Settings.css'

type UiRegistryView = {
  source: string
  version: string
  cache_ttl_seconds?: number
  styles?: readonly StyleRegistryStyle[]
  component_bundles?: readonly RegistryComponentBundle[]
  metadata?: Record<string, unknown>
}

const formatRegistryComponentBundle = (bundle: RegistryComponentBundle): string => {
  const details = [bundle.label, bundle.adapter, bundle.fallback ? `fallback=${bundle.fallback}` : null]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
  return details.length > 0 ? `${bundle.id} (${details.join(', ')})` : bundle.id
}

export const UIRegistryAdmin: React.FC = () => {
  const settings = useSettings()
  const [uiRegistryView, setUiRegistryView] = useState<UiRegistryView | null>(null)
  const [selectedIconProvider, setSelectedIconProvider] = useState<IconProviderName>(settings.applicationSettings?.iconProvider || DEFAULT_ICON_PROVIDER)
  const [selectedStylePackage, setSelectedStylePackage] = useState<StylePackageName>(settings.applicationSettings?.stylePackage || DEFAULT_STYLE_PACKAGE)
  const [hasChanges, setHasChanges] = useState(false)
  const [saveStatusMessage, setSaveStatusMessage] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveErrorReferenceId, setSaveErrorReferenceId] = useState<string | null>(null)

  useEffect(() => {
    setSelectedIconProvider(settings.applicationSettings?.iconProvider || DEFAULT_ICON_PROVIDER)
    setSelectedStylePackage(settings.applicationSettings?.stylePackage || DEFAULT_STYLE_PACKAGE)
  }, [settings.applicationSettings?.iconProvider, settings.applicationSettings?.stylePackage])

  useEffect(() => {
    if (!settings.applicationSettings?.apiBaseUrl) {
      setUiRegistryView(null)
      return
    }

    let cancelled = false

    const loadUiRegistry = async () => {
      try {
        const apiBase = toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)
        const token = getAuthToken()
        const response = await fetch(`${apiBase}/ui-registry`, {
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        })

        if (!response.ok || cancelled) {
          return
        }

        const view = (await response.json()) as UiRegistryView
        if (!cancelled) {
          setUiRegistryView(view)
        }
      } catch {
        if (!cancelled) {
          setUiRegistryView(null)
        }
      }
    }

    void loadUiRegistry()

    return () => {
      cancelled = true
    }
  }, [settings.applicationSettings?.apiBaseUrl])

  const iconProviderOptions = useMemo(
    () => getAppIconProviderOptions(selectedIconProvider, uiRegistryView?.component_bundles ?? null),
    [selectedIconProvider, uiRegistryView?.component_bundles],
  )

  const stylePackageOptions = useMemo(
    () => getStylePackageOptions(selectedStylePackage, uiRegistryView?.styles ?? null),
    [selectedStylePackage, uiRegistryView?.styles],
  )

  const handleSave = async () => {
    try {
      setSaveError(null)
      setSaveErrorReferenceId(null)
      setSaveStatusMessage(null)

      await settings.updateSettings({
        category: 'application',
        data: {
          apiBaseUrl: settings.applicationSettings?.apiBaseUrl,
          iconProvider: selectedIconProvider,
          stylePackage: selectedStylePackage,
        },
      })

      setHasChanges(false)
      setSaveStatusMessage('UI registry settings saved successfully')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to save UI registry settings.'
      setSaveError(message)
      setSaveErrorReferenceId(createSupportReferenceId())
    }
  }

  const handleCancel = () => {
    setSelectedIconProvider(settings.applicationSettings?.iconProvider || DEFAULT_ICON_PROVIDER)
    setSelectedStylePackage(settings.applicationSettings?.stylePackage || DEFAULT_STYLE_PACKAGE)
    setHasChanges(false)
    setSaveError(null)
    setSaveErrorReferenceId(null)
    setSaveStatusMessage(null)
  }

  if (!settings.applicationSettings) {
    return (
      <AppPageShell className="settings-container">
        <AdminPageHeader title="UI Registry" subtitle="Loading UI registry settings..." />
        <div className="settings-content">
          <div className="settings-panel" />
        </div>
      </AppPageShell>
    )
  }

  return (
    <AppPageShell className="settings-container">
      <AdminPageHeader
        title="UI Registry"
        subtitle="Manage style packages, component bundles, and the icon gallery"
        actions={
          hasChanges ? (
            <>
              <SecondaryButton onClick={handleCancel}>Cancel</SecondaryButton>
              <PrimaryButton onClick={handleSave}>Save Changes</PrimaryButton>
            </>
          ) : undefined
        }
      />

      <div className="settings-content">
        {(saveError || saveStatusMessage) && (
          <div className={`settings-message ${saveError ? 'error' : 'success'}`} role="status" aria-live="polite">
            <AppIcon name={saveError ? 'exclamation-circle' : 'check-circle'} />
            <span>
              {saveError || saveStatusMessage}
              {saveErrorReferenceId && saveError && (
                <>
                  <br />
                  {formatSupportReferenceId(saveErrorReferenceId)}
                </>
              )}
            </span>
            {saveError && (
              <button onClick={() => { setSaveError(null); setSaveErrorReferenceId(null) }}>
                Dismiss
              </button>
            )}
          </div>
        )}

        <div className="settings-panel">
          <div className="settings-form">
            <div className="settings-section">
              <h3>Registry Selections</h3>

              <div className="form-group">
                <AppSelect
                  id="stylePackage"
                  label="Style package"
                  value={selectedStylePackage}
                  onChange={(value) => {
                    setSelectedStylePackage(value)
                    setHasChanges(true)
                  }}
                  options={stylePackageOptions.map((option) => ({
                    value: option.value,
                    label: option.label,
                  }))}
                />
                <p className="info-text">Controls which stylesheet the app loads at runtime.</p>
              </div>

              <div className="form-group">
                <AppSelect
                  id="iconProvider"
                  label="Icon provider"
                  value={selectedIconProvider}
                  onChange={(value) => {
                    setSelectedIconProvider(value as IconProviderName)
                    setHasChanges(true)
                  }}
                  options={iconProviderOptions.map((option) => ({
                    value: option.value,
                    label: option.label,
                  }))}
                />
                <p className="info-text">Controls the active icon provider used by the app-owned icon seam.</p>
              </div>
            </div>

            <div className="settings-section">
              <h3>UI Registry Snapshot</h3>
              {uiRegistryView ? (
                <>
                  <p className="info-text">
                    Source: {uiRegistryView.source} | Version: {uiRegistryView.version} | Styles: {uiRegistryView.styles?.length || 0} | Component bundles: {uiRegistryView.component_bundles?.length || 0}
                  </p>
                  {uiRegistryView.styles?.length ? (
                    <p className="info-text">
                      Styles: {uiRegistryView.styles.map((style) => `${style.id}${style.label ? ` (${style.label})` : ''}`).join(', ')}
                    </p>
                  ) : null}
                  {uiRegistryView.component_bundles?.length ? (
                    <p className="info-text">
                      Component bundles: {uiRegistryView.component_bundles.map((bundle) => formatRegistryComponentBundle(bundle)).join(', ')}
                    </p>
                  ) : null}
                  {uiRegistryView.metadata?.storage_table && (
                    <p className="info-text">Stored in {String(uiRegistryView.metadata.storage_table)}</p>
                  )}
                </>
              ) : (
                <p className="info-text">No UI registry snapshot is currently loaded.</p>
              )}
            </div>

            <div className="settings-section">
              <h3>Icon Gallery</h3>
              <IconGallery />
            </div>
          </div>
        </div>
      </div>
    </AppPageShell>
  )
}
