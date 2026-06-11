import React from 'react'
import './DiscussionPanel.css'

export type DiscussionCommentType = 'general' | 'note' | 'concern' | 'question'
export type DiscussionCommentState = 'new' | 'acknowledged_by_owner' | 'voted_up' | 'resolved' | 'reopened' | 'locked'

export interface DiscussionEntry {
  id: string
  authorId?: string | null
  authorName: string
  content: string
  type: DiscussionCommentType
  createdAt: string
  state?: DiscussionCommentState | null
  locked?: boolean
  removed?: boolean
  removedAt?: string | null
  removedBy?: string | null
  removedReason?: string | null
  edited?: boolean
  editedAt?: string | null
  editedBy?: string | null
  editCount?: number | null
  voteCount?: number | null
  acknowledgedAt?: string | null
  acknowledgedBy?: string | null
  resolvedAt?: string | null
  resolvedBy?: string | null
  reopenedAt?: string | null
  reopenedBy?: string | null
}

export interface DiscussionEntryInput {
  id?: string
  authorId?: string | null
  author_id?: string | null
  authorName?: string | null
  author_name?: string | null
  content?: string | null
  comment?: string | null
  message?: string | null
  body?: string | null
  text?: string | null
  type?: string | null
  commentType?: string | null
  comment_type?: string | null
  createdAt?: string | null
  created_at?: string | null
  timestamp?: string | null
  timestamp_at?: string | null
  state?: string | null
  locked?: boolean | null
  removed?: boolean | null
  removedAt?: string | null
  removed_at?: string | null
  removedBy?: string | null
  removed_by?: string | null
  removedReason?: string | null
  removed_reason?: string | null
  edited?: boolean
  editedAt?: string | null
  edited_at?: string | null
  editedBy?: string | null
  edited_by?: string | null
  editCount?: number | null
  edit_count?: number | null
  voteCount?: number | null
  vote_count?: number | null
  acknowledgedAt?: string | null
  acknowledged_at?: string | null
  acknowledgedBy?: string | null
  acknowledged_by?: string | null
  resolvedAt?: string | null
  resolved_at?: string | null
  resolvedBy?: string | null
  resolved_by?: string | null
  reopenedAt?: string | null
  reopened_at?: string | null
  reopenedBy?: string | null
  reopened_by?: string | null
}

export interface DiscussionComposerProps {
  commentType: DiscussionCommentType
  commentText: string
  onCommentTypeChange?: (nextType: DiscussionCommentType) => void
  onCommentTextChange: (nextText: string) => void
  onSubmit: () => void
  submitLabel: string
  placeholder?: string
  disabled?: boolean
  typeOptions?: Array<{ value: DiscussionCommentType, label: string }>
  typeLabel?: string
  textareaLabel?: string
  typeSelectId?: string
  textareaId?: string
}

export interface DiscussionPanelProps {
  title: string
  entries: DiscussionEntry[]
  emptyState: string
  subtitle?: string
  className?: string
  composer?: DiscussionComposerProps | null
}

const DEFAULT_TYPE_OPTIONS: Array<{ value: DiscussionCommentType, label: string }> = [
  { value: 'general', label: 'General Note' },
  { value: 'note', label: 'Note' },
  { value: 'concern', label: 'Concern' },
  { value: 'question', label: 'Question' },
]

const DISCUSSION_TYPE_LABELS: Record<DiscussionCommentType, string> = {
  general: 'General',
  note: 'Note',
  concern: 'Concern',
  question: 'Question',
}

const DISCUSSION_STATE_LABELS: Record<DiscussionCommentState, string> = {
  new: 'New',
  acknowledged_by_owner: 'Acknowledged',
  voted_up: 'Voted up',
  resolved: 'Resolved',
  reopened: 'Reopened',
  locked: 'Locked',
}

const isDiscussionCommentType = (value: string): value is DiscussionCommentType => {
  return value === 'general' || value === 'note' || value === 'concern' || value === 'question'
}

const normalizeDiscussionCommentType = (value: unknown): DiscussionCommentType => {
  const normalized = String(value ?? '').trim().toLowerCase()
  return isDiscussionCommentType(normalized) ? normalized : 'general'
}

const isDiscussionCommentState = (value: string): value is DiscussionCommentState => {
  return value === 'new' || value === 'acknowledged_by_owner' || value === 'voted_up' || value === 'resolved' || value === 'reopened' || value === 'locked'
}

const normalizeDiscussionCommentState = (value: unknown): DiscussionCommentState | null => {
  const normalized = String(value ?? '').trim().toLowerCase().replace(/-/g, '_')
  return isDiscussionCommentState(normalized) ? normalized : null
}

const firstNonEmptyString = (...values: unknown[]): string | null => {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }
  return null
}

const formatDiscussionDate = (value: string): string => {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

export const normalizeDiscussionEntry = (entry: DiscussionEntryInput | string | null | undefined, fallbackAuthorName = 'System'): DiscussionEntry | null => {
  if (typeof entry === 'string') {
    const trimmed = entry.trim()
    if (!trimmed) {
      return null
    }
    const createdAt = new Date().toISOString()
    return {
      id: `discussion-${createdAt}`,
      authorId: null,
      authorName: fallbackAuthorName,
      content: trimmed,
      type: 'general',
      createdAt,
    }
  }

  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
    return null
  }

  const content = firstNonEmptyString(
    entry.content,
    entry.comment,
    entry.message,
    entry.body,
    entry.text,
  )
  const removed = Boolean(entry.removed)
  const resolvedContent = content || (removed ? '[removed]' : null)

  if (!resolvedContent) {
    return null
  }

  const createdAt = firstNonEmptyString(
    entry.createdAt,
    entry.created_at,
    entry.timestamp,
    entry.timestamp_at,
  ) || new Date().toISOString()

  return {
    id: firstNonEmptyString(entry.id) || `discussion-${createdAt}-${resolvedContent.slice(0, 12)}`,
    authorId: firstNonEmptyString(entry.authorId, entry.author_id),
    authorName: firstNonEmptyString(entry.authorName, entry.author_name) || fallbackAuthorName,
    content: resolvedContent,
    type: normalizeDiscussionCommentType(entry.type ?? entry.commentType ?? entry.comment_type),
    createdAt,
    state: normalizeDiscussionCommentState(entry.state),
    locked: Boolean(entry.locked),
    removed,
    removedAt: firstNonEmptyString(entry.removedAt, entry.removed_at),
    removedBy: firstNonEmptyString(entry.removedBy, entry.removed_by),
    removedReason: firstNonEmptyString(entry.removedReason, entry.removed_reason),
    edited: Boolean(entry.edited),
    editedAt: firstNonEmptyString(entry.editedAt, entry.edited_at),
    editedBy: firstNonEmptyString(entry.editedBy, entry.edited_by),
    editCount: typeof entry.editCount === 'number' ? entry.editCount : entry.edit_count ?? null,
    voteCount: typeof entry.voteCount === 'number' ? entry.voteCount : entry.vote_count ?? null,
    acknowledgedAt: firstNonEmptyString(entry.acknowledgedAt, entry.acknowledged_at),
    acknowledgedBy: firstNonEmptyString(entry.acknowledgedBy, entry.acknowledged_by),
    resolvedAt: firstNonEmptyString(entry.resolvedAt, entry.resolved_at),
    resolvedBy: firstNonEmptyString(entry.resolvedBy, entry.resolved_by),
    reopenedAt: firstNonEmptyString(entry.reopenedAt, entry.reopened_at),
    reopenedBy: firstNonEmptyString(entry.reopenedBy, entry.reopened_by),
  }
}

export const normalizeDiscussionEntries = (entries: unknown, fallbackAuthorName = 'System'): DiscussionEntry[] => {
  if (Array.isArray(entries)) {
    return entries
      .map((entry) => normalizeDiscussionEntry(entry as DiscussionEntryInput | string | null | undefined, fallbackAuthorName))
      .filter((entry): entry is DiscussionEntry => entry !== null)
  }

  const normalizedEntry = normalizeDiscussionEntry(entries as DiscussionEntryInput | string | null | undefined, fallbackAuthorName)
  return normalizedEntry ? [normalizedEntry] : []
}

export const DiscussionThread: React.FC<{
  title: string
  entries: DiscussionEntry[]
  emptyState: string
  subtitle?: string
  className?: string
}> = ({ title, entries, emptyState, subtitle, className }) => {
  return (
    <section className={`comment-thread-section${className ? ` ${className}` : ''}`}>
      <h5>{title}</h5>
      {subtitle && <p className="discussion-thread-subtitle">{subtitle}</p>}
      <div className="comment-thread">
        {entries.length === 0 ? (
          <div className="discussion-thread-empty-state">{emptyState}</div>
        ) : (
          entries.map((entry) => (
            <div key={entry.id} className="comment-item">
              <div className="comment-header">
                <span className="comment-author">{entry.authorName}</span>
                <span className={`comment-type comment-type-${entry.type}`}>
                  {DISCUSSION_TYPE_LABELS[entry.type]}
                </span>
                {entry.state && (
                  <span className={`comment-state comment-state-${entry.state}`}>
                    {DISCUSSION_STATE_LABELS[entry.state]}
                  </span>
                )}
                {entry.locked && <span className="comment-lock-state">Locked</span>}
                {entry.removed && <span className="comment-removal-state">Removed</span>}
                <span className="comment-time">{formatDiscussionDate(entry.createdAt)}</span>
                {entry.edited && <span className="discussion-entry-edited">Edited</span>}
              </div>
              <div className={`comment-content${entry.removed ? ' comment-content-removed' : ''}`}>
                {entry.content}
              </div>
              {entry.removedReason && <div className="discussion-entry-meta">Reason: {entry.removedReason}</div>}
            </div>
          ))
        )}
      </div>
    </section>
  )
}

export const DiscussionComposer: React.FC<DiscussionComposerProps> = ({
  commentType,
  commentText,
  onCommentTypeChange,
  onCommentTextChange,
  onSubmit,
  submitLabel,
  placeholder = 'Add a comment...',
  disabled = false,
  typeOptions = DEFAULT_TYPE_OPTIONS,
  typeLabel = 'Comment type',
  textareaLabel = 'Comment',
  typeSelectId = 'discussion-comment-type',
  textareaId = 'discussion-comment-text',
}) => {
  const trimmedText = commentText.trim()

  return (
    <div className="comment-input-section">
      <div className="comment-input-header">
        <label htmlFor={typeSelectId}>{typeLabel}:</label>
        <select
          id={typeSelectId}
          className="comment-type-select"
          value={commentType}
          onChange={(event) => onCommentTypeChange?.(normalizeDiscussionCommentType(event.target.value))}
          disabled={disabled || !onCommentTypeChange}
        >
          {typeOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <label className="discussion-textarea-label" htmlFor={textareaId}>
        {textareaLabel}
      </label>
      <textarea
        id={textareaId}
        className="discussion-textarea"
        placeholder={placeholder}
        value={commentText}
        onChange={(event) => onCommentTextChange(event.target.value)}
        disabled={disabled}
        rows={3}
      />

      <button
        type="button"
        className="discussion-submit-button"
        onClick={onSubmit}
        disabled={disabled || trimmedText.length === 0}
      >
        {submitLabel}
      </button>
    </div>
  )
}

export const DiscussionPanel: React.FC<DiscussionPanelProps> = ({
  title,
  entries,
  emptyState,
  subtitle,
  className,
  composer,
}) => {
  return (
    <section className={`comment-thread-section${className ? ` ${className}` : ''}`}>
      <h5>{title}</h5>
      {subtitle && <p className="discussion-thread-subtitle">{subtitle}</p>}
      <div className="comment-thread">
        {entries.length === 0 ? (
          <div className="discussion-thread-empty-state">{emptyState}</div>
        ) : (
          entries.map((entry) => (
            <div key={entry.id} className="comment-item">
              <div className="comment-header">
                <span className="comment-author">{entry.authorName}</span>
                <span className={`comment-type comment-type-${entry.type}`}>
                  {DISCUSSION_TYPE_LABELS[entry.type]}
                </span>
                {entry.state && (
                  <span className={`comment-state comment-state-${entry.state}`}>
                    {DISCUSSION_STATE_LABELS[entry.state]}
                  </span>
                )}
                {entry.locked && <span className="comment-lock-state">Locked</span>}
                {entry.removed && <span className="comment-removal-state">Removed</span>}
                <span className="comment-time">{formatDiscussionDate(entry.createdAt)}</span>
                {entry.edited && <span className="discussion-entry-edited">Edited</span>}
              </div>
              <div className={`comment-content${entry.removed ? ' comment-content-removed' : ''}`}>
                {entry.content}
              </div>
              {entry.removedReason && <div className="discussion-entry-meta">Reason: {entry.removedReason}</div>}
            </div>
          ))
        )}
      </div>
      {composer && (
        <DiscussionComposer
          commentType={composer.commentType}
          commentText={composer.commentText}
          onCommentTypeChange={composer.onCommentTypeChange}
          onCommentTextChange={composer.onCommentTextChange}
          onSubmit={composer.onSubmit}
          submitLabel={composer.submitLabel}
          placeholder={composer.placeholder}
          disabled={composer.disabled}
          typeOptions={composer.typeOptions}
          typeLabel={composer.typeLabel}
          textareaLabel={composer.textareaLabel}
          typeSelectId={composer.typeSelectId}
          textareaId={composer.textareaId}
        />
      )}
    </section>
  )
}