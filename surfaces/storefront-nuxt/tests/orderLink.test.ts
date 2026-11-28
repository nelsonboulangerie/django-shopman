import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it, vi } from 'vitest'
import { cleanOrderPath, openOrderLink, splitOrderLinkParam } from '~/presentation/orderLink'

// DEV-2026-093: o link do aviso é `/pedido/<ref>~<selo>`. A página troca o selo
// pelo acesso a ESTE pedido antes de ler o acompanhamento, e deixa a URL limpa.

describe('order link param', () => {
  it('separates the ref from the capability', () => {
    expect(splitOrderLinkParam('WEB-261125-A93~OXLcKv9MuXF5_LLkNqh-PQ')).toEqual({
      ref: 'WEB-261125-A93',
      capability: 'OXLcKv9MuXF5_LLkNqh-PQ'
    })
  })

  it('keeps a plain ref as is, with no capability', () => {
    expect(splitOrderLinkParam('WEB-261125-A93')).toEqual({ ref: 'WEB-261125-A93', capability: '' })
    expect(splitOrderLinkParam(undefined)).toEqual({ ref: '', capability: '' })
  })

  it('builds the clean order path, without the capability', () => {
    expect(cleanOrderPath('WEB-261125-A93')).toBe('/pedido/WEB-261125-A93')
  })
})

describe('opening the order link', () => {
  it('exchanges the capability BEFORE leaving the clean URL', async () => {
    const calls: string[] = []
    const exchange = vi.fn(async (ref: string, cap: string) => { calls.push(`exchange:${ref}:${cap}`) })
    const replace = vi.fn(async (path: string) => { calls.push(`replace:${path}`) })

    const result = await openOrderLink('WEB-261125-A93~SELO', { exchange, replace })

    expect(calls).toEqual(['exchange:WEB-261125-A93:SELO', 'replace:/pedido/WEB-261125-A93'])
    expect(result).toEqual({ ref: 'WEB-261125-A93', arrivedWithCapability: true, exchanged: true })
  })

  it('still cleans the URL when the capability is refused (expired, revoked)', async () => {
    const replace = vi.fn()
    const result = await openOrderLink('WEB-261125-A93~VENCIDO', {
      exchange: () => Promise.reject(new Error('404')),
      replace
    })
    expect(replace).toHaveBeenCalledWith('/pedido/WEB-261125-A93')
    expect(result.exchanged).toBe(false)
  })

  it('does nothing for a plain order URL', async () => {
    const exchange = vi.fn()
    const replace = vi.fn()
    const result = await openOrderLink('WEB-261125-A93', { exchange, replace })
    expect(exchange).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
    expect(result.arrivedWithCapability).toBe(false)
  })
})

describe('order page wiring', () => {
  const page = readFileSync(resolve(__dirname, '../app/pages/pedido/[ref]/index.vue'), 'utf8')

  it('waits for the exchange: no server read and no immediate read with a capability', () => {
    expect(page).toContain('server: !arrivedWithCapability')
    expect(page).toContain('immediate: !arrivedWithCapability')
    expect(page).toMatch(/openOrderLink\(String\(route\.params\.ref/)
    expect(page).toContain('/access/')
    expect(page).toContain('router.replace(path)')
  })

  it('shows the server invitation to sign in instead of cancel when opened by the link', () => {
    expect(page).toContain('data-login-invite')
    expect(page).toContain('loginInvite.href')
  })
})
