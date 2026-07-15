import { describe, expect, it } from 'vitest'

import { APP_ICON_NAMES } from './appIconRegistry'
import { APP_ICON_PROVIDER_ICON_NAMES, APP_ICON_PROVIDER_LABELS, getAppIconNamesForProvider, getAppIconProviderLabel, getAppIconProviderOptions } from './appIconProviders'
import { getLucideIconComponent } from './lucideAdapter'
import { getTablerIconComponent } from './tablerAdapter'

const providers = ['tabler', 'lucide']

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

  it('falls back safely for unknown providers', () => {
    expect(APP_ICON_PROVIDER_LABELS.custom_registry_theme).toBeUndefined()
    expect(getAppIconProviderLabel('custom_registry_theme')).toBe('custom_registry_theme')
    expect(getAppIconNamesForProvider('custom_registry_theme')).toEqual(APP_ICON_PROVIDER_ICON_NAMES.tabler)
  })

  it('prefers registry labels for known icon provider bundles and keeps builtin fallback behavior', () => {
    const options = getAppIconProviderOptions('tabler', [
      { id: 'tabler', label: 'Registry Tabler', adapter: 'app.adapters.icons.tabler', fallback: 'fallback', isActive: true },
      { id: 'lucide', label: 'Registry Lucide', adapter: 'app.adapters.icons.lucide', fallback: 'replace', isActive: true },
      { id: 'other', label: 'Other', adapter: 'app.adapters.other', fallback: 'ignore', isActive: true },
    ])

    expect(options).toEqual([
      { value: 'tabler', label: 'Registry Tabler', source: 'registry' },
      { value: 'lucide', label: 'Registry Lucide', source: 'registry' },
    ])
  })

  it('falls back to builtin providers when registry bundles are inactive or unmapped', () => {
    const options = getAppIconProviderOptions('tabler', [
      { id: 'tabler', label: 'Registry Tabler', adapter: 'app.adapters.icons.tabler', fallback: 'fallback', isActive: false },
      { id: 'other', label: 'Other', adapter: 'app.adapters.other', fallback: 'ignore', isActive: true },
    ])

    expect(options).toEqual([
      { value: 'tabler', label: 'Tabler', source: 'builtin' },
      { value: 'lucide', label: 'Lucide', source: 'builtin' },
    ])
  })
})