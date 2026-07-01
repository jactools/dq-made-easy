import type { StylePackageName } from '../types/settings'

export type StylePackageOption = {
  value: StylePackageName
  label: string
}

export type StyleRegistryStyle = {
  id: string
  label?: string
  description?: string
  sourceRef?: string
  cssUrl?: string
  fallback?: string
  priority?: number
  isActive?: boolean
}

export const isLocalStylesheetHref = (href: string): boolean => {
  const trimmed = href.trim()
  if (!trimmed) {
    return false
  }

  if (trimmed.startsWith('/') || trimmed.startsWith('./') || trimmed.startsWith('../')) {
    return true
  }

  try {
    const baseOrigin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost'
    const resolvedUrl = new URL(trimmed, baseOrigin)
    return resolvedUrl.origin === baseOrigin
  } catch {
    return false
  }
}

export const DEFAULT_STYLE_PACKAGE: StylePackageName = 'data-web-css'

export const STYLE_PACKAGE_OPTIONS: readonly StylePackageOption[] = [
  { value: 'custom-built-package', label: 'Custom-built CSS package' },
  { value: 'tailwind', label: 'Tailwind CSS' },
  { value: 'astrowind', label: 'AstroWind' },
  { value: 'data-web-css', label: 'Data Web CSS' },
] as const

const STYLE_PACKAGE_LABELS: Record<string, string> = {
  'custom-built-package': 'Custom-built CSS package',
  'tailwind': 'Tailwind CSS',
  astrowind: 'AstroWind',
  'data-web-css': 'Data Web CSS',
}

const STYLE_PACKAGE_STYLESHEETS: Record<string, string> = {
  'custom-built-package': new URL('../style-packages/custom-built-package.css', import.meta.url).href,
  tailwind: '/style-packages/tailwind.css',
  astrowind: '/style-packages/astrowind.css',
  'data-web-css': '/style-packages/data-web.css',
}

export const normalizeStylePackageName = (value: unknown): StylePackageName => {
  if (typeof value === 'string') {
    const normalized = value.trim()
    return normalized || DEFAULT_STYLE_PACKAGE
  }

  return DEFAULT_STYLE_PACKAGE
}

export const getStylePackageLabel = (stylePackage: StylePackageName): string => STYLE_PACKAGE_LABELS[stylePackage] || stylePackage

export const getStylePackageOptions = (
  selectedStylePackage: StylePackageName,
  registryStyles?: readonly StyleRegistryStyle[] | null,
): readonly StylePackageOption[] => {
  const activeRegistryOptions = (registryStyles ?? [])
    .filter((entry) => entry.isActive !== false && typeof entry.id === 'string' && entry.id.trim())
    .map((entry) => ({
      value: entry.id as StylePackageName,
      label: entry.label?.trim() || getStylePackageLabel(entry.id as StylePackageName),
    }))

  if (activeRegistryOptions.some((option) => option.value === selectedStylePackage)) {
    return activeRegistryOptions
  }

  return [
    { value: selectedStylePackage, label: `${getStylePackageLabel(selectedStylePackage)} (current)` },
    ...activeRegistryOptions,
  ]
}

export const getStylePackageStylesheetHref = (
  stylePackage: StylePackageName,
  registryStyles?: readonly StyleRegistryStyle[] | null,
): string | undefined => {
  const registryStyle = registryStyles?.find((entry) => entry.isActive !== false && entry.id === stylePackage)
  const registryHref = registryStyle?.cssUrl?.trim()
  if (registryHref && isLocalStylesheetHref(registryHref)) {
    return registryHref
  }

  return STYLE_PACKAGE_STYLESHEETS[stylePackage]
}