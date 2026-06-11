import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const srcRoot = resolve(__dirname, '../..')

const allowedLegacyIconSources = new Set([
  'components/CheckTypeForm/ReferentialIntegrityPickerDrawer.tsx',
  'components/HierarchyTree.tsx',
])

const collectRawRdsIconSources = () => {
  const legacyIconPattern = new RegExp(['r', 'ds-icon-[A-Za-z0-9-]+'].join(''), 'g')
  const sourceFiles: string[] = []

  const walk = (relativeDir: string) => {
    for (const entry of readdirSync(resolve(srcRoot, relativeDir), { withFileTypes: true })) {
      const relativePath = relativeDir ? `${relativeDir}/${entry.name}` : entry.name
      if (entry.isDirectory()) {
        walk(relativePath)
        continue
      }

      if (entry.isFile() && /\.(ts|tsx)$/.test(entry.name)) {
        sourceFiles.push(relativePath)
      }
    }
  }

  walk('components')
  walk('contexts')

  const offendingSources = new Set<string>()

  for (const relativePath of sourceFiles) {
    if (allowedLegacyIconSources.has(relativePath)) {
      continue
    }

    const source = readFileSync(resolve(srcRoot, relativePath), 'utf8')
    if (legacyIconPattern.test(source)) {
      offendingSources.add(relativePath)
    }
  }

  return [...offendingSources].sort()
}

describe('app icon portability', () => {
  it('keeps raw legacy icon names out of app-owned feature sources', () => {
    expect(collectRawRdsIconSources()).toEqual([])
  })
})