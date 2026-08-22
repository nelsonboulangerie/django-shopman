import { describe, expect, it } from 'vitest'
import { safeInternalPath } from '../app/utils/safeNavigation'
import { isStorefrontApiPathAllowed } from '../server/utils/storefrontApiAllowlist'

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
})
