import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// A página que o Google pede como "página inicial do app" na tela de consentimento
// OAuth. Ela aponta para as páginas legais da loja, que falam português com o
// cliente: /privacidade e /termos. /privacy e /terms só existem como 301.
const source = readFileSync(
  fileURLToPath(new URL('../app/pages/shopman-marketing.vue', import.meta.url)),
  'utf8'
)

describe('página pública do Shopman Marketing', () => {
  it('aponta para a política de privacidade e os termos nas URLs que existem', () => {
    expect(source).toContain('to="/privacidade"')
    expect(source).toContain('to="/termos"')
    expect(source).not.toContain('/privacy')
    expect(source).not.toContain('/terms')
  })

  it('diz o que acessa no Google, pelo nome que o Google usa', () => {
    expect(source).toContain('Perfil da Empresa no Google')
    expect(source).toContain('business.manage')
    expect(source).toContain('Não acessa Gmail, Drive, contatos nem arquivos da conta.')
  })

  it('não carrega a identidade da loja no código: ela vem da sessão', () => {
    expect(source).toContain('useShopSession()')
    expect(source).not.toContain('nelsonFallback')
  })
})
