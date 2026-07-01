import React, { useEffect, useMemo, useState } from 'react'
import {
  AppInput,
  AppIcon,
  APP_ICON_PROVIDER_LABELS,
  getAppIconNamesForProvider,
  AppPageHeader,
  AppPageShell,
  type AppIconName,
} from './app-primitives'
import { useSettingsOptional } from '../hooks/useContexts'
import { DEFAULT_ICON_PROVIDER, getAppIconProviderLabel, normalizeIconProviderName } from './app-primitives/appIconProviders'
import './IconGallery.css'

export const IconGallery: React.FC = () => {
  const settings = useSettingsOptional()
  const [searchTerm, setSearchTerm] = useState('')
  const [copiedIconName, setCopiedIconName] = useState<AppIconName | null>(null)
  const activeIconProvider = normalizeIconProviderName(settings?.applicationSettings?.iconProvider || DEFAULT_ICON_PROVIDER)
  const activeProviderLabel = getAppIconProviderLabel(activeIconProvider)
  const allIcons = useMemo(
    () => [...getAppIconNamesForProvider(activeIconProvider)].sort(),
    [activeIconProvider],
  )

  useEffect(() => {
    if (!copiedIconName) return

    const timeoutId = window.setTimeout(() => setCopiedIconName(null), 1200)
    return () => window.clearTimeout(timeoutId)
  }, [copiedIconName])

  const copyIconName = async (iconName: AppIconName) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(iconName)
      } else {
        const input = document.createElement('input')
        input.value = iconName
        input.setAttribute('readonly', 'true')
        input.style.position = 'absolute'
        input.style.left = '-9999px'
        document.body.appendChild(input)
        input.select()
        document.execCommand('copy')
        document.body.removeChild(input)
      }
      setCopiedIconName(iconName)
    } catch {
      setCopiedIconName(null)
    }
  }

  const filteredIcons = useMemo(() => {
    let icons = allIcons

    if (searchTerm) {
      const search = searchTerm.toLowerCase()
      icons = icons.filter((icon) => icon.toLowerCase().includes(search))
    }

    return icons
  }, [allIcons, searchTerm])

  return (
    <AppPageShell className="icon-gallery">
      <AppPageHeader
        title="Icon Gallery"
        subtitle={`Browse ${allIcons.length} ${activeProviderLabel} icons available from the selected active icon provider. Click any icon name to copy it.`}
      />

      <div className="icon-gallery-controls">
        <div className="icon-gallery-search">
          <div style={{ position: 'relative', width: '100%' }}>
            <AppInput
              label="Search icons"
              fieldClassName="icon-gallery-search-field"
              labelClassName="icon-gallery-search-label"
              type="search"
              placeholder="Search icons..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            <AppIcon
              name="search"
              style={{
                position: 'absolute',
                left: '10px',
                top: '50%',
                transform: 'translateY(-50%)',
                pointerEvents: 'none',
                fontSize: '16px',
                color: 'var(--app-text-secondary)',
              }}
            />
          </div>
        </div>

        <div className="icon-gallery-provider" aria-label="Active icon provider">
          <span className="icon-gallery-provider-label">Active provider</span>
          <span className="icon-gallery-provider-name">{activeProviderLabel}</span>
        </div>
      </div>

      <div className="icon-gallery-count">
        {filteredIcons.length === allIcons.length
          ? `Showing all ${filteredIcons.length} ${activeProviderLabel} icons`
          : `Found ${filteredIcons.length} ${activeProviderLabel} icon${filteredIcons.length !== 1 ? 's' : ''}`}
      </div>

      <div className="icon-gallery-grid">
        {filteredIcons.map((iconName) => (
          <div
            key={iconName}
            className={`icon-gallery-item${copiedIconName === iconName ? ' copied' : ''}`}
            onClick={() => void copyIconName(iconName)}
            data-icon={iconName}
            title={`Click to copy: ${iconName}`}
          >
            <div className="icon-gallery-icon-wrapper">
              <AppIcon name={iconName} />
            </div>
            {copiedIconName === iconName && <div className="icon-gallery-copied-badge">Copied!</div>}
            <div className="icon-gallery-icon-name">{iconName}</div>
          </div>
        ))}
      </div>

      {filteredIcons.length === 0 && (
        <div className="icon-gallery-empty">
          <AppIcon name="search" />
          <p>No {activeProviderLabel} icons found matching "{searchTerm}"</p>
        </div>
      )}
    </AppPageShell>
  )
}
