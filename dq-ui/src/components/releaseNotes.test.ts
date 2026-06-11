import { describe, expect, it } from 'vitest'

import { parseReleaseNotesMarkdown } from './releaseNotes'

describe('parseReleaseNotesMarkdown', () => {
  it('treats a hyphenated release header as the latest release', () => {
    const markdown = [
      '# Release Notes — For Users',
      '',
      '## v0.11.2 - Definition Mappings AI-Assisted Data Definition Manual (May 27, 2026)',
      '',
      "### ✅ What's Updated",
      '',
      '- UI package version bumped to 0.11.2',
      '',
      '## v0.10.5 — Public Documentation Portal (May 22, 2026)',
      '',
      "### ✅ What's Updated",
      '',
      '- UI package version bumped to 0.10.5',
    ].join('\n')

    const releases = parseReleaseNotesMarkdown(markdown)

    expect(releases).toHaveLength(2)
    expect(releases[0]?.version).toBe('0.11.2')
    expect(releases[0]?.title).toBe('Definition Mappings AI-Assisted Data Definition Manual')
    expect(releases[0]?.date).toBe('May 27, 2026')
  })
})