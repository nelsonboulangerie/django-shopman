import { normalizeSearchText, formatCount } from '~/utils/display'
import type { CatalogItemProjection, CatalogSectionProjection } from '~/types/shopman'

// Transforms puros do cardápio: busca com scoring, filtros multi-select e
// badges de disponibilidade. Nenhum estado de UI aqui — a página orquestra.

export type SearchFilterKind = 'collection' | 'product' | 'keyword'

export type SearchListOption = {
  key: string
  kind: SearchFilterKind
  value: string
  label: string
  meta: string
  count?: number
  icon: string
  imageUrl?: string
  item?: CatalogItemProjection
  section?: CatalogSectionProjection
}

// O painel de busca tem três zonas: sem busca, a lista vertical de coleções
// (navega até a seção); com busca, chips filtram ao vivo (keywords e
// coleções) e linhas de produto navegam para a PDP.
export type SearchPanelView = {
  collections: SearchListOption[]
  chips: SearchListOption[]
  products: SearchListOption[]
}

export type TileBadge = {
  label: string
  variant: 'warning' | 'outline' | 'destructive'
}

export const FILTERED_SECTION_VALUE = 'filtered'

const COLLECTION_LABEL_BY_REF: Record<string, string> = {
  featured: 'Destaques',
  fresh_from_oven: 'Recém saídos do forno',
  new_arrivals: 'Novidades',
  favorites: 'Seus favoritos'
}

const PUBLIC_DYNAMIC_SECTION_SLUG_BY_REF: Record<string, string> = {
  featured: 'destaques',
  fresh_from_oven: 'recem-saidos-do-forno',
  new_arrivals: 'novidades',
  favorites: 'favoritos'
}

const DYNAMIC_SECTION_REF_BY_PUBLIC_SLUG = Object.fromEntries(
  Object.entries(PUBLIC_DYNAMIC_SECTION_SLUG_BY_REF).map(([ref, slug]) => [slug, ref])
) as Record<string, string>

const SEARCH_TOKEN_ALIASES: Record<string, string[]> = {
  pao: ['paes'],
  paes: ['pao']
}

const KEYWORD_LABEL_BY_KEY: Record<string, string> = {
  cafe: 'Café',
  pao: 'Pão',
  paes: 'Pães',
  'pao doce': 'Pão doce'
}

export function searchTokens (search: string): string[] {
  return Array.from(new Set(
    normalizeSearchText(search)
      .split(/[^\p{Letter}\p{Number}]+/gu)
      .map(token => token.trim())
      .filter(token => token.length >= 2)
  ))
}

function searchTokenCandidates (token: string): string[] {
  const candidates = new Set([token, ...(SEARCH_TOKEN_ALIASES[token] || [])])
  if (token.length > 2 && !token.endsWith('s')) candidates.add(`${token}s`)
  if (token.length > 3 && token.endsWith('s')) candidates.add(token.slice(0, -1))
  if (token.length > 4 && token.endsWith('is')) candidates.add(`${token.slice(0, -2)}l`)
  if (token.length > 4 && token.endsWith('l')) candidates.add(`${token.slice(0, -1)}is`)
  if (token.length > 4 && token.endsWith('ns')) candidates.add(`${token.slice(0, -2)}m`)
  if (token.length > 3 && token.endsWith('m')) candidates.add(`${token.slice(0, -1)}ns`)
  if (token.length > 4 && token.endsWith('oes')) candidates.add(`${token.slice(0, -3)}ao`)
  if (token.length > 3 && token.endsWith('ao')) {
    candidates.add(`${token.slice(0, -2)}oes`)
    candidates.add(`${token.slice(0, -2)}aes`)
  }
  return Array.from(candidates)
}

function allSearchTokensMatchText (tokens: string[], text: string): boolean {
  if (!tokens.length) return false
  const haystackTokens = searchTokens(text)
  return tokens.every(token => searchTokenCandidates(token).some(candidate => {
    if (text.includes(candidate)) return true
    if (candidate.length < 5) return false
    const maxDistance = candidate.length >= 9 ? 2 : 1
    return haystackTokens.some(haystackToken => editDistanceWithin(candidate, haystackToken, maxDistance))
  }))
}

export function searchTextMatches (search: string, text: string): boolean {
  const needle = normalizeSearchText(search)
  if (!needle) return true
  const haystack = normalizeSearchText(text)
  if (haystack.includes(needle)) return true
  return allSearchTokensMatchText(searchTokens(needle), haystack)
}

function editDistanceWithin (left: string, right: string, maxDistance: number): boolean {
  if (Math.abs(left.length - right.length) > maxDistance) return false
  if (left === right) return true
  let previous = Array.from({ length: right.length + 1 }, (_, index) => index)
  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    const current = [leftIndex]
    let rowMin = current[0]!
    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      const cost = left[leftIndex - 1] === right[rightIndex - 1] ? 0 : 1
      const value = Math.min(
        previous[rightIndex]! + 1,
        current[rightIndex - 1]! + 1,
        previous[rightIndex - 1]! + cost
      )
      current[rightIndex] = value
      rowMin = Math.min(rowMin, value)
    }
    if (rowMin > maxDistance) return false
    previous = current
  }
  return previous[right.length]! <= maxDistance
}

function humanizeRefLabel (ref: string): string {
  const label = ref.replace(/[-_]+/g, ' ').trim()
  return label ? label.charAt(0).toLocaleUpperCase('pt-BR') + label.slice(1) : 'Coleção'
}

function normalizedKeywordKey (term: string): string {
  return normalizeSearchText(term).replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim()
}

export function keywordDisplayLabel (term: string): string {
  const normalized = normalizedKeywordKey(term)
  return KEYWORD_LABEL_BY_KEY[normalized] || term.replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim()
}

export function collectionDisplayLabel (section: Pick<CatalogSectionProjection, 'ref' | 'label' | 'dynamic_ref'>): string {
  const label = section.label.trim()
  if (label) return label
  return COLLECTION_LABEL_BY_REF[section.dynamic_ref || section.ref] || humanizeRefLabel(section.ref)
}

function publicRouteSlug (value: string): string {
  return normalizeSearchText(value)
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

export function sectionPublicSlug (section: Pick<CatalogSectionProjection, 'ref' | 'label' | 'dynamic_ref' | 'is_dynamic'>): string {
  const internalRef = section.dynamic_ref || section.ref
  if (section.is_dynamic && PUBLIC_DYNAMIC_SECTION_SLUG_BY_REF[internalRef]) {
    return PUBLIC_DYNAMIC_SECTION_SLUG_BY_REF[internalRef]
  }
  return section.ref || publicRouteSlug(collectionDisplayLabel(section))
}

export function resolveSectionRefFromParam (
  raw: string,
  sections: ReadonlyArray<Pick<CatalogSectionProjection, 'ref' | 'label' | 'dynamic_ref' | 'is_dynamic'>>
): string {
  const wanted = publicRouteSlug(raw)
  if (!wanted) return ''
  for (const section of sections) {
    const candidates = [
      section.ref,
      section.dynamic_ref || '',
      sectionPublicSlug(section),
      collectionDisplayLabel(section)
    ].map(publicRouteSlug).filter(Boolean)
    if (candidates.includes(wanted)) return section.ref
  }
  return raw
}

export function dynamicCollectionPublicSlug (raw: string): string | null {
  const value = String(raw || '').trim()
  const normalized = publicRouteSlug(value)
  const ref = PUBLIC_DYNAMIC_SECTION_SLUG_BY_REF[value]
    ? value
    : DYNAMIC_SECTION_REF_BY_PUBLIC_SLUG[normalized]
  if (!ref) return null
  return PUBLIC_DYNAMIC_SECTION_SLUG_BY_REF[ref]!
}

export function dynamicCollectionMenuTarget (raw: string): string | null {
  const slug = dynamicCollectionPublicSlug(raw)
  return slug ? `/menu?secao=${encodeURIComponent(slug)}` : null
}

export function collectionTargetForSearchOption (option: SearchListOption): string {
  const section = option.section
  if (section && !section.is_dynamic) {
    return `/colecao/${encodeURIComponent(section.ref)}`
  }
  const publicSlug = section
    ? sectionPublicSlug(section)
    : PUBLIC_DYNAMIC_SECTION_SLUG_BY_REF[option.value] || publicRouteSlug(option.label || option.value)
  return `/menu?secao=${encodeURIComponent(publicSlug)}`
}

// Badge só quando informa: disponível é o estado default e não ganha selo.
// Aceita qualquer projeção com estado de disponibilidade (item de catálogo, PDP).
// WP-2: dentro de `unavailable`, "pausado pelo operador" ganha rótulo próprio
// ("Pausado", neutro — é temporário) e se separa do esgotado honesto (destrutivo).
export function tileBadge (item: Pick<CatalogItemProjection, 'availability' | 'availability_label'> & Partial<Pick<CatalogItemProjection, 'is_paused'>>): TileBadge | null {
  if (item.availability === 'low_stock') return { label: item.availability_label, variant: 'warning' }
  if (item.availability === 'planned_ok') return { label: item.availability_label, variant: 'outline' }
  if (item.availability === 'unavailable') {
    if (item.is_paused) return { label: 'Pausado', variant: 'outline' }
    return { label: item.availability_label, variant: 'destructive' }
  }
  return null
}

export function uniqueItemsBySku (items: ReadonlyArray<CatalogItemProjection>): CatalogItemProjection[] {
  const seen = new Set<string>()
  return items.filter(item => {
    if (seen.has(item.sku)) return false
    seen.add(item.sku)
    return true
  })
}

export function buildSectionsBySku (sections: ReadonlyArray<CatalogSectionProjection>): Map<string, CatalogSectionProjection[]> {
  const map = new Map<string, CatalogSectionProjection[]>()
  for (const section of sections) {
    for (const item of section.items) {
      const memberships = map.get(item.sku) || []
      memberships.push(section)
      map.set(item.sku, memberships)
    }
  }
  return map
}

export function primarySectionBySku (sectionsBySku: Map<string, CatalogSectionProjection[]>): Map<string, CatalogSectionProjection> {
  const map = new Map<string, CatalogSectionProjection>()
  for (const [sku, memberships] of sectionsBySku.entries()) {
    const firstStaticSection = memberships.find(section => !section.is_dynamic)
    const primary = firstStaticSection || memberships[0]
    if (primary) map.set(sku, primary)
  }
  return map
}

export function matchesItem (item: CatalogItemProjection, section: CatalogSectionProjection | undefined, search: string): boolean {
  return searchTextMatches(search, [
    item.name,
    item.short_description,
    item.category,
    section ? collectionDisplayLabel(section) : '',
    (item.tags || []).join(' '),
    (item.search_terms || []).join(' '),
    (item.allergens || []).join(' '),
    (item.dietary_info || []).join(' ')
  ].join(' '))
}

export function matchesProductAcrossCatalog (
  item: CatalogItemProjection,
  search: string,
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): boolean {
  return searchTextMatches(search, [
    item.name,
    item.short_description,
    item.category,
    ...((sectionsBySku.get(item.sku) || []).flatMap(section => [collectionDisplayLabel(section), section.description, section.ref])),
    (item.tags || []).join(' '),
    (item.search_terms || []).join(' '),
    (item.allergens || []).join(' '),
    (item.dietary_info || []).join(' ')
  ].join(' '))
}

export function collectionSearchScore (section: CatalogSectionProjection, search: string): number {
  const displayLabel = collectionDisplayLabel(section)
  const label = normalizeSearchText(displayLabel)
  const haystack = normalizeSearchText([displayLabel, section.description, section.ref].join(' '))
  if (label === search) return 0
  if (label.startsWith(search)) return 1
  if (label.includes(search)) return 2
  if (haystack.includes(search)) return 3
  if (allSearchTokensMatchText(searchTokens(search), haystack)) return 4
  return Number.POSITIVE_INFINITY
}

export function productSearchScore (
  item: CatalogItemProjection,
  search: string,
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): number {
  const name = normalizeSearchText(item.name)
  const directTerms = normalizeSearchText([
    item.name,
    (item.tags || []).join(' '),
    (item.search_terms || []).join(' ')
  ].join(' '))
  const tokens = searchTokens(search)
  if (name === search) return 0
  if (name.startsWith(search)) return 1
  if (name.includes(search)) return 2
  if (directTerms.includes(search)) return 3
  if (allSearchTokensMatchText(tokens, directTerms)) return 4
  if (matchesProductAcrossCatalog(item, search, sectionsBySku)) return 5
  return Number.POSITIVE_INFINITY
}

export function keywordLabelsForItem (item: CatalogItemProjection): string[] {
  const itemName = normalizedKeywordKey(item.name)
  const itemCategory = normalizedKeywordKey(item.category || '')
  const labels: string[] = []
  const seen = new Set<string>()
  for (const rawTerm of [
    ...(item.tags || []),
    ...(item.search_terms || []),
    ...(item.allergens || []),
    ...(item.dietary_info || [])
  ]) {
    const term = rawTerm.trim()
    const normalized = normalizedKeywordKey(term)
    if (!normalized || normalized === itemName || normalized === itemCategory) continue
    if (term.length > 32 || /[,.]/.test(term)) continue
    // SKUs vazam pelos search_terms; código de produto não é chip de keyword.
    if (/^[A-Z0-9_-]+$/.test(term) && /[A-Z]/.test(term)) continue
    if (normalized.split(/\s+/).length > 3) continue
    const label = keywordDisplayLabel(term)
    const labelKey = normalizedKeywordKey(label)
    if (seen.has(labelKey)) continue
    seen.add(labelKey)
    labels.push(label)
  }
  return labels
}

export function filterKey (kind: SearchFilterKind, value: string): string {
  return `${kind}:${value}`
}

export function parseFilterKey (key: string): { kind: SearchFilterKind, value: string } | null {
  const [kind, ...rest] = key.split(':')
  if (!kind || !['collection', 'product', 'keyword'].includes(kind) || !rest.length) return null
  return { kind: kind as SearchFilterKind, value: rest.join(':') }
}

export function itemMatchesFilter (
  item: CatalogItemProjection,
  section: CatalogSectionProjection | undefined,
  key: string,
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): boolean {
  const parsed = parseFilterKey(key)
  if (!parsed) return false
  if (parsed.kind === 'product') return item.sku === parsed.value
  if (parsed.kind === 'collection') return section?.ref === parsed.value
  return matchesProductAcrossCatalog(item, normalizeSearchText(parsed.value), sectionsBySku)
}

export function itemMatchesAnyFilter (
  item: CatalogItemProjection,
  section: CatalogSectionProjection | undefined,
  keys: string[],
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): boolean {
  if (!keys.length) return true
  return keys.some(key => itemMatchesFilter(item, section, key, sectionsBySku))
}

export function itemPassesMenuFilters (
  item: CatalogItemProjection,
  section: CatalogSectionProjection | undefined,
  search: string,
  appliedFilterKeys: string[],
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): boolean {
  if (search && !matchesItem(item, section, search)) return false
  if (appliedFilterKeys.length && !itemMatchesAnyFilter(item, section, appliedFilterKeys, sectionsBySku)) return false
  return true
}

// Em busca/filtro as seções estáticas vêm antes das dinâmicas e cada SKU
// aparece uma vez só (a primeira seção que o contém fica com ele).
export function orderedSections (
  sections: ReadonlyArray<CatalogSectionProjection>,
  searchOrFilterMode: boolean
): CatalogSectionProjection[] {
  if (!searchOrFilterMode) return [...sections]
  const staticSections = sections.filter(section => !section.is_dynamic)
  const dynamicSections = sections.filter(section => section.is_dynamic)
  return [...staticSections, ...dynamicSections]
}

export function filteredSections (
  sections: ReadonlyArray<CatalogSectionProjection>,
  search: string,
  appliedFilterKeys: string[],
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): CatalogSectionProjection[] {
  const searchOrFilterMode = Boolean(search || appliedFilterKeys.length)
  const seenSkus = new Set<string>()
  return orderedSections(sections, searchOrFilterMode)
    .map(section => ({
      ...section,
      items: section.items.filter(item => {
        if (!itemPassesMenuFilters(item, section, search, appliedFilterKeys, sectionsBySku)) return false
        if (!searchOrFilterMode) return true
        if (seenSkus.has(item.sku)) return false
        seenSkus.add(item.sku)
        return true
      })
    }))
    .filter(section => section.items.length)
}

export function collectionSearchOptions (
  sections: ReadonlyArray<CatalogSectionProjection>,
  search: string
): SearchListOption[] {
  if (!search) return []
  return sections
    .map(section => ({ section, score: collectionSearchScore(section, search) }))
    .filter(result => result.score < Number.POSITIVE_INFINITY)
    .sort((a, b) => a.score - b.score || collectionDisplayLabel(a.section).localeCompare(collectionDisplayLabel(b.section)))
    .map(result => {
      const count = uniqueItemsBySku([...result.section.items]).length
      const label = collectionDisplayLabel(result.section)
      return {
        key: filterKey('collection', result.section.ref),
        kind: 'collection' as const,
        value: result.section.ref,
        label,
        meta: formatCount(count, 'item', 'itens'),
        count,
        icon: 'lucide:rows-3',
        section: result.section
      }
    })
    .slice(0, 12)
}

export function productSearchOptions (
  items: ReadonlyArray<CatalogItemProjection>,
  search: string,
  sectionBySku: Map<string, CatalogSectionProjection>,
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): SearchListOption[] {
  if (!search) return []
  return items
    .map(item => ({
      item,
      section: sectionBySku.get(item.sku),
      score: productSearchScore(item, search, sectionsBySku)
    }))
    .filter(result => result.score < Number.POSITIVE_INFINITY)
    .sort((a, b) => a.score - b.score || a.item.name.localeCompare(b.item.name))
    .map(result => ({
      key: filterKey('product', result.item.sku),
      kind: 'product' as const,
      value: result.item.sku,
      label: result.item.name,
      meta: result.item.price_display,
      icon: 'lucide:utensils',
      imageUrl: result.item.image_url || undefined,
      item: result.item,
      section: result.section
    }))
    .slice(0, 12)
}

export function keywordSearchOptions (
  items: ReadonlyArray<CatalogItemProjection>,
  search: string,
  sectionBySku: Map<string, CatalogSectionProjection>,
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): SearchListOption[] {
  if (!search) return []
  const options = new Map<string, SearchListOption & { skus: Set<string> }>()
  for (const item of items) {
    const section = sectionBySku.get(item.sku)
    for (const keyword of keywordLabelsForItem(item)) {
      const normalized = normalizeSearchText(keyword)
      if (!normalized || !searchTextMatches(search, normalized)) continue
      const key = filterKey('keyword', keyword)
      if (!options.has(key)) {
        options.set(key, {
          key,
          kind: 'keyword',
          value: keyword,
          label: keyword,
          meta: '0 itens',
          icon: 'lucide:tag',
          section,
          skus: new Set()
        })
      }
      options.get(key)?.skus.add(item.sku)
    }
  }
  return Array.from(options.values())
    .map(option => {
      const count = items.filter(item => matchesProductAcrossCatalog(item, normalizeSearchText(option.value), sectionsBySku)).length
      return { ...option, count, meta: formatCount(count, 'item', 'itens') }
    })
    .sort((a, b) => (b.count || 0) - (a.count || 0) || a.label.localeCompare(b.label))
    .map(({ skus: _skus, ...option }) => option)
    .slice(0, 8)
}

// Chips dos filtros já aplicados — visíveis ao reabrir a busca, para
// desempilhar ou conferir o que está ativo.
export function appliedFilterChips (
  keys: string[],
  sections: ReadonlyArray<CatalogSectionProjection>
): Array<{ key: string, label: string }> {
  return keys
    .map(key => {
      const parsed = parseFilterKey(key)
      if (!parsed) return null
      if (parsed.kind === 'collection') {
        const section = sections.find(s => s.ref === parsed.value)
        return { key, label: section ? collectionDisplayLabel(section) : COLLECTION_LABEL_BY_REF[parsed.value] || humanizeRefLabel(parsed.value) }
      }
      return { key, label: parsed.value }
    })
    .filter((chip): chip is { key: string, label: string } => chip !== null)
}

export function searchPanelView (input: {
  sections: ReadonlyArray<CatalogSectionProjection>
  items: ReadonlyArray<CatalogItemProjection>
  search: string
  favoriteRef: string
  sectionBySku: Map<string, CatalogSectionProjection>
  sectionsBySku: Map<string, CatalogSectionProjection[]>
}): SearchPanelView {
  const { sections, items, search, favoriteRef, sectionBySku, sectionsBySku } = input
  if (!search) {
    return {
      collections: sections.map(section => {
        const count = uniqueItemsBySku([...section.items]).length
        const label = collectionDisplayLabel(section)
        return {
          key: filterKey('collection', section.ref),
          kind: 'collection' as const,
          value: section.ref,
          label,
          meta: formatCount(count, 'item', 'itens'),
          count,
          icon: !!favoriteRef && [section.ref, section.category?.ref, section.dynamic_ref].includes(favoriteRef) ? 'lucide:heart' : 'lucide:rows-3',
          section
        }
      }),
      chips: [],
      products: []
    }
  }

  const keywords = keywordSearchOptions(items, search, sectionBySku, sectionsBySku)
  const collections = collectionSearchOptions(sections, search)
  return {
    collections: [],
    chips: [...keywords, ...collections].slice(0, 10),
    products: productSearchOptions(items, search, sectionBySku, sectionsBySku)
  }
}
