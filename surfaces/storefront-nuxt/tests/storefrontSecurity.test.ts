import { describe, expect, it } from 'vitest'
import {
  STOREFRONT_CONTENT_SECURITY_POLICY,
  STOREFRONT_PERMISSIONS_POLICY,
  storefrontResponseHeaders,
} from '../server/utils/storefrontSecurity'

describe('storefront security headers', () => {
  it('blocks framing and MIME sniffing while preserving required customer capabilities', () => {
    const headers = storefrontResponseHeaders(true)

    expect(headers['X-Frame-Options']).toBe('DENY')
    expect(headers['X-Content-Type-Options']).toBe('nosniff')
    expect(headers['Referrer-Policy']).toBe('strict-origin-when-cross-origin')
    expect(headers['Strict-Transport-Security']).toBe('max-age=31536000; includeSubDomains; preload')
    expect(STOREFRONT_CONTENT_SECURITY_POLICY).toContain("frame-ancestors 'none'")
    expect(STOREFRONT_CONTENT_SECURITY_POLICY).toContain("object-src 'none'")
    expect(STOREFRONT_CONTENT_SECURITY_POLICY).toContain('https://*.googleapis.com')
    expect(STOREFRONT_CONTENT_SECURITY_POLICY).toContain('https://*.js.stripe.com')
    expect(STOREFRONT_CONTENT_SECURITY_POLICY).toContain('https://js.stripe.com')
    expect(STOREFRONT_CONTENT_SECURITY_POLICY).toContain('https://checkout.stripe.com')
    expect(STOREFRONT_PERMISSIONS_POLICY).toContain('geolocation=(self)')
  })

  it('does not emit HSTS for a plain HTTP development request', () => {
    expect(storefrontResponseHeaders(false)['Strict-Transport-Security']).toBeUndefined()
  })

  it('never caches or sends a referrer from the stock-alert capability page', () => {
    const headers = storefrontResponseHeaders(true, '/gerenciar-aviso')

    expect(headers['Cache-Control']).toBe('private, no-store, max-age=0')
    expect(headers.Pragma).toBe('no-cache')
    expect(headers['Referrer-Policy']).toBe('no-referrer')
  })
})
