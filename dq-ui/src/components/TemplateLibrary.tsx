import React, { useMemo, useState } from 'react'
import { RuleTemplate, DAMA_TEMPLATES, DAMADimension } from '../types/templates'
import { AppEmptyState, AppPageHeader, AppPageShell, AppPanel, AppSelect } from './app-primitives'
import { Button } from './Button'
import { AppIcon, type AppIconName } from './app-primitives'
import { buildPolicyDocumentMarkdown, type PolicyDocumentKind } from '../utils/policyDocuments'
import './TemplateLibrary.css'

interface TemplateLibraryProps {
  onSelectTemplate: (template: RuleTemplate) => void
  onClose?: () => void
}

export const TemplateLibrary: React.FC<TemplateLibraryProps> = ({ onSelectTemplate, onClose }) => {
  const [selectedDimension, setSelectedDimension] = useState<DAMADimension | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState<'name' | 'dimension' | 'risk'>('name')
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(DAMA_TEMPLATES[0]?.id || null)
  const [policyDocumentKind, setPolicyDocumentKind] = useState<PolicyDocumentKind>('quality_standard')

  const dimensions: DAMADimension[] = ['completeness', 'accuracy', 'consistency', 'timeliness', 'validity', 'uniqueness']
  const dimensionLabels: Record<DAMADimension, string> = {
    completeness: 'Completeness',
    accuracy: 'Accuracy',
    consistency: 'Consistency',
    timeliness: 'Timeliness',
    validity: 'Validity',
    uniqueness: 'Uniqueness',
  }

  const dimensionIcons: Record<DAMADimension, AppIconName> = {
    completeness: 'warning',
    accuracy: 'check-circle',
    consistency: 'link',
    timeliness: 'clock',
    validity: 'info-circle',
    uniqueness: 'padlock-closed',
  }

  const filteredTemplates = useMemo(() => {
    let templates = DAMA_TEMPLATES

    if (selectedDimension) {
      templates = templates.filter(t => t.dimension === selectedDimension)
    }

    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      templates = templates.filter(
        t =>
          t.name.toLowerCase().includes(query) ||
          t.description.toLowerCase().includes(query) ||
          t.dimension.toLowerCase().includes(query)
      )
    }

    // Sort templates
    return templates.sort((a, b) => {
      switch (sortBy) {
        case 'name':
          return a.name.localeCompare(b.name)
        case 'dimension':
          return a.dimension.localeCompare(b.dimension)
        case 'risk':
          const riskOrder = { low: 0, medium: 1, high: 2 }
          return (riskOrder[a.defaultRiskLevel] || 0) - (riskOrder[b.defaultRiskLevel] || 0)
        default:
          return 0
      }
    })
  }, [selectedDimension, searchQuery, sortBy])

  const selectedTemplate = useMemo(
    () => DAMA_TEMPLATES.find((template) => template.id === selectedTemplateId) || filteredTemplates[0] || null,
    [filteredTemplates, selectedTemplateId],
  )

  const selectedPolicyDocument = useMemo(() => {
    if (!selectedTemplate) return ''
    return buildPolicyDocumentMarkdown(selectedTemplate, {
      kind: policyDocumentKind,
      owner: 'Policy steward',
      steward: 'Data quality lead',
      reviewCadence: 'Quarterly or after a material change',
    })
  }, [policyDocumentKind, selectedTemplate])

  return (
    <AppPageShell className="template-library">
      <AppPageHeader
        eyebrow="Rule authoring"
        title="Template Library"
        description="Search reusable DAMA templates, filter by dimension, and preview generated policy documents."
        actions={onClose ? (
          <button className="library-close" onClick={onClose} aria-label="Close template library">
            ✕
          </button>
        ) : null}
      >
        <div className="library-controls">
          <div className="search-box">
            <input
              type="text"
              placeholder="Search templates..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="search-input"
            />
          </div>

          <div className="filter-sort">
            <AppSelect
              id="template-sort"
              label="Sort templates"
              value={sortBy}
              onChange={(value) => setSortBy(value as 'name' | 'dimension' | 'risk')}
              options={[
                { value: 'name', label: 'Sort by Name' },
                { value: 'dimension', label: 'Sort by Dimension' },
                { value: 'risk', label: 'Sort by Risk Level' },
              ]}
            />
          </div>
        </div>
      </AppPageHeader>

      <AppPanel as="section" className="library-filters-panel" title="Dimension filters" titleAs="h2" bodyClassName="library-filters">
        <button
          className={`filter-btn ${selectedDimension === null ? 'active' : ''}`}
          onClick={() => setSelectedDimension(null)}
        >
          All ({DAMA_TEMPLATES.length})
        </button>
        {dimensions.map((dim) => {
          const count = DAMA_TEMPLATES.filter(t => t.dimension === dim).length
          return (
            <button
              key={dim}
              className={`filter-btn ${selectedDimension === dim ? 'active' : ''}`}
              onClick={() => setSelectedDimension(dim)}
            >
              <AppIcon name={dimensionIcons[dim]} />
              {dimensionLabels[dim]} ({count})
            </button>
          )
        })}
      </AppPanel>

      <AppPanel as="section" className="library-results-panel" bodyClassName="library-content">
        {filteredTemplates.length === 0 ? (
          <AppEmptyState
            title="No templates found matching your criteria"
            description="Try a different search term or dimension filter."
          />
        ) : (
          <>
            <div className="templates-grid">
              {filteredTemplates.map((template) => (
                <div
                  key={template.id}
                  className={`template-card ${selectedTemplate?.id === template.id ? 'template-card-selected' : ''}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedTemplateId(template.id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setSelectedTemplateId(template.id)
                    }
                  }}
                >
                  <div className="template-card-header">
                    <AppIcon name={template.icon || 'document'} />
                    <span className={`risk-badge risk-${template.defaultRiskLevel}`}>
                      {template.defaultRiskLevel.toUpperCase()}
                    </span>
                  </div>

                  <div className="template-card-body">
                    <h3>{template.name}</h3>
                    <p className="dimension-tag">
                      <AppIcon name={dimensionIcons[template.dimension]} />
                      {dimensionLabels[template.dimension]}
                    </p>
                    <p className="description">{template.description}</p>

                    <div className="template-stats">
                      <div className="stat">
                        <span className="stat-label">Rules</span>
                        <span className="stat-value">0</span>
                      </div>
                      <div className="stat">
                        <span className="stat-label">Created</span>
                        <span className="stat-value">Never</span>
                      </div>
                    </div>
                  </div>

                  <div className="template-card-footer">
                    <Button
                      className="template-action-btn"
                      variant="primary-default"
                      onClick={(event) => {
                        event.stopPropagation()
                        onSelectTemplate(template)
                      }}
                    >
                      <AppIcon name="arrow-right" />
                      Use Template
                    </Button>
                  </div>
                </div>
              ))}
            </div>

            {selectedTemplate && (
              <AppPanel
                as="section"
                tone="muted"
                className="policy-document-preview"
                title="Policy document preview"
                description="Generated from the reusable template metadata and structured parameters."
                actions={(
                  <div className="policy-document-kind-switch" role="tablist" aria-label="Policy document kind">
                    <button
                      type="button"
                      className={`policy-document-kind-btn ${policyDocumentKind === 'quality_standard' ? 'active' : ''}`}
                      onClick={() => setPolicyDocumentKind('quality_standard')}
                      aria-pressed={policyDocumentKind === 'quality_standard'}
                    >
                      Quality standard
                    </button>
                    <button
                      type="button"
                      className={`policy-document-kind-btn ${policyDocumentKind === 'monitor_definition' ? 'active' : ''}`}
                      onClick={() => setPolicyDocumentKind('monitor_definition')}
                      aria-pressed={policyDocumentKind === 'monitor_definition'}
                    >
                      Monitor definition
                    </button>
                    <button
                      type="button"
                      className={`policy-document-kind-btn ${policyDocumentKind === 'reconciliation_definition' ? 'active' : ''}`}
                      onClick={() => setPolicyDocumentKind('reconciliation_definition')}
                      aria-pressed={policyDocumentKind === 'reconciliation_definition'}
                    >
                      Reconciliation definition
                    </button>
                  </div>
                )}
              >
                <div className="policy-document-meta">
                  <span><strong>Template:</strong> {selectedTemplate.name}</span>
                  <span><strong>Dimension:</strong> {selectedTemplate.dimension}</span>
                  <span><strong>Risk:</strong> {selectedTemplate.defaultRiskLevel.toUpperCase()}</span>
                </div>

                <pre className="policy-document-preview-body">{selectedPolicyDocument}</pre>
              </AppPanel>
            )}
          </>
        )}
      </AppPanel>

      <AppPanel as="footer" tone="muted" className="library-stats">
        <p>Showing {filteredTemplates.length} of {DAMA_TEMPLATES.length} templates</p>
      </AppPanel>
    </AppPageShell>
  )
}
