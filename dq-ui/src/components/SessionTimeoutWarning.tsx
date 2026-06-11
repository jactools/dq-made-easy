import React, { useEffect, useMemo, useState } from 'react'
import { getAuthTokenExpiresAt, getAuthTokenObservedAt, getSessionLastActivityAt } from '../contexts/AuthContext'
import { useAuth } from '../hooks/useKeycloak'
import { useSettings } from '../hooks/useContexts'
import { AppIcon } from './app-primitives'

const formatRemainingTime = (remainingMs: number): string => {
  const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60

  const minuteLabel = `${minutes} minute${minutes === 1 ? '' : 's'}`
  const secondLabel = `${seconds} second${seconds === 1 ? '' : 's'}`

  if (minutes <= 0) {
    return secondLabel
  }

  if (seconds === 0) {
    return minuteLabel
  }

  return `${minuteLabel} ${secondLabel}`
}

export const SessionTimeoutWarning: React.FC = () => {
  const auth = useAuth()
  const settings = useSettings()
  const [now, setNow] = useState(() => Date.now())
  const [dismissedTokenExpiresAt, setDismissedTokenExpiresAt] = useState<number | null>(null)
  const [dismissedUntilAt, setDismissedUntilAt] = useState<number | null>(null)
  const timeoutMinutes = settings.applicationSettings?.sessionTimeoutMinutes ?? 0
  const warningLeadMinutes = settings.applicationSettings?.sessionTimeoutWarningMinutes ?? 5

  const refreshTokenPresent = Boolean(localStorage.getItem('refreshToken'))
  const refreshUnavailable = Boolean(auth.refreshUnavailable)

  useEffect(() => {
    if (!auth.isAuthenticated) {
      return
    }

    const timerId = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timerId)
  }, [auth.isAuthenticated])

  const { nextExpiry, shouldShow, tokenExpiresAt } = useMemo(() => {
    if (!auth.isAuthenticated) {
      return {
        nextExpiry: null as null | { reason: 'idle' | 'token'; remainingMs: number },
        shouldShow: false,
        tokenExpiresAt: null as number | null,
      }
    }

    const warningWindowMs = Math.max(0, Math.floor(warningLeadMinutes) * 60 * 1000)

    const lastActivityAt = getSessionLastActivityAt()
    const timeoutMs = Math.max(0, Math.floor(timeoutMinutes) * 60 * 1000)
    const idleRemainingMs =
      lastActivityAt !== null && timeoutMs > 0
        ? timeoutMs - (now - lastActivityAt)
        : null

    const tokenExpiresAt = getAuthTokenExpiresAt()
    const tokenRemainingMs = tokenExpiresAt !== null ? tokenExpiresAt - now : null

    const tokenObservedAt = getAuthTokenObservedAt()
    const tokenTtlMs =
      tokenExpiresAt !== null && tokenObservedAt !== null && tokenExpiresAt > tokenObservedAt
        ? tokenExpiresAt - tokenObservedAt
        : null

    let candidate: null | { reason: 'idle' | 'token'; remainingMs: number } = null
    if (idleRemainingMs !== null && Number.isFinite(idleRemainingMs) && idleRemainingMs > 0) {
      candidate = { reason: 'idle', remainingMs: idleRemainingMs }
    }
    if (tokenRemainingMs !== null && Number.isFinite(tokenRemainingMs) && tokenRemainingMs > 0) {
      if (!candidate || tokenRemainingMs < candidate.remainingMs) {
        candidate = { reason: 'token', remainingMs: tokenRemainingMs }
      }
    }

    if (!candidate) {
      return { nextExpiry: null, shouldShow: false, tokenExpiresAt }
    }

    // If the warning lead is >= the idle timeout, the banner becomes always-on (unhelpful).
    // In that case, reduce the effective idle warning window by 1 minute (or disable if too small).
    const idleWarningWindowMs =
      timeoutMs > 0 && warningWindowMs >= timeoutMs
        ? Math.max(0, timeoutMs - 60 * 1000)
        : warningWindowMs

    const effectiveWindowMs =
      candidate.reason === 'idle' && timeoutMs > 0
        ? Math.min(timeoutMs, idleWarningWindowMs)
        : (() => {
            if (candidate.reason !== 'token') {
              return warningWindowMs
            }

            // If the token lifetime is <= the warning lead, the banner becomes always-on.
            // Use observed-at to approximate token TTL and shrink the effective token warning window.
            if (tokenTtlMs !== null && tokenTtlMs > 0 && warningWindowMs >= tokenTtlMs) {
              return Math.max(0, tokenTtlMs - 60 * 1000)
            }

            return warningWindowMs
          })()

    const baseShouldShow = candidate.remainingMs > 0 && candidate.remainingMs <= effectiveWindowMs

    // UX: hide the banner briefly on user activity. If we are truly about to expire,
    // the banner should reappear (hard warning window).
    const hardWarningMs = 30 * 1000
    const isDismissedByRecentActivity =
      dismissedUntilAt !== null &&
      now < dismissedUntilAt &&
      candidate.remainingMs > hardWarningMs

    const tokenHardWarningMs = 30 * 1000
    const isDismissedForThisToken =
      candidate.reason === 'token' &&
      !refreshTokenPresent &&
      dismissedTokenExpiresAt !== null &&
      tokenExpiresAt !== null &&
      dismissedTokenExpiresAt === tokenExpiresAt &&
      candidate.remainingMs > tokenHardWarningMs

    return {
      nextExpiry: candidate,
      shouldShow: baseShouldShow && !isDismissedForThisToken && !isDismissedByRecentActivity,
      tokenExpiresAt,
    }
  }, [auth.isAuthenticated, now, timeoutMinutes, warningLeadMinutes, refreshTokenPresent, dismissedTokenExpiresAt, dismissedUntilAt])

  const shouldRefreshOnActivity = Boolean(
    auth.isAuthenticated &&
    shouldShow &&
    nextExpiry?.reason === 'token' &&
    refreshTokenPresent
  )

  const shouldDismissTokenOnActivity = Boolean(
    auth.isAuthenticated &&
    shouldShow &&
    nextExpiry?.reason === 'token' &&
    !refreshTokenPresent
  )

  useEffect(() => {
    if (!auth.isAuthenticated || !shouldShow || !nextExpiry) {
      return
    }

    let lastRefreshAttemptAt = 0
    const handler = () => {
      const nowMs = Date.now()
      setNow(nowMs)
      setDismissedUntilAt(nowMs + 60000)

      if (shouldDismissTokenOnActivity) {
        setDismissedTokenExpiresAt(tokenExpiresAt)
      }

      if (shouldRefreshOnActivity) {
        if (nowMs - lastRefreshAttemptAt < 15000) {
          return
        }
        lastRefreshAttemptAt = nowMs
        void auth.refreshAuthToken()
      }
    }

    const activityEvents: Array<keyof WindowEventMap> = [
      'mousemove',
      'mousedown',
      'keydown',
      'touchstart',
      'scroll',
      'wheel',
      'click',
      'focus',
    ]

    activityEvents.forEach((ev) => window.addEventListener(ev, handler))
    return () => activityEvents.forEach((ev) => window.removeEventListener(ev, handler))
  }, [auth, auth.isAuthenticated, nextExpiry, shouldDismissTokenOnActivity, shouldRefreshOnActivity, shouldShow, tokenExpiresAt])

  if (!auth.isAuthenticated || !shouldShow || !nextExpiry) {
    return null
  }

  const remainingLabel = formatRemainingTime(nextExpiry.remainingMs)
  const canKeepAliveOnActivity = nextExpiry.reason === 'idle' || (nextExpiry.reason === 'token' && refreshTokenPresent && !refreshUnavailable)
  const needsRefreshUnavailableMessage = nextExpiry.reason === 'token' && refreshUnavailable

  return (
    <div className="session-timeout-banner" role="status" aria-live="polite">
      <div className="session-timeout-banner-icon" aria-hidden="true">
        <AppIcon name="info-circle" />
      </div>
      <div className="session-timeout-banner-copy">
        <span>
          <>
            <strong>You will be logged off in {remainingLabel}.</strong>
            {needsRefreshUnavailableMessage
              ? ' Automatic refresh is unavailable. Please sign in again soon to continue.'
              : canKeepAliveOnActivity
                ? ' Any activity will keep your session active.'
                : ' You may need to sign in again soon to continue.'}
          </>
        </span>
      </div>
    </div>
  )
}

export default SessionTimeoutWarning