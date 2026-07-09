import React from 'react'
import Link from '@docusaurus/Link'

export default function DocsHomePage() {
  return (
    <div className="docs-home-page">
      <section className="docs-home-hero">
        <div className="docs-home-hero__copy">
          <p className="docs-home-eyebrow">Public documentation portal</p>
          <h1>One entry point for the docs that matter.</h1>
          <p className="docs-home-lede">
            Use this site to move between feature planning, technical references, release notes,
            manuals, API docs, and architecture records without hunting through the tree.
          </p>

          <div className="docs-home-actions">
            <Link className="docs-home-button docs-home-button--primary" to="/feature-plans">
              Open feature plans
            </Link>
            <Link className="docs-home-button docs-home-button--secondary" to="/features/DQ_FEATURES">
              See the feature map
            </Link>
          </div>

          <dl className="docs-home-facts">
            <div>
              <dt>Authoritative sources</dt>
              <dd>docs/ and architecture/</dd>
            </div>
            <div>
              <dt>Primary audience</dt>
              <dd>operators, stewards, and implementers</dd>
            </div>
            <div>
              <dt>Current emphasis</dt>
              <dd>public docs plus working references</dd>
            </div>
          </dl>
        </div>

        <aside className="docs-home-hero__panel">
          <p className="docs-home-panel-kicker">Featured now</p>
          <h2>DQ-17 reconciliation workflow</h2>
          <p>
            Review the persistent reconciliation flow, active-run protection, and the reusable
            reconciliation definition for rules and data assets.
          </p>
          <Link className="docs-home-panel-link" to="/user-manuals/DQ_17_RECONCILIATION_WORKFLOW_GUIDE">
            Open the guide
          </Link>
          <ul className="docs-home-mini-list">
            <li>Persistent run history</li>
            <li>Single-active-run protection per datasource</li>
            <li>Reusable reconciliation blueprint</li>
          </ul>
        </aside>
      </section>

      <section className="docs-home-section">
        <h2>What do you want to do today?</h2>

        <div className="docs-home-card-grid">
          <Link className="docs-home-card" to="/features">
            <span className="docs-home-card__eyebrow">Current status</span>
            <h3>Status and roadmap</h3>
            <p>See the latest summary, work in progress, and planning context.</p>
          </Link>

          <Link className="docs-home-card" to="/feature-plans">
            <span className="docs-home-card__eyebrow">Roadmap</span>
            <h3>Feature plans</h3>
            <p>Review the feature map, status tracking, and the current delivery direction.</p>
          </Link>

          <Link className="docs-home-card" to="/technical-references">
            <span className="docs-home-card__eyebrow">Reference</span>
            <h3>Technical references</h3>
            <p>Jump to implementation guides, policies, and operational reference material.</p>
          </Link>

          <Link className="docs-home-card" to="/release-notes">
            <span className="docs-home-card__eyebrow">Changelog</span>
            <h3>Release notes</h3>
            <p>Follow the latest published changes and portal-level release notes.</p>
          </Link>

          <Link className="docs-home-card" to="/user-manuals">
            <span className="docs-home-card__eyebrow">Task guides</span>
            <h3>User manuals</h3>
            <p>Open the short, task-focused cards for terminology and workflow guidance.</p>
          </Link>

          <Link className="docs-home-card" to="/api-reference">
            <span className="docs-home-card__eyebrow">API surface</span>
            <h3>API reference</h3>
            <p>Browse the public API documentation and supporting contract material.</p>
          </Link>
        </div>
      </section>

      <section className="docs-home-section docs-home-split">
        <section className="docs-home-panel docs-home-panel--plain">
          <p className="docs-home-panel-kicker">Overview</p>
          <h2>A single place to move from context to action.</h2>
          <p>
            DQ Made Easy is the public-facing documentation surface for building, validating,
            governing, and operating data-quality workflows. The docs are organized so you can move
            from a high-level explanation to the exact implementation or policy reference you need.
          </p>
          <p>
            The homepage keeps the most common paths visible, while the sidebar gives you full access
            to the authored source trees.
          </p>
        </section>

        <section className="docs-home-panel docs-home-panel--list">
          <p className="docs-home-panel-kicker">Additional links</p>
          <ul className="docs-home-link-list">
            <li>
              <Link to="/">Documentation home</Link>
              <span>Return to the curated landing page.</span>
            </li>
            <li>
              <Link to="/engineering-decisions">Engineering decisions</Link>
              <span>Repository-scoped decision records and rollout notes.</span>
            </li>
            <li>
              <Link to="/architecture">Architecture</Link>
              <span>Cross-cutting decisions and numbered deviation records.</span>
            </li>
            <li>
              <Link to="/features">Current status</Link>
              <span>Live summaries, milestones, and work-in-progress context.</span>
            </li>
            <li>
              <Link to="/runbooks">Runbooks</Link>
              <span>Operational procedures for common incident scenarios.</span>
            </li>
          </ul>
        </section>
      </section>
    </div>
  )
}