import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import postcss, { type Declaration, type Rule } from 'postcss'

export interface CssSourceFile {
  relativePath: string
  absolutePath: string
  source: string
}

export interface CssDuplicationOccurrence {
  relativePath: string
  selector: string
  line: number
  column: number
}

export interface CssDuplicationGroup {
  declarationBlock: string
  declarationCount: number
  occurrences: CssDuplicationOccurrence[]
}

export interface CssDuplicationReport {
  scannedFiles: number
  scannedRules: number
  threshold: number
  duplicateGroups: CssDuplicationGroup[]
}

export interface CssDuplicationReportOptions {
  minOccurrences?: number
  limit?: number
}

const srcRoot = resolve(__dirname, '..')

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

const normalizeDeclaration = (declaration: Declaration): string => {
  const property = declaration.prop.trim()
  const value = declaration.value.trim().replace(/\s+/g, ' ')
  const important = declaration.important ? ' !important' : ''

  return `${property}: ${value}${important};`
}

const ruleSignature = (rule: Rule): string | null => {
  const declarations = rule.nodes
    ?.filter((node): node is Declaration => node.type === 'decl')
    .map(normalizeDeclaration) ?? []

  if (declarations.length === 0) {
    return null
  }

  return declarations.join('\n')
}

const lineOrDefault = (value: number | undefined): number => value || 0

const buildReportFromSources = (
  sources: readonly CssSourceFile[],
  options: CssDuplicationReportOptions = {},
): CssDuplicationReport => {
  const minOccurrences = Math.max(options.minOccurrences ?? 3, 2)
  const limit = options.limit ?? 15
  const groupsBySignature = new Map<
    string,
    {
      declarationBlock: string
      declarationCount: number
      occurrences: CssDuplicationOccurrence[]
    }
  >()

  let scannedRules = 0

  for (const sourceFile of sources) {
    const root = postcss.parse(sourceFile.source, { from: sourceFile.absolutePath })

    root.walkRules((rule) => {
      scannedRules += 1
      const signature = ruleSignature(rule)

      if (!signature) {
        return
      }

      const existingGroup = groupsBySignature.get(signature)
      const occurrence: CssDuplicationOccurrence = {
        relativePath: sourceFile.relativePath,
        selector: rule.selector,
        line: lineOrDefault(rule.source?.start?.line),
        column: lineOrDefault(rule.source?.start?.column),
      }

      if (existingGroup) {
        existingGroup.occurrences.push(occurrence)
        return
      }

      groupsBySignature.set(signature, {
        declarationBlock: signature,
        declarationCount: signature.split('\n').length,
        occurrences: [occurrence],
      })
    })
  }

  const duplicateGroups = Array.from(groupsBySignature.values())
    .filter((group) => group.occurrences.length >= minOccurrences)
    .sort((left, right) => {
      const occurrenceDelta = right.occurrences.length - left.occurrences.length
      if (occurrenceDelta !== 0) {
        return occurrenceDelta
      }

      const declarationDelta = right.declarationCount - left.declarationCount
      if (declarationDelta !== 0) {
        return declarationDelta
      }

      return left.declarationBlock.localeCompare(right.declarationBlock)
    })
    .slice(0, limit)

  return {
    scannedFiles: sources.length,
    scannedRules,
    threshold: minOccurrences,
    duplicateGroups,
  }
}

export const createCssDuplicationReport = (
  options: CssDuplicationReportOptions = {},
): CssDuplicationReport => {
  const sources = collectCssFiles().map((relativePath) => {
    const absolutePath = resolve(srcRoot, relativePath)

    return {
      relativePath,
      absolutePath,
      source: readFileSync(absolutePath, 'utf8'),
    }
  })

  return buildReportFromSources(sources, options)
}

export const createCssDuplicationReportFromSources = (
  sources: readonly CssSourceFile[],
  options: CssDuplicationReportOptions = {},
): CssDuplicationReport => buildReportFromSources(sources, options)

const formatOccurrence = (occurrence: CssDuplicationOccurrence): string => {
  return `- ${occurrence.relativePath}:${occurrence.line}:${occurrence.column} ${occurrence.selector}`
}

export const formatCssDuplicationReport = (report: CssDuplicationReport): string => {
  const lines: string[] = [
    'UI-PORT-7G CSS duplication report',
    `- source files scanned: ${report.scannedFiles}`,
    `- rule blocks scanned: ${report.scannedRules}`,
    `- threshold: repeated at least ${report.threshold} times`,
    `- repeated declaration blocks: ${report.duplicateGroups.length}`,
  ]

  if (report.duplicateGroups.length === 0) {
    lines.push('- no repeated declaration blocks met the threshold')
    return lines.join('\n')
  }

  report.duplicateGroups.forEach((group, index) => {
    lines.push('')
    lines.push(`${index + 1}. ${group.occurrences.length} occurrences`)
    lines.push('   declarations:')
    for (const declarationLine of group.declarationBlock.split('\n')) {
      lines.push(`     ${declarationLine}`)
    }
    lines.push('   occurrences:')
    for (const occurrence of group.occurrences) {
      lines.push(`     ${formatOccurrence(occurrence)}`)
    }
  })

  return lines.join('\n')
}