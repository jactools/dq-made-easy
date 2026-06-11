import React, { useState, useEffect, useRef, useMemo } from 'react'
import { Rule, RuleApproval } from '../types/rules'
import { PrimaryButton, SecondaryButton, Button } from './Button'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import { useUnsavedChangesConfirmation } from '../hooks/useUnsavedChangesConfirmation'
import './RuleActionModals.css'

const extractInputValue = (event: any): string => {
  if (typeof event?.detail?.value === 'string') {
    return event.detail.value
  }
  if (typeof event?.target?.value === 'string') {
    return event.target.value
  }
  if (typeof event?.currentTarget?.value === 'string') {
    return event.currentTarget.value
  }
  return ''
}

interface SubmitApprovalModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (comments?: string) => Promise<void>
  title?: string
  placeholder?: string
  submitLabel?: string
}

export const SubmitApprovalModal: React.FC<SubmitApprovalModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  title = 'Submit for Approval',
  placeholder = 'Add any notes for the reviewer...',
  submitLabel = 'Submit for Review',
}) => {
  const [comments, setComments] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const hasChanges = useMemo(() => comments.trim().length > 0, [comments])

  const {
    showConfirmation,
    handleCloseWithConfirmation,
    handleConfirmClose,
    handleCancelConfirmation,
  } = useUnsavedChangesConfirmation({
    isOpen,
    hasChanges,
    onClose,
  })

  const handleSubmit = async () => {
    setIsLoading(true)
    try {
      await onSubmit(comments)
      setComments('')
      onClose()
    } finally {
      setIsLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <>
      <div className="rule-modal-overlay" onClick={handleCloseWithConfirmation}>
        <div className="rule-modal-content" onClick={e => e.stopPropagation()}>
          <div className="rule-modal-header">
            <h3>{title}</h3>
            <button className="rule-modal-close" onClick={handleCloseWithConfirmation}>×</button>
          </div>
          <div className="rule-modal-body">
            <label htmlFor="approval-comments">Comments (optional)</label>
            <textarea
              id="approval-comments"
              className="approval-textarea"
              placeholder={placeholder}
              value={comments}
              onChange={(e) => setComments(extractInputValue(e))}
              onInput={(e) => setComments(extractInputValue(e))}
              disabled={isLoading}
            />
          </div>
          <div className="rule-modal-footer">
            <SecondaryButton onClick={handleCloseWithConfirmation} disabled={isLoading}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={handleSubmit} disabled={isLoading}>
              {isLoading ? 'Submitting...' : submitLabel}
            </PrimaryButton>
          </div>
        </div>
      </div>

      <UnsavedChangesDialog
        isOpen={showConfirmation}
        onConfirm={handleConfirmClose}
        onCancel={handleCancelConfirmation}
      />
    </>
  )
}

interface ApproveRejectModalProps {
  isOpen: boolean
  ruleName: string
  onClose: () => void
  onApprove: (comments?: string) => Promise<void>
  onReject: (comments: string) => Promise<void>
}

export const ApproveRejectModal: React.FC<ApproveRejectModalProps> = ({
  isOpen,
  ruleName,
  onClose,
  onApprove,
  onReject,
}) => {
  const [comments, setComments] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasChanges = useMemo(() => comments.trim().length > 0, [comments])

  const {
    showConfirmation,
    handleCloseWithConfirmation,
    handleConfirmClose,
    handleCancelConfirmation,
  } = useUnsavedChangesConfirmation({
    isOpen,
    hasChanges,
    onClose,
  })

  const handleApprove = async () => {
    setIsLoading(true)
    setError(null)
    try {
      await onApprove(comments || undefined)
      setComments('')
      onClose()
    } catch {
      setError('Failed to approve this rule. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleReject = async () => {
    if (!comments.trim()) {
      setError('Please provide a reason for rejection.')
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      await onReject(comments)
      setComments('')
      onClose()
    } catch {
      setError('Failed to reject this rule. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <>
      <div className="rule-modal-overlay" onClick={handleCloseWithConfirmation}>
        <div className="rule-modal-content rule-modal-lg" onClick={e => e.stopPropagation()}>
          <div className="rule-modal-header">
            <h3>Review Rule: {ruleName}</h3>
            <button className="rule-modal-close" onClick={handleCloseWithConfirmation}>×</button>
          </div>
          <div className="rule-modal-body">
            <label htmlFor="review-comments">Comments / Reason</label>
            <textarea
              id="review-comments"
              className="approval-textarea"
              placeholder="Required for rejection. Optional for approval — add any notes for the rule creator."
              value={comments}
              onChange={(e) => {
                setComments(extractInputValue(e))
                setError(null)
              }}
              onInput={(e) => {
                setComments(extractInputValue(e))
                setError(null)
              }}
              disabled={isLoading}
              rows={6}
            />
            {error && (
              <p style={{ color: 'var(--app-status-error-text)', marginTop: '8px', fontSize: '0.875rem' }}>
                {error}
              </p>
            )}
          </div>
          <div className="rule-modal-footer">
            <SecondaryButton onClick={handleCloseWithConfirmation} disabled={isLoading}>
              Cancel
            </SecondaryButton>
            <Button onClick={handleReject} disabled={isLoading} variant="secondary" destructive>
              {isLoading ? 'Rejecting...' : 'Reject'}
            </Button>
            <PrimaryButton onClick={handleApprove} disabled={isLoading}>
              {isLoading ? 'Approving...' : 'Approve'}
            </PrimaryButton>
          </div>
        </div>
      </div>

      <UnsavedChangesDialog
        isOpen={showConfirmation}
        onConfirm={handleConfirmClose}
        onCancel={handleCancelConfirmation}
      />
    </>
  )
}

interface ActivateRuleModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: () => Promise<void>
}

interface DeactivateRuleModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: () => Promise<void>
}

export const ActivateRuleModal: React.FC<ActivateRuleModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async () => {
    setIsLoading(true)
    try {
      await onSubmit()
      onClose()
    } finally {
      setIsLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="rule-modal-overlay" onClick={onClose}>
      <div className="rule-modal-content" onClick={e => e.stopPropagation()}>
        <div className="rule-modal-header">
          <h3>Activate Rule</h3>
          <button className="rule-modal-close" onClick={onClose}>×</button>
        </div>
        <div className="rule-modal-body">
          <p>⚠️ Activating this rule will begin enforcing it on all new data.</p>
          <p>This rule will scan incoming data and flag violations according to its logic.</p>
        </div>
        <div className="rule-modal-footer">
          <SecondaryButton onClick={onClose} disabled={isLoading}>
            Cancel
          </SecondaryButton>
          <PrimaryButton onClick={handleSubmit} disabled={isLoading}>
            {isLoading ? 'Activating...' : 'Activate Rule'}
          </PrimaryButton>
        </div>
      </div>
    </div>
  )
}

export const DeactivateRuleModal: React.FC<DeactivateRuleModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async () => {
    setIsLoading(true)
    try {
      await onSubmit()
      onClose()
    } finally {
      setIsLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="rule-modal-overlay" onClick={onClose}>
      <div className="rule-modal-content" onClick={e => e.stopPropagation()}>
        <div className="rule-modal-header">
          <h3>Request Deactivation</h3>
          <button className="rule-modal-close" onClick={onClose}>×</button>
        </div>
        <div className="rule-modal-body">
          <p><strong>Approval required.</strong> This will create a deactivation request. The rule stays active until the request is approved.</p>
          <p>After approval, the rule can be reopened and edited again through the lifecycle flow.</p>
        </div>
        <div className="rule-modal-footer">
          <SecondaryButton onClick={onClose} disabled={isLoading}>
            Cancel
          </SecondaryButton>
          <Button onClick={handleSubmit} disabled={isLoading} variant="secondary" destructive>
            {isLoading ? 'Submitting...' : 'Request Deactivation'}
          </Button>
        </div>
      </div>
    </div>
  )
}

interface SaveTemplateModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (name: string, description: string) => Promise<void>
  currentRuleName: string
}

export const SaveTemplateModal: React.FC<SaveTemplateModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  currentRuleName,
}) => {
  const [name, setName] = useState(currentRuleName)
  const [description, setDescription] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const hasChanges = useMemo(
    () => name !== currentRuleName || description.trim().length > 0,
    [name, description, currentRuleName]
  )

  const {
    showConfirmation,
    handleCloseWithConfirmation,
    handleConfirmClose,
    handleCancelConfirmation,
  } = useUnsavedChangesConfirmation({
    isOpen,
    hasChanges,
    onClose,
  })

  const handleSubmit = async () => {
    if (!name.trim()) {
      alert('Template name is required')
      return
    }
    setIsLoading(true)
    try {
      await onSubmit(name, description)
      setName('')
      setDescription('')
      onClose()
    } finally {
      setIsLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <>
      <div className="rule-modal-overlay" onClick={handleCloseWithConfirmation}>
        <div className="rule-modal-content" onClick={e => e.stopPropagation()}>
          <div className="rule-modal-header">
            <h3>Save as Template</h3>
            <button className="rule-modal-close" onClick={handleCloseWithConfirmation}>×</button>
          </div>
          <div className="rule-modal-body">
            <label htmlFor="template-name">Template Name *</label>
            <input
              id="template-name"
              type="text"
              className="modal-input"
              value={name}
              onChange={e => setName(e.target.value)}
              disabled={isLoading}
              placeholder="e.g., Email Format Validation"
            />

            <label htmlFor="template-description">Description</label>
            <textarea
              id="template-description"
              className="modal-textarea"
              value={description}
              onChange={e => setDescription(e.target.value)}
              disabled={isLoading}
              placeholder="Describe what this template does and when to use it..."
              rows={4}
            />
          </div>
          <div className="rule-modal-footer">
            <SecondaryButton onClick={handleCloseWithConfirmation} disabled={isLoading}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={handleSubmit} disabled={isLoading || !name.trim()}>
              {isLoading ? 'Saving...' : 'Save as Template'}
            </PrimaryButton>
          </div>
        </div>
      </div>

      <UnsavedChangesDialog
        isOpen={showConfirmation}
        onConfirm={handleConfirmClose}
        onCancel={handleCancelConfirmation}
      />
    </>
  )
}
