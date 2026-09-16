import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CloudflareEmailBoundary from '../../app/components/CloudflareEmailBoundary.vue'

describe('CloudflareEmailBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('keeps the documented email-obfuscation opt-out in SSR output', async () => {
    const app = createSSRApp({
      render: () => h(CloudflareEmailBoundary, { protect: true }, {
        default: () => 'Contato: loja@example.invalid'
      })
    })

    const html = await renderToString(app)

    expect(html).toContain('<!--email_off-->')
    expect(html).toContain('Contato: loja@example.invalid')
    expect(html).toContain('<!--/email_off-->')
    expect(html.indexOf('<!--email_off-->')).toBeLessThan(html.indexOf('loja@example.invalid'))
    expect(html.indexOf('loja@example.invalid')).toBeLessThan(html.indexOf('<!--/email_off-->'))
  })

  it('hydrates the response after Cloudflare consumes its control comments', async () => {
    const serverApp = createSSRApp({
      render: () => h(CloudflareEmailBoundary, { protect: true }, {
        default: () => 'Contato: loja@example.invalid'
      })
    })
    const transformedHtml = (await renderToString(serverApp))
      .replace('<!--email_off-->', '')
      .replace('<!--/email_off-->', '')
    const container = document.createElement('div')
    container.innerHTML = transformedHtml
    document.body.append(container)
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const clientApp = createSSRApp({
      render: () => h(CloudflareEmailBoundary, { protect: false }, {
        default: () => 'Contato: loja@example.invalid'
      })
    })

    clientApp.mount(container)

    expect(consoleError).not.toHaveBeenCalledWith(expect.stringMatching(/hydrat|mismatch/i))
    expect(container.textContent).toBe('Contato: loja@example.invalid')
  })
})
