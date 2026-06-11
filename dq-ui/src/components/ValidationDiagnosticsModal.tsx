import React from 'react'
import { AppButton, AppBanner, AppIcon, AppModal, AppPanel, AppStack } from './app-primitives'
import './ValidationDiagnosticsModal.css'

interface Diagnostic {
  scope: string
  severity: 'error' | 'warning'
  message: string
  code?: string
  reference?: string
}

export interface ValidationResult {
  valid: boolean
  summary: { errors: number; warnings: number }
  compiledExpression?: string
  artifactKey?: string
  compilerVersion?: string
  target?: string
  intermediateModel?: {
    schemaVersion?: string
    executionContract?: {
      engineTarget?: string
    }
  }
  engineExpectation?: string | null
  diagnostics: Diagnostic[]
}

interface ValidationDiagnosticsModalProps {
  isOpen: boolean
  ruleName: string
  result: ValidationResult
  onClose: () => void
}

const scopeLabel = (scope: string) => {
  if (scope === 'reusable-filter') return 'Filter'
  return scope.charAt(0).toUpperCase() + scope.slice(1)
}

export const ValidationDiagnosticsModal: React.FC<ValidationDiagnosticsModalProps> = ({
  isOpen,
  ruleName,
  result,
  onClose,
}) => {
  const errors = (result.diagnostics || []).filter(d => d.severity === 'error')
  const warnings = (result.diagnostics || []).filter(d => d.severity === 'warning')
  const schemaVersion = result.intermediateModel?.schemaVersion
  const executionEngine = result.intermediateModel?.executionContract?.engineTarget
  const hasCompilerMetadata = Boolean(
    result.artifactKey || result.compilerVersion || result.target || schemaVersion || executionEngine
  )

  return (
    <AppModal
      isOpen={isOpen}
      onClose={onClose}
      title={`Validation: ${ruleName}`}
      titleAs="h3"
      size="lg"
      bodyClassName="vdm-body"
      footer={<AppButton variant="secondary" onClick={onClose}>Close</AppButton>}
    >
      <AppStack gap="lg" className="vdm-stack">
        <AppBanner variant={result.valid ? 'success' : 'error'}>
          <AppIcon name={result.valid ? 'check-circle' : 'warning'} />
          {result.valid
            ? result.summary.warnings > 0
              ? `Passed with ${result.summary.warnings} warning${result.summary.warnings === 1 ? '' : 's'}`
              : 'Valid — rule composition is correct'
            : `Failed — ${result.summary.errors} error${result.summary.errors === 1 ? '' : 's'}${result.summary.warnings > 0 ? `, ${result.summary.warnings} warning${result.summary.warnings === 1 ? '' : 's'}` : ''}`}
        </AppBanner>

        {result.engineExpectation && (
          <AppPanel title="Validation Expectation" titleAs="h4">
            <code className="vdm-code-pill">{result.engineExpectation}</code>
          </AppPanel>
        )}

        {result.compiledExpression && (
          <AppPanel title="Compiled Expression" titleAs="h4">
            <pre className="vdm-code-block">{result.compiledExpression}</pre>
          </AppPanel>
        )}

        {hasCompilerMetadata && (
          <AppPanel title="Compiler Metadata" titleAs="h4">
            <dl className="vdm-metadata-grid">
              {result.target && (
                <div className="vdm-metadata-item">
                  <dt>Compiler target</dt>
                  <dd>{result.target}</dd>
                </div>
              )}
              {executionEngine && (
                <div className="vdm-metadata-item">
                  <dt>Execution engine</dt>
                  <dd>{executionEngine}</dd>
                </div>
              )}
              {result.compilerVersion && (
                <div className="vdm-metadata-item">
                  <dt>Compiler version</dt>
                  <dd><code>{result.compilerVersion}</code></dd>
                </div>
              )}
              {schemaVersion && (
                <div className="vdm-metadata-item">
                  <dt>Schema version</dt>
                  <dd><code>{schemaVersion}</code></dd>
                </div>
              )}
              {result.artifactKey && (
                <div className="vdm-metadata-item vdm-metadata-item--wide">
                  <dt>Artifact key</dt>
                  <dd><code>{result.artifactKey}</code></dd>
                </div>
              )}
            </dl>
          </AppPanel>
        )}

        <AppPanel
          title="Diagnostics"
          titleAs="h4"
          actions={result.diagnostics.length > 0 ? (
            <div className="vdm-diag-count">
              {errors.length > 0 && <span className="vdm-count-error">{errors.length} error{errors.length === 1 ? '' : 's'}</span>}
              {warnings.length > 0 && <span className="vdm-count-warning">{warnings.length} warning{warnings.length === 1 ? '' : 's'}</span>}
            </div>
          ) : null}
        >
          {result.diagnostics.length === 0 ? (
            <div className="vdm-no-diagnostics">No diagnostics — the rule compiled cleanly.</div>
          ) : (
            <ul className="vdm-diagnostic-list">
              {[...errors, ...warnings].map((d, i) => (
                <li key={i} className={`vdm-diagnostic vdm-diagnostic--${d.severity}`}>
                  <AppIcon name={d.severity === 'error' ? 'close-circle' : 'warning'} className="vdm-diagnostic-icon" />
                  <div className="vdm-diagnostic-content">
                    <div className="vdm-diagnostic-message">{d.message}</div>
                    <div className="vdm-diagnostic-meta">
                      <span className="vdm-badge vdm-badge--scope">{scopeLabel(d.scope)}</span>
                      {d.code && (
                        <span className="vdm-badge vdm-badge--code">{d.code}</span>
                      )}
                      {d.reference && (
                        <span className="vdm-badge vdm-badge--ref">{d.reference}</span>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </AppPanel>
      </AppStack>
    </AppModal>
  )
}
