export interface SsoCallbackTokens {
  authToken: string
  authIdToken: string | null
  refreshToken: string | null
}

const normalizeUrlPart = (value: string): string => value.trim().replace(/\/+$/, '')

export const buildSsoRedirectUrl = (
  apiBaseUrl: string,
  frontendOrigin: string,
  browserHostname?: string,
): URL => {
  const redirectPath = `${normalizeUrlPart(apiBaseUrl)}/redirect`
  const redirectUrl = typeof window !== 'undefined' && window.location?.origin
    ? new URL(redirectPath, window.location.origin)
    : new URL(redirectPath)

  if (browserHostname) {
    const targetHost = redirectUrl.hostname === 'localhost' || redirectUrl.hostname === '127.0.0.1'
    const browserIsLocalhost = browserHostname === 'localhost' || browserHostname === '127.0.0.1'
    if (targetHost && !browserIsLocalhost) {
      redirectUrl.hostname = browserHostname
    }
  }

  if (frontendOrigin) {
    redirectUrl.searchParams.set('frontend', frontendOrigin)
  }

  return redirectUrl
}

export const readSsoCallbackTokens = (search: string, hash: string): SsoCallbackTokens | null => {
  const searchParams = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const hashParams = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash)

  const authToken = searchParams.get('auth_token') || hashParams.get('auth_token')
  if (!authToken) {
    return null
  }

  return {
    authToken,
    authIdToken: searchParams.get('auth_id_token') || hashParams.get('auth_id_token') || null,
    refreshToken: searchParams.get('refresh_token') || hashParams.get('refresh_token') || null,
  }
}

export const canUseBrowserSsoAuth = (issuerUrl?: string): boolean => {
  if (typeof window === 'undefined') {
    return false
  }

  const configuredIssuerUrl = String(
    issuerUrl
    || import.meta.env.VITE_SSO_ISSUER_URL
    || import.meta.env.VITE_KEYCLOAK_PUBLIC_URL
    || '',
  ).trim()

  if (!configuredIssuerUrl) {
    return false
  }

  try {
    const parsed = new URL(configuredIssuerUrl)
    return parsed.protocol === 'https:' && Boolean(parsed.hostname)
  } catch {
    return false
  }
}
