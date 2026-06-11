import { useEffect, useState, useCallback } from 'react'
import { useSettings } from './useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'

export interface CatalogTerm {
  termKey: string
  termName: string
  description?: string
  dataType?: string
  domain?: string
  glossaryId?: string
  lastSynced?: string
  matchScorePct?: number
}

export interface UseCatalogTermsReturn {
  terms: CatalogTerm[]
  loading: boolean
  error: string | null
  lastSync: Date | null
  isEnabled: boolean
  searchTerms: (query: string) => CatalogTerm[]
  refetch: () => Promise<void>
}

/**
 * Hook to fetch and cache business terms from catalog
 * 
 * Usage:
 * const { terms, loading, searchTerms } = useCatalogTerms()
 * const matches = searchTerms('amount')
 */
export const useCatalogTerms = (searchQuery: string = ''): UseCatalogTermsReturn => {
  const settings = useSettings()
  const [terms, setTerms] = useState<CatalogTerm[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastSync, setLastSync] = useState<Date | null>(null)
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState(searchQuery)
  const isEnabled = true // Feature flag check could go here
  const debounceMs = settings.applicationSettings?.debounceMs ?? 300

  const fetchTerms = useCallback(async (domain?: string, query?: string) => {
    setLoading(true)
    setError(null)
    
    try {
      const authToken = getAuthToken()
      if (!authToken) {
        setError('Not authenticated')
        return
      }

      const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
      const params = new URLSearchParams()
      if (domain) {
        params.append('domain', domain)
      }
      const normalizedQuery = query?.trim() || ''
      if (normalizedQuery) {
        params.append('search', normalizedQuery)
      }
      const thresholdPct = settings.displaySettings?.catalogTermMatchThresholdPct
        ?? settings.applicationSettings?.defaultCatalogTermMatchThresholdPct
        ?? 70
      params.append('match_threshold_pct', String(thresholdPct))

      const response = await fetch(`${apiBase}/catalog/terms?${params}`, {
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`)
      }

      const data = await response.json()
      setTerms(data.terms || [])
      if (data.lastSynced) {
        setLastSync(new Date(data.lastSynced))
      }
    } catch (err: any) {
      const message = err?.message || 'Failed to load business terms'
      setError(message)
      console.error('Business terms fetch error:', err)
    } finally {
      setLoading(false)
    }
  }, [settings.applicationSettings?.apiBaseUrl, settings.applicationSettings?.defaultCatalogTermMatchThresholdPct, settings.displaySettings?.catalogTermMatchThresholdPct])

  useEffect(() => {
    const debounceDelayMs = searchQuery === debouncedSearchQuery ? 0 : debounceMs
    const timerId = window.setTimeout(() => {
      setDebouncedSearchQuery(searchQuery)
    }, debounceDelayMs)

    return () => {
      window.clearTimeout(timerId)
    }
  }, [debounceMs, searchQuery, debouncedSearchQuery])

  useEffect(() => {
    if (isEnabled) {
      fetchTerms(undefined, debouncedSearchQuery)
    }
  }, [isEnabled, fetchTerms, debouncedSearchQuery])

  const searchTerms = useCallback((query: string): CatalogTerm[] => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) return terms

    const queryTokens = normalizedQuery
      .split(/\s+/)
      .map((token) => token.trim())
      .filter(Boolean)

    return terms.filter((term) => {
      const searchableText = [term.termName, term.description, term.termKey]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()

      return searchableText.includes(normalizedQuery)
        || queryTokens.some((token) => searchableText.includes(token))
    })
  }, [terms])

  return {
    terms,
    loading,
    error,
    lastSync,
    isEnabled,
    searchTerms,
    refetch: () => fetchTerms(undefined, searchQuery),
  }
}
