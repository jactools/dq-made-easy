import React, { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../hooks/useKeycloak'
import { DAMA_TEMPLATES, RuleTemplate } from '../types/templates'
import { buildPolicyDocumentMarkdown, type PolicyDocumentKind } from '../utils/policyDocuments'
import { Button } from './Button'
import './PolicyDocumentsPage.css'

type PolicyReviewStatus = 'draft' | 'reviewed' | 'acknowledged'
type PolicyApprovalStatus = 'draft' | 'pending_review' | 'approved' | 'rejected'
type PolicyReuseScope = 'current_workspace' | 'selected_workspaces' | 'all_accessible_workspaces'
type PolicyAssetTarget = 'rules' | 'monitors' | 'data_assets' | 'exceptions'

type PolicyDocumentRecord = {
  status: PolicyReviewStatus
  reviewedBy?: string
  reviewedAt?: string
  acknowledgedBy?: string
  acknowledgedAt?: string
  approvalStatus: PolicyApprovalStatus
  changeSummary?: string
  submittedBy?: string
  submittedAt?: string
  reviewedByPolicy?: string
  reviewedAtPolicy?: string
  approvalNote?: string
}

const POLICY_KIND_OPTIONS: Array<{ value: PolicyDocumentKind; label: string }> = [
  { value: 'quality_standard', label: 'Quality standard' },
  { value: 'monitor_definition', label: 'Monitor definition' },
  { value: 'reconciliation_definition', label: 'Reconciliation definition' },
]

const REUSE_SCOPE_OPTIONS: Array<{ value: PolicyReuseScope; label: string; description: string }> = [
  { value: 'current_workspace', label: 'Current workspace only', description: 'Limit reuse to the active workspace.' },
  { value: 'selected_workspaces', label: 'Selected workspaces', description: 'Choose the workspaces that can reuse this policy.' },
  { value: 'all_accessible_workspaces', label: 'All accessible workspaces', description: 'Allow reuse across every workspace you can access.' },
]

const LIBRARY_SHARE_SCOPE_OPTIONS: Array<{ value: PolicyReuseScope; label: string; description: string }> = [
  { value: 'current_workspace', label: 'Current workspace only', description: 'Keep the policy library private to the active workspace.' },
  { value: 'selected_workspaces', label: 'Selected workspaces', description: 'Share the library with specific workspaces you choose.' },
  { value: 'all_accessible_workspaces', label: 'All accessible workspaces', description: 'Share the library across every workspace you can access.' },
]

const ASSET_TARGET_OPTIONS: Array<{ value: PolicyAssetTarget; label: string; description: string }> = [
  { value: 'rules', label: 'Rules', description: 'Reusable in rule definitions and rule templates.' },
  { value: 'monitors', label: 'Monitors', description: 'Reusable in operational monitors and alerts.' },
  { value: 'data_assets', label: 'Data Assets', description: 'Reusable in data asset contracts and checks.' },
  { value: 'exceptions', label: 'Exception records', description: 'Reusable in governance exception workflows.' },
]

const STATUS_LABELS: Record<PolicyReviewStatus, string> = {
  draft: 'Draft',
  reviewed: 'Reviewed',
  acknowledged: 'Acknowledged',
}

const APPROVAL_STATUS_LABELS: Record<PolicyApprovalStatus, string> = {
  draft: 'Draft',
  pending_review: 'Pending review',
  approved: 'Approved',
  rejected: 'Rejected',
}

const buildInitialRecords = (): Record<string, PolicyDocumentRecord> =>
  Object.fromEntries(DAMA_TEMPLATES.map((template) => [template.id, { status: 'draft' as const, approvalStatus: 'draft' as const }]))

const formatTimestamp = (value?: string): string => {
  if (!value) return 'Not yet recorded'
  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) return value
  return timestamp.toLocaleString()
}

const countByStatus = (records: Record<string, PolicyDocumentRecord>) => {
  return Object.values(records).reduce(
    (accumulator, record) => {
      accumulator[record.status] += 1
      return accumulator
    },
    { draft: 0, reviewed: 0, acknowledged: 0 } as Record<PolicyReviewStatus, number>,
  )
}

const areStringArraysEqual = (left: string[], right: string[]): boolean => {
  if (left.length !== right.length) {
    return false
  }

  return left.every((value, index) => value === right[index])
}

export const PolicyDocumentsPage: React.FC = () => {
  const auth = useAuth()
  const currentReviewer = auth.user?.name || 'Policy reviewer'
  const accessibleWorkspaces = useMemo(
    () => Array.from(new Map((auth.user?.workspaceRoles || []).map((workspaceRole) => [String(workspaceRole.workspaceId || '').trim(), workspaceRole])).entries())
      .map(([workspaceId]) => workspaceId)
      .filter(Boolean),
    [auth.user?.workspaceRoles],
  )
  const currentWorkspaceId = auth.currentWorkspaceId || accessibleWorkspaces[0] || ''
  const [selectedTemplateId, setSelectedTemplateId] = useState(DAMA_TEMPLATES[0]?.id || '')
  const [policyKind, setPolicyKind] = useState<PolicyDocumentKind>('quality_standard')
  const [libraryShareScope, setLibraryShareScope] = useState<PolicyReuseScope>('current_workspace')
  const [sharedWorkspaceIds, setSharedWorkspaceIds] = useState<string[]>(() => (currentWorkspaceId ? [currentWorkspaceId] : []))
  const [reuseScope, setReuseScope] = useState<PolicyReuseScope>('current_workspace')
  const [selectedWorkspaceIds, setSelectedWorkspaceIds] = useState<string[]>(() => (currentWorkspaceId ? [currentWorkspaceId] : []))
  const [selectedAssetTargets, setSelectedAssetTargets] = useState<PolicyAssetTarget[]>(['rules'])
  const [changeSummaryDraft, setChangeSummaryDraft] = useState('')
  const [approvalNoteDraft, setApprovalNoteDraft] = useState('')
  const [policyRecords, setPolicyRecords] = useState<Record<string, PolicyDocumentRecord>>(() => buildInitialRecords())

  useEffect(() => {
    setSharedWorkspaceIds((currentSelections) => {
      const permittedSelections = currentSelections.filter((workspaceId) => accessibleWorkspaces.includes(workspaceId))
      const nextSelections = permittedSelections.length > 0
        ? permittedSelections
        : currentWorkspaceId && accessibleWorkspaces.includes(currentWorkspaceId)
          ? [currentWorkspaceId]
          : accessibleWorkspaces.slice(0, 1)

      return areStringArraysEqual(currentSelections, nextSelections) ? currentSelections : nextSelections
    })

    setSelectedWorkspaceIds((currentSelections) => {
      const permittedSelections = currentSelections.filter((workspaceId) => accessibleWorkspaces.includes(workspaceId))
      const nextSelections = permittedSelections.length > 0
        ? permittedSelections
        : currentWorkspaceId && accessibleWorkspaces.includes(currentWorkspaceId)
          ? [currentWorkspaceId]
          : accessibleWorkspaces.slice(0, 1)

      return areStringArraysEqual(currentSelections, nextSelections) ? currentSelections : nextSelections
    })
  }, [accessibleWorkspaces, currentWorkspaceId])

  const selectedTemplate = useMemo<RuleTemplate>(() => {
    return DAMA_TEMPLATES.find((template) => template.id === selectedTemplateId) || DAMA_TEMPLATES[0]
  }, [selectedTemplateId])

  const selectedRecord = policyRecords[selectedTemplate.id] || { status: 'draft' as const }
  const statusCounts = useMemo(() => countByStatus(policyRecords), [policyRecords])
  const approvalCounts = useMemo(() => {
    return Object.values(policyRecords).reduce(
      (accumulator, record) => {
        accumulator[record.approvalStatus] += 1
        return accumulator
      },
      { draft: 0, pending_review: 0, approved: 0, rejected: 0 } as Record<PolicyApprovalStatus, number>,
    )
  }, [policyRecords])
  const canEditPolicy = Boolean(auth.canEditGovernance?.())
  const canApprovePolicy = Boolean(auth.canApproveGovernance?.())
  const sharedWorkspaceIdsByScope = useMemo(() => {
    if (libraryShareScope === 'current_workspace') {
      return currentWorkspaceId ? [currentWorkspaceId] : []
    }

    if (libraryShareScope === 'selected_workspaces') {
      return sharedWorkspaceIds
    }

    return accessibleWorkspaces
  }, [accessibleWorkspaces, currentWorkspaceId, libraryShareScope, sharedWorkspaceIds])
  const reuseWorkspaceIds = useMemo(() => {
    if (reuseScope === 'current_workspace') {
      return currentWorkspaceId ? [currentWorkspaceId] : []
    }

    if (reuseScope === 'selected_workspaces') {
      return selectedWorkspaceIds
    }

    return accessibleWorkspaces
  }, [accessibleWorkspaces, currentWorkspaceId, reuseScope, selectedWorkspaceIds])
  const reuseScopeLabel = useMemo(() => {
    const option = REUSE_SCOPE_OPTIONS.find((entry) => entry.value === reuseScope)
    return option?.label || 'Current workspace only'
  }, [reuseScope])

  const libraryShareScopeLabel = useMemo(() => {
    const option = LIBRARY_SHARE_SCOPE_OPTIONS.find((entry) => entry.value === libraryShareScope)
    return option?.label || 'Current workspace only'
  }, [libraryShareScope])

  const workspaceLabelById = useMemo(() => {
    return accessibleWorkspaces.reduce<Record<string, string>>((accumulator, workspaceId) => {
      accumulator[workspaceId] = `Workspace ${workspaceId.toUpperCase()}`
      return accumulator
    }, {})
  }, [accessibleWorkspaces])

  const selectedWorkspaceLabels = useMemo(
    () => reuseWorkspaceIds.map((workspaceId) => workspaceLabelById[workspaceId] || workspaceId),
    [reuseWorkspaceIds, workspaceLabelById],
  )

  const sharedWorkspaceLabels = useMemo(
    () => sharedWorkspaceIdsByScope.map((workspaceId) => workspaceLabelById[workspaceId] || workspaceId),
    [sharedWorkspaceIdsByScope, workspaceLabelById],
  )

  const selectedAssetTargetLabels = useMemo(
    () => selectedAssetTargets.map((assetTarget) => ASSET_TARGET_OPTIONS.find((option) => option.value === assetTarget)?.label || assetTarget),
    [selectedAssetTargets],
  )

  const selectedDocument = useMemo(() => {
    return buildPolicyDocumentMarkdown(selectedTemplate, {
      kind: policyKind,
      owner: currentReviewer,
      steward: 'Governance lead',
      reviewCadence: 'Quarterly or after a material change',
      scope: libraryShareScope === 'current_workspace'
        ? `Governed policies shared across the current workspace (${currentWorkspaceId || 'unassigned'}).`
        : libraryShareScope === 'selected_workspaces'
          ? `Governed policies shared across selected workspaces (${sharedWorkspaceLabels.join(', ')}).`
          : 'Governed policies shared across all accessible workspaces.',
      libraryShareScope,
      sharedWorkspaces: sharedWorkspaceIdsByScope,
      reuseScope,
      allowedWorkspaces: reuseWorkspaceIds,
      assetTargets: policyKind === 'reconciliation_definition' ? ['rules', 'data_assets'] : selectedAssetTargets,
      approvalStatus: selectedRecord.approvalStatus,
      submittedBy: selectedRecord.submittedBy,
      submittedAt: selectedRecord.submittedAt,
      reviewedBy: selectedRecord.reviewedByPolicy,
      reviewedAt: selectedRecord.reviewedAtPolicy,
      approvalNote: selectedRecord.approvalNote,
    })
  }, [currentReviewer, currentWorkspaceId, policyKind, libraryShareScope, reuseScope, reuseWorkspaceIds, selectedAssetTargets, selectedRecord.approvalNote, selectedRecord.approvalStatus, selectedRecord.reviewedAtPolicy, selectedRecord.reviewedByPolicy, selectedRecord.submittedAt, selectedRecord.submittedBy, selectedTemplate, sharedWorkspaceIdsByScope, sharedWorkspaceLabels.join(', ')])

  const updateSelectedRecord = (updater: (current: PolicyDocumentRecord) => PolicyDocumentRecord) => {
    setPolicyRecords((currentRecords) => {
      const currentRecord = currentRecords[selectedTemplate.id] || { status: 'draft' as const }
      return {
        ...currentRecords,
        [selectedTemplate.id]: updater(currentRecord),
      }
    })
  }

  const handleMarkReviewed = () => {
    const now = new Date().toISOString()
    updateSelectedRecord((currentRecord) => ({
      ...currentRecord,
      status: 'reviewed',
      reviewedBy: currentReviewer,
      reviewedAt: now,
    }))
  }

  const handleAcknowledge = () => {
    const now = new Date().toISOString()
    updateSelectedRecord((currentRecord) => ({
      ...currentRecord,
      status: 'acknowledged',
      reviewedBy: currentRecord.reviewedBy || currentReviewer,
      reviewedAt: currentRecord.reviewedAt || now,
      acknowledgedBy: currentReviewer,
      acknowledgedAt: now,
    }))
  }

  const handleReset = () => {
    updateSelectedRecord(() => ({ status: 'draft', approvalStatus: 'draft' }))
  }

  const handleSubmitForReview = () => {
    const now = new Date().toISOString()
    const trimmedChangeSummary = changeSummaryDraft.trim()
    updateSelectedRecord((currentRecord) => ({
      ...currentRecord,
      approvalStatus: 'pending_review',
      changeSummary: trimmedChangeSummary,
      submittedBy: currentReviewer,
      submittedAt: now,
      approvalNote: currentRecord.approvalNote || '',
    }))
  }

  const handleApprovePolicy = () => {
    const now = new Date().toISOString()
    updateSelectedRecord((currentRecord) => ({
      ...currentRecord,
      approvalStatus: 'approved',
      reviewedByPolicy: currentReviewer,
      reviewedAtPolicy: now,
      approvalNote: approvalNoteDraft.trim() || currentRecord.approvalNote || 'Approved for active use.',
    }))
  }

  const handleRejectPolicy = () => {
    const now = new Date().toISOString()
    const rejectionNote = approvalNoteDraft.trim() || 'Review rejected. Please revise and resubmit.'
    updateSelectedRecord((currentRecord) => ({
      ...currentRecord,
      approvalStatus: 'rejected',
      reviewedByPolicy: currentReviewer,
      reviewedAtPolicy: now,
      approvalNote: rejectionNote,
    }))
  }

  const handleClearApprovalDraft = () => {
    setChangeSummaryDraft('')
    setApprovalNoteDraft('')
    updateSelectedRecord((currentRecord) => ({
      ...currentRecord,
      approvalStatus: 'draft',
      changeSummary: '',
      submittedBy: undefined,
      submittedAt: undefined,
      reviewedByPolicy: undefined,
      reviewedAtPolicy: undefined,
      approvalNote: '',
    }))
  }

  const toggleWorkspaceSelection = (workspaceId: string) => {
    setSelectedWorkspaceIds((currentSelections) => {
      if (currentSelections.includes(workspaceId)) {
        return currentSelections.filter((existingWorkspaceId) => existingWorkspaceId !== workspaceId)
      }

      return [...currentSelections, workspaceId]
    })
  }

  const toggleAssetTarget = (assetTarget: PolicyAssetTarget) => {
    setSelectedAssetTargets((currentTargets) => {
      if (currentTargets.includes(assetTarget)) {
        return currentTargets.filter((existingTarget) => existingTarget !== assetTarget)
      }

      return [...currentTargets, assetTarget]
    })
  }

  return (
    <div className="policy-documents-page">
      <header className="policy-documents-hero">
        <div>
          <p className="policy-documents-eyebrow">Governance</p>
          <h1>Policy Documents</h1>
          <p className="policy-documents-subtitle">
            View reusable policy drafts, share policy libraries across workspaces, review them against the template metadata, and acknowledge the current version.
          </p>
        </div>

        <div className="policy-documents-kind-switch" role="tablist" aria-label="Policy document kind">
          {POLICY_KIND_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`policy-kind-btn ${policyKind === option.value ? 'active' : ''}`}
              onClick={() => setPolicyKind(option.value)}
              aria-pressed={policyKind === option.value}
            >
              {option.label}
            </button>
          ))}
        </div>
      </header>

      <section className="policy-documents-summary">
        <article className="policy-summary-card">
          <span className="policy-summary-value">{DAMA_TEMPLATES.length}</span>
          <span className="policy-summary-label">Available documents</span>
        </article>
        <article className="policy-summary-card">
          <span className="policy-summary-value">{statusCounts.reviewed}</span>
          <span className="policy-summary-label">Reviewed</span>
        </article>
        <article className="policy-summary-card">
          <span className="policy-summary-value">{statusCounts.acknowledged}</span>
          <span className="policy-summary-label">Acknowledged</span>
        </article>
        <article className="policy-summary-card">
          <span className="policy-summary-value">{statusCounts.draft}</span>
          <span className="policy-summary-label">Still draft</span>
        </article>
          <article className="policy-summary-card">
            <span className="policy-summary-value">{approvalCounts.pending_review}</span>
            <span className="policy-summary-label">Pending approval</span>
          </article>
      </section>

      <section className="policy-documents-layout">
        <aside className="policy-documents-list" aria-label="Policy documents list">
          {DAMA_TEMPLATES.map((template) => {
            const record = policyRecords[template.id] || { status: 'draft' as const }
            const isSelected = selectedTemplate.id === template.id

            return (
              <button
                key={template.id}
                type="button"
                className={`policy-document-card ${isSelected ? 'selected' : ''}`}
                onClick={() => setSelectedTemplateId(template.id)}
              >
                <div className="policy-document-card-header">
                  <strong>{template.name}</strong>
                  <span className={`policy-status-badge policy-status-${record.status}`}>
                    {STATUS_LABELS[record.status]}
                  </span>
                </div>
                <p>{template.description}</p>
                <div className="policy-document-card-meta">
                  <span>{template.dimension}</span>
                  <span>{template.defaultRiskLevel.toUpperCase()}</span>
                </div>
              </button>
            )
          })}
        </aside>

        <main className="policy-documents-detail">
          <div className="policy-documents-detail-header">
            <div>
              <p className="policy-documents-eyebrow">Selected document</p>
              <h2>{selectedTemplate.name}</h2>
              <p>{selectedTemplate.description}</p>
            </div>

            <div className="policy-documents-status-stack">
              <div className={`policy-status-banner policy-status-${selectedRecord.status}`}>
                {STATUS_LABELS[selectedRecord.status]}
              </div>
              <div className={`policy-status-banner policy-approval-${selectedRecord.approvalStatus}`}>
                Approval: {APPROVAL_STATUS_LABELS[selectedRecord.approvalStatus]}
              </div>
            </div>
          </div>

          <div className="policy-documents-actions">
            <Button variant="secondary-default" onClick={handleMarkReviewed}>
              Mark Reviewed
            </Button>
            <Button variant="primary-default" onClick={handleAcknowledge}>
              Acknowledge
            </Button>
            <Button variant="secondary-default" onClick={handleReset}>
              Reset
            </Button>
          </div>

          <section className="policy-review-panel" aria-label="Policy change review">
            <div className="policy-reuse-panel-header">
              <div>
                <p className="policy-documents-eyebrow">Policy change review</p>
                <h3>Submit and approve a policy change</h3>
                <p>Use this flow when a shared standard changes and needs governance review before activation.</p>
              </div>
            </div>

            <label className="policy-review-field">
              <span>Proposed change</span>
              <textarea
                value={changeSummaryDraft}
                onChange={(event) => setChangeSummaryDraft(event.target.value)}
                placeholder="Describe what is changing and why it should be approved."
                rows={4}
              />
            </label>

            <label className="policy-review-field">
              <span>Review note</span>
              <textarea
                value={approvalNoteDraft}
                onChange={(event) => setApprovalNoteDraft(event.target.value)}
                placeholder="Add approval comments or a rejection reason."
                rows={3}
              />
            </label>

            <div className="policy-review-actions">
              <Button variant="primary-default" onClick={handleSubmitForReview} disabled={!canEditPolicy || !changeSummaryDraft.trim()}>
                Submit for Approval
              </Button>
              <Button variant="secondary-default" onClick={handleClearApprovalDraft} disabled={!canEditPolicy}>
                Clear Review Draft
              </Button>
              {canApprovePolicy && (
                <>
                  <Button variant="primary-default" onClick={handleApprovePolicy} disabled={selectedRecord.approvalStatus !== 'pending_review'}>
                    Approve Change
                  </Button>
                  <Button variant="secondary-default" onClick={handleRejectPolicy} disabled={selectedRecord.approvalStatus !== 'pending_review'}>
                    Reject Change
                  </Button>
                </>
              )}
            </div>

            <div className="policy-review-summary">
              <span><strong>Submitted by:</strong> {selectedRecord.submittedBy || 'Not yet submitted'}</span>
              <span><strong>Submitted at:</strong> {formatTimestamp(selectedRecord.submittedAt)}</span>
              <span><strong>Reviewed by:</strong> {selectedRecord.reviewedByPolicy || 'Not yet recorded'}</span>
              <span><strong>Reviewed at:</strong> {formatTimestamp(selectedRecord.reviewedAtPolicy)}</span>
              <span><strong>Change summary:</strong> {selectedRecord.changeSummary || 'No change summary recorded'}</span>
              <span><strong>Review note:</strong> {selectedRecord.approvalNote || 'No review note recorded'}</span>
            </div>
          </section>

          <section className="policy-library-panel" aria-label="Policy library sharing">
            <div className="policy-reuse-panel-header">
              <div>
                <p className="policy-documents-eyebrow">Library sharing</p>
                <h3>Share the policy library</h3>
                <p>Set which workspaces can discover the policy library before reuse is narrowed further.</p>
              </div>
            </div>

            <div className="policy-reuse-scope-grid" role="tablist" aria-label="Policy library sharing scope">
              {LIBRARY_SHARE_SCOPE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`policy-reuse-scope-btn ${libraryShareScope === option.value ? 'active' : ''}`}
                  onClick={() => setLibraryShareScope(option.value)}
                  aria-pressed={libraryShareScope === option.value}
                >
                  <span className="policy-reuse-scope-label">{option.label}</span>
                  <span className="policy-reuse-scope-description">{option.description}</span>
                </button>
              ))}
            </div>

            {libraryShareScope === 'selected_workspaces' && (
              <div className="policy-reuse-workspaces">
                {accessibleWorkspaces.length === 0 ? (
                  <p className="policy-reuse-empty">No accessible workspaces are available for sharing.</p>
                ) : (
                  accessibleWorkspaces.map((workspaceId) => (
                    <label key={workspaceId} className="policy-reuse-workspace-option">
                      <input
                        type="checkbox"
                        checked={sharedWorkspaceIds.includes(workspaceId)}
                        onChange={() => {
                          setSharedWorkspaceIds((currentSelections) => {
                            if (currentSelections.includes(workspaceId)) {
                              return currentSelections.filter((existingWorkspaceId) => existingWorkspaceId !== workspaceId)
                            }

                            return [...currentSelections, workspaceId]
                          })
                        }}
                      />
                      <span>{workspaceLabelById[workspaceId] || workspaceId}</span>
                    </label>
                  ))
                )}
              </div>
            )}

            <div className="policy-reuse-summary">
              <span><strong>Sharing scope:</strong> {libraryShareScopeLabel}</span>
              <span><strong>Shared workspaces:</strong> {sharedWorkspaceLabels.length > 0 ? sharedWorkspaceLabels.join(', ') : 'Current workspace only'}</span>
            </div>
          </section>

          <section className="policy-reuse-panel" aria-label="Policy reuse controls">
            <div className="policy-reuse-panel-header">
              <div>
                <p className="policy-documents-eyebrow">Reuse controls</p>
                <h3>Workspace reuse and asset scope</h3>
                <p>Choose where this policy may be reused and which asset types can adopt it.</p>
              </div>
            </div>

            <div className="policy-reuse-scope-grid" role="tablist" aria-label="Workspace reuse scope">
              {REUSE_SCOPE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`policy-reuse-scope-btn ${reuseScope === option.value ? 'active' : ''}`}
                  onClick={() => setReuseScope(option.value)}
                  aria-pressed={reuseScope === option.value}
                >
                  <span className="policy-reuse-scope-label">{option.label}</span>
                  <span className="policy-reuse-scope-description">{option.description}</span>
                </button>
              ))}
            </div>

            {reuseScope === 'selected_workspaces' && (
              <div className="policy-reuse-workspaces">
                {accessibleWorkspaces.length === 0 ? (
                  <p className="policy-reuse-empty">No accessible workspaces are available for reuse.</p>
                ) : (
                  accessibleWorkspaces.map((workspaceId) => (
                    <label key={workspaceId} className="policy-reuse-workspace-option">
                      <input
                        type="checkbox"
                        checked={selectedWorkspaceIds.includes(workspaceId)}
                        onChange={() => toggleWorkspaceSelection(workspaceId)}
                      />
                      <span>{workspaceLabelById[workspaceId] || workspaceId}</span>
                    </label>
                  ))
                )}
              </div>
            )}

            <div className="policy-reuse-assets">
              {ASSET_TARGET_OPTIONS.map((option) => (
                <label key={option.value} className="policy-reuse-asset-option">
                  <input
                    type="checkbox"
                    checked={selectedAssetTargets.includes(option.value)}
                    onChange={() => toggleAssetTarget(option.value)}
                  />
                  <span>
                    <strong>{option.label}</strong>
                    <small>{option.description}</small>
                  </span>
                </label>
              ))}
            </div>

            <div className="policy-reuse-summary">
              <span><strong>Workspace scope:</strong> {reuseScopeLabel}</span>
              <span><strong>Allowed workspaces:</strong> {selectedWorkspaceLabels.length > 0 ? selectedWorkspaceLabels.join(', ') : 'Current workspace only'}</span>
              <span><strong>Asset targets:</strong> {selectedAssetTargetLabels.join(', ')}</span>
            </div>
          </section>

          <div className="policy-documents-timeline">
            <div>
              <span className="policy-timeline-label">Reviewed by</span>
              <span className="policy-timeline-value">{selectedRecord.reviewedBy || 'Not yet recorded'}</span>
            </div>
            <div>
              <span className="policy-timeline-label">Reviewed at</span>
              <span className="policy-timeline-value">{formatTimestamp(selectedRecord.reviewedAt)}</span>
            </div>
            <div>
              <span className="policy-timeline-label">Acknowledged by</span>
              <span className="policy-timeline-value">{selectedRecord.acknowledgedBy || 'Not yet recorded'}</span>
            </div>
            <div>
              <span className="policy-timeline-label">Acknowledged at</span>
              <span className="policy-timeline-value">{formatTimestamp(selectedRecord.acknowledgedAt)}</span>
            </div>
          </div>

          <section className="policy-document-preview-panel">
            <div className="policy-document-preview-header">
              <div>
                <h3>Rendered policy document</h3>
                <p>The document below is generated from the reusable template metadata.</p>
              </div>
            </div>

            <pre className="policy-document-preview-body">{selectedDocument}</pre>
          </section>
        </main>
      </section>
    </div>
  )
}