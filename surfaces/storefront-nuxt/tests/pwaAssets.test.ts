import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import sharp from 'sharp'
import { describe, expect, it } from 'vitest'

describe('storefront PWA assets', () => {
  it('keeps any-purpose icons transparent and background icons full-bleed', async () => {
    const transparentSource = readFileSync(resolve('brand/nelson-mark.svg'), 'utf8')
    const backgroundSource = readFileSync(resolve('brand/nelson-mark-bg.svg'), 'utf8')
    const transparent = await sharp(resolve('public/pwa/pwa-512x512.png'))
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
    const topLeftRgb = Array.from(maskable.data.subarray(0, 3))
    const topRightOffset = (maskable.info.width - 1) * 4
    const topRightRgb = Array.from(maskable.data.subarray(topRightOffset, topRightOffset + 3))

    expect(transparentSource).toContain('fill: #ffcd40;')
    expect(transparentSource).toContain('fill: #aa6a2b;')
    expect(backgroundSource).toContain('linearGradient')
    expect(backgroundSource).toContain('stop-color="#cca135"')
    expect(backgroundSource).toContain('stop-color="#ffcd40"')
    expect(transparent.data[3]).toBe(0)
    expect(maskable.data[3]).toBe(255)
    expect(apple.data[3]).toBe(255)
    expect(topLeftRgb).not.toEqual(topRightRgb)
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
