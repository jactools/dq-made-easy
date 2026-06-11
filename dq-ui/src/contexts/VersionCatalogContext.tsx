import React, { ReactNode, createContext, useCallback, useEffect, useMemo, useState } from 'react'
import { toApiGroupV1Base } from '../config/api'
import { useAuth } from '../hooks/useKeycloak'
import { useSettings } from '../hooks/useContexts'

declare const __APP_VERSION__: string

export interface VersionCatalog {
  apps: {
    ui: string
    api: string
  }
  components: Record<string, string>
}

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

export interface VersionCatalogContextType {
  versionCatalog: VersionCatalog
  isLoading: boolean
  error: string | null
  refresh: () => Promise<void>
  getComponentVersion: (componentName: string) => string
}

export const VersionCatalogContext = createContext<VersionCatalogContextType | null>(null)

export const VersionCatalogProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const auth = useAuth()
  const settings = useSettings()
  const [versionCatalog, setVersionCatalog] = useState<VersionCatalog>(DEFAULT_VERSION_CATALOG)
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch(`${toApiGroupV1Base('system', settings.applicationSettings?.apiBaseUrl)}/version-catalog`, {
        credentials: 'include',
      })

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
  }, [settings.applicationSettings?.apiBaseUrl])

  useEffect(() => {
    if (!auth.isAuthenticated) {
      setVersionCatalog(DEFAULT_VERSION_CATALOG)
      setIsLoading(false)
      setError(null)
      return
    }

    refresh()
  }, [auth.isAuthenticated, refresh])

  const getComponentVersion = useCallback((componentName: string): string => {
    return String(versionCatalog.components[componentName] || versionCatalog.apps.ui || 'unknown')
  }, [versionCatalog])

  const value = useMemo(() => ({
    versionCatalog,
    isLoading,
    error,
    refresh,
    getComponentVersion
  }), [error, getComponentVersion, isLoading, refresh, versionCatalog])

  return (
    <VersionCatalogContext.Provider value={value}>
      {children}
    </VersionCatalogContext.Provider>
  )
}
