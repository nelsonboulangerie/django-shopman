import { describe, expect, it } from 'vitest'
import {
  buildStorefrontManifest,
  STOREFRONT_PWA_FALLBACK
} from '../server/utils/pwaManifest'

describe('storefront PWA manifest', () => {
  it('keeps the install contract and brand fallbacks complete', () => {
    const manifest = buildStorefrontManifest()

    expect(manifest).toMatchObject({
      id: '/',
      name: STOREFRONT_PWA_FALLBACK.brand_name,
      short_name: STOREFRONT_PWA_FALLBACK.short_name,
      lang: 'pt-BR',
      start_url: '/?source=pwa',
      scope: '/',
      display: 'standalone',
      theme_color: '#7C3A40',
      background_color: '#FCF7EE'
    })
    expect(manifest.icons).toEqual(expect.arrayContaining([
      expect.objectContaining({ sizes: '192x192', purpose: 'any' }),
      expect.objectContaining({ sizes: '512x512', purpose: 'any' }),
      expect.objectContaining({ sizes: '512x512', purpose: 'maskable' }),
      expect.objectContaining({ src: '/pwa/monochrome-512x512.png?v=5', purpose: 'monochrome' })
    ]))
    expect(manifest.screenshots).toEqual(expect.arrayContaining([
      expect.objectContaining({ sizes: '1080x1920', form_factor: 'narrow' }),
      expect.objectContaining({ sizes: '1280x720', form_factor: 'wide' })
    ]))
  })

  it('avoids the extra maskable plate on Mac without removing Android adaptive icons', () => {
    const mac = buildStorefrontManifest({}, 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/153.0.0.0 Safari/537.36')
    expect(mac.icons.some(icon => icon.purpose === 'maskable')).toBe(false)
    expect(mac.icons.some(icon => icon.purpose === 'any' && icon.sizes === '512x512')).toBe(true)
    for (const ua of ['Mozilla/5.0 (Linux; Android 15)', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Mobile/15E148']) {
      expect(buildStorefrontManifest({}, ua).icons.some(icon => icon.purpose === 'maskable')).toBe(true)
    }
  })

  it('truncates brand_name to twelve characters when short_name is absent', () => {
    const manifest = buildStorefrontManifest({
      brand_name: 'Boulangerie de Quartier',
      short_name: '   '
    })

    expect(manifest.short_name).toBe('Boulangerie')
    expect(manifest.short_name).toHaveLength(11)
  })

  it('uses the public Shop projection instead of build defaults when present', () => {
    const manifest = buildStorefrontManifest({
      brand_name: 'Casa do Pão',
      short_name: 'Casa',
      description: 'Pães de fermentação natural.',
      theme_color: '#112233',
      background_color: '#F0E0D0'
    })

    expect(manifest).toMatchObject({
      name: 'Casa do Pão',
      short_name: 'Casa',
      description: 'Pães de fermentação natural.',
      theme_color: '#112233',
      background_color: '#F0E0D0'
    })
  })
})
