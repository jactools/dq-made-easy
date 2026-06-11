#!/usr/bin/env bash
set -euo pipefail

# Purpose: Publish git-backed test proof JSON as human-readable documentation.
# What it does:
# - Reads committed proof JSON files from test-results/test-proof/<app_version>/<proof_type>/
# - Validates every proof JSON file against the canonical test-proof schema
# - Generates Markdown pages under docs/test-proof/<app_version>/<proof_type>/
# - Builds an index page linking every generated proof page
# Version: 1.2
# Last modified: 2026-05-27

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
proof_root="$repo_root/test-results/test-proof"
docs_root="$repo_root/docs/test-proof"
validate_script="$repo_root/scripts/validate_test_proof.sh"

"$validate_script"

PROOF_ROOT="$proof_root" DOCS_ROOT="$docs_root" REPO_ROOT="$repo_root" node --input-type=module <<'NODE'
import fs from 'node:fs'
import path from 'node:path'

const proofRoot = path.resolve(process.env.PROOF_ROOT)
const docsRoot = path.resolve(process.env.DOCS_ROOT)
const repoRoot = path.resolve(process.env.REPO_ROOT)

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true })
}

function removeGeneratedMarkdown(dirPath) {
  if (!fs.existsSync(dirPath)) {
    return
  }

  for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
    const entryPath = path.join(dirPath, entry.name)
    if (entry.isDirectory()) {
      removeGeneratedMarkdown(entryPath)
      if (fs.readdirSync(entryPath).length === 0) {
        fs.rmdirSync(entryPath)
      }
    } else if (/\.md$/i.test(entry.name)) {
      fs.rmSync(entryPath)
    }
  }
}

function walkJson(rootPath) {
  if (!fs.existsSync(rootPath)) {
    return []
  }

  const files = []
  const stack = [rootPath]
  while (stack.length > 0) {
    const current = stack.pop()
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const entryPath = path.join(current, entry.name)
      if (entry.isDirectory()) {
        if (current === rootPath && entry.name === 'rules') {
          continue
        }
        stack.push(entryPath)
      } else if (/\.json$/i.test(entry.name)) {
        files.push(entryPath)
      }
    }
  }

  return files.sort((left, right) => left.localeCompare(right))
}

function mdEscape(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\|/g, '\\|')
    .replace(/\r?\n/g, '<br />')
}

function titleCase(value) {
  return String(value)
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function proofTitle(proof, fallbackName) {
  if (typeof proof.title === 'string' && proof.title.trim()) {
    return proof.title.trim()
  }
  if (typeof proof.summary === 'string' && proof.summary.trim()) {
    return proof.summary.trim()
  }
  if (typeof proof.proof_id === 'string' && proof.proof_id.trim()) {
    return titleCase(proof.proof_id)
  }
  return titleCase(fallbackName.replace(/\.json$/i, ''))
}

function markdownList(items) {
  if (!Array.isArray(items) || items.length === 0) {
    return ''
  }

  return items.map((item) => `- ${mdEscape(item)}`).join('\n')
}

function scalarRows(proof) {
  const preferred = [
    'app_version',
    'proof_id',
    'proof_type',
    'feature',
    'status',
    'executed_at_utc',
    'test_file_count',
    'test_count',
    'command',
    'raw_evidence_directory',
  ]
  const rows = []
  const seen = new Set(['title', 'summary'])

  for (const key of preferred) {
    if (Object.prototype.hasOwnProperty.call(proof, key)) {
      const value = proof[key]
      if (value === null || ['string', 'number', 'boolean'].includes(typeof value)) {
        rows.push([key, value])
        seen.add(key)
      }
    }
  }

  for (const [key, value] of Object.entries(proof)) {
    if (seen.has(key)) {
      continue
    }
    if (value === null || ['string', 'number', 'boolean'].includes(typeof value)) {
      rows.push([key, value])
    }
  }

  return rows
}

function renderObjectSection(title, value) {
  if (!value || typeof value !== 'object') {
    return ''
  }

  return `\n## ${title}\n\n\`\`\`json\n${JSON.stringify(value, null, 2)}\n\`\`\`\n`
}

function relativeFromDocsPage(docsPagePath, targetPath) {
  return path.relative(path.dirname(docsPagePath), targetPath).replace(/\\/g, '/')
}

function renderProofPage(proof, sourcePath, outputPath) {
  const sourceRelative = path.relative(repoRoot, sourcePath).replace(/\\/g, '/')
  const title = proofTitle(proof, path.basename(sourcePath))
  const rows = scalarRows(proof)
  const table = rows.length > 0
    ? ['| Field | Value |', '| --- | --- |', ...rows.map(([key, value]) => `| ${mdEscape(titleCase(key))} | ${mdEscape(value)} |`)].join('\n')
    : 'No scalar metadata fields were present.'
  const sourceLink = relativeFromDocsPage(outputPath, sourcePath)

  const sections = []
  if (typeof proof.summary === 'string' && proof.summary.trim()) {
    sections.push(`## Summary\n\n${mdEscape(proof.summary)}`)
  }
  sections.push(`## Metadata\n\n${table}`)
  if (Array.isArray(proof.test_files) && proof.test_files.length > 0) {
    sections.push(`## Test Files\n\n${markdownList(proof.test_files)}`)
  }
  if (Array.isArray(proof.assertions) && proof.assertions.length > 0) {
    sections.push(`## Assertions\n\n${markdownList(proof.assertions)}`)
  }
  if (proof.proof_data) {
    sections.push(renderObjectSection('Proof Data', proof.proof_data).trim())
  }
  if (proof.metrics) {
    sections.push(renderObjectSection('Metrics', proof.metrics).trim())
  }
  if (proof.diagnostics) {
    sections.push(renderObjectSection('Diagnostics', proof.diagnostics).trim())
  }

  const frontmatterTitle = title.replace(/"/g, '\\"')
  return `---\ntitle: "${frontmatterTitle}"\ndescription: "Human-readable test proof generated from ${sourceRelative}."\n---\n\n# ${mdEscape(title)}\n\nThis page was generated from [${sourceRelative}](${sourceLink}).\n\n${sections.filter(Boolean).join('\n\n')}\n`
}

ensureDir(docsRoot)
removeGeneratedMarkdown(docsRoot)

const proofFiles = walkJson(proofRoot)
const pages = []

for (const proofFile of proofFiles) {
  const relativeProofPath = path.relative(proofRoot, proofFile).replace(/\\/g, '/')
  const outputPath = path.join(docsRoot, relativeProofPath.replace(/\.json$/i, '.md'))
  ensureDir(path.dirname(outputPath))

  let proof
  try {
    proof = JSON.parse(fs.readFileSync(proofFile, 'utf8'))
  } catch (error) {
    throw new Error(`Invalid proof JSON at ${path.relative(repoRoot, proofFile)}: ${error.message}`)
  }
  const [versionRoot, proofTypeRoot] = relativeProofPath.split('/')
  if (!versionRoot || !proofTypeRoot) {
    throw new Error(`Proof JSON must live under test-results/test-proof/<app_version>/<proof_type>/: ${relativeProofPath}`)
  }

  if (versionRoot !== proof.app_version) {
    throw new Error(`Proof app_version mismatch at ${path.relative(repoRoot, proofFile)}: expected ${versionRoot}, got ${proof.app_version || '<missing>'}`)
  }

  if (proofTypeRoot !== proof.proof_type) {
    throw new Error(`Proof proof_type mismatch at ${path.relative(repoRoot, proofFile)}: expected ${proofTypeRoot}, got ${proof.proof_type || '<missing>'}`)
  }

  fs.writeFileSync(outputPath, renderProofPage(proof, proofFile, outputPath))
  pages.push({
    proof,
    proofPath: proofFile,
    outputPath,
    title: proofTitle(proof, path.basename(proofFile)),
  })
}

const indexRows = pages.map((page) => {
  const docRelative = path.relative(docsRoot, page.outputPath).replace(/\\/g, '/')
  const proofRelative = path.relative(repoRoot, page.proofPath).replace(/\\/g, '/')
  const appVersion = page.proof.app_version || docRelative.split('/')[0] || 'unknown'
  const type = page.proof.proof_type || docRelative.split('/')[1] || 'proof'
  const status = page.proof.status || page.proof.passed || 'recorded'
  return `| ${mdEscape(appVersion)} | [${mdEscape(page.title)}](${docRelative}) | ${mdEscape(type)} | ${mdEscape(status)} | \`${mdEscape(proofRelative)}\` |`
})

const indexContent = `---\ntitle: "Test Proof"\ndescription: "Human-readable test proof generated from git-backed proof JSON."\n---\n\n# Test Proof\n\nThis section is generated from committed JSON proof files under \`test-results/test-proof/<app_version>/<proof_type>/\`. Run \`scripts/publish_test_proof.sh\` after adding or changing proof JSON.\n\n${pages.length === 0 ? 'No test proof JSON files were found.' : ['| App Version | Proof | Type | Status | Source JSON |', '| --- | --- | --- | --- | --- |', ...indexRows].join('\n')}\n`

fs.writeFileSync(path.join(docsRoot, 'index.md'), indexContent)
console.log(`Published ${pages.length} test proof page(s) to ${path.relative(repoRoot, docsRoot)}`)
NODE
