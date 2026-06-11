import { useState, useCallback, useEffect } from 'react'

export interface PerformanceMetric {
  operation: string
  startTime: number
  endTime: number
  duration: number
  success: boolean
  metadata?: Record<string, any>
}

export interface AggregatedMetrics {
  operation: string
  count: number
  avgDuration: number
  minDuration: number
  maxDuration: number
  successRate: number
  lastExecuted: number
}

export interface CacheMetrics {
  hits: number
  misses: number
  hitRate: number
}

interface PerformanceMonitoringState {
  metrics: PerformanceMetric[]
  aggregated: Record<string, AggregatedMetrics>
  cacheStats: Record<string, CacheMetrics>
  startTime: number
}

const MAX_METRICS = 1000 // Keep last 1000 operations

export function usePerformanceMonitoring() {
  const [state, setState] = useState<PerformanceMonitoringState>({
    metrics: [],
    aggregated: {},
    cacheStats: {},
    startTime: Date.now(),
  })

  // Track a single operation
  const trackOperation = useCallback((operation: string, startTime: number, success: boolean, metadata?: Record<string, any>) => {
    const endTime = Date.now()
    const duration = endTime - startTime

    const metric: PerformanceMetric = {
      operation,
      startTime,
      endTime,
      duration,
      success,
      metadata,
    }

    setState(prev => {
      const newMetrics = [...prev.metrics, metric].slice(-MAX_METRICS)
      
      // Update aggregated stats
      const existing = prev.aggregated[operation]
      const newCount = (existing?.count || 0) + 1
      const successCount = (existing ? existing.successRate * existing.count : 0) + (success ? 1 : 0)
      
      const aggregated = {
        ...prev.aggregated,
        [operation]: {
          operation,
          count: newCount,
          avgDuration: existing 
            ? (existing.avgDuration * existing.count + duration) / newCount
            : duration,
          minDuration: existing ? Math.min(existing.minDuration, duration) : duration,
          maxDuration: existing ? Math.max(existing.maxDuration, duration) : duration,
          successRate: successCount / newCount,
          lastExecuted: endTime,
        }
      }

      return {
        ...prev,
        metrics: newMetrics,
        aggregated,
      }
    })
  }, [])

  // Track cache hit/miss
  const trackCache = useCallback((operation: string, hit: boolean) => {
    setState(prev => {
      const existing = prev.cacheStats[operation] || { hits: 0, misses: 0, hitRate: 0 }
      const hits = existing.hits + (hit ? 1 : 0)
      const misses = existing.misses + (hit ? 0 : 1)
      const total = hits + misses

      return {
        ...prev,
        cacheStats: {
          ...prev.cacheStats,
          [operation]: {
            hits,
            misses,
            hitRate: total > 0 ? hits / total : 0,
          }
        }
      }
    })
  }, [])

  // Helper to start timing an operation
  const startTimer = useCallback(() => {
    return Date.now()
  }, [])

  // Helper to complete timing an operation
  const endTimer = useCallback((operation: string, startTime: number, success: boolean = true, metadata?: Record<string, any>) => {
    trackOperation(operation, startTime, success, metadata)
  }, [trackOperation])

  // Get metrics for a specific operation
  const getOperationMetrics = useCallback((operation: string) => {
    return state.metrics.filter(m => m.operation === operation)
  }, [state.metrics])

  // Get slow operations (>1000ms)
  const getSlowOperations = useCallback(() => {
    return state.metrics.filter(m => m.duration > 1000).slice(-50)
  }, [state.metrics])

  // Get failed operations
  const getFailedOperations = useCallback(() => {
    return state.metrics.filter(m => !m.success).slice(-50)
  }, [state.metrics])

  // Clear all metrics
  const clearMetrics = useCallback(() => {
    setState({
      metrics: [],
      aggregated: {},
      cacheStats: {},
      startTime: Date.now(),
    })
  }, [])

  // Get overall statistics
  const getOverallStats = useCallback(() => {
    const totalOperations = state.metrics.length
    const successfulOperations = state.metrics.filter(m => m.success).length
    const avgDuration = totalOperations > 0 
      ? state.metrics.reduce((sum, m) => sum + m.duration, 0) / totalOperations 
      : 0
    const uptime = Date.now() - state.startTime

    return {
      totalOperations,
      successfulOperations,
      failedOperations: totalOperations - successfulOperations,
      successRate: totalOperations > 0 ? successfulOperations / totalOperations : 1,
      avgDuration,
      uptime,
    }
  }, [state.metrics, state.startTime])

  return {
    // State
    metrics: state.metrics,
    aggregated: state.aggregated,
    cacheStats: state.cacheStats,
    
    // Methods
    startTimer,
    endTimer,
    trackCache,
    getOperationMetrics,
    getSlowOperations,
    getFailedOperations,
    getOverallStats,
    clearMetrics,
  }
}
