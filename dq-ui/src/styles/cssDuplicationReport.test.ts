import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  createCssDuplicationReport,
  createCssDuplicationReportFromSources,
  formatCssDuplicationReport,
} from './cssDuplicationReport'

describe('css duplication report', () => {
  it('groups repeated declaration blocks from arbitrary css sources', () => {
    const report = createCssDuplicationReportFromSources([
      {
        relativePath: 'src/styles/a.css',
        absolutePath: resolve('/Users/jacbeekers/gitrepos/dq-rulebuilder/tmp/a.css'),
        source: '.alpha { display: flex; gap: 8px; }',
      },
      {
        relativePath: 'src/styles/b.css',
        absolutePath: resolve('/Users/jacbeekers/gitrepos/dq-rulebuilder/tmp/b.css'),
        source: '.beta { display: flex; gap: 8px; }',
      },
      {
        relativePath: 'src/styles/c.css',
        absolutePath: resolve('/Users/jacbeekers/gitrepos/dq-rulebuilder/tmp/c.css'),
        source: '.gamma { display: grid; }',
      },
    ], { minOccurrences: 2 })

    expect(report.scannedFiles).toBe(3)
    expect(report.scannedRules).toBe(3)
    expect(report.duplicateGroups).toHaveLength(1)
    expect(report.duplicateGroups[0].declarationCount).toBe(2)
    expect(report.duplicateGroups[0].occurrences).toHaveLength(2)
    expect(report.duplicateGroups[0].declarationBlock).toContain('display: flex;')
    expect(report.duplicateGroups[0].declarationBlock).toContain('gap: 8px;')
  })

  it('prints a review report for the real dq-ui source css tree', () => {
    const report = createCssDuplicationReport({ minOccurrences: 3, limit: 8 })
    const summary = formatCssDuplicationReport(report)

    expect(report.scannedFiles).toBeGreaterThan(0)
    expect(report.scannedRules).toBeGreaterThan(0)
    expect(summary).toContain('UI-PORT-7G CSS duplication report')
    expect(summary).toContain('threshold: repeated at least 3 times')

    console.info(summary)
  })
})