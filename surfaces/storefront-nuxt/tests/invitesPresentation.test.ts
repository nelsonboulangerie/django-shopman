import { describe, expect, it } from 'vitest'
import { isShopInviteRouteExcluded } from '../app/presentation/invites'

// Decisão 3 do plano de excelência da loja (16/11/2026): convite só depois do
// pedido enviado. Nada no caminho da compra nem nas portas de entrada; uma lista
// só para os dois convites (P2-05).
describe('isShopInviteRouteExcluded', () => {
  it.each([
    '/entrar', '/entrar/', '/a', '/a/TOKEN',
    '/produto/croissant', '/sacola', '/finalizar', '/finalizar/endereco',
    '/pedido/NB-123', '/pedido/NB-123/pagamento'
  ])('nenhum convite em %s', path => {
    expect(isShopInviteRouteExcluded(path)).toBe(true)
  })

  it.each(['/', '/menu', '/conta', '/conta/preferencias', '/conta/pedidos', '/pedidos', '/produtos-da-casa'])(
    'o convite pode subir em %s',
    path => {
      expect(isShopInviteRouteExcluded(path)).toBe(false)
    }
  )
})
