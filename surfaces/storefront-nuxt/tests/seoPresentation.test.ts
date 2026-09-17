import { describe, expect, it } from 'vitest'
import type { ProductDetailProjection, ShopProjection, SiteBusinessProjection } from '~/types/shopman'
import {
  absoluteImage,
  absoluteUrl,
  availabilitySchemaUrl,
  bakeryJsonLd,
  breadcrumbJsonLd,
  collectionJsonLd,
  faqJsonLd,
  jsonLdText,
  listingDescription,
  localBusinessJsonLd,
  metaDescription,
  normalizeSite,
  priceFromQ,
  productCollectionCrumb,
  productJsonLd,
  sitePageSeo,
  siteVerificationMeta,
  truncateClean,
  websiteJsonLd
} from '~/presentation/seo'

const ORIGIN = 'https://loja.exemplo.com'

function product (overrides: Partial<ProductDetailProjection> = {}): ProductDetailProjection {
  return {
    sku: 'CROIS-01',
    name: 'Croissant de Manteiga',
    short_description: 'Folhado, amanteigado, assado na hora.',
    seo_description: 'Croissant artesanal francês, folhado em camadas, assado fresco todo dia.',
    seo_keywords: ['croissant', 'padaria francesa', 'café da manhã'],
    image_url: '/media/produtos/croissant.jpg',
    base_price_q: 1290,
    price_display: 'R$ 12,90',
    availability: 'available',
    availability_label: 'Disponível',
    ...overrides
  } as unknown as ProductDetailProjection
}

function shop (overrides: Partial<ShopProjection> = {}): ShopProjection {
  return {
    brand_name: 'Nelson Boulangerie',
    description: 'Padaria artesanal francesa em Londrina.',
    logo_url: '/static/logo.png',
    phone: '+554333231997',
    email: 'nelson@boulangerie.com.br',
    full_address: 'Av. Madre Leônia Milito, 446 - Bela Suíça',
    default_city: 'Londrina',
    social_links: [{ url: 'https://instagram.com/nelson', platform: 'instagram', label: 'Instagram', icon_svg: '' }],
    ...overrides
  } as unknown as ShopProjection
}

describe('absoluteUrl', () => {
  it('junta origin + path', () => {
    expect(absoluteUrl(ORIGIN, '/produto/x')).toBe('https://loja.exemplo.com/produto/x')
    expect(absoluteUrl(ORIGIN + '/', 'produto/x')).toBe('https://loja.exemplo.com/produto/x')
  })
  it('preserva URL já absoluta', () => {
    expect(absoluteUrl(ORIGIN, 'https://cdn.x/y.jpg')).toBe('https://cdn.x/y.jpg')
  })
})

describe('absoluteImage', () => {
  it('resolve relativa contra origin', () => {
    expect(absoluteImage(ORIGIN, '/media/a.jpg')).toBe('https://loja.exemplo.com/media/a.jpg')
  })
  it('null quando vazio', () => {
    expect(absoluteImage(ORIGIN, null)).toBeNull()
    expect(absoluteImage(ORIGIN, '')).toBeNull()
  })
})

describe('priceFromQ', () => {
  it('centavos → reais com 2 casas', () => {
    expect(priceFromQ(1290)).toBe('12.90')
    expect(priceFromQ(0)).toBe('0.00')
    expect(priceFromQ(null)).toBe('0.00')
  })
})

describe('availabilitySchemaUrl', () => {
  it('mapeia disponibilidade para schema.org', () => {
    expect(availabilitySchemaUrl('available')).toBe('https://schema.org/InStock')
    expect(availabilitySchemaUrl('low_stock')).toBe('https://schema.org/InStock')
    expect(availabilitySchemaUrl('planned_ok')).toBe('https://schema.org/PreOrder')
    expect(availabilitySchemaUrl('unavailable')).toBe('https://schema.org/OutOfStock')
    expect(availabilitySchemaUrl(undefined)).toBe('https://schema.org/OutOfStock')
  })
})

describe('truncateClean', () => {
  it('mantém texto curto', () => {
    expect(truncateClean('curto', 160)).toBe('curto')
  })
  it('corta sem quebrar palavra', () => {
    const out = truncateClean('palavra '.repeat(40), 50)
    expect(out.length).toBeLessThanOrEqual(51)
    expect(out.endsWith('…')).toBe(true)
    expect(out).not.toContain('palavr…')
  })
})

describe('metaDescription', () => {
  it('prioriza seo_description', () => {
    expect(metaDescription(product())).toContain('Croissant artesanal')
  })
  it('cai para short_description', () => {
    expect(metaDescription(product({ seo_description: '' }))).toContain('Folhado')
  })
  it('vazio sem produto', () => {
    expect(metaDescription(null)).toBe('')
  })
})

describe('productJsonLd', () => {
  it('monta Product + Offer com dados do backend', () => {
    const url = 'https://loja.exemplo.com/produto/CROIS-01'
    const ld = productJsonLd({ product: product(), origin: ORIGIN, url, brandName: 'Nelson Boulangerie' })
    expect(ld['@type']).toBe('Product')
    expect(ld.name).toBe('Croissant de Manteiga')
    expect(ld.sku).toBe('CROIS-01')
    expect(ld.image).toBe('https://loja.exemplo.com/media/produtos/croissant.jpg')
    expect(ld.brand).toEqual({ '@type': 'Brand', name: 'Nelson Boulangerie' })
    expect(ld.keywords).toBe('croissant, padaria francesa, café da manhã')
    const offer = ld.offers as Record<string, unknown>
    expect(offer.price).toBe('12.90')
    expect(offer.priceCurrency).toBe('BRL')
    expect(offer.availability).toBe('https://schema.org/InStock')
    expect(offer.url).toBe(url)
  })
  it('omite imagem/brand quando ausentes', () => {
    const ld = productJsonLd({ product: product({ image_url: null }), origin: ORIGIN, url: 'x', brandName: '' })
    expect(ld.image).toBeUndefined()
    expect(ld.brand).toBeUndefined()
  })
})

describe('breadcrumbJsonLd', () => {
  it('numera as posições a partir de 1', () => {
    const ld = breadcrumbJsonLd([
      { name: 'Início', url: 'https://x/' },
      { name: 'Cardápio', url: 'https://x/menu' },
      { name: 'Croissant', url: 'https://x/produto/CROIS-01' }
    ])
    expect(ld['@type']).toBe('BreadcrumbList')
    const items = ld.itemListElement as Array<Record<string, unknown>>
    expect(items).toHaveLength(3)
    expect(items[0]!.position).toBe(1)
    expect(items[2]!.position).toBe(3)
    expect(items[2]!.name).toBe('Croissant')
    expect(items[2]!.item).toBe('https://x/produto/CROIS-01')
  })
})

describe('collectionJsonLd', () => {
  const items = [
    { sku: 'CROIS-01', name: 'Croissant', base_price_q: 1290, availability: 'available' as const, image_url: '/media/c.jpg' },
    { sku: 'BAGUE-01', name: 'Baguete', base_price_q: 1300, availability: 'unavailable' as const, image_url: null }
  ]
  it('monta CollectionPage com ItemList de produtos', () => {
    const ld = collectionJsonLd({ name: 'Cardápio', url: ORIGIN + '/menu', origin: ORIGIN, items })
    expect(ld['@type']).toBe('CollectionPage')
    expect(ld.url).toBe('https://loja.exemplo.com/menu')
    const list = ld.mainEntity as Record<string, unknown>
    expect(list['@type']).toBe('ItemList')
    expect(list.numberOfItems).toBe(2)
    const elements = list.itemListElement as Array<Record<string, unknown>>
    expect(elements[0]!.position).toBe(1)
    const first = elements[0]!.item as Record<string, unknown>
    expect(first['@type']).toBe('Product')
    expect(first.url).toBe('https://loja.exemplo.com/produto/CROIS-01')
    expect(first.image).toBe('https://loja.exemplo.com/media/c.jpg')
    expect((first.offers as Record<string, unknown>).price).toBe('12.90')
  })
  it('omite imagem quando ausente', () => {
    const ld = collectionJsonLd({ name: 'Cardápio', url: ORIGIN + '/menu', origin: ORIGIN, items })
    const elements = (ld.mainEntity as Record<string, unknown>).itemListElement as Array<Record<string, unknown>>
    const second = elements[1]!.item as Record<string, unknown>
    expect(second.image).toBeUndefined()
    expect((second.offers as Record<string, unknown>).availability).toBe('https://schema.org/OutOfStock')
  })
})

describe('bakeryJsonLd', () => {
  it('monta Bakery com endereço, geo e sameAs', () => {
    const ld = bakeryJsonLd({
      shop: shop(), origin: ORIGIN, url: ORIGIN + '/', latitude: -23.31, longitude: -51.16
    })
    expect(ld['@type']).toBe('Bakery')
    expect(ld.name).toBe('Nelson Boulangerie')
    expect(ld.telephone).toBe('+554333231997')
    expect(ld.image).toBe('https://loja.exemplo.com/static/logo.png')
    expect((ld.address as Record<string, unknown>).addressLocality).toBe('Londrina')
    expect((ld.geo as Record<string, unknown>).latitude).toBe(-23.31)
    expect(ld.sameAs).toEqual(['https://instagram.com/nelson'])
  })
  it('omite geo quando faltam coordenadas', () => {
    const ld = bakeryJsonLd({ shop: shop(), origin: ORIGIN, url: ORIGIN, latitude: null, longitude: null })
    expect(ld.geo).toBeUndefined()
  })
})

describe('faqJsonLd', () => {
  it('publica as mesmas perguntas e respostas servidas pela projeção', () => {
    const ld = faqJsonLd([
      {
        ref: 'delivery',
        question: 'Vocês fazem entrega?',
        answer: 'Sim. Fazemos entrega.'
      }
    ])
    expect(ld['@type']).toBe('FAQPage')
    expect(ld.mainEntity).toEqual([
      {
        '@type': 'Question',
        name: 'Vocês fazem entrega?',
        acceptedAnswer: {
          '@type': 'Answer',
          text: 'Sim. Fazemos entrega.'
        }
      }
    ])
  })
})

// ── Identidade pública do site ───────────────────────────────────────────────

const FULL_SITE = {
  pages: {
    home: { title: 'Nelson Boulangerie · Padaria artesanal em Londrina', description: 'Pães de fermentação natural.' },
    menu: { title: 'Cardápio', description: 'O cardápio do dia.' },
    faq: { title: 'Perguntas frequentes', description: 'Entrega, encomenda e horário.' }
  },
  share_image_url: 'https://cdn.exemplo.com/share.jpg',
  verifications: { google: 'g-123', bing: '', facebook: 'fb-456', pinterest: '' },
  business: {
    type: 'Bakery',
    name: 'Nelson Boulangerie',
    legal_name: 'Nelson Boulangerie Ltda',
    description: 'Padaria artesanal em Londrina.',
    url: '',
    telephone: '+55 43 3323-1997',
    email: 'nelson@boulangerie.com.br',
    logo_url: '/static/logo.png',
    price_range: '$$',
    founding_year: 1997,
    address: {
      street: 'Av. Madre Leônia Milito, 446',
      neighborhood: 'Bela Suíça',
      locality: 'Londrina',
      region: 'PR',
      postal_code: '86050-270',
      country_code: 'BR'
    },
    geo: { latitude: -23.3348, longitude: -51.1673 },
    opening_hours: [
      { days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'], opens: '09:00', closes: '18:00' },
      { days: ['Sunday'], opens: '08:00', closes: '12:00' }
    ],
    maps_url: 'https://g.page/nelsonboulangerie',
    same_as: ['https://www.instagram.com/nelsonboulangerie', 'https://www.facebook.com/nelsonboulangerie']
  },
  faq: [{ ref: 'delivery', question: 'Vocês entregam?', answer: 'Sim.' }]
}

function sparseBusiness (overrides: Partial<SiteBusinessProjection> = {}): SiteBusinessProjection {
  return { ...normalizeSite({ business: { name: 'Nelson Boulangerie' } })!.business, ...overrides }
}

// Caminhos de toda chave vazia ('' / null / [] / {}) — JSON-LD não carrega nenhuma.
function emptyKeys (value: unknown, path = '$'): string[] {
  if (Array.isArray(value)) {
    return value.length ? value.flatMap((entry, index) => emptyKeys(entry, `${path}[${index}]`)) : [path]
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value)
    if (!entries.length) return [path]
    return entries.flatMap(([key, entry]) => emptyKeys(entry, `${path}.${key}`))
  }
  return value === '' || value === null || value === undefined ? [path] : []
}

describe('normalizeSite', () => {
  it('devolve null quando o endpoint não mandou objeto', () => {
    expect(normalizeSite(null)).toBeNull()
    expect(normalizeSite(undefined)).toBeNull()
    expect(normalizeSite('erro')).toBeNull()
    expect(normalizeSite([])).toBeNull()
  })

  it('preenche o que faltou com vazio, nunca com undefined', () => {
    const site = normalizeSite({ business: { name: '  Nelson  ', geo: { latitude: 'x', longitude: 1 }, founding_year: 0 } })!
    expect(site.pages.home).toEqual({ title: '', description: '' })
    expect(site.verifications).toEqual({ google: '', bing: '', facebook: '', pinterest: '' })
    expect(site.business.name).toBe('Nelson')
    expect(site.business.geo).toBeNull()
    expect(site.business.founding_year).toBeNull()
    expect(site.business.opening_hours).toEqual([])
    expect(site.business.same_as).toEqual([])
    expect(site.faq).toEqual([])
  })

  it('descarta pergunta sem resposta', () => {
    const site = normalizeSite({ faq: [{ ref: 'a', question: 'P?', answer: '' }, { ref: 'b', question: 'Q?', answer: 'R.' }] })!
    expect(site.faq).toEqual([{ ref: 'b', question: 'Q?', answer: 'R.' }])
  })
})

describe('sitePageSeo', () => {
  it('lê título e descrição da página', () => {
    expect(sitePageSeo(normalizeSite(FULL_SITE), 'menu')).toEqual({ title: 'Cardápio', description: 'O cardápio do dia.' })
  })
  it('vazio sem site — a página cai no próprio padrão', () => {
    expect(sitePageSeo(null, 'home')).toEqual({ title: '', description: '' })
  })
})

describe('siteVerificationMeta', () => {
  it('emite só as verificações preenchidas, com o nome que cada serviço lê', () => {
    expect(siteVerificationMeta(normalizeSite(FULL_SITE)!.verifications)).toEqual([
      { name: 'google-site-verification', content: 'g-123' },
      { name: 'facebook-domain-verification', content: 'fb-456' }
    ])
  })
  it('conhece Bing e Pinterest', () => {
    expect(siteVerificationMeta({ bing: 'b', pinterest: 'p' })).toEqual([
      { name: 'msvalidate.01', content: 'b' },
      { name: 'p:domain_verify', content: 'p' }
    ])
  })
  it('nada quando não há verificação', () => {
    expect(siteVerificationMeta(null)).toEqual([])
    expect(siteVerificationMeta({ google: '  ' })).toEqual([])
  })
})

describe('localBusinessJsonLd', () => {
  it('monta o LocalBusiness completo a partir do cadastro', () => {
    const ld = localBusinessJsonLd({
      business: normalizeSite(FULL_SITE)!.business,
      origin: ORIGIN,
      images: ['https://cdn.exemplo.com/share.jpg', '/media/pao.jpg']
    })
    expect(ld).toEqual({
      '@context': 'https://schema.org',
      '@type': 'Bakery',
      '@id': 'https://loja.exemplo.com/#business',
      url: 'https://loja.exemplo.com/',
      name: 'Nelson Boulangerie',
      legalName: 'Nelson Boulangerie Ltda',
      description: 'Padaria artesanal em Londrina.',
      telephone: '+55 43 3323-1997',
      email: 'nelson@boulangerie.com.br',
      image: [
        'https://cdn.exemplo.com/share.jpg',
        'https://loja.exemplo.com/media/pao.jpg',
        'https://loja.exemplo.com/static/logo.png'
      ],
      logo: 'https://loja.exemplo.com/static/logo.png',
      priceRange: '$$',
      foundingDate: '1997',
      address: {
        '@type': 'PostalAddress',
        streetAddress: 'Av. Madre Leônia Milito, 446 - Bela Suíça',
        addressLocality: 'Londrina',
        addressRegion: 'PR',
        postalCode: '86050-270',
        addressCountry: 'BR'
      },
      geo: { '@type': 'GeoCoordinates', latitude: -23.3348, longitude: -51.1673 },
      openingHoursSpecification: [
        {
          '@type': 'OpeningHoursSpecification',
          dayOfWeek: [
            'https://schema.org/Monday',
            'https://schema.org/Tuesday',
            'https://schema.org/Wednesday',
            'https://schema.org/Thursday',
            'https://schema.org/Friday',
            'https://schema.org/Saturday'
          ],
          opens: '09:00',
          closes: '18:00'
        },
        {
          '@type': 'OpeningHoursSpecification',
          dayOfWeek: ['https://schema.org/Sunday'],
          opens: '08:00',
          closes: '12:00'
        }
      ],
      hasMap: 'https://g.page/nelsonboulangerie',
      sameAs: ['https://www.instagram.com/nelsonboulangerie', 'https://www.facebook.com/nelsonboulangerie'],
      hasMenu: 'https://loja.exemplo.com/menu'
    })
    expect(emptyKeys(ld)).toEqual([])
  })

  it('com cadastro esparso, omite tudo o que não sabe — nenhuma chave vazia', () => {
    const ld = localBusinessJsonLd({ business: sparseBusiness(), origin: ORIGIN, images: [null, ''] })
    expect(ld).toEqual({
      '@context': 'https://schema.org',
      '@type': 'LocalBusiness',
      '@id': 'https://loja.exemplo.com/#business',
      url: 'https://loja.exemplo.com/',
      name: 'Nelson Boulangerie',
      hasMenu: 'https://loja.exemplo.com/menu'
    })
    expect(emptyKeys(ld)).toEqual([])
  })

  it('endereço parcial vira PostalAddress só com o que existe', () => {
    const ld = localBusinessJsonLd({
      business: sparseBusiness({
        address: { street: '', neighborhood: '', locality: 'Londrina', region: '', postal_code: '', country_code: 'BR' }
      }),
      origin: ORIGIN
    })
    expect(ld.address).toEqual({ '@type': 'PostalAddress', addressLocality: 'Londrina', addressCountry: 'BR' })
    expect(emptyKeys(ld)).toEqual([])
  })

  it('horário: ignora dia desconhecido e grupo sem abertura, fechamento ou dias', () => {
    const ld = localBusinessJsonLd({
      business: sparseBusiness({
        opening_hours: [
          { days: ['monday', 'Feriado', 'https://schema.org/Tuesday'], opens: '07:00', closes: '19:00' },
          { days: ['Sunday'], opens: '', closes: '12:00' },
          { days: [], opens: '08:00', closes: '12:00' }
        ]
      }),
      origin: ORIGIN
    })
    expect(ld.openingHoursSpecification).toEqual([
      {
        '@type': 'OpeningHoursSpecification',
        dayOfWeek: ['https://schema.org/Monday', 'https://schema.org/Tuesday'],
        opens: '07:00',
        closes: '19:00'
      }
    ])
  })

  it('tipo mal formado cai em LocalBusiness; o logo da loja cobre o que falta', () => {
    const ld = localBusinessJsonLd({
      business: sparseBusiness({ type: 'Padaria Artesanal' }),
      origin: ORIGIN,
      fallbackLogoUrl: '/static/loja.png'
    })
    expect(ld['@type']).toBe('LocalBusiness')
    expect(ld.logo).toBe('https://loja.exemplo.com/static/loja.png')
    expect(ld.image).toEqual(['https://loja.exemplo.com/static/loja.png'])
  })
})

describe('websiteJsonLd', () => {
  it('liga o site ao estabelecimento pelo @id', () => {
    expect(websiteJsonLd({ origin: ORIGIN, name: 'Nelson Boulangerie', publisherId: 'https://loja.exemplo.com/#business' })).toEqual({
      '@context': 'https://schema.org',
      '@type': 'WebSite',
      '@id': 'https://loja.exemplo.com/#website',
      url: 'https://loja.exemplo.com/',
      inLanguage: 'pt-BR',
      name: 'Nelson Boulangerie',
      publisher: { '@id': 'https://loja.exemplo.com/#business' }
    })
  })
  it('sem nome nem publisher, não emite chave vazia', () => {
    const ld = websiteJsonLd({ origin: ORIGIN, name: '' })
    expect(ld.name).toBeUndefined()
    expect(ld.publisher).toBeUndefined()
    expect(emptyKeys(ld)).toEqual([])
  })
  it('o Bakery de fallback usa o mesmo @id para o qual o WebSite aponta', () => {
    const ld = bakeryJsonLd({ shop: shop(), origin: ORIGIN, url: ORIGIN + '/', latitude: null, longitude: null })
    expect(ld['@id']).toBe('https://loja.exemplo.com/#business')
  })
})

describe('listingDescription', () => {
  it('diz o que é a casa, onde fica e o que tem', () => {
    expect(listingDescription({
      subject: 'Cardápio',
      brandName: 'Nelson Boulangerie',
      tagline: 'Padaria artesanal',
      city: 'Londrina',
      names: ['Pães', 'Viennoiseries', 'Cafés']
    })).toBe('Cardápio da Nelson Boulangerie, padaria artesanal em Londrina: Pães, Viennoiseries e Cafés.')
  })
  it('sem nomes, fecha a frase; sem tagline, ainda diz a cidade', () => {
    expect(listingDescription({ subject: 'Cardápio', brandName: 'Nelson Boulangerie', city: 'Londrina' }))
      .toBe('Cardápio da Nelson Boulangerie em Londrina.')
  })
  it('tagline em Title Case (como está no cadastro vivo) desce a caixa inteira', () => {
    expect(listingDescription({ subject: 'Cardápio', brandName: 'Nelson Boulangerie', tagline: 'Padaria Artesanal', city: 'Londrina' }))
      .toBe('Cardápio da Nelson Boulangerie, padaria artesanal em Londrina.')
  })
  it('preserva sigla na tagline e corta em 160', () => {
    expect(listingDescription({ subject: 'Rústicos', brandName: 'Loja', tagline: 'NB padaria', names: ['Pão'] }))
      .toBe('Rústicos da Loja, NB padaria: Pão.')
    const long = listingDescription({
      subject: 'Cardápio',
      brandName: 'Loja',
      names: Array.from({ length: 4 }, (_, index) => `Produto de nome bem comprido número ${index}`)
    })
    expect(long.length).toBeLessThanOrEqual(161)
    expect(long.endsWith('…')).toBe(true)
  })
})

describe('productCollectionCrumb', () => {
  it('aponta para a página da coleção estática', () => {
    expect(productCollectionCrumb({ ref: 'rusticos', name: 'Rústicos' })).toEqual({ name: 'Rústicos', path: '/colecao/rusticos' })
  })
  it('nunca devolve fragmento; coleção dinâmica ou sem ref sai da trilha', () => {
    expect(productCollectionCrumb({ ref: 'featured', name: 'Destaques' })).toBeNull()
    expect(productCollectionCrumb({ ref: '', name: 'Rústicos' })).toBeNull()
    expect(productCollectionCrumb(null)).toBeNull()
  })
})

describe('jsonLdText', () => {
  it('neutraliza fechamento de script em conteúdo editorial', () => {
    const text = jsonLdText({ answer: '</script><script>alert(1)</script>' })
    expect(text).not.toContain('<')
    expect(text).toContain('\\u003c/script>')
    expect(JSON.parse(text).answer).toBe('</script><script>alert(1)</script>')
  })
})
