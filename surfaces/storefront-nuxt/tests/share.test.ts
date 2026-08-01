import { describe, expect, it } from 'vitest'
import {
  orderShareUrl,
  shareMessage,
  whatsAppShareHref
} from '../app/utils/share'

describe('mensagem de compartilhamento', () => {
  it('junta a frase e o link numa mensagem só', () => {
    expect(shareMessage('Meu pedido WEB-1 na Nelson Boulangerie', 'https://nelson/pedido/WEB-1'))
      .toBe('Meu pedido WEB-1 na Nelson Boulangerie https://nelson/pedido/WEB-1')
  })

  it('degrada para o que existir', () => {
    expect(shareMessage('', 'https://nelson/pedido/WEB-1')).toBe('https://nelson/pedido/WEB-1')
    expect(shareMessage('Meu pedido', '')).toBe('Meu pedido')
  })
})

describe('link de fallback do WhatsApp', () => {
  it('usa o endpoint de envio, nao o click-to-chat sem telefone', () => {
    // `wa.me/?text=` tem o telefone VAZIO e cai na pagina "Continue to Chat",
    // que perde o texto — era por isso que so o link cru chegava.
    const href = whatsAppShareHref('Meu pedido WEB-1 https://nelson/pedido/WEB-1')

    expect(href).toContain('api.whatsapp.com/send')
    expect(href).not.toContain('wa.me/?')
  })

  it('leva a frase inteira, nao so o link', () => {
    const href = whatsAppShareHref('Meu pedido WEB-1 https://nelson/pedido/WEB-1')

    expect(new URL(href).searchParams.get('text'))
      .toBe('Meu pedido WEB-1 https://nelson/pedido/WEB-1')
  })

  it('sem mensagem nao oferece link', () => {
    expect(whatsAppShareHref('   ')).toBe('')
  })
})

describe('URL compartilhada do pedido', () => {
  it('e canonica: sem a query string da sessao', () => {
    // `window.location.href` levava `?channel=…` junto — o cliente compartilhava
    // o proprio contexto de navegacao sem querer.
    expect(orderShareUrl('https://nelson.com.br', 'WEB-260801-A86'))
      .toBe('https://nelson.com.br/pedido/WEB-260801-A86')
  })

  it('nao duplica a barra da origem', () => {
    expect(orderShareUrl('https://nelson.com.br/', 'WEB-1')).toBe('https://nelson.com.br/pedido/WEB-1')
  })

  it('sem origem (SSR) nao inventa link', () => {
    expect(orderShareUrl('', 'WEB-1')).toBe('')
  })
})
