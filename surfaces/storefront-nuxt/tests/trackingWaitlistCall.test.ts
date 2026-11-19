import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// Quando a loja chama a cliente da fila (#2771), o chamado é a frase principal do
// painel do acompanhamento (título e mensagem da promessa, vindos do servidor). O
// cartão da fila, logo abaixo, fica só com o relógio e o botão. Antes o cartão
// repetia o chamado com outras palavras, e a frase principal mandava esperar.

const page = readFileSync(join(process.cwd(), 'app/pages/pedido/[ref]/index.vue'), 'utf8')
const types = readFileSync(join(process.cwd(), 'app/types/shopman.ts'), 'utf8')

function confirmingCard () {
  const start = page.indexOf('data-waitlist="confirming"')
  const end = page.indexOf('data-waitlist="confirmed"')
  expect(start).toBeGreaterThan(0)
  expect(end).toBeGreaterThan(start)
  return page.slice(start, end)
}

describe('acompanhamento: o chamado da fila', () => {
  it('o cartão da fila tem o relógio e o botão, e não repete o chamado', () => {
    const card = confirmingCard()

    expect(card).toContain('Confirme em {{ waitlistDeadlineLeft }}')
    expect(card).toContain('tracking.copy.waitlist_confirm_cta')
    expect(card).toContain('@click="confirmWaitlistSlot"')
    expect(card).not.toContain('waitlist_confirm_title')
    expect(card).not.toContain('waitlist_confirm_message')
  })

  it('o chamado é a frase principal: título e mensagem da promessa', () => {
    expect(page).toContain('{{ tracking.promise.title || tracking.status_label }}')
    expect(page).toContain('{{ tracking.promise.message || tracking.copy.promise_fallback_message }}')
    // A frase principal vem antes do cartão da fila no painel.
    expect(page.indexOf('tracking.promise.message')).toBeLessThan(page.indexOf('data-waitlist="confirming"'))
  })

  it('o contrato da copy não carrega mais o título nem a mensagem do cartão', () => {
    expect(types).toContain('waitlist_confirm_cta: string')
    expect(types).not.toContain('waitlist_confirm_title')
    expect(types).not.toContain('waitlist_confirm_message')
  })
})
