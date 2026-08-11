import { describe, expect, it } from 'vitest'
import { orderTrackingRoute } from '../app/utils/routes'

// A tradução de rota morreu junto com os 301: o Django emite os caminhos REAIS da loja
// (`storefront_links`), então não há inglês para traduzir nem redirect para absorver.
// Sobrou o que sempre foi construção de rota, não tradução.
describe('rotas locais', () => {
  it('monta a rota de acompanhamento escapando o ref', () => {
    expect(orderTrackingRoute('ORD 123')).toBe('/pedido/ORD%20123')
    expect(orderTrackingRoute('ORD-123')).toBe('/pedido/ORD-123')
  })
})
