// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { isUiTelemetrySuppressedUrl, normalizeUiPageName, patchFetchForCorrelationHeader } from '../telemetry'

describe('telemetry fetch patch', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // Clear any existing patched fetch
    try {
      // @ts-ignore
      delete (globalThis as any).fetch
    } catch {
      ;(globalThis as any).fetch = undefined
    }
    if (typeof window !== 'undefined' && window.sessionStorage && typeof window.sessionStorage.clear === 'function') {
      window.sessionStorage.clear()
    }
  })

  it('converts outgoing request bodies to snake_case and adds correlation header', async () => {
    const captured: any = {}
    const originalFetch = vi.fn((input: any, init?: any) => {
      captured.input = input
      captured.init = init
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } }))
    })

    // Set the existing fetch to our originalFetch so the patch wraps it
    ;(globalThis as any).fetch = originalFetch

    patchFetchForCorrelationHeader()

    await fetch('/rulebuilder/v1/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sampleCount: 5 }) })

    expect(captured.init).toBeDefined()
    const parsedBody = JSON.parse(captured.init.body)
    expect(parsedBody).toHaveProperty('sample_count', 5)

    // Headers are passed as a Headers instance
    const headers = captured.init.headers
    expect(typeof headers.get === 'function').toBeTruthy()
    expect(headers.get('X-Correlation-ID')).toBeTruthy()
  })

  it('normalizes incoming JSON responses to camelCase', async () => {
    const originalFetch = vi.fn((input: any, init?: any) => {
      return Promise.resolve(new Response(JSON.stringify({ my_value: 123 }), { headers: { 'Content-Type': 'application/json' } }))
    })

    ;(globalThis as any).fetch = originalFetch
    patchFetchForCorrelationHeader()

    const response = await fetch('/system/v1/some')
    const json = await response.json()
    expect(json).toEqual({ myValue: 123 })
  })

  it('suppresses telemetry for the admin me endpoint', async () => {
    expect(isUiTelemetrySuppressedUrl('/api/admin/v1/me')).toBe(true)
    expect(isUiTelemetrySuppressedUrl('/api/admin/v1/me?foo=bar')).toBe(true)
    expect(isUiTelemetrySuppressedUrl('/api/admin/v1/me/profile')).toBe(false)

    const originalFetch = vi.fn((input: any, init?: any) => {
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } }))
    })

    ;(globalThis as any).fetch = originalFetch
    patchFetchForCorrelationHeader()

    await fetch('/api/admin/v1/me', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sampleCount: 5 }),
    })

    const capturedInit = originalFetch.mock.calls[0]?.[1]
    expect(capturedInit.headers?.get?.('X-Correlation-ID')).toBeUndefined()
    expect(capturedInit.body).toBe(JSON.stringify({ sampleCount: 5 }))
  })

  it('keeps Rules and Rule Quality page views distinct', () => {
    expect(normalizeUiPageName('rules-my')).toBe('rules')
    expect(normalizeUiPageName('rule-quality-validation')).toBe('rule_quality')
    expect(normalizeUiPageName('approvals-my')).toBe('governance')
    expect(normalizeUiPageName('reports-metrics')).toBe('operations')
  })

  it('still patches fetch when browser OTLP export is disabled by an insecure endpoint on HTTPS', async () => {
    const originalFetch = vi.fn((input: any, init?: any) => {
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } }))
    })

    ;(globalThis as any).fetch = originalFetch

    Object.defineProperty(window, 'isSecureContext', {
      value: true,
      configurable: true,
    })

    vi.stubEnv('VITE_OTEL_ENDPOINT', 'http://observability.jac.dot:4318')

    vi.resetModules()
    const { initTelemetry } = await import('../telemetry')
    initTelemetry()

    await fetch('/system/v1/trace-test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sampleCount: 5 }) })

    expect(originalFetch).toHaveBeenCalled()
    const capturedInit = originalFetch.mock.calls[0]?.[1]
    expect(JSON.parse(capturedInit.body)).toHaveProperty('sample_count', 5)
  })

  it('keeps telemetry bootstrap quiet while the collector is down and reports the unavailable status', async () => {
    const originalFetch = vi.fn((input: any, init?: any) => {
      if (String(init?.method || '').toUpperCase() === 'OPTIONS') {
        return Promise.reject(new TypeError('Failed to fetch'))
      }

      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } }))
    })

    ;(globalThis as any).fetch = originalFetch

    Object.defineProperty(window, 'isSecureContext', {
      value: false,
      configurable: true,
    })

    vi.stubEnv('VITE_OTEL_ENDPOINT', 'http://observability.jac.dot:4318')

    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    vi.resetModules()
    const { getUiTelemetryConnectionState, initTelemetry } = await import('../telemetry')
    initTelemetry()

    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(getUiTelemetryConnectionState()).toBe('unavailable')
    expect(originalFetch).toHaveBeenCalledWith(
      'http://observability.jac.dot:4318/v1/traces',
      expect.objectContaining({ method: 'OPTIONS', mode: 'cors', credentials: 'omit' }),
    )
    expect(consoleErrorSpy).not.toHaveBeenCalled()
  })

  it('treats a 405 OTLP OPTIONS probe as reachable and starts telemetry once', async () => {
    const originalFetch = vi.fn((input: any, init?: any) => {
      if (String(init?.method || '').toUpperCase() === 'OPTIONS') {
        return Promise.resolve(new Response(null, { status: 405 }))
      }

      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } }))
    })

    ;(globalThis as any).fetch = originalFetch

    Object.defineProperty(window, 'isSecureContext', {
      value: false,
      configurable: true,
    })

    vi.stubEnv('VITE_OTEL_ENDPOINT', 'http://observability.jac.dot:4318')

    vi.resetModules()
    const { getUiTelemetryConnectionState, initTelemetry } = await import('../telemetry')
    initTelemetry()

    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(getUiTelemetryConnectionState()).toBe('available')
    expect(originalFetch).toHaveBeenCalledTimes(1)
    expect(originalFetch).toHaveBeenCalledWith(
      'http://observability.jac.dot:4318/v1/traces',
      expect.objectContaining({ method: 'OPTIONS', mode: 'cors', credentials: 'omit' }),
    )
  })
})
