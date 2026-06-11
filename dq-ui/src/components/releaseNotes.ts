export interface ReleaseNoteListBlock {
  type: 'list'
  ordered: boolean
  items: string[]
}

export interface ReleaseNoteParagraphBlock {
  type: 'paragraph'
  text: string
}

export interface ReleaseNoteSubheadingBlock {
  type: 'subheading'
  text: string
}

export interface ReleaseNoteCodeBlock {
  type: 'code'
  code: string
  language?: string
}

export interface ReleaseNoteTableBlock {
  type: 'table'
  headers: string[]
  rows: string[][]
}

export type ReleaseNoteBlock =
  | ReleaseNoteListBlock
  | ReleaseNoteParagraphBlock
  | ReleaseNoteSubheadingBlock
  | ReleaseNoteCodeBlock
  | ReleaseNoteTableBlock

export interface ReleaseNoteSection {
  title: string
  blocks: ReleaseNoteBlock[]
}

export interface ReleaseNote {
  version: string
  date: string
  title: string
  sections: ReleaseNoteSection[]
}

const RELEASE_HEADER_REGEX = /^##\s+v([^\s(]+)(?:\s+(?:—|-+)\s+(.+?))?(?:\s+\(([^)]+)\))?\s*$/

function stripInlineMarkdown(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    .trim()
}

function normalizeHeading(text: string): string {
  return stripInlineMarkdown(text.replace(/^#+\s*/, '').trim())
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => stripInlineMarkdown(cell.trim()))
}

function hasContent(section: ReleaseNoteSection): boolean {
  return section.blocks.length > 0
}

function parseReleaseBody(lines: string[]): ReleaseNoteSection[] {
  const sections: ReleaseNoteSection[] = []
  let currentSection: ReleaseNoteSection = { title: 'Overview', blocks: [] }
  let index = 0

  const pushSection = () => {
    if (hasContent(currentSection)) {
      sections.push(currentSection)
    }
  }

  while (index < lines.length) {
    const rawLine = lines[index]
    const trimmed = rawLine.trim()

    if (!trimmed || trimmed === '---') {
      index += 1
      continue
    }

    if (trimmed.startsWith('### ')) {
      pushSection()
      currentSection = {
        title: normalizeHeading(trimmed.slice(4)),
        blocks: [],
      }
      index += 1
      continue
    }

    if (trimmed.startsWith('#### ')) {
      currentSection.blocks.push({
        type: 'subheading',
        text: normalizeHeading(trimmed.slice(5)),
      })
      index += 1
      continue
    }

    if (trimmed.startsWith('```')) {
      const language = trimmed.slice(3).trim() || undefined
      const codeLines: string[] = []
      index += 1

      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }

      if (index < lines.length) {
        index += 1
      }

      currentSection.blocks.push({
        type: 'code',
        code: codeLines.join('\n').trimEnd(),
        language,
      })
      continue
    }

    if (trimmed.startsWith('|')) {
      const tableLines: string[] = []
      while (index < lines.length && lines[index].trim().startsWith('|')) {
        tableLines.push(lines[index].trim())
        index += 1
      }

      if (tableLines.length >= 2) {
        const headers = parseTableRow(tableLines[0])
        const rows = tableLines
          .slice(2)
          .map(parseTableRow)
          .filter((row) => row.some((cell) => cell.length > 0))

        currentSection.blocks.push({
          type: 'table',
          headers,
          rows,
        })
      }
      continue
    }

    const unorderedMatch = trimmed.match(/^[-*]\s+(.*)$/)
    if (unorderedMatch) {
      const items: string[] = []

      while (index < lines.length) {
        const candidate = lines[index].trim()
        const match = candidate.match(/^[-*]\s+(.*)$/)
        if (!match) {
          break
        }
        items.push(stripInlineMarkdown(match[1]))
        index += 1
      }

      currentSection.blocks.push({ type: 'list', ordered: false, items })
      continue
    }

    const orderedMatch = trimmed.match(/^\d+\.\s+(.*)$/)
    if (orderedMatch) {
      const items: string[] = []

      while (index < lines.length) {
        const candidate = lines[index].trim()
        const match = candidate.match(/^\d+\.\s+(.*)$/)
        if (!match) {
          break
        }
        items.push(stripInlineMarkdown(match[1]))
        index += 1
      }

      currentSection.blocks.push({ type: 'list', ordered: true, items })
      continue
    }

    const paragraphLines: string[] = []
    while (index < lines.length) {
      const candidate = lines[index].trim()
      if (
        !candidate ||
        candidate === '---' ||
        candidate.startsWith('### ') ||
        candidate.startsWith('#### ') ||
        candidate.startsWith('```') ||
        candidate.startsWith('|') ||
        /^[-*]\s+/.test(candidate) ||
        /^\d+\.\s+/.test(candidate)
      ) {
        break
      }

      paragraphLines.push(stripInlineMarkdown(candidate.replace(/^>\s*/, '')))
      index += 1
    }

    const paragraph = paragraphLines.join(' ').trim()
    if (paragraph) {
      currentSection.blocks.push({ type: 'paragraph', text: paragraph })
    }
  }

  pushSection()

  return sections
}

export function parseReleaseNotesMarkdown(markdown: string): ReleaseNote[] {
  const lines = markdown.split(/\r?\n/)
  const releases: ReleaseNote[] = []
  let currentRelease: ReleaseNote | null = null
  let bodyLines: string[] = []

  const pushRelease = () => {
    if (!currentRelease) {
      return
    }

    currentRelease.sections = parseReleaseBody(bodyLines)
    releases.push(currentRelease)
  }

  for (const line of lines) {
    const match = line.match(RELEASE_HEADER_REGEX)
    if (match) {
      pushRelease()

      const [, version, explicitTitle, trailingValue] = match
      const title = stripInlineMarkdown(explicitTitle || trailingValue || 'Release Notes')
      const date = explicitTitle ? stripInlineMarkdown(trailingValue || '') : ''

      currentRelease = {
        version: stripInlineMarkdown(version),
        date,
        title,
        sections: [],
      }
      bodyLines = []
      continue
    }

    if (currentRelease) {
      bodyLines.push(line)
    }
  }

  pushRelease()

  return releases
}