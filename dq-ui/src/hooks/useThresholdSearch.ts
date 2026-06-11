import { useCallback, useState } from 'react'
import { DEFAULT_SEARCH_MINIMUM_LENGTH, committedSearchValue, normalizeSearchQuery } from '../utils/listFilterState'

interface UseThresholdSearchOptions {
  minimumLength?: number
  initialValue?: string
}

export const useThresholdSearch = ({ minimumLength = DEFAULT_SEARCH_MINIMUM_LENGTH, initialValue = '' }: UseThresholdSearchOptions = {}) => {
  const [inputValue, setInputValue] = useState(initialValue)
  const [searchValue, setSearchValue] = useState(initialValue)

  const setValue = useCallback((nextValue: string) => {
    const normalizedValue = normalizeSearchQuery(nextValue)
    setInputValue(nextValue)
    setSearchValue(committedSearchValue(normalizedValue, minimumLength))
  }, [minimumLength])

  const reset = useCallback(() => {
    setInputValue('')
    setSearchValue('')
  }, [])

  return {
    inputValue,
    searchValue,
    setValue,
    reset,
    minimumLength,
  }
}