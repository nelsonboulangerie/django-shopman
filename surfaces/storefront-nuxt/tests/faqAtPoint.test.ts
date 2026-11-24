// EXPERIMENT(duvida-no-ponto) remove_after 2027-02-20
// OC-33 B3: a dúvida respondida onde ela aparece. A escolha de qual pergunta mora em
// cada ponto, e a prova de que a resposta é a MESMA da FAQ (mesmo objeto do shell).
import { describe, expect, it } from 'vitest'
import { FAQ_AT_POINT, FAQ_AT_POINT_LIMIT, faqAtPoint } from '~/presentation/faqAtPoint'
import type { FAQItemProjection } from '~/types/shopman'

// O `shell.faq` como `build_public_faq` monta: operacionais primeiro, curadas depois.
const faq: FAQItemProjection[] = [
  { ref: 'delivery', question: 'Vocês fazem entrega?', answer: 'Sim. Fazemos entrega.' },
  { ref: 'hours', question: 'Quais são os horários de funcionamento?', answer: 'Aberto agora. Seg a sáb: 7h às 19h' },
  { ref: 'location', question: 'Onde vocês ficam?', answer: 'Ficamos na Rua X, 10.' },
  { ref: 'payment', question: 'Como posso pagar?', answer: 'Você paga com Pix, cartão ou dinheiro (na retirada ou na entrega).' },
  { ref: 'preorder', question: 'Posso encomendar para outro dia?', answer: 'Sim. Ao finalizar o pedido, você escolhe o dia, com até 30 dias de antecedência.' },
  { ref: 'allergens', question: 'Os produtos têm alérgenos?', answer: 'Produzimos em cozinha compartilhada. Os ingredientes de cada produto estão na página dele.' },
  { ref: 'contact', question: 'Como falar com vocês?', answer: 'Você pode falar conosco por telefone.' },
  { ref: 'curated-como-conservar', question: 'Como conservar o pão?', answer: 'Em saco de papel.' }
]

const refs = (items: FAQItemProjection[]) => items.map(item => item.ref)

describe('faqAtPoint', () => {
  it('sacola: entrega, horário e encomenda, nessa ordem', () => {
    expect(refs(faqAtPoint(faq, 'cart'))).toEqual(['delivery', 'hours', 'preorder'])
  })

  it('só a sacola tem ponto: nem pagamento (as opções já respondem) nem produto (o aviso já está na página)', () => {
    expect(Object.keys(FAQ_AT_POINT)).toEqual(['cart'])
    expect(refs(faqAtPoint(faq, 'cart'))).not.toContain('payment')
    expect(refs(faqAtPoint(faq, 'cart'))).not.toContain('allergens')
  })

  it('a pergunta e a resposta são as da FAQ, sem reescrita', () => {
    for (const item of faqAtPoint(faq, 'cart')) {
      expect(faq).toContain(item)
    }
  })

  it('pergunta que a loja não responde não aparece (encomenda desligada)', () => {
    const semEncomenda = faq.filter(item => item.ref !== 'preorder')
    expect(refs(faqAtPoint(semEncomenda, 'cart'))).toEqual(['delivery', 'hours'])
  })

  it('pergunta sem resposta, shell vazio ou ausente: nada', () => {
    expect(faqAtPoint([{ ref: 'delivery', question: 'Vocês fazem entrega?', answer: ' ' }], 'cart')).toEqual([])
    expect(faqAtPoint([], 'cart')).toEqual([])
    expect(faqAtPoint(undefined, 'cart')).toEqual([])
    expect(faqAtPoint(null, 'cart')).toEqual([])
  })

  it('nunca mais de três por ponto', () => {
    expect(faqAtPoint(faq, 'cart').length).toBeLessThanOrEqual(FAQ_AT_POINT_LIMIT)
    expect(FAQ_AT_POINT_LIMIT).toBe(3)
  })
})
