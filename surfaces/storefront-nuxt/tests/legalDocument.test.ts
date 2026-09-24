import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// A FORMA das páginas legais. O texto é travado em legalVersion.test.ts; aqui
// fica o que faz ele ser legível e citável.
//
// - As duas páginas usam a mesma moldura (`LegalDocument`), para a tipografia
//   morar num lugar só.
// - Nada de acordeão: texto legal é lido de ponta a ponta, é o que o cliente
//   aceita ao entrar, e a âncora de uma cláusula tem que abrir a cláusula.
// - Cada seção tem âncora própria, única e em inglês (URL é em inglês, e o
//   fragmento é parte da URL que se compartilha).

const raiz = resolve(__dirname, '..')
const ler = (caminho: string) => readFileSync(resolve(raiz, caminho), 'utf8')
const templateDe = (fonte: string) => fonte.slice(fonte.indexOf('<template>'))

const PAGINAS = {
  'app/pages/privacy.vue': ['controller', 'data-we-keep', 'legal-basis', 'sharing', 'retention', 'cookies', 'your-rights', 'changes'],
  'app/pages/terms.vue': ['seller', 'eligibility-and-acceptance', 'price-and-availability', 'order-confirmation', 'payment', 'pickup-and-delivery', 'cancellation', 'ifood-orders', 'your-account']
} as const

describe('páginas legais — a forma', () => {
  for (const [pagina, ancoras] of Object.entries(PAGINAS)) {
    it(`${pagina} usa a moldura comum, sem acordeão, com as âncoras publicadas`, () => {
      const template = templateDe(ler(pagina))
      expect(template).toMatch(/<LegalDocument title="[^"]+">/)
      expect(template).not.toMatch(/<details\b|Accordion|Collapsible/)
      // Tipografia é da moldura: a página não reinventa classe de corpo.
      expect(template).not.toContain('text-sm leading-6')
      expect(template).not.toContain('shop-heading')

      const encontradas = [...template.matchAll(/<LegalSection id="([^"]+)">\s*<template #title>/g)].map(m => m[1])
      // Âncora é link compartilhado: renomear quebra quem já mandou o link.
      expect(encontradas).toEqual([...ancoras])
      expect(new Set(encontradas).size).toBe(encontradas.length)
      for (const id of encontradas) expect(id).toMatch(/^[a-z]+(?:-[a-z]+)*$/)
    })
  }

  for (const [pagina, ancoras] of Object.entries(PAGINAS)) {
    it(`${pagina}: todo item do resumo aponta uma seção que existe, e o resumo se declara resumo`, () => {
      const template = templateDe(ler(pagina))
      const alvos = [...template.matchAll(/<LegalSummaryItem to="#([^"]+)"/g)].map(m => m[1])
      // 4 a 7 itens: resumo que cresce vira segundo documento.
      expect(alvos.length).toBeGreaterThanOrEqual(4)
      expect(alvos.length).toBeLessThanOrEqual(7)
      for (const alvo of alvos) expect(ancoras as readonly string[]).toContain(alvo)
      expect(template).toMatch(/<template #disclaimer>\s*Este resumo não substitui/)
    })
  }

  it('a moldura dá índice, âncora, próximo foco e volta ao topo', () => {
    const moldura = ler('app/components/LegalDocument.vue')
    const secao = ler('app/components/LegalSection.vue')
    // O índice sai das próprias seções — nenhuma segunda lista de títulos.
    expect(moldura).toContain('node.type === LegalSection')
    expect(moldura).toContain('data-legal-toc="desktop"')
    expect(moldura).toContain('data-legal-toc="mobile"')
    expect(moldura).toContain('useNextFocus')
    expect(moldura).toContain('data-legal-back-to-top')
    expect(moldura).toContain('<MoreBelow />')
    expect(moldura).toContain('max-w-[65ch]')
    expect(secao).toContain(':data-focus-target="id"')
    expect(secao).toContain('<slot name="title" />')
  })
})
