import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const sourcePath = resolve(process.cwd(), 'src/components/TemplateAttributeCatalogPickerModal.tsx')

describe('TemplateAttributeCatalogPickerModal contract', () => {
  it('uses the shared modal shell and button primitives', () => {
    const source = readFileSync(sourcePath, 'utf8')

    expect(source).toContain("import { AppButton, AppModal, AppStack } from './app-primitives'")
    expect(source).not.toContain("import { ModalShell } from './ModalShell'")
    expect(source).not.toContain("import { Button } from './Button'")
    expect(source).toContain('<AppModal')
    expect(source).toContain('<AppButton')
    expect(source).toContain('<AppStack')
  })
})
