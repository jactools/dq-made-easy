import type { IconProviderName } from '../../types/settings'
import type { AppIconName } from './appIconRegistry'
import { LUCIDE_ICON_NAMES } from './lucideAdapter'
import { TABLER_ICON_NAMES } from './tablerAdapter'

export type RegistryComponentBundle = {
  id: string
  label?: string
  description?: string
  adapter?: string | null
  fallback?: string
  priority?: number
  isActive?: boolean
}

export type AppIconProviderOption = {
  value: IconProviderName
  label: string
  source: 'builtin' | 'registry'
}

export const DEFAULT_ICON_PROVIDER: IconProviderName = 'tabler'

export const APP_ICON_PROVIDER_LABELS: Record<string, string> = {
  tabler: 'Tabler',
  lucide: 'Lucide',
}

export const APP_ICON_PROVIDER_ICON_NAMES: Record<string, readonly AppIconName[]> = {
  tabler: TABLER_ICON_NAMES,
  lucide: LUCIDE_ICON_NAMES,
}

const ICON_PROVIDER_ADAPTER_ALIASES: Record<IconProviderName, readonly string[]> = {
  tabler: ['tabler', 'app.adapters.icons.tabler', 'app.icon_provider.tabler'],
  lucide: ['lucide', 'app.adapters.icons.lucide', 'app.icon_provider.lucide'],
}

const normalizeLookupKey = (value: string): string => value.trim().toLowerCase()

const resolveRegistryIconProviderId = (bundle: RegistryComponentBundle): IconProviderName | null => {
  const bundleId = normalizeLookupKey(bundle.id)
  const adapter = normalizeLookupKey(bundle.adapter ?? '')

  if (bundleId in APP_ICON_PROVIDER_ICON_NAMES) {
    return bundleId as IconProviderName
  }

  for (const provider of Object.keys(ICON_PROVIDER_ADAPTER_ALIASES) as IconProviderName[]) {
    const aliases = ICON_PROVIDER_ADAPTER_ALIASES[provider]
    if (aliases.includes(bundleId) || aliases.includes(adapter)) {
      return provider
    }
  }

  return null
}

const getActiveRegistryIconProviderOptions = (
  registryBundles?: readonly RegistryComponentBundle[] | null,
): Partial<Record<IconProviderName, AppIconProviderOption>> => {
  const resolvedOptions: Partial<Record<IconProviderName, AppIconProviderOption>> = {}

  for (const bundle of [...(registryBundles ?? [])].sort((left, right) => (right.priority ?? 0) - (left.priority ?? 0))) {
    if (bundle.isActive === false) {
      continue
    }

    const provider = resolveRegistryIconProviderId(bundle)
    if (!provider || resolvedOptions[provider]) {
      continue
    }

    resolvedOptions[provider] = {
      value: provider,
      label: bundle.label?.trim() || APP_ICON_PROVIDER_LABELS[provider] || provider,
      source: 'registry',
    }
  }

  return resolvedOptions
}

export const normalizeIconProviderName = (value: unknown): IconProviderName => {
  if (typeof value === 'string') {
    const normalized = value.trim()
    return normalized || DEFAULT_ICON_PROVIDER
  }

  return DEFAULT_ICON_PROVIDER
}

export const getAppIconProviderLabel = (provider: IconProviderName): string => (
  APP_ICON_PROVIDER_LABELS[provider] || provider
)

export const getAppIconProviderOptions = (
  selectedProvider: IconProviderName,
  registryBundles?: readonly RegistryComponentBundle[] | null,
): readonly AppIconProviderOption[] => {
  const registryOptions = getActiveRegistryIconProviderOptions(registryBundles)
  const builtinOptions: readonly AppIconProviderOption[] = Object.keys(APP_ICON_PROVIDER_LABELS).map((provider) => {
    const normalizedProvider = provider as IconProviderName
    return {
      value: normalizedProvider,
      label: APP_ICON_PROVIDER_LABELS[normalizedProvider] || normalizedProvider,
      source: 'builtin',
    }
  })

  const mergedOptions = builtinOptions.map((option) => registryOptions[option.value] ?? option)

  if (mergedOptions.some((option) => option.value === selectedProvider)) {
    return mergedOptions
  }

  const selectedRegistryOption = registryOptions[selectedProvider]
  return [
    selectedRegistryOption ?? {
      value: selectedProvider,
      label: `${getAppIconProviderLabel(selectedProvider)} (current)`,
      source: 'builtin',
    },
    ...mergedOptions,
  ]
}

export const getAppIconNamesForProvider = (provider: IconProviderName): readonly AppIconName[] => (
  APP_ICON_PROVIDER_ICON_NAMES[provider] || APP_ICON_PROVIDER_ICON_NAMES[DEFAULT_ICON_PROVIDER]
)