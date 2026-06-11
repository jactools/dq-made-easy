import { describe, expect, it } from 'vitest'

import { DAMA_TEMPLATES } from '../types/templates'
import { buildPolicyDocumentMarkdown } from './policyDocuments'

describe('buildPolicyDocumentMarkdown', () => {
  it('renders a quality-standard policy document from template metadata', () => {
    const template = DAMA_TEMPLATES.find((item) => item.id === 'template-timeliness-1')

    expect(template).toBeTruthy()

    const markdown = buildPolicyDocumentMarkdown(template!, {
      kind: 'quality_standard',
      owner: 'Quality steward',
      steward: 'Operations lead',
      reviewCadence: 'Monthly',
    })

    expect(markdown).toContain('# Quality standard: Freshness Check')
    expect(markdown).toContain('## Purpose')
    expect(markdown).toContain('## Structured template parameters')
    expect(markdown).toContain('"maxDaysOld": 7')
    expect(markdown).toContain('- Owner: Quality steward')
    expect(markdown).toContain('Reuse this quality standard wherever the same governed data rule should apply.')
  })

  it('renders a monitor-definition policy document from the same template', () => {
    const template = DAMA_TEMPLATES.find((item) => item.id === 'template-accuracy-2')

    expect(template).toBeTruthy()

    const markdown = buildPolicyDocumentMarkdown(template!, {
      kind: 'monitor_definition',
    })

    expect(markdown).toContain('# Monitor definition: Email Format Check')
    expect(markdown).toContain('Monitored datasets, dashboards, and operational alerts that adopt this policy.')
    expect(markdown).toContain('Reuse this monitor definition wherever the same operational signal must be observed.')
  })

  it('renders workspace and asset reuse controls when provided', () => {
    const template = DAMA_TEMPLATES.find((item) => item.id === 'template-completeness-1')

    expect(template).toBeTruthy()

    const markdown = buildPolicyDocumentMarkdown(template!, {
      libraryShareScope: 'selected_workspaces',
      sharedWorkspaces: ['retail-banking', 'corporate-banking'],
      reuseScope: 'selected_workspaces',
      allowedWorkspaces: ['retail-banking', 'corporate-banking'],
      assetTargets: ['rules', 'monitors', 'data_assets'],
    })

    expect(markdown).toContain('## Policy library sharing')
    expect(markdown).toContain('- Sharing scope: Selected workspaces')
    expect(markdown).toContain('- Shared workspaces: retail-banking, corporate-banking')
    expect(markdown).toContain('## Reuse controls')
    expect(markdown).toContain('- Workspace scope: Selected workspaces')
    expect(markdown).toContain('- Allowed workspaces: retail-banking, corporate-banking')
    expect(markdown).toContain('- Asset targets: Rules, Monitors, Data Assets')
  })

  it('renders the policy approval workflow state', () => {
    const template = DAMA_TEMPLATES.find((item) => item.id === 'template-timeliness-1')

    expect(template).toBeTruthy()

    const markdown = buildPolicyDocumentMarkdown(template, {
      kind: 'quality_standard',
      owner: 'Governance Lead',
      steward: 'Policy Board',
      reviewCadence: 'Monthly',
      approvalStatus: 'pending_review',
      submittedBy: 'Policy Steward',
      submittedAt: '2026-04-12T09:00:00.000Z',
      reviewedBy: 'Governance Reviewer',
      reviewedAt: '2026-04-12T10:00:00.000Z',
      approvalNote: 'Approved for the retail-banking workspace.',
    })

    expect(markdown).toContain('## Policy approval workflow')
    expect(markdown).toContain('- Current approval status: Pending review')
    expect(markdown).toContain('- Submitted by: Policy Steward')
    expect(markdown).toContain('- Submitted at: 2026-04-12T09:00:00.000Z')
    expect(markdown).toContain('- Reviewed by: Governance Reviewer')
    expect(markdown).toContain('- Reviewed at: 2026-04-12T10:00:00.000Z')
    expect(markdown).toContain('- Review note: Approved for the retail-banking workspace.')
  })

  it('renders a reconciliation-definition policy document from the shared blueprint template', () => {
    const template = DAMA_TEMPLATES.find((item) => item.id === 'template-reconciliation-1')

    expect(template).toBeTruthy()

    const markdown = buildPolicyDocumentMarkdown(template!, {
      kind: 'reconciliation_definition',
      assetTargets: ['rules', 'data_assets'],
      reuseScope: 'selected_workspaces',
      allowedWorkspaces: ['retail-banking'],
    })

    expect(markdown).toContain('# Reconciliation definition: Reconciliation Blueprint')
    expect(markdown).toContain('Governed Data Assets, rules, and reusable reconciliation libraries that adopt the same comparison contract.')
    expect(markdown).toContain('- Asset targets: Rules, Data Assets')
    expect(markdown).toContain('Reuse this reconciliation definition wherever the same pairwise comparison contract must stay aligned across rules and Data Assets.')
  })
})