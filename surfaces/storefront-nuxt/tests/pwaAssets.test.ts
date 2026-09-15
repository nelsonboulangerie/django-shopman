import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('storefront PWA assets', () => {
  it('uses the same high-contrast instruction grammar in both iOS steps', () => {
    const shareStep = readFileSync(resolve('public/pwa/ios-share-step.svg'), 'utf8')
    const addStep = readFileSync(resolve('public/pwa/ios-add-step.svg'), 'utf8')

    expect(shareStep).toContain('<rect x="52" y="148" width="216" height="48" rx="12" fill="#7c3a40"/>')
    expect(shareStep).toContain('d="M160 176v-20m0 0-8 8m8-8 8 8M149 174v13h22v-13"')
    expect(shareStep).toContain('stroke="#fcf7ee" stroke-width="3.5" stroke-linecap="round"')
    expect(shareStep).not.toContain('<rect x="140"')
    expect(addStep).toContain('<rect x="52" y="100" width="216" height="76" rx="12" fill="#7c3a40"/>')
    expect(addStep).toContain('<rect x="70" y="118" width="40" height="40" rx="9" fill="#fcf7ee"/>')
    expect(shareStep).not.toContain('<circle')
  })
})
