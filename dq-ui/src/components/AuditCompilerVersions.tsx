import React, { useEffect, useMemo, useState } from 'react'
import { getAuthToken } from '../contexts/AuthContext'
import { useSettings } from '../hooks/useContexts'
import { toApiGroupV1Base } from '../config/api'
import './AuditCompilerVersions.css'

interface CompilerVersionRow {
  ruleId: string
  ruleName: string
  ruleVersionId: string | null
  ruleVersionNumber: number | null
  compilerVersion: string | null
  compilerRevision: number | null
  compileStatus: string | null
  artifactKey: string | null
  compiledAt: string | null
}

interface CompilerVersionResponse {
  data: CompilerVersionRow[]
  pagination: {
    total: number
    page: number
    limit: number
    totalPages: number
    hasNext: boolean
    hasPrevious: boolean
  }
}

export const AuditCompilerVersions: React.FC<{ showHeader?: boolean }> = ({ showHeader = true }) => {
  const settings = useSettings()
  const apiBase = useMemo(
    () => toApiGroupV1Base('rulebuilder', settings.applicationSettings?.apiBaseUrl),
    [settings.applicationSettings?.apiBaseUrl],
  )

  const [rows, setRows] = useState<CompilerVersionRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchRows = async () => {
      const token = getAuthToken()
      if (!token) {
        setRows([])
        setLoading(false)
        return
      }

      try {
        setLoading(true)
        const response = await fetch(`${apiBase}/rules/compiler-versions?page=1&limit=100`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })

        if (!response.ok) {
          throw new Error(`Failed to load compiler versions (${response.status})`)
        }

        const rawPayload: any = await response.json()

        if (!rawPayload || !Array.isArray(rawPayload.data)) {
          throw new Error('Unexpected compiler versions payload (expected { data: [...] })')
        }

        const normalizeRow = (input: any): CompilerVersionRow => {
          if (!input || typeof input !== 'object') {
            throw new Error('Unexpected compiler versions row (expected object)')
          }

          // Repo contract: API payloads are snake_case; UI converts at the boundary.
          // With global fetch normalization active, UI code should see camelCase.
          // Fail fast if snake_case leaks through (normalization broken / bypassed).
          if (
            'rule_id' in input ||
            'rule_name' in input ||
            'rule_version_id' in input ||
            'compiler_version' in input
          ) {
            throw new Error('Unexpected compiler versions row keys (snake_case leaked into UI)')
          }

          return {
            ruleId: String((input as any).ruleId ?? ''),
            ruleName: String((input as any).ruleName ?? ''),
            ruleVersionId: ((input as any).ruleVersionId ?? null) as string | null,
            ruleVersionNumber: ((input as any).ruleVersionNumber ?? null) as number | null,
            compilerVersion: ((input as any).compilerVersion ?? null) as string | null,
            compilerRevision: ((input as any).compilerRevision ?? null) as number | null,
            compileStatus: ((input as any).compileStatus ?? null) as string | null,
            artifactKey: ((input as any).artifactKey ?? null) as string | null,
            compiledAt: ((input as any).compiledAt ?? null) as string | null,
          }
        }

        const normalizedRows = rawPayload.data.map(normalizeRow)

        const sortedRows = [...normalizedRows].sort((first, second) => {
          if (first.compilerVersion && !second.compilerVersion) return -1
          if (!first.compilerVersion && second.compilerVersion) return 1
          return String(first.ruleName || '').localeCompare(String(second.ruleName || ''))
        })
        setRows(sortedRows)
        setError(null)
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : 'Failed to load compiler versions')
        setRows([])
      } finally {
        setLoading(false)
      }
    }

    fetchRows()
  }, [apiBase])

  const formatDate = (value: string | null): string => {
    if (!value) return '-'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return '-'
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return (
    <section className="audit-compiler-versions" aria-label="Rule and compiler versions">
      <div className="audit-compiler-versions-header">
        <h2>Audit Trail - Rule and Compiler Versions</h2>
        <p>Current user-visible rule version and internal compiler revision per rule (compiler fields stay empty until a rule is compiled at least once).</p>
      </div>

      {loading && (
        <div className="audit-compiler-versions-state">Loading version mappings...</div>
      )}

      {!loading && error && (
        <div className="audit-compiler-versions-state error">{error}</div>
      )}

      {!loading && !error && rows.length === 0 && (
        <div className="audit-compiler-versions-state">No version mappings found.</div>
      )}

      {!loading && !error && rows.length > 0 && (
        <div className="audit-compiler-versions-table-wrap">
          <table className="audit-compiler-versions-table">
            <thead>
              <tr>
                <th>Rule</th>
                <th>Rule Version</th>
                <th>Rule Version ID</th>
                <th>Compiler Version</th>
                <th>Compiler Revision</th>
                <th>Status</th>
                <th>Compiled At</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const rowKey =
                  row.artifactKey ||
                  [row.ruleId, row.ruleVersionId, row.compilerRevision, index].filter(Boolean).join(':')
                const ruleVersionNumber =
                  typeof row.ruleVersionNumber === 'number' && row.ruleVersionNumber > 0
                    ? row.ruleVersionNumber
                    : null
                const compilerRevision =
                  typeof row.compilerRevision === 'number' && row.compilerRevision > 0
                    ? row.compilerRevision
                    : null

                return (
                <tr key={rowKey}>
                  <td>
                    <div className="rule-name-cell">
                      <span>{row.ruleName}</span>
                      <small>{row.ruleId}</small>
                    </div>
                  </td>
                  <td>{ruleVersionNumber ?? '-'}</td>
                  <td>{row.ruleVersionId || '-'}</td>
                  <td>{row.compilerVersion || '-'}</td>
                  <td>{compilerRevision ?? '-'}</td>
                  <td>
                    <span className={`compile-status ${row.compileStatus || 'none'}`}>
                      {row.compileStatus || 'not-compiled'}
                    </span>
                  </td>
                  <td>{formatDate(row.compiledAt)}</td>
                </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
