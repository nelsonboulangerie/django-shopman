import { describe, expect, it } from 'vitest'

import { loginDestination } from '~/utils/loginDestination'

// A regra da casa, na voz do dono: "ao logar, o sistema deve OU preservar onde o
// usuário estava/queria ir, OU levar à home (como fallback)".
//
// O que quebrava: não há botão "Entrar" na loja. A única porta é a aba "Conta",
// e o guard gravava cegamente a rota barrada — então quem tocava nela só para se
// identificar voltava para `/conta`, uma tela que não pediu, perdendo a página em
// que estava.

describe('loginDestination — a aba "Conta" é porta de login, não destino', () => {
  it('quem estava num produto e tocou em Conta VOLTA para o produto', () => {
    expect(loginDestination('/conta', '/produto/BF')).toBe('/produto/BF')
  })

  it('quem estava no cardápio volta para o cardápio', () => {
    expect(loginDestination('/conta', '/menu')).toBe('/menu')
  })

  it('quem estava na sacola volta para a sacola', () => {
    expect(loginDestination('/conta', '/sacola')).toBe('/sacola')
  })

  it('entrada DIRETA em /conta preserva /conta', () => {
    // Digitou o endereço ou abriu um favorito: ele realmente queria a conta.
    // Mandá-lo para a home seria trocar um destino errado por outro.
    expect(loginDestination('/conta', '')).toBe('/conta')
    expect(loginDestination('/conta', null)).toBe('/conta')
    expect(loginDestination('/conta', undefined)).toBe('/conta')
  })

  it('vindo da própria /conta (recarregou), preserva /conta', () => {
    expect(loginDestination('/conta', '/conta')).toBe('/conta')
  })

  it('nunca volta para a tela de login — isso seria um laço', () => {
    expect(loginDestination('/conta', '/entrar')).toBe('/conta')
    expect(loginDestination('/conta', '/entrar?next=/algo')).toBe('/conta')
    expect(loginDestination('/conta', '/a')).toBe('/conta')
  })
})

describe('loginDestination — pedido EXPLÍCITO se preserva', () => {
  it('sub-rotas da conta são destino de verdade', () => {
    // "Ver meus pedidos" e "editar perfil" são o que o cliente pediu, não a
    // porta de login: preserva mesmo tendo vindo de outra página.
    expect(loginDestination('/conta/pedidos', '/produto/BF')).toBe('/conta/pedidos')
    expect(loginDestination('/conta/perfil', '/menu')).toBe('/conta/perfil')
  })

  it('checkout e acompanhamento se preservam', () => {
    expect(loginDestination('/finalizar', '/sacola')).toBe('/finalizar')
    expect(loginDestination('/pedido/PDV-1', '/')).toBe('/pedido/PDV-1')
  })

  it('/conta com query ainda é a porta de login', () => {
    expect(loginDestination('/conta?aba=dados', '/menu')).toBe('/menu')
  })
})

describe('loginDestination — destino inseguro nunca escapa', () => {
  it('caminho externo cai na home', () => {
    // A mesma guarda de `safeInternalPath`: `//evil.com` e `/\evil` são
    // redirecionamento aberto disfarçado de caminho relativo.
    expect(loginDestination('//evil.com', '/menu')).toBe('/')
    expect(loginDestination('https://evil.com', '/menu')).toBe('/')
  })

  it('origem insegura é ignorada, e o destino barrado prevalece', () => {
    expect(loginDestination('/conta', '//evil.com')).toBe('/conta')
  })

  it('lixo no destino cai na home', () => {
    expect(loginDestination('', '/menu')).toBe('/')
  })
})
