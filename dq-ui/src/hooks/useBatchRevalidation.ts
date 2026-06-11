import { useState, useCallback } from 'react'
import { useSettings } from './useContexts'
import { toApiGroupV1Base } from '../config/api'
import { getAuthToken } from '../contexts/AuthContext'
import { camelToSnake } from '../utils/caseConverters'

export interface RevalidationResult {
  ruleId: string
  ruleName: string
  validationChanged: boolean
  wasValid: boolean
  nowValid: boolean
  newIssues: string[]
  resolvedIssues: string[]
  status: string
}

export interface DriftReviewRule {
  ruleId: string
  ruleName: string
  ruleVersionId: string
  versionNumber: number
  affectedAliases: string[]
  totalDrifts: number
  needsRevalidation: boolean
}

export interface RevalidationJobStatus {
  jobId: string
  status: string
  progress: string
  queued: number
  completed: number
  failed: number
  validationImproved: number
  validationDegraded: number
  validationUnchanged: number
  triggeredByTerm: string
  startedAt?: string
  completedAt?: string
  durationSeconds?: number
  results: RevalidationResult[]
}

export interface UseBatchRevalidationReturn {
  startRevalidationJob: (
    ruleVersionIds: string[],
    termId?: string,
    termName?: string
  ) => Promise<{ jobId: string; status: string }>
  recordDriftReview: (
    affectedRules: DriftReviewRule[],
    termId?: string,
    termName?: string
  ) => Promise<{ reviewedCount: number; reviewedAt: string }>
  getJobStatus: (jobId: string) => Promise<RevalidationJobStatus>
  loading: boolean
  error: string | null
}

/**
 * Hook for triggering and monitoring batch revalidation jobs
 *
 * Usage:
 * const { startRevalidationJob, getJobStatus } = useBatchRevalidation()
 *
 * // Trigger revalidation for rules affected by term change
 * const { jobId } = await startRevalidationJob(['v1', 'v2'], 'term-123', 'amount')
 *
 * // Poll job status
 * const status = await getJobStatus(jobId)
 * console.log(`Progress: ${status.progress}`)
 * console.log(`${status.validationImproved} rules improved`)
 */
export const useBatchRevalidation = (): UseBatchRevalidationReturn => {
  const settings = useSettings()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const startRevalidationJob = useCallback(
    async (ruleVersionIds: string[], termId?: string, termName?: string) => {
      setLoading(true)
      setError(null)

      try {
        const authToken = getAuthToken()
        if (!authToken) {
          throw new Error('Not authenticated')
        }

        if (!ruleVersionIds || ruleVersionIds.length === 0) {
          throw new Error('No rule versions provided')
        }

        const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
        const response = await fetch(
          `${apiBase}/governance/revalidation/jobs`,
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${authToken}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(
              camelToSnake({
                ruleVersionIds,
                triggeredByTermId: termId,
                triggeredByTermName: termName,
              })
            ),
          }
        )

        if (!response.ok) {
          throw new Error(`Failed to start revalidation: ${response.statusText}`)
        }

        const data = await response.json()
        return {
          jobId: data.jobId,
          status: data.status,
        }
      } catch (err: any) {
        const errorMsg = err.message || 'Failed to start revalidation job'
        setError(errorMsg)
        console.error('Error starting revalidation job:', err)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [settings]
  )

  const recordDriftReview = useCallback(
    async (affectedRules: DriftReviewRule[], termId?: string, termName?: string) => {
      setLoading(true)
      setError(null)

      try {
        const authToken = getAuthToken()
        if (!authToken) {
          throw new Error('Not authenticated')
        }

        if (!affectedRules || affectedRules.length === 0) {
          throw new Error('No affected rules provided')
        }

        const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
        const response = await fetch(
          `${apiBase}/governance/drift/reviews`,
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${authToken}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(
              camelToSnake({
                affectedRules,
                triggeredByTermId: termId,
                triggeredByTermName: termName,
              })
            ),
          }
        )

        if (!response.ok) {
          throw new Error(`Failed to record drift review: ${response.statusText}`)
        }

        const data = await response.json()
        return {
          reviewedCount: data.reviewed_count,
          reviewedAt: data.reviewed_at,
        }
      } catch (err: any) {
        const errorMsg = err.message || 'Failed to record drift review'
        setError(errorMsg)
        console.error('Error recording drift review:', err)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [settings]
  )

  const getJobStatus = useCallback(
    async (jobId: string): Promise<RevalidationJobStatus> => {
      setLoading(true)
      setError(null)

      try {
        const authToken = getAuthToken()
        if (!authToken) {
          throw new Error('Not authenticated')
        }

        const apiBase = toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl)
        const response = await fetch(
          `${apiBase}/governance/revalidation/jobs/${jobId}`,
          {
            headers: {
              Authorization: `Bearer ${authToken}`,
              'Content-Type': 'application/json',
            },
          }
        )

        if (!response.ok) {
          throw new Error(`Failed to get job status: ${response.statusText}`)
        }

        const data = await response.json()
        return {
          jobId: data.job_id,
          status: data.status,
          progress: data.progress,
          queued: data.queued,
          completed: data.completed,
          failed: data.failed,
          validationImproved: data.validation_improved,
          validationDegraded: data.validation_degraded,
          validationUnchanged: data.validation_unchanged,
          triggeredByTerm: data.triggered_by_term,
          startedAt: data.started_at,
          completedAt: data.completed_at,
          durationSeconds: data.duration_seconds,
          results: data.results || [],
        }
      } catch (err: any) {
        const errorMsg = err.message || 'Failed to get job status'
        setError(errorMsg)
        console.error('Error getting job status:', err)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [settings]
  )

  return {
    startRevalidationJob,
    recordDriftReview,
    getJobStatus,
    loading,
    error,
  }
}
