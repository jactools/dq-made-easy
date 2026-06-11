const createRandomFragment = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().replace(/-/g, '').slice(0, 12).toUpperCase()
  }

  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`.toUpperCase()
}

export const createSupportReferenceId = (): string => `SUP-${createRandomFragment()}`

export const formatSupportReferenceId = (referenceId: string): string => {
  const normalized = String(referenceId || '').trim()
  return normalized ? `Reference ID: ${normalized}` : 'Reference ID: n/a'
}
