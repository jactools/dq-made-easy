import React from 'react'
import { AppIcon } from './app-primitives'
import './AliasDiagnosticsDisplay.css'

export interface AliasDiagnostic {
  resolutionStatus: 'resolved' | 'unresolved' | 'fuzzy_match'
  source: 'catalog' | 'manual' | 'unresolved'
  resolvedTermName?: string
  resolvedDataType?: string
  domain?: string
  confidence: number
  warning?: string
}

export interface AliasDiagnosticsDisplayProps {
  diagnostics: Record<string, AliasDiagnostic>
  catalogAvailable: boolean
  lastSync?: string
}

/**
 * Component to display business term resolution diagnostics with source badges.
 * 
 * Shows:
 * - Each business term with its resolution status (resolved/unresolved/fuzzy)
 * - Source badge: "Catalog", "Manual", or "⚠ Unresolved"
 * - Resolved term name and datatype
 * - Domain/glossary info
 * - Confidence score for fuzzy matches
 */
export const AliasDiagnosticsDisplay: React.FC<AliasDiagnosticsDisplayProps> = ({
  diagnostics,
  catalogAvailable,
  lastSync,
}) => {
  if (!diagnostics || Object.keys(diagnostics).length === 0) {
    return null
  }

  const catalogSourced = Object.entries(diagnostics).filter(
    ([, d]) => d.source === 'catalog'
  )
  const manualSourced = Object.entries(diagnostics).filter(
    ([, d]) => d.source === 'manual'
  )
  const unresolved = Object.entries(diagnostics).filter(
    ([, d]) => d.source === 'unresolved'
  )

  return (
    <div className="alias-diagnostics-container">
      <div className="diagnostics-header">
        <h3>Business Term Resolution Diagnostics</h3>
        <div className="diagnostics-meta">
          {catalogAvailable && lastSync && (
            <small className="sync-info">
              <AppIcon name="check-circle" />
              Last synced: {new Date(lastSync).toLocaleString()}
            </small>
          )}
          {!catalogAvailable && (
            <small className="sync-warning">
              <AppIcon name="exclamation-triangle" />
              Catalog unavailable - using cached data
            </small>
          )}
        </div>
      </div>

      {catalogSourced.length > 0 && (
        <div className="diagnostics-section">
          <h4 className="section-title">
            <AppIcon name="book" />
            Catalog Sourced Business Terms ({catalogSourced.length})
          </h4>
          <div className="alias-list">
            {catalogSourced.map(([aliasName, diagnostic]) => (
              <div key={aliasName} className="alias-item">
                <div className="alias-name">{aliasName}</div>
                <div className="alias-details">
                  <span className="source-badge catalog">Catalog</span>
                  {diagnostic.resolvedTermName && (
                    <span className="term-name">{diagnostic.resolvedTermName}</span>
                  )}
                  {diagnostic.resolvedDataType && (
                    <span className="data-type">({diagnostic.resolvedDataType})</span>
                  )}
                  {diagnostic.domain && (
                    <span className="domain">Domain: {diagnostic.domain}</span>
                  )}
                  {diagnostic.confidence < 1.0 && (
                    <span className="confidence">
                      {Math.round(diagnostic.confidence * 100)}% match
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {manualSourced.length > 0 && (
        <div className="diagnostics-section">
          <h4 className="section-title">
            <AppIcon name="person" />
            Manual Business Term Mappings ({manualSourced.length})
          </h4>
          <div className="alias-list">
            {manualSourced.map(([aliasName, diagnostic]) => (
              <div key={aliasName} className="alias-item">
                <div className="alias-name">{aliasName}</div>
                <div className="alias-details">
                  <span className="source-badge manual">Manual</span>
                  {diagnostic.resolvedTermName && (
                    <span className="term-name">{diagnostic.resolvedTermName}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {unresolved.length > 0 && (
        <div className="diagnostics-section warning">
          <h4 className="section-title">
            <AppIcon name="exclamation-circle" />
            Unresolved Business Terms ({unresolved.length})
          </h4>
          <div className="alias-list">
            {unresolved.map(([aliasName, diagnostic]) => (
              <div key={aliasName} className="alias-item unresolved">
                <div className="alias-name">{aliasName}</div>
                <div className="alias-details">
                  <span className="source-badge unresolved">Unresolved</span>
                  <small className="warning-text">
                    This business term could not be resolved. Please check the spelling or add a manual mapping.
                  </small>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
