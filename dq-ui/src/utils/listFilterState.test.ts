import { describe, expect, it } from 'vitest'

import {
  committedSearchValue,
  matchesTokenizedSearch,
  readUrlFilterState,
  searchTokensForInput,
  serializeUrlFilterState,
  tokenizeSearchQuery,
} from './listFilterState'

const definitions = {
  scope: { param: 'rules_scope', defaultValue: 'my', allowedValues: ['my', 'team', 'all', 'global'] },
  status: { param: 'rules_status', defaultValue: 'all', allowedValues: ['all', 'draft', 'activated'] },
  query: { param: 'rules_q', defaultValue: '' },
}

describe('list filter state utilities', () => {
  it('reads allowed URL filter values and rejects unsupported values', () => {
    const values = readUrlFilterState('?rules_scope=global&rules_status=unknown&rules_q= customer   id ', definitions)

    expect(values).toEqual({
      scope: 'global',
      status: 'all',
      query: 'customer id',
    })
  })

  it('serializes non-default values while preserving unrelated query params', () => {
    const search = serializeUrlFilterState('?tab=rules&rules_status=draft', definitions, {
      scope: 'team',
      status: 'all',
      query: 'email address',
    })

    expect(search).toBe('?tab=rules&rules_scope=team&rules_q=email+address')
  })

  it('normalizes token search consistently', () => {
    expect(tokenizeSearchQuery('  Data   Object  ')).toEqual(['data', 'object'])
    expect(searchTokensForInput('ab', 3)).toEqual([])
    expect(searchTokensForInput('abc def', 3)).toEqual(['abc', 'def'])
    expect(committedSearchValue('ab', 3)).toBe('')
    expect(committedSearchValue('abc', 3)).toBe('abc')
  })

  it('matches every committed token across searchable values', () => {
    expect(matchesTokenizedSearch(['Customer Account', 'active status'], 'customer active')).toBe(true)
    expect(matchesTokenizedSearch(['Customer Account', 'active status'], 'customer missing')).toBe(false)
    expect(matchesTokenizedSearch(['Customer Account'], 'cu')).toBe(true)
  })
})
