// @vitest-environment node

import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { afterEach, describe, expect, it } from 'vitest'

const uiRoot = process.cwd()
const sourceDir = path.resolve(uiRoot, '../docs/user-manuals')
const targetDir = path.resolve(uiRoot, 'public/user-manuals')
const scriptPath = path.resolve(uiRoot, 'scripts/sync-user-manuals.sh')
const tempSourcePath = path.join(sourceDir, 'zz-temporary-regression-card.md')
const tempTargetPath = path.join(targetDir, 'zz-temporary-regression-card.html')

function runPublisher() {
  execFileSync('bash', [scriptPath], { cwd: uiRoot, stdio: 'pipe' })
}

function removeTempCard() {
  if (fs.existsSync(tempSourcePath)) {
    fs.rmSync(tempSourcePath, { force: true })
  }
}

afterEach(() => {
  removeTempCard()
  runPublisher()
})

describe('sync-user-manuals publisher', () => {
  it('publishes manuals and removes deleted source cards on rebuild', () => {
    runPublisher()

    const indexPath = path.join(targetDir, 'index.html')
    const governancePath = path.join(targetDir, 'governance-terminology.html')

    expect(fs.existsSync(indexPath)).toBe(true)
    expect(fs.existsSync(governancePath)).toBe(true)

    const indexHtml = fs.readFileSync(indexPath, 'utf8')
    expect(indexHtml).toContain('href="/user-manuals/governance-terminology.html"')
    expect(indexHtml).toContain('User Manuals')
    expect(indexHtml).toContain('Data Quality Made Easy')
    expect(indexHtml).toContain('dq-made-easy-light.svg')
    expect(indexHtml).toContain('dq-made-easy-dark.svg')
    expect(indexHtml).toContain('manuals-search-input')
    expect(indexHtml).toContain('manuals-search-results')
    expect(indexHtml).toContain('manuals-quick-links')
    expect(indexHtml).toContain('href="#manuals-search-input"')
    expect(indexHtml).toContain('href="#current-cards"')
    expect(indexHtml).toContain('Generated on')
    expect(indexHtml).toContain('Responsible publisher: dq-rulebuilder maintainers.')
    expect(indexHtml).toContain('const manualsSearchIndex = [')
    expect(indexHtml).toContain('governance-terminology.html')
    expect(indexHtml).toContain('data-theme')
    expect(indexHtml).toContain('--font-primary')
    expect(indexHtml).toContain('--color-primary: #1a5999')
    expect(indexHtml).toContain('--color-nav-bg: #0d3c63')
    expect(indexHtml).toContain('--color-card-bg: #fff')
    expect(indexHtml).toContain("font-family: var(--font-primary);")
    expect(indexHtml).toContain('background: linear-gradient(180deg, var(--color-nav-bg) 0%, var(--color-primary-dark) 100%);')
    expect(indexHtml).not.toContain('_template')
    expect(indexHtml).not.toContain('_reference-template')

    const governanceHtml = fs.readFileSync(governancePath, 'utf8')
    expect(governanceHtml).toContain('<title>Governance Terminology Reference Card</title>')
    expect(governanceHtml).toContain('<table>')
    expect(governanceHtml).toContain('Typical app context')
    expect(governanceHtml).toContain('color-scheme: light dark')
    expect(governanceHtml).toContain('prefers-color-scheme: dark')
    expect(governanceHtml).toContain('manuals-brand')
    expect(governanceHtml).toContain('manuals-search-input')
    expect(governanceHtml).toContain('Generated on')
    expect(governanceHtml).toContain('Responsible publisher: dq-rulebuilder maintainers.')
    expect(governanceHtml).toContain('data-theme')
    expect(governanceHtml).toContain('--font-primary')
    expect(governanceHtml).toContain('--color-primary: #1a5999')
    expect(governanceHtml).toContain('--color-nav-bg: #0d3c63')
    expect(governanceHtml).toContain('background: linear-gradient(180deg, var(--color-nav-bg) 0%, var(--color-primary-dark) 100%);')

    fs.writeFileSync(
      tempSourcePath,
      [
        '# Temporary Regression Card',
        '',
        '**Time to read:** 1 minute',
        '**Last updated:** 2026-05-03',
        '',
        '## Item',
        'Temporary regression coverage.',
        '',
      ].join('\n'),
    )

    runPublisher()

    expect(fs.existsSync(tempTargetPath)).toBe(true)
    expect(fs.readFileSync(tempTargetPath, 'utf8')).toContain('<title>Temporary Regression Card</title>')

    fs.rmSync(tempSourcePath, { force: true })
    runPublisher()

    expect(fs.existsSync(tempTargetPath)).toBe(false)
  })
})