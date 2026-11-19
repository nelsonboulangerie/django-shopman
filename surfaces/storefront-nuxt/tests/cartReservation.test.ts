import { describe, expect, it } from 'vitest'
import { cartReservationNotice, reservationDeadlineMs } from '~/presentation/cart'
import { serverClockOffsetMs } from '~/presentation/deadline'

// Reserva com prazo à vista (WP-L11): a sacola diz até quando guarda os itens. A
// hora vem pronta do servidor, e o prazo é contado pelo relógio dele.

const SERVER_NOW = '2026-11-19T19:00:00-03:00'
const serverNowMs = Date.parse(SERVER_NOW)

function cart (overrides: Partial<Parameters<typeof cartReservationNotice>[0]> = {}) {
  return {
    is_empty: false,
    reserved_until_iso: '2026-11-19T19:18:00-03:00',
    reserved_until_display: '19h18',
    ...overrides
  }
}

describe('cartReservationNotice', () => {
  it('diz até quando guarda os itens, com a hora no formato da casa', () => {
    expect(cartReservationNotice(cart(), serverNowMs)).toEqual({
      kind: 'held',
      text: 'Guardamos seus itens até 19h18.'
    })
  })

  it('a frase não tem travessão, nem "carrinho", nem hora com dois-pontos', () => {
    const held = cartReservationNotice(cart(), serverNowMs)!.text
    const lapsed = cartReservationNotice(cart(), serverNowMs + 60 * 60_000)!.text
    for (const text of [held, lapsed]) {
      expect(text).not.toMatch(/[—–]/)
      expect(text).not.toMatch(/carrinho/i)
      expect(text).not.toMatch(/\d:\d/)
    }
  })

  it('sacola vazia não promete hora', () => {
    expect(cartReservationNotice(cart({ is_empty: true }), serverNowMs)).toBeNull()
  })

  it('sem reserva com prazo (só fornada futura), nenhuma linha', () => {
    expect(cartReservationNotice(cart({ reserved_until_iso: null, reserved_until_display: null }), serverNowMs)).toBeNull()
  })

  it('prazo ilegível não vira promessa', () => {
    expect(reservationDeadlineMs({ reserved_until_iso: 'amanhã cedo' })).toBeNull()
    expect(cartReservationNotice(cart({ reserved_until_iso: 'amanhã cedo' }), serverNowMs)).toBeNull()
  })

  it('quando o prazo passa, a frase conta o que houve', () => {
    const afterDeadline = Date.parse('2026-11-19T19:18:01-03:00')
    expect(cartReservationNotice(cart(), afterDeadline)).toEqual({
      kind: 'lapsed',
      text: 'A reserva valia até 19h18 e já venceu. A sacola mostra o que continua disponível.'
    })
  })

  it('depois de relida a sacola, a frase continua com a hora que a tela guardou', () => {
    const reread = cart({ reserved_until_iso: null, reserved_until_display: null })
    expect(cartReservationNotice(reread, serverNowMs + 20 * 60_000, '19h18')).toEqual({
      kind: 'lapsed',
      text: 'A reserva valia até 19h18 e já venceu. A sacola mostra o que continua disponível.'
    })
  })

  it('um gesto reserva de novo: a hora nova vence a frase do prazo vencido', () => {
    const renewed = cart({ reserved_until_iso: '2026-11-19T19:50:00-03:00', reserved_until_display: '19h50' })
    expect(cartReservationNotice(renewed, Date.parse('2026-11-19T19:20:00-03:00'), '19h18')).toEqual({
      kind: 'held',
      text: 'Guardamos seus itens até 19h50.'
    })
  })

  it('o prazo é contado pelo relógio do servidor, não pelo do aparelho', () => {
    // O aparelho está 40 minutos adiantado: por ele, o prazo das 19h18 já passou.
    const deviceNowMs = serverNowMs + 40 * 60_000
    const offset = serverClockOffsetMs(SERVER_NOW, deviceNowMs)

    expect(cartReservationNotice(cart(), deviceNowMs)?.kind).toBe('lapsed')
    expect(cartReservationNotice(cart(), deviceNowMs + offset)?.kind).toBe('held')
  })

  it('antes de a tela ter relógio, o prazo que veio com a sacola vale como está', () => {
    // No servidor e na hidratação o agora da tela é 0: a frase não some nem vence.
    expect(cartReservationNotice(cart(), 0)?.kind).toBe('held')
  })

  it('o mesmo prazo não é dito duas vezes na tela', () => {
    // O aviso "Tudo pronto! Confirme até 19h18" já diz esse prazo.
    expect(cartReservationNotice(cart(), serverNowMs, null, '2026-11-19T19:18:00-03:00')).toBeNull()
    // Prazo diferente do aviso: a reserva comum vence antes, e a tela diz.
    expect(cartReservationNotice(cart(), serverNowMs, null, '2026-11-19T19:40:00-03:00')?.kind).toBe('held')
  })
})
