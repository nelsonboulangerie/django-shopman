// A página do entregador da casa (DEV-2026-030, frente M2): o que cada tela diz.
//
// Telas aprovadas pelo dono em 16/11/2026 (plano `docs/plans/DELIVERY-MULTI-SERVICE-PLAN.md`
// §4.4 e §4.5.2). Hiperfoco: uma tela por momento, e a tela muda sozinha quando o momento
// muda. O servidor diz o momento (`moment` de `own_fleet.ride_view`); a página só acrescenta
// o que é do celular e não do pedido: "Cheguei" (a tela da porta), o Desfazer de 10 s, as
// folhas de Problema e o aviso de cancelado já lido.
//
// Puro de propósito: tudo que vira texto na tela sai daqui, e o teste cobra a frase.

import { formatClock } from '~/utils/clock'

// ── O contrato da API (`/api/v1/courier/rides/<token>/`) ─────────────────────

export type CourierMoment =
  | 'confirm'
  | 'pickup'
  | 'pickup_wait'
  | 'route'
  | 'back'
  | 'closed'
  | 'cancelled'
  | 'reassigned'
  | 'unknown'
  | 'bad_device'
  | 'other_device'

export type StopState = 'open' | 'done' | 'cancelled'
export type PaidOther = '' | 'card' | 'pix' | 'cash'

export interface CourierStop {
  ref: string
  code: string
  name: string
  street: string
  complement: string
  neighborhood: string
  instructions: string
  bags: number
  ready: boolean
  state: StopState
  receive: {
    cash_q: number
    card_q: number
    pays_with_q: number
    change_back_q: number
    paid_other: PaidOther
  }
  lat: number | null
  lng: number | null
  phone?: string
  /** "HH:MM", a previsão de pronto da Cozinha (`kitchen_eta.ready_eta`, #2647); some sem previsão. */
  ready_at?: string
}

export interface CourierRideView {
  moment: CourierMoment
  courier?: string
  ride_ref?: string
  label?: string
  letter?: string
  value_q?: number | null
  today_q?: number
  stops?: CourierStop[]
  machine?: string
  settle?: { cash_q: number, machine: string, bags_back: string[] }
  detail?: string
  /** A observação da loja para esta corrida (escrita no Gestor, ao enviar). */
  note?: string
  /** O tema gravado no cadastro do entregador (#2648): o celular novo já abre nele. */
  theme?: CourierTheme
}

/** O recado da loja para a corrida, sem espaços sobrando; vazio quando não há. */
export function storeNote (view: CourierRideView | null | undefined): string {
  return (view?.note || '').trim()
}

// ── O que a página escolhe mostrar ───────────────────────────────────────────

export type CourierScreen =
  | 'loading'
  | 'home'
  | 'confirm'
  | 'pickup'
  | 'pickup_wait'
  | 'drive'
  | 'door'
  | 'no_answer'
  | 'back'
  | 'closed'
  | 'cancelled'
  | 'stop_cancelled'
  | 'refused'

/** O que o celular sabe e o servidor não. */
export interface CourierLocal {
  /** A parada em que ele tocou "Cheguei". */
  arrivedRef?: string | null
  /** A parada do "Ninguém atendeu", enquanto a loja liga. */
  noAnswerRef?: string | null
  /** Códigos cancelados que ele já leu ("Entendi"). */
  seenCancelled?: readonly string[]
  /** Ele já leu a rota fechada (ou o cancelamento inteiro): volta à tela inicial. */
  seenEnd?: boolean
}

export function openStops (view: CourierRideView): CourierStop[] {
  return (view.stops || []).filter(stop => stop.state === 'open')
}

/** A próxima parada: a primeira aberta, na ordem da rota. */
export function nextStop (view: CourierRideView): CourierStop | null {
  return openStops(view)[0] || null
}

/** O pedido cancelado com ele na rua e que ele ainda não leu: passa na frente de tudo. */
export function unseenCancelledStop (view: CourierRideView, local: CourierLocal = {}): CourierStop | null {
  if (view.moment !== 'route' && view.moment !== 'back') return null
  const seen = new Set(local.seenCancelled || [])
  return (view.stops || []).find(stop => stop.state === 'cancelled' && !seen.has(stop.code)) || null
}

export function screenFor (view: CourierRideView | null, local: CourierLocal = {}): CourierScreen {
  if (!view) return 'loading'
  switch (view.moment) {
    case 'confirm':
      return 'confirm'
    case 'pickup':
    case 'pickup_wait':
      return view.moment
    case 'route': {
      if (unseenCancelledStop(view, local)) return 'stop_cancelled'
      const open = openStops(view)
      if (local.noAnswerRef && open.some(stop => stop.ref === local.noAnswerRef)) return 'no_answer'
      if (local.arrivedRef && open.some(stop => stop.ref === local.arrivedRef)) return 'door'
      return open.length ? 'drive' : 'back'
    }
    case 'back':
      return unseenCancelledStop(view, local) ? 'stop_cancelled' : 'back'
    case 'closed':
      return local.seenEnd ? 'home' : 'closed'
    case 'cancelled':
      return local.seenEnd ? 'home' : 'cancelled'
    case 'reassigned':
      return 'home'
    default:
      return 'refused'
  }
}

/** Hiperfoco: tema e "Adicionar à tela inicial" só existem fora da corrida. */
export function showsSettings (screen: CourierScreen): boolean {
  return screen === 'home'
}

// ── Dinheiro, hora e contagem ────────────────────────────────────────────────

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })

/** Centavos (`_q`) em reais: "R$ 58,00". Sempre centavos, nunca reais. */
export function money (amountQ: number | null | undefined): string {
  const value = Number.isFinite(amountQ) ? Number(amountQ) : 0
  return BRL.format(value / 100).replace(/\s/gu, ' ')
}

export function bagsText (bags: number): string {
  if (!bags || bags < 1) return ''
  return bags === 1 ? '1 sacola' : `${bags} sacolas`
}

export function remainingText (count: number): string {
  return count === 1 ? 'Falta 1' : `Faltam ${count}`
}

/** "Maquininha Azul", com o nome que o balcão deu. Nunca repete a palavra. */
export function machineText (machine: string | null | undefined): string {
  const label = (machine || '').trim()
  if (!label) return ''
  return /^maquininha\b/i.test(label) ? `Maquininha ${label.replace(/^maquininha\s*/i, '')}`.trim() : `Maquininha ${label}`
}

function machineLower (machine: string | null | undefined): string {
  const text = machineText(machine)
  return text ? `m${text.slice(1)}` : 'maquininha'
}

// ── As telas ─────────────────────────────────────────────────────────────────

/** "Rota A" ou "Pedido B12": o nome que o entregador conhece. */
export function rideName (view: CourierRideView): string {
  return view.label || 'Corrida'
}

export interface PickupBlock {
  code: string
  /** "Pronto", "Fica pronto às 12h48", "Ainda não ficou pronto" ou "Cancelado". */
  status: string
  /** O status pesa como o fato (18) quando é o que segura a saída. */
  statusStrong: boolean
  lines: string[]
}

export function pickupBlocks (view: CourierRideView): PickupBlock[] {
  return (view.stops || []).map((stop) => {
    if (stop.state === 'cancelled') {
      return { code: stop.code, status: 'Cancelado', statusStrong: true, lines: ['Deixe no balcão. Não leve.'] }
    }
    const lines: string[] = []
    const bags = bagsText(stop.bags)
    if (bags) lines.push(bags)
    if (stop.receive.change_back_q > 0) lines.push(`Troco ${money(stop.receive.change_back_q)}`)
    if (stop.receive.card_q > 0) lines.push(machineText(view.machine) || 'Maquininha')
    const readyAt = formatClock(stop.ready_at || '')
    const status = stop.ready ? 'Pronto' : readyAt ? `Fica pronto às ${readyAt}` : 'Ainda não ficou pronto'
    return { code: stop.code, status, statusStrong: !stop.ready, lines }
  })
}

/** A arrumação da bag: o último a entregar no fundo, o primeiro por cima. */
export function bagTip (view: CourierRideView): string {
  const live = (view.stops || []).filter(stop => stop.state !== 'cancelled')
  if (live.length < 2) return ''
  const first = live[0]!.code
  const last = live[live.length - 1]!.code
  return `Dica: ${last} no fundo, ${first} por cima. ${first} é a primeira entrega.`
}

/** No balcão esperando: quem segura a saída. */
export function waitText (view: CourierRideView): string {
  const waiting = (view.stops || []).filter(stop => stop.state !== 'cancelled' && !stop.ready).map(stop => stop.code)
  if (!waiting.length) return ''
  if (waiting.length === 1) return `Espere ${waiting[0]} ficar pronto`
  return `Espere ${waiting.slice(0, -1).join(', ')} e ${waiting[waiting.length - 1]} ficarem prontos`
}

export interface MoneyBlock {
  label: string
  amount: string
  note: string
}

/** O que receber na porta. Lista vazia quando já está pago. */
export function doorMoney (stop: CourierStop, machine: string | null | undefined): MoneyBlock[] {
  const blocks: MoneyBlock[] = []
  const receive = stop.receive
  if (receive.cash_q > 0) {
    const note = receive.pays_with_q > receive.cash_q
      ? `${stop.name || 'O cliente'} paga com ${money(receive.pays_with_q)}. Devolva ${money(receive.change_back_q)}.`
      : 'Sem troco.'
    blocks.push({ label: 'Receber em dinheiro', amount: money(receive.cash_q), note })
  }
  if (receive.card_q > 0) {
    const label = receive.paid_other === 'pix' ? 'Receber no Pix' : 'Receber no cartão'
    blocks.push({ label, amount: money(receive.card_q), note: `Na ${machineLower(machine)}.` })
  }
  return blocks
}

export function quoted (text: string | null | undefined): string {
  const clean = (text || '').trim().replace(/^["“]+|["”]+$/g, '')
  return clean ? `“${clean}”` : ''
}

/** A linha de endereço que cabe embaixo do nome, na porta. */
export function doorPlace (stop: CourierStop): string {
  return [stop.street, stop.neighborhood].filter(Boolean).join(' · ')
}

// ── Navegação externa ────────────────────────────────────────────────────────

function hasPoint (stop: CourierStop): boolean {
  return Number.isFinite(stop.lat) && Number.isFinite(stop.lng) && stop.lat !== null && stop.lng !== null
}

function addressQuery (stop: CourierStop): string {
  return encodeURIComponent([stop.street, stop.neighborhood].filter(Boolean).join(', '))
}

export function wazeUrl (stop: CourierStop): string {
  if (hasPoint(stop)) return `https://waze.com/ul?ll=${stop.lat},${stop.lng}&navigate=yes`
  return `https://waze.com/ul?q=${addressQuery(stop)}&navigate=yes`
}

export function mapsUrl (stop: CourierStop): string {
  const destination = hasPoint(stop) ? `${stop.lat},${stop.lng}` : addressQuery(stop)
  return `https://www.google.com/maps/dir/?api=1&destination=${destination}&travelmode=driving`
}

export function telUrl (phone: string | null | undefined): string {
  const digits = (phone || '').replace(/[^\d+]/g, '')
  return digits ? `tel:${digits}` : ''
}

// ── As folhas da porta ───────────────────────────────────────────────────────

export const PROBLEM_CASES = [
  { kind: 'other_payment', label: 'Pagou de outro jeito' },
  { kind: 'no_answer', label: 'Ninguém atendeu' },
  { kind: 'address_not_found', label: 'Não achei o endereço' },
  { kind: 'refused', label: 'Recusou o pedido' },
  { kind: 'order_problem', label: 'Pedido com problema' }
] as const

export type ProblemKind = typeof PROBLEM_CASES[number]['kind']

export function paymentChoices (machine: string | null | undefined) {
  const where = machineLower(machine)
  return [
    { payment: 'card', label: `No cartão, na ${where}` },
    { payment: 'pix', label: `No Pix, na ${where}` },
    { payment: 'cash', label: 'Em dinheiro' }
  ] as const
}

/** O aviso que passa na frente depois de um caso que não muda a tela. */
export function problemAck (kind: ProblemKind, stop: CourierStop): string {
  if (kind === 'other_payment') return 'Pronto. A cobrança mudou.'
  return `A loja já sabe e vai ligar para ${stop.name || 'o cliente'}.`
}

/** O apoio da folha "Qual o problema?". */
export function problemNote (stop: CourierStop): string {
  return `A loja fica sabendo na hora e liga para ${stop.name || 'o cliente'}.`
}

// ── Acerto e fecho ───────────────────────────────────────────────────────────

export function settleBlocks (view: CourierRideView): string[][] {
  const blocks: string[][] = []
  const settle = view.settle
  if (settle && settle.cash_q > 0) blocks.push(['Dinheiro', money(settle.cash_q)])
  const machine = machineText(settle?.machine || view.machine)
  if (machine) blocks.push([machine])
  const back = settle?.bags_back || []
  if (back.length) blocks.push([back.length === 1 ? `Sacola de ${back[0]}` : `Sacolas de ${back.join(', ')}`])
  return blocks
}

export function closedTitle (view: CourierRideView): string {
  const label = rideName(view)
  return label.startsWith('Pedido') ? `${label} fechado` : `${label} fechada`
}

export function earnedText (valueQ: number | null | undefined): string {
  return valueQ ? `${money(valueQ)} para você.` : ''
}

export function todayText (todayQ: number | null | undefined): string {
  return `A receber hoje: ${money(todayQ || 0)}`
}

/** O que dizer quando o link recusa. A frase do servidor vence, se veio. */
export function refusalText (view: CourierRideView): { title: string, note: string } {
  if (view.moment === 'other_device') {
    return {
      title: view.detail || 'Esta rota está aberta em outro celular.',
      note: 'Trocou de celular? Peça ao balcão para soltar o link.'
    }
  }
  if (view.moment === 'bad_device') {
    return { title: view.detail || 'Abra o link pelo navegador do celular.', note: 'Toque em abrir no navegador e tente de novo.' }
  }
  return { title: view.detail || 'Este link não existe.', note: 'Peça ao balcão o link da rota.' }
}

// ── A cor da rota (só no quadrado da letra) ──────────────────────────────────

// As mesmas seis cores das corridas do Gestor (`orders-nuxt/app/presentation/ridePalette.ts`,
// dono 14/11 e 16/11). A loja builda sozinha e não estende o operator-kit, então a lista
// mora aqui também; a ordem é a mesma e a letra escolhe a cor (A é a primeira).
export const RIDE_COLORS: ReadonlyArray<{ bg: string, fg: string }> = [
  { bg: '#0047ff', fg: '#ffffff' },
  { bg: '#008933', fg: '#ffffff' },
  { bg: '#ffd000', fg: '#000000' },
  { bg: '#ff5a00', fg: '#000000' },
  { bg: '#e4007c', fg: '#ffffff' },
  { bg: '#111111', fg: '#ffffff' }
]

export function rideTone (letter: string | null | undefined): { bg: string, fg: string } | null {
  const code = (letter || '').trim().toUpperCase().charCodeAt(0)
  if (!(code >= 65 && code <= 90)) return null
  return RIDE_COLORS[(code - 65) % RIDE_COLORS.length]!
}

// ── Tema da página (só na tela inicial) ──────────────────────────────────────

export type CourierTheme = 'light' | 'dark' | 'system'

export const THEME_CHOICES: ReadonlyArray<{ value: CourierTheme, label: string }> = [
  { value: 'light', label: 'Claro' },
  { value: 'dark', label: 'Escuro' },
  { value: 'system', label: 'Do celular' }
]

export function parseTheme (value: string | null | undefined): CourierTheme {
  return value === 'light' || value === 'dark' ? value : 'system'
}

/**
 * O tema do cadastro que a página adota (#2648), ou `null` para manter o deste celular.
 *
 * O cadastro manda quando MUDA (a primeira leitura, ou a escolha feita em outro celular),
 * não a cada releitura: uma escolha que não chegou ao servidor (sem sinal) não volta atrás
 * na releitura seguinte.
 */
export function themeToAdopt (server: string | null | undefined, lastServer: string): CourierTheme | null {
  if (!server || server === lastServer) return null
  return parseTheme(server)
}

// ── O Desfazer ───────────────────────────────────────────────────────────────

export const UNDO_SECONDS = 10

export interface PendingDelivery {
  token: string
  orderRef: string
  code: string
  at: number
}

/** O "Entreguei" guardado: vai ao servidor quando o Desfazer vence, mesmo se a página fechou. */
export function pendingIsDue (pending: PendingDelivery, now: number): boolean {
  return now - pending.at >= UNDO_SECONDS * 1000
}

export function parsePending (raw: string | null): PendingDelivery | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as Partial<PendingDelivery>
    if (typeof value.token !== 'string' || typeof value.orderRef !== 'string' || typeof value.at !== 'number') return null
    return { token: value.token, orderRef: value.orderRef, code: String(value.code || ''), at: value.at }
  } catch {
    return null
  }
}

// ── A chave do celular ───────────────────────────────────────────────────────

/** 32 bytes aleatórios em base64url (43 caracteres). O servidor guarda só o hash. */
export function newDeviceKey (random: (bytes: Uint8Array<ArrayBuffer>) => Uint8Array<ArrayBuffer>): string {
  const bytes = random(new Uint8Array(32))
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}
