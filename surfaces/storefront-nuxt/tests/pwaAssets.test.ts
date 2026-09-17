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

    // Meio da borda superior: fora do raio do canto, é campo bordô opaco nos três.
    const topEdgeMiddle = (image: typeof regular) => (Math.floor(image.info.width / 2)) * 4

    expect(Array.from(regular.data.subarray(topEdgeMiddle(regular), topEdgeMiddle(regular) + 4))).toEqual([...bordeaux, 255])
    expect(Array.from(maskable.data.subarray(0, 3))).toEqual(bordeaux)
    expect(Array.from(apple.data.subarray(0, 3))).toEqual(bordeaux)
    expect(maskable.data[3]).toBe(255)
    expect(apple.data[3]).toBe(255)
    expect(foregroundPixels(regular.data)).toBeGreaterThan(5_000)
    expect(foregroundPixels(maskable.data)).toBeLessThan(foregroundPixels(regular.data))
  })

  it('rounds only the any-purpose icons: desktop shows them unmasked, Android and iOS mask the rest', async () => {
    // Windows/macOS/Linux desktop exibem o ícone `any` como está; quadrado cheio vira
    // azulejo de quinas vivas. `maskable` (launcher Android) e `apple-touch-icon` (iOS)
    // continuam cheios — o SO recorta, e o iOS pinta de preto o que for transparente.
    for (const size of [64, 192, 512]) {
      const { data } = await sharp(resolve(`public/pwa/pwa-${size}x${size}.png`)).ensureAlpha().raw().toBuffer({ resolveWithObject: true })
      expect(data[3], `pwa-${size}x${size} corner`).toBe(0)
    }
    for (const name of ['maskable-512x512.png', 'apple-touch-icon-180x180.png']) {
      const { data } = await sharp(resolve(`public/pwa/${name}`)).ensureAlpha().raw().toBuffer({ resolveWithObject: true })
      expect(data[3], `${name} corner`).toBe(255)
    }
  })

  it('keeps the installed-icon geometry of the operator family, so the Dock shows both at one size', async () => {
    // O Chrome no macOS gera o ícone do app a partir do `maskable` (recorte na grade do
    // macOS, forma em 412/512) e só cai no `any` de ponta a ponta quando não há
    // `maskable`. A loja estava 512/512 contra 412/512 do PDV no Dock (17/09/2026).
    // O PDV é a referência: mesmo gerador de forma, mesma zona segura.
    const alpha = async (file: string) => {
      const { data, info } = await sharp(resolve(file)).ensureAlpha().raw().toBuffer({ resolveWithObject: true })
      return { alpha: Array.from({ length: info.width * info.height }, (_, pixel) => data[pixel * 4 + 3]), info, data }
    }
    const operatorReference = '../pos-nuxt/public/pwa'
    for (const name of ['pwa-512x512.png', 'maskable-512x512.png', 'apple-touch-icon-180x180.png']) {
      const store = await alpha(`public/pwa/${name}`)
      const operator = await alpha(`${operatorReference}/${name}`)
      expect(store.info.width, name).toBe(operator.info.width)
      const divergent = store.alpha.filter((value, pixel) => Math.abs(value - operator.alpha[pixel]) > 8).length
      expect(divergent, `${name}: pixels de forma diferentes da família de operador`).toBe(0)
    }

    // Todo traço creme do `maskable` cabe no círculo de 40% do lado (zona segura do
    // Android), que também fica dentro do recorte de 80,5% do Mac.
    const { data, info } = await alpha('public/pwa/maskable-512x512.png')
    const center = info.width / 2
    let farthest = 0
    for (let pixel = 0; pixel < info.width * info.height; pixel += 1) {
      const offset = pixel * 4
      if (data[offset] > 240 && data[offset + 1] > 235 && data[offset + 2] > 225) {
        const x = (pixel % info.width) + 0.5 - center
        const y = Math.floor(pixel / info.width) + 0.5 - center
        farthest = Math.max(farthest, Math.hypot(x, y) / info.width)
      }
    }
    expect(farthest).toBeGreaterThan(0.2)
    expect(farthest).toBeLessThanOrEqual(0.4)
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
