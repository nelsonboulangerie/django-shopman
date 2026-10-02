// /menu com o Continuum ligado (como no ambiente vivo: a flag nasce `false` no
// repositório e `true` em NUXT_PUBLIC_CONTINUUM_CATALOG_ENABLED). A vitrine
// chega antes de preços e disponibilidade, e havia DOIS avisos ao mesmo tempo:
// o overlay "Abrindo o cardápio…" e um card azul "Confirmando o cardápio". A
// regra é um só narrador: a espera inteira é do aviso de navegação, que só troca
// a frase; na página fica apenas a FALHA, com "Tentar de novo".
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'
import { createError, setResponseHeader } from 'h3'
import MenuPage from '~/pages/menu.vue'
import { usePageContentPendingCount, usePageContentWaitCopy } from '~/composables/usePageContentPending'
import type { CatalogStructureState, ContinuumSnapshot } from '~/types/continuum'

function structureSnapshot (): ContinuumSnapshot<CatalogStructureState> {
  return {
    specversion: '1.0',
    id: 'evt-1',
    source: 'urn:shopman:storefront:catalog-structure',
    type: 'continuum.projection.snapshot.v0.2',
    subject: 'stream/s_shopman_storefront_catalog_structure_v1',
    time: '2026-10-02T12:00:00.000Z',
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
        cursor: { epoch: 'epoch-1', sequence: '00000000000000000001' },
        state_token: 'token-1',
        state_digest: 'sha256-digest-1'
      },
      freshness: { fresh_for_ms: 30_000, stale_if_error_ms: 120_000, age_ms: 0 },
      state: {
        items: {
          PAO: {
            sku: 'PAO',
            slug: 'pao',
            name: 'Pão',
            short_description: 'Fermentação natural',
            image_url: null,
            category: 'Pães',
            tags: [],
            search_terms: ['pao'],
            dietary_info: [],
            is_new: false,
            unit_weight_label: '500 g',
            allergens: [],
            category_color: null,
            category_icon: null
          }
        },
        item_order: ['PAO'],
        categories: [],
        sections: [{ ref: 'paes', label: 'Pães', icon: 'wheat', description: '', category: null, skus: ['PAO'] }],
        has_items: true
      },
      reset_reason: 'bootstrap'
    }
  } as ContinuumSnapshot<CatalogStructureState>
}

// O cardápio canônico (preço e disponibilidade): segura ou falha, por teste.
let canonical: 'hold' | 'fail' = 'hold'
// Sem ETag o Continuum recusa o snapshot (`continuum_missing_etag`).
registerEndpoint('/api/v1/storefront/continuum/v0.2/catalog-structure/', (event) => {
  setResponseHeader(event, 'etag', '"structure-1"')
  return structureSnapshot()
})
registerEndpoint('/api/v1/storefront/catalog/', () => {
  if (canonical === 'fail') throw createError({ statusCode: 500 })
  return new Promise(() => {})
})

const mounted: Array<{ unmount: () => void }> = []

async function openMenu () {
  clearNuxtData()
  const page = await mountSuspended(MenuPage)
  mounted.push(page)
  await flushPromises()
  await nextTick()
  return page
}

describe('/menu com o Continuum ligado: um só aviso de espera', () => {
  beforeEach(() => {
    useRuntimeConfig().public.continuumCatalogEnabled = true
  })

  afterEach(() => {
    while (mounted.length) mounted.pop()!.unmount()
    useRuntimeConfig().public.continuumCatalogEnabled = false
    usePageContentPendingCount().value = 0
    usePageContentWaitCopy().value = null
  })

  it('confirmando preços: a página não abre aviso próprio; o aviso de navegação narra', async () => {
    canonical = 'hold'
    const page = await openMenu()

    // A vitrine já está na tela (estrutura do Continuum)...
    expect(page.text()).toContain('Pão')
    // ...e nenhum segundo aviso na página.
    expect(page.find('[data-continuum-catalog-status]').exists()).toBe(false)
    expect(page.text()).not.toContain('Confirmando o cardápio')
    // A espera segue declarada ao NavigationFeedback, com a frase da fase.
    expect(usePageContentPendingCount().value).toBe(1)
    expect(usePageContentWaitCopy().value?.title).toBe('Confirmando preços e disponibilidade…')
  })

  it('a falha da confirmação fica na página, com "Tentar de novo", e solta o aviso', async () => {
    canonical = 'fail'
    const page = await openMenu()

    const status = page.get('[data-continuum-catalog-status]')
    expect(status.text()).toContain('A vitrine está aberta')
    expect(status.text()).toContain('Tentar de novo')
    expect(usePageContentPendingCount().value).toBe(0)
    expect(usePageContentWaitCopy().value).toBeNull()
  })
})
