import type { CategoryProjection, EmptyStateCtaCopy, ProductOptionGroup } from '~/types/shopman'

export interface ContinuumVersion {
  cursor: {
    epoch: string
    sequence: string
  }
  state_token: string
  state_digest: string
}

export interface CatalogStructureItem {
  sku: string
  slug: string
  name: string
  short_description: string
  image_url: string | null
  category: string | null
  tags: string[]
  search_terms: string[]
  dietary_info: string[]
  is_new: boolean
  unit_weight_label: string | null
  allergens: string[]
  category_color: string | null
  category_icon: string | null
  choice_group?: string | null
  choice_group_label?: string | null
  option_groups?: ProductOptionGroup[]
}

export interface CatalogStructureState {
  items: Record<string, CatalogStructureItem>
  item_order: string[]
  categories: CategoryProjection[]
  sections: Array<{
    ref: string
    label: string
    icon: string
    description: string
    category: CategoryProjection | null
    skus: string[]
  }>
  empty_state?: EmptyStateCtaCopy | null
  search_empty_state?: EmptyStateCtaCopy | null
  has_items: boolean
}

export interface ContinuumSnapshot<TState> {
  specversion: '1.0'
  id: string
  source: string
  type: 'continuum.projection.snapshot.v0.2'
  subject: string
  time: string
  datacontenttype: 'application/json'
  dataschema: string
  data: {
    protocol_version: '0.2'
    kind: 'snapshot'
    stream: {
      id: string
      projection: string
      partition: string
      schema: string
      classification: 'public'
    }
    target: ContinuumVersion
    freshness: {
      fresh_for_ms: number
      stale_if_error_ms: number
      age_ms: number
    }
    state: TState
    reset_reason?: 'bootstrap' | 'repair' | 'epoch_changed'
  }
}

export interface ContinuousSnapshotCache<TState> {
  message: ContinuumSnapshot<TState>
  etag: string
  validated_at_ms: number
  age_ms: number
}
