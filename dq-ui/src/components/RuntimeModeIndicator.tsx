import React from 'react'

type RuntimeMode = 'vite-dev' | 'nginx-prod'

const isViteClientRuntime = (): boolean => {
  if (typeof window === 'undefined' || typeof document === 'undefined') return false

  const vitePreamble = Boolean((window as any).__vite_plugin_react_preamble_installed__)
  const hasViteClientScript = Array.from(document.scripts).some((script) =>
    (script.src || '').includes('/@vite/client')
  )

  return vitePreamble || hasViteClientScript
}

const getRuntimeMode = (): RuntimeMode => {
  if (import.meta.env.DEV) return 'vite-dev'
  if (isViteClientRuntime()) return 'vite-dev'
  return 'nginx-prod'
}

export function RuntimeModeIndicator() {
  const mode = getRuntimeMode()
  const isDev = mode === 'vite-dev'

  return (
    <div
      className={`runtime-mode-indicator ${isDev ? 'runtime-mode-indicator-dev' : 'runtime-mode-indicator-prod'}`}
      title={isDev ? 'Served by Vite development server' : 'Served by frontend container (production build)'}
      aria-live="polite"
    >
      {isDev ? 'Vite Dev' : 'Nginx Prod'}
    </div>
  )
}
