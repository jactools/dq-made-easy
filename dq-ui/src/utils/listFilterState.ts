export interface UrlFilterDefinition<T extends string = string> {
  param: string
  defaultValue: T
  allowedValues?: readonly T[]
}

export type UrlFilterDefinitions = Record<string, UrlFilterDefinition>
export type UrlFilterValues<TDefinitions extends UrlFilterDefinitions> = {
  [K in keyof TDefinitions]: string
}

export const DEFAULT_SEARCH_MINIMUM_LENGTH = 3

const normalizeWhitespace = (value: string): string => value.trim().replace(/\s+/g, ' ')

export const normalizeSearchQuery = (value: unknown): string => normalizeWhitespace(String(value || ''))

export const tokenizeSearchQuery = (value: unknown): string[] => {
  const normalized = normalizeSearchQuery(value).toLowerCase()
  return normalized ? normalized.split(' ').filter(Boolean) : []
}

export const committedSearchValue = (value: unknown, minimumLength = DEFAULT_SEARCH_MINIMUM_LENGTH): string => {
  const normalized = normalizeSearchQuery(value)
  return normalized.length === 0 || normalized.length >= minimumLength ? normalized : ''
}

export const searchTokensForInput = (value: unknown, minimumLength = DEFAULT_SEARCH_MINIMUM_LENGTH): string[] => {
  return tokenizeSearchQuery(committedSearchValue(value, minimumLength))
}

export const matchesTokenizedSearch = (
  values: unknown[],
  searchValue: unknown,
  minimumLength = DEFAULT_SEARCH_MINIMUM_LENGTH,
): boolean => {
  const tokens = searchTokensForInput(searchValue, minimumLength)
  if (tokens.length === 0) return true

  const haystack = values
    .map((value) => String(value || '').trim().toLowerCase())
    .filter(Boolean)
    .join(' ')

  return tokens.every((token) => haystack.includes(token))
}

export const readUrlFilterState = <TDefinitions extends UrlFilterDefinitions>(
  search: string,
  definitions: TDefinitions,
): UrlFilterValues<TDefinitions> => {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const values = {} as UrlFilterValues<TDefinitions>

  for (const [key, definition] of Object.entries(definitions)) {
    const rawValue = normalizeWhitespace(params.get(definition.param) || '')
    const allowedValues = definition.allowedValues as readonly string[] | undefined
    values[key as keyof TDefinitions] = (
      rawValue && (!allowedValues || allowedValues.includes(rawValue))
        ? rawValue
        : definition.defaultValue
    ) as UrlFilterValues<TDefinitions>[keyof TDefinitions]
  }

  return values
}

export const serializeUrlFilterState = <TDefinitions extends UrlFilterDefinitions>(
  currentSearch: string,
  definitions: TDefinitions,
  values: Partial<UrlFilterValues<TDefinitions>>,
): string => {
  const params = new URLSearchParams(currentSearch.startsWith('?') ? currentSearch.slice(1) : currentSearch)

  for (const [key, definition] of Object.entries(definitions)) {
    const value = normalizeWhitespace(String(values[key as keyof TDefinitions] ?? definition.defaultValue))
    if (!value || value === definition.defaultValue) {
      params.delete(definition.param)
    } else {
      params.set(definition.param, value)
    }
  }

  const serialized = params.toString()
  return serialized ? `?${serialized}` : ''
}
