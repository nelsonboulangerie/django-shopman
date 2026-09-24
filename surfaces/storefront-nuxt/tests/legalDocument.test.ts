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
// - Cada seção tem âncora própria, única e estável: o fragmento é parte da URL
//   que se compartilha, e a cópia arquivada de cada versão guarda o mesmo id.

const root = resolve(__dirname, '..')
const read = (path: string) => readFileSync(resolve(root, path), 'utf8')
const templateOf = (fonte: string) => fonte.slice(fonte.indexOf('<template>'))

const PAGES = {
  'app/pages/privacidade.vue': ['controller', 'data-we-keep', 'legal-basis', 'sharing', 'retention', 'cookies', 'your-rights', 'changes'],
  'app/pages/termos.vue': ['seller', 'eligibility-and-acceptance', 'price-and-availability', 'order-confirmation', 'payment', 'pickup-and-delivery', 'cancellation', 'ifood-orders', 'your-account']
} as const

describe('páginas legais — a forma', () => {
  for (const [page, anchors] of Object.entries(PAGES)) {
    it(`${page} usa a moldura comum, sem acordeão, com as âncoras publicadas`, () => {
      const template = templateOf(read(page))
      expect(template).toMatch(/<LegalDocument title="[^"]+">/)
      expect(template).not.toMatch(/<details\b|Accordion|Collapsible/)
      // Tipografia é da moldura: a página não reinventa classe de corpo.
      expect(template).not.toContain('text-sm leading-6')
      expect(template).not.toContain('shop-heading')

      const found = [...template.matchAll(/<LegalSection id="([^"]+)">\s*<template #title>/g)].map(m => m[1])
      // Âncora é link compartilhado: renomear quebra quem já mandou o link.
      expect(found).toEqual([...anchors])
      expect(new Set(found).size).toBe(found.length)
      for (const id of found) expect(id).toMatch(/^[a-z]+(?:-[a-z]+)*$/)
    })
  }

  it('a moldura dá índice, âncora, próximo foco e volta ao topo', () => {
    const frame = read('app/components/LegalDocument.vue')
    const section = read('app/components/LegalSection.vue')
    // O índice sai das próprias seções — nenhuma segunda lista de títulos.
    expect(frame).toContain('node.type === LegalSection')
    expect(frame).toContain('data-legal-toc="desktop"')
    expect(frame).toContain('data-legal-toc="mobile"')
    expect(frame).toContain('useNextFocus')
    expect(frame).toContain('data-legal-back-to-top')
    expect(frame).toContain('<MoreBelow />')
    expect(frame).toContain('max-w-[65ch]')
    expect(section).toContain(':data-focus-target="id"')
    expect(section).toContain('<slot name="title" />')
  })
})
