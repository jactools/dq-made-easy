/// <reference types="vite/client" />

declare module '*.md?raw' {
  const content: string
  export default content
}

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_SSO_PROVIDER?: string
  readonly VITE_SSO_ISSUER_URL?: string
  readonly VITE_SSO_CLIENT_ID?: string
  readonly VITE_SSO_ENABLED?: string
  readonly VITE_OTEL_ENDPOINT?: string
  readonly VITE_ENVIRONMENT?: string
  readonly VITE_SERVICE_VERSION?: string
  readonly VITE_OTEL_ENABLED?: string
  readonly VITE_OTEL_SAMPLE_RATIO?: string
  readonly OTEL_SERVICE_NAME?: string
  readonly OTEL_SERVICE_VERSION?: string
}

interface ImportMeta {
  glob: (pattern: string, options?: { eager?: boolean }) => Record<string, any>
}

declare const __APP_VERSION__: string

interface Window {
  __DQ_CONFIG__?: {
    API_BASE_URL?: string
  }
}

