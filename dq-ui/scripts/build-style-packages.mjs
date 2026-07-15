import fs from 'fs'
import path from 'path'
import { execFileSync } from 'child_process'

const rootDir = path.resolve(new URL('..', import.meta.url).pathname)
const repoRootDir = path.resolve(rootDir, '..')
const sourceDir = path.join(rootDir, 'src', 'style-packages')
const publicDir = path.join(rootDir, 'public', 'style-packages')
const tmpDir = path.join(repoRootDir, 'tmp', 'style-packages')
const manifestFile = path.join(sourceDir, 'style-packages.manifest.json')
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

if (!fs.existsSync(manifestFile)) {
  throw new Error(`Style package manifest not found: ${manifestFile}`)
}

const manifest = JSON.parse(fs.readFileSync(manifestFile, 'utf8'))

if (!manifest || manifest.version !== '1.0.0' || !Array.isArray(manifest.packages)) {
  throw new Error(`Invalid style package manifest: ${manifestFile}`)
}

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

const stylePackages = manifest.packages

for (const entry of stylePackages) {
  if (!entry || typeof entry !== 'object') {
    throw new Error(`Invalid style package manifest entry: ${JSON.stringify(entry)}`)
  }

  switch (entry.kind) {
    case 'copy': {
      if (!entry.source || !entry.output) {
        throw new Error(`Copy package entry requires source and output: ${JSON.stringify(entry)}`)
      }
      const sourceFile = path.join(sourceDir, entry.source)
      const outputFile = path.join(publicDir, entry.output)
      if (!fs.existsSync(sourceFile)) {
        throw new Error(`Style source file not found: ${sourceFile}`)
      }
      fs.copyFileSync(sourceFile, outputFile)
      break
    }
    case 'tailwind': {
      if (!entry.input || !entry.output || !entry.rewriteConfigFrom || !entry.rewriteConfigTo) {
        throw new Error(`Tailwind package entry requires input, output, rewriteConfigFrom, and rewriteConfigTo: ${JSON.stringify(entry)}`)
      }
      ensureAppTailwindBuildEnv()
      const inputFile = path.join(sourceDir, entry.input)
      const outputFile = path.join(publicDir, entry.output)
      if (!fs.existsSync(inputFile)) {
        throw new Error(`Tailwind input stylesheet not found: ${inputFile}`)
      }
      fs.copyFileSync(inputFile, appTailwindBuildSourceFile)
      const appTailwindBuildSourceContent = fs.readFileSync(appTailwindBuildSourceFile, 'utf8')
      const rewrittenAppTailwindBuildSourceContent = appTailwindBuildSourceContent.replace(
        entry.rewriteConfigFrom,
        entry.rewriteConfigTo,
      )

      if (rewrittenAppTailwindBuildSourceContent === appTailwindBuildSourceContent) {
        throw new Error(`Unable to rewrite Tailwind config path in ${appTailwindBuildSourceFile}`)
      }

      fs.writeFileSync(appTailwindBuildSourceFile, rewrittenAppTailwindBuildSourceContent)
      execFileSync(
        path.join(appTailwindBuildEnvDir, 'node_modules', '.bin', 'tailwindcss'),
        ['-c', appTailwindBuildConfigFile, '-i', appTailwindBuildSourceFile, '-o', outputFile, '--minify'],
        {
          cwd: appTailwindBuildEnvDir,
          stdio: 'inherit',
        },
      )
      break
    }
    case 'astrowind': {
      if (!entry.version || !entry.output || !entry.bridge) {
        throw new Error(`AstroWind package entry requires version, output, and bridge: ${JSON.stringify(entry)}`)
      }
      const archiveFile = path.join(vendorCacheDir, `astrowind-v${entry.version}.tar.gz`)
      const extractedRootDir = path.join(vendorCacheDir, `astrowind-${entry.version}`)
      const sourceRootDir = path.join(extractedRootDir, `astrowind-${entry.version}`)
      const upstreamInputFile = path.join(sourceRootDir, 'src', 'assets', 'styles', 'tailwind.css')
      const customStylesFile = path.join(sourceRootDir, 'src', 'components', 'CustomStyles.astro')
      const buildSourceFile = path.join(astroWindBuildEnvDir, 'astrowind.input.css')
      const compiledOutputFile = path.join(astroWindBuildEnvDir, 'astrowind.compiled.css')
      const outputFile = path.join(publicDir, entry.output)
      const bridgeFile = path.join(sourceDir, entry.bridge)

      ensureDownloaded(archiveFile, 'curl', ['-L', '-o', archiveFile, `https://github.com/arthelokyo/astrowind/archive/refs/tags/v${entry.version}.tar.gz`])
      ensureExtracted(archiveFile, extractedRootDir, upstreamInputFile)
      ensureAstroWindBuildEnv()

      fs.copyFileSync(upstreamInputFile, buildSourceFile)
      execFileSync(
        path.join(astroWindBuildEnvDir, 'node_modules', '.bin', 'tailwindcss'),
        ['-i', buildSourceFile, '-o', compiledOutputFile],
        {
          cwd: astroWindBuildEnvDir,
          stdio: 'inherit',
        },
      )

      const astroWindCustomStylesSource = fs.readFileSync(customStylesFile, 'utf8')
      const styleMatch = astroWindCustomStylesSource.match(/<style is:inline>\s*([\s\S]*?)\s*<\/style>/)
      if (!styleMatch) {
        throw new Error(`Unable to locate AstroWind inline style block in: ${customStylesFile}`)
      }

      const astroWindCustomStyles = styleMatch[1]
        .replace(/(^|\n)\s*:root\s*\{/g, "$1:root[data-style-package='astrowind'] {")
        .replace(/(^|\n)\s*\.dark\s*\{/g, "$1:root[data-style-package='astrowind'].dark {")
        .trim()
      const astroWindCompiledStyles = fs.readFileSync(compiledOutputFile, 'utf8').trim()
      const astroWindBridgeCSS = fs.readFileSync(bridgeFile, 'utf8')
      fs.writeFileSync(outputFile, `${astroWindCustomStyles}\n${astroWindCompiledStyles}\n${astroWindBridgeCSS}`)
      break
    }
    case 'carbon': {
      if (!entry.packageName || !entry.version || !entry.output || !entry.bridge) {
        throw new Error(`Carbon package entry requires packageName, version, output, and bridge: ${JSON.stringify(entry)}`)
      }
      const archiveFile = path.join(vendorCacheDir, `carbon-styles-${entry.version}.tgz`)
      const extractedRootDir = path.join(vendorCacheDir, `carbon-styles-${entry.version}`)
      const sourceFile = path.join(extractedRootDir, 'package', 'css', 'styles.css')
      const outputFile = path.join(publicDir, entry.output)
      const bridgeFile = path.join(sourceDir, entry.bridge)

      ensureDownloaded(archiveFile, 'npm', ['pack', `${entry.packageName}@${entry.version}`, '--pack-destination', vendorCacheDir])
      ensureExtracted(archiveFile, extractedRootDir, sourceFile)
      const carbonCSS = fs.readFileSync(sourceFile, 'utf8').trimEnd()
      const bridgeCSS = fs.readFileSync(bridgeFile, 'utf8')
      fs.writeFileSync(outputFile, `${carbonCSS}
${bridgeCSS}`)
      break
    }
    default:
      throw new Error(`Unsupported style package kind: ${entry.kind}`)
  }
}
fs.copyFileSync(customBuiltSourceFile, customBuiltOutputFile)