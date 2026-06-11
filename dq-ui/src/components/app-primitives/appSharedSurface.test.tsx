// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import {
  AppBadge,
  AppEmptyState,
  AppListRow,
  AppPageHeader,
  AppPageShell,
  AppPanel,
  AppStack,
  AppToolbar,
} from './index'

describe('shared app primitive surfaces', () => {
  it('renders the page shell and header contract', () => {
    render(
      <AppPageShell data-testid="shell">
        <AppPageHeader
          eyebrow="Administration"
          title="Icon Gallery"
          description="Browse active provider icons."
          actions={<button type="button">Refresh</button>}
        />
      </AppPageShell>,
    )

    expect(screen.getByTestId('shell').className).toContain('app-page-shell')
    expect(screen.getByRole('heading', { name: 'Icon Gallery' }).className).toContain('app-page-title')
    expect(screen.getByText('Browse active provider icons.').className).toContain('app-page-description')
    expect(screen.getByRole('button', { name: 'Refresh' }).textContent).toBe('Refresh')
  })

  it('renders the panel and stack contract', () => {
    render(
      <AppPanel
        eyebrow="Summary"
        title="Shared pattern layer"
        description="Reusable CSS and primitive contracts."
        actions={<button type="button">Edit</button>}
      >
        <AppStack gap="sm">
          <span>Pattern one</span>
          <span>Pattern two</span>
        </AppStack>
      </AppPanel>,
    )

    expect(screen.getByRole('heading', { name: 'Shared pattern layer' }).className).toContain('app-panel__title')
    expect(screen.getByText('Reusable CSS and primitive contracts.').className).toContain('app-panel__description')
    expect(screen.getByText('Pattern one').closest('.app-stack')?.className).toContain('app-stack--sm')
  })

  it('renders toolbar, badge, empty state, and list row semantics', () => {
    render(
      <div>
        <AppToolbar align="end" data-testid="toolbar">
          <button type="button">Add</button>
        </AppToolbar>
        <AppBadge tone="warning">Needs review</AppBadge>
        <AppEmptyState
          title="No results found"
          description="Adjust the filters and try again."
          actions={<button type="button">Clear filters</button>}
        />
        <div role="list">
          <AppListRow
            title="Catalog term"
            meta="Active provider"
            selected
            actions={<button type="button">Open</button>}
          />
        </div>
      </div>,
    )

    expect(screen.getByTestId('toolbar').className).toContain('app-toolbar--end')
    expect(screen.getByText('Needs review').className).toContain('app-status-chip--warning')
    expect(screen.getByRole('status').className).toContain('app-empty-state')
    expect(screen.getByRole('listitem').getAttribute('aria-selected')).toBe('true')
    expect(screen.getByText('Catalog term').className).toContain('app-list-row__title')
  })
})