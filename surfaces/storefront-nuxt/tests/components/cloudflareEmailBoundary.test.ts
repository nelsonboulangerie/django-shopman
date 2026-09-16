import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it } from 'vitest'
import CloudflareEmailBoundary from '../../app/components/CloudflareEmailBoundary.vue'

describe('CloudflareEmailBoundary', () => {
  it('keeps the documented email-obfuscation opt-out in SSR output', async () => {
    const app = createSSRApp({
      render: () => h(CloudflareEmailBoundary, null, {
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
})
