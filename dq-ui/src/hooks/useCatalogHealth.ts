import { useEffect, useState, useCallback } from 'react'
import { useSettings } from './useContexts'
import { toApiGroupV1Base } from '../config/api'

export interface CatalogHealth {
  status: 'healthy' | 'degraded' | 'unknown' | 'error'
  lastSync: Date | null
  termCount: number
  message?: string
}

export interface UseCatalogHealthReturn {
  health: CatalogHealth
  loading: boolean
  error: string | null
  isAvailable: boolean
  refetch: () => Promise<void>
}

/**
 * Hook to check catalog health and sync status
 * 
 * Useful for displaying warnings if catalog is unavailable
 */
export const useCatalogHealth = (): UseCatalogHealthReturn => {
  const settings = useSettings()
  const [health, setHealth] = useState<CatalogHealth>({
    status: 'unknown',
    lastSync: null,
    termCount: 0,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchHealth = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      
      const response = await fetch(`${apiBase}/catalog/health`, {
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        setHealth({
          status: 'error',
          lastSync: null,
          termCount: 0,
          message: `HTTP ${response.status}`,
        })
        return
      }

      const data = await response.json()
      setHealth({
        status: data.status,
        lastSync: data.last_sync ? new Date(data.last_sync) : null,
        termCount: data.term_count || 0,
        message: data.message,
      })
    } catch (err: any) {
      const message = err?.message || 'Failed to check catalog health'
      setError(message)
      setHealth({
        status: 'error',
        lastSync: null,
        termCount: 0,
        message,
      })
    } finally {
      setLoading(false)
    }
  }, [settings.applicationSettings?.apiBaseUrl])

  // Check health on mount and periodically
  useEffect(() => {
    fetchHealth()
    
    // Refresh every 5 minutes
    const interval = setInterval(fetchHealth, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [fetchHealth])

  return {
    health,
    loading,
    error,
    isAvailable: health.status === 'healthy' || health.status === 'degraded',
    refetch: fetchHealth,
  }
}
