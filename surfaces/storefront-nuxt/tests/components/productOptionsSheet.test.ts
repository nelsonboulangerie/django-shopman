// Folha de escolhas do produto (Fase 1): título = produto, um bloco por grupo com
// a regra em palavras, opção fora com "Indisponível", preço ao vivo, "Adicionar"
// só com os mínimos e o POST da linha só com {group, ref}. E o card de produto
// com escolhas abre a folha em vez de mandar o PUT por SKU.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import ProductOptionsSheet from '~/components/ProductOptionsSheet.vue'
import CartQuantityAction from '~/components/CartQuantityAction.vue'
import type { ProductMutationMeta, ProductOptionGroup } from '~/types/shopman'

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return fn
})

const meta: ProductMutationMeta = {
  sku: 'CQMO',
  name: 'Croque Monsieur',
  price_q: 3200,
  price_display: 'R$ 32,00',
  image_url: null
}

const groups: ProductOptionGroup[] = [
  {
    ref: 'sabor',
    label: 'Sabor',
    min: 1,
    max: 1,
    options: [
      { ref: 'tradicional', label: 'Tradicional', price_q: 0, available: true },
      { ref: 'trufado', label: 'Trufado', price_q: 0, available: true }
    ]
  },
  {
    ref: 'adicionais',
    label: 'Adicionais',
    min: 0,
    max: 2,
    options: [
      { ref: 'ovo', label: 'Ovo frito', price_q: 400, available: true },
      { ref: 'salada', label: 'Salada', price_q: 300, available: false }
    ]
  }
]

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

function q<T extends Element = HTMLElement> (selector: string): T {
  const element = document.body.querySelector<T>(selector)
  if (!element) throw new Error(`não achei ${selector}`)
  return element
}

describe('ProductOptionsSheet', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    document.body.innerHTML = ''
    fetchMock.mockReset()
  })

  it('mostra os grupos com a regra, a opção fora como Indisponível e o preço da opção', async () => {
    await mountSuspended(ProductOptionsSheet, { props: { open: true, meta, optionGroups: groups } })
    await nextTick()

    const body = document.body.textContent || ''
    expect(body).toContain('Croque Monsieur')
    expect(q('[data-product-option-group="sabor"] [data-product-option-rule]').textContent).toBe('Escolha 1')
    expect(q('[data-product-option-group="adicionais"] [data-product-option-rule]').textContent).toBe('Opcional, até 2')
    expect(q('[data-product-option="ovo"]').textContent).toContain('+ R$ 4,00')
    expect(q('[data-product-option="salada"]').textContent).toContain('Indisponível')
    expect(q<HTMLButtonElement>('[data-product-option="salada"]').disabled).toBe(true)
    expect(body).not.toMatch(/[—–]/)
  })

  it('"Adicionar" só acende com o mínimo; o preço soma as escolhas; o POST leva só {group, ref}', async () => {
    fetchMock.mockResolvedValue({ cart: { items: [], items_count: 1, is_empty: false } })
    const wrapper = await mountSuspended(ProductOptionsSheet, { props: { open: true, meta, optionGroups: groups } })
    await nextTick()

    const add = q<HTMLButtonElement>('[data-product-options-add]')
    expect(add.disabled).toBe(true)
    expect(q('[data-product-options-missing]').textContent).toContain('Escolha 1 em Sabor')
    expect(q('[data-product-options-total]').textContent).toContain('R$ 32,00')

    q<HTMLButtonElement>('[data-product-option="trufado"]').click()
    q<HTMLButtonElement>('[data-product-option="ovo"]').click()
    await nextTick()
    expect(q('[data-product-options-total]').textContent).toContain('R$ 36,00')
    expect(q<HTMLButtonElement>('[data-product-options-add]').disabled).toBe(false)

    q<HTMLButtonElement>('[data-product-options-add]').click()
    await flush()

    const [url, options] = fetchMock.mock.calls[0]!
    expect(String(url)).toContain('/api/v1/cart/lines/')
    expect(options).toMatchObject({
      method: 'POST',
      body: { sku: 'CQMO', qty: 1, options: [{ group: 'sabor', ref: 'trufado' }, { group: 'adicionais', ref: 'ovo' }] }
    })
    expect(wrapper.emitted('update:open')?.at(-1)).toEqual([false])
  })

  it('escolha recusada pelo servidor (400) mostra o detail na folha, que continua aberta', async () => {
    fetchMock
      .mockRejectedValueOnce(Object.assign(new Error('HTTP 400'), {
        response: { status: 400 },
        data: { detail: 'O Trufado acabou de sair. Escolha outro sabor.', error_code: 'option_unavailable', field: 'options' }
      }))
      .mockResolvedValueOnce({ cart: { items: [], items_count: 0, is_empty: true } })
    const wrapper = await mountSuspended(ProductOptionsSheet, { props: { open: true, meta, optionGroups: groups } })
    await nextTick()

    q<HTMLButtonElement>('[data-product-option="trufado"]').click()
    await nextTick()
    q<HTMLButtonElement>('[data-product-options-add]').click()
    await flush()
    await flush()

    expect(q('[data-product-options-error]').textContent).toContain('O Trufado acabou de sair.')
    expect(wrapper.emitted('update:open')).toBeUndefined()
  })
})

describe('CartQuantityAction com escolhas', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    document.body.innerHTML = ''
    fetchMock.mockReset()
  })

  it('o toque em "Adicionar" abre a folha e não manda o PUT por SKU', async () => {
    const wrapper = await mountSuspended(CartQuantityAction, { props: { meta, qty: 0, optionGroups: groups } })

    await wrapper.get('button').trigger('click')
    await flush()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(document.body.querySelector('[data-product-options-sheet]')).not.toBeNull()
  })

  it('com o item na sacola segue o botão (nunca a pílula de quantidade)', async () => {
    const wrapper = await mountSuspended(CartQuantityAction, { props: { meta, qty: 2, optionGroups: groups } })

    expect(wrapper.find('[data-quantity-increase]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Adicionar')
  })
})
