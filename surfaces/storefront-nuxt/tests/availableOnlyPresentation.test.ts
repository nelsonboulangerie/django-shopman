import { describe, expect, it } from 'vitest'
import {
  availableOnlyHint,
  availableOnlySections,
  choiceGroupsByName,
  hiddenUnavailableCount,
  isOrderableNow,
  orderableItems,
  parseAvailableOnlyChoice,
  resolveAvailableOnly
} from '~/presentation/menu'
import type { CatalogItemProjection, CatalogSection } from '~/types/shopman'

function item (overrides: Partial<CatalogItemProjection> = {}): CatalogItemProjection {
  return {
    sku: 'PAO-001',
    slug: 'pao-frances',
    name: 'Pão Francês',
    short_description: '',
    image_url: null,
    category: 'Rústicos',
    tags: [],
    search_terms: [],
    base_price_q: 150,
    price_display: 'R$ 1,50',
    has_promotion: false,
    original_price_display: null,
    promotion_label: null,
    unit_weight_label: null,
    availability: 'available',
    availability_label: '',
    can_add_to_cart: true,
    dietary_info: [],
    is_new: false,
    is_featured: false,
    qty_in_cart: 0,
    available_qty: null,
    allergens: [],
    category_color: null,
    category_icon: null,
    ...overrides
  } as CatalogItemProjection
}

function section (ref: string, items: CatalogItemProjection[]): CatalogSection {
  return { ref, label: ref, icon: '', description: '', is_dynamic: false, dynamic_ref: null, category: null, items } as CatalogSection
}

const pao = item({ sku: 'PAO', name: 'Pão' })
const croissant = item({ sku: 'CROIS', name: 'Croissant', availability: 'unavailable', availability_label: 'Indisponível' })
const brioche = item({ sku: 'BRIO', name: 'Brioche', availability: 'low_stock' })
const encomenda = item({ sku: 'BOLO', name: 'Bolo', availability: 'planned_ok' })

describe('mostrar só disponíveis', () => {
  it('só o indisponível sai: pouco estoque e "sai mais tarde" ainda podem ser pedidos', () => {
    expect(isOrderableNow(pao)).toBe(true)
    expect(isOrderableNow(brioche)).toBe(true)
    expect(isOrderableNow(encomenda)).toBe(true)
    expect(isOrderableNow(croissant)).toBe(false)
    expect(orderableItems([pao, croissant, brioche]).map(i => i.sku)).toEqual(['PAO', 'BRIO'])
  })

  it('a escolha do cliente vence o padrão da casa; sem escolha vale a casa', () => {
    expect(resolveAvailableOnly(null, true)).toBe(true)
    expect(resolveAvailableOnly(null, false)).toBe(false)
    expect(resolveAvailableOnly(null, undefined)).toBe(false)
    expect(resolveAvailableOnly(false, true)).toBe(false)
    expect(resolveAvailableOnly(true, false)).toBe(true)
  })

  it('o storage só conhece on/off; qualquer outra coisa é "não escolheu"', () => {
    expect(parseAvailableOnlyChoice('on')).toBe(true)
    expect(parseAvailableOnlyChoice('off')).toBe(false)
    expect(parseAvailableOnlyChoice(null)).toBeNull()
    expect(parseAvailableOnlyChoice('true')).toBeNull()
  })

  it('seção que fica sem nada disponível sai do cardápio', () => {
    const sections = [section('folhados', [croissant]), section('paes', [pao, croissant])]
    const result = availableOnlySections(sections)
    expect(result.map(s => s.ref)).toEqual(['paes'])
    expect(result[0]!.items.map(i => i.sku)).toEqual(['PAO'])
  })

  it('conta SKUs diferentes: o mesmo item em duas seções é um escondido', () => {
    expect(hiddenUnavailableCount([croissant, pao, croissant])).toBe(1)
    expect(hiddenUnavailableCount([pao, brioche])).toBe(0)
  })

  it('o zero se explica e a palavra é só "indisponível"', () => {
    expect(availableOnlyHint(false, 3)).toBe('Esconde o que não dá para pedir agora.')
    expect(availableOnlyHint(true, 0)).toBe('Tudo o que está no cardápio pode ser pedido agora.')
    expect(availableOnlyHint(true, 1)).toBe('1 item indisponível escondido.')
    expect(availableOnlyHint(true, 4)).toBe('4 itens indisponíveis escondidos.')
    for (const hint of [availableOnlyHint(true, 2), availableOnlyHint(false, 2)]) {
      expect(hint).not.toMatch(/esgot|pausad/i)
    }
  })

  it('opção indisponível sai do cartão de escolha; grupo com uma opção volta a ser item', () => {
    const chaA = item({ sku: 'CHA-A', choice_group: 'Chás' } as Partial<CatalogItemProjection>)
    const chaB = item({ sku: 'CHA-B', choice_group: 'Chás', availability: 'unavailable' } as Partial<CatalogItemProjection>)
    expect(choiceGroupsByName([chaA, chaB]).has('Chás')).toBe(true)
    expect(choiceGroupsByName(orderableItems([chaA, chaB])).has('Chás')).toBe(false)
  })
})
