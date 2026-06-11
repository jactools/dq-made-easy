import React, { useEffect, useState } from 'react'
import { useSettings } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { AppIcon } from './app-primitives'
import './VersionStatistics.css'

interface VersionStatsResponse {
  versions: {
    total: number
    active: number
    markedForRollback: number
    changeTypes: Record<string, number>
  }
  testing: Array<{
    version_id: string
    version_number: number
    test_count: number
    passed_tests: number
    avg_coverage: number | null
  }>
  rollbacks: {
    total: number
    rollbackTargets: Record<string, number>
  }
}

interface VersionStatisticsProps {
  ruleId: string
  refreshKey?: number
}

export const VersionStatistics: React.FC<VersionStatisticsProps> = ({
  ruleId,
  refreshKey = 0,
}) => {
  const settings = useSettings()
  const apiBaseUrl = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
  const [stats, setStats] = useState<VersionStatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken())

  useEffect(() => {
    const syncTokenFromStorage = () => {
      setAuthToken(getAuthToken())
    }

    syncTokenFromStorage()
    if (typeof window !== 'undefined') {
      window.addEventListener('storage', syncTokenFromStorage)
      window.addEventListener('dq-auth-token-changed', syncTokenFromStorage)
    }

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('storage', syncTokenFromStorage)
        window.removeEventListener('dq-auth-token-changed', syncTokenFromStorage)
      }
    }
  }, [])

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true)
        const response = await fetch(`${apiBaseUrl}/rules/${ruleId}/versions/stats`, {
          headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
        })
        if (!response.ok) throw new Error('Failed to fetch version statistics')

        const data = await response.json()
        setStats(data.stats || null)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load statistics')
      } finally {
        setLoading(false)
      }
    }

    fetchStats()
  }, [apiBaseUrl, authToken, ruleId, refreshKey])

  if (loading) {
    return (
      <div className="version-statistics version-statistics-loading">
        <p>Loading statistics...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="version-statistics version-statistics-error">
        <p><AppIcon name="warning" /> {error}</p>
      </div>
    )
  }

  if (!stats) {
    return null
  }

  const testedVersions = stats.testing.filter(item => Number(item.test_count) > 0).length

  return (
    <section className="version-statistics" aria-label="Version statistics">
      <h4>Version Statistics</h4>

      <div className="version-statistics-grid">
        <div className="stat-card">
          <span className="stat-label">Total Versions</span>
          <span className="stat-value">{stats.versions.total}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Active Versions</span>
          <span className="stat-value">{stats.versions.active}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Marked for Rollback</span>
          <span className="stat-value">{stats.versions.markedForRollback}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total Rollbacks</span>
          <span className="stat-value">{stats.rollbacks.total}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Versions with Tests</span>
          <span className="stat-value">{testedVersions}</span>
        </div>
      </div>

      {Object.keys(stats.versions.changeTypes).length > 0 && (
        <div className="change-types">
          <h5>Change Types</h5>
          <div className="change-type-list">
            {Object.entries(stats.versions.changeTypes).map(([type, count]) => (
              <div key={type} className="change-type-item">
                <span className="change-type-name">{type.replace(/_/g, ' ')}</span>
                <span className="change-type-count">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
