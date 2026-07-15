import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useSettings } from '../hooks/useContexts'
import { getAuthToken } from '../contexts/AuthContext'
import { toApiGroupV1Base } from '../config/api'
import { AppIcon, AppInput, AppPageShell, AppSelect } from './app-primitives'
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

type UiRegistryAssetKind = 'style' | 'component'
type UiRegistryAssetImportMode = 'url' | 'upload'
type UiRegistryAssetImportState = {
  kind: UiRegistryAssetKind
  mode: UiRegistryAssetImportMode
} | null

type UiRegistryAssetImportResponse = {
  public_url?: string
  file_name?: string
}

type UiRegistryAssetErrorResponse = {
  detail?: string | { message?: string }
  message?: string
}

type UiRegistryAssetUploadFeedbackTone = 'progress' | 'success' | 'error'

type UiRegistryAssetUploadFeedback = {
  kind: UiRegistryAssetKind
  tone: UiRegistryAssetUploadFeedbackTone
  message: string
} | null

const formatRegistryComponentBundle = (bundle: RegistryComponentBundle): string => {
  const details = [bundle.label, bundle.adapter, bundle.fallback ? `fallback=${bundle.fallback}` : null]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
  return details.length > 0 ? `${bundle.id} (${details.join(', ')})` : bundle.id
}

const toBrowserAssetUrl = (publicUrl: string): string => {
  const trimmed = publicUrl.trim()
  if (!trimmed) {
    return ''
  }

  if (trimmed.startsWith('/api/')) {
    return trimmed
  }

  return trimmed.startsWith('/') ? `/api${trimmed}` : trimmed
}

export const verifyUploadedUiRegistryAssetUrl = async (publicUrl?: string, token?: string): Promise<boolean> => {
  const verificationUrl = publicUrl ? toBrowserAssetUrl(publicUrl) : ''
  if (!verificationUrl) {
    return false
  }

  try {
    const headResponse = await fetch(verificationUrl, {
      method: 'HEAD',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })

    if (headResponse.ok) {
      return true
    }
  } catch {
    // Fall through to a GET probe when HEAD is not supported or the gateway rejects it.
  }

  // Some gateway and contract-validation layers reject HEAD even when GET works.
  // Always probe GET after a failed HEAD so verification follows the same path as the browser.
  try {
    const getResponse = await fetch(verificationUrl, {
      method: 'GET',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      cache: 'no-store',
    })
    return getResponse.ok
  } catch {
    return false
  }
}

const readUiRegistryAssetErrorMessage = async (response: Response, fallbackMessage: string): Promise<string> => {
  try {
    const payload = (await response.clone().json()) as UiRegistryAssetErrorResponse
    if (typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail.trim()
    }
    if (payload.detail && typeof payload.detail === 'object' && typeof payload.detail.message === 'string' && payload.detail.message.trim()) {
      return payload.detail.message.trim()
    }
    if (typeof payload.message === 'string' && payload.message.trim()) {
      return payload.message.trim()
    }
  } catch {
    const text = (await response.clone().text()).trim()
    if (text) {
      return text
    }
  }

  return fallbackMessage
}

export const UIRegistryAdmin: React.FC = () => {
  const settings = useSettings()
  const [uiRegistryView, setUiRegistryView] = useState<UiRegistryView | null>(null)
  const [selectedIconProvider, setSelectedIconProvider] = useState<IconProviderName>(settings.applicationSettings?.iconProvider || DEFAULT_ICON_PROVIDER)
  const [selectedStylePackage, setSelectedStylePackage] = useState<StylePackageName>(settings.applicationSettings?.stylePackage || DEFAULT_STYLE_PACKAGE)
  const [styleBundleSourceUrl, setStyleBundleSourceUrl] = useState('')
  const [styleBundleFilename, setStyleBundleFilename] = useState('')
  const [styleBundleName, setStyleBundleName] = useState('')
  const [styleBundleArchive, setStyleBundleArchive] = useState<File | null>(null)
  const [styleBundleArchiveKey, setStyleBundleArchiveKey] = useState(0)
  const [componentBundleSourceUrl, setComponentBundleSourceUrl] = useState('')
  const [componentBundleFilename, setComponentBundleFilename] = useState('')
  const [componentBundleArchive, setComponentBundleArchive] = useState<File | null>(null)
  const [componentBundleArchiveKey, setComponentBundleArchiveKey] = useState(0)
  const [hasChanges, setHasChanges] = useState(false)
  const [saveStatusMessage, setSaveStatusMessage] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveErrorReferenceId, setSaveErrorReferenceId] = useState<string | null>(null)
  const [importStatusMessage, setImportStatusMessage] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [uploadFeedback, setUploadFeedback] = useState<UiRegistryAssetUploadFeedback>(null)
  const [importingAsset, setImportingAsset] = useState<UiRegistryAssetImportState>(null)

  useEffect(() => {
    setSelectedIconProvider(settings.applicationSettings?.iconProvider || DEFAULT_ICON_PROVIDER)
    setSelectedStylePackage(settings.applicationSettings?.stylePackage || DEFAULT_STYLE_PACKAGE)
  }, [settings.applicationSettings?.iconProvider, settings.applicationSettings?.stylePackage])

  const loadUiRegistry = useCallback(async () => {
    if (!settings.applicationSettings?.apiBaseUrl) {
      setUiRegistryView(null)
      return
    }

    try {
      const apiBase = toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)
      const token = getAuthToken()
      const response = await fetch(`${apiBase}/ui-registry`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })

      if (!response.ok) {
        return
      }

      const view = (await response.json()) as UiRegistryView
      setUiRegistryView(view)
    } catch {
      setUiRegistryView(null)
    }
  }, [settings.applicationSettings?.apiBaseUrl])

  useEffect(() => {
    void loadUiRegistry()
  }, [loadUiRegistry])

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

      const apiBaseUrl = settings.applicationSettings?.apiBaseUrl
      if (!apiBaseUrl) {
        throw new Error('Unable to save UI registry settings because the API base URL is unavailable.')
      }

      const token = getAuthToken()
      const apiBase = toApiGroupV1Base('system', apiBaseUrl)
      const response = await fetch(`${apiBase}/app-config`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          iconProvider: selectedIconProvider,
          stylePackage: selectedStylePackage,
        }),
      })

      if (!response.ok) {
        const message = await readUiRegistryAssetErrorMessage(response, 'Unable to save UI registry settings.')
        throw new Error(message)
      }

      await settings.loadSettings()

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

  const resetArchiveSelection = (kind: UiRegistryAssetKind) => {
    if (kind === 'style') {
      setStyleBundleArchive(null)
      setStyleBundleArchiveKey((current) => current + 1)
      setStyleBundleName('')
      return
    }

    setComponentBundleArchive(null)
    setComponentBundleArchiveKey((current) => current + 1)
  }

  const beginUploadProgressNotice = useCallback((kind: UiRegistryAssetKind) => {
    const actionLabel = kind === 'style' ? 'Style bundle' : 'Component bundle'
    setUploadFeedback({
      kind,
      tone: 'progress',
      message: `${actionLabel} upload in progress...`,
    })
  }, [])

  const renderUploadFeedback = useCallback((kind: UiRegistryAssetKind) => {
    if (!uploadFeedback || uploadFeedback.kind !== kind) {
      return null
    }

    return (
      <span className={`upload-status upload-status--${uploadFeedback.tone}`} role="status" aria-live="polite">
        {uploadFeedback.tone === 'success' ? <AppIcon name="check-circle" /> : null}
        {uploadFeedback.tone === 'error' ? <AppIcon name="exclamation-circle" /> : null}
        <span>{uploadFeedback.message}</span>
      </span>
    )
  }, [uploadFeedback])

  const handleImportAsset = async (kind: UiRegistryAssetKind) => {
    const sourceUrl = kind === 'style' ? styleBundleSourceUrl : componentBundleSourceUrl
    const filename = kind === 'style' ? styleBundleFilename : componentBundleFilename
    const actionLabel = kind === 'style' ? 'Style bundle' : 'Component bundle'

    if (!sourceUrl.trim()) {
      setImportError('Source URL is required before importing a UI registry asset.')
      setImportStatusMessage(null)
      return
    }

    try {
      setImportingAsset({ kind, mode: 'url' })
      setImportError(null)
      setImportStatusMessage(`${actionLabel} import in progress...`)

      if (!settings.applicationSettings?.apiBaseUrl) {
        throw new Error('Application API base URL is not configured.')
      }

      const apiBase = toApiGroupV1Base('system', settings.applicationSettings.apiBaseUrl)
      const token = getAuthToken()
      const response = await fetch(`${apiBase}/ui-registry/assets/import`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          source_url: sourceUrl.trim(),
          kind,
          ...(filename.trim() ? { filename: filename.trim() } : {}),
        }),
      })

      if (!response.ok) {
        throw new Error(
          await readUiRegistryAssetErrorMessage(
            response,
            `Unable to import ${kind === 'style' ? 'style bundle' : 'component bundle'} (${response.status}).`,
          ),
        )
      }

      const payload = (await response.json()) as UiRegistryAssetImportResponse
      setImportStatusMessage(
        `${actionLabel} imported successfully${payload.public_url ? `: ${payload.public_url}` : ''}`,
      )
      void loadUiRegistry()
    } catch (error) {
      setImportStatusMessage(null)
      setImportError(error instanceof Error ? error.message : 'Unable to import UI registry asset.')
    } finally {
      setImportingAsset(null)
    }
  }

  const handleUploadAsset = async (kind: UiRegistryAssetKind) => {
    const archive = kind === 'style' ? styleBundleArchive : componentBundleArchive

    if (!archive) {
      setUploadFeedback({
        kind,
        tone: 'error',
        message: 'Select a zip or tgz archive before uploading a UI registry asset.',
      })
      return
    }

    try {
      setImportingAsset({ kind, mode: 'upload' })
      setUploadFeedback(null)
      beginUploadProgressNotice(kind)

      if (!settings.applicationSettings?.apiBaseUrl) {
        throw new Error('Application API base URL is not configured.')
      }

      const apiBase = toApiGroupV1Base('system', settings.applicationSettings.apiBaseUrl)
      const token = getAuthToken()
      const formData = new FormData()
      formData.append('kind', kind)
      formData.append('file', archive, archive.name)
      if (kind === 'style' && styleBundleName.trim()) {
        formData.append('label', styleBundleName.trim())
      }

      const response = await fetch(`${apiBase}/ui-registry/assets/upload`, {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: formData,
      })

      if (!response.ok) {
        throw new Error(
          await readUiRegistryAssetErrorMessage(
            response,
            `Unable to upload ${kind === 'style' ? 'style bundle' : 'component bundle'} (${response.status}).`,
          ),
        )
      }

      const payload = (await response.json()) as UiRegistryAssetImportResponse

      setUploadFeedback({
        kind,
        tone: 'success',
        message:
          kind === 'style'
            ? `Style bundle uploaded successfully${styleBundleName.trim() ? `: ${styleBundleName.trim()}` : ''}`
            : `Component bundle uploaded successfully${payload.public_url ? `: ${payload.public_url}` : ''}`,
      })
      resetArchiveSelection(kind)
      void loadUiRegistry()
    } catch (error) {
      setUploadFeedback({
        kind,
        tone: 'error',
        message: error instanceof Error ? error.message : 'Unable to upload UI registry asset.',
      })
    } finally {
      setImportingAsset(null)
    }
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
        {(saveError || saveStatusMessage || importError || importStatusMessage) && (
          <div className={`settings-message ${saveError || importError ? 'error' : 'success'}`} role="status" aria-live="polite">
            <AppIcon name={saveError || importError ? 'exclamation-circle' : 'check-circle'} />
            <span>
              {saveError || saveStatusMessage || importError || importStatusMessage}
              {saveErrorReferenceId && saveError && (
                <>
                  <br />
                  {formatSupportReferenceId(saveErrorReferenceId)}
                </>
              )}
            </span>
            {(saveError || importError) && (
              <button onClick={() => { setSaveError(null); setSaveErrorReferenceId(null); setImportError(null); setImportStatusMessage(null) }}>
                Dismiss
              </button>
            )}
          </div>
        )}

        <div className="settings-panel">
          <div className="settings-form">
            <div className="settings-section">
              <h3>Import Style Bundle</h3>

              <div className="form-group">
                <AppInput
                  id="styleBundleSourceUrl"
                  label="Style bundle source URL"
                  type="url"
                  value={styleBundleSourceUrl}
                  onChange={(event) => setStyleBundleSourceUrl(event.target.value)}
                  placeholder="https://example.com/theme.css"
                  required
                />
              </div>

              <div className="form-group">
                <AppInput
                  id="styleBundleFilename"
                  label="Style bundle filename"
                  type="text"
                  value={styleBundleFilename}
                  onChange={(event) => setStyleBundleFilename(event.target.value)}
                  placeholder="theme.css"
                  hint="Optional. Leave empty to keep the source filename."
                />
              </div>

              <PrimaryButton onClick={() => void handleImportAsset('style')} disabled={importingAsset !== null || !styleBundleSourceUrl.trim()}>
                {importingAsset?.kind === 'style' && importingAsset.mode === 'url' ? 'Importing Style Bundle...' : 'Import Style Bundle'}
              </PrimaryButton>

              <div className="form-group">
                <AppInput
                  id="styleBundleName"
                  label="Style bundle name"
                  type="text"
                  value={styleBundleName}
                  onChange={(event) => setStyleBundleName(event.target.value)}
                  placeholder="Custom Style"
                  hint="Optional. Leave empty to keep the archive-derived label."
                />
              </div>

              <div className="form-group">
                <AppInput
                  key={styleBundleArchiveKey}
                  id="styleBundleArchive"
                  label="Style bundle archive"
                  type="file"
                  accept=".zip,.tgz,.tar.gz,application/zip,application/gzip,application/x-gtar,application/x-tar"
                  onChange={(event) => {
                    setStyleBundleArchive(event.target.files?.[0] ?? null)
                    setUploadFeedback(null)
                    setImportError(null)
                    setImportStatusMessage(null)
                  }}
                  hint="Upload a zip or tar.gz archive that contains a single stylesheet bundle file."
                />
                {styleBundleArchive ? <p className="info-text">Selected archive: {styleBundleArchive.name}</p> : null}
              </div>

              <div className="upload-action-row">
                <PrimaryButton onClick={() => void handleUploadAsset('style')} disabled={importingAsset !== null || !styleBundleArchive}>
                  Upload Style Bundle Archive
                </PrimaryButton>
                {renderUploadFeedback('style')}
              </div>
            </div>

            <div className="settings-section">
              <h3>Import Component Bundle</h3>

              <div className="form-group">
                <AppInput
                  id="componentBundleSourceUrl"
                  label="Component bundle source URL"
                  type="url"
                  value={componentBundleSourceUrl}
                  onChange={(event) => setComponentBundleSourceUrl(event.target.value)}
                  placeholder="https://example.com/icons.js"
                  required
                />
              </div>

              <div className="form-group">
                <AppInput
                  id="componentBundleFilename"
                  label="Component bundle filename"
                  type="text"
                  value={componentBundleFilename}
                  onChange={(event) => setComponentBundleFilename(event.target.value)}
                  placeholder="icons.js"
                  hint="Optional. Leave empty to keep the source filename."
                />
              </div>

              <PrimaryButton onClick={() => void handleImportAsset('component')} disabled={importingAsset !== null || !componentBundleSourceUrl.trim()}>
                {importingAsset?.kind === 'component' && importingAsset.mode === 'url' ? 'Importing Component Bundle...' : 'Import Component Bundle'}
              </PrimaryButton>

              <div className="form-group">
                <AppInput
                  key={componentBundleArchiveKey}
                  id="componentBundleArchive"
                  label="Component bundle archive"
                  type="file"
                  accept=".zip,.tgz,.tar.gz,application/zip,application/gzip,application/x-gtar,application/x-tar"
                  onChange={(event) => {
                    setComponentBundleArchive(event.target.files?.[0] ?? null)
                    setUploadFeedback(null)
                    setImportError(null)
                    setImportStatusMessage(null)
                  }}
                  hint="Upload a zip or tar.gz archive that contains a single component bundle file."
                />
                {componentBundleArchive ? <p className="info-text">Selected archive: {componentBundleArchive.name}</p> : null}
              </div>

              <div className="upload-action-row">
                <PrimaryButton onClick={() => void handleUploadAsset('component')} disabled={importingAsset !== null || !componentBundleArchive}>
                  Upload Component Bundle Archive
                </PrimaryButton>
                {renderUploadFeedback('component')}
              </div>
            </div>

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
