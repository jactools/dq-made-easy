import { describe, expect, it } from 'vitest'

import { APP_ICON_NAMES } from './appIconRegistry'
import { APP_ICON_USAGE, APP_ICON_USAGE_BY_SURFACE } from './appIconUsage'

describe('app icon coverage', () => {
  it('tracks the app-owned icons used by the reusable primitives', () => {
    const usedIcons = new Set(APP_ICON_USAGE)

    expect(APP_ICON_USAGE_BY_SURFACE).toMatchObject({
      reports_tabs: ['line-chart', 'list', 'exclamation-circle', 'table'],
      reports_search: ['search'],
      notifications_page: ['search', 'close', 'bell', 'exclamation-circle', 'check-circle', 'info-circle'],
      session_timeout_warning: ['info-circle'],
      version_info_modal: ['exclamation-circle', 'info-circle', 'database', 'check-circle', 'package'],
    })

    for (const iconName of usedIcons) {
      expect(APP_ICON_NAMES).toContain(iconName)
    }
  })
})