import type { IconProviderName } from '../../types/settings'
import type { AppIconName } from './appIconRegistry'
import { LUCIDE_ICON_NAMES } from './lucideAdapter'
import { TABLER_ICON_NAMES } from './tablerAdapter'

export const APP_ICON_PROVIDER_LABELS: Record<IconProviderName, string> = {
  tabler: 'Tabler',
  lucide: 'Lucide',
}

export const APP_ICON_PROVIDER_ICON_NAMES: Record<IconProviderName, readonly AppIconName[]> = {
  tabler: TABLER_ICON_NAMES,
  lucide: LUCIDE_ICON_NAMES,
}

export const getAppIconNamesForProvider = (provider: IconProviderName): readonly AppIconName[] => (
  APP_ICON_PROVIDER_ICON_NAMES[provider]
)