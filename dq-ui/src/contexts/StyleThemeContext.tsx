import React, { createContext, useContext, useLayoutEffect, useMemo, type ReactNode } from 'react'

import type { StylePackageName } from '../types/settings'
import {
  DEFAULT_STYLE_PACKAGE,
  STYLE_PACKAGE_OPTIONS,
  type StyleRegistryStyle,
  getStylePackageStylesheetHref,
  normalizeStylePackageName,
  toBrowserStylesheetHref,
} from './styleThemeCatalog'

export interface StyleThemeContextType {
  stylePackage: StylePackageName
  stylePackageOptions: readonly { value: StylePackageName; label: string }[]
}

const STYLE_PACKAGE_STYLESHEET_LINK_ID = 'dq-style-package-stylesheet'

const StyleThemeContext = createContext<StyleThemeContextType | undefined>(undefined)

export const StyleThemeProvider: React.FC<{ children: ReactNode; stylePackage: StylePackageName; registryStyles?: readonly StyleRegistryStyle[] | null }> = ({
  children,
  stylePackage,
  registryStyles,
}) => {
  const normalizedStylePackage = normalizeStylePackageName(stylePackage)
  const registryStyleHref = useMemo(() => {
    const registryStyle = registryStyles?.find((entry) => entry.isActive !== false && entry.id === normalizedStylePackage)
    const href = registryStyle?.cssUrl?.trim() || undefined
    return href ? toBrowserStylesheetHref(href) : undefined
  }, [normalizedStylePackage, registryStyles])
  const selectedHref = useMemo(
    () => getStylePackageStylesheetHref(normalizedStylePackage, registryStyles),
    [normalizedStylePackage, registryStyles],
  )

  useLayoutEffect(() => {
    const root = document.documentElement
    root.setAttribute('data-style-package', normalizedStylePackage)

    const existingLink = document.getElementById(STYLE_PACKAGE_STYLESHEET_LINK_ID) as HTMLLinkElement | null

    if (!selectedHref || (normalizedStylePackage === DEFAULT_STYLE_PACKAGE && !registryStyleHref)) {
      existingLink?.remove()
      return
    }

    const link = existingLink ?? document.createElement('link')
    link.id = STYLE_PACKAGE_STYLESHEET_LINK_ID
    link.rel = 'stylesheet'
    link.href = selectedHref
    link.dataset.stylePackage = normalizedStylePackage

    if (!existingLink) {
      document.head.appendChild(link)
    }

    return () => {
      link.remove()
    }
  }, [normalizedStylePackage, registryStyleHref, selectedHref])

  const value = useMemo<StyleThemeContextType>(
    () => ({
      stylePackage: normalizedStylePackage,
      stylePackageOptions: STYLE_PACKAGE_OPTIONS,
    }),
    [normalizedStylePackage],
  )

  return <StyleThemeContext.Provider value={value}>{children}</StyleThemeContext.Provider>
}

export const useStyleTheme = (): StyleThemeContextType => {
  const context = useContext(StyleThemeContext)
  if (!context) {
    throw new Error('useStyleTheme must be used within a StyleThemeProvider')
  }
  return context
}