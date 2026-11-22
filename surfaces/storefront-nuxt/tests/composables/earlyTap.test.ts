// O script inline do toque precoce (utils/earlyTap.ts), executado pelo próprio
// texto que vai no <head>. A repetição pelo componente está em
// tests/components/cartQuantityAction.test.ts.
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { claimEarlyTap, EARLY_TAP_QUEUE, EARLY_TAP_SCRIPT, EARLY_TAP_STORE, parseCartAddKey, takeOrphanEarlyTaps } from '~/utils/earlyTap'

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
    window.sessionStorage.clear()
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

  it('guarda o toque também na aba, com o nome do produto (#3171)', () => {
    const el = button('cart-add:PAO:1')
    el.setAttribute('data-early-tap-name', 'Pão de forma')
    el.click()
    el.click()
    expect(JSON.parse(window.sessionStorage.getItem(EARLY_TAP_STORE)!)).toEqual([{ k: 'cart-add:PAO:1', n: 'Pão de forma' }])
  })

  it('o botão da página nova reclama o toque da página anterior, uma vez só', () => {
    window.sessionStorage.setItem(EARLY_TAP_STORE, JSON.stringify([{ k: 'cart-add:PAO:1', n: 'Pão' }]))
    expect(claimEarlyTap('cart-add:PAO:1')).toBe(true)
    expect(claimEarlyTap('cart-add:PAO:1')).toBe(false)
    expect(takeOrphanEarlyTaps()).toEqual([])
  })

  it('o que nenhum botão reclamou sai uma vez, da aba e da memória, sem a marca visual', () => {
    window.sessionStorage.setItem(EARLY_TAP_STORE, JSON.stringify([{ k: 'cart-add:PAO:1', n: 'Pão' }]))
    const el = button('cart-add:CAFE:2')
    el.click()
    expect(takeOrphanEarlyTaps()).toEqual([
      { key: 'cart-add:PAO:1', name: 'Pão' },
      { key: 'cart-add:CAFE:2', name: '' }
    ])
    expect(el.hasAttribute('data-early-tap-pending')).toBe(false)
    expect(takeOrphanEarlyTaps()).toEqual([])
    expect(window.sessionStorage.getItem(EARLY_TAP_STORE)).toBeNull()
  })

  it('um toque, uma execução: o botão que reclama tira da memória E da aba, e o app não repete', () => {
    const el = button('cart-add:PAO:1')
    el.click()
    // O toque está nos dois lugares; o botão monta e reclama.
    expect(queue()).toEqual(['cart-add:PAO:1'])
    expect(window.sessionStorage.getItem(EARLY_TAP_STORE)).not.toBeNull()
    expect(claimEarlyTap('cart-add:PAO:1')).toBe(true)
    // O plugin do app, depois de montar, não recebe nada para repetir.
    expect(takeOrphanEarlyTaps()).toEqual([])
    expect(claimEarlyTap('cart-add:PAO:1')).toBe(false)
  })

  it('aba com lixo não derruba nada', () => {
    window.sessionStorage.setItem(EARLY_TAP_STORE, '{não é json')
    expect(claimEarlyTap('cart-add:PAO:1')).toBe(false)
    expect(takeOrphanEarlyTaps()).toEqual([])
  })

  it('lê a chave do Adicionar', () => {
    expect(parseCartAddKey('cart-add:PAO-FORMA:2')).toEqual({ sku: 'PAO-FORMA', qty: 2 })
    expect(parseCartAddKey('cart-add:PAO:0')).toBeNull()
    expect(parseCartAddKey('outra-coisa')).toBeNull()
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
