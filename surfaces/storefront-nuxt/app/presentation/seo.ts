import { dynamicCollectionPublicSlug } from '~/presentation/menu'
import type {
  CatalogItemProjection,
  CategoryProjection,
  FAQItemProjection,
  ProductDetailProjection,
  ShopProjection,
  SiteBusinessProjection,
  SitePageSeoProjection,
  SitePagesProjection,
  SiteProjection,
  SiteVerificationsProjection
} from '~/types/shopman'

// Lógica pura de SEO técnico. Contrato vem das projeções do backend (SAGRADO):
// montamos meta tags + JSON-LD schema.org a partir do dado já servido (produto,
// shop, config). Sem Vue/Nuxt aqui — 100% testável (vitest). As páginas passam
// o `origin`/`url` (via useRequestURL) para os links ficarem absolutos.

const CURRENCY = 'BRL'

// ── URLs absolutas ───────────────────────────────────────────────────────────
export function absoluteUrl (origin: string, path: string): string {
  const base = (origin || '').replace(/\/$/, '')
  if (!path) return base
  if (/^https?:\/\//i.test(path)) return path
  return `${base}${path.startsWith('/') ? '' : '/'}${path}`
}

// Imagem para Open Graph/schema: precisa ser absoluta. Resolve relativas contra
// o origin; passa absolutas adiante; null/vazio → null (cai no fallback).
export function absoluteImage (origin: string, imageUrl: string | null | undefined): string | null {
  const value = (imageUrl || '').trim()
  if (!value) return null
  return absoluteUrl(origin, value)
}

// ── Preço/disponibilidade no vocabulário schema.org ──────────────────────────
export function priceFromQ (priceQ: number | null | undefined): string {
  return (Math.max(0, Math.round(priceQ || 0)) / 100).toFixed(2)
}

export function availabilitySchemaUrl (availability: string | null | undefined): string {
  switch (availability) {
    case 'available':
    case 'low_stock':
      return 'https://schema.org/InStock'
    case 'planned_ok':
      return 'https://schema.org/PreOrder'
    default:
      return 'https://schema.org/OutOfStock'
  }
}

// ── Meta description ─────────────────────────────────────────────────────────
// Prioriza a curada (seo_description), cai para short_description; corta limpo
// em ~160 chars sem quebrar palavra.
export function metaDescription (
  product: Pick<ProductDetailProjection, 'seo_description' | 'short_description' | 'name'> | null | undefined,
  max = 160
): string {
  if (!product) return ''
  const raw = (product.seo_description || product.short_description || product.name || '').trim()
  return truncateClean(raw, max)
}

export function truncateClean (text: string, max: number): string {
  const value = (text || '').trim()
  if (value.length <= max) return value
  const cut = value.slice(0, max)
  const lastSpace = cut.lastIndexOf(' ')
  return `${(lastSpace > max * 0.6 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`
}

// ── JSON-LD: Product + Offer ─────────────────────────────────────────────────
export function productJsonLd (params: {
  product: ProductDetailProjection
  origin: string
  url: string
  brandName: string
}): Record<string, unknown> {
  const { product, origin, url, brandName } = params
  // Rich results favorecem múltiplas imagens: principal + galeria (absolutas, deduped).
  const images = [...new Set(
    [product.image_url, ...(product.gallery || [])]
      .map(candidate => absoluteImage(origin, candidate))
      .filter((candidate): candidate is string => !!candidate)
  )]
  const ld: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: product.name,
    sku: product.sku,
    description: metaDescription(product, 320),
    offers: {
      '@type': 'Offer',
      price: priceFromQ(product.base_price_q),
      priceCurrency: CURRENCY,
      availability: availabilitySchemaUrl(product.availability),
      url
    }
  }
  if (images.length) ld.image = images.length === 1 ? images[0] : images
  if (brandName) ld.brand = { '@type': 'Brand', name: brandName }
  if (Array.isArray(product.seo_keywords) && product.seo_keywords.length) {
    ld.keywords = product.seo_keywords.join(', ')
  }
  return ld
}

// ── JSON-LD: BreadcrumbList ──────────────────────────────────────────────────
export function breadcrumbJsonLd (items: Array<{ name: string, url: string }>): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: item.url
    }))
  }
}

// ── JSON-LD: CollectionPage + ItemList ───────────────────────────────────────
// Cardápio = uma página de coleção com a lista de produtos. Cada item aponta para
// a própria PDP (/produto/<sku>) com Offer mínima — ajuda o Google a entender a
// vitrine sem duplicar o Product completo (que vive na PDP).
export function collectionJsonLd (params: {
  name: string
  url: string
  origin: string
  items: Array<Pick<CatalogItemProjection, 'sku' | 'name' | 'base_price_q' | 'availability' | 'image_url'>>
}): Record<string, unknown> {
  const { name, url, origin, items } = params
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name,
    url,
    mainEntity: {
      '@type': 'ItemList',
      numberOfItems: items.length,
      itemListElement: items.map((item, index) => {
        const product: Record<string, unknown> = {
          '@type': 'Product',
          name: item.name,
          sku: item.sku,
          url: absoluteUrl(origin, `/produto/${encodeURIComponent(item.sku)}`),
          offers: {
            '@type': 'Offer',
            price: priceFromQ(item.base_price_q),
            priceCurrency: CURRENCY,
            availability: availabilitySchemaUrl(item.availability)
          }
        }
        const image = absoluteImage(origin, item.image_url)
        if (image) product.image = image
        return {
          '@type': 'ListItem',
          position: index + 1,
          item: product
        }
      })
    }
  }
}

// ── JSON-LD: Bakery (LocalBusiness) ──────────────────────────────────────────
// Subtipo de FoodEstablishment. Só emite o que existe — nada de campo vazio que
// gere schema inválido.
export function bakeryJsonLd (params: {
  shop: ShopProjection
  origin: string
  url: string
  latitude: number | null
  longitude: number | null
}): Record<string, unknown> {
  const { shop, origin, url, latitude, longitude } = params
  const ld: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Bakery',
    '@id': businessJsonLdId(origin),
    name: shop.brand_name,
    url
  }
  const logo = absoluteImage(origin, shop.logo_url)
  if (logo) ld.image = logo
  if (shop.description) ld.description = truncateClean(shop.description, 320)
  if (shop.phone) ld.telephone = shop.phone
  if (shop.email) ld.email = shop.email
  if (shop.full_address) {
    ld.address = { '@type': 'PostalAddress', streetAddress: shop.full_address, addressLocality: shop.default_city || undefined }
  }
  if (typeof latitude === 'number' && typeof longitude === 'number') {
    ld.geo = { '@type': 'GeoCoordinates', latitude, longitude }
  }
  if (Array.isArray(shop.social_links) && shop.social_links.length) {
    ld.sameAs = shop.social_links.map(link => link.url).filter(Boolean)
  }
  return ld
}

// ── Identidade pública do site (/api/v1/storefront/site/) ────────────────────
// O endpoint é novo e a loja no ar pode ainda não tê-lo: tudo aqui tolera o
// campo ausente, o tipo errado e o objeto inteiro nulo. Nada vira `undefined`
// no meio do caminho — string ausente é '', lista ausente é [].

function cleanText (value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function cleanTextList (value: unknown): string[] {
  return Array.isArray(value) ? value.map(cleanText).filter(Boolean) : []
}

function asRecord (value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function cleanPage (value: unknown): SitePageSeoProjection {
  const page = asRecord(value)
  return { title: cleanText(page.title), description: cleanText(page.description) }
}

function finiteNumber (value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function normalizeSite (raw: unknown): SiteProjection | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const site = raw as Record<string, unknown>
  const pages = asRecord(site.pages)
  const verifications = asRecord(site.verifications)
  const business = asRecord(site.business)
  const address = asRecord(business.address)
  const geo = asRecord(business.geo)
  const latitude = finiteNumber(geo.latitude)
  const longitude = finiteNumber(geo.longitude)
  const foundingYear = finiteNumber(business.founding_year)
  return {
    pages: {
      home: cleanPage(pages.home),
      menu: cleanPage(pages.menu),
      faq: cleanPage(pages.faq)
    },
    share_image_url: cleanText(site.share_image_url),
    verifications: {
      google: cleanText(verifications.google),
      bing: cleanText(verifications.bing),
      facebook: cleanText(verifications.facebook),
      pinterest: cleanText(verifications.pinterest)
    },
    business: {
      type: cleanText(business.type),
      name: cleanText(business.name),
      legal_name: cleanText(business.legal_name),
      description: cleanText(business.description),
      url: cleanText(business.url),
      telephone: cleanText(business.telephone),
      email: cleanText(business.email),
      logo_url: cleanText(business.logo_url),
      price_range: cleanText(business.price_range),
      founding_year: foundingYear !== null && foundingYear > 0 ? Math.trunc(foundingYear) : null,
      address: {
        street: cleanText(address.street),
        neighborhood: cleanText(address.neighborhood),
        locality: cleanText(address.locality),
        region: cleanText(address.region),
        postal_code: cleanText(address.postal_code),
        country_code: cleanText(address.country_code)
      },
      geo: latitude !== null && longitude !== null ? { latitude, longitude } : null,
      opening_hours: (Array.isArray(business.opening_hours) ? business.opening_hours : []).map((entry) => {
        const group = asRecord(entry)
        return { days: cleanTextList(group.days), opens: cleanText(group.opens), closes: cleanText(group.closes) }
      }),
      maps_url: cleanText(business.maps_url),
      same_as: cleanTextList(business.same_as)
    },
    faq: (Array.isArray(site.faq) ? site.faq : [])
      .map((entry) => {
        const item = asRecord(entry)
        return { ref: cleanText(item.ref), question: cleanText(item.question), answer: cleanText(item.answer) }
      })
      .filter(item => item.question && item.answer)
  }
}

// Título e descrição que a casa escreveu para a página; '' quando não escreveu
// (a página cai no próprio padrão).
export function sitePageSeo (site: SiteProjection | null | undefined, page: keyof SitePagesProjection): SitePageSeoProjection {
  return {
    title: cleanText(site?.pages?.[page]?.title),
    description: cleanText(site?.pages?.[page]?.description)
  }
}

// Meta tags de verificação de domínio. Só entra o que a casa preencheu: uma meta
// com `content` vazio é lixo no <head> e, no Google, verificação que falha.
const VERIFICATION_META_NAME: Record<keyof SiteVerificationsProjection, string> = {
  google: 'google-site-verification',
  bing: 'msvalidate.01',
  facebook: 'facebook-domain-verification',
  pinterest: 'p:domain_verify'
}

export function siteVerificationMeta (
  verifications: Partial<SiteVerificationsProjection> | null | undefined
): Array<{ name: string, content: string }> {
  return (Object.keys(VERIFICATION_META_NAME) as Array<keyof SiteVerificationsProjection>)
    .map(key => ({ name: VERIFICATION_META_NAME[key], content: cleanText(verifications?.[key]) }))
    .filter(entry => entry.content)
}

// ── JSON-LD: LocalBusiness + WebSite ─────────────────────────────────────────
// O estabelecimento tem UM identificador no site inteiro; o WebSite aponta para
// ele como publisher. Assim o Google junta as duas descrições numa entidade só.
export function businessJsonLdId (origin: string): string {
  return absoluteUrl(origin, '/#business')
}

export function websiteJsonLdId (origin: string): string {
  return absoluteUrl(origin, '/#website')
}

const SCHEMA_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

function schemaDayUrl (day: string): string | null {
  const wanted = day.replace(/^https?:\/\/schema\.org\//i, '').toLowerCase()
  const match = SCHEMA_DAYS.find(candidate => candidate.toLowerCase() === wanted)
  return match ? `https://schema.org/${match}` : null
}

// Só um nome de tipo schema.org bem formado passa (Bakery, CafeOrCoffeeShop…): o
// valor vem do cadastro, e um espaço ou acento ali invalidaria o bloco inteiro.
function schemaTypeName (value: string): string {
  return /^[A-Z][A-Za-z]+$/.test(value) ? value : 'LocalBusiness'
}

export function localBusinessJsonLd (params: {
  business: SiteBusinessProjection
  origin: string
  // Imagens candidatas, em ordem de preferência (compartilhamento, destaque…).
  images?: Array<string | null | undefined>
  // Logo quando o estabelecimento não tem um próprio (o da loja, por exemplo).
  fallbackLogoUrl?: string | null
}): Record<string, unknown> {
  const { business, origin } = params
  const logo = absoluteImage(origin, business.logo_url || params.fallbackLogoUrl)
  const images = [...new Set(
    [...(params.images || []), logo]
      .map(candidate => absoluteImage(origin, candidate))
      .filter((candidate): candidate is string => !!candidate)
  )]

  const ld: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': schemaTypeName(cleanText(business.type)),
    '@id': businessJsonLdId(origin),
    url: absoluteUrl(origin, '/')
  }
  const fields: Array<[string, unknown]> = [
    ['name', cleanText(business.name)],
    ['legalName', cleanText(business.legal_name)],
    ['description', truncateClean(cleanText(business.description), 320)],
    ['telephone', cleanText(business.telephone)],
    ['email', cleanText(business.email)],
    ['image', images.length ? images : null],
    ['logo', logo],
    ['priceRange', cleanText(business.price_range)],
    ['foundingDate', business.founding_year ? String(business.founding_year) : null]
  ]
  for (const [key, value] of fields) {
    if (value) ld[key] = value
  }

  const address = business.address
  const postalAddress: Record<string, string> = {}
  const addressFields: Array<[string, string]> = [
    // O bairro vai junto da rua: schema.org não tem campo de bairro, e endereço
    // brasileiro sem ele fica ambíguo para quem lê.
    ['streetAddress', [cleanText(address?.street), cleanText(address?.neighborhood)].filter(Boolean).join(' - ')],
    ['addressLocality', cleanText(address?.locality)],
    ['addressRegion', cleanText(address?.region)],
    ['postalCode', cleanText(address?.postal_code)],
    ['addressCountry', cleanText(address?.country_code)]
  ]
  for (const [key, value] of addressFields) {
    if (value) postalAddress[key] = value
  }
  if (Object.keys(postalAddress).length) ld.address = { '@type': 'PostalAddress', ...postalAddress }

  const latitude = finiteNumber(business.geo?.latitude)
  const longitude = finiteNumber(business.geo?.longitude)
  if (latitude !== null && longitude !== null) {
    ld.geo = { '@type': 'GeoCoordinates', latitude, longitude }
  }

  const openingHours = (business.opening_hours || [])
    .map(group => ({
      days: [...new Set((group.days || []).map(schemaDayUrl).filter((day): day is string => !!day))],
      opens: cleanText(group.opens),
      closes: cleanText(group.closes)
    }))
    .filter(group => group.days.length && group.opens && group.closes)
    .map(group => ({
      '@type': 'OpeningHoursSpecification',
      dayOfWeek: group.days,
      opens: group.opens,
      closes: group.closes
    }))
  if (openingHours.length) ld.openingHoursSpecification = openingHours

  const mapsUrl = cleanText(business.maps_url)
  if (mapsUrl) ld.hasMap = mapsUrl
  const sameAs = [...new Set(cleanTextList(business.same_as))]
  if (sameAs.length) ld.sameAs = sameAs
  ld.hasMenu = absoluteUrl(origin, '/menu')
  return ld
}

export function websiteJsonLd (params: {
  origin: string
  name: string
  publisherId?: string | null
}): Record<string, unknown> {
  const ld: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    '@id': websiteJsonLdId(params.origin),
    url: absoluteUrl(params.origin, '/'),
    inLanguage: 'pt-BR'
  }
  const name = cleanText(params.name)
  if (name) ld.name = name
  if (params.publisherId) ld.publisher = { '@id': params.publisherId }
  return ld
}

// ── Descrição de listagem ────────────────────────────────────────────────────
// "42 itens publicados." não diz a ninguém — nem ao Google — o que é o lugar.
// A frase padrão nomeia a casa, o que ela é, onde fica e o que tem, só com o que
// veio do cadastro e do catálogo (nada inventado).
// A tagline entra no meio da frase: "Padaria artesanal" vira "padaria artesanal".
// Cadastro em Title Case ("Padaria Artesanal") desce a caixa de toda palavra —
// senão sai "padaria Artesanal"; sigla ("NB") fica como está.
function taglineInSentence (text: string): string {
  const upper = (word: string) => word.toLocaleUpperCase('pt-BR')
  const lower = (word: string) => word.toLocaleLowerCase('pt-BR')
  const isAcronym = (word: string) => word.length > 1 && word === upper(word) && word !== lower(word)
  const words = text.split(/\s+/)
  const titleCase = words
    .filter(word => word.length > 2 && !isAcronym(word))
    .every(word => word.charAt(0) === upper(word.charAt(0)))
  return words
    .map((word, index) => (isAcronym(word) || (!titleCase && index > 0))
      ? word
      : lower(word.charAt(0)) + word.slice(1))
    .join(' ')
}

function joinNames (names: string[]): string {
  if (names.length <= 1) return names[0] || ''
  return `${names.slice(0, -1).join(', ')} e ${names[names.length - 1]}`
}

export function listingDescription (params: {
  subject: string
  brandName: string
  tagline?: string | null
  city?: string | null
  names?: Array<string | null | undefined>
  max?: number
}): string {
  const subject = cleanText(params.subject)
  const brandName = cleanText(params.brandName)
  const tagline = cleanText(params.tagline)
  const city = cleanText(params.city)
  const names = [...new Set((params.names || []).map(cleanText).filter(Boolean))].slice(0, 4)

  let lead = brandName ? `${subject} da ${brandName}` : subject
  if (tagline) lead += `, ${taglineInSentence(tagline)}${city ? ` em ${city}` : ''}`
  else if (city) lead += ` em ${city}`
  return truncateClean(names.length ? `${lead}: ${joinNames(names)}.` : `${lead}.`, params.max ?? 160)
}

// ── Coleção na trilha do produto ─────────────────────────────────────────────
// A trilha só aponta para uma página que existe e é indexável: a coleção
// estática em /colecao/<ref>. Coleção dinâmica (destaques, novidades…) não tem
// página própria, e `/menu#ref` é fragmento — o Google o descarta e o nível da
// trilha não leva a lugar nenhum. Sem página, o nível sai.
export function productCollectionCrumb (
  category: Pick<CategoryProjection, 'ref' | 'name'> | null | undefined
): { name: string, path: string } | null {
  const ref = cleanText(category?.ref)
  const name = cleanText(category?.name)
  if (!ref || !name || dynamicCollectionPublicSlug(ref)) return null
  return { name, path: `/colecao/${encodeURIComponent(ref)}` }
}

export function faqJsonLd (items: FAQItemProjection[]): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: items.map(item => ({
      '@type': 'Question',
      name: item.question,
      acceptedAnswer: {
        '@type': 'Answer',
        text: item.answer
      }
    }))
  }
}

export function jsonLdText (value: Record<string, unknown>): string {
  return JSON.stringify(value)
    .replace(/</g, '\\u003c')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029')
}
