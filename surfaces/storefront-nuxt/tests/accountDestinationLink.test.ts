import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { accountDestinationLink } from '~/utils/accountNavEntry'
import { loginDestination } from '~/utils/loginDestination'

// O caso do dono (23/09): deslogado, tocou em "Conta e pedidos" no rodapé, entrou
// — e voltou para a página de onde tinha saído, não para a conta. "Isso é muito
// chato para o usuário!"
//
// A causa: o link apontava para `/conta` puro. O guard vê `/conta` alcançado a
// partir de outra página e o toma pela porta de login ("só queria se
// identificar"), gravando a ORIGEM no `?next=`. Certo para a aba "Conta" de
// antigamente; errado para um link cujo rótulo promete a conta.

const read = (path: string) => readFileSync(resolve(__dirname, '..', path), 'utf8')

describe('accountDestinationLink — o rodapé pede a conta, e a conta é o destino', () => {
  it('deslogado, vai ao login com next=/conta explícito', () => {
    expect(accountDestinationLink(false, '/conta')).toBe('/entrar?next=%2Fconta')
  })

  it('logado, vai direto à conta', () => {
    expect(accountDestinationLink(true, '/conta')).toBe('/conta')
  })

  it('preserva sub-rotas da conta', () => {
    expect(accountDestinationLink(false, '/conta/pedidos')).toBe('/entrar?next=%2Fconta%2Fpedidos')
  })

  it('destino externo nunca vira next (redirecionamento aberto)', () => {
    expect(accountDestinationLink(false, '//evil.com')).toBe('/entrar?next=%2Fconta')
    expect(accountDestinationLink(false, 'https://evil.com')).toBe('/entrar?next=%2Fconta')
    expect(accountDestinationLink(true, '/\\evil.com')).toBe('/conta')
  })

  it('o defeito que isto conserta: /conta via guard devolvia à origem', () => {
    // O comportamento do guard continua o mesmo (é o certo para a porta);
    // por isso o link do rodapé não pode depender dele.
    expect(loginDestination('/conta', '/menu')).toBe('/menu')
  })
})

describe('os links que prometem a conta não passam pela porta do guard', () => {
  it('rodapé: "Conta e pedidos" usa accountDestinationLink, nunca to="/conta"', () => {
    const footer = read('app/components/ShopFooter.vue')
    expect(footer).toContain("accountDestinationLink(session.isAuthenticated.value, '/conta')")
    expect(footer).not.toMatch(/to="\/conta"/)
  })

  it('acompanhamento: a migalha "Pedidos" leva a /conta/pedidos (destino explícito)', () => {
    const tracking = read('app/pages/pedido/[ref]/index.vue')
    expect(tracking).toContain("{ label: 'Pedidos', link: '/conta/pedidos' }")
  })
})
