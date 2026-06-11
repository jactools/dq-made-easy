import { useMemo } from 'react'

export type EntityViewScope = 'my' | 'team' | 'all' | 'global'

interface ComputeEntityScopedItemsParams<T> {
  viewScope: EntityViewScope
  canViewAllItems: boolean
  allItems: T[]
  workspaceItems: T[]
  isItemOwnedByCurrentUser: (item: T) => boolean
  matchesAllScope: (item: T) => boolean
}

interface ComputeEntityEmptyMessageParams {
  viewScope: EntityViewScope
  canViewAllItems: boolean
  messages: {
    my: string
    team: string
    all: string
    global: string
  }
}

interface UseEntityScopeParams<T> {
  viewScope: EntityViewScope
  canViewAllItems: boolean
  allItems: T[]
  workspaceItems: T[]
  isItemOwnedByCurrentUser: (item: T) => boolean
  matchesAllScope: (item: T) => boolean
  messages: {
    my: string
    team: string
    all: string
    global: string
  }
}

export const computeEntityScopedItems = <T,>({
  viewScope,
  canViewAllItems,
  allItems,
  workspaceItems,
  isItemOwnedByCurrentUser,
  matchesAllScope,
}: ComputeEntityScopedItemsParams<T>): T[] => {
  if (viewScope === 'global' && canViewAllItems) {
    return allItems
  }

  if (viewScope === 'all' && canViewAllItems) {
    return allItems.filter(matchesAllScope)
  }

  if (viewScope === 'team') {
    return workspaceItems.filter((item) => !isItemOwnedByCurrentUser(item))
  }

  return workspaceItems.filter((item) => isItemOwnedByCurrentUser(item))
}

export const computeEntityEmptyMessage = ({
  viewScope,
  canViewAllItems,
  messages,
}: ComputeEntityEmptyMessageParams): string => {
  if (viewScope === 'global' && canViewAllItems) {
    return messages.global
  }

  if (viewScope === 'all' && canViewAllItems) {
    return messages.all
  }

  if (viewScope === 'team') {
    return messages.team
  }

  return messages.my
}

export const useEntityScope = <T,>({
  viewScope,
  canViewAllItems,
  allItems,
  workspaceItems,
  isItemOwnedByCurrentUser,
  matchesAllScope,
  messages,
}: UseEntityScopeParams<T>) => {
  const scopedItems = useMemo(() => {
    return computeEntityScopedItems({
      viewScope,
      canViewAllItems,
      allItems,
      workspaceItems,
      isItemOwnedByCurrentUser,
      matchesAllScope,
    })
  }, [
    viewScope,
    canViewAllItems,
    allItems,
    workspaceItems,
    isItemOwnedByCurrentUser,
    matchesAllScope,
  ])

  const emptyMessage = useMemo(() => {
    return computeEntityEmptyMessage({ viewScope, canViewAllItems, messages })
  }, [viewScope, canViewAllItems, messages])

  return {
    scopedItems,
    emptyMessage,
  }
}
