import fs from 'fs'
import path from 'path'
import { execFileSync } from 'child_process'

const rootDir = path.resolve(new URL('..', import.meta.url).pathname)
const repoRootDir = path.resolve(rootDir, '..')
const sourceDir = path.join(rootDir, 'src', 'style-packages')
const publicDir = path.join(rootDir, 'public', 'style-packages')
const tmpDir = path.join(repoRootDir, 'tmp', 'style-packages')
const vendorCacheDir = path.join(tmpDir, 'vendor-cache')
const appTailwindBuildEnvDir = path.join(tmpDir, 'tailwind-build-env')
const astroWindBuildEnvDir = path.join(tmpDir, 'astrowind-build-env')
const tailwindInputFile = path.join(sourceDir, 'tailwind.input.css')
const tailwindOutputFile = path.join(publicDir, 'tailwind.css')
const appTailwindBuildPackageFile = path.join(appTailwindBuildEnvDir, 'package.json')
const appTailwindBuildConfigFile = path.join(appTailwindBuildEnvDir, 'tailwind.config.cjs')
const appTailwindBuildSourceFile = path.join(appTailwindBuildEnvDir, 'tailwind.input.css')
const astroWindOutputFile = path.join(publicDir, 'astrowind.css')
const dataWebOutputFile = path.join(publicDir, 'data-web.css')
const customBuiltSourceFile = path.join(sourceDir, 'custom-built-package.css')
const customBuiltOutputFile = path.join(publicDir, 'custom-built-package.css')
const dataWebBridgeFile = path.join(sourceDir, 'data-web.bridge.css')
const astroWindBridgeFile = path.join(sourceDir, 'astrowind.bridge.css')
const tailwindConfigFile = path.join(rootDir, 'tailwind.config.cjs')

const astroWindVersion = '1.0.0-beta.60'
const astroWindTarballUrl = `https://github.com/arthelokyo/astrowind/archive/refs/tags/v${astroWindVersion}.tar.gz`
const astroWindArchiveFile = path.join(vendorCacheDir, `astrowind-v${astroWindVersion}.tar.gz`)
const astroWindExtractedRootDir = path.join(vendorCacheDir, `astrowind-${astroWindVersion}`)
const astroWindSourceRootDir = path.join(astroWindExtractedRootDir, `astrowind-${astroWindVersion}`)
const astroWindUpstreamInputFile = path.join(astroWindSourceRootDir, 'src', 'assets', 'styles', 'tailwind.css')
const astroWindCustomStylesFile = path.join(astroWindSourceRootDir, 'src', 'components', 'CustomStyles.astro')
const astroWindBuildSourceFile = path.join(astroWindBuildEnvDir, 'astrowind.input.css')
const astroWindCompiledOutputFile = path.join(astroWindBuildEnvDir, 'astrowind.compiled.css')
const astroWindBuildPackageFile = path.join(astroWindBuildEnvDir, 'package.json')

const dataWebVersion = '1.107.0'
const dataWebArchiveFile = path.join(vendorCacheDir, `carbon-styles-${dataWebVersion}.tgz`)
const dataWebExtractedRootDir = path.join(vendorCacheDir, `carbon-styles-${dataWebVersion}`)
const dataWebSourceFile = path.join(dataWebExtractedRootDir, 'package', 'css', 'styles.css')

fs.mkdirSync(publicDir, { recursive: true })
fs.mkdirSync(tmpDir, { recursive: true })
fs.mkdirSync(vendorCacheDir, { recursive: true })
fs.mkdirSync(appTailwindBuildEnvDir, { recursive: true })
fs.mkdirSync(astroWindBuildEnvDir, { recursive: true })

if (!fs.existsSync(tailwindInputFile)) {
  throw new Error(`Tailwind input stylesheet not found: ${tailwindInputFile}`)
}

if (!fs.existsSync(customBuiltSourceFile)) {
  throw new Error(`Custom built package stylesheet not found: ${customBuiltSourceFile}`)
}

const writeJsonIfChanged = (filePath, value) => {
  const nextContent = `${JSON.stringify(value, null, 2)}\n`
  const currentContent = fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : null
  if (currentContent !== nextContent) {
    fs.writeFileSync(filePath, nextContent)
    return true
  }

  return false
}

const writeTextIfChanged = (filePath, value) => {
  const currentContent = fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : null
  if (currentContent !== value) {
    fs.writeFileSync(filePath, value)
    return true
  }

  return false
}

const ensureDownloaded = (destinationFile, command, args) => {
  if (fs.existsSync(destinationFile)) {
    return
  }

  execFileSync(command, args, { stdio: 'inherit' })
}

const ensureExtracted = (archiveFile, extractedDir, extractedCheckFile) => {
  if (fs.existsSync(extractedCheckFile)) {
    return
  }

  fs.rmSync(extractedDir, { recursive: true, force: true })
  fs.mkdirSync(extractedDir, { recursive: true })
  execFileSync('tar', ['-xzf', archiveFile, '-C', extractedDir], { stdio: 'inherit' })
}

const installedPackageVersion = (buildEnvDir, packageName) => {
  const packageJsonFile = path.join(buildEnvDir, 'node_modules', packageName, 'package.json')
  if (!fs.existsSync(packageJsonFile)) {
    return null
  }

  try {
    const packageJson = JSON.parse(fs.readFileSync(packageJsonFile, 'utf8'))
    return typeof packageJson.version === 'string' ? packageJson.version : null
  } catch {
    return null
  }
}

const ensureInstalledPackageVersion = (buildEnvDir, packageName, expectedVersion) => {
  return installedPackageVersion(buildEnvDir, packageName) === expectedVersion
}

const ensureAstroWindBuildEnv = () => {
  const packageChanged = writeJsonIfChanged(astroWindBuildPackageFile, {
    name: 'astrowind-build-env',
    private: true,
    dependencies: {
      '@tailwindcss/cli': '4.3.0',
      '@tailwindcss/typography': '0.5.19',
      tailwindcss: '4.3.0',
    },
  })

  if (packageChanged) {
    fs.rmSync(path.join(astroWindBuildEnvDir, 'node_modules'), { recursive: true, force: true })
    fs.rmSync(path.join(astroWindBuildEnvDir, 'package-lock.json'), { force: true })
  }

  if (
    !ensureInstalledPackageVersion(astroWindBuildEnvDir, 'tailwindcss', '4.3.0') ||
    !ensureInstalledPackageVersion(astroWindBuildEnvDir, '@tailwindcss/cli', '4.3.0')
  ) {
    fs.rmSync(path.join(astroWindBuildEnvDir, 'node_modules'), { recursive: true, force: true })
    fs.rmSync(path.join(astroWindBuildEnvDir, 'package-lock.json'), { force: true })
    execFileSync('npm', ['install'], {
      cwd: astroWindBuildEnvDir,
      stdio: 'inherit',
    })
  }
}

const ensureAppTailwindBuildEnv = () => {
  const packageChanged = writeJsonIfChanged(appTailwindBuildPackageFile, {
    name: 'tailwind-build-env',
    private: true,
    dependencies: {
      '@tailwindcss/cli': '4.3.0',
      tailwindcss: '4.3.0',
    },
  })

  if (packageChanged) {
    fs.rmSync(path.join(appTailwindBuildEnvDir, 'node_modules'), { recursive: true, force: true })
    fs.rmSync(path.join(appTailwindBuildEnvDir, 'package-lock.json'), { force: true })
  }

  if (
    !ensureInstalledPackageVersion(appTailwindBuildEnvDir, 'tailwindcss', '4.3.0') ||
    !ensureInstalledPackageVersion(appTailwindBuildEnvDir, '@tailwindcss/cli', '4.3.0')
  ) {
    fs.rmSync(path.join(appTailwindBuildEnvDir, 'node_modules'), { recursive: true, force: true })
    fs.rmSync(path.join(appTailwindBuildEnvDir, 'package-lock.json'), { force: true })
    execFileSync('npm', ['install'], {
      cwd: appTailwindBuildEnvDir,
      stdio: 'inherit',
    })
  }

  writeTextIfChanged(
    appTailwindBuildConfigFile,
    `const path = require('node:path')

const rootDir = ${JSON.stringify(rootDir)}

module.exports = {
  content: [
    path.join(rootDir, 'index.html'),
    path.join(rootDir, 'src/**/*.{ts,tsx,js,jsx,html}'),
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
`,
  )
}

const extractAstroWindCustomStyles = () => {
  const astroWindCustomStylesSource = fs.readFileSync(astroWindCustomStylesFile, 'utf8')
  const styleMatch = astroWindCustomStylesSource.match(/<style is:inline>\s*([\s\S]*?)\s*<\/style>/)

  if (!styleMatch) {
    throw new Error(`Unable to locate AstroWind inline style block in: ${astroWindCustomStylesFile}`)
  }

  return styleMatch[1]
    .replace(/(^|\n)\s*:root\s*\{/g, "$1:root[data-style-package='astrowind'] {")
    .replace(/(^|\n)\s*\.dark\s*\{/g, "$1:root[data-style-package='astrowind'].dark {")
    .trim()
}

const buildAstroWindStylesheet = () => {
  ensureDownloaded(astroWindArchiveFile, 'curl', ['-L', '-o', astroWindArchiveFile, astroWindTarballUrl])
  ensureExtracted(astroWindArchiveFile, astroWindExtractedRootDir, astroWindUpstreamInputFile)
  ensureAstroWindBuildEnv()

  fs.copyFileSync(astroWindUpstreamInputFile, astroWindBuildSourceFile)
  execFileSync(
    path.join(astroWindBuildEnvDir, 'node_modules', '.bin', 'tailwindcss'),
    ['-i', astroWindBuildSourceFile, '-o', astroWindCompiledOutputFile],
    {
      cwd: astroWindBuildEnvDir,
      stdio: 'inherit',
    },
  )

  const astroWindCustomStyles = extractAstroWindCustomStyles()
  const astroWindCompiledStyles = fs.readFileSync(astroWindCompiledOutputFile, 'utf8').trim()
  const astroWindBridgeCSS = fs.readFileSync(astroWindBridgeFile, 'utf8')

  fs.writeFileSync(astroWindOutputFile, `${astroWindCustomStyles}\n${astroWindCompiledStyles}\n${astroWindBridgeCSS}`)
}

const buildDataWebStylesheet = () => {
  ensureDownloaded(dataWebArchiveFile, 'npm', ['pack', `@carbon/styles@${dataWebVersion}`, '--pack-destination', vendorCacheDir])
  ensureExtracted(dataWebArchiveFile, dataWebExtractedRootDir, dataWebSourceFile)
  const carbonCSS = fs.readFileSync(dataWebSourceFile, 'utf8').trimEnd()
  const bridgeCSS = fs.readFileSync(dataWebBridgeFile, 'utf8')
  fs.writeFileSync(dataWebOutputFile, `${carbonCSS}
${bridgeCSS}`)
}

ensureAppTailwindBuildEnv()
fs.copyFileSync(
  tailwindInputFile,
  appTailwindBuildSourceFile,
)
const appTailwindBuildSourceContent = fs.readFileSync(appTailwindBuildSourceFile, 'utf8')
const rewrittenAppTailwindBuildSourceContent = appTailwindBuildSourceContent.replace(
  "@config '../../tailwind.config.cjs';",
  "@config './tailwind.config.cjs';",
)

if (rewrittenAppTailwindBuildSourceContent === appTailwindBuildSourceContent) {
  throw new Error(`Unable to rewrite Tailwind config path in ${appTailwindBuildSourceFile}`)
}

fs.writeFileSync(appTailwindBuildSourceFile, rewrittenAppTailwindBuildSourceContent)
execFileSync(
  path.join(appTailwindBuildEnvDir, 'node_modules', '.bin', 'tailwindcss'),
  ['-c', appTailwindBuildConfigFile, '-i', appTailwindBuildSourceFile, '-o', tailwindOutputFile, '--minify'],
  {
    cwd: appTailwindBuildEnvDir,
    stdio: 'inherit',
  },
)

buildAstroWindStylesheet()
buildDataWebStylesheet()
fs.copyFileSync(customBuiltSourceFile, customBuiltOutputFile)