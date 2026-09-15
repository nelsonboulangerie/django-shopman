import { describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'

import PaymentBlock from '~/components/PaymentBlock.vue'
import type { TrackingCopyProjection, TrackingPromiseProjection } from '~/types/shopman'

const promise = {
  payment_method: 'pix',
  payment_method_label: 'Pix',
  pix_qr_code: null,
  pix_copy_paste: '000201...',
  checkout_url: null
} as TrackingPromiseProjection

const copy = {
  total_label: 'Total',
  pix_instruction: 'Escaneie o QR Code.',
  pix_copy_label: 'Pix copia e cola',
  pix_copy_btn: 'Copiar',
  pix_copied: 'Copiado.',
  pix_pending_note: 'Gerando Pix.',
  pix_auto_update_note: 'Atualização automática.',
  card_intro: '',
  card_security_note: ''
} as TrackingCopyProjection

describe('PaymentBlock — Pix do provedor em teste', () => {
  it('não expõe captura simulada quando o backend não a autorizou', async () => {
    const wrapper = await mountSuspended(PaymentBlock, {
      props: { promise, copy, totalDisplay: 'R$ 10,00', mockEnabled: false, mockPending: false }
    })

    expect(wrapper.text()).toContain('Pix copia e cola')
    expect(wrapper.text()).not.toContain('Simular pagamento')
    expect(wrapper.text()).not.toContain('Pagamento de teste')
  })
})
