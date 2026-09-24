import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// A página que o Google pede como "página inicial do app" na tela de consentimento
// OAuth. Ela aponta para as páginas legais, e as URLs são em inglês: /privacy e
// /terms. O #614 apontava para /privacidade e /termos, que não existem.
const source = readFileSync(
  fileURLToPath(new URL('../app/pages/shopman-marketing.vue', import.meta.url)),
  'utf8'
)

describe('página pública do Shopman Marketing', () => {
  it('aponta para a política de privacidade e os termos nas URLs que existem', () => {
    expect(source).toContain('to="/privacy"')
    expect(source).toContain('to="/terms"')
    expect(source).not.toContain('/privacidade')
    expect(source).not.toContain('/termos')
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
