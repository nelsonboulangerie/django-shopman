import { describe, expect, it } from 'vitest'
import { safeInternalPath } from '../app/utils/safeNavigation'
import { isStorefrontApiPathAllowed } from '../server/utils/storefrontApiAllowlist'
import { hasPathTraversal } from '../server/utils/djangoProxy'

describe('storefront security boundaries', () => {
  it('rejects protocol-relative login redirects', () => {
    expect(safeInternalPath('//evil.test')).toBe('/')
    expect(safeInternalPath('/\\evil.test')).toBe('/')
    expect(safeInternalPath('/finalizar')).toBe('/finalizar')
  })

  it('does not proxy backstage APIs through the public storefront BFF', () => {
    expect(isStorefrontApiPathAllowed('storefront/menu/')).toBe(true)
    expect(isStorefrontApiPathAllowed('auth/session/')).toBe(true)
    expect(isStorefrontApiPathAllowed('backstage/orders/')).toBe(false)
    expect(isStorefrontApiPathAllowed('/backstage/kds/')).toBe(false)
  })

  it('allows the ROOT endpoint of each allowed prefix (Nitro drops the trailing slash)', () => {
    // O catch-all entrega `/api/v1/checkout/` como `checkout` — foi o 404
    // silencioso do "Enviar pedido" (POST /api/v1/checkout/, o commit da loja).
    expect(isStorefrontApiPathAllowed('checkout')).toBe(true)
    expect(isStorefrontApiPathAllowed('cart')).toBe(true)
    // Prefixo parcial NÃO é raiz: continua bloqueado.
    expect(isStorefrontApiPathAllowed('checkoutX')).toBe(false)
    expect(isStorefrontApiPathAllowed('backstage')).toBe(false)
  })

  it('recusa travessia de caminho — a allowlist sozinha cai com um "../"', () => {
    // A allowlist aprova pelo PREFIXO, e o parser de URL do `$fetch` colapsa os
    // `..` só depois. Sem a trava no proxy, isto passava:
    expect(isStorefrontApiPathAllowed('cart/../backstage/pos/cash/movement/')).toBe(true)
    // ...e é o proxy que tem de recusar, antes de montar o alvo.
    expect(hasPathTraversal('/api/v1/cart/../backstage/pos/cash/movement/')).toBe(true)
    expect(hasPathTraversal('/api/v1/../../admin/login/')).toBe(true)
    // Escrito de outro jeito é o mesmo pedido.
    expect(hasPathTraversal('/api/v1/%2e%2e/%2e%2e/admin/login/')).toBe(true)
    expect(hasPathTraversal('/api/v1/%252e%252e/admin/login/')).toBe(true)
    expect(hasPathTraversal('/api/v1/cart\\..\\backstage/')).toBe(true)
    // Encoding malformado é recusa, não adivinhação.
    expect(hasPathTraversal('/api/v1/cart/%zz/')).toBe(true)
  })

  it('deixa passar o caminho honesto, inclusive com acento percent-encoded', () => {
    expect(hasPathTraversal('/api/v1/cart/')).toBe(false)
    expect(hasPathTraversal('/api/v1/orders/NB-1234/')).toBe(false)
    expect(hasPathTraversal('/api/v1/catalog/p%C3%A3o/')).toBe(false)
  })
})
