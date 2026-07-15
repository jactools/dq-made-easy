import fs from 'fs'
import path from 'path'
import { execFileSync } from 'child_process'
import { fileURLToPath } from 'url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const sourceDir = path.join(rootDir, 'src', 'style-packages')
const tailwindConfigFile = path.join(rootDir, 'tailwind.config.cjs')
const manifestFile = path.join(sourceDir, 'style-packages.manifest.json')
const buildScriptFile = path.join(rootDir, 'scripts', 'build-style-packages.mjs')

const watchedPaths = [sourceDir, tailwindConfigFile, manifestFile]
let rebuildScheduled = false
let rebuildInFlight = false

const runBuild = () => {
  execFileSync('node', [buildScriptFile], { stdio: 'inherit' })
}

const scheduleRebuild = () => {
  if (rebuildScheduled) {
    return
  }

  rebuildScheduled = true
  setTimeout(() => {
    rebuildScheduled = false
    if (rebuildInFlight) {
      return
    }

    rebuildInFlight = true
    try {
      runBuild()
    } finally {
      rebuildInFlight = false
    }
  }, 150)
}

for (const watchedPath of watchedPaths) {
  if (!fs.existsSync(watchedPath)) {
    throw new Error(`Watch target not found: ${watchedPath}`)
  }
}

runBuild()

const sourceWatcher = fs.watch(sourceDir, { recursive: true }, (_eventType, filename) => {
  if (!filename) {
    scheduleRebuild()
    return
  }

  if (
    filename.endsWith('tailwind.input.css') ||
    filename.endsWith('style-packages.manifest.json') ||
    filename.endsWith('custom-built-package.css')
  ) {
    scheduleRebuild()
  }
})

const configWatcher = fs.watch(tailwindConfigFile, scheduleRebuild)

const shutdown = () => {
  sourceWatcher.close()
  configWatcher.close()
}

process.on('SIGINT', () => {
  shutdown()
  process.exit(0)
})

process.on('SIGTERM', () => {
  shutdown()
  process.exit(0)
})

console.log('Watching style-package sources for changes...')