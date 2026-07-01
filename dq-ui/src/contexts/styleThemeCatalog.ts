import type { StylePackageName } from '../types/settings'

export type StylePackageOption = {
  value: StylePackageName
  label: string
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

export const getStylePackageStylesheetHref = (stylePackage: StylePackageName): string | undefined => STYLE_PACKAGE_STYLESHEETS[stylePackage]