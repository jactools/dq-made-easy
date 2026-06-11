import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import postcss from 'postcss'

const srcRoot = resolve(__dirname)

const collectCssFiles = (relativeDir = ''): string[] => {
  const entries = readdirSync(resolve(srcRoot, relativeDir), { withFileTypes: true })
  const cssFiles: string[] = []

  for (const entry of entries) {
    const relativePath = relativeDir ? `${relativeDir}/${entry.name}` : entry.name

    if (entry.isDirectory()) {
      cssFiles.push(...collectCssFiles(relativePath))
      continue
    }

    if (entry.isFile() && entry.name.endsWith('.css')) {
      cssFiles.push(relativePath)
    }
  }

  return cssFiles.sort()
}

const formatCssParseError = (relativePath: string, error: unknown): string => {
  const syntaxError = error as { line?: number; column?: number; reason?: string }
  const location = syntaxError.line && syntaxError.column
    ? `${syntaxError.line}:${syntaxError.column}`
    : 'unknown location'

  if (error instanceof Error) {
    return `${relativePath}:${location} ${syntaxError.reason || error.message}`
  }

  return `${relativePath}:${location} ${String(error)}`
}

describe('source CSS syntax guard', () => {
  it('parses every source CSS file with PostCSS', () => {
    const failures: string[] = []

    for (const relativePath of collectCssFiles()) {
      const absolutePath = resolve(srcRoot, relativePath)
      const source = readFileSync(absolutePath, 'utf8')

      try {
        postcss.parse(source, { from: absolutePath })
      } catch (error) {
        failures.push(formatCssParseError(relativePath, error))
      }
    }

    expect(failures).toEqual([])
  })
})