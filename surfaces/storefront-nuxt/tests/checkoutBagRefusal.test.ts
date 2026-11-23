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

describe('finalizar.vue trata a recusa da sacola com o aviso de página, sem toast', () => {
  const source = readFileSync(join(fileURLToPath(new URL('..', import.meta.url)), 'app/pages/finalizar.vue'), 'utf8')
  const handled = source.indexOf('checkoutBagRefusal(data)')
  const branch = source.slice(handled, source.indexOf('// Preço/cupom mudou', handled))

  it('lê a recusa antes do toast genérico', () => {
    expect(handled).toBeGreaterThan(-1)
    expect(handled).toBeLessThan(source.lastIndexOf('useSonner.error(serverError.value)'))
  })

  it('nenhum toast nas recusas da sacola', () => {
    expect(branch).not.toMatch(/useSonner/)
    const conflict = source.slice(source.indexOf("data.error_code === 'idempotency_conflict'"), source.indexOf("data.error_code === 'mutation_in_progress'"))
    expect(conflict).not.toMatch(/useSonner/)
  })

  it('o pedido que já saiu: aviso na página do pedido, sem ação, e a tela vai até lá', () => {
    expect(branch).toMatch(/showPageNotice\(bagRefusal\.message, bagRefusal\.href\)\s*await navigateTo\(bagRefusal\.href\)/)
  })

  it('a tentativa que outra aba já enviou: o mesmo aviso, no pedido recuperado', () => {
    expect(source).toMatch(/idempotency_conflict' && await recoverCheckout\(attemptKey\.value\)\) \{\s*if \(confirmedTrackingUrl\.value\) showPageNotice\(ORDER_ALREADY_SENT_MESSAGE, confirmedTrackingUrl\.value\)/)
  })

  it('a sacola que sumiu: aviso nesta página, de atenção, com a saída da recusa', () => {
    expect(branch).toMatch(/showPageNotice\(bagRefusal\.message, route\.path, \{\s*tone: 'attention',\s*action: \{ label: bagRefusal\.actionLabel, to: bagRefusal\.href \}/)
  })

  it('a sacola que sumiu aceita a leitura vazia, sem a barreira de revisão', () => {
    const reread = branch.lastIndexOf('await refresh()')
    expect(reread).toBeGreaterThan(-1)
    expect(branch.indexOf('acceptEmptiedCheckout()', reread)).toBeGreaterThan(reread)
    // Fora do `catch`: lá dentro, `data` é o corpo do erro, não a leitura do checkout.
    const helper = source.indexOf('function acceptEmptiedCheckout')
    expect(helper).toBeGreaterThan(-1)
    expect(helper).toBeLessThan(source.indexOf('async function submitCheckout'))
    expect(source.slice(helper, helper + 200)).toMatch(/freshestCheckout\.value = data\.value\.checkout/)
  })

  it('com o aviso à vista, a etapa e a barra do total não repetem a frase nem a saída', () => {
    expect(source).toMatch(/action: bagGoneNoticeShowing\.value \? null : action\.value/)
    expect(source).toMatch(/<template v-if="!bagGoneNoticeShowing">\s*<UiButton\s+size="lg"\s+:icon="primaryAction\.icon"/)
    // A sacola vazia sem recusa segue igual: o botão "Adicionar itens" e a frase.
    expect(source).toMatch(/label: 'Adicionar itens', icon: 'lucide:utensils'.*reason: 'Sacola vazia\.'/)
  })
})
