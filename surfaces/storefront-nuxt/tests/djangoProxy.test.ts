import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { csrfTokenFromCookieHeader, mergeSetCookieIntoCookieHeader, storefrontSetCookieHeader } from '../server/utils/djangoProxy'
import { resolveDjangoBaseUrl } from '../server/utils/djangoBaseUrl'

const proxySource = readFileSync(fileURLToPath(new URL('../server/utils/djangoProxy.ts', import.meta.url)), 'utf8')

describe('Django proxy CSRF transport', () => {
  it('reads and updates the csrftoken cookie without dropping the session', () => {
    const cookie = 'sessionid=session-123; csrftoken=old-token'

    expect(csrfTokenFromCookieHeader(cookie)).toBe('old-token')
    expect(mergeSetCookieIntoCookieHeader(cookie, 'csrftoken=new-token; Path=/; SameSite=Lax')).toBe('sessionid=session-123; csrftoken=new-token')
  })

  it('keeps cookie values containing "=" intact (signed/base64 values)', () => {
    const cookie = 'csrftoken=old-token'

    expect(mergeSetCookieIntoCookieHeader(cookie, 'sessionid=abc.def=ghi==; Path=/; HttpOnly')).toBe('csrftoken=old-token; sessionid=abc.def=ghi==')
  })

  it('emits storefront cookies as host-only cookies', () => {
    expect(storefrontSetCookieHeader('sessionid=s1; Domain=.boulangerie.com.br; Path=/; SameSite=Lax; Secure; HttpOnly'))
      .toBe('sessionid=s1; Path=/; SameSite=Lax; Secure; HttpOnly')
    expect(storefrontSetCookieHeader('csrftoken=t1; domain=.boulangerie.com.br; Path=/; SameSite=Lax; Secure'))
      .toBe('csrftoken=t1; Path=/; SameSite=Lax; Secure')
  })

  it('normalizes unsafe request origin to the Django backend origin', () => {
    expect(proxySource).toContain('headers.origin = djangoOrigin')
    expect(proxySource).toContain('headers.referer = `${djangoOrigin}/`')
    expect(proxySource).not.toContain("getRequestHeader(event, 'origin')")
    expect(proxySource).not.toContain("getRequestHeader(event, 'referer')")
  })

  it('rejects a local Django upstream in production', () => {
    const previous = process.env.SHOPMAN_ENVIRONMENT
    process.env.SHOPMAN_ENVIRONMENT = 'production'
    try {
      try {
        resolveDjangoBaseUrl('http://127.0.0.1:8000/')
        throw new Error('expected local upstream to be rejected')
      } catch (error: any) {
        expect(error.statusCode).toBe(503)
      }
      expect(resolveDjangoBaseUrl('https://api.example.test/')).toBe('https://api.example.test')
    } finally {
      if (previous == null) delete process.env.SHOPMAN_ENVIRONMENT
      else process.env.SHOPMAN_ENVIRONMENT = previous
    }
  })
})
