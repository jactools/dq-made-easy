/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render } from '@testing-library/react'

import { StyleThemeProvider } from './StyleThemeContext'
import { getStylePackageStylesheetHref } from './styleThemeCatalog'

afterEach(() => {
  cleanup()
})

describe('StyleThemeProvider', () => {
  it('resolves local registry stylesheet urls before built-in package mappings', () => {
    expect(
      getStylePackageStylesheetHref('custom-registry-theme', [
        { id: 'custom-registry-theme', cssUrl: '/themes/custom.css' },
      ]),
    ).toBe('/api/themes/custom.css')
  })

  it('ignores remote registry stylesheet urls', () => {
    expect(
      getStylePackageStylesheetHref('custom-registry-theme', [
        { id: 'custom-registry-theme', cssUrl: 'https://cdn.example/themes/custom.css' },
      ]),
    ).toBeUndefined()
  })

  it('injects, updates, and removes the active stylesheet link', () => {
    const { rerender, unmount } = render(
      <StyleThemeProvider
        stylePackage="custom-built-package"
        registryStyles={[{ id: 'custom-built-package', cssUrl: '/themes/custom-built.css' }]}
      >
        <div data-testid="child" />
      </StyleThemeProvider>,
    )

    expect(document.documentElement.getAttribute('data-style-package')).toBe('custom-built-package')

    const initialLink = document.getElementById('dq-style-package-stylesheet') as HTMLLinkElement | null
    expect(initialLink).toBeTruthy()
    expect(initialLink?.getAttribute('href')).toBe('/api/themes/custom-built.css')

    rerender(
      <StyleThemeProvider
        stylePackage="astrowind"
        registryStyles={[{ id: 'astrowind', cssUrl: '/themes/astrowind.css' }]}
      >
        <div data-testid="child" />
      </StyleThemeProvider>,
    )

    const updatedLink = document.getElementById('dq-style-package-stylesheet') as HTMLLinkElement | null
    expect(updatedLink).toBeTruthy()
    expect(updatedLink?.getAttribute('href')).toBe('/api/themes/astrowind.css')

    unmount()
    expect(document.getElementById('dq-style-package-stylesheet')).toBeNull()
  })
})