import { describe, expect, it } from 'vitest'

import type { IconProviderName } from '../../types/settings'
import { APP_ICON_NAMES } from './appIconRegistry'
import { APP_ICON_PROVIDER_ICON_NAMES, APP_ICON_PROVIDER_LABELS, getAppIconNamesForProvider } from './appIconProviders'
import { getLucideIconComponent } from './lucideAdapter'
import { getTablerIconComponent } from './tablerAdapter'

const providers: IconProviderName[] = ['tabler', 'lucide']

describe('app icon providers', () => {
  it('exposes labels and icon names for every supported provider', () => {
    for (const provider of providers) {
      expect(APP_ICON_PROVIDER_LABELS[provider]).toBeTruthy()
      expect(getAppIconNamesForProvider(provider)).toEqual(APP_ICON_PROVIDER_ICON_NAMES[provider])
      expect(getAppIconNamesForProvider(provider).length).toBeGreaterThan(0)
    }
  })

  it('only exposes provider-backed app icon names', () => {
    const appIconNames = new Set(APP_ICON_NAMES)

    for (const provider of providers) {
      for (const iconName of getAppIconNamesForProvider(provider)) {
        expect(appIconNames.has(iconName)).toBe(true)
        const providerIcon = provider === 'lucide'
          ? getLucideIconComponent(iconName)
          : getTablerIconComponent(iconName)
        expect(providerIcon).toBeTruthy()
      }
    }
  })
})