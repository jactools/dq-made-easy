import React from 'react'
import './Changelog.css'
import { ReleaseNotesPanel } from './ReleaseNotesPanel'

const APP_NAME = 'Data Quality Made Easy'

export const Changelog: React.FC = () => {
  return (
    <div className="changelog-container">
      <div className="changelog-header">
        <h1>Release Notes & Changelog</h1>
        <p className="changelog-subtitle">
          Track all updates, features, and improvements to {APP_NAME}
        </p>
      </div>

      <ReleaseNotesPanel />

      <div className="changelog-footer">
        <div className="footer-section">
          <h3>📚 Getting Started</h3>
          <ul>
            <li>📖 Read the <strong>Release Notes</strong> for feature details</li>
            <li>✚ Go to <strong>Suggestions</strong> to try the new feature</li>
            <li>⚙️ Visit <strong>Settings</strong> to configure preferences</li>
            <li>📊 Check <strong>System Metrics</strong> for performance insights</li>
          </ul>
        </div>
        <div className="footer-section">
          <h3>🔗 For Developers</h3>
          <ul>
            <li>Technical docs: Start at <strong>docs/technical/README.md</strong></li>
            <li>API reference: Detailed endpoint documentation included</li>
            <li>Architecture: Database schema and service design details</li>
            <li>Setup: Deployment and configuration instructions</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
