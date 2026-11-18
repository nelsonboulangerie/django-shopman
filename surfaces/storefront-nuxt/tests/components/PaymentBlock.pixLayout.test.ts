// WP-L07 (P1-09): no celular, copiar o código é o primeiro gesto do Pix. O QR não
// serve no próprio aparelho, então fica recolhido em "Mostrar QR Code" logo
// abaixo. No computador (md+, 768 px), o QR vem primeiro e sempre à vista.
//
// A troca é CSS (Tailwind `hidden md:flex`, `md:order-first`, `md:hidden`), para o
// SSR sair certo nas duas larguras sem piscar. O happy-dom não aplica CSS, então
// o teste resolve as classes responsivas do próprio componente para cada largura:
// `layoutAt` diz o que fica visível e em que ordem a 375 px e a 1366 px.
import { describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import type { DOMWrapper, VueWrapper } from '@vue/test-utils'

import PaymentBlock from '~/components/PaymentBlock.vue'
import type { TrackingCopyProjection, TrackingPromiseProjection } from '~/types/shopman'

const CODE = '00020101021226870014br.gov.bcb.pix2565qrcodes.exemplo.com/v2/cobv/9d36'
const QR = 'data:image/png;base64,iVBORw0KGgo='

const copy = {
  total_label: 'Total',
  pix_instruction: 'Escaneie o QR Code.',
  pix_copy_label: 'Pix copia e cola',
  pix_copy_btn: 'Copiar código',
  pix_copied: 'Código Pix copiado.',
  pix_pending_note: 'Gerando Pix.',
  pix_auto_update_note: 'Atualização automática.',
  card_intro: '',
  card_security_note: ''
} as TrackingCopyProjection

function pix (over: Partial<TrackingPromiseProjection> = {}) {
  return {
    payment_method: 'pix',
    payment_method_label: 'Pix',
    pix_qr_code: QR,
    pix_copy_paste: CODE,
    checkout_url: null,
    ...over
  } as TrackingPromiseProjection
}

function mount (promise = pix()) {
  return mountSuspended(PaymentBlock, {
    props: { promise, copy, totalDisplay: 'R$ 10,00', mockEnabled: false, mockPending: false }
  })
}

type Width = 'celular' | 'computador'
const WIDE = { celular: false, computador: true } as const

// Resolve `hidden`/`md:hidden`/`md:flex`/`md:block` de um elemento numa largura.
function hiddenAt (el: Element, width: Width): boolean {
  const cls = el.classList
  if (WIDE[width]) {
    if (cls.contains('md:hidden')) return true
    if (cls.contains('md:flex') || cls.contains('md:block')) return false
  }
  return cls.contains('hidden')
}

function visibleAt (el: Element, width: Width): boolean {
  for (let node: Element | null = el; node; node = node.parentElement) {
    if (hiddenAt(node, width)) return false
  }
  return true
}

// Ordem visual dos filhos diretos do bloco do Pix (flex-col + md:order-first).
function blockOrder (wrapper: VueWrapper, width: Width): string[] {
  const block = wrapper.find('[data-pix-block]').element
  const children = Array.from(block.children)
  const order = (el: Element) => (WIDE[width] && el.classList.contains('md:order-first') ? -1 : 0)
  return children
    .map((el, index) => ({ el, index }))
    .sort((a, b) => order(a.el) - order(b.el) || a.index - b.index)
    .map(({ el }) => (el.hasAttribute('data-pix-qr') ? 'qr' : el.hasAttribute('data-pix-copy') ? 'copiar' : 'nota'))
}

function layoutAt (wrapper: VueWrapper, width: Width) {
  const qrImage = wrapper.find('img[alt="QR Code Pix"]')
  const toggle = wrapper.find('[data-pix-qr-toggle]')
  return {
    order: blockOrder(wrapper, width),
    copyVisible: visibleAt(wrapper.find('[data-pix-copy-button]').element, width),
    qrVisible: qrImage.exists() && visibleAt(qrImage.element, width),
    toggleVisible: toggle.exists() && visibleAt(toggle.element, width)
  }
}

function text (el: DOMWrapper<Element>) {
  return el.text().replace(/\s+/g, ' ').trim()
}

describe('PaymentBlock — Pix no celular e no computador (WP-L07)', () => {
  it('celular (375 px): valor, depois "Copiar código"; o QR fica recolhido logo abaixo', async () => {
    const wrapper = await mount()
    const layout = layoutAt(wrapper, 'celular')

    expect(layout.order).toEqual(['copiar', 'qr', 'nota'])
    expect(layout.copyVisible).toBe(true)
    expect(layout.qrVisible).toBe(false)
    expect(layout.toggleVisible).toBe(true)

    // O valor vem antes do botão no cartão; o botão é o primeiro controle.
    const html = wrapper.html()
    expect(html.indexOf('R$ 10,00')).toBeLessThan(html.indexOf('data-pix-copy-button'))
    const firstButton = wrapper.find('button')
    expect(firstButton.attributes('data-pix-copy-button')).toBeDefined()
    expect(text(firstButton)).toBe('Copiar código')

    const toggle = wrapper.find('[data-pix-qr-toggle]')
    expect(text(toggle)).toBe('Mostrar QR Code')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.attributes('aria-controls')).toBe('pix-qr-code')
  })

  it('celular: um toque em "Mostrar QR Code" abre o QR, outro recolhe', async () => {
    const wrapper = await mount()

    await wrapper.find('[data-pix-qr-toggle]').trigger('click')
    expect(layoutAt(wrapper, 'celular').qrVisible).toBe(true)
    expect(text(wrapper.find('[data-pix-qr-toggle]'))).toBe('Esconder QR Code')
    expect(wrapper.find('[data-pix-qr-toggle]').attributes('aria-expanded')).toBe('true')

    await wrapper.find('[data-pix-qr-toggle]').trigger('click')
    expect(layoutAt(wrapper, 'celular').qrVisible).toBe(false)
  })

  it('computador (1366 px): o QR vem primeiro e à vista, sem o botão de mostrar', async () => {
    const wrapper = await mount()
    const layout = layoutAt(wrapper, 'computador')

    expect(layout.order).toEqual(['qr', 'copiar', 'nota'])
    expect(layout.qrVisible).toBe(true)
    expect(layout.toggleVisible).toBe(false)
    expect(layout.copyVisible).toBe(true)
  })

  it('sem copia e cola, o QR é o único caminho: à vista nas duas larguras', async () => {
    const wrapper = await mount(pix({ pix_copy_paste: null }))

    expect(wrapper.find('[data-pix-qr-toggle]').exists()).toBe(false)
    for (const width of ['celular', 'computador'] as const) {
      expect(visibleAt(wrapper.find('img[alt="QR Code Pix"]').element, width)).toBe(true)
    }
  })

  it('sem QR, nada a recolher: só o copiar', async () => {
    const wrapper = await mount(pix({ pix_qr_code: null }))

    expect(wrapper.find('[data-pix-qr]').exists()).toBe(false)
    expect(layoutAt(wrapper, 'celular').order).toEqual(['copiar', 'nota'])
  })
})
