import React, { useMemo } from 'react'
import { Button } from './Button'
import { AppIcon } from './app-primitives'
import './BulkActionsToolbar.css'

interface BulkActionsToolbarProps {
  selectedRuleIds: string[]
  canApprove?: boolean
  canActivate?: boolean
  approveEligibleCount?: number
  activateEligibleCount?: number
  ruleValidationEligibleCount?: number
  blockedRules?: Array<{ ruleId: string; ruleName: string; reason: string }>
  onApproveSelected?: () => void
  onActivateSelected?: () => void
  onOpenInRuleValidation?: () => void
  onClearSelection?: () => void
  totalCount?: number
}

export const BulkActionsToolbar: React.FC<BulkActionsToolbarProps> = ({
  selectedRuleIds,
  canApprove = false,
  canActivate = false,
  approveEligibleCount = 0,
  activateEligibleCount = 0,
  ruleValidationEligibleCount = selectedRuleIds.length,
  blockedRules = [],
  onApproveSelected,
  onActivateSelected,
  onOpenInRuleValidation,
  onClearSelection,
  totalCount = 0,
}) => {
  const selectionPercentage = useMemo(() => {
    if (totalCount === 0) return 0
    return Math.round((selectedRuleIds.length / totalCount) * 100)
  }, [selectedRuleIds.length, totalCount])

  if (selectedRuleIds.length === 0) {
    return null
  }

  return (
    <div className="bulk-actions-toolbar">
      <div className="toolbar-left">
        <div className="selection-info">
          <span className="selection-count">
            {selectedRuleIds.length} selected
          </span>
          {totalCount > 0 && (
            <span className="selection-percentage">({selectionPercentage}%)</span>
          )}
        </div>
        <div className="bulk-eligibility-summary">
          <span>{approveEligibleCount} approval-ready</span>
          {selectedRuleIds.length > approveEligibleCount && (
            <span>{selectedRuleIds.length - approveEligibleCount} skipped for approval</span>
          )}
          <span>{activateEligibleCount} activation-ready</span>
          {selectedRuleIds.length > activateEligibleCount && (
            <span>{selectedRuleIds.length - activateEligibleCount} skipped for activation</span>
          )}
          <span>{ruleValidationEligibleCount} validation-ready</span>
          {blockedRules.length > 0 && <span>{blockedRules.length} blocked</span>}
        </div>
      </div>

      <div className="toolbar-actions">
        <div className="action-group">
          {onApproveSelected && (
            <Button
              className="bulk-toolbar-btn"
              variant="secondary-default"
              onClick={onApproveSelected}
              disabled={!canApprove || approveEligibleCount === 0}
              title={canApprove ? 'Approve eligible selected rules' : 'No selected rules are eligible for approval'}
            >
              <AppIcon slot="icon" name="check-circle" />
              Approve ({approveEligibleCount})
            </Button>
          )}

          {onActivateSelected && (
            <Button
              className="bulk-toolbar-btn"
              variant="secondary-default"
              onClick={onActivateSelected}
              disabled={!canActivate || activateEligibleCount === 0}
              title={canActivate ? 'Activate eligible selected rules' : 'No selected rules are eligible for activation'}
            >
              <AppIcon slot="icon" name="power" />
              Activate ({activateEligibleCount})
            </Button>
          )}

          {onOpenInRuleValidation && (
            <Button
              className="bulk-toolbar-btn"
              variant="secondary-default"
              onClick={onOpenInRuleValidation}
              title="Open the selected rules in Rule Validation"
            >
              <AppIcon slot="icon" name="check-circle" />
              Rule Validation ({ruleValidationEligibleCount})
            </Button>
          )}
        </div>

        <div className="separator" />

        <Button
          className="bulk-toolbar-btn"
          variant="tertiary-default"
          onClick={onClearSelection}
          title="Clear selection"
        >
          <AppIcon slot="icon" name="times" />
          Clear
        </Button>
      </div>

      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${selectionPercentage}%` }}
        />
      </div>
      {blockedRules.length > 0 && (
        <div className="bulk-blocked-list" aria-label="Blocked selected rules">
          {blockedRules.slice(0, 3).map((rule) => (
            <span key={rule.ruleId}>{rule.ruleName}: {rule.reason}</span>
          ))}
          {blockedRules.length > 3 && <span>{blockedRules.length - 3} more blocked.</span>}
        </div>
      )}
    </div>
  )
}
