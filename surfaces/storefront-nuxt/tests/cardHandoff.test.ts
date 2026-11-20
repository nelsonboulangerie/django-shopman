// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from 'vitest'
import { markCardHandoff, takeCardHandoff } from '~/utils/cardHandoff'

// Cartão em um toque (WP-L05, P2-09): a marca do checkout leva ao pagamento UMA vez,
// só para o pedido que acabou de ser enviado, e vence em minutos.
describe('cardHandoff', () => {
  beforeEach(() => { window.sessionStorage.clear() })

  it('o acompanhamento consome a marca do pedido recém-enviado uma vez só', () => {
    markCardHandoff('WEB-1', 1_000)
    expect(takeCardHandoff('WEB-1', 2_000)).toBe(true)
    expect(takeCardHandoff('WEB-1', 3_000)).toBe(false)
  })

  it('outro pedido não consome a marca', () => {
    markCardHandoff('WEB-1', 1_000)
    expect(takeCardHandoff('WEB-2', 2_000)).toBe(false)
    expect(takeCardHandoff('WEB-1', 2_000)).toBe(true)
  })

  it('marca velha não leva ninguém a lugar nenhum, e é apagada', () => {
    markCardHandoff('WEB-1', 1_000)
    expect(takeCardHandoff('WEB-1', 1_000 + 3 * 60_000 + 1)).toBe(false)
    expect(takeCardHandoff('WEB-1', 2_000)).toBe(false)
  })

  it('sem marca, sem pedido ou com lixo no armazenamento: nada', () => {
    expect(takeCardHandoff('WEB-1')).toBe(false)
    expect(takeCardHandoff('')).toBe(false)
    window.sessionStorage.setItem('shopman-card-handoff', 'não é json')
    expect(takeCardHandoff('WEB-1')).toBe(false)
  })
})
