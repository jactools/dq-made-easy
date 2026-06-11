import { beforeAll } from 'vitest'

beforeAll(() => {
  const g: any = globalThis as any

  // Ensure a window-like object exists for modules that consult window.__DQ_CONFIG__.
  if (!g.window) {
    g.window = {}
  }

  if (!g.window.location) {
    g.window.location = { hostname: 'localhost', origin: 'http://localhost' }
  }

  if (!g.window.__DQ_CONFIG__) {
    g.window.__DQ_CONFIG__ = {}
  }

  // Tests must explicitly configure the API base URL (no implicit fallbacks).
  if (!g.window.__DQ_CONFIG__.API_BASE_URL) {
    g.window.__DQ_CONFIG__.API_BASE_URL = 'http://localhost:9111'
  }
})
