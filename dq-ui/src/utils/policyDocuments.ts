import { RuleTemplate } from '../types/templates'

export type PolicyDocumentKind = 'quality_standard' | 'monitor_definition' | 'reconciliation_definition'

export interface PolicyDocumentContext {
  kind?: PolicyDocumentKind
  owner?: string
  steward?: string
  scope?: string
  reviewCadence?: string
  libraryShareScope?: 'current_workspace' | 'selected_workspaces' | 'all_accessible_workspaces'
  sharedWorkspaces?: string[]
  reuseScope?: 'current_workspace' | 'selected_workspaces' | 'all_accessible_workspaces'
  allowedWorkspaces?: string[]
  assetTargets?: string[]
  approvalStatus?: 'draft' | 'pending_review' | 'approved' | 'rejected'
  submittedBy?: string
  submittedAt?: string
  reviewedBy?: string
  reviewedAt?: string
  approvalNote?: string
}

const POLICY_KIND_LABELS: Record<PolicyDocumentKind, string> = {
  quality_standard: 'Quality standard',
  monitor_definition: 'Monitor definition',
  reconciliation_definition: 'Reconciliation definition',
}

const REUSE_SCOPE_LABELS: Record<NonNullable<PolicyDocumentContext['reuseScope']>, string> = {
  current_workspace: 'Current workspace only',
  selected_workspaces: 'Selected workspaces',
  all_accessible_workspaces: 'All accessible workspaces',
}

const LIBRARY_SHARE_SCOPE_LABELS: Record<NonNullable<PolicyDocumentContext['libraryShareScope']>, string> = {
  current_workspace: 'Current workspace only',
  selected_workspaces: 'Selected workspaces',
  all_accessible_workspaces: 'All accessible workspaces',
}

const ASSET_TARGET_LABELS: Record<string, string> = {
  rules: 'Rules',
  monitors: 'Monitors',
  data_assets: 'Data Assets',
  exceptions: 'Exception records',
}

const APPROVAL_STATUS_LABELS: Record<NonNullable<PolicyDocumentContext['approvalStatus']>, string> = {
  draft: 'Draft',
  pending_review: 'Pending review',
  approved: 'Approved',
  rejected: 'Rejected',
}

const CONTROL_GUIDANCE: Record<RuleTemplate['ruleType'], Partial<Record<PolicyDocumentKind, string[]>>> = {
  threshold: {
    quality_standard: [
      'Measure the selected attribute(s) against the approved threshold before publication.',
      'Escalate exceptions when the measured value falls outside the agreed control limit.',
    ],
    monitor_definition: [
      'Schedule the control to run at the agreed cadence and alert on threshold breaches.',
      'Record the failure reason and route the alert to the owning workspace.',
    ],
  },
  regex: {
    quality_standard: [
      'Validate the selected attribute(s) against the approved pattern before use.',
      'Document the steward-approved pattern and any allowed flags as policy parameters.',
    ],
    monitor_definition: [
      'Run the pattern check continuously or on the scheduled cadence and alert on invalid values.',
      'Treat repeated format failures as a monitoring signal for data-entry or upstream defects.',
    ],
  },
  range: {
    quality_standard: [
      'Keep numeric or date values within the approved minimum and maximum bounds.',
      'Treat out-of-range values as policy exceptions that require review before reuse.',
    ],
    monitor_definition: [
      'Evaluate the configured range on the schedule and notify when the bound is crossed.',
      'Capture the breach context so operations can correlate it with upstream change.',
    ],
  },
  custom: {
    quality_standard: [
      'Apply the documented business rule consistently across every governed asset or workspace that reuses it.',
      'Keep any exception handling explicit and steward-approved.',
    ],
    monitor_definition: [
      'Run the documented control on the agreed cadence and surface exceptions as operational alerts.',
      'Keep the monitoring outcome and operator notes attached to the policy record.',
    ],
    reconciliation_definition: [
      'Treat the comparison contract as the canonical definition for both rule authoring and Data Asset reuse.',
      'Keep the left/right sources, join keys, and comparison semantics aligned wherever the definition is reused.',
    ],
  },
}

export const buildPolicyDocumentMarkdown = (template: RuleTemplate, context: PolicyDocumentContext = {}): string => {
  const kind = context.kind || 'quality_standard'
  const kindLabel = POLICY_KIND_LABELS[kind]
  const guidance = CONTROL_GUIDANCE[template.ruleType][kind] || CONTROL_GUIDANCE[template.ruleType].quality_standard || []
  const scope = context.scope || (kind === 'monitor_definition'
    ? 'Monitored datasets, dashboards, and operational alerts that adopt this policy.'
    : kind === 'reconciliation_definition'
      ? 'Governed Data Assets, rules, and reusable reconciliation libraries that adopt the same comparison contract.'
    : 'Governed data assets, rules, and reusable control libraries that adopt this policy.')
  const parameters = JSON.stringify(template.templateRuleDefinition, null, 2)
  const libraryShareScope = context.libraryShareScope || 'current_workspace'
  const sharedWorkspaces = (context.sharedWorkspaces || []).map((workspaceId) => String(workspaceId || '').trim()).filter(Boolean)
  const reuseScope = context.reuseScope || 'current_workspace'
  const allowedWorkspaces = (context.allowedWorkspaces || []).map((workspaceId) => String(workspaceId || '').trim()).filter(Boolean)
  const assetTargets = (context.assetTargets || []).map((assetTarget) => String(assetTarget || '').trim()).filter(Boolean)
  const approvalStatus = context.approvalStatus || 'draft'

  return [
    `# ${kindLabel}: ${template.name}`,
    '',
    '## Purpose',
    template.description,
    '',
    '## Scope',
    scope,
    '',
    '## Control objectives',
    `- Dimension: ${template.dimension}`,
    `- Default risk level: ${template.defaultRiskLevel}`,
    `- Example use: ${template.exampleUse}`,
    ...guidance.map((entry) => `- ${entry}`),
    '',
    '## Structured template parameters',
    '```json',
    parameters,
    '```',
    '',
    '## Ownership and review',
    `- Owner: ${context.owner || 'Data steward'}`,
    `- Steward: ${context.steward || 'Policy owner'}`,
    `- Review cadence: ${context.reviewCadence || 'Quarterly or after material change'}`,
    '',
    '## Policy library sharing',
    `- Sharing scope: ${LIBRARY_SHARE_SCOPE_LABELS[libraryShareScope]}`,
    `- Shared workspaces: ${sharedWorkspaces.length > 0 ? sharedWorkspaces.join(', ') : 'Current workspace only'}`,
    '',
    '## Policy approval workflow',
    `- Current approval status: ${APPROVAL_STATUS_LABELS[approvalStatus]}`,
    `- Submitted by: ${context.submittedBy || 'Not yet submitted'}`,
    `- Submitted at: ${context.submittedAt || 'Not yet recorded'}`,
    `- Reviewed by: ${context.reviewedBy || 'Not yet recorded'}`,
    `- Reviewed at: ${context.reviewedAt || 'Not yet recorded'}`,
    `- Review note: ${context.approvalNote || 'No review note recorded'}`,
    '',
    '## Reuse controls',
    `- Workspace scope: ${REUSE_SCOPE_LABELS[reuseScope]}`,
    `- Allowed workspaces: ${allowedWorkspaces.length > 0 ? allowedWorkspaces.join(', ') : 'Current workspace only'}`,
    `- Asset targets: ${assetTargets.length > 0 ? assetTargets.map((assetTarget) => ASSET_TARGET_LABELS[assetTarget] || assetTarget).join(', ') : 'Rules'}`,
    '',
    '## Reuse notes',
    kind === 'monitor_definition'
      ? '- Reuse this monitor definition wherever the same operational signal must be observed.'
      : kind === 'reconciliation_definition'
        ? '- Reuse this reconciliation definition wherever the same pairwise comparison contract must stay aligned across rules and Data Assets.'
      : '- Reuse this quality standard wherever the same governed data rule should apply.',
  ].join('\n')
}