import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const sourcePath = resolve(process.cwd(), 'src/components/HierarchyTree.tsx')

describe('HierarchyTree contract', () => {
  it('uses the app-owned button and icon primitives', () => {
    const source = readFileSync(sourcePath, 'utf8')

    expect(source).toContain("import { AppButton, AppIcon, type AppIconName } from './app-primitives'")
    expect(source).not.toContain("<button")
    expect(source).toContain('<AppButton')
    expect(source).toContain('<AppIcon')
  })
})