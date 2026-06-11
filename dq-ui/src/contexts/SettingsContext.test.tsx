import { describe, expect, it } from 'vitest'

import { normalizePreferences } from './SettingsContext'

describe('normalizePreferences', () => {
  it('hydrates api preferences from snake_case backend payloads into camelCase UI values', () => {
    const normalized = normalizePreferences({
      api: {
        rate_limit_per_minute: 120,
        webhook_url: 'https://example.test/webhook',
        allowed_origins: ['https://app.test'],
        encryption_enabled: true,
        audit_logging_enabled: false,
        api_timeout: 45,
      },
    })

    expect(normalized.api).toEqual({
      rateLimitPerMinute: 120,
      webhookUrl: 'https://example.test/webhook',
      allowedOrigins: ['https://app.test'],
      encryptionEnabled: true,
      auditLoggingEnabled: false,
      apiTimeout: 45,
    })
  })
})
