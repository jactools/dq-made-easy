/** @vitest-environment jsdom */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  DASHBOARD_NAV_SELECTION_KEY,
  consumeDashboardNavigationSelection,
  getDashboardNavigationIntent,
  navigateFromDashboardCard,
} from './dashboardNavigation'

describe('dashboardNavigation', () => {
  afterEach(() => {
    window.sessionStorage.removeItem(DASHBOARD_NAV_SELECTION_KEY)
  })

  it('maps dashboard cards to their owning workflows and filter presets', () => {
    expect(getDashboardNavigationIntent('failed-validation-runs')).toMatchObject({
      destination: 'reports-rule-monitoring',
      preset: {
        browse_status: 'failed',
      },
    })
    expect(getDashboardNavigationIntent('active-rules')).toMatchObject({
      destination: 'rules-all',
      preset: {
        view_scope: 'all',
        filter_status: 'activated',
      },
    })
    expect(getDashboardNavigationIntent('pending-deactivation')).toMatchObject({
      destination: 'approvals-my',
      preset: {
        view_scope: 'my',
        request_filter: 'deactivation',
      },
    })
  })

  it('writes a one-shot preset before navigating and clears it after the owning workflow consumes it', () => {
    const onNavigate = vi.fn()

    navigateFromDashboardCard('failed-validation-runs', onNavigate)

    expect(onNavigate).toHaveBeenCalledWith('reports-rule-monitoring')
    expect(JSON.parse(window.sessionStorage.getItem(DASHBOARD_NAV_SELECTION_KEY) || '{}')).toMatchObject({
      destination: 'reports-rule-monitoring',
      source: 'dashboard',
      card_id: 'failed-validation-runs',
      preset: {
        browse_status: 'failed',
      },
    })

    expect(consumeDashboardNavigationSelection('rules-all')).toBeNull()
    expect(window.sessionStorage.getItem(DASHBOARD_NAV_SELECTION_KEY)).not.toBeNull()
    expect(consumeDashboardNavigationSelection('reports-rule-monitoring')).toMatchObject({
      browse_status: 'failed',
    })
    expect(window.sessionStorage.getItem(DASHBOARD_NAV_SELECTION_KEY)).toBeNull()
  })
})
