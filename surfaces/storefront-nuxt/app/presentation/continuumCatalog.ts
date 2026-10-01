import type { CatalogProjection, CatalogItemProjection } from '~/types/shopman'
import type {
  CatalogStructureState,
  ContinuousSnapshotCache,
  ContinuumSnapshot
} from '~/types/continuum'

export const CATALOG_STRUCTURE_STREAM = 's_shopman_storefront_catalog_structure_v1'

function sequenceNumber (value: string): bigint {
  if (!/^\d{20}$/.test(value)) throw new Error('continuum_invalid_sequence')
  return BigInt(value)
}

export function isCatalogStructureSnapshot (
  value: unknown
): value is ContinuumSnapshot<CatalogStructureState> {
  if (!value || typeof value !== 'object') return false
  const message = value as Partial<ContinuumSnapshot<CatalogStructureState>>
  const data = message.data
  const state = data?.state
  return message.specversion === '1.0'
    && message.type === 'continuum.projection.snapshot.v0.2'
    && data?.protocol_version === '0.2'
    && data.kind === 'snapshot'
    && data.stream?.id === CATALOG_STRUCTURE_STREAM
    && data.stream.classification === 'public'
    && typeof data.target?.cursor?.epoch === 'string'
    && /^\d{20}$/.test(data.target?.cursor?.sequence || '')
    && typeof data.target?.state_token === 'string'
    && typeof data.target?.state_digest === 'string'
    && !!state
    && typeof state === 'object'
    && !!state.items
    && Array.isArray(state.item_order)
    && Array.isArray(state.sections)
}

export function installCatalogStructureSnapshot (
  current: ContinuousSnapshotCache<CatalogStructureState> | null,
  message: ContinuumSnapshot<CatalogStructureState>,
  metadata: { etag: string, validatedAtMs: number, ageMs: number }
): ContinuousSnapshotCache<CatalogStructureState> {
  if (!isCatalogStructureSnapshot(message)) throw new Error('continuum_invalid_snapshot')
  if (!metadata.etag) throw new Error('continuum_missing_etag')

  if (current) {
    const previous = current.message.data.target
    const incoming = message.data.target
    if (previous.cursor.epoch === incoming.cursor.epoch) {
      const previousSequence = sequenceNumber(previous.cursor.sequence)
      const incomingSequence = sequenceNumber(incoming.cursor.sequence)
      if (incomingSequence < previousSequence) return current
      if (incomingSequence === previousSequence) {
        if (
          previous.state_token !== incoming.state_token
          || previous.state_digest !== incoming.state_digest
        ) {
          throw new Error('continuum_equivocation')
        }
      }
    }
  }

  return {
    message,
    etag: metadata.etag,
    validated_at_ms: metadata.validatedAtMs,
    age_ms: Math.max(0, metadata.ageMs)
  }
}

function pendingItem (item: CatalogStructureState['items'][string]): CatalogItemProjection {
  return {
    ...item,
    base_price_q: 0,
    price_display: '',
    has_promotion: false,
    original_price_display: null,
    promotion_label: null,
    availability: 'available',
    availability_label: '',
    can_add_to_cart: false,
    is_featured: false,
    qty_in_cart: 0,
    available_qty: null,
    is_paused: false,
    is_notifiable: false,
    is_notify_subscribed: false,
    is_favorite: false,
    dietary_warnings: []
  }
}

/**
 * Converte apenas o quadro estrutural público. Preço, disponibilidade, carrinho
 * e preferências continuam ausentes até a projeção canônica autorizada chegar.
 */
export function catalogFromStructureSnapshot (
  message: ContinuumSnapshot<CatalogStructureState> | null | undefined
): CatalogProjection | null {
  if (!message || !isCatalogStructureSnapshot(message)) return null
  const state = message.data.state
  const items = state.item_order
    .map(sku => state.items[sku])
    .filter((item): item is CatalogStructureState['items'][string] => !!item)
    .map(pendingItem)
  return {
    items,
    categories: Array.isArray(state.categories) ? state.categories : [],
    sections: state.sections.map(section => ({
      ref: section.ref,
      label: section.label,
      icon: section.icon,
      description: section.description,
      is_dynamic: false,
      dynamic_ref: null,
      category: section.category,
      skus: [...section.skus]
    })),
    featured: [],
    active_category_ref: null,
    happy_hour: null,
    favorite_category_ref: null,
    has_items: state.has_items && items.length > 0,
    empty_state: state.empty_state || null,
    search_empty_state: state.search_empty_state || null
  }
}

export function continuumFeatureEnabled (value: unknown): boolean {
  return value === true || String(value || '').toLowerCase() === 'true'
}
