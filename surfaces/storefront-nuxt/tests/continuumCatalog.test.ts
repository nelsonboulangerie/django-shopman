import { describe, expect, it } from 'vitest'
import {
  catalogFromStructureSnapshot,
  continuumFeatureEnabled,
  installCatalogStructureSnapshot,
  isCatalogStructureSnapshot
} from '../app/presentation/continuumCatalog'
import { resolveCatalogSections } from '../app/presentation/menu'
import type { CatalogStructureState, ContinuumSnapshot } from '../app/types/continuum'

function snapshot (
  sequence = '00000000000000000001',
  token = 'token-1',
  digest = 'sha256-digest-1'
): ContinuumSnapshot<CatalogStructureState> {
  return {
    specversion: '1.0',
    id: 'evt-1',
    source: 'urn:shopman:storefront:catalog-structure',
    type: 'continuum.projection.snapshot.v0.2',
    subject: 'stream/s_shopman_storefront_catalog_structure_v1',
    time: '2026-09-28T12:00:00.000Z',
    datacontenttype: 'application/json',
    dataschema: 'urn:shopman:schema:continuum:v0.2:snapshot',
    data: {
      protocol_version: '0.2',
      kind: 'snapshot',
      stream: {
        id: 's_shopman_storefront_catalog_structure_v1',
        projection: 'shopman.storefront.catalog_structure',
        partition: 'p_public_web',
        schema: 'urn:shopman:schema:storefront:catalog-structure:v1',
        classification: 'public'
      },
      target: {
        cursor: { epoch: 'epoch-1', sequence },
        state_token: token,
        state_digest: digest
      },
      freshness: { fresh_for_ms: 30_000, stale_if_error_ms: 120_000, age_ms: 0 },
      state: {
        items: {
          PAO: {
            sku: 'PAO',
            slug: 'pao',
            name: 'Pão',
            short_description: 'Fermentação natural',
            image_url: '/img/products/pao.webp',
            category: 'Pães',
            tags: ['artesanal'],
            search_terms: ['pao'],
            dietary_info: ['Contém glúten'],
            is_new: false,
            unit_weight_label: '500 g',
            allergens: ['glúten'],
            category_color: '#531D22',
            category_icon: 'wheat'
          }
        },
        item_order: ['PAO'],
        categories: [],
        sections: [{
          ref: 'paes',
          label: 'Pães',
          icon: 'wheat',
          description: 'Da fornada',
          category: null,
          skus: ['PAO']
        }],
        has_items: true
      },
      reset_reason: 'bootstrap'
    }
  }
}

describe('Continuum estrutural do cardápio', () => {
  it('valida o stream esperado e cria somente placeholders não compráveis', () => {
    const message = snapshot()
    expect(isCatalogStructureSnapshot(message)).toBe(true)

    const catalog = catalogFromStructureSnapshot(message)!
    // Mesma forma do payload canônico: a seção traz os SKUs, a tela resolve.
    expect(catalog.sections[0]?.skus).toEqual(['PAO'])
    const sections = resolveCatalogSections(catalog)
    expect(sections[0]?.items[0]).toBe(catalog.items[0])
    expect(sections[0]?.items[0]).toMatchObject({
      sku: 'PAO',
      name: 'Pão',
      price_display: '',
      can_add_to_cart: false,
      is_favorite: false,
      dietary_warnings: []
    })
    expect(catalog.items[0]).not.toHaveProperty('session')
    expect(sections[0]?.items[0]?.base_price_q).toBe(0)
  })

  it('rejeita equivocation e não deixa uma sequência antiga regredir a tela', () => {
    const first = installCatalogStructureSnapshot(null, snapshot('00000000000000000002'), {
      etag: '"etag-2"',
      validatedAtMs: 100,
      ageMs: 0
    })
    const regressed = installCatalogStructureSnapshot(first, snapshot('00000000000000000001'), {
      etag: '"etag-1"',
      validatedAtMs: 200,
      ageMs: 0
    })
    expect(regressed).toBe(first)
    expect(() => installCatalogStructureSnapshot(
      first,
      snapshot('00000000000000000002', 'other-token', 'other-digest'),
      { etag: '"other"', validatedAtMs: 300, ageMs: 0 }
    )).toThrow('continuum_equivocation')
  })

  it('interpreta a flag de runtime sem tornar a string false verdadeira', () => {
    expect(continuumFeatureEnabled(true)).toBe(true)
    expect(continuumFeatureEnabled('true')).toBe(true)
    expect(continuumFeatureEnabled(false)).toBe(false)
    expect(continuumFeatureEnabled('false')).toBe(false)
  })
})
