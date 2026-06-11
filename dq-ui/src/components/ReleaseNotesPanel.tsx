import React, { useEffect, useState } from 'react'
import './ReleaseNotesPanel.css'
import {
  type ReleaseNote,
  type ReleaseNoteBlock,
  parseReleaseNotesMarkdown,
} from './releaseNotes'

const RELEASE_NOTES_PATH = '/release-notes/RELEASE_NOTES_USER.md'

function renderBlock(block: ReleaseNoteBlock, key: string) {
  switch (block.type) {
    case 'subheading':
      return (
        <h4 key={key} className="release-subheading">
          {block.text}
        </h4>
      )
    case 'paragraph':
      return (
        <p key={key} className="release-paragraph">
          {block.text}
        </p>
      )
    case 'list': {
      const ListTag = block.ordered ? 'ol' : 'ul'
      const className = block.ordered ? 'section-items ordered' : 'section-items'

      return (
        <ListTag key={key} className={className}>
          {block.items.map((item, itemIndex) => (
            <li key={`${key}-${itemIndex}`}>{item}</li>
          ))}
        </ListTag>
      )
    }
    case 'code':
      return (
        <pre key={key} className="release-code-block">
          <code>{block.code}</code>
        </pre>
      )
    case 'table':
      return (
        <div key={key} className="release-table-wrapper">
          <table className="release-table">
            <thead>
              <tr>
                {block.headers.map((header, headerIndex) => (
                  <th key={`${key}-header-${headerIndex}`}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rowIndex) => (
                <tr key={`${key}-row-${rowIndex}`}>
                  {row.map((cell, cellIndex) => (
                    <td key={`${key}-cell-${rowIndex}-${cellIndex}`}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    default:
      return null
  }
}

export const ReleaseNotesPanel: React.FC = () => {
  const [releases, setReleases] = useState<ReleaseNote[]>([])
  const [expandedVersions, setExpandedVersions] = useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let isDisposed = false

    const loadReleaseNotes = async () => {
      try {
        setIsLoading(true)
        setLoadError(null)

        const response = await fetch(RELEASE_NOTES_PATH, { cache: 'no-cache' })
        if (!response.ok) {
          throw new Error(`Failed to load release notes (${response.status})`)
        }

        const markdown = await response.text()
        const parsedReleases = parseReleaseNotesMarkdown(markdown)

        if (isDisposed) {
          return
        }

        setReleases(parsedReleases)
        setExpandedVersions(
          parsedReleases[0] ? new Set([parsedReleases[0].version]) : new Set()
        )
      } catch (error) {
        if (!isDisposed) {
          setLoadError(error instanceof Error ? error.message : 'Unable to load release notes')
          setReleases([])
          setExpandedVersions(new Set())
        }
      } finally {
        if (!isDisposed) {
          setIsLoading(false)
        }
      }
    }

    void loadReleaseNotes()

    return () => {
      isDisposed = true
    }
  }, [])

  const toggleExpanded = (version: string) => {
    const next = new Set(expandedVersions)
    if (next.has(version)) {
      next.delete(version)
    } else {
      next.add(version)
    }
    setExpandedVersions(next)
  }

  if (isLoading) {
    return <div className="release-notes-state">Loading release notes…</div>
  }

  if (loadError) {
    return <div className="release-notes-state">{loadError}</div>
  }

  if (releases.length === 0) {
    return <div className="release-notes-state">No release notes are available.</div>
  }

  const latestRelease = releases[0]

  return (
    <>
      <div className="changelog-info">
        <div className="info-card">
          <div className="info-icon">📋</div>
          <div className="info-content">
            <h3>Latest Version: {latestRelease.version}</h3>
            <p>
              {latestRelease.title}
              {latestRelease.date ? ` — Released ${latestRelease.date}` : ''}
            </p>
          </div>
        </div>
      </div>

      <div className="releases-list">
        {releases.map((release) => (
          <div key={release.version} className="release-card">
            <div
              className="release-header"
              onClick={() => toggleExpanded(release.version)}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  toggleExpanded(release.version)
                }
              }}
            >
              <div className="release-title-group">
                <h2 className="release-title">v{release.version}</h2>
                {release.date && <span className="release-date">{release.date}</span>}
              </div>
              <div className="release-subtitle">{release.title}</div>
              <div className="release-expand-icon">
                {expandedVersions.has(release.version) ? '▼' : '▶'}
              </div>
            </div>

            {expandedVersions.has(release.version) && (
              <div className="release-content">
                {release.sections.map((section, sectionIndex) => (
                  <div key={`${release.version}-${sectionIndex}`} className="release-section">
                    <h3>{section.title}</h3>
                    {section.blocks.map((block, blockIndex) =>
                      renderBlock(block, `${release.version}-${sectionIndex}-${blockIndex}`)
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  )
}