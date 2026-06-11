import { useEffect } from 'react'
import { type TrackedAsyncRequest, useAsyncRequestTrackerContext } from '../contexts/AsyncRequestTrackerContext'

export const useAsyncRequests = () => useAsyncRequestTrackerContext()

export const useTrackedAsyncRequest = (requestId?: string | null): TrackedAsyncRequest | null => {
  const context = useAsyncRequestTrackerContext()

  useEffect(() => {
    if (!requestId) return undefined
    context.registerWatcher(requestId)
    return () => context.unregisterWatcher(requestId)
  }, [context, requestId])

  if (!requestId) {
    return null
  }

  return context.requests[requestId] || null
}