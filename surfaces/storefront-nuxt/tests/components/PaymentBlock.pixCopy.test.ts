// U4 (laudo 23/10): copiar o Pix copia e cola não pode virar botão morto.
// Sucesso diz que copiou; falha da Clipboard API cai no plano B, com o código
// INTEIRO selecionado num campo somente leitura e a instrução de como copiar.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'

import PaymentBlock from '~/components/PaymentBlock.vue'
import type { TrackingCopyProjection, TrackingPromiseProjection } from '~/types/shopman'

const CODE = '00020101021226870014br.gov.bcb.pix2565qrcodes.exemplo.com/v2/cobv/9d36b84fc70b478fb95c12729b90ca25520400005303986540510.005802BR5913NELSON BOULAN6008LONDRINA62070503***6304ABCD'

const promise = {
  payment_method: 'pix',
  payment_method_label: 'Pix',
  pix_qr_code: null,
  pix_copy_paste: CODE,
  checkout_url: null
} as TrackingPromiseProjection

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

function mount () {
  return mountSuspended(PaymentBlock, {
    props: { promise, copy, totalDisplay: 'R$ 10,00', mockEnabled: false, mockPending: false }
  })
}

function setClipboard (writeText: ((text: string) => Promise<void>) | undefined) {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: writeText ? { writeText } : undefined
  })
}

describe('PaymentBlock — Pix copia e cola', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    setClipboard(undefined)
  })

  it('mostra o código inteiro num campo somente leitura (sem reticências)', async () => {
    const wrapper = await mount()
    const field = wrapper.find('[data-pix-copy-field]')
    expect(field.exists()).toBe(true)
    expect(field.element.tagName).toBe('TEXTAREA')
    expect((field.element as HTMLTextAreaElement).value).toBe(CODE)
    expect(field.attributes('readonly')).toBeDefined()
    expect(field.classes()).not.toContain('truncate')
  })

  it('copiou: confirma no botão e no aviso', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    setClipboard(writeText)
    const wrapper = await mount()

    await wrapper.find('[data-pix-copy-button]').trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith(CODE)
    expect(wrapper.find('[data-pix-copy-button]').text()).toBe('Copiado')
    expect(wrapper.find('[data-pix-copy-fallback]').exists()).toBe(false)
  })

  it('Clipboard API recusou: não lança, seleciona o código e diz como copiar', async () => {
    setClipboard(vi.fn().mockRejectedValue(new DOMException('denied', 'NotAllowedError')))
    const execCommand = vi.fn().mockReturnValue(false)
    Object.defineProperty(document, 'execCommand', { configurable: true, value: execCommand })
    const wrapper = await mount()

    await wrapper.find('[data-pix-copy-button]').trigger('click')
    await flushPromises()

    const fallback = wrapper.find('[data-pix-copy-fallback]')
    expect(fallback.exists()).toBe(true)
    expect(fallback.text()).toContain('toque e segure')
    const field = wrapper.find('[data-pix-copy-field]').element as HTMLTextAreaElement
    expect(field.selectionStart).toBe(0)
    expect(field.selectionEnd).toBe(CODE.length)
    expect(wrapper.find('[data-pix-copy-button]').text()).toBe('Copiar código')
  })

  it('sem Clipboard API (navegador embutido): tenta o copiar do navegador', async () => {
    setClipboard(undefined)
    const execCommand = vi.fn().mockReturnValue(true)
    Object.defineProperty(document, 'execCommand', { configurable: true, value: execCommand })
    const wrapper = await mount()

    await wrapper.find('[data-pix-copy-button]').trigger('click')
    await flushPromises()

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(wrapper.find('[data-pix-copy-button]').text()).toBe('Copiado')
  })
})
