import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const sourcePath = resolve(process.cwd(), 'src/components/IconGallery.tsx')

describe('IconGallery contract', () => {
  it('uses the app-owned page and input primitives', () => {
    const source = readFileSync(sourcePath, 'utf8')

    expect(source).toContain("import {\n  AppInput,\n  AppIcon,\n  APP_ICON_PROVIDER_LABELS,\n  getAppIconNamesForProvider,\n  AppPageHeader,\n  AppPageShell,\n  type AppIconName,\n} from './app-primitives'")
    expect(source).not.toContain("import { AdminPageHeader } from './AdminPageHeader'")
    expect(source).toContain('<AppPageShell')
    expect(source).toContain('<AppPageHeader')
    expect(source).toContain('<AppInput')
  })
})