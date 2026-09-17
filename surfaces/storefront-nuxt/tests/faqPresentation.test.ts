import { describe, expect, it } from 'vitest'
import { faqContactLinks, faqItems, telHref } from '~/presentation/faq'

describe('faqItems', () => {
  const home = [{ ref: 'home', question: 'Da home?', answer: 'Sim.' }]

  it('as perguntas do cadastro do site vencem', () => {
    const site = [{ ref: 'site', question: 'Do site?', answer: 'Sim.' }]
    expect(faqItems(site, home)).toEqual(site)
  })

  it('sem o endpoint (ou lista vazia), a página usa as da home', () => {
    expect(faqItems(null, home)).toEqual(home)
    expect(faqItems([], home)).toEqual(home)
    expect(faqItems([{ ref: 'x', question: 'Sem resposta?', answer: ' ' }], home)).toEqual(home)
  })

  it('nada nos dois lados: lista vazia (a página mostra o estado vazio)', () => {
    expect(faqItems(undefined, undefined)).toEqual([])
  })
})

describe('telHref', () => {
  it('mantém só dígitos e o +', () => {
    expect(telHref('+55 43 3323-1997')).toBe('tel:+554333231997')
    expect(telHref('   ')).toBe('')
  })
})

describe('faqContactLinks', () => {
  it('cadastro do site vence; WhatsApp, telefone e e-mail na ordem', () => {
    const links = faqContactLinks({
      business: { telephone: '+55 43 3323-1997', email: 'nelson@boulangerie.com.br' },
      shop: { phone: '4333231997', phone_display: '(43) 3323-1997', phone_url: 'tel:4333231997', email: 'outro@x.com', whatsapp_url: 'https://wa.me/loja' },
      whatsappUrl: 'https://wa.me/554333231997'
    })
    expect(links.map(link => [link.kind, link.value, link.href])).toEqual([
      ['whatsapp', 'Falar no WhatsApp', 'https://wa.me/554333231997'],
      ['phone', '+55 43 3323-1997', 'tel:+554333231997'],
      ['email', 'nelson@boulangerie.com.br', 'mailto:nelson@boulangerie.com.br']
    ])
  })

  it('sem cadastro do site, a loja cobre', () => {
    const links = faqContactLinks({
      business: null,
      shop: { phone: '4333231997', phone_display: '(43) 3323-1997', phone_url: 'tel:+554333231997', email: 'loja@x.com', whatsapp_url: 'https://wa.me/loja' }
    })
    expect(links.map(link => [link.kind, link.value, link.href])).toEqual([
      ['whatsapp', 'Falar no WhatsApp', 'https://wa.me/loja'],
      ['phone', '(43) 3323-1997', 'tel:+554333231997'],
      ['email', 'loja@x.com', 'mailto:loja@x.com']
    ])
  })

  it('canal que não existe não aparece', () => {
    expect(faqContactLinks({ business: { telephone: '', email: '' }, shop: null })).toEqual([])
  })
})
