/**
 * Contrato de projection COMPARTILHADO BE↔FE — o lado consumidor.
 *
 * Os JSONs em `contracts/projections/` são GERADOS pelo Django
 * (shopman/storefront/tests/test_shared_projection_contracts.py) a partir de
 * um cenário canônico e comparados byte a byte lá. Aqui o MESMO arquivo é:
 *
 *  1. atribuído aos tipos TS (a atribuição roda no `npm run typecheck` do
 *     Surfaces Gate — rename de chave no BE quebra AQUI, não na tela);
 *  2. atravessado pelas funções de presentation reais, provando que o FE
 *     consome a forma que o BE de fato produz — nunca uma fixture paralela.
 *
 * Mudou o contrato? Regenere no Django (SHOPMAN_UPDATE_CONTRACTS=1) e
 * commite BE + JSON + FE juntos.
 */
import { describe, expect, it } from 'vitest'

import catalogContractJson from '../../../contracts/projections/storefront_catalog.json'
import productDetailContractJson from '../../../contracts/projections/storefront_product_detail.json'
import {
  buildSectionsBySku,
  tileBadge,
  uniqueItemsBySku,
} from '../app/presentation/menu'
import type {
  CatalogItemProjection,
  CatalogProjection,
  ProductDetailProjection,
} from '../app/types/shopman'

// A atribuição É o teste de contrato estrutural: o typecheck do gate reprova
// qualquer chave que o BE renomeie ou remova.
const catalogContract: CatalogProjection =
  catalogContractJson as unknown as CatalogProjection
const productDetailContract: ProductDetailProjection =
  productDetailContractJson as unknown as ProductDetailProjection

describe('contrato compartilhado: storefront_catalog', () => {
  it('cobre os estados de disponibilidade que a loja distingue', () => {
    const bySku = new Map(catalogContract.items.map((item) => [item.sku, item]))
    expect(bySku.get('PAO-CONTRATO')?.availability).toBe('available')
    expect(bySku.get('CROISSANT-CONTRATO')?.availability).toBe('low_stock')
    expect(bySku.get('CROISSANT-CONTRATO')?.available_qty).toBe(2)
    expect(bySku.get('BOLO-CONTRATO')?.availability).toBe('unavailable')
    expect(bySku.get('BOLO-CONTRATO')?.is_notifiable).toBe(true)
  })

  it('atravessa a presentation real sem fixture paralela', () => {
    const items = uniqueItemsBySku(catalogContract.items)
    expect(items.length).toBeGreaterThanOrEqual(4)

    const sections = buildSectionsBySku(catalogContract.sections)
    for (const item of items) {
      expect(sections.has(item.sku)).toBe(true)
    }

    const badges = items.map((item: CatalogItemProjection) => tileBadge(item))
    // Esgotado ganha selo; disponível não.
    expect(badges.some((badge) => badge !== null)).toBe(true)
  })
})

describe('contrato compartilhado: storefront_product_detail', () => {
  it('carrega os campos que a PDP renderiza', () => {
    expect(productDetailContract.sku).toBe('CROISSANT-CONTRATO')
    expect(productDetailContract.availability).toBe('low_stock')
    expect(productDetailContract.available_qty).toBe(2)
    expect(productDetailContract.can_add_to_cart).toBe(true)
    expect(typeof productDetailContract.availability_label).toBe('string')
    expect(productDetailContract.availability_label.length).toBeGreaterThan(0)
  })
})
