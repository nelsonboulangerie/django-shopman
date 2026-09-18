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
      expect.objectContaining({ src: '/pwa/monochrome-512x512.png?v=6', purpose: 'monochrome' })
    ]))
    expect(manifest.screenshots).toEqual(expect.arrayContaining([
      expect.objectContaining({ sizes: '1080x1920', form_factor: 'narrow' }),
      expect.objectContaining({ sizes: '1280x720', form_factor: 'wide' })
    ]))
  })

  it('publishes the maskable icon, which Chrome on macOS insets on the platform grid', () => {
    // Sem `maskable`, o Chrome no Mac usa o `any` de ponta a ponta (512/512) e o app
    // fica ~24% maior que os vizinhos no Dock; com ele, recorta na grade do macOS
    // (412/512). A família de operador publica os dois; a loja também.
    const { icons } = buildStorefrontManifest()
    expect(icons).toEqual(expect.arrayContaining([
      { src: '/pwa/pwa-512x512.png?v=6', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/pwa/maskable-512x512.png?v=6', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
    ]))
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
