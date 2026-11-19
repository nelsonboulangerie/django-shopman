import { describe, expect, it } from 'vitest'

import {
  type CourierRideView,
  type CourierStop,
  bagTip,
  closedTitle,
  doorMoney,
  machineText,
  mapsUrl,
  money,
  newDeviceKey,
  parsePending,
  parseTheme,
  paymentChoices,
  pendingIsDue,
  pickupBlocks,
  problemAck,
  refusalText,
  remainingText,
  rideTone,
  screenFor,
  settleBlocks,
  showsSettings,
  telUrl,
  waitText,
  wazeUrl
} from '../app/presentation/courierRide'

// A página do entregador da casa (DEV-2026-030, M2): telas aprovadas pelo dono em 16/11/2026
// (plano DELIVERY-MULTI-SERVICE-PLAN §4.5.2). O teste cobra a frase que a tela mostra.

function stop (over: Partial<CourierStop> = {}): CourierStop {
  return {
    ref: 'ORD-A47',
    code: 'A47',
    name: 'Marina',
    street: 'Rua Caracas 420',
    complement: 'Torre 2 · Apto 41',
    neighborhood: 'Gleba Palhano',
    instructions: 'O interfone não funciona, me ligue que eu desço.',
    bags: 2,
    ready: true,
    state: 'open',
    receive: { cash_q: 5800, card_q: 0, pays_with_q: 10000, change_back_q: 4200, paid_other: '' },
    lat: -23.33,
    lng: -51.18,
    phone: '+55 43 99999-0000',
    ...over
  }
}

const c03 = stop({
  ref: 'ORD-C03',
  code: 'C03',
  name: 'Paulo',
  street: 'Rua Bélgica 155',
  complement: 'Casa de portão verde',
  bags: 1,
  receive: { cash_q: 0, card_q: 4200, pays_with_q: 0, change_back_q: 0, paid_other: '' }
})

function ride (over: Partial<CourierRideView> = {}): CourierRideView {
  return {
    moment: 'pickup',
    courier: 'Diego',
    ride_ref: 'R1',
    label: 'Rota A',
    letter: 'A',
    value_q: 1500,
    stops: [stop(), c03],
    machine: 'Azul',
    settle: { cash_q: 10000, machine: 'Azul', bags_back: [] },
    ...over
  }
}

describe('qual tela o momento abre', () => {
  it('cada momento do servidor tem a sua tela', () => {
    expect(screenFor(null)).toBe('loading')
    expect(screenFor(ride({ moment: 'confirm' }))).toBe('confirm')
    expect(screenFor(ride({ moment: 'pickup' }))).toBe('pickup')
    expect(screenFor(ride({ moment: 'pickup_wait' }))).toBe('pickup_wait')
    expect(screenFor(ride({ moment: 'route' }))).toBe('drive')
    expect(screenFor(ride({ moment: 'back' }))).toBe('back')
    expect(screenFor(ride({ moment: 'closed' }))).toBe('closed')
    expect(screenFor(ride({ moment: 'cancelled' }))).toBe('cancelled')
    expect(screenFor(ride({ moment: 'reassigned' }))).toBe('home')
    expect(screenFor({ moment: 'other_device' })).toBe('refused')
    expect(screenFor({ moment: 'unknown' })).toBe('refused')
  })

  it('"Cheguei" abre a porta só de uma parada aberta', () => {
    expect(screenFor(ride({ moment: 'route' }), { arrivedRef: 'ORD-A47' })).toBe('door')
    const done = ride({ moment: 'route', stops: [stop({ state: 'done' }), c03] })
    expect(screenFor(done, { arrivedRef: 'ORD-A47' })).toBe('drive')
  })

  it('"Ninguém atendeu" segura a espera até ele dizer que atendeu', () => {
    expect(screenFor(ride({ moment: 'route' }), { noAnswerRef: 'ORD-A47', arrivedRef: 'ORD-A47' })).toBe('no_answer')
  })

  it('o pedido cancelado na rua passa na frente de tudo até ele ler', () => {
    const view = ride({ moment: 'route', stops: [stop(), { ...c03, state: 'cancelled' }] })
    expect(screenFor(view, { arrivedRef: 'ORD-A47' })).toBe('stop_cancelled')
    expect(screenFor(view, { arrivedRef: 'ORD-A47', seenCancelled: ['C03'] })).toBe('door')
  })

  it('fechada e cancelada voltam à tela inicial depois de lidas', () => {
    expect(screenFor(ride({ moment: 'closed' }), { seenEnd: true })).toBe('home')
    expect(screenFor(ride({ moment: 'cancelled' }), { seenEnd: true })).toBe('home')
  })

  it('hiperfoco: configuração só na tela inicial', () => {
    expect(showsSettings('home')).toBe(true)
    for (const screen of ['confirm', 'pickup', 'pickup_wait', 'drive', 'door', 'back', 'closed', 'cancelled'] as const) {
      expect(showsSettings(screen)).toBe(false)
    }
  })
})

describe('no balcão', () => {
  it('um bloco por pedido: código, pronto, sacolas, troco e maquininha', () => {
    expect(pickupBlocks(ride())).toEqual([
      { code: 'A47', status: 'Pronto', statusStrong: false, lines: ['2 sacolas', 'Troco R$ 42,00'] },
      { code: 'C03', status: 'Pronto', statusStrong: false, lines: ['1 sacola', 'Maquininha Azul'] }
    ])
  })

  it('o que não está pronto diz a hora da casa, quando ela vier', () => {
    const view = ride({ moment: 'pickup_wait', stops: [stop(), { ...c03, ready: false, ready_at: '12:48' }] })
    expect(pickupBlocks(view)[1]!.status).toBe('Fica pronto às 12h48')
    expect(waitText(view)).toBe('Espere C03 ficar pronto')
    const noTime = ride({ stops: [stop({ ready: false }), { ...c03, ready: false }] })
    expect(pickupBlocks(noTime)[0]!.status).toBe('Ainda não ficou pronto')
    expect(waitText(noTime)).toBe('Espere A47 e C03 ficarem prontos')
  })

  it('a dica da bag: o último no fundo, o primeiro por cima', () => {
    expect(bagTip(ride())).toBe('Dica: C03 no fundo, A47 por cima. A47 é a primeira entrega.')
    expect(bagTip(ride({ stops: [stop()] }))).toBe('')
  })
})

describe('na porta', () => {
  it('dinheiro com troco: quanto receber e quanto devolver', () => {
    expect(doorMoney(stop(), 'Azul')).toEqual([
      { label: 'Receber em dinheiro', amount: 'R$ 58,00', note: 'Marina paga com R$ 100,00. Devolva R$ 42,00.' }
    ])
  })

  it('cartão na maquininha pelo nome', () => {
    expect(doorMoney(c03, 'Azul')).toEqual([
      { label: 'Receber no cartão', amount: 'R$ 42,00', note: 'Na maquininha Azul.' }
    ])
  })

  it('já pago: nada a receber', () => {
    expect(doorMoney(stop({ receive: { cash_q: 0, card_q: 0, pays_with_q: 0, change_back_q: 0, paid_other: '' } }), 'Azul')).toEqual([])
  })

  it('pagou no Pix pela maquininha', () => {
    const pix = stop({ receive: { cash_q: 0, card_q: 5800, pays_with_q: 0, change_back_q: 0, paid_other: 'pix' } })
    expect(doorMoney(pix, 'Azul')[0]!.label).toBe('Receber no Pix')
  })

  it('as folhas e os avisos', () => {
    expect(paymentChoices('Azul').map(choice => choice.label)).toEqual([
      'No cartão, na maquininha Azul',
      'No Pix, na maquininha Azul',
      'Em dinheiro'
    ])
    expect(problemAck('address_not_found', stop())).toBe('A loja já sabe e vai ligar para Marina.')
    expect(remainingText(1)).toBe('Falta 1')
    expect(remainingText(2)).toBe('Faltam 2')
  })

  it('Waze, mapa e telefone', () => {
    expect(wazeUrl(stop())).toBe('https://waze.com/ul?ll=-23.33,-51.18&navigate=yes')
    expect(mapsUrl(stop())).toBe('https://www.google.com/maps/dir/?api=1&destination=-23.33,-51.18&travelmode=driving')
    expect(wazeUrl(stop({ lat: null, lng: null }))).toContain('q=Rua%20Caracas%20420%2C%20Gleba%20Palhano')
    expect(telUrl('+55 43 99999-0000')).toBe('tel:+5543999990000')
    expect(telUrl('')).toBe('')
  })
})

describe('acerto, fecho e recusa', () => {
  it('entregue no caixa: dinheiro e maquininha', () => {
    expect(settleBlocks(ride({ moment: 'back' }))).toEqual([['Dinheiro', 'R$ 100,00'], ['Maquininha Azul']])
  })

  it('rota ou pedido fechado', () => {
    expect(closedTitle(ride())).toBe('Rota A fechada')
    expect(closedTitle(ride({ label: 'Pedido B12' }))).toBe('Pedido B12 fechado')
  })

  it('outro celular', () => {
    expect(refusalText({ moment: 'other_device', detail: 'Esta rota está aberta em outro celular.' }).title)
      .toBe('Esta rota está aberta em outro celular.')
  })
})

describe('peças', () => {
  it('dinheiro em centavos, sem espaço inquebrável', () => {
    expect(money(5800)).toBe('R$ 58,00')
    expect(money(123456)).toBe('R$ 1.234,56')
    expect(money(null)).toBe('R$ 0,00')
  })

  it('maquininha nunca repete a palavra', () => {
    expect(machineText('Azul')).toBe('Maquininha Azul')
    expect(machineText('Maquininha Azul')).toBe('Maquininha Azul')
    expect(machineText('')).toBe('')
  })

  it('a cor da rota vem da letra (A é a primeira)', () => {
    expect(rideTone('A')).toEqual({ bg: '#0047ff', fg: '#ffffff' })
    expect(rideTone('G')).toEqual({ bg: '#0047ff', fg: '#ffffff' })
    expect(rideTone('')).toBeNull()
  })

  it('tema lembrado, "Do celular" por padrão', () => {
    expect(parseTheme('dark')).toBe('dark')
    expect(parseTheme('light')).toBe('light')
    expect(parseTheme(null)).toBe('system')
  })

  it('o Entreguei guardado vence em 10 s', () => {
    const pending = { token: 't', orderRef: 'ORD-A47', code: 'A47', at: 1_000 }
    expect(pendingIsDue(pending, 10_999)).toBe(false)
    expect(pendingIsDue(pending, 11_000)).toBe(true)
    expect(parsePending(JSON.stringify(pending))).toEqual(pending)
    expect(parsePending('{broken')).toBeNull()
  })

  it('a chave do celular tem 43 caracteres base64url', () => {
    const key = newDeviceKey(bytes => bytes.fill(255))
    expect(key).toHaveLength(43)
    expect(key).toMatch(/^[A-Za-z0-9_-]+$/)
  })
})
