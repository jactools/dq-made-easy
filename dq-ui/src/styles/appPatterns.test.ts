import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const srcRoot = resolve(__dirname, '..')

const readSource = (relativePath: string) => readFileSync(resolve(srcRoot, relativePath), 'utf8')

const cssBlock = (source: string, selector: string): string => {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = source.match(new RegExp(`${escapedSelector}\\s*\\{([\\s\\S]*?)\\n\\}`))
  return match?.[1] || ''
}

const legacyTokenPrefix = ['var(--', 'rd', 's-'].join('')

const requiredPatternSelectors = [
  '.app-page-shell',
  '.app-page-header',
  '.app-page-content',
  '.app-panel',
  '.app-panel__header',
  '.app-panel__body',
  '.app-stack',
  '.app-toolbar',
  '.app-action-row',
  '.app-meta-label',
  '.app-status-chip',
  '.app-empty-state',
  '.app-list',
  '.app-list-row',
]

describe('shared app styling patterns', () => {
  it('defines the canonical UI-PORT-7B layout and surface selectors on app tokens', () => {
    const patternsCss = readSource('styles/appPatterns.css')

    for (const selector of requiredPatternSelectors) {
      const block = cssBlock(patternsCss, selector)
      expect(block, `${selector} should exist`).not.toBe('')
      expect(block, `${selector} should use app-owned tokens only`).not.toContain(legacyTokenPrefix)
    }

    expect(patternsCss).toContain('--app-page-bg')
    expect(patternsCss).toContain('--app-surface-primary')
    expect(patternsCss).toContain('--app-border-subtle')
    expect(patternsCss).toContain('--app-hover-bg')
    expect(patternsCss).toContain('--app-selected-bg')
  })

  it('loads shared patterns after semantic tokens and before app/page CSS', () => {
    const mainSource = readSource('main.tsx')
    const themesImport = mainSource.indexOf("import './themes.css'")
    const patternsImport = mainSource.indexOf("import './styles/appPatterns.css'")
    const appCssImport = mainSource.indexOf("import './App.css'")

    expect(themesImport).toBeGreaterThan(-1)
    expect(patternsImport).toBeGreaterThan(themesImport)
    expect(appCssImport).toBeGreaterThan(patternsImport)
  })
})