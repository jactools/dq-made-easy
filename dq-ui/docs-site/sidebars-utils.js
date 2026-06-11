const fs = require('fs')
const path = require('path')

function isDocFile(fileName) {
  return /\.(md|mdx)$/i.test(fileName)
}

function labelFromSegment(segment) {
  return segment
    .replace(/[-_]+/g, ' ')
    .trim()
    .split(/\s+/)
    .map((part) => (part === part.toUpperCase() ? part : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(' ')
}

function docIdFromRelativePath(relativePath) {
  return relativePath.replace(/\\/g, '/').replace(/\.(md|mdx)$/i, '')
}

function buildSidebarItems(rootDir, relativeDir = '', indexDocId = null) {
  const absoluteDir = path.join(rootDir, relativeDir)
  const entries = fs.readdirSync(absoluteDir, { withFileTypes: true })
  const visibleEntries = entries.filter((entry) => !entry.name.startsWith('_'))
  const docFiles = visibleEntries.filter((entry) => entry.isFile() && isDocFile(entry.name)).sort((left, right) => left.name.localeCompare(right.name))
  const directories = visibleEntries.filter((entry) => entry.isDirectory()).sort((left, right) => left.name.localeCompare(right.name))
  const items = []

  const indexFile = docFiles.find((entry) => /^index\.(md|mdx)$/i.test(entry.name)) || docFiles.find((entry) => /^README\.(md|mdx)$/i.test(entry.name))
  const skipFileNames = new Set(indexFile && /^index\.(md|mdx)$/i.test(indexFile.name) ? [indexFile.name, 'README.md', 'README.mdx'] : indexFile ? [indexFile.name] : [])
  if (indexFile) {
    const indexRelativePath = path.posix.join(relativeDir.replace(/\\/g, '/'), indexFile.name)
    items.push(indexDocId || docIdFromRelativePath(indexRelativePath))
  }

  for (const entry of docFiles) {
    if (skipFileNames.has(entry.name)) {
      continue
    }

    items.push(docIdFromRelativePath(path.posix.join(relativeDir.replace(/\\/g, '/'), entry.name)))
  }

  for (const entry of directories) {
    const childRelativeDir = path.posix.join(relativeDir.replace(/\\/g, '/'), entry.name)
    const childItems = buildSidebarItems(rootDir, childRelativeDir)
    if (childItems.length === 0) {
      continue
    }

    items.push({
      type: 'category',
      label: labelFromSegment(entry.name),
      items: childItems,
    })
  }

  return items
}

module.exports = {
  buildSidebarItems,
}