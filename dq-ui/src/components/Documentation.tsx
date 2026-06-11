import React, { useState } from 'react'
import './Documentation.css'
import { ReleaseNotesPanel } from './ReleaseNotesPanel'

const APP_NAME = 'Data Quality Made Easy'
const DOCS_HUB_PATH = 'docs/README.md'
const FEATURE_DOCS_PATH = 'docs/features/README.md'
const TECHNICAL_DOCS_PATH = 'docs/technical/README.md'
const RELEASE_DOCS_PATH = 'docs/releases/README.md'
const USER_MANUALS_PATH = '/user-manuals/'
const GOVERNANCE_TERMINOLOGY_PATH = '/user-manuals/governance-terminology'

const architectureDecisionRecords = [
  {
    id: 'ADR-001',
    title: 'RFC 7807 Problem Details for Error Responses',
    path: 'architecture/adr/ADR-001-rfc-7807-problem-details-for-error-responses.md',
  },
  {
    id: 'ADR-002',
    title: 'Correlation IDs for Distributed Tracing',
    path: 'architecture/adr/ADR-002-correlation-ids-for-distributed-tracing.md',
  },
  {
    id: 'ADR-003',
    title: 'Standardized Pagination',
    path: 'architecture/adr/ADR-003-standardized-pagination.md',
  },
  {
    id: 'ADR-004',
    title: 'OpenAPI 3.0 Specification with Swagger',
    path: 'architecture/adr/ADR-004-openapi-3-0-specification-with-swagger.md',
  },
  {
    id: 'ADR-005',
    title: 'Health and Readiness Endpoints',
    path: 'architecture/adr/ADR-005-health-and-readiness-endpoints.md',
  },
  {
    id: 'ADR-006',
    title: 'Versioned API Routes',
    path: 'architecture/adr/ADR-006-versioned-api-routes.md',
  },
  {
    id: 'ADR-007',
    title: 'Dual-Standard API Contracts (OpenAPI + ODCS)',
    path: 'architecture/adr/ADR-007-dual-standard-api-contracts-openapi-odcs.md',
  },
  {
    id: 'ADR-008',
    title: 'Authentication Flow for Gateway Integration',
    path: 'architecture/adr/ADR-008-authentication-flow-for-gateway-integration.md',
  },
  {
    id: 'ADR-009',
    title: 'API Gateway Technology Selection',
    path: 'architecture/adr/ADR-009-api-gateway-technology-selection.md',
  },
  {
    id: 'ADR-010',
    title: 'API Service Decomposition into Focused Sub-services',
    path: 'architecture/adr/ADR-010-apiservice-decomposition-into-focused-sub-services.md',
  },
  {
    id: 'ADR-011',
    title: 'Executable Rule Transformation Strategy (DSL-first + GE adapter)',
    path: 'architecture/adr/ADR-011-executable-rule-transformation-strategy-dsl-first-with-great-expectations-adapter.md',
  },
]

const ADR_HOSTED_BASE_PATH = '/architecture/adr/'

type TabType = 'release-notes' | 'technical' | 'features' | 'getting-started'

interface Tab {
  id: TabType
  label: string
  icon: string
}

const tabs: Tab[] = [
  { id: 'release-notes', label: 'Release Notes', icon: '📜' },
  { id: 'technical', label: 'Technical Documentation', icon: '⚙️' },
  { id: 'features', label: 'Feature Documentation', icon: '✨' },
  { id: 'getting-started', label: 'Getting Started', icon: '🚀' },
]

interface DocumentationProps {
  onNavigate?: (destination: string) => void
  onSetTab?: (tab: TabType) => void
}

export const Documentation: React.FC<DocumentationProps> = ({ onNavigate, onSetTab: externalSetTab }) => {
  const [activeTab, setActiveTab] = useState<TabType>('release-notes')
  const [expandedDiagram, setExpandedDiagram] = useState(false)

  // Use external handler if provided, otherwise use internal state
  const handleSetTab = externalSetTab || setActiveTab

  return (
    <div className="documentation-container">
      <div className="documentation-header">
        <h1>Documentation & Release Notes</h1>
        <p className="documentation-subtitle">
          Everything you need to know about {APP_NAME}
        </p>
      </div>

      <div className="documentation-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`documentation-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
            aria-selected={activeTab === tab.id}
            role="tab"
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="documentation-content">
        {activeTab === 'release-notes' && (
          <div className="tab-content release-notes-tab">
            <ReleaseNotesPanel />
          </div>
        )}

        {activeTab === 'technical' && (
          <div className="tab-content technical-tab">
            <div className="documentation-section">
              <h2>Technical Documentation</h2>
              <p className="section-description">
                Complete reference for developers and system administrators
              </p>

              <div className="tech-note">
                <strong>📚 Documentation Hub:</strong> The canonical documentation tree lives under{' '}
                <code>{DOCS_HUB_PATH}</code>. Use <code>{FEATURE_DOCS_PATH}</code> for feature specs,{' '}
                <code>{TECHNICAL_DOCS_PATH}</code> for technical references, and{' '}
                <code>{RELEASE_DOCS_PATH}</code> for release notes.
              </div>

              <div className="tech-cards">
                <div className="tech-card">
                  <h3>📚 Documentation Hub</h3>
                  <p>Entry points for the reorganized documentation structure</p>
                  <ul className="tech-points">
                    <li>
                      <code>{DOCS_HUB_PATH}</code> - documentation home and navigation
                    </li>
                    <li>
                      <code>{FEATURE_DOCS_PATH}</code> - feature plans, specs, and trackers
                    </li>
                    <li>
                      <code>{TECHNICAL_DOCS_PATH}</code> - deployment, architecture, and system guides
                    </li>
                    <li>
                      <code>{RELEASE_DOCS_PATH}</code> - release notes and planning
                    </li>
                  </ul>
                </div>

                <div className="tech-card">
                  <h3>📒 User Manuals</h3>
                  <p>Topic-focused lookup cards for terminology, FAQ, and other reference items</p>
                  <ul className="tech-points">
                    <li>
                      <code>{USER_MANUALS_PATH}</code> - published static manuals index
                    </li>
                    <li>
                      <code>{GOVERNANCE_TERMINOLOGY_PATH}</code> - governance terminology reference card
                    </li>
                    <li>
                      <code>docs/user-manuals/</code> - source Markdown files for the manuals
                    </li>
                  </ul>
                </div>

                <div className="tech-card">
                  <h3>📡 API Reference</h3>
                  <p>Complete endpoint documentation with request/response examples</p>
                  <ul className="tech-points">
                    <li>Rule Suggestions API endpoints</li>
                    <li>Data Profiling endpoints</li>
                    <li>Interaction tracking endpoints</li>
                    <li>Authentication and authorization</li>
                  </ul>
                  <div className="tech-card-link" style={{ marginTop: '8px' }}>
                    <strong>OpenAPI/Swagger:</strong> <code>/openapi/</code> and <code>/openapi/index.json</code>
                  </div>
                </div>

                <div className="tech-card">
                  <h3>🗄️ Database Schema</h3>
                  <p>PostgreSQL database structure and relationships</p>
                  <ul className="tech-points">
                    <li>profiling_requests table</li>
                    <li>suggestions table</li>
                    <li>suggestion_interactions table</li>
                    <li>Indexes and constraints</li>
                  </ul>
                  <a 
                    href="#schema-diagram-details" 
                    className="tech-card-link"
                    onClick={(e) => {
                      e.preventDefault()
                      document.getElementById('schema-diagram-details')?.scrollIntoView({ behavior: 'smooth' })
                    }}
                  >
                    📊 View diagram & details below →
                  </a>
                </div>

                <div className="tech-card">
                  <h3>🏗️ Architecture</h3>
                  <p>System design and component interactions</p>
                  <ul className="tech-points">
                    <li>FastAPI backend services</li>
                    <li>React frontend components</li>
                    <li>Bull job queue system</li>
                    <li>Service layer design</li>
                    <li>Architecture Decision Records (ADR-001 to ADR-011)</li>
                  </ul>
                  <a 
                    href="#architecture-adr-details" 
                    className="tech-card-link"
                    onClick={(e) => {
                      e.preventDefault()
                      document.getElementById('architecture-adr-details')?.scrollIntoView({ behavior: 'smooth' })
                    }}
                  >
                    📚 View architecture ADRs below →
                  </a>
                </div>

                <div className="tech-card">
                  <h3>🚀 Deployment</h3>
                  <p>How to deploy and configure the system</p>
                  <ul className="tech-points">
                    <li>Docker Compose setup</li>
                    <li>Environment variables</li>
                    <li>Database migrations</li>
                    <li>Production checklist</li>
                  </ul>
                </div>

                <div className="tech-card">
                  <h3>🔒 Access Control</h3>
                  <p>Role-based access and permissions</p>
                  <ul className="tech-points">
                    <li>User roles (editor, reviewer, admin)</li>
                    <li>Permission matrix</li>
                    <li>Feature flags</li>
                    <li>Authentication flow</li>
                  </ul>
                </div>

                <div className="tech-card">
                  <h3>⚙️ Configuration</h3>
                  <p>System settings and tuning</p>
                  <ul className="tech-points">
                    <li>Feature flags</li>
                    <li>Rate limiting</li>
                    <li>Performance tuning</li>
                    <li>Logging configuration</li>
                  </ul>
                </div>


                <div className="tech-card">
                  <h3>📄 Data Contracts (ODCS 2.3.0)</h3>
                  <p>Open Data Contract Standard support for data specifications</p>
                  <ul className="tech-points">
                    <li>Vendor-neutral machine-readable format</li>
                    <li>Schema definitions, quality rules, SLAs</li>
                    <li>YAML and JSON format support</li>
                    <li>Standards-compliant with SodaCL</li>
                  </ul>
                  <div className="tech-card-link" style={{ marginTop: '8px' }}>
                    <strong>Endpoint:</strong> <code>GET /api/data-catalog/v1/data-contracts</code>
                  </div>
                </div>

                <div className="tech-card">
                  <h3>�🔄 Database Schema Versioning</h3>
                  <p>Automated version control for database schema changes</p>
                  <ul className="tech-points">
                    <li>Git-based automated versioning with pre-commit hooks</li>
                    <li>Git commit hash tracking for full traceability</li>
                    <li>Four operation modes: prompt, auto, strict, skip</li>
                    <li>View version info in UI header (click version number)</li>
                  </ul>
                  <a 
                    href="#versioning-details" 
                    className="tech-card-link"
                    onClick={(e) => {
                      e.preventDefault()
                      document.getElementById('versioning-details')?.scrollIntoView({ behavior: 'smooth' })
                    }}
                  >
                    📚 See detailed guide below →
                  </a>
                </div>
              </div>

              <div className="tech-note">
                <strong>📖 Full Technical Details:</strong> For complete technical documentation
                including code examples, API specifications, and troubleshooting, see{' '}
                <code>{TECHNICAL_DOCS_PATH}</code>.
              </div>

              <div id="architecture-adr-details" className="documentation-section" style={{ marginTop: '3rem' }}>
                <h2>🏗️ Architecture Decision Records (ADR)</h2>
                <p className="section-description">
                  Formal architecture decisions available in this repository, surfaced here for quick access.
                </p>

                <div className="versioning-content">
                  <div className="versioning-card">
                    <h3>ADR Index</h3>
                    <table className="versioning-table">
                      <thead>
                        <tr>
                          <th>ID</th>
                          <th>Decision</th>
                          <th>Repository Path</th>
                          <th>Hosted</th>
                        </tr>
                      </thead>
                      <tbody>
                        {architectureDecisionRecords.map((adr) => (
                          <tr key={adr.id}>
                            <td><code>{adr.id}</code></td>
                            <td>{adr.title}</td>
                            <td><code>{adr.path}</code></td>
                            <td>
                              <a
                                href={`${ADR_HOSTED_BASE_PATH}${adr.path.split('/').pop()}`}
                                target="_blank"
                                rel="noreferrer"
                                className="tech-card-link"
                              >
                                Open
                              </a>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* Database Schema Versioning - Detailed Section */}
              <div id="versioning-details" className="documentation-section" style={{ marginTop: '3rem' }}>
                <h2>🔄 Database Schema Versioning</h2>
                <p className="section-description">
                  Automated version control system for database schema changes using git hooks
                </p>

                <div className="versioning-content">
                  <div className="versioning-card">
                    <h3>⚡ Quick Start</h3>
                    <div className="code-block">
                      <pre>
# One-time setup (per developer){'\n'}
./dq-db/scripts/install-git-hooks.sh{'\n'}
{'\n'}
# Then commit schema changes normally{'\n'}
git commit -m "feat(db): add new table"{'\n'}
# Hook auto-increments: 1.0.0 → 1.0.1{'\n'}
# Records git commit: a1b2c3d
                      </pre>
                    </div>
                  </div>

                  <div className="versioning-card">
                    <h3>🎯 How It Works</h3>
                    <ol className="versioning-steps">
                      <li><strong>You edit</strong> schema files (01_schema.sql, 02_profiling_schema.sql)</li>
                      <li><strong>Git hook detects</strong> schema changes when you commit</li>
                      <li><strong>Hook prompts</strong> you to auto-increment or update manually</li>
                      <li><strong>Git commit hash</strong> captured automatically for traceability</li>
                      <li><strong>system_info.csv updated</strong> with version + git ref + timestamp</li>
                      <li><strong>Commit proceeds</strong> with versioning complete</li>
                      <li><strong>UI displays</strong> version info in header (click to see details)</li>
                    </ol>
                  </div>

                  <div className="versioning-card">
                    <h3>🔧 Operation Modes</h3>
                    <table className="versioning-table">
                      <thead>
                        <tr>
                          <th>Mode</th>
                          <th>Behavior</th>
                          <th>Use Case</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td><code>prompt</code></td>
                          <td>Asks what to do (default)</td>
                          <td>Interactive development</td>
                        </tr>
                        <tr>
                          <td><code>auto</code></td>
                          <td>Auto-increments PATCH version</td>
                          <td>Routine fixes, small changes</td>
                        </tr>
                        <tr>
                          <td><code>strict</code></td>
                          <td>Blocks commit without version update</td>
                          <td>CI/CD pipelines, enforcement</td>
                        </tr>
                        <tr>
                          <td><code>skip</code></td>
                          <td>Bypasses version check</td>
                          <td>WIP commits (use sparingly)</td>
                        </tr>
                      </tbody>
                    </table>
                    <div className="code-block" style={{ marginTop: '1rem' }}>
                      <pre>
# Use auto mode for this commit{'\n'}
DB_VERSION_AUTO_INCREMENT=auto git commit -m "fix: update schema"{'\n'}
{'\n'}
# Set mode globally for repository{'\n'}
git config hooks.dbVersionMode auto
                      </pre>
                    </div>
                  </div>

                  <div className="versioning-card">
                    <h3>📊 What Gets Tracked</h3>
                    <ul className="tech-points">
                      <li><strong>Schema Version:</strong> Semantic versioning (major.minor.patch)</li>
                      <li><strong>Git Commit Hash:</strong> Short hash linking to exact code change</li>
                      <li><strong>Update Timestamp:</strong> When the schema was last modified</li>
                      <li><strong>Full Traceability:</strong> Every version linked to git commit in UI</li>
                    </ul>
                    <div className="versioning-note">
                      <strong>💡 View Current Version:</strong> Click the version number in the header 
                      to see complete system information including schema version and git commit.
                    </div>
                  </div>

                  <div className="versioning-card">
                    <h3>🛠️ Manual Version Updates</h3>
                    <p>For MAJOR or MINOR version bumps (breaking changes or new features):</p>
                    <div className="code-block">
                      <pre>
# Breaking change (MAJOR){'\n'}
./dq-db/scripts/update_schema_version.sh 2.0.0{'\n'}
{'\n'}
# New feature (MINOR){'\n'}
./dq-db/scripts/update_schema_version.sh 1.1.0{'\n'}
{'\n'}
# Bug fix (PATCH) - or let hook auto-increment{'\n'}
./dq-db/scripts/update_schema_version.sh 1.0.1
                      </pre>
                    </div>
                  </div>

                  <div className="versioning-card">
                    <h3>📁 Key Files</h3>
                    <table className="versioning-table">
                      <thead>
                        <tr>
                          <th>File</th>
                          <th>Purpose</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td><code>dq-db/scripts/install-git-hooks.sh</code></td>
                          <td>Install git hook (one-time setup)</td>
                        </tr>
                        <tr>
                          <td><code>dq-db/scripts/git-hooks/pre-commit</code></td>
                          <td>Git hook that detects schema changes</td>
                        </tr>
                        <tr>
                          <td><code>dq-db/scripts/update_schema_version.sh</code></td>
                          <td>Manual version update script</td>
                        </tr>
                        <tr>
                          <td><code>dq-db/mock-data/system_info.csv</code></td>
                          <td>Version data (seeded into database)</td>
                        </tr>
                        <tr>
                          <td><code>dq-db/AUTOMATED_VERSIONING.md</code></td>
                          <td>Complete guide with examples</td>
                        </tr>
                        <tr>
                          <td><code>dq-db/DB_VERSION.md</code></td>
                          <td>Version history changelog</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <div className="versioning-card">
                    <h3>✅ Best Practices</h3>
                    <div className="versioning-dos-donts">
                      <div className="versioning-do">
                        <h4>✅ DO:</h4>
                        <ul>
                          <li>Install git hooks: <code>./dq-db/scripts/install-git-hooks.sh</code></li>
                          <li>Use auto mode for routine changes</li>
                          <li>Document changes in DB_VERSION.md</li>
                          <li>Let the hook capture git commit hashes</li>
                          <li>Test with <code>./scripts/start-all.sh --seed-all</code></li>
                        </ul>
                      </div>
                      <div className="versioning-dont">
                        <h4>❌ DON'T:</h4>
                        <ul>
                          <li>Skip version checks unless necessary</li>
                          <li>Manually edit git commit hash in CSV</li>
                          <li>Make schema changes without committing</li>
                          <li>Use <code>--no-verify</code> flag routinely</li>
                        </ul>
                      </div>
                    </div>
                  </div>

                  <div className="versioning-card">
                    <h3>🔍 Troubleshooting</h3>
                    <details>
                      <summary><strong>Hook doesn't run on commit</strong></summary>
                      <div className="code-block">
                        <pre>
# Reinstall the hook{'\n'}
./dq-db/scripts/install-git-hooks.sh{'\n'}
{'\n'}
# Verify it's executable{'\n'}
ls -la .git/hooks/pre-commit
                        </pre>
                      </div>
                    </details>
                    <details>
                      <summary><strong>Want to bypass hook temporarily</strong></summary>
                      <div className="code-block">
                        <pre>
# Use --no-verify (use sparingly!){'\n'}
git commit --no-verify -m "wip: schema changes"
                        </pre>
                      </div>
                    </details>
                    <details>
                      <summary><strong>Wrong version auto-incremented</strong></summary>
                      <div className="code-block">
                        <pre>
# Abort the commit{'\n'}
git reset HEAD~1{'\n'}
{'\n'}
# Update version manually{'\n'}
./dq-db/scripts/update_schema_version.sh 1.1.0{'\n'}
{'\n'}
# Commit again{'\n'}
git commit -m "feat(db): add new feature"
                        </pre>
                      </div>
                    </details>
                  </div>

                  <div className="tech-note" style={{ marginTop: '2rem' }}>
                    <strong>📖 Complete Documentation:</strong> For full details, examples, and advanced usage, 
                    see <code>dq-db/AUTOMATED_VERSIONING.md</code> in the repository.
                  </div>
                </div>
              </div>

              {/* Database Schema Diagram Section */}
              <div id="schema-diagram-details" className="documentation-section" style={{ marginTop: '3rem' }}>
                <h2>🗄️ Database Schema Diagram</h2>
                <p className="section-description">
                  Visual representation of the database structure and table relationships
                </p>

                <div className="schema-diagram-container">
                  <div className="schema-diagram">
                    <svg viewBox="0 0 1200 800" style={{ width: '100%', height: 'auto', border: '1px solid var(--app-border-subtle)' }}>
                      {/* Title */}
                      <text x="600" y="25" textAnchor="middle" style={{ fontSize: '18px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>
                        Data Quality Database Schema
                      </text>

                      {/* Legend */}
                      <g>
                        <text x="20" y="50" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>Legend:</text>
                        <line x1="100" y1="42" x2="130" y2="42" stroke="var(--app-brand-primary)" strokeWidth="2" strokeDasharray="5,5" />
                        <text x="135" y="46" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>One-to-Many</text>
                        
                        <line x1="280" y1="42" x2="310" y2="42" stroke="var(--app-brand-primary)" strokeWidth="2" />
                        <text x="315" y="46" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>Foreign Key</text>
                      </g>

                      {/* Table boxes - Core */}
                      {/* USERS table */}
                      <g>
                        <rect x="50" y="80" width="140" height="100" fill="var(--app-surface-secondary)" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="120" y="100" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>USERS</text>
                        <line x1="50" y1="108" x2="190" y2="108" stroke="var(--app-brand-primary)" strokeWidth="1" />
                        <text x="60" y="125" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>id (PK)</text>
                        <text x="60" y="138" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>name</text>
                        <text x="60" y="151" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>email</text>
                        <text x="60" y="164" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>preferences</text>
                      </g>

                      {/* RULES table */}
                      <g>
                        <rect x="280" y="80" width="140" height="120" fill="var(--app-surface-secondary)" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="350" y="100" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>RULES</text>
                        <line x1="280" y1="108" x2="420" y2="108" stroke="var(--app-brand-primary)" strokeWidth="1" />
                        <text x="290" y="125" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>id (PK)</text>
                        <text x="290" y="138" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>name</text>
                        <text x="290" y="151" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>expression</text>
                        <text x="290" y="164" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>dimension</text>
                        <text x="290" y="177" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>active</text>
                        <text x="290" y="190" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>workspace</text>
                      </g>

                      {/* WORKSPACES table */}
                      <g>
                        <rect x="510" y="80" width="140" height="100" fill="var(--app-surface-secondary)" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="580" y="100" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>WORKSPACES</text>
                        <line x1="510" y1="108" x2="650" y2="108" stroke="var(--app-brand-primary)" strokeWidth="1" />
                        <text x="520" y="125" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>id (PK)</text>
                        <text x="520" y="138" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>name</text>
                        <text x="520" y="151" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>description</text>
                      </g>

                      {/* DATA_PRODUCTS table */}
                      <g>
                        <rect x="740" y="80" width="160" height="100" fill="var(--app-surface-secondary)" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="820" y="100" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>DATA_PRODUCTS</text>
                        <line x1="740" y1="108" x2="900" y2="108" stroke="var(--app-brand-primary)" strokeWidth="1" />
                        <text x="750" y="125" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>id (PK)</text>
                        <text x="750" y="138" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>name</text>
                        <text x="750" y="151" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>owner</text>
                        <text x="750" y="164" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>workspace_id (FK)</text>
                      </g>

                      {/* Second row - Supporting Tables */}
                      {/* APPROVALS */}
                      <g>
                        <rect x="50" y="250" width="140" height="100" fill="var(--app-surface-secondary)" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="120" y="270" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>APPROVALS</text>
                        <line x1="50" y1="278" x2="190" y2="278" stroke="var(--app-brand-primary)" strokeWidth="1" />
                        <text x="60" y="295" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>id (PK)</text>
                        <text x="60" y="308" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>ruleId (FK)</text>
                        <text x="60" y="321" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>status</text>
                      </g>

                      {/* PROFILING_REQUESTS */}
                      <g>
                        <rect x="280" y="250" width="180" height="100" fill="var(--app-surface-secondary)" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="370" y="270" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>PROFILING_RQ</text>
                        <line x1="280" y1="278" x2="460" y2="278" stroke="var(--app-brand-primary)" strokeWidth="1" />
                        <text x="290" y="295" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>id (PK)</text>
                        <text x="290" y="308" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>data_source_id</text>
                        <text x="290" y="321" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>requested_by (FK)</text>
                        <text x="290" y="334" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>status</text>
                      </g>

                      {/* SUGGESTIONS */}
                      <g>
                        <rect x="550" y="250" width="150" height="100" fill="var(--app-surface-secondary)" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="625" y="270" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>SUGGESTIONS</text>
                        <line x1="550" y1="278" x2="700" y2="278" stroke="var(--app-brand-primary)" strokeWidth="1" />
                        <text x="560" y="295" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>id (PK)</text>
                        <text x="560" y="308" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>user_id (FK)</text>
                        <text x="560" y="321" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>confidence</text>
                        <text x="560" y="334" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>rule_type</text>
                      </g>

                      {/* DATA_OBJECTS_CATALOG */}
                      <g>
                        <rect x="800" y="250" width="150" height="100" fill="var(--app-surface-secondary)" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="875" y="270" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>DATA_OBJECTS</text>
                        <line x1="800" y1="278" x2="950" y2="278" stroke="var(--app-brand-primary)" strokeWidth="1" />
                        <text x="810" y="295" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>id (PK)</text>
                        <text x="810" y="308" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>dataset_id (FK)</text>
                        <text x="810" y="321" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>name</text>
                        <text x="810" y="334" style={{ fontSize: '10px', fill: 'var(--app-text-secondary)' }}>description</text>
                      </g>

                      {/* Relationships/Connections */}
                      {/* USERS to RULES */}
                      <line x1="190" y1="130" x2="280" y2="140" stroke="var(--app-brand-primary)" strokeWidth="1.5" strokeDasharray="5,5" />
                      <text x="235" y="125" style={{ fontSize: '9px', fill: 'var(--app-text-secondary)' }}>created</text>

                      {/* RULES to APPROVALS */}
                      <line x1="350" y1="200" x2="120" y2="250" stroke="var(--app-brand-primary)" strokeWidth="1.5" />
                      <text x="220" y="220" style={{ fontSize: '9px', fill: 'var(--app-text-secondary)' }}>has</text>

                      {/* WORKSPACES to RULES */}
                      <line x1="580" y1="180" x2="380" y2="200" stroke="var(--app-brand-primary)" strokeWidth="1.5" />
                      <text x="470" y="185" style={{ fontSize: '9px', fill: 'var(--app-text-secondary)' }}>contains</text>

                      {/* WORKSPACES to DATA_PRODUCTS */}
                      <line x1="650" y1="130" x2="740" y2="130" stroke="var(--app-brand-primary)" strokeWidth="1.5" />
                      <text x="690" y="125" style={{ fontSize: '9px', fill: 'var(--app-text-secondary)' }}>has</text>

                      {/* USERS to PROFILING_REQUESTS */}
                      <line x1="120" y1="180" x2="370" y2="250" stroke="var(--app-brand-primary)" strokeWidth="1.5" strokeDasharray="5,5" />
                      <text x="200" y="210" style={{ fontSize: '9px', fill: 'var(--app-text-secondary)' }}>requests</text>

                      {/* PROFILING_REQUESTS to SUGGESTIONS */}
                      <line x1="460" y1="300" x2="550" y2="300" stroke="var(--app-brand-primary)" strokeWidth="1.5" />
                      <text x="500" y="295" style={{ fontSize: '9px', fill: 'var(--app-text-secondary)' }}>generates</text>

                      {/* USERS to SUGGESTIONS */}
                      <line x1="190" y1="130" x2="625" y2="250" stroke="var(--app-brand-primary)" strokeWidth="1.5" strokeDasharray="5,5" />
                      <text x="370" y="185" style={{ fontSize: '9px', fill: 'var(--app-text-secondary)' }}>creates</text>

                      {/* DATA_PRODUCTS to DATA_OBJECTS */}
                      <line x1="900" y1="180" x2="875" y2="250" stroke="var(--app-brand-primary)" strokeWidth="1.5" />
                      <text x="920" y="210" style={{ fontSize: '9px', fill: 'var(--app-text-secondary)' }}>contains</text>

                      {/* Info boxes */}
                      <g>
                        <rect x="50" y="420" width="300" height="80" fill="var(--app-surface-secondary)" stroke="var(--app-brand-primary)" strokeWidth="1" rx="4" />
                        <text x="200" y="440" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>Core Tables</text>
                        <text x="60" y="460" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>• Rules: Quality rule definitions</text>
                        <text x="60" y="475" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>• Users: System users &amp; roles</text>
                        <text x="60" y="490" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>• Workspaces: Multi-tenancy</text>
                      </g>

                      <g>
                        <rect x="450" y="420" width="300" height="80" fill="var(--app-surface-secondary)" stroke="var(--app-brand-primary)" strokeWidth="1" rx="4" />
                        <text x="600" y="440" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>Profiling &amp; Suggestions</text>
                        <text x="460" y="460" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>• Profiling: Data analysis jobs</text>
                        <text x="460" y="475" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>• Suggestions: AI-generated rules</text>
                        <text x="460" y="490" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>• Interactions: User actions</text>
                      </g>

                      <g>
                        <rect x="850" y="420" width="300" height="80" fill="var(--app-surface-secondary)" stroke="var(--app-brand-primary)" strokeWidth="1" rx="4" />
                        <text x="1000" y="440" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>Data Catalog</text>
                        <text x="860" y="460" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>• Data Objects: Table definitions</text>
                        <text x="860" y="475" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>• Attributes: Column metadata</text>
                        <text x="860" y="490" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>• Versioning: Schema tracking</text>
                      </g>

                      {/* Key Statistics */}
                      <g>
                        <text x="600" y="560" textAnchor="middle" style={{ fontSize: '13px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>Schema Summary</text>
                        <text x="600" y="585" textAnchor="middle" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>24 Tables • 40+ Foreign Keys • Full Audit Trail • Multi-tenant Support</text>
                      </g>
                    </svg>
                  </div>

                  <div className="schema-tables">
                    <h3>📋 Table Groups</h3>
                    
                    <div className="schema-group">
                      <h4>Core Tables (Rules & Access Control)</h4>
                      <ul className="schema-table-list">
                        <li><strong>rules</strong> - Data quality rule definitions with expressions and dimensions</li>
                        <li><strong>users</strong> - System users with workspace assignments</li>
                        <li><strong>roles</strong> - Roles (editor, reviewer, admin)</li>
                        <li><strong>user_roles</strong> - Many-to-many relationship between users and roles</li>
                        <li><strong>workspaces</strong> - Workspace containers for multi-tenancy</li>
                      </ul>
                    </div>

                    <div className="schema-group">
                      <h4>Approval & Audit</h4>
                      <ul className="schema-table-list">
                        <li><strong>approvals</strong> - Rule approval requests and status tracking</li>
                        <li><strong>audit</strong> - Complete audit trail of all changes</li>
                        <li><strong>batch_test_requests</strong> - Testing and validation tracking</li>
                        <li><strong>test_proofs</strong> - Test execution results and DQ Score</li>
                      </ul>
                    </div>

                    <div className="schema-group">
                      <h4>Profiling & Suggestions</h4>
                      <ul className="schema-table-list">
                        <li><strong>data_source_metadata</strong> - Source connection details and statistics</li>
                        <li><strong>data_source_profiling_requests</strong> - Profiling job requests and status</li>
                        <li><strong>suggestions</strong> - AI-generated rule suggestions with confidence scores</li>
                        <li><strong>suggestion_interactions</strong> - User actions on suggestions (viewed, accepted, applied)</li>
                      </ul>
                    </div>

                    <div className="schema-group">
                      <h4>Data Catalog & Versioning</h4>
                      <ul className="schema-table-list">
                        <li><strong>data_products</strong> - Top-level data asset groupings</li>
                        <li><strong>data_sets</strong> - Collections of related data objects</li>
                        <li><strong>data_objects_catalog</strong> - Table definitions with versioning</li>
                        <li><strong>data_object_versions</strong> - Version history for schema changes</li>
                        <li><strong>attributes_catalog</strong> - Column definitions and metadata</li>
                        <li><strong>data_deliveries</strong> - Data ingestion events and metrics</li>
                      </ul>
                    </div>

                    <div className="schema-group">
                      <h4>Configuration & System</h4>
                      <ul className="schema-table-list">
                        <li><strong>system_info</strong> - System configuration and version information</li>
                        <li><strong>app_config</strong> - Application settings and feature flags</li>
                        <li><strong>rule_attributes</strong> - Mapping between rules and attributes</li>
                        <li><strong>attributes</strong> - Column metadata independent of versioning</li>
                      </ul>
                    </div>
                  </div>
                </div>

                <div className="tech-note" style={{ marginTop: '2rem' }}>
                  <strong>📖 SQL Schema Files:</strong> See <code>dq-db/init/01_schema.sql</code> and 
                  <code>dq-db/init/02_profiling_schema.sql</code> for the complete schema definition with all 
                  column types, constraints, and indexes.
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'features' && (
          <div className="tab-content features-tab">
            <div className="documentation-section">
              <h2>Feature Documentation</h2>
              <p className="section-description">
                Learn how to use {APP_NAME} and get the most from each feature
              </p>

              <div className="feature-cards">
                <div className="feature-card">
                  <h3>🎯 Rule Suggestions & Lifecycle Flow</h3>
                  <div className="feature-description">
                    <p>AI-powered suggestions to help you discover data quality rules faster</p>
                    <div className="feature-steps">
                      <h4>Quick Start:</h4>
                      <ol>
                        <li>Go to <strong>Rule Quality → Rule Suggestions</strong> in the sidebar</li>
                        <li>Select a data source</li>
                        <li>Click <strong>"Run Data Profiling"</strong></li>
                        <li>Review and apply suggestions</li>
                      </ol>
                    </div>
                    <div className="feature-tips">
                      <h4>💡 Tips:</h4>
                      <ul>
                        <li>High-confidence suggestions are usually reliable</li>
                        <li>You can apply multiple suggestions at once</li>
                        <li>Dismissed suggestions can help train the system</li>
                        <li>Profiling respects the 30-minute cooldown per source</li>
                      </ul>
                    </div>
                    
                    <div style={{ marginTop: '2rem', padding: '1rem', backgroundColor: 'var(--app-surface-secondary)', borderRadius: '4px' }}>
                      <h4>📊 Suggestion & Rule Lifecycle Flow:</h4>
                      <p style={{ fontSize: '12px', color: 'var(--app-text-secondary)', marginBottom: '1rem' }}>
                        Shows how suggestions progress through different status values and how they become rules in the system
                      </p>
                      <div 
                        onClick={() => setExpandedDiagram(true)}
                        style={{ cursor: 'pointer', position: 'relative' }}
                        title="Click to enlarge"
                      >
                        <svg viewBox="0 0 800 600" style={{ width: '100%', height: 'auto', maxWidth: '600px' }}>
                        {/* Title */}
                        <text x="400" y="25" textAnchor="middle" style={{ fontSize: '14px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>
                          Suggestion & Rule Lifecycle
                        </text>
                        
                        {/* Data Profiling Run */}
                        <rect x="300" y="50" width="200" height="40" fill="#FFF3CD" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="400" y="75" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                          📊 Data Profiling Run
                        </text>
                        
                        {/* Arrow down */}
                        <line x1="400" y1="90" x2="400" y2="110" stroke="var(--app-brand-primary)" strokeWidth="2" markerEnd="url(#arrowhead)" />
                        
                        {/* Pending (yellow) */}
                        <rect x="300" y="110" width="200" height="40" fill="#FFF3CD" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="400" y="135" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                          Suggestion: pending
                        </text>
                        
                        {/* Three paths */}
                        <line x1="300" y1="150" x2="150" y2="180" stroke="var(--app-brand-primary)" strokeWidth="2" />
                        <line x1="400" y1="150" x2="400" y2="180" stroke="var(--app-brand-primary)" strokeWidth="2" />
                        <line x1="500" y1="150" x2="650" y2="180" stroke="var(--app-brand-primary)" strokeWidth="2" />
                        
                        {/* Accepted (blue) */}
                        <rect x="50" y="180" width="200" height="40" fill="#D1ECF1" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="150" y="205" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                          Suggestion: accepted
                        </text>
                        
                        {/* Applied (green) */}
                        <rect x="300" y="180" width="200" height="40" fill="#D4EDDA" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="400" y="205" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                          Suggestion: applied
                        </text>
                        
                        {/* Dismissed (red) */}
                        <rect x="550" y="180" width="200" height="40" fill="#F8D7DA" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="650" y="205" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                          Suggestion: dismissed
                        </text>
                        
                        {/* Applied → Rule Status Draft */}
                        <line x1="400" y1="220" x2="400" y2="260" stroke="var(--app-brand-primary)" strokeWidth="2" />
                        <text x="420" y="245" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>
                          New Rule
                        </text>
                        
                        {/* Rule: Draft (purple) */}
                        <rect x="300" y="260" width="200" height="40" fill="#E7E7FF" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="400" y="285" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                          Rule Status: Draft
                        </text>
                        
                        {/* Testing → Tested */}
                        <line x1="400" y1="300" x2="400" y2="340" stroke="var(--app-brand-primary)" strokeWidth="2" />
                        <text x="420" y="325" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>
                          Test & Verify
                        </text>
                        
                        {/* Rule: Tested (purple) */}
                        <rect x="300" y="340" width="200" height="40" fill="#E7E7FF" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="400" y="365" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                          Rule Status: Tested
                        </text>
                        
                        {/* Pending Approval */}
                        <line x1="400" y1="380" x2="400" y2="420" stroke="var(--app-brand-primary)" strokeWidth="2" />
                        <text x="420" y="405" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>
                          Submit for Review
                        </text>
                        
                        {/* Rule: Pending Approval (orange) */}
                        <rect x="300" y="420" width="200" height="40" fill="#FFE7E7" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="400" y="445" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                          Rule: Pending Approval
                        </text>
                        
                        {/* Approved */}
                        <line x1="400" y1="460" x2="400" y2="500" stroke="var(--app-brand-primary)" strokeWidth="2" />
                        <text x="420" y="485" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>
                          Approved
                        </text>
                        
                        {/* Rule: Activated (green) */}
                        <rect x="300" y="500" width="200" height="40" fill="#90EE90" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
                        <text x="400" y="525" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                          Rule Status: Activated
                        </text>
                        
                        {/* Arrow marker definition */}
                        <defs>
                          <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
                            <polygon points="0 0, 10 3, 0 6" fill="var(--app-brand-primary)" />
                          </marker>
                        </defs>
                      </svg>
                      </div>
                      <p style={{ fontSize: '12px', color: 'var(--app-text-secondary)', marginTop: '0.5rem', textAlign: 'center' }}>
                        ✨ Click diagram to enlarge
                      </p>
                    </div>
                    
                    {onNavigate && (
                      <button 
                        className="tech-card-link"
                        onClick={() => onNavigate('rule-quality-suggestions')}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: 'var(--app-brand-primary)',
                          cursor: 'pointer',
                          fontSize: '14px',
                          padding: '8px 0',
                          textDecoration: 'none',
                          marginTop: '12px'
                        }}
                      >
                        🚀 Go to Suggestions →
                      </button>
                    )}
                  </div>
                </div>

                <div className="feature-card">
                  <h3>📝 Rule Management</h3>
                  <div className="feature-description">
                    <p>Create, edit, and manage data quality rules</p>
                    <div className="feature-steps">
                      <h4>Key Actions:</h4>
                      <ul>
                        <li><strong>Create:</strong> Build rules from scratch or from suggestions</li>
                        <li><strong>Edit:</strong> Modify rule parameters and test conditions</li>
                        <li><strong>Test:</strong> Execute rules and view results</li>
                        <li><strong>Submit:</strong> Send to approval workflow</li>
                      </ul>
                    </div>
                    <div className="feature-tips">
                      <h4>💡 Best Practices:</h4>
                      <ul>
                        <li>Use clear, descriptive rule names</li>
                        <li>Test rules thoroughly before submitting for approval</li>
                        <li>Document expectations in rule descriptions</li>
                      </ul>
                    </div>
                  </div>
                </div>

                <div className="feature-card">
                  <h3>✅ Approval Workflow</h3>
                  <div className="feature-description">
                    <p>Submit rules for review and final approval</p>
                    <div className="feature-steps">
                      <h4>Workflow Stages:</h4>
                      <ol>
                        <li><strong>Draft:</strong> Create and test your rule</li>
                        <li><strong>Submitted:</strong> Send to reviewers</li>
                        <li><strong>Approved:</strong> Rule is ready to use</li>
                        <li><strong>Active:</strong> Rule is running and monitoring data</li>
                      </ol>
                    </div>
                    <div className="feature-tips">
                      <h4>💡 Tips:</h4>
                      <ul>
                        <li>Include test evidence with your submission</li>
                        <li>Respond to reviewer feedback promptly</li>
                        <li>Track rule status in the Governance section</li>
                      </ul>
                    </div>
                    {handleSetTab && (
                      <button 
                        className="tech-card-link"
                        onClick={() => handleSetTab('release-notes')}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: 'var(--app-brand-primary)',
                          cursor: 'pointer',
                          fontSize: '14px',
                          padding: '8px 0',
                          textDecoration: 'none',
                          marginTop: '12px'
                        }}
                      >
                        📖 View Lifecycle Statuses & Transitions →
                      </button>
                    )}
                  </div>
                </div>

                <div className="feature-card">
                  <h3>📊 Reporting & Analytics</h3>
                  <div className="feature-description">
                    <p>Track rule performance and data quality metrics</p>
                    <div className="feature-steps">
                      <h4>Available Operations Views:</h4>
                      <ul>
                        <li><strong>Metrics & Analytics:</strong> Overall quality trends</li>
                        <li><strong>Test Results:</strong> Individual rule execution details</li>
                        <li><strong>Audit Trail:</strong> Complete change history</li>
                      </ul>
                    </div>
                    <div className="feature-tips">
                      <h4>💡 Tips:</h4>
                      <ul>
                        <li>Generate reports at regular intervals</li>
                        <li>Export data for external analysis</li>
                        <li>Use filters to focus on specific data sources</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>

              <div className="common-workflows">
                <h3>📋 Common Workflows</h3>
                <div className="workflow-cards">
                  <div className="workflow-card">
                    <h4>Discover & Create Rules Fast</h4>
                    <ol>
                      <li>Use Rule Suggestions to analyze data patterns</li>
                      <li>Accept high-confidence suggestions</li>
                      <li>Create rules from accepted suggestions</li>
                      <li>Submit for approval</li>
                    </ol>
                  </div>
                  <div className="workflow-card">
                    <h4>Audit Data Quality</h4>
                    <ol>
                      <li>Check Operations → Operational Metrics</li>
                      <li>Review failing rules in Test Results</li>
                      <li>Investigate issues in Data Catalog</li>
                      <li>Update rules as needed</li>
                    </ol>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'getting-started' && (
          <div className="tab-content getting-started-tab">
            <div className="documentation-section">
              <h2>Getting Started</h2>
              <p className="section-description">
                New to {APP_NAME}? Start here!
              </p>

              <div className="getting-started-cards">
                <div className="gs-card">
                  <h3>👤 First Time Setup</h3>
                  <ol className="gs-steps">
                    <li>Log in with your credentials</li>
                    <li>Review your role in the Settings page</li>
                    <li>Explore the Dashboard to see current status</li>
                    <li>Check Data Catalog to understand available data sources</li>
                  </ol>
                </div>

                <div className="gs-card">
                  <h3>🎯 Your First Rule</h3>
                  <ol className="gs-steps">
                    <li>Click "Rules" in the sidebar</li>
                    <li>Click "New Rule" or use Rule Suggestions</li>
                    <li>Define your rule parameters</li>
                    <li>Click "Test" to verify it works</li>
                    <li>Click "Submit for Approval"</li>
                  </ol>
                </div>

                <div className="gs-card">
                  <h3>🚀 Using Rule Suggestions</h3>
                  <ol className="gs-steps">
                    <li>Go to "Rule Quality → Rule Suggestions" in the sidebar</li>
                    <li>Select a data source</li>
                    <li>Click "Run Data Profiling"</li>
                    <li>Wait for profiling to complete</li>
                    <li>Review and apply high-confidence suggestions</li>
                  </ol>
                  {onNavigate && (
                    <button 
                      className="tech-card-link"
                      onClick={() => onNavigate('rule-quality-suggestions')}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: 'var(--app-brand-primary)',
                        cursor: 'pointer',
                        fontSize: '14px',
                        padding: '8px 0',
                        textDecoration: 'none',
                        marginTop: '12px',
                        display: 'block'
                      }}
                    >
                      🚀 Go to Suggestions Now →
                    </button>
                  )}
                </div>

                <div className="gs-card">
                  <h3>❓ Frequently Asked Questions</h3>
                  <div className="faq-items">
                    <div className="faq-item">
                      <strong>Q: How long does profiling take?</strong>
                      <p>Depends on data size. Usually 1-5 minutes for typical datasets.</p>
                    </div>
                    <div className="faq-item">
                      <strong>Q: Can I generate multiple suggestions?</strong>
                      <p>Yes, but there's a 30-minute cooldown between profiles for the same source.</p>
                    </div>
                    <div className="faq-item">
                      <strong>Q: What if I dismiss a suggestion?</strong>
                      <p>Dismissed suggestions are tracked and help improve future recommendations.</p>
                    </div>
                    <div className="faq-item">
                      <strong>Q: How do I know if my role has permissions?</strong>
                      <p>Check Settings → User Information. Or look for "permission denied" messages.</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="quick-tips">
                <h3>💡 Quick Tips</h3>
                <ul className="tips-list">
                  <li>Use dark mode in Settings for better visibility in low-light environments</li>
                  <li>Bookmark the Data Catalog for quick reference</li>
                  <li>Sort suggestions by confidence first</li>
                  <li>Add descriptive comments to your rules</li>
                  <li>Check Audit Trail to see what changed and who changed it</li>
                  <li>Use templates to create similar rules faster</li>
                </ul>
              </div>

              <div className="gs-note">
                <strong>🆘 Need Help?</strong>
                <ul className="help-links">
                  <li>Check the <strong>Release Notes</strong> tab for latest features</li>
                  <li>See <strong>Technical Documentation</strong> tab for details</li>
                  <li>Browse <strong>Feature Documentation</strong> for specific tasks</li>
                  <li>Contact your system administrator for access issues</li>
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Expanded Diagram Modal */}
      {expandedDiagram && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '2rem'
          }}
          onClick={() => setExpandedDiagram(false)}
        >
          <div 
            style={{
              backgroundColor: 'var(--app-surface-primary)',
              borderRadius: '8px',
              padding: '2rem',
              maxWidth: '90vw',
              maxHeight: '90vh',
              overflow: 'auto',
              position: 'relative',
              boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close Button */}
            <button
              onClick={() => setExpandedDiagram(false)}
              style={{
                position: 'absolute',
                top: '1rem',
                right: '1rem',
                backgroundColor: 'var(--app-surface-secondary)',
                border: 'none',
                borderRadius: '50%',
                width: '40px',
                height: '40px',
                fontSize: '24px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--app-text-primary)',
                transition: 'background-color 0.2s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--app-brand-primary)'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'var(--app-surface-secondary)'}
            >
              ✕
            </button>

            <h2 style={{ marginTop: 0, marginBottom: '1.5rem', textAlign: 'center' }}>
              📊 Suggestion & Rule Lifecycle Flow
            </h2>

            {/* Enlarged SVG */}
            <svg viewBox="0 0 800 600" style={{ width: '100%', height: 'auto', minWidth: '600px' }}>
              {/* Title */}
              <text x="400" y="25" textAnchor="middle" style={{ fontSize: '14px', fontWeight: 'bold', fill: 'var(--app-text-primary)' }}>
                Suggestion & Rule Lifecycle
              </text>
              
              {/* Data Profiling Run */}
              <rect x="300" y="50" width="200" height="40" fill="#FFF3CD" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
              <text x="400" y="75" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                📊 Data Profiling Run
              </text>
              
              {/* Arrow down */}
              <line x1="400" y1="90" x2="400" y2="110" stroke="var(--app-brand-primary)" strokeWidth="2" markerEnd="url(#arrowhead)" />
              
              {/* Pending (yellow) */}
              <rect x="300" y="110" width="200" height="40" fill="#FFF3CD" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
              <text x="400" y="135" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                Suggestion: pending
              </text>
              
              {/* Three paths */}
              <line x1="300" y1="150" x2="150" y2="180" stroke="var(--app-brand-primary)" strokeWidth="2" />
              <line x1="400" y1="150" x2="400" y2="180" stroke="var(--app-brand-primary)" strokeWidth="2" />
              <line x1="500" y1="150" x2="650" y2="180" stroke="var(--app-brand-primary)" strokeWidth="2" />
              
              {/* Accepted (blue) */}
              <rect x="50" y="180" width="200" height="40" fill="#D1ECF1" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
              <text x="150" y="205" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                Suggestion: accepted
              </text>
              
              {/* Applied (green) */}
              <rect x="300" y="180" width="200" height="40" fill="#D4EDDA" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
              <text x="400" y="205" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                Suggestion: applied
              </text>
              
              {/* Dismissed (red) */}
              <rect x="550" y="180" width="200" height="40" fill="#F8D7DA" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
              <text x="650" y="205" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                Suggestion: dismissed
              </text>
              
              {/* Applied → Rule Status Draft */}
              <line x1="400" y1="220" x2="400" y2="260" stroke="var(--app-brand-primary)" strokeWidth="2" />
              <text x="420" y="245" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>
                New Rule
              </text>
              
              {/* Rule: Draft (purple) */}
              <rect x="300" y="260" width="200" height="40" fill="#E7E7FF" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
              <text x="400" y="285" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                Rule Status: Draft
              </text>
              
              {/* Testing → Tested */}
              <line x1="400" y1="300" x2="400" y2="340" stroke="var(--app-brand-primary)" strokeWidth="2" />
              <text x="420" y="325" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>
                Test & Verify
              </text>
              
              {/* Rule: Tested (purple) */}
              <rect x="300" y="340" width="200" height="40" fill="#E7E7FF" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
              <text x="400" y="365" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                Rule Status: Tested
              </text>
              
              {/* Pending Approval */}
              <line x1="400" y1="380" x2="400" y2="420" stroke="var(--app-brand-primary)" strokeWidth="2" />
              <text x="420" y="405" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>
                Submit for Review
              </text>
              
              {/* Rule: Pending Approval (orange) */}
              <rect x="300" y="420" width="200" height="40" fill="#FFE7E7" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
              <text x="400" y="445" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                Rule: Pending Approval
              </text>
              
              {/* Approved */}
              <line x1="400" y1="460" x2="400" y2="500" stroke="var(--app-brand-primary)" strokeWidth="2" />
              <text x="420" y="485" style={{ fontSize: '11px', fill: 'var(--app-text-secondary)' }}>
                Approved
              </text>
              
              {/* Rule: Activated (green) */}
              <rect x="300" y="500" width="200" height="40" fill="#90EE90" stroke="var(--app-brand-primary)" strokeWidth="2" rx="4" />
              <text x="400" y="525" textAnchor="middle" style={{ fontSize: '12px', fontWeight: 'bold', fill: '#000' }}>
                Rule Status: Activated
              </text>
              
              {/* Arrow marker definition */}
              <defs>
                <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
                  <polygon points="0 0, 10 3, 0 6" fill="var(--app-brand-primary)" />
                </marker>
              </defs>
            </svg>

            <p style={{ textAlign: 'center', marginTop: '1.5rem', fontSize: '14px', color: 'var(--app-text-secondary)' }}>
              Click outside or press ✕ to close
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
