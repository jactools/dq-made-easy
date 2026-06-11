import { useCallback, useContext, useEffect, useMemo, useState } from 'react'
import {
  VersionCatalog,
  VersionCatalogContext,
  VersionCatalogContextType
} from '../contexts/VersionCatalogContext'
import { toApiGroupV1Base } from '../config/api'
import { useSettings } from './useContexts'

declare const __APP_VERSION__: string

const DEFAULT_UI_VERSION = typeof __APP_VERSION__ === 'string' && __APP_VERSION__.trim()
  ? __APP_VERSION__
  : 'unknown'

const DEFAULT_VERSION_CATALOG: VersionCatalog = {
  apps: {
    ui: DEFAULT_UI_VERSION,
    api: 'unknown'
  },
  components: {}
}

const useLocalVersionCatalog = (isEnabled = true): VersionCatalogContextType => {
  const settings = useSettings()
  const [versionCatalog, setVersionCatalog] = useState<VersionCatalog>(DEFAULT_VERSION_CATALOG)
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!isEnabled) {
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch(`${toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)}/version-catalog`)

      if (!response.ok) {
        if (response.status === 401) {
          setVersionCatalog(DEFAULT_VERSION_CATALOG)
          return
        }
        throw new Error(`Failed to fetch version catalog (${response.status})`)
      }

      const payload = await response.json()
      setVersionCatalog({
        apps: {
          ui: String(payload?.apps?.ui || 'unknown'),
          api: String(payload?.apps?.api || 'unknown')
        },
        components: typeof payload?.components === 'object' && payload?.components !== null
          ? payload.components
          : {}
      })
    } catch (fetchError) {
      console.error('Error fetching version catalog:', fetchError)
      setError('Unable to load version catalog')
      setVersionCatalog(DEFAULT_VERSION_CATALOG)
    } finally {
      setIsLoading(false)
    }
  }, [isEnabled, settings.applicationSettings?.apiBaseUrl])

  useEffect(() => {
    refresh()
  }, [refresh])

  const getComponentVersion = useCallback((componentName: string): string => {
    return String(versionCatalog.components[componentName] || versionCatalog.apps.ui || 'unknown')
  }, [versionCatalog])

  return useMemo(() => ({
    versionCatalog,
    isLoading,
    error,
    refresh,
    getComponentVersion
  }), [error, getComponentVersion, isLoading, refresh, versionCatalog])
}

export const useVersionCatalog = (isEnabled = true) => {
  const context = useContext(VersionCatalogContext)
  const localCatalog = useLocalVersionCatalog(isEnabled && !context)
  return context ?? localCatalog
}
