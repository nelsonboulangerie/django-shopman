// #3267: a recusa do envio que fala da sacola (já saiu, ou sumiu) chega com a ação
// que resolve, nunca como a frase do Core num toast sem saída.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { checkoutBagRefusal } from '../app/utils/checkoutBagRefusal'

describe('checkoutBagRefusal', () => {
  it('o pedido que outra aba já enviou leva ao acompanhamento dele', () => {
    expect(checkoutBagRefusal({
      detail: 'Este pedido já foi enviado.',
      error_code: 'order_already_sent',
      next_url: '/pedido/WEB-1',
      actions: [{ ref: 'view_order', kind: 'link', label: 'Ver o pedido', href: '/pedido/WEB-1' }]
    })).toEqual({
      kind: 'order_already_sent',
      message: 'Este pedido já foi enviado.',
      href: '/pedido/WEB-1',
      actionLabel: 'Ver o pedido'
    })
  })

  it('sem a ação, o pedido ainda abre pelo next_url', () => {
    expect(checkoutBagRefusal({ detail: 'Este pedido já foi enviado.', error_code: 'order_already_sent', next_url: '/pedido/WEB-2' }))
      .toMatchObject({ href: '/pedido/WEB-2', actionLabel: 'Ver o pedido' })
  })

  it('a sacola que sumiu leva ao cardápio', () => {
    expect(checkoutBagRefusal({
      detail: 'Sua sacola ficou vazia antes do envio.',
      error_code: 'cart_empty',
      actions: [{ ref: 'menu', kind: 'link', label: 'Ver o cardápio', href: '/menu' }]
    })).toEqual({
      kind: 'cart_empty',
      message: 'Sua sacola ficou vazia antes do envio.',
      href: '/menu',
      actionLabel: 'Ver o cardápio'
    })
  })

  it('link para fora da loja nunca vira destino', () => {
    expect(checkoutBagRefusal({
      detail: 'Sua sacola ficou vazia antes do envio.',
      error_code: 'cart_empty',
      actions: [{ ref: 'menu', kind: 'link', label: 'Ver o cardápio', href: '//evil.example/menu' }]
    })).toMatchObject({ href: '/menu', actionLabel: 'Ver o cardápio' })
  })

  it('as outras recusas seguem o caminho de sempre', () => {
    expect(checkoutBagRefusal({ detail: 'Sua sacola mudou.', error_code: 'revision_changed' })).toBeNull()
    expect(checkoutBagRefusal({ detail: 'Informe o endereço de entrega.', field: 'delivery_address' })).toBeNull()
    expect(checkoutBagRefusal(undefined)).toBeNull()
  })
})

describe('finalizar.vue trata a recusa da sacola antes do toast genérico', () => {
  const source = readFileSync(join(fileURLToPath(new URL('..', import.meta.url)), 'app/pages/finalizar.vue'), 'utf8')

  it('lê a recusa e oferece a ação dela', () => {
    const handled = source.indexOf('checkoutBagRefusal(data)')
    const generic = source.lastIndexOf('useSonner.error(serverError.value)')
    expect(handled).toBeGreaterThan(-1)
    expect(handled).toBeLessThan(generic)
    expect(source).toMatch(/action: \{ label: bagRefusal\.actionLabel/)
    expect(source).toMatch(/navigateTo\(bagRefusal\.href\)/)
  })
})
