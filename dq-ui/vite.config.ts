import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import * as fs from 'fs'
import * as path from 'path'

const packageJson = JSON.parse(fs.readFileSync('./package.json', 'utf-8'))
const buildDate = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long' })
const devServerHost = process.env.VITE_HOST || '0.0.0.0'
const devServerPort = Number(process.env.VITE_PORT || '5174')
const allowedHosts = ['dq-made-easy.local', 'localhost', '127.0.0.1', 'dq-made-easy.jac.dot']
const iconManifestRoute = '/assets/icon-manifest.json'
const useDevHttps = process.env.VITE_DEV_HTTPS === 'true'
const devHttpsKeyFile = process.env.VITE_HTTPS_KEY_FILE || path.resolve('..', 'tmp', 'certs', 'dq-made-easy.jac.dot+3-key.pem')
const devHttpsCertFile = process.env.VITE_HTTPS_CERT_FILE || path.resolve('..', 'tmp', 'certs', 'dq-made-easy.jac.dot+3.pem')

const isAbsoluteHttpUrl = (value?: string): value is string => Boolean(value && /^https?:\/\//i.test(value))

const resolveDevApiProxyTarget = (command: 'build' | 'serve'): string | undefined => {
  if (command !== 'serve') {
    return undefined
  }

  const candidates = [
    process.env.VITE_API_PROXY_TARGET,
    process.env.KONG_LOCAL_URL,
    process.env.KONG_PUBLIC_URL,
  ]

  for (const candidate of candidates) {
    if (isAbsoluteHttpUrl(candidate)) {
      return candidate
    }
  }

  throw new Error(
    'Vite dev proxy target is not configured. Set VITE_API_PROXY_TARGET or KONG_LOCAL_URL before starting the dev server.'
  )
}

const resolveDevOtelProxyTarget = (command: 'build' | 'serve'): string | undefined => {
  if (command !== 'serve') {
    return undefined
  }

  const target = process.env.VITE_OTEL_PROXY_TARGET
  if (isAbsoluteHttpUrl(target)) {
    return target
  }

  throw new Error(
    'Vite OTLP proxy target is not configured. Set VITE_OTEL_PROXY_TARGET before starting the dev server.'
  )
}

const devServerHttps = useDevHttps
  ? {
      key: fs.readFileSync(devHttpsKeyFile),
      cert: fs.readFileSync(devHttpsCertFile),
    }
  : undefined

const publicHmrHost = (() => {
  const hmrHost = process.env.VITE_HMR_HOST || process.env.UI_VITE_LOCAL_URL || 'https://dq-made-easy.jac.dot:5174'
  try {
    return new URL(hmrHost).hostname
  } catch {
    return hmrHost || 'dq-made-easy.jac.dot'
  }
})()

const resolveIconSourceDir = (): string | null => {
  const candidates = [
    path.resolve('dist/assets/icon'),
  ]

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate
    }
  }

  return null
}

const userManualsPublicDir = path.resolve('public/user-manuals')

const rewriteUserManualsRequest = (requestPath: string): string | null => {
  if (requestPath === '/user-manuals' || requestPath === '/user-manuals/') {
    return '/user-manuals/index.html'
  }

  if (!requestPath.startsWith('/user-manuals/')) {
    return null
  }

  if (requestPath.endsWith('.html') || requestPath.endsWith('/')) {
    return null
  }

  const relativeSlug = requestPath.slice('/user-manuals/'.length)
  const candidateHtml = path.join(userManualsPublicDir, `${relativeSlug}.html`)
  if (fs.existsSync(candidateHtml)) {
    return `${requestPath}.html`
  }

  return null
}

const serveUserManualsPublicPath = (server: { middlewares: { use: (handler: (req: { url?: string }, res: { setHeader: (name: string, value: string) => void; end: (body: string) => void }, next: () => void) => void) => void } }) => {
  server.middlewares.use((req, res, next) => {
    const requestPath = req.url?.split('?')[0]
    if (!requestPath) {
      next()
      return
    }

    const rewrittenPath = rewriteUserManualsRequest(requestPath)
    if (!rewrittenPath) {
      next()
      return
    }

    req.url = req.url?.replace(requestPath, rewrittenPath)
    next()
  })
}

const mirrorIconsWithAliases = (srcDir: string, targetDir: string) => {
  if (!fs.existsSync(srcDir)) {
    return
  }

  fs.mkdirSync(targetDir, { recursive: true })
  fs.cpSync(srcDir, targetDir, { recursive: true, force: true })

  for (const entry of fs.readdirSync(targetDir)) {
    if (!entry.endsWith('.svg')) {
      continue
    }

    const aliasMatch = entry.match(/^(.*)-([a-f0-9]{8})\.svg$/)
    if (!aliasMatch) {
      continue
    }

    const aliasFileName = `${aliasMatch[1]}.svg`
    const aliasPath = path.join(targetDir, aliasFileName)
    if (!fs.existsSync(aliasPath)) {
      fs.copyFileSync(path.join(targetDir, entry), aliasPath)
    }
  }
}

const listIconNames = (srcDir: string): string[] => {
  if (!fs.existsSync(srcDir)) {
    return []
  }

  const iconNames = new Set<string>()
  for (const entry of fs.readdirSync(srcDir)) {
    if (!entry.endsWith('.svg')) {
      continue
    }

    const normalizedFileName = entry.replace(/-[a-f0-9]{8}\.svg$/i, '.svg')
    iconNames.add(normalizedFileName.replace(/\.svg$/i, ''))
  }

  return Array.from(iconNames).sort()
}

const writeIconManifest = (srcDir: string, targetFile: string) => {
  fs.mkdirSync(path.dirname(targetFile), { recursive: true })
  fs.writeFileSync(targetFile, JSON.stringify({ icons: listIconNames(srcDir) }, null, 2))
}

const iconSourceDir = resolveIconSourceDir()
if (iconSourceDir) {
  mirrorIconsWithAliases(iconSourceDir, path.resolve('public/assets/icon'))
  mirrorIconsWithAliases(iconSourceDir, path.resolve('public/assets/assets/icon'))
  writeIconManifest(iconSourceDir, path.resolve('public/assets/icon-manifest.json'))
}

export default defineConfig(({ command }) => {
  const devApiProxyTarget = resolveDevApiProxyTarget(command)
  const devOtelProxyTarget = resolveDevOtelProxyTarget(command)

  return {
  plugins: [
    react(),
    {
      name: 'serve-user-manuals-public-path',
      configureServer(server) {
        serveUserManualsPublicPath(server)
      },
      configurePreviewServer(server) {
        serveUserManualsPublicPath(server)
      },
    },
  ],
  root: '.',
  server: {
    host: devServerHost,
    port: devServerPort,
    ...(devServerHttps ? { https: devServerHttps } : {}),
    hmr: {
      protocol: devServerHttps ? 'wss' : 'ws',
      host: publicHmrHost || devServerHost,
      port: devServerPort,
    },
    allowedHosts,
    ...(command === 'serve'
      ? {
          proxy: {
            '/api/system/v1/ui-registry': {
              target: devApiProxyTarget,
              changeOrigin: true,
              secure: false,
            },
            '/api': {
              target: devApiProxyTarget,
              changeOrigin: true,
              secure: false,
              rewrite: (requestPath) => requestPath.replace(/^\/api(?=\/|$)/, '') || '/',
            },
            '/observability/otlp': {
              target: devOtelProxyTarget,
              changeOrigin: true,
              secure: false,
              rewrite: (requestPath) => requestPath.replace(/^\/observability\/otlp(?=\/|$)/, '') || '/',
            }
          }
        }
      : {})
  },
  define: {
    __APP_VERSION__: JSON.stringify(packageJson.version),
    __BUILD_DATE__: JSON.stringify(buildDate)
  }
}})
