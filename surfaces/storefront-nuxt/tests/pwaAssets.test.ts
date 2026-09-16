import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import sharp from 'sharp'
import { describe, expect, it } from 'vitest'

describe('storefront PWA assets', () => {
  it('keeps the approved store symbol centered on a solid bordeaux field', async () => {
    const regular = await sharp(resolve('public/pwa/pwa-512x512.png'))
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true })
    const maskable = await sharp(resolve('public/pwa/maskable-512x512.png'))
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true })
    const apple = await sharp(resolve('public/pwa/apple-touch-icon-180x180.png'))
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true })
    const bordeaux = [109, 31, 50]
    const foregroundPixels = (data: Buffer) => {
      let count = 0
      for (let offset = 0; offset < data.length; offset += 4) {
        if (data[offset] > 240 && data[offset + 1] > 235 && data[offset + 2] > 225) count += 1
      }
      return count
    }

    expect(Array.from(regular.data.subarray(0, 3))).toEqual(bordeaux)
    expect(Array.from(maskable.data.subarray(0, 3))).toEqual(bordeaux)
    expect(Array.from(apple.data.subarray(0, 3))).toEqual(bordeaux)
    expect(regular.data[3]).toBe(255)
    expect(maskable.data[3]).toBe(255)
    expect(apple.data[3]).toBe(255)
    expect(foregroundPixels(regular.data)).toBeGreaterThan(5_000)
    expect(foregroundPixels(maskable.data)).toBeLessThan(foregroundPixels(regular.data))
  })

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
