// O script inline do toque precoce (utils/earlyTap.ts), executado pelo próprio
// texto que vai no <head>. A repetição pelo componente está em
// tests/components/cartQuantityAction.test.ts.
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { claimEarlyTap, EARLY_TAP_QUEUE, EARLY_TAP_SCRIPT } from '~/utils/earlyTap'

type EarlyTapWindow = Window & { [EARLY_TAP_QUEUE]?: string[] }
const queue = () => (window as EarlyTapWindow)[EARLY_TAP_QUEUE]!

function button (key: string | null, parent: HTMLElement = document.body) {
  const el = document.createElement('button')
  el.type = 'button'
  if (key) el.setAttribute('data-early-tap', key)
  const label = document.createElement('span')
  label.textContent = 'Adicionar'
  el.appendChild(label)
  parent.appendChild(el)
  return el
}

describe('toque antes da hidratação (script inline)', () => {
  beforeAll(() => {
    new Function(EARLY_TAP_SCRIPT)()
    // Instalar duas vezes não duplica o ouvinte (o <head> pode ser reaproveitado).
    new Function(EARLY_TAP_SCRIPT)()
  })

  beforeEach(() => {
    queue().length = 0
    document.body.innerHTML = ''
  })

  it('guarda o toque uma vez só e marca o botão como em andamento', () => {
    const el = button('cart-add:PAO:1')
    el.click()
    el.click()
    expect(queue()).toEqual(['cart-add:PAO:1'])
    expect(el.getAttribute('data-early-tap-pending')).toBe('true')
    expect(el.getAttribute('aria-busy')).toBe('true')
  })

  it('pega o toque no filho do botão (ícone, rótulo)', () => {
    const el = button('cart-add:PAO:1')
    ;(el.firstElementChild as HTMLElement).click()
    expect(queue()).toEqual(['cart-add:PAO:1'])
  })

  it('segura a navegação de um cartão-link enquanto o app não está pronto', () => {
    const link = document.createElement('a')
    link.href = '/produto/PAO'
    document.body.appendChild(link)
    const el = button('cart-add:PAO:1', link)
    const event = new MouseEvent('click', { bubbles: true, cancelable: true })
    el.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('ignora botão desabilitado e botão sem a marca', () => {
    const off = button('cart-add:PAO:1')
    off.disabled = true
    off.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    const plain = button(null)
    const event = new MouseEvent('click', { bubbles: true, cancelable: true })
    plain.dispatchEvent(event)
    expect(queue()).toEqual([])
    expect(event.defaultPrevented).toBe(false)
  })

  it('claimEarlyTap entrega o toque uma vez e limpa a marca visual', () => {
    const el = button('cart-add:PAO:1')
    el.click()
    expect(claimEarlyTap('cart-add:PAO:1')).toBe(true)
    expect(claimEarlyTap('cart-add:PAO:1')).toBe(false)
    expect(el.hasAttribute('data-early-tap-pending')).toBe(false)
    expect(el.hasAttribute('aria-busy')).toBe(false)
    expect(claimEarlyTap('cart-add:OUTRO:1')).toBe(false)
  })
})
