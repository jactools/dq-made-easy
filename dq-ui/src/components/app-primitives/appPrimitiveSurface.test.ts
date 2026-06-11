import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import * as appPrimitives from './index'
import {
  APP_PRIMITIVE_COMPONENT_EXPORTS,
  APP_PRIMITIVE_SUPPORT_EXPORTS,
  APP_PRIMITIVE_TYPE_EXPORTS,
} from './appPrimitiveSurface'

const srcRoot = resolve(__dirname, '../..')

const readSource = (relativePath: string) => readFileSync(resolve(srcRoot, relativePath), 'utf8')

const collectSourceFiles = (relativeDir: string): string[] => {
  const sourceFiles: string[] = []

  for (const entry of readdirSync(resolve(srcRoot, relativeDir), { withFileTypes: true })) {
    const relativePath = `${relativeDir}/${entry.name}`
    if (entry.isDirectory()) {
      sourceFiles.push(...collectSourceFiles(relativePath))
    } else if (/\.(ts|tsx)$/.test(entry.name)) {
      sourceFiles.push(relativePath)
    }
  }

  return sourceFiles
}

describe('app primitive surface', () => {
  it('exports only the canonical primitive runtime surface from the barrel', () => {
    const allowedRuntimeExports = new Set([
      ...APP_PRIMITIVE_COMPONENT_EXPORTS,
      ...APP_PRIMITIVE_SUPPORT_EXPORTS,
    ])

    expect(Object.keys(appPrimitives).sort()).toEqual([...allowedRuntimeExports].sort())
  })

  it('publishes the canonical primitive type exports from the barrel', () => {
    const indexSource = readFileSync(resolve(__dirname, 'index.ts'), 'utf8')

    for (const exportName of APP_PRIMITIVE_TYPE_EXPORTS) {
      expect(indexSource, `${exportName} should be exported from app-primitives`).toContain(exportName)
    }

    expect(indexSource).not.toContain('RDSIcon')
    expect(indexSource).not.toContain('LEGACY_RDS')
  })

  it('keeps feature code importing primitives through the canonical barrel', () => {
    const sourceFiles = [
      ...collectSourceFiles('components'),
      ...collectSourceFiles('types'),
    ]

    const offenders = sourceFiles
      .filter((relativePath) => !relativePath.includes('/app-primitives/'))
      .filter((relativePath) => !/\.(test|spec)\.(ts|tsx)$/.test(relativePath))
      .filter((relativePath) => /from ['"].*app-primitives\//.test(readSource(relativePath)))

    expect(offenders).toEqual([])
  })
})