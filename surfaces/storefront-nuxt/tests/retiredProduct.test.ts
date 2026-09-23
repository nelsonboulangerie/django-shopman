import { describe, expect, it } from 'vitest'
import { retiredFromPayload } from '~/composables/useRetiredProduct'

const PAYLOAD = {
  redirects: { CT: 'CRO' },
  gone: {
    PU: { collection: 'doces', collection_name: 'Doces' },
    'COMBO-PETIT-DEJ': { collection: '', collection_name: '' }
  }
}

describe('retiredFromPayload', () => {
  it('encontra a lápide e a prateleira de onde o produto saiu', () => {
    expect(retiredFromPayload(PAYLOAD, 'PU')).toEqual({ collection: 'doces', collection_name: 'Doces' })
  })

  // A coleção "Combos" ficou vazia quando o combo saiu: a lápide existe, o
  // destino não. A tela cai no cardápio.
  it('devolve a lápide sem coleção quando não há prateleira viva', () => {
    expect(retiredFromPayload(PAYLOAD, 'COMBO-PETIT-DEJ')).toEqual({ collection: '', collection_name: '' })
  })

  // Sem lápide o caminho é o 404 de sempre — é o caso do produto despublicado,
  // que continua no catálogo e pode voltar.
  it('devolve null para código que não tem lápide', () => {
    expect(retiredFromPayload(PAYLOAD, 'MIB')).toBeNull()
  })

  it('aguenta resposta sem o bloco, nula ou de outro formato', () => {
    expect(retiredFromPayload({ redirects: {} }, 'PU')).toBeNull()
    expect(retiredFromPayload(null, 'PU')).toBeNull()
    expect(retiredFromPayload({ gone: { PU: 'doces' } }, 'PU')).toBeNull()
  })
})
