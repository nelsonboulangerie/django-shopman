import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { parse } from 'vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

// O cardápio não salta (P2-01, WP-L04). Com o snapshot do cardápio ligado, a tela
// nasce com as seções fixas e, quando a leitura canônica chega, entram no topo a
// chave "Mostrar só disponíveis" e as seções vivas ("Destaques", "Recém saídos do
// forno"). Medido na pilha local em 19/11/2026, com o snapshot ligado como no
// alpha: deslocamento de layout de 0,40 (1366 px) a 0,72 (375 px) na carga.
//
// A prova de verdade é a medição na pilha (está no PR). Esta trava segura o
// desenho: o topo fica guardado enquanto a leitura canônica não chega, e a
// reserva nasce e morre com a mesma condição nos dois lugares.

const source = readFileSync(join(process.cwd(), 'app/pages/menu.vue'), 'utf8')
const { descriptor } = parse(source)
const template = descriptor.template?.content || ''
const script = descriptor.scriptSetup?.content || ''

function tagWith (attribute: string): string {
  const match = template.match(new RegExp(`<[a-zA-Z][^>]*${attribute}[^>]*>`, 's'))
  return match?.[0] || ''
}

describe('cardápio: o topo fica guardado enquanto a leitura canônica não chega', () => {
  it('a reserva vale só na espera da leitura canônica, na visão inteira', () => {
    expect(script).toMatch(
      /const reservesTop = computed\(\(\) => confirmingCatalog\.value && activeSection\.value === 'all' && !hasAppliedFilters\.value\)/
    )
    // A falha da leitura não é espera: a reserva sai e as seções fixas sobem.
    expect(script).toContain('const confirmingCatalog = computed(() => continuumPending.value && !continuumFailed.value)')
  })

  it('o lugar das seções vivas tem a altura da tela, e não entra na leitura de quem usa leitor de tela', () => {
    const placeholder = tagWith('data-menu-live-sections-placeholder')

    expect(placeholder).toContain('v-if="reservesTop"')
    expect(placeholder).toContain('min-h-svh')
    expect(placeholder).toContain('aria-hidden="true"')
  })

  it('o lugar da chave usa a mesma marcação da chave, com o texto invisível', () => {
    const placeholder = tagWith('data-menu-available-only-placeholder')
    const real = tagWith('data-menu-available-only\\b(?!-)')

    expect(placeholder).toContain('v-else-if="reservesTop"')
    expect(placeholder).toContain('aria-hidden="true"')
    // Mesma moldura: a altura bate por construção, não por número mágico.
    for (const cls of ['rounded-lg', 'border', 'bg-card', 'p-3']) {
      expect(real).toContain(cls)
      expect(placeholder).toContain(cls)
    }
    const block = template.slice(template.indexOf('data-menu-available-only-placeholder'))
    expect(block.slice(0, 500)).toContain('<p class="shop-body font-semibold">Mostrar só disponíveis</p>')
    expect(block.slice(0, 500)).toContain('class="invisible min-w-0"')
  })

  it('a reserva vem antes das seções, dentro da mesma pilha', () => {
    const stack = template.indexOf('<div v-if="activeSections.length" class="shop-stack-section">')
    const placeholder = template.indexOf('data-menu-live-sections-placeholder')
    const sections = template.indexOf('v-for="section in activeSections"')

    expect(stack).toBeGreaterThan(-1)
    expect(placeholder).toBeGreaterThan(stack)
    expect(sections).toBeGreaterThan(placeholder)
  })
})
