const stripTrailingSlash = (value: string): string => value.replace(/\/$/, '')
const stripTrailingVersionSegment = (value: string): string =>
  value.replace(/\/[a-z0-9-]+\/v\d+$/i, '').replace(/\/v\d+$/i, '')
const INTERNAL_DOCKER_HOST_ALIASES = new Set(['kong', 'api', 'db', 'redis', 'keycloak'])

const rewriteLegacyOrInternalBrowserUrl = (value: string): string => {
  let normalized = stripTrailingSlash(value)

  if (typeof window !== 'undefined') {
    try {
      const parsed = new URL(normalized)

      if (INTERNAL_DOCKER_HOST_ALIASES.has(parsed.hostname)) {
        parsed.hostname = window.location.hostname || 'localhost'
      }

      if (parsed.port === '4001') {
        parsed.port = '4010'
      }

      normalized = stripTrailingSlash(parsed.toString())
    } catch {
      // Keep original value if not a valid absolute URL.
    }
  }

  return normalized
}

export const getConfiguredApiBaseUrl = (): string => {
  const runtimeValue =
    (typeof window !== 'undefined' && window.__DQ_CONFIG__?.API_BASE_URL
      ? window.__DQ_CONFIG__.API_BASE_URL
      : '')
      .trim()

  const envValue =
    (import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || '').trim()
  // No implicit fallbacks: API base URL must be explicitly configured.
  return rewriteLegacyOrInternalBrowserUrl(runtimeValue || envValue || '')
}

export const normalizeApiBaseUrl = (value?: string | null): string => {
  const raw = (value || '').trim()
  if (!raw) {
    const configured = getConfiguredApiBaseUrl()
    if (!configured) {
      throw new Error(
        'API base URL is not configured. Set window.__DQ_CONFIG__.API_BASE_URL or VITE_API_BASE_URL.'
      )
    }
    return configured
  }
  const normalized = rewriteLegacyOrInternalBrowserUrl(raw)
  return stripTrailingVersionSegment(normalized)
}

export const toApiGroupV1Base = (group: string, value?: string | null): string => {
  const trimmed = (group || '').trim().replace(/^\/+|\/+$/g, '')
  if (!trimmed) throw new Error('API group is required')
  return `${normalizeApiBaseUrl(value)}/${trimmed}/v1`
}
