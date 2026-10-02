// Observação por item na sacola: o editor é a folha canônica da loja. Fecha por
// X, fundo e Esc sem exigir salvar; texto novo segue no MESMO PUT da linha
// (`/cart/lines/<line_id>/notes/`) em segundo plano; erro de rede reabre com o
// rascunho e o aviso; remover é PUT com notes vazio; descartar o que foi escrito
// pede confirmação só quando difere do salvo. O item com observação ganha selo
// + uma linha, a mesma marca que a revisão da finalização usa.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import CartLineNote from '~/components/CartLineNote.vue'
import CartLineNoteMark from '~/components/CartLineNoteMark.vue'
import { lineNoteCloseIntent } from '~/presentation/cart'
import type { CartItemProjection } from '~/types/shopman'

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return fn
})

function line (overrides: Partial<CartItemProjection> = {}): CartItemProjection {
  return {
    line_id: 'L-1',
    sku: 'PAO-GERGELIM',
    name: 'Pão de gergelim',
    qty: 2,
    unit_price_q: 900,
    total_price_q: 1800,
    price_display: 'R$ 9,00',
    total_display: 'R$ 18,00',
    image_url: null,
    original_price_display: null,
    discount_label: null,
    is_available: true,
    availability_warning: null,
    available_qty: null,
    is_notifiable: false,
    is_notify_subscribed: false,
    is_made_to_order: false,
    made_to_order_label: '',
    is_awaiting_confirmation: false,
    is_ready_for_confirmation: false,
    confirmation_deadline_iso: null,
    confirmation_deadline_display: null,
    planned_for_date: null,
    planned_for_notice: null,
    notes: '',
    ...overrides
  }
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

function find<T extends Element = HTMLElement> (selector: string): T | null {
  return document.body.querySelector<T>(selector)
}
function q<T extends Element = HTMLElement> (selector: string): T {
  const element = find<T>(selector)
  if (!element) throw new Error(`não achei ${selector}`)
  return element
}
function click (selector: string) {
  q<HTMLElement>(selector).click()
}
async function type (value: string) {
  const input = q<HTMLTextAreaElement>('[data-cart-line-note-input]')
  input.value = value
  input.dispatchEvent(new Event('input'))
  await nextTick()
}
// Esc no conteúdo E no documento: dois avisos de fechar para o mesmo gesto, o
// que também prova que a folha não grava duas vezes.
async function pressEscape () {
  q('[data-cart-line-note-sheet]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await flush()
  await nextTick()
}
// A folha vive num portal e entra na pilha de camadas do Reka: componente que
// sobra de um teste continua ouvindo o Esc do seguinte. Desmonta tudo no fim.
const mounted: Array<{ unmount: () => void }> = []
async function mountNote (props: { line: CartItemProjection }) {
  const wrapper = await mountSuspended(CartLineNote, { props })
  mounted.push(wrapper)
  return wrapper
}
async function openSheet (props: { line: CartItemProjection }) {
  const wrapper = await mountNote(props)
  await wrapper.get('[data-cart-line-note-open]').trigger('click')
  await flush()
  await nextTick()
  return wrapper
}
function putCalls () {
  return fetchMock.mock.calls.filter(([url]) => String(url).includes('/notes/'))
}

describe('CartLineNote', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    document.body.innerHTML = ''
    fetchMock.mockReset()
  })
  afterEach(async () => {
    while (mounted.length) mounted.pop()!.unmount()
    await flush()
  })

  it('abre a folha com o nome do item, campo de 280 e contador anunciado', async () => {
    await openSheet({ line: line() })

    const sheet = q('[data-cart-line-note-sheet]')
    expect(sheet.textContent).toContain('Observação de Pão de gergelim')
    expect(sheet.textContent).not.toMatch(/[—–]/)
    expect(q('[data-cart-line-note-input]').getAttribute('maxlength')).toBe('280')
    await type('sem gergelim')
    const count = q('[data-cart-line-note-count]')
    expect(count.getAttribute('aria-live')).toBe('polite')
    expect(count.textContent?.trim()).toBe('12/280')
    // Sem observação salva, não há o que remover.
    expect(find('[data-cart-line-note-remove]')).toBeNull()
  })

  it('salvar grava pela line_id e fecha quando o servidor confirma', async () => {
    fetchMock.mockResolvedValue({ cart: { items: [line({ notes: 'sem gergelim' })] } })
    await openSheet({ line: line() })

    await type('  sem gergelim  ')
    click('[data-cart-line-note-save]')
    await flush()
    await nextTick()

    expect(putCalls()).toHaveLength(1)
    expect(String(putCalls()[0]![0])).toContain('/api/v1/cart/lines/L-1/notes/')
    expect(putCalls()[0]![1]).toMatchObject({ method: 'PUT', body: { notes: 'sem gergelim' } })
    expect(find('[data-cart-line-note-sheet]')).toBeNull()
  })

  it('fechar por Esc com texto novo fecha na hora e grava no mesmo PUT em segundo plano', async () => {
    let resolvePut!: (value: unknown) => void
    fetchMock.mockImplementation(() => new Promise(resolve => { resolvePut = resolve }))
    const wrapper = await openSheet({ line: line({ line_id: 'L-2' }) })

    await type('bem assado')
    await pressEscape()

    // Fechou antes da resposta, e a linha já mostra o que foi escrito.
    expect(find('[data-cart-line-note-sheet]')).toBeNull()
    expect(wrapper.get('[data-cart-line-note-text]').text()).toBe('bem assado')
    expect(putCalls()).toHaveLength(1)
    expect(String(putCalls()[0]![0])).toContain('/api/v1/cart/lines/L-2/notes/')
    expect(putCalls()[0]![1]).toMatchObject({ method: 'PUT', body: { notes: 'bem assado' } })

    resolvePut({ cart: { items: [line({ line_id: 'L-2', notes: 'bem assado' })] } })
    await flush()
    // Um segundo gesto de fechar não grava de novo.
    expect(putCalls()).toHaveLength(1)
    expect(find('[data-cart-line-note-sheet]')).toBeNull()
  })

  it('fechar sem alteração não chama o servidor', async () => {
    await openSheet({ line: line({ notes: 'bem assado' }) })

    await pressEscape()

    expect(find('[data-cart-line-note-sheet]')).toBeNull()
    expect(putCalls()).toHaveLength(0)
  })

  it('erro de rede ao gravar em segundo plano reabre a folha com o rascunho e o aviso', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const wrapper = await openSheet({ line: line() })

    await type('sem cebola')
    await pressEscape()
    // O retry com backoff da sacola esgota antes de desistir.
    await vi.waitFor(() => expect(find('[data-cart-line-note-error]')).not.toBeNull(), { timeout: 5000 })
    await nextTick()

    expect(q('[data-cart-line-note-error]').getAttribute('role')).toBe('alert')
    expect(q<HTMLTextAreaElement>('[data-cart-line-note-input]').value).toBe('sem cebola')
    // Não ficou marca de uma observação que o servidor não guardou.
    expect(wrapper.find('[data-cart-line-note-text]').exists()).toBe(false)
  })

  it('remover observação manda o PUT da linha com notes vazio', async () => {
    fetchMock.mockResolvedValue({ cart: { items: [line({ notes: '' })] } })
    await openSheet({ line: line({ notes: 'bem assado' }) })

    click('[data-cart-line-note-remove]')
    await flush()
    await nextTick()

    expect(putCalls()).toHaveLength(1)
    expect(String(putCalls()[0]![0])).toContain('/api/v1/cart/lines/L-1/notes/')
    expect(putCalls()[0]![1]).toMatchObject({ method: 'PUT', body: { notes: '' } })
    expect(find('[data-cart-line-note-sheet]')).toBeNull()
  })

  it('cancelar só pede confirmação quando o texto difere do salvo', async () => {
    await openSheet({ line: line({ notes: 'bem assado' }) })

    click('[data-cart-line-note-cancel]')
    await flush()
    await nextTick()
    expect(find('[data-cart-line-note-sheet]')).toBeNull()

    mounted.pop()!.unmount()
    await openSheet({ line: line({ notes: 'bem assado' }) })
    await type('bem assado e sem gergelim')
    click('[data-cart-line-note-cancel]')
    await nextTick()
    expect(q('[data-cart-line-note-discard]').textContent).toContain('Descartar o que você escreveu?')

    click('[data-cart-line-note-discard-confirm]')
    await flush()
    await nextTick()
    expect(find('[data-cart-line-note-sheet]')).toBeNull()
    expect(putCalls()).toHaveLength(0)
  })

  it('o item com observação ganha selo e uma linha, com o convite para alterar', async () => {
    const wrapper = await mountNote({ line: line({ notes: 'bem assado' }) })

    expect(wrapper.get('[data-cart-line-note-mark]').text()).toContain('Com observação')
    expect(wrapper.get('[data-cart-line-note-text]').text()).toBe('bem assado')
    expect(wrapper.get('[data-cart-line-note-open]').attributes('aria-label')).toBe('Alterar a observação de Pão de gergelim')
  })

  it('a revisão da finalização usa a mesma marca da sacola', async () => {
    const mark = await mountSuspended(CartLineNoteMark, { props: { notes: 'sem gergelim' } })
    expect(mark.get('[data-cart-line-note-text]').text()).toBe('sem gergelim')
    expect(mark.html()).toContain('Com observação')

    const { readFileSync } = await import('node:fs')
    const { resolve } = await import('node:path')
    const checkout = readFileSync(resolve(__dirname, '../../app/pages/finalizar.vue'), 'utf8')
    expect(checkout).toContain('<CartLineNoteMark v-if="line.notes" :notes="line.notes"')
    expect(checkout).not.toContain('Obs.: {{ line.notes }}')
  })

  it('não oferece observação numa linha que ainda não chegou ao servidor', async () => {
    const wrapper = await mountNote({ line: line({ line_id: 'optimistic-PAO-GERGELIM' }) })

    expect(wrapper.find('[data-cart-line-note]').exists()).toBe(false)
  })
})

describe('lineNoteCloseIntent', () => {
  it('sem alteração só fecha; texto novo grava; texto apagado pergunta', () => {
    expect(lineNoteCloseIntent('bem assado ', 'bem assado')).toBe('close')
    expect(lineNoteCloseIntent('', '')).toBe('close')
    expect(lineNoteCloseIntent('sem gergelim', 'bem assado')).toBe('save')
    expect(lineNoteCloseIntent('sem gergelim', null)).toBe('save')
    expect(lineNoteCloseIntent('   ', 'bem assado')).toBe('confirm-discard')
  })
})
