import { describe, expect, it, vi } from 'vitest'

import { canUseBrowserSsoAuth, buildSsoRedirectUrl } from './browserAuthClient'

describe('browserAuthClient', () => {
  it('validates a secure issuer URL for SSO redirect support', () => {
    expect(canUseBrowserSsoAuth('http://keycloak.jac.dot:8080/realms/jaccloud')).toBe(false)
    expect(canUseBrowserSsoAuth('https://keycloak.jac.dot/realms/jaccloud')).toBe(true)
  })

  it('builds the redirect flow URL from a relative API base using the browser origin', () => {
    const redirectUrl = buildSsoRedirectUrl('/api/auth/v1', 'https://frontend.example/login')

    expect(redirectUrl.origin).toBe(window.location.origin)
    expect(redirectUrl.pathname).toBe('/api/auth/v1/redirect')
    expect(redirectUrl.searchParams.get('frontend')).toBe('https://frontend.example/login')
  })
})