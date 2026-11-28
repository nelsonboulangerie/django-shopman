// @vitest-environment happy-dom
import { beforeEach, describe, expect, it } from 'vitest'
import { markJustPlaced, takeJustPlaced } from '../app/utils/justPlaced'
import { orderSecuredThisVisit } from '../app/utils/orderSecured'

describe('momento yoin no navegador', () => {
  beforeEach(() => window.sessionStorage.clear())

  it('comemora uma vez só o pedido que este navegador fechou', () => {
    markJustPlaced('NB-1')

    expect(takeJustPlaced('NB-1')).toBe(true)
    expect(takeJustPlaced('NB-1')).toBe(false)
  })

  it('não comemora o pedido de outra pessoa nem queima a marca do próprio', () => {
    markJustPlaced('NB-1')

    expect(takeJustPlaced('NB-2')).toBe(false)
    expect(takeJustPlaced('NB-1')).toBe(true)
  })

  it('dois pedidos seguidos: só o último conta como recém-fechado', () => {
    markJustPlaced('NB-1')
    markJustPlaced('NB-2')

    expect(takeJustPlaced('NB-1')).toBe(false)
    expect(takeJustPlaced('NB-2')).toBe(true)
  })

  it('o pedido comemorado libera os convites desta visita; marca alheia não', () => {
    window.sessionStorage.removeItem('shopman-order-secured')
    markJustPlaced('NB-1')

    expect(takeJustPlaced('NB-2')).toBe(false)
    expect(orderSecuredThisVisit()).toBe(false)
    expect(takeJustPlaced('NB-1')).toBe(true)
    expect(orderSecuredThisVisit()).toBe(true)
  })

  it('sem marca não há comemoração', () => {
    expect(takeJustPlaced('NB-1')).toBe(false)
    expect(takeJustPlaced('')).toBe(false)
  })
})
