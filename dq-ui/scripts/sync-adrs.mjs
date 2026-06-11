import fs from 'node:fs'
import path from 'node:path'

const uiRoot = process.cwd()
const sourceDir = path.resolve(uiRoot, '../architecture/adr')
const targetDir = path.resolve(uiRoot, 'public/architecture/adr')
const releaseNotesSource = path.resolve(uiRoot, '../RELEASE_NOTES_USER.md')
const releaseNotesTarget = path.resolve(uiRoot, 'public/release-notes/RELEASE_NOTES_USER.md')

if (!fs.existsSync(sourceDir)) {
  console.error(`[sync-adrs] Source directory not found: ${sourceDir}`)
  process.exit(1)
}

fs.mkdirSync(targetDir, { recursive: true })

// Remove previously copied ADR markdown files so deleted ADRs don't linger in public assets.
for (const entry of fs.readdirSync(targetDir)) {
  if (entry.toLowerCase().endsWith('.md')) {
    fs.rmSync(path.join(targetDir, entry), { force: true })
  }
}

const adrFiles = fs
  .readdirSync(sourceDir)
  .filter((entry) => entry.toLowerCase().endsWith('.md'))

for (const fileName of adrFiles) {
  fs.copyFileSync(path.join(sourceDir, fileName), path.join(targetDir, fileName))
}

if (!fs.existsSync(releaseNotesSource)) {
  console.error(`[sync-adrs] Release notes file not found: ${releaseNotesSource}`)
  process.exit(1)
}

fs.mkdirSync(path.dirname(releaseNotesTarget), { recursive: true })
fs.copyFileSync(releaseNotesSource, releaseNotesTarget)

console.log(`[sync-adrs] Copied ${adrFiles.length} ADR files to ${targetDir}`)
console.log(`[sync-adrs] Copied release notes to ${releaseNotesTarget}`)
