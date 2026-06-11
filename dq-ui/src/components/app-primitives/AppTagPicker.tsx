import React, { useId, useMemo, useState } from 'react'
import './AppPrimitives.css'
import { AppField } from './AppField'
import { AppIcon } from './AppIcon'
import { joinClassNames } from './joinClassNames'

export interface AppTagPickerProps {
  label: React.ReactNode
  selectedTags: string[]
  availableTags: string[]
  onChange: (tags: string[]) => void
  hint?: React.ReactNode
  placeholder?: string
  fieldClassName?: string
  labelClassName?: string
  className?: string
}

const normalizeTag = (value: string): string => String(value || '').trim()

const dedupeTags = (values: string[]): string[] => {
  const seen = new Set<string>()
  const tags: string[] = []

  for (const value of values) {
    const tag = normalizeTag(value)
    const key = tag.toLowerCase()
    if (!tag || seen.has(key)) {
      continue
    }
    seen.add(key)
    tags.push(tag)
  }

  return tags
}

export const AppTagPicker: React.FC<AppTagPickerProps> = ({
  label,
  selectedTags,
  availableTags,
  onChange,
  hint,
  placeholder = 'Type a tag and press Enter',
  fieldClassName,
  labelClassName,
  className,
}) => {
  const inputId = useId()
  const [query, setQuery] = useState('')
  const [isFocused, setIsFocused] = useState(false)

  const normalizedSelectedTags = useMemo(() => dedupeTags(selectedTags), [selectedTags])
  const normalizedAvailableTags = useMemo(() => dedupeTags(availableTags), [availableTags])
  const selectedTagKeys = useMemo(() => new Set(normalizedSelectedTags.map((tag) => tag.toLowerCase())), [normalizedSelectedTags])

  const queryValue = query.trim()
  const matchingTags = useMemo(() => {
    const normalizedQuery = queryValue.toLowerCase()
    const suggestions = normalizedAvailableTags.filter((tag) => {
      if (selectedTagKeys.has(tag.toLowerCase())) {
        return false
      }
      if (!normalizedQuery) {
        return true
      }
      return tag.toLowerCase().includes(normalizedQuery)
    })
    return suggestions.slice(0, 8)
  }, [normalizedAvailableTags, queryValue, selectedTagKeys])

  const commitTag = (value: string) => {
    const tag = normalizeTag(value)
    if (!tag) {
      return
    }

    const normalizedTag = tag.toLowerCase()
    if (selectedTagKeys.has(normalizedTag)) {
      setQuery('')
      setIsFocused(true)
      return
    }

    onChange(dedupeTags([...normalizedSelectedTags, tag]))
    setQuery('')
    setIsFocused(true)
  }

  const removeTag = (tagToRemove: string) => {
    const normalizedTag = normalizeTag(tagToRemove).toLowerCase()
    onChange(normalizedSelectedTags.filter((tag) => tag.toLowerCase() !== normalizedTag))
  }

  const canCreateTag = queryValue.length > 0 && !selectedTagKeys.has(queryValue.toLowerCase())

  return (
    <AppField
      label={label}
      htmlFor={inputId}
      hint={hint}
      className={fieldClassName}
      labelClassName={labelClassName}
    >
      <div className={joinClassNames('app-tag-picker', className)}>
        {normalizedSelectedTags.length > 0 ? (
          <div className="app-tag-picker__chips" aria-label="Selected tags">
            {normalizedSelectedTags.map((tag) => (
              <button
                key={tag}
                type="button"
                className="app-tag-picker__chip"
                onClick={() => removeTag(tag)}
                title={`Remove ${tag}`}
              >
                <AppIcon name="tag" className="app-tag-picker__chip-icon" aria-hidden="true" />
                <span>{tag}</span>
                <span aria-hidden="true" className="app-tag-picker__chip-remove">×</span>
              </button>
            ))}
          </div>
        ) : null}

        <div className="app-tag-picker__composer">
          <input
            id={inputId}
            className="app-control app-input app-tag-picker__input"
            value={query}
            placeholder={placeholder}
            autoComplete="off"
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ',') {
                event.preventDefault()
                commitTag(queryValue)
                return
              }

              if (event.key === 'Backspace' && !queryValue && normalizedSelectedTags.length > 0) {
                event.preventDefault()
                removeTag(normalizedSelectedTags[normalizedSelectedTags.length - 1])
              }
            }}
          />

          {isFocused && (matchingTags.length > 0 || canCreateTag) ? (
            <div className="app-tag-picker__menu" role="listbox" aria-label="Tag suggestions">
              {matchingTags.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  className="app-tag-picker__option"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => commitTag(tag)}
                >
                  <AppIcon name="tag" className="app-tag-picker__option-icon" aria-hidden="true" />
                  <span>{tag}</span>
                </button>
              ))}

              {canCreateTag ? (
                <button
                  type="button"
                  className="app-tag-picker__option app-tag-picker__option--create"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => commitTag(queryValue)}
                >
                  <AppIcon name="tag" className="app-tag-picker__option-icon" aria-hidden="true" />
                  <span>Create tag “{queryValue}”</span>
                </button>
              ) : null}
            </div>
          ) : null}
        </div>

        {normalizedAvailableTags.length > 0 ? (
          <div className="app-tag-picker__footer">
            <span>{normalizedAvailableTags.length} available tag{normalizedAvailableTags.length === 1 ? '' : 's'}</span>
            <span>{normalizedSelectedTags.length} selected</span>
          </div>
        ) : null}
      </div>
    </AppField>
  )
}
