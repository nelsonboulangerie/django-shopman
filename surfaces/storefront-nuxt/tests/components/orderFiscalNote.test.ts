import { describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'

import OrderFiscalNote from '~/components/OrderFiscalNote.vue'
import type { FiscalNote } from '~/types/shopman'

// A nota da loja online chega DIGITAL, na página do pedido (decisão do dono,
// 25/09/2026): link para abrir e a chave para conferir na SEFAZ.

const note: FiscalNote = {
  title: 'Nota fiscal',
  number_display: 'NFC-e nº 123',
  access_key_display: '4125 0912 3456 7800 0199 6500 1000 0001 2310 0000 1234',
  url: 'https://api.focusnfe.com.br/notas_fiscais_consumidor/NFe123.html',
  link_label: 'Abrir a nota fiscal',
  note: ''
}

describe('OrderFiscalNote', () => {
  it('abre a nota numa aba nova e mostra a chave de acesso', async () => {
    const wrapper = await mountSuspended(OrderFiscalNote, { props: { note } })
    const link = wrapper.find('[data-order-fiscal-note-link]')
    expect(link.text()).toContain('Abrir a nota fiscal')
    expect(link.attributes('href')).toBe(note.url)
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
    expect(wrapper.text()).toContain('NFC-e nº 123')
    expect(wrapper.find('[data-order-fiscal-note-key]').text()).toBe(note.access_key_display)
    expect(wrapper.find('[data-order-fiscal-note-status]').exists()).toBe(false)
  })

  it('nota de teste diz que não vale', async () => {
    const wrapper = await mountSuspended(OrderFiscalNote, {
      props: { note: { ...note, note: 'Nota de teste, sem valor fiscal.' } }
    })
    expect(wrapper.find('[data-order-fiscal-note-status]').text()).toBe('Nota de teste, sem valor fiscal.')
  })

  it('nota cancelada não oferece o link', async () => {
    const wrapper = await mountSuspended(OrderFiscalNote, {
      props: { note: { ...note, url: '', link_label: '', note: 'Esta nota foi cancelada e não vale mais.' } }
    })
    expect(wrapper.find('[data-order-fiscal-note-link]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Esta nota foi cancelada e não vale mais.')
  })
})
