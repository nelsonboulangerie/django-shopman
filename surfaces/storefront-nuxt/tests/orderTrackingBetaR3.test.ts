import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  EXPIRY_RECONCILE_MAX_ATTEMPTS,
  paymentDeadlineLapsed,
  shouldRetryExpiryReconcile,
  showsTrackingSkeleton,
  timelineStepSrSuffix,
} from '~/presentation/orderTracking'

// Acompanhamento do pedido: achados da 3a rodada do beta (06/11/2026).

const page = readFileSync(join(process.cwd(), 'app/pages/pedido/[ref]/index.vue'), 'utf8')

describe('SMS-12: o painel não vira esqueleto a cada atualização', () => {
  it('esqueleto só na primeira carga', () => {
    expect(showsTrackingSkeleton(true, false)).toBe(true)
    expect(showsTrackingSkeleton(true, true)).toBe(false)
    expect(showsTrackingSkeleton(false, false)).toBe(false)
  })

  it('a página não condiciona o conteúdo ao pending cru', () => {
    expect(page).not.toMatch(/v-if="pending"/)
    expect(page).not.toMatch(/usePageContentPending\(pending\)/)
  })
})

describe('PIXEXP-04: Pix vencido sai da tela antes de o servidor cancelar', () => {
  it('prazo de pagar zerado com pedido ativo some com o QR', () => {
    expect(paymentDeadlineLapsed({ deadline_kind: 'payment' }, true, true)).toBe(true)
  })

  it('não confunde com o relógio de confirmação da loja nem com pedido já encerrado', () => {
    expect(paymentDeadlineLapsed({ deadline_kind: 'availability' }, true, true)).toBe(false)
    expect(paymentDeadlineLapsed({ deadline_kind: 'payment' }, false, true)).toBe(false)
    expect(paymentDeadlineLapsed({ deadline_kind: 'payment' }, true, false)).toBe(false)
  })

  it('a ponte insiste até o servidor trazer o cancelamento, com teto', () => {
    expect(shouldRetryExpiryReconcile(1, true)).toBe(true)
    expect(shouldRetryExpiryReconcile(EXPIRY_RECONCILE_MAX_ATTEMPTS, true)).toBe(false)
    expect(shouldRetryExpiryReconcile(1, false)).toBe(false)
  })

  it('o bloco de pagamento e o cancelar obedecem ao prazo vencido', () => {
    expect(page).toMatch(/if \(paymentLapsed\.value\) return false/)
    expect(page).toMatch(/const cancelAction = computed\(\(\) => paymentLapsed\.value/)
    expect(page).toContain('O Pix venceu. Não pague este código.')
  })
})

describe('PIXEXP-10: leitor de tela não repete "cancelado"', () => {
  it('passo cancelado não ganha sufixo de estado', () => {
    expect(timelineStepSrSuffix({ key: 'cancelled', state: 'cancelled' })).toBe('')
    expect(timelineStepSrSuffix({ key: 'received', state: 'completed' })).toBe(', concluído')
  })
})

describe('PIXEXP-02 e F5: o dinheiro vem antes do convite para pedir de novo', () => {
  it('a frase do dinheiro substitui o "Reembolso: Reembolso concluído"', () => {
    expect(page).toContain('tracking.cancellation_money_line')
    expect(page).not.toContain('refund_status_label')
    expect(page.indexOf('data-cancellation-info')).toBeLessThan(page.indexOf('tracking.promise.footnote'))
  })

  it('o diálogo de cancelar diz o que acontece com o dinheiro', () => {
    expect(page).toContain('cancel_dialog_money_line')
    expect(page).toContain('<UiAlertDialogDescription>{{ cancelDialogDescription }}</UiAlertDialogDescription>')
  })
})


describe('Concluído não é anunciado como em andamento', () => {
  it('o passo terminal já nomeia sua conclusão, mesmo sendo o status atual da projeção', () => {
    expect(timelineStepSrSuffix({ key: 'completed', state: 'current' })).toBe('')
    expect(timelineStepSrSuffix({ key: 'completed', state: 'pending' })).toBe(', ainda não')
    expect(timelineStepSrSuffix({ key: 'completed', state: 'completed' })).toBe('')
    expect(timelineStepSrSuffix({ key: 'preparing', state: 'current' })).toBe(', em andamento')
  })
})
