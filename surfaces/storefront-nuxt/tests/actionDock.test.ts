import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { actionDockFits, contentShareWithDock, MIN_CONTENT_SHARE } from '~/presentation/actionDock'

// #3573 (X11): o cartão do total na base só flutua enquanto deixa a página à vista.
// Os números são os medidos na loja compilada (375x812 e 320x812, seed `qa`), antes do
// conserto: cabeçalho 70 px (134 a 200 %), cartão até a base 80 px (160 a 200 %).

describe('actionDockFits', () => {
  it('fonte normal, celular em pé: o cartão da sacola e o do finalizar seguem fixos', () => {
    // sacola/finalizar a 100 %: cartão de 98 px.
    expect(actionDockFits({ viewportHeight: 812, topChrome: 70, bottomOffset: 80, dockHeight: 98 })).toBe(true)
    // A menor tela em pé (568 px) com a linha de motivo embaixo do botão (~120 px).
    expect(actionDockFits({ viewportHeight: 568, topChrome: 70, bottomOffset: 80, dockHeight: 120 })).toBe(true)
  })

  it('fonte a 200 %: o cartão da sacola (266 px) e o do finalizar (234 a 276 px) descem para o fluxo', () => {
    expect(actionDockFits({ viewportHeight: 812, topChrome: 134, bottomOffset: 160, dockHeight: 266 })).toBe(false)
    expect(actionDockFits({ viewportHeight: 812, topChrome: 134, bottomOffset: 160, dockHeight: 234 })).toBe(false)
    expect(actionDockFits({ viewportHeight: 812, topChrome: 134, bottomOffset: 160, dockHeight: 276 })).toBe(false)
    // Nem na tela mais alta de celular (932 px).
    expect(actionDockFits({ viewportHeight: 932, topChrome: 134, bottomOffset: 160, dockHeight: 234 })).toBe(false)
  })

  it('a fração é o que sobra entre o cabeçalho e o cartão, nunca negativa', () => {
    expect(contentShareWithDock({ viewportHeight: 1000, topChrome: 100, bottomOffset: 100, dockHeight: 200 })).toBe(0.6)
    expect(contentShareWithDock({ viewportHeight: 400, topChrome: 134, bottomOffset: 160, dockHeight: 266 })).toBe(0)
    expect(contentShareWithDock({ viewportHeight: 0, topChrome: 0, bottomOffset: 0, dockHeight: 0 })).toBe(1)
    expect(MIN_CONTENT_SHARE).toBe(0.45)
  })
})

describe('quem usa o cartão do total', () => {
  const read = (path: string) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

  it.each(['app/pages/sacola.vue', 'app/pages/finalizar.vue'])('%s mede o cartão e o tira de obstáculo quando ele desce', (path) => {
    const page = read(path)
    expect(page).toContain('useActionDockFit(actionDock)')
    expect(page).toContain('ref="actionDock"')
    expect(page).toContain(":class=\"{ 'shop-action-dock--in-flow': !actionDockFloats }\"")
    expect(page).toContain(':data-focus-obstruction="actionDockFloats ? \'\' : undefined"')
  })

  it('o CSS do fluxo vale só onde o cartão é fixo (abaixo de md)', () => {
    const css = read('app/assets/css/tailwind.css')
    const mobile = css.slice(css.indexOf('@media (max-width: 767px)'))
    expect(mobile.indexOf('.shop-action-dock.shop-action-dock--in-flow')).toBeGreaterThan(0)
    expect(mobile).toMatch(/\.shop-action-dock\.shop-action-dock--in-flow \{\s*position: static;/)
  })
})
