import type { AppIconName } from './appIconRegistry'

export const APP_ICON_USAGE_BY_SURFACE = {
  reports_tabs: ['line-chart', 'list', 'exclamation-circle', 'table'],
  reports_search: ['search'],
  notifications_page: ['search', 'close', 'bell', 'exclamation-circle', 'check-circle', 'info-circle'],
  session_timeout_warning: ['info-circle'],
  version_info_modal: ['exclamation-circle', 'info-circle', 'database', 'check-circle', 'package'],
} as const satisfies Record<string, readonly AppIconName[]>

export const APP_ICON_USAGE = [...new Set(Object.values(APP_ICON_USAGE_BY_SURFACE).flat())] as AppIconName[]