import { describe, expect, it } from 'vitest'

import { accountNavEntry } from '~/utils/accountNavEntry'

// Até aqui a loja não tinha "Entrar" em lugar nenhum: quem quisesse se
// identificar tocava em "Conta", era barrado pelo guard e caía no login. O
// rótulo mentia (prometia a conta, entregava um formulário) e o caminho tinha um
// salto a mais — e cada salto é uma chance de o cliente achar que se perdeu.

describe('accountNavEntry — deslogado, o slot é a PORTA', () => {
  it('diz "Entrar", com ícone de entrada', () => {
    const item = accountNavEntry(false, '/menu')

    expect(item.label).toBe('Entrar')
    expect(item.icon).toBe('lucide:log-in')
  })

  it('vai DIRETO ao login, sem passar por /conta', () => {
    // Some o salto `/conta` → guard → `/entrar`.
    expect(accountNavEntry(false, '/menu').to).toBe('/entrar?next=%2Fmenu')
  })

  it('guarda a página atual, com query e tudo', () => {
    expect(accountNavEntry(false, '/produto/BF?de=busca').to)
      .toBe('/entrar?next=%2Fproduto%2FBF%3Fde%3Dbusca')
  })

  it('na própria tela de login não guarda origem — seria um laço', () => {
    expect(accountNavEntry(false, '/entrar').to).toBe('/entrar')
    expect(accountNavEntry(false, '/entrar?next=/menu').to).toBe('/entrar')
    expect(accountNavEntry(false, '/a?t=abc').to).toBe('/entrar')
  })

  it('origem insegura não vira next', () => {
    // `//evil.com` é redirecionamento aberto disfarçado de caminho relativo.
    expect(accountNavEntry(false, '//evil.com').to).toBe('/entrar')
    expect(accountNavEntry(false, 'https://evil.com').to).toBe('/entrar')
    expect(accountNavEntry(false, '').to).toBe('/entrar')
  })
})

describe('accountNavEntry — logado, o slot é a CONTA', () => {
  it('volta a ser a conta, com o ícone de pessoa', () => {
    const item = accountNavEntry(true, '/menu')

    expect(item).toEqual({ to: '/conta', label: 'Conta', icon: 'lucide:user-round' })
  })

  it('ignora a página atual: logado não há next a guardar', () => {
    expect(accountNavEntry(true, '/produto/BF').to).toBe('/conta')
  })

  it('o rótulo de logado se adapta à largura de quem chama', () => {
    // A barra de baixo cabe "Conta"; o menu do cabeçalho cabe "Conta e pedidos".
    expect(accountNavEntry(true, '/', 'Conta e pedidos').label).toBe('Conta e pedidos')
  })

  it('mas o rótulo da PORTA é um só, em qualquer largura', () => {
    // "Entrar" não muda conforme o espaço: a porta tem um nome.
    expect(accountNavEntry(false, '/', 'Conta e pedidos').label).toBe('Entrar')
  })
})
