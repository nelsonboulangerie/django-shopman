// O botão com rótulo cresce com a fonte grande (X11, OC-30); o controle de tamanho fixo
// (pontos do carrossel da home e do produto, ícones, pílula com altura própria) fica
// exatamente como no main. Regressão de 24/11: o piso de altura do botão com rótulo valia
// também para o ponto `h-2 w-2 p-0`, que virou uma barra de 36 px sobre a foto.
import { describe, expect, it } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import { h } from 'vue'
import UiButton from '~/components/Ui/Button.vue'

function classes (wrapper: { classes: () => string[] }): string[] {
  return wrapper.classes()
}

describe('UiButton: piso de altura só para botão com rótulo', () => {
  it('o botão com rótulo ganha altura mínima e quebra linha', async () => {
    const wrapper = await mountSuspended(UiButton, { slots: { default: () => 'Encomendar para amanhã' } })
    const c = classes(wrapper)
    expect(c).toEqual(expect.arrayContaining(['min-h-9', 'h-auto', 'whitespace-normal', 'max-w-full']))
    expect(c).not.toContain('h-9')
    expect(c).not.toContain('whitespace-nowrap')
  })

  it('cada tamanho com rótulo tem o piso do próprio tamanho', async () => {
    for (const [size, floor] of [['xs', 'min-h-7'], ['sm', 'min-h-8'], ['lg', 'min-h-10']] as const) {
      const wrapper = await mountSuspended(UiButton, { props: { size }, slots: { default: () => 'Continuar' } })
      expect(classes(wrapper), size).toContain(floor)
    }
  })

  it('o ponto do carrossel (home e produto) fica com 8 px, sem piso', async () => {
    // A mesma marcação dos pontos em `HomeHeroThing.vue` e `pages/produto/[sku].vue`.
    for (const dotClass of ['h-2 w-2 min-w-0 rounded-full p-0 shadow-[0_0_2px_rgba(0,0,0,0.6)]', 'size-2 rounded-full p-0']) {
      const wrapper = await mountSuspended(UiButton, { props: { variant: 'ghost', class: dotClass }, attrs: { 'aria-label': 'Ir para a foto 1' } })
      const c = classes(wrapper)
      expect(c.some(name => name.startsWith('min-h-')), dotClass).toBe(false)
      expect(c, dotClass).not.toContain('h-auto')
      expect(c, dotClass).not.toContain('h-9')
      expect(c, dotClass).toContain('whitespace-nowrap')
    }
  })

  it('o botão-link `h-auto` quebra a linha mas não ganha piso de altura', async () => {
    // "Prefere receber um código por SMS?" (entrar) e "Observação deste item" (sacola).
    const wrapper = await mountSuspended(UiButton, { props: { variant: 'link', class: 'mx-auto h-auto px-0 text-muted-foreground' }, slots: { default: () => 'Prefere receber um código por SMS?' } })
    const c = classes(wrapper)
    expect(c).toEqual(expect.arrayContaining(['h-auto', 'whitespace-normal', 'max-w-full']))
    expect(c.some(name => name.startsWith('min-h-'))).toBe(false)
  })

  it('o botão de ícone e o botão com altura própria ficam como no main', async () => {
    const icon = await mountSuspended(UiButton, { props: { size: 'icon', icon: 'lucide:x' }, attrs: { 'aria-label': 'Fechar' } })
    expect(classes(icon)).toContain('size-9')
    expect(classes(icon).some(name => name.startsWith('min-h-'))).toBe(false)

    const pill = await mountSuspended(UiButton, { props: { size: 'sm', class: 'h-9 shrink-0 rounded-full px-3' }, slots: { default: () => h('span', 'Limpar filtro') } })
    expect(classes(pill)).toContain('h-9')
    expect(classes(pill)).toContain('whitespace-nowrap')
    expect(classes(pill).some(name => name.startsWith('min-h-'))).toBe(false)
  })
})
