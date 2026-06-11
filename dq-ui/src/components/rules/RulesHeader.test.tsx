/** @vitest-environment jsdom */

import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { RulesHeader } from './RulesHeader'

vi.mock('../Button', async () => {
  const React = await import('react')
  const Button = ({ children, ...props }: any) => React.createElement('button', { type: 'button', ...props }, children)
  return { Button, PrimaryButton: Button, SecondaryButton: Button, TertiaryButton: Button }
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('RulesHeader', () => {
  it('renders the inline scope selector and reports scope changes', () => {
    const handleScopeChange = vi.fn()

    render(
      <RulesHeader
        viewScope="my"
        filterStatus="all"
        searchQuery=""
        ownerFilter=""
        updatedSince=""
        updatedBefore=""
        sortBy="status"
        sortDirection="asc"
        filtersExpanded={true}
        statusCounts={{
          all: 0,
          draft: 0,
          testing: 0,
          tested: 0,
          'pending-approval': 0,
          approved: 0,
          activated: 0,
          deactivated: 0,
          rejected: 0,
        }}
        scopeDescription="Scope: my rules in workspace ws-1."
        searchMinimumLength={3}
        onViewScopeChange={handleScopeChange}
        onFilterStatusChange={vi.fn()}
        onSearchQueryChange={vi.fn()}
        onOwnerFilterChange={vi.fn()}
        onUpdatedSinceChange={vi.fn()}
        onUpdatedBeforeChange={vi.fn()}
        onSortByChange={vi.fn()}
        onSortDirectionChange={vi.fn()}
        onClearFilters={vi.fn()}
        onToggleFilters={vi.fn()}
        onOpenReusableFilters={vi.fn()}
        onOpenTemplateSelector={vi.fn()}
        onOpenOnboardingRuleGeneration={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('tab', { name: /all across/i }))

    expect(handleScopeChange).toHaveBeenCalledWith('global')
  })

  it('collapses the bulky filter block when requested', () => {
    const handleToggleFilters = vi.fn()

    render(
      <RulesHeader
        viewScope="my"
        filterStatus="all"
        searchQuery=""
        ownerFilter=""
        updatedSince=""
        updatedBefore=""
        sortBy="status"
        sortDirection="asc"
        filtersExpanded={false}
        statusCounts={{
          all: 0,
          draft: 0,
          testing: 0,
          tested: 0,
          'pending-approval': 0,
          approved: 0,
          activated: 0,
          deactivated: 0,
          rejected: 0,
        }}
        scopeDescription="Scope: my rules in workspace ws-1."
        searchMinimumLength={3}
        onViewScopeChange={vi.fn()}
        onFilterStatusChange={vi.fn()}
        onSearchQueryChange={vi.fn()}
        onOwnerFilterChange={vi.fn()}
        onUpdatedSinceChange={vi.fn()}
        onUpdatedBeforeChange={vi.fn()}
        onSortByChange={vi.fn()}
        onSortDirectionChange={vi.fn()}
        onClearFilters={vi.fn()}
        onToggleFilters={handleToggleFilters}
        onOpenReusableFilters={vi.fn()}
        onOpenTemplateSelector={vi.fn()}
        onOpenOnboardingRuleGeneration={vi.fn()}
      />,
    )

    expect(screen.queryByLabelText('Search')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /expand filter panel/i }))

    expect(handleToggleFilters).toHaveBeenCalled()
  })

  it('invokes guided onboarding action when requested', () => {
    const handleOpenOnboarding = vi.fn()

    render(
      <RulesHeader
        viewScope="my"
        filterStatus="all"
        searchQuery=""
        ownerFilter=""
        updatedSince=""
        updatedBefore=""
        sortBy="status"
        sortDirection="asc"
        filtersExpanded={true}
        statusCounts={{
          all: 0,
          draft: 0,
          testing: 0,
          tested: 0,
          'pending-approval': 0,
          approved: 0,
          activated: 0,
          deactivated: 0,
          rejected: 0,
        }}
        scopeDescription="Scope: my rules in workspace ws-1."
        searchMinimumLength={3}
        onViewScopeChange={vi.fn()}
        onFilterStatusChange={vi.fn()}
        onSearchQueryChange={vi.fn()}
        onOwnerFilterChange={vi.fn()}
        onUpdatedSinceChange={vi.fn()}
        onUpdatedBeforeChange={vi.fn()}
        onSortByChange={vi.fn()}
        onSortDirectionChange={vi.fn()}
        onClearFilters={vi.fn()}
        onToggleFilters={vi.fn()}
        onOpenReusableFilters={vi.fn()}
        onOpenTemplateSelector={vi.fn()}
        onOpenOnboardingRuleGeneration={handleOpenOnboarding}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /guided rule generation/i }))
    expect(handleOpenOnboarding).toHaveBeenCalledTimes(1)
  })
})