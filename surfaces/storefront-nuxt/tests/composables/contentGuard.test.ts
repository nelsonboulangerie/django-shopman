import { describe, expect, it } from 'vitest'
import { requireContentOnSsr, shouldFailOnSsr } from '~/composables/useContentGuard'

// A régua tem três lados: no SERVIDOR, com a busca FALHADA e SEM conteúdo, cai.
// Qualquer outro caso segue em frente.
describe('shouldFailOnSsr', () => {
  it('cai quando a busca falhou e não veio conteúdo', () => {
    expect(shouldFailOnSsr(true, { statusCode: 504 }, false)).toBe(true)
  })

  it('não cai quando o conteúdo veio, mesmo com erro registrado', () => {
    expect(shouldFailOnSsr(true, { statusCode: 500 }, true)).toBe(false)
  })

  // Vitrine vazia é estado possível da casa; backend mudo não é (WP-S5).
  it('não cai quando o backend respondeu sem dado', () => {
    expect(shouldFailOnSsr(true, null, false)).toBe(false)
  })

  // No cliente a página já está montada: o caminho é o "Tente de novo" inline.
  it('não cai no cliente', () => {
    expect(shouldFailOnSsr(false, { statusCode: 504 }, false)).toBe(false)
  })
})

describe('requireContentOnSsr', () => {
  // No ambiente de teste (cliente) a função é inerte — é a garantia de que ela
  // nunca derruba a navegação de quem já está na loja.
  it('não levanta erro fora do servidor', () => {
    expect(() => requireContentOnSsr({ statusCode: 504 }, false, 'Produto')).not.toThrow()
  })
})
