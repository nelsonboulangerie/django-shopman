import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('storefront PWA assets', () => {
  it('keeps the iOS share glyph comfortably inside its toolbar highlight', () => {
    const shareStep = readFileSync(resolve('public/pwa/ios-share-step.svg'), 'utf8')

    expect(shareStep).toContain('<circle cx="160" cy="174" r="15"')
    expect(shareStep).toContain('d="M160 175v-8m0 0-4 4m4-4 4 4M156 173h-2v8h12v-8h-2"')
    expect(shareStep).toContain('stroke-width="2"')
    expect(shareStep).not.toContain('r="22"')
  })
})
