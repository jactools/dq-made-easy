import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AppIcon } from './app-primitives'
import './NotificationSnoozeControl.css'

export type SnoozeDuration = '2h' | '4h' | 'eod' | '1w' | 'clear'

interface SnoozeDurationOption {
  value: SnoozeDuration
  label: string
}

const SNOOZE_OPTIONS: SnoozeDurationOption[] = [
  { value: '2h', label: '2 hours' },
  { value: '4h', label: '4 hours' },
  { value: 'eod', label: 'Until end of day' },
  { value: '1w', label: '1 week' },
]

/** Compute the ISO timestamp for the given snooze duration. */
export const computeSnoozedUntil = (duration: SnoozeDuration): string | undefined => {
  const now = new Date()
  switch (duration) {
    case '2h': {
      now.setHours(now.getHours() + 2)
      return now.toISOString()
    }
    case '4h': {
      now.setHours(now.getHours() + 4)
      return now.toISOString()
    }
    case 'eod': {
      now.setHours(23, 59, 59, 0)
      return now.toISOString()
    }
    case '1w': {
      now.setDate(now.getDate() + 7)
      return now.toISOString()
    }
    case 'clear':
      return undefined
  }
}

/** Returns true when notifications should be suppressed right now. */
export const isCurrentlySnoozed = (snoozedUntil: string | undefined): boolean => {
  if (!snoozedUntil) return false
  return new Date(snoozedUntil) > new Date()
}

interface NotificationSnoozeControlProps {
  /** Current snoozedUntil value from NotificationSettings. */
  snoozedUntil?: string
  /** Called when the user picks a duration or clears the snooze. */
  onChange: (snoozedUntil: string | undefined) => void
  /** If true, shows as a compact dropdown toggle (for the header). Default: false (full panel). */
  compact?: boolean
}

export const NotificationSnoozeControl: React.FC<NotificationSnoozeControlProps> = ({
  snoozedUntil,
  onChange,
  compact = false,
}) => {
  const active = isCurrentlySnoozed(snoozedUntil)
  const [open, setOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement | null>(null)

  // Close on outside click in compact mode
  useEffect(() => {
    if (!compact || !open) return
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [compact, open])

  const handleSelect = useCallback(
    (duration: SnoozeDuration) => {
      onChange(computeSnoozedUntil(duration))
      setOpen(false)
    },
    [onChange]
  )

  const formatSnoozedUntil = (ts: string) => {
    const date = new Date(ts)
    const today = new Date()
    const isToday =
      date.getFullYear() === today.getFullYear() &&
      date.getMonth() === today.getMonth() &&
      date.getDate() === today.getDate()
    return isToday
      ? `today at ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
      : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
  }

  if (compact) {
    return (
      <div className="snooze-compact" ref={panelRef}>
        <button
          type="button"
          className={`snooze-compact-trigger${active ? ' snooze-active' : ''}`}
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-label={active ? 'Notifications snoozed – click to manage' : 'Snooze notifications'}
          title={active && snoozedUntil ? `Snoozed until ${formatSnoozedUntil(snoozedUntil)}` : 'Snooze notifications'}
        >
          <AppIcon className="snooze-compact-icon" name="bell" aria-hidden="true" />
          {active ? 'Snoozed' : 'Snooze'}
        </button>

        {open && (
          <div className="snooze-compact-dropdown" role="menu">
            {active && snoozedUntil && (
              <p className="snooze-compact-status">
                Snoozed until {formatSnoozedUntil(snoozedUntil)}
              </p>
            )}
            {SNOOZE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                role="menuitem"
                className="snooze-compact-option"
                onClick={() => handleSelect(opt.value)}
              >
                {opt.label}
              </button>
            ))}
            {active && (
              <button
                type="button"
                role="menuitem"
                className="snooze-compact-option snooze-clear"
                onClick={() => handleSelect('clear')}
              >
                Resume notifications
              </button>
            )}
          </div>
        )}
      </div>
    )
  }

  // Full panel mode (settings page)
  return (
    <div className="snooze-panel">
      <h3 className="snooze-panel-heading">Temporary silence</h3>
      <p className="snooze-panel-subtitle">
        Pause all notifications for a set period, for example while you are on vacation.
      </p>

      {active && snoozedUntil && (
        <div className="snooze-active-banner" role="status">
          <AppIcon className="snooze-active-icon" name="bell" aria-hidden="true" />
          <span>
            Notifications are silenced until <strong>{formatSnoozedUntil(snoozedUntil)}</strong>
          </span>
          <button
            type="button"
            className="snooze-clear-btn"
            onClick={() => handleSelect('clear')}
          >
            Resume now
          </button>
        </div>
      )}

      <div className="snooze-options-row">
        {SNOOZE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            className="snooze-option-btn"
            onClick={() => handleSelect(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}
