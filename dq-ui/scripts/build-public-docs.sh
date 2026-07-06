#!/usr/bin/env bash
# Purpose: Build and publish the public docs site into dq-ui/public/docs.
# What it does:
# - Copies repo docs and architecture content into the docs-site workspace.
# - Normalizes copied links so the Docusaurus build can resolve local targets.
# - Installs docs-site dependencies on demand when the local Docusaurus bin is missing.
# Version: 1.4
# Last modified: 2026-06-30

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ui_root="$(cd "$script_dir/.." && pwd)"
repo_root="$(cd "$ui_root/.." && pwd)"
docs_site_dir="$ui_root/docs-site"
docs_build_dir="$docs_site_dir/build"
docs_public_dir="$ui_root/public/docs"

copy_docs_tree() {
  local source_dir="$1"
  local target_path="$2"

  rm -rf "$target_path"
  mkdir -p "$target_path"
  cp -R "$source_dir"/. "$target_path"/
}

copy_docs_contents() {
  local source_dir="$1"
  local target_path="$2"

  mkdir -p "$target_path"
  cp -R "$source_dir"/. "$target_path"/
}

prepare_docs_tree() {
  local target_path="$1"

  rm -rf "$target_path"
  mkdir -p "$target_path"
}

normalize_copied_docs_links() {
  local docs_root="$1"
  local repo_root="$2"

  DOCS_ROOT="$docs_root" REPO_ROOT="$repo_root" node --input-type=module <<'NODE'
import fs from 'node:fs'
import path from 'node:path'

const docsRoot = path.resolve(process.env.DOCS_ROOT)
const repoRoot = path.resolve(process.env.REPO_ROOT)
const githubBlobBase = 'https://github.com/jactools/dq-rulebuilder/blob/main'
const repoSourcePrefixes = new Set([
  '.github',
  'db',
  'docker',
  'dq-api',
  'dq-architecture',
  'dq-base',
  'dq-db',
  'dq-domain-validation',
  'dq-edge',
  'dq-engine',
  'dq-keycloak',
  'dq-kong',
  'dq-llm',
  'dq-metadata',
  'dq-profiling',
  'dq-rules-ui',
  'dq-ui',
  'dq-utils',
  'memories',
  'observability',
  'scripts',
  'tests',
])

function walkMarkdown(rootDir) {
  const files = []
  const stack = [rootDir]

  while (stack.length > 0) {
    const dir = stack.pop()
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const entryPath = path.join(dir, entry.name)
      if (entry.isDirectory()) {
        stack.push(entryPath)
      } else if (/\.(md|mdx)$/i.test(entry.name)) {
        files.push(entryPath)
      }
    }
  }

  return files
}

function copiedToSourcePath(copiedPath) {
  const copiedRelativePath = path.relative(docsRoot, copiedPath).replace(/\\/g, '/')
  if (copiedRelativePath.startsWith('architecture/')) {
    return path.join(repoRoot, copiedRelativePath)
  }

  return path.join(repoRoot, 'docs', copiedRelativePath)
}

function sourceMarkdownRoute(sourcePath) {
  const sourceRelativePath = path.relative(repoRoot, sourcePath).replace(/\\/g, '/')
  let docsRelativePath = sourceRelativePath

  if (docsRelativePath.startsWith('docs/')) {
    docsRelativePath = docsRelativePath.slice('docs/'.length)
  } else if (!docsRelativePath.startsWith('architecture/')) {
    return `${githubBlobBase}/${sourceRelativePath}`
  }

  const parsed = path.posix.parse(docsRelativePath)
  if (parsed.dir === 'features' && parsed.name === 'FEATURES') {
    return '/docs/features/'
  }

  if (/^(README|index)$/i.test(parsed.name)) {
    const directory = parsed.dir
    return directory ? `/docs/${directory}/` : '/docs/'
  }

  return `/docs/${path.posix.join(parsed.dir, parsed.name)}/`
}

function isMarkdownFile(filePath) {
  return /\.(md|mdx)$/i.test(filePath)
}

const markdownByBaseName = new Map()
for (const rootPath of [path.join(repoRoot, 'docs'), path.join(repoRoot, 'architecture')]) {
  if (!fs.existsSync(rootPath)) {
    continue
  }

  for (const filePath of walkMarkdown(rootPath)) {
    const baseName = path.basename(filePath).replace(/\.(md|mdx)$/i, '')
    if (!markdownByBaseName.has(baseName)) {
      markdownByBaseName.set(baseName, [])
    }
    markdownByBaseName.get(baseName).push(filePath)
  }
}

function splitTarget(rawTarget) {
  const match = rawTarget.match(/^([^#?]*)([?#].*)?$/)
  return {
    pathname: match ? match[1] : rawTarget,
    suffix: match && match[2] ? match[2] : '',
  }
}

function rewriteTarget(rawTarget, copiedPath) {
  if (rawTarget.startsWith(`${repoRoot}/`)) {
    return `${githubBlobBase}/${path.relative(repoRoot, rawTarget).replace(/\\/g, '/')}`
  }

  if (rawTarget.includes('/dq-rulebuilder/')) {
    const repoRelativePath = rawTarget.slice(rawTarget.indexOf('/dq-rulebuilder/') + '/dq-rulebuilder/'.length)
    return `${githubBlobBase}/${repoRelativePath}`
  }

  if (rawTarget.startsWith('/docs/')) {
    const docsRelativePath = rawTarget.slice('/docs/'.length).replace(/\/$/, '')
    const firstSegment = docsRelativePath.split('/')[0]
    const copiedMarkdownPath = path.join(docsRoot, `${docsRelativePath}.md`)
    const copiedReadmePath = path.join(docsRoot, docsRelativePath, 'README.md')
    const copiedIndexPath = path.join(docsRoot, docsRelativePath, 'index.md')

    if (repoSourcePrefixes.has(firstSegment)) {
      return `${githubBlobBase}/${docsRelativePath}`
    }

    if (
      docsRelativePath &&
      !fs.existsSync(copiedMarkdownPath) &&
      !fs.existsSync(copiedReadmePath) &&
      !fs.existsSync(copiedIndexPath)
    ) {
      return `${githubBlobBase}/${docsRelativePath}.md`
    }
  }

  if (
    rawTarget === '' ||
    rawTarget.startsWith('#') ||
    rawTarget.startsWith('/') ||
    /^[a-z][a-z0-9+.-]*:/i.test(rawTarget)
  ) {
    return rawTarget
  }

  const { pathname, suffix } = splitTarget(rawTarget)
  const sourcePath = copiedToSourcePath(copiedPath)
  const resolvedPath = path.resolve(path.dirname(sourcePath), pathname)

  if (fs.existsSync(resolvedPath)) {
    if (isMarkdownFile(resolvedPath)) {
      return `${sourceMarkdownRoute(resolvedPath)}${suffix}`
    }

    const repoRelativePath = path.relative(repoRoot, resolvedPath).replace(/\\/g, '/')
    if (!repoRelativePath.startsWith('..') && !path.isAbsolute(repoRelativePath)) {
      return `${githubBlobBase}/${repoRelativePath}${suffix}`
    }
  }

  const docsSegmentIndex = pathname.indexOf('docs/')
  if (docsSegmentIndex >= 0) {
    const docsRelativePath = pathname.slice(docsSegmentIndex + 'docs/'.length)
    const candidatePath = path.join(repoRoot, 'docs', docsRelativePath)
    if (fs.existsSync(candidatePath) && isMarkdownFile(candidatePath)) {
      return `${sourceMarkdownRoute(candidatePath)}${suffix}`
    }
  }

  const baseName = path.basename(pathname).replace(/\.(md|mdx)$/i, '')
  const matches = markdownByBaseName.get(baseName) || []
  if (matches.length === 1) {
    return `${sourceMarkdownRoute(matches[0])}${suffix}`
  }

  if (/\.(md|mdx)$/i.test(pathname)) {
    const strippedPathname = pathname.replace(/^(\.\/|\.\.\/)+/, '')
    return `${githubBlobBase}/${strippedPathname}${suffix}`
  }

  const strippedPathname = pathname.replace(/^(\.\/|\.\.\/)+/, '')
  const firstSegment = strippedPathname.split('/')[0]
  if (strippedPathname.replace(/\/$/, '') === 'runbooks') {
    return `/docs/runbooks/${suffix}`
  }

  const repoRootCandidate = path.join(repoRoot, strippedPathname)
  if (fs.existsSync(repoRootCandidate)) {
    return `${githubBlobBase}/${strippedPathname}${suffix}`
  }

  if (strippedPathname === '.env' || /^docker-compose.*\.ya?ml$/i.test(strippedPathname)) {
    return `${githubBlobBase}/${strippedPathname}${suffix}`
  }

  if (repoSourcePrefixes.has(firstSegment)) {
    return `${githubBlobBase}/${strippedPathname}${suffix}`
  }

  return rawTarget
}

function sanitizeMarkdownForMdx(content) {
  const lines = content.split('\n')
  let inFence = false

  return lines.map((line) => {
    if (/^\s*```/.test(line)) {
      inFence = !inFence
      return line
    }

    if (inFence) {
      return line
    }

    return line
      .replace(/`([^`\n]+)`/g, (_match, code) => `\`${code.replace(/\|/g, '\\|')}\``)
      .replace(/<(?=[0-9=$,]|[A-Za-z][A-Za-z0-9_-]*>)/g, '&lt;')
      .replace(/&lt;([A-Za-z][A-Za-z0-9_-]*)>/g, '&lt;$1&gt;')
      .replace(/\$\{/g, () => '$&#123;')
      .replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (_match, placeholder) => `&#123;${placeholder}&#125;`)
  }).join('\n')
}

for (const copiedPath of walkMarkdown(docsRoot)) {
  const original = fs.readFileSync(copiedPath, 'utf8')
  const rewrittenLinks = original.replace(/(?<!\!)\]\(([^)\s]+)\)/g, (match, target) => {
    const rewrittenTarget = rewriteTarget(target, copiedPath)
    return rewrittenTarget === target ? match : `](${rewrittenTarget})`
  })
  const rewritten = copiedPath.endsWith('.md') ? sanitizeMarkdownForMdx(rewrittenLinks) : rewrittenLinks

  if (rewritten !== original) {
    fs.writeFileSync(copiedPath, rewritten)
  }
}
NODE
}

if [[ ! -f "$docs_site_dir/package.json" ]]; then
  echo "[build-public-docs] Missing docs-site package.json at $docs_site_dir" >&2
  exit 1
fi

if [[ ! -x "$docs_site_dir/node_modules/.bin/docusaurus" ]]; then
  echo "[build-public-docs] Installing docs-site dependencies" >&2
  (cd "$repo_root" && npm --prefix "$docs_site_dir" install --include=dev --no-audit --no-fund --package-lock=false)
fi

if [[ -x "$repo_root/scripts/publish_test_proof.sh" ]]; then
  "$repo_root/scripts/publish_test_proof.sh"
else
  echo "[build-public-docs] Skipping test proof publishing; helper not available at $repo_root/scripts/publish_test_proof.sh" >&2
fi

prepare_docs_tree "$docs_site_dir/docs"
if [[ -d "$repo_root/docs" ]]; then
  copy_docs_contents "$repo_root/docs" "$docs_site_dir/docs"
else
  echo "[build-public-docs] Skipping repo docs copy; source directory not available at $repo_root/docs" >&2
fi
if [[ -d "$repo_root/architecture" ]]; then
  copy_docs_tree "$repo_root/architecture" "$docs_site_dir/docs/architecture"
else
  echo "[build-public-docs] Skipping architecture copy; source directory not available at $repo_root/architecture" >&2
fi
rm -f \
  "$docs_site_dir/docs/README.md" \
  "$docs_site_dir/docs/user-manuals/README.md" \
  "$docs_site_dir/docs/features/README.md" \
  "$docs_site_dir/docs/status/current/README.md" \
  "$docs_site_dir/docs/releases/README.md" \
  "$docs_site_dir/docs/engineering-decisions/README.md" \
  "$docs_site_dir/docs/architecture/README.md"
normalize_copied_docs_links "$docs_site_dir/docs" "$repo_root"

npm --prefix "$docs_site_dir" run build

rm -rf "$docs_public_dir"
mkdir -p "$docs_public_dir"
cp -R "$docs_build_dir"/. "$docs_public_dir"/