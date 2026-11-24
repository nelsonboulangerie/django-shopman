import { describe, expect, it } from 'vitest'
import {
  HEADER_COLLAPSE_AT,
  HEADER_EXPAND_AT,
  STATUS_BAR_HEIGHT,
  focusRulerAllowance,
  headerCollapsed
} from '~/presentation/scroll'

describe('headerCollapsed', () => {
  it('expandida fica expandida até o limiar de colapso', () => {
    expect(headerCollapsed(false, 0)).toBe(false)
    expect(headerCollapsed(false, HEADER_EXPAND_AT)).toBe(false)
    expect(headerCollapsed(false, HEADER_COLLAPSE_AT)).toBe(false)
  })

  it('colapsa passado o limiar de colapso', () => {
    expect(headerCollapsed(false, HEADER_COLLAPSE_AT + 1)).toBe(true)
    expect(headerCollapsed(false, 400)).toBe(true)
  })

  it('colapsada fica colapsada na zona morta entre os limiares', () => {
    expect(headerCollapsed(true, HEADER_COLLAPSE_AT)).toBe(true)
    expect(headerCollapsed(true, HEADER_EXPAND_AT + 4)).toBe(true)
    expect(headerCollapsed(true, HEADER_EXPAND_AT)).toBe(true)
  })

  it('reexpande só de volta ao topo', () => {
    expect(headerCollapsed(true, HEADER_EXPAND_AT - 1)).toBe(false)
    expect(headerCollapsed(true, 0)).toBe(false)
  })

  // Colapsado, o header desliza `STATUS_BAR_HEIGHT` para cima mantendo a altura
  // no fluxo, então a navbar cobre o conteúdo só a partir dessa rolagem. Se o
  // estado colapsado pudesse existir mais acima, apareceria uma faixa de fundo
  // entre a navbar e o conteúdo.
  it('nunca fica colapsada antes do conteúdo passar sob a navbar', () => {
    expect(HEADER_EXPAND_AT).toBeGreaterThanOrEqual(STATUS_BAR_HEIGHT)
    for (let y = 0; y < STATUS_BAR_HEIGHT; y++) {
      expect(headerCollapsed(true, y)).toBe(false)
      expect(headerCollapsed(false, y)).toBe(false)
    }
  })

  // Regressão do tremor visto no alpha. O colapso mexia na altura da página e o
  // browser corrigia o scroll sozinho — por clamp, ou por scroll anchoring, que
  // desloca a rolagem pela altura EXATA da barra. Esse salto pulava a zona morta
  // e a barra oscilava para sempre (medido no browser: y alternando entre 38 e 2
  // com os limiares anteriores, 24/4).
  //
  // O componente tirou a mudança de altura do fluxo, então o salto não acontece
  // mais. Isto aqui é a defesa em profundidade: mesmo que sobre uma correção de
  // scroll do tamanho da barra, o estado tem de assentar. Simula o usuário
  // chegando expandido, parando em cada posição, e o scroll sendo corrigido a
  // cada troca de estado.
  it('assenta mesmo se o scroll for corrigido pela altura da barra', () => {
    for (let inicio = 0; inicio <= 600; inicio++) {
      let collapsed = false
      let y = inicio
      for (let passo = 0; passo < 16; passo++) {
        const anterior = collapsed
        collapsed = headerCollapsed(collapsed, y)
        if (collapsed !== anterior) {
          y = Math.max(0, y + (collapsed ? -STATUS_BAR_HEIGHT : STATUS_BAR_HEIGHT))
        }
      }
      // Assentou: reavaliar no estado final não troca mais nada.
      expect(headerCollapsed(collapsed, y)).toBe(collapsed)
    }
  })

  // A propriedade que sustenta o teste acima, dita de forma direta.
  it('zona morta é no mínimo a altura da barra', () => {
    expect(HEADER_COLLAPSE_AT - HEADER_EXPAND_AT).toBeGreaterThanOrEqual(STATUS_BAR_HEIGHT)
  })
})

// A régua do próximo foco (#3477): o bloco nunca para atrás da status bar.
describe('focusRulerAllowance', () => {
  // Altura do chrome que cobre o topo numa rolagem, dado o estado de partida.
  function chromeAt (startCollapsed: boolean, y: number): number {
    const NAVBAR = 70 // 4rem + o fio de 6px: a régua base, a do CSS
    return headerCollapsed(startCollapsed, y) ? NAVBAR : NAVBAR + STATUS_BAR_HEIGHT
  }

  it('o caso medido no /entrar a 375 px: parada em 54 desce a régua a altura da barra', () => {
    expect(focusRulerAllowance(54)).toBe(STATUS_BAR_HEIGHT)
  })

  it('parada depois do limiar de colapso usa a régua base', () => {
    expect(focusRulerAllowance(HEADER_COLLAPSE_AT + 1)).toBe(0)
    expect(focusRulerAllowance(900)).toBe(0)
  })

  it('em qualquer bloco e qualquer estado de partida, o bloco para NA linha de foco, nunca sob o chrome', () => {
    const NAVBAR = 70
    // O cabeçalho é sticky e ocupa o fluxo: conteúdo nenhum começa acima dele.
    const firstContent = NAVBAR + STATUS_BAR_HEIGHT
    for (const startCollapsed of [false, true]) {
      for (let blockTop = firstContent; blockTop <= 600; blockTop++) {
        const base = Math.max(0, blockTop - NAVBAR)
        const ruler = NAVBAR + focusRulerAllowance(base)
        const landing = Math.max(0, blockTop - ruler)
        const visibleTop = blockTop - landing
        const chrome = chromeAt(startCollapsed, landing)
        const where = `bloco em ${blockTop}, partida ${startCollapsed ? 'recolhida' : 'de pé'}`
        expect(visibleTop, where).toBeGreaterThanOrEqual(chrome)
        // A MESMA linha da régua padrão (barra recolhida, régua do CSS): o topo do
        // bloco encosta na base do chrome que está à vista, com a status bar de pé
        // ou não. O respiro até o conteúdo é do próprio bloco (o passo do checkout
        // tem py-4; o do /entrar, -mt-4 pt-4), então ele é o mesmo nos dois estados.
        // Exceções medidas: a página no topo (não dá para subir mais) e a parada
        // exata na reexpansão com a barra recolhida (36px a mais, à vista).
        const clamped = landing === 0
        const expandEdge = startCollapsed && landing === HEADER_EXPAND_AT
        if (!clamped && !expandEdge) expect(visibleTop - chrome, where).toBe(0)
      }
    }
  })
})
