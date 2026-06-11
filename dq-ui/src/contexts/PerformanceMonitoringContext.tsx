import React, { createContext, useContext, ReactNode } from 'react'
import { usePerformanceMonitoring } from '../hooks/usePerformanceMonitoring'
import type { PerformanceMetric, AggregatedMetrics, CacheMetrics } from '../hooks/usePerformanceMonitoring'

interface PerformanceMonitoringContextType {
  metrics: PerformanceMetric[]
  aggregated: Record<string, AggregatedMetrics>
  cacheStats: Record<string, CacheMetrics>
  startTimer: () => number
  endTimer: (operation: string, startTime: number, success?: boolean, metadata?: Record<string, any>) => void
  trackCache: (operation: string, hit: boolean) => void
  getOperationMetrics: (operation: string) => PerformanceMetric[]
  getSlowOperations: () => PerformanceMetric[]
  getFailedOperations: () => PerformanceMetric[]
  getOverallStats: () => {
    totalOperations: number
    successfulOperations: number
    failedOperations: number
    successRate: number
    avgDuration: number
    uptime: number
  }
  clearMetrics: () => void
}

const PerformanceMonitoringContext = createContext<PerformanceMonitoringContextType | undefined>(undefined)

export function PerformanceMonitoringProvider({ children }: { children: ReactNode }) {
  const monitoring = usePerformanceMonitoring()

  return (
    <PerformanceMonitoringContext.Provider value={monitoring}>
      {children}
    </PerformanceMonitoringContext.Provider>
  )
}

export function usePerformanceMonitoringContext() {
  const context = useContext(PerformanceMonitoringContext)
  if (!context) {
    throw new Error('usePerformanceMonitoringContext must be used within PerformanceMonitoringProvider')
  }
  return context
}
