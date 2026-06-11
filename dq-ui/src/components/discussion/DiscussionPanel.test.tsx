/** @vitest-environment jsdom */

import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DiscussionPanel, normalizeDiscussionEntries } from './DiscussionPanel'

describe('DiscussionPanel', () => {
  it('renders normalized discussion entries and the composer', () => {
    const onCommentTypeChange = vi.fn()
    const onCommentTextChange = vi.fn()
    const onSubmit = vi.fn()

    render(
      <DiscussionPanel
        title="Notes & Discussion"
        subtitle="Shared across the app"
        entries={normalizeDiscussionEntries([
          {
            id: 'discussion-1',
            author_name: 'Alice Reviewer',
            comment: 'Needs another look before release.',
            comment_type: 'concern',
            created_at: '2026-04-05T12:20:00Z',
          },
        ])}
        emptyState="No comments yet."
        composer={{
          commentType: 'note',
          commentText: 'Follow up with the steward.',
          onCommentTypeChange,
          onCommentTextChange,
          onSubmit,
          submitLabel: 'Add Comment',
          placeholder: 'Add a note or question...',
          typeSelectId: 'discussion-type',
          textareaId: 'discussion-text',
        }}
      />,
    )

    expect(screen.getByText('Notes & Discussion')).toBeTruthy()
    expect(screen.getByText('Shared across the app')).toBeTruthy()
    expect(screen.getByText('Alice Reviewer')).toBeTruthy()
    expect(screen.getByText('Needs another look before release.')).toBeTruthy()
    expect(screen.getByText('Concern', { selector: '.comment-type' })).toBeTruthy()

    fireEvent.change(screen.getByLabelText(/Comment type/i), { target: { value: 'question' } })
    fireEvent.change(screen.getByLabelText(/^Comment$/), { target: { value: 'Please verify the fix.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add Comment' }))

    expect(onCommentTypeChange).toHaveBeenCalledWith('question')
    expect(onCommentTextChange).toHaveBeenCalledWith('Please verify the fix.')
    expect(onSubmit).toHaveBeenCalled()
  })

  it('renders governed comment state badges', () => {
    render(
      <DiscussionPanel
        title="Governed Discussion"
        entries={normalizeDiscussionEntries([
          {
            id: 'discussion-2',
            author_name: 'Reviewer',
            comment: 'This should be acknowledged.',
            comment_type: 'general',
            state: 'acknowledged_by_owner',
            vote_count: 2,
            removed: true,
            removed_reason: 'removed by admin',
            created_at: '2026-04-05T12:30:00Z',
          },
        ])}
        emptyState="No comments yet."
      />,
    )

    expect(screen.getByText('Acknowledged')).toBeTruthy()
    expect(screen.getByText('Removed')).toBeTruthy()
    expect(screen.getByText('Reason: removed by admin')).toBeTruthy()
  })
})