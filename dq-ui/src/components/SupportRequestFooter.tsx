import React, { useCallback, useMemo, useState } from 'react'

import { SIDEBAR_MENU_ITEMS } from './Sidebar'
import { StatusBanner } from './StatusBanner'
import { SupportRequestFlow } from './SupportRequestFlow'

type SupportRequestFooterProps = {
  apiBaseUrl: string
  pageId: string
  workspaceId?: string | null
  className?: string
}

const SUPPORT_REQUEST_FOOTER_DISMISSED_KEY = 'dq-made-easy:support-request-footer-dismissed'

const getStoredDismissedState = (): boolean => {
  try {
    return window.localStorage.getItem(SUPPORT_REQUEST_FOOTER_DISMISSED_KEY) === 'true'
  } catch {
    return false
  }
}

const setStoredDismissedState = (dismissed: boolean): void => {
  try {
    window.localStorage.setItem(SUPPORT_REQUEST_FOOTER_DISMISSED_KEY, dismissed ? 'true' : 'false')
  } catch {
    // Local storage can be unavailable in private browsing or test sandboxes.
  }
}

const humanizeFallbackLabel = (value: string): string => {
  const normalized = String(value || '').trim().replace(/[-_]+/g, ' ')
  if (!normalized) {
    return 'Current page'
  }

  return normalized
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

const findSidebarLabel = (pageId: string, menuItems = SIDEBAR_MENU_ITEMS): string | null => {
  for (const item of menuItems) {
    if (item.id === pageId) {
      return item.label
    }

    if (item.submenu) {
      const match = item.submenu.find((submenuItem) => submenuItem.id === pageId)
      if (match) {
        return match.label
      }
    }
  }

  return null
}

export const SupportRequestFooter: React.FC<SupportRequestFooterProps> = ({
  apiBaseUrl,
  pageId,
  workspaceId,
  className,
}) => {
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState(getStoredDismissedState)

  const pageLabel = useMemo(() => {
    return findSidebarLabel(pageId) || humanizeFallbackLabel(pageId)
  }, [pageId])

  const handleDismissError = useCallback(() => {
    setErrorMessage(null)
  }, [])

  const handleDismissFooter = useCallback(() => {
    setErrorMessage(null)
    setDismissed(true)
    setStoredDismissedState(true)
  }, [])

  const handleOpenFooter = useCallback(() => {
    setDismissed(false)
    setStoredDismissedState(false)
  }, [])

  if (dismissed) {
    return (
      <footer className={className ? `support-request-footer support-request-footer--compact ${className}` : 'support-request-footer support-request-footer--compact'} aria-label="Request assistance">
        <button
          type="button"
          className="support-request-footer__icon-button"
          aria-label="Open request assistance"
          title="Request assistance"
          onClick={handleOpenFooter}
        >
          <span className="support-request-footer__icon-glyph support-request-footer__icon-glyph--help" aria-hidden="true">
            ?
          </span>
        </button>
      </footer>
    )
  }

  return (
    <footer className={className ? `support-request-footer ${className}` : 'support-request-footer'} aria-label="Request assistance">
      <button
        type="button"
        className="support-request-footer__dismiss"
        aria-label="Minimize request assistance"
        title="Minimize request assistance"
        onClick={handleDismissFooter}
      >
        <span className="support-request-footer__icon-glyph support-request-footer__icon-glyph--close" aria-hidden="true" />
      </button>

      <div className="support-request-footer__copy">
        <span className="support-request-footer__eyebrow">Need help?</span>
        <h2 className="support-request-footer__title">Request assistance</h2>
        <p className="support-request-footer__description">
          Send a support request for the current page. We include the page and workspace context automatically.
        </p>
      </div>

      <div className="support-request-footer__action">
        <SupportRequestFlow
          apiBaseUrl={apiBaseUrl}
          buttonLabel="Request assistance"
          createRequestBody={() => ({
            title: `Application assistance: ${pageLabel}`,
            message: `I need help with the ${pageLabel} page in dq-made-easy.`,
            source: 'app-footer',
            workspaceId,
            details: {
              page_id: pageId,
              page_label: pageLabel,
              path: window.location.pathname,
            },
          })}
          onError={setErrorMessage}
          className="support-request-footer__flow"
        />

        {errorMessage ? (
          <StatusBanner
            variant="error"
            message={errorMessage}
            onDismiss={handleDismissError}
            className="support-request-footer__error"
          />
        ) : null}
      </div>
    </footer>
  )
}