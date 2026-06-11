import React from 'react'
import { PrimaryButton, Button } from '../Button'
import { AppPageHeader, AppSelect } from '../app-primitives'
import { AppIcon } from '../app-primitives'
import { RuleStatus } from '../../types/rules'
import { WorkspaceScopeSegmentedControl, type WorkspaceScope } from '../WorkspaceScopeSegmentedControl'

interface RulesHeaderProps {
  viewScope: WorkspaceScope
  filterStatus: RuleStatus | 'all'
  searchQuery: string
  ownerFilter: string
  updatedSince: string
  updatedBefore: string
  sortBy: 'name' | 'created' | 'status'
  sortDirection: 'asc' | 'desc'
  filtersExpanded: boolean
  statusCounts: Record<RuleStatus | 'all', number>
  scopeDescription: string
  searchMinimumLength: number
  onViewScopeChange: (value: WorkspaceScope) => void
  onFilterStatusChange: (value: RuleStatus | 'all') => void
  onSearchQueryChange: (value: string) => void
  onOwnerFilterChange: (value: string) => void
  onUpdatedSinceChange: (value: string) => void
  onUpdatedBeforeChange: (value: string) => void
  onSortByChange: (value: 'name' | 'created' | 'status') => void
  onSortDirectionChange: (value: 'asc' | 'desc') => void
  onClearFilters: () => void
  onToggleFilters: () => void
  onOpenReusableFilters: () => void
  onOpenTemplateSelector: () => void
  onOpenOnboardingRuleGeneration: () => void
}

export const RulesHeader: React.FC<RulesHeaderProps> = ({
  viewScope,
  filterStatus,
  searchQuery,
  ownerFilter,
  updatedSince,
  updatedBefore,
  sortBy,
  sortDirection,
  filtersExpanded,
  statusCounts,
  scopeDescription,
  searchMinimumLength,
  onViewScopeChange,
  onFilterStatusChange,
  onSearchQueryChange,
  onOwnerFilterChange,
  onUpdatedSinceChange,
  onUpdatedBeforeChange,
  onSortByChange,
  onSortDirectionChange,
  onClearFilters,
  onToggleFilters,
  onOpenReusableFilters,
  onOpenTemplateSelector,
  onOpenOnboardingRuleGeneration,
}) => {
  const handleSortChange = (value: string) => {
    const normalized = String(value || '').trim().toLowerCase()
    if (normalized === 'name' || normalized === 'created' || normalized === 'status') {
      onSortByChange(normalized)
    }
  }

  const handleSortDirectionChange = (value: string) => {
    const normalized = String(value || '').trim().toLowerCase()
    if (normalized === 'asc' || normalized === 'desc') {
      onSortDirectionChange(normalized)
    }
  }

  return (
    <AppPageHeader
      className="rules-header"
      title="Rules Management"
      description={scopeDescription}
      actions={(
        <div className="rules-header-actions">
          <Button onClick={onToggleFilters} aria-expanded={filtersExpanded}>
            <AppIcon name={filtersExpanded ? 'chevron-up' : 'chevron-down'} slot="icon" />
            {filtersExpanded ? 'Collapse filter panel' : 'Expand filter panel'}
          </Button>
          <Button onClick={onOpenReusableFilters}>
            <AppIcon name="filter" slot="icon" />
            Reusable Filters
          </Button>
          <Button onClick={onOpenOnboardingRuleGeneration}>
            <AppIcon name="sparkles" slot="icon" />
            Guided Rule Generation
          </Button>
          <PrimaryButton onClick={() => onOpenTemplateSelector()}>
            <AppIcon name="plus" slot="icon" />
            Create from Template
          </PrimaryButton>
        </div>
      )}
    >
      <WorkspaceScopeSegmentedControl
        value={viewScope}
        onChange={onViewScopeChange}
        ariaLabel="Rules scope"
        label="Show:"
        className="rules-scope-group"
        controlClassName="rules-scope-control"
      />
      {filtersExpanded && (
        <div className="rules-controls">
          <div className="rules-search-group">
            <label htmlFor="rules-search-query">Search</label>
            <input
              id="rules-search-query"
              type="search"
              value={searchQuery}
              onChange={(event) => onSearchQueryChange(event.target.value)}
              placeholder="Name, ID, expression, or description"
              className="rules-text-input"
            />
            <span className="rules-filter-hint">Applied at {searchMinimumLength}+ characters.</span>
          </div>

          <div className="rules-filter-group">
            <AppSelect
              id="rules-status-filter"
              label="Status"
              value={filterStatus}
              onChange={(value) => onFilterStatusChange(value as RuleStatus | 'all')}
              options={[
                { value: 'all', label: `All (${statusCounts.all})` },
                { value: 'draft', label: `Draft (${statusCounts.draft})` },
                { value: 'testing', label: `Testing (${statusCounts.testing})` },
                { value: 'tested', label: `Tested (${statusCounts.tested})` },
                { value: 'pending-approval', label: `Pending (${statusCounts['pending-approval']})` },
                { value: 'approved', label: `Approved (${statusCounts.approved})` },
                { value: 'activated', label: `Active (${statusCounts.activated})` },
                { value: 'deactivated', label: `Deactivated (${statusCounts.deactivated})` },
                { value: 'rejected', label: `Rejected (${statusCounts.rejected})` },
              ]}
              fieldClassName="rules-select-wrapper"
            />
            <div className="rules-field-group">
              <label htmlFor="rules-owner-filter">Owner</label>
              <input
                id="rules-owner-filter"
                type="search"
                value={ownerFilter}
                onChange={(event) => onOwnerFilterChange(event.target.value)}
                placeholder="User ID, name, or email"
                className="rules-text-input"
              />
            </div>
            <div className="rules-field-group">
              <label htmlFor="rules-updated-since">Updated since</label>
              <input
                id="rules-updated-since"
                type="date"
                value={updatedSince}
                onChange={(event) => onUpdatedSinceChange(event.target.value)}
                className="rules-text-input"
              />
            </div>
            <div className="rules-field-group">
              <label htmlFor="rules-updated-before">Updated before</label>
              <input
                id="rules-updated-before"
                type="date"
                value={updatedBefore}
                onChange={(event) => onUpdatedBeforeChange(event.target.value)}
                className="rules-text-input"
              />
            </div>
            <div className="rules-field-group rules-clear-filters-group">
              <Button className="rules-clear-filters-btn" onClick={onClearFilters}>Clear filters</Button>
            </div>
          </div>

          <div className="rules-sort-group">
            <AppSelect
              id="rules-sort-by"
              label="Sort by"
              value={sortBy}
              onChange={handleSortChange}
              options={[
                { value: 'name', label: 'Name' },
                { value: 'created', label: 'Created Date' },
                { value: 'status', label: 'Status' },
              ]}
              fieldClassName="rules-select-wrapper"
            />
            <AppSelect
              id="rules-sort-order"
              label="Order"
              value={sortDirection}
              onChange={handleSortDirectionChange}
              options={[
                { value: 'asc', label: 'ASC' },
                { value: 'desc', label: 'DESC' },
              ]}
              fieldClassName="rules-select-wrapper"
            />
          </div>
        </div>
      )}
    </AppPageHeader>
  )
}
