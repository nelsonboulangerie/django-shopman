import type { CartItemProjection, CartProjection, ProductMutationMeta, SubstituteProjection } from '~/types/shopman'

// Transforms puros para escrita otimista do carrinho. Linhas (qty, total da linha,
// contagem) mudam na hora; o resumo (subtotal, descontos, total geral) é
// autoritativo do servidor e fica marcado como summary_pending até a reconciliação.

export const OPTIMISTIC_LINE_PREFIX = 'optimistic-'

export function formatCentavos (amountQ: number): string {
  const display = (amountQ / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
  return display.replace(/\u00A0/g, ' ')
}

export function isOptimisticLine (line: CartItemProjection): boolean {
  return line.line_id.startsWith(OPTIMISTIC_LINE_PREFIX)
}

// Observação por item (meta.notes da linha): teto do backend.
export const LINE_NOTES_MAX_LENGTH = 280

export type LineNoteCloseIntent = 'close' | 'save' | 'confirm-discard'

// O que fazer quando a folha da observação fecha por gesto (X, alça, fundo, Esc).
// Fechar não pede para salvar: texto alterado e válido segue para o servidor em
// segundo plano. Texto apagado não é remoção por gesto (remover é ato explícito),
// então pergunta antes de jogar fora. Sem alteração, só fecha.
export function lineNoteCloseIntent (draft: string, saved: string | null | undefined): LineNoteCloseIntent {
  const next = draft.trim()
  const current = (saved || '').trim()
  if (next === current) return 'close'
  if (next && next.length <= LINE_NOTES_MAX_LENGTH) return 'save'
  return 'confirm-discard'
}

function optimisticLine (meta: ProductMutationMeta, qty: number): CartItemProjection {
  return {
    line_id: `${OPTIMISTIC_LINE_PREFIX}${meta.sku}`,
    sku: meta.sku,
    name: meta.name,
    qty,
    unit_price_q: meta.price_q,
    total_price_q: meta.price_q * qty,
    price_display: meta.price_display,
    total_display: formatCentavos(meta.price_q * qty),
    image_url: meta.image_url,
    discount_label: null,
    promo_price_display: null,
    is_available: true,
    availability_warning: null,
    available_qty: null,
    // Linha otimista nasce disponível; o sino é resposta do servidor.
    is_notifiable: false,
    is_notify_subscribed: false,
    is_made_to_order: false,
    made_to_order_label: '',
    is_awaiting_confirmation: false,
    is_ready_for_confirmation: false,
    confirmation_deadline_iso: null,
    confirmation_deadline_display: null,
    planned_for_date: null,
    planned_for_notice: null,
    earlier_available_date: null,
    notes: ''
  }
}

function withQty (line: CartItemProjection, qty: number): CartItemProjection {
  return {
    ...line,
    qty,
    total_price_q: line.unit_price_q * qty,
    total_display: formatCentavos(line.unit_price_q * qty)
  }
}

export function cartItemsCount (items: CartItemProjection[]): number {
  return items.reduce((total, line) => total + line.qty, 0)
}

// Preço por unidade da linha, na mesma dupla do cardápio: com promoção, o cheio
// riscado (`original`) e o da promoção (`current`); sem promoção, só o cheio.
// O total da linha segue cheio, para a soma das linhas fechar com o Subtotal.
export function linePrice (line: Pick<CartItemProjection, 'price_display' | 'promo_price_display'>): { original: string | null, current: string } {
  const promo = line.promo_price_display?.trim()
  return promo && promo !== line.price_display
    ? { original: line.price_display, current: promo }
    : { original: null, current: line.price_display }
}

// Planned-hold (AVAILABILITY-PLAN §8): a linha ou aguarda confirmação da
// produção planejada ('awaiting') ou o estoque materializou e o cliente
// precisa confirmar antes do TTL ('ready'). Timeouts são transparentes:
// deadline explícito + countdown vivo.

// 'reserved': a linha segura reserva planejada, mas o pedido não entra em fila
// na data em que ele vai sair (data anterior com saldo, ou pedido para depois
// da fornada). Mesma regra de `reviewWaitlist`: sem selo de espera nem
// "Previsto para", e a linha também não aparece como indisponível.
export type CartLineHold = {
  kind: 'awaiting' | 'ready' | 'reserved'
  deadlineIso: string | null
  deadlineDisplay: string | null
  plannedForNotice: string | null
}

type HoldFields = Pick<CartItemProjection, 'is_awaiting_confirmation' | 'is_ready_for_confirmation' | 'confirmation_deadline_iso' | 'confirmation_deadline_display' | 'planned_for_notice'>
  & Partial<Pick<CartItemProjection, 'planned_for_date' | 'earlier_available_date'>>

/** O estado de reserva da linha na sacola. `deliveryDate` é a data em que o
 *  pedido vai sair: na sacola, ainda sem escolha, é o piso que o checkout vai
 *  pré-selecionar (`cartBatchFloor`). A espera segue a MESMA regra da revisão
 *  (`reviewWaitlist`): o "Previsto para sexta" não pode aparecer na sacola e
 *  sumir no "Finalizar" para a mesma data (beta 09/11). */
export function lineHoldState (
  line: HoldFields,
  deliveryDate: string = '',
  today: string = new Date().toLocaleDateString('en-CA')
): CartLineHold | null {
  // ⚠️ Havia aqui um `if (line.is_made_to_order) return null`, e ele passou a
  // ESCONDER FILA DE VERDADE quando os dois eixos foram separados.
  //
  // Enquanto o selo era deduzido de `demand_ok`, "preparado na hora" servia de
  // atalho para "não há fornada envolvida" — e a guarda parecia inofensiva.
  // Agora o selo é promessa declarada da casa (`Product.metadata.made_to_order`)
  // e a fila é estado do hold: um croque que espera a fornada de amanhã é as
  // duas coisas. Calar a espera porque o item é preparado na hora tiraria da
  // tela justamente o "quando".
  if (line.is_ready_for_confirmation) {
    return { kind: 'ready', deadlineIso: line.confirmation_deadline_iso, deadlineDisplay: line.confirmation_deadline_display, plannedForNotice: null }
  }
  if (line.is_awaiting_confirmation) {
    const wait = reviewWaitlist({ ...line, planned_for_date: line.planned_for_date ?? null }, deliveryDate, today)
    if (!wait) return { kind: 'reserved', deadlineIso: null, deadlineDisplay: null, plannedForNotice: null }
    return { kind: 'awaiting', deadlineIso: null, deadlineDisplay: null, plannedForNotice: wait.notice || null }
  }
  return null
}

/** Lista de espera na REVISÃO do pedido: a história inteira (badge + data
 *  prevista + "avisamos quando ficarem prontos") vale quando o pedido é para o
 *  MESMO dia da fornada que o hold da sacola espera. Pedido agendado para
 *  DEPOIS da fornada não tem fila: o commit re-ancora a reserva na data com
 *  prioridade de pedido (WP-C), e o badge de espera contradiria o "Quando".
 *  Pedido para ANTES da fornada (retirar hoje o pão de quarta) não cala: a
 *  data prevista fica à vista, porque é ela que diz que o "Quando" está errado
 *  (o servidor recusa esse pedido). A exceção é a data anterior que já tem
 *  saldo para a linha (`earlier_available_date`): aí o pedido leva o pão dessa
 *  data, sem fila. Retorna null (sem história de espera) ou o
 *  notice da fornada (pode ser string vazia quando não há data a mostrar). */
export function reviewWaitlist (
  line: Pick<CartItemProjection, 'is_awaiting_confirmation' | 'planned_for_date' | 'planned_for_notice'>
    & Partial<Pick<CartItemProjection, 'earlier_available_date'>>,
  deliveryDate: string,
  today: string = new Date().toLocaleDateString('en-CA')
): { notice: string } | null {
  // Sem guarda por `is_made_to_order`, pela mesma razão de `lineHoldState`: os
  // dois eixos são independentes, e a espera é o dado que o cliente precisa
  // para decidir. Quem manda calar aqui é a DATA, não a natureza do item.
  if (!line.is_awaiting_confirmation) return null
  const batchDate = line.planned_for_date || today
  if (deliveryDate && deliveryDate > batchDate) return null
  const earlier = line.earlier_available_date || ''
  if (earlier && (deliveryDate || today) >= earlier && (deliveryDate || today) < batchDate) return null
  return { notice: line.planned_for_notice || '' }
}

/** A primeira data em que a sacola inteira pode sair, com o item que a segura.
 *  Um pedido, uma data: o pedido não pode ser para antes dela. Por linha vale
 *  a fornada que ela espera, ou a data anterior que já tem saldo para ela
 *  (`earlier_available_date`). `null` quando nenhuma linha segura o pedido
 *  para depois de hoje. */
export function cartBatchFloor (
  items: Array<Pick<CartItemProjection, 'name' | 'planned_for_date'> & Partial<Pick<CartItemProjection, 'earlier_available_date'>>>,
  today: string = new Date().toLocaleDateString('en-CA')
): { date: string, name: string } | null {
  let floor: { date: string, name: string } | null = null
  for (const item of items) {
    const date = item.earlier_available_date || item.planned_for_date || ''
    if (date > today && (!floor || date > floor.date)) floor = { date, name: item.name }
  }
  return floor
}

const BATCH_WEEKDAYS = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado']

/** "amanhã, 10/11" / "na quarta, 11/11" / "no sábado, 14/11". */
export function batchDayPhrase (date: string, today: string = new Date().toLocaleDateString('en-CA')): string {
  const [year, month, day] = date.split('-').map(Number)
  if (!year || !month || !day) return ''
  const stamp = `${String(day).padStart(2, '0')}/${String(month).padStart(2, '0')}`
  const value = new Date(year, month - 1, day)
  const [ty, tm, td] = today.split('-').map(Number)
  const tomorrow = new Date(ty || year, (tm || month) - 1, (td || day) + 1)
  if (value.getTime() === tomorrow.getTime()) return `amanhã, ${stamp}`
  const weekday = value.getDay()
  const article = weekday === 0 || weekday === 6 ? 'no' : 'na'
  return `${article} ${BATCH_WEEKDAYS[weekday]}, ${stamp}`
}

/** Por que as datas antes da fornada estão desabilitadas, numa frase:
 *  "Kuro Pan sai na quarta, 11/11. Antes disso, não dá para retirar." */
export function cartBatchFloorReason (
  floor: { date: string, name: string } | null,
  fulfillmentType: string,
  today: string = new Date().toLocaleDateString('en-CA')
): string {
  if (!floor || floor.date <= today) return ''
  const when = batchDayPhrase(floor.date, today)
  if (!when) return ''
  const verb = fulfillmentType === 'delivery' ? 'receber' : 'retirar'
  return `${floor.name} sai ${when}. Antes disso, não dá para ${verb}.`
}

export function holdCountdown (deadlineIso: string | null | undefined, nowMs: number): { totalSeconds: number, display: string } | null {
  if (!deadlineIso) return null
  const deadline = Date.parse(deadlineIso)
  if (Number.isNaN(deadline)) return null
  const totalSeconds = Math.max(0, Math.floor((deadline - nowMs) / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const pad = (value: number) => String(value).padStart(2, '0')
  return {
    totalSeconds,
    display: hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${pad(minutes)}:${pad(seconds)}`
  }
}

export type CartHoldBanner =
  | { kind: 'ready', deadlineIso: string | null, deadlineDisplay: string | null }
  | { kind: 'awaiting' }

export function cartHoldBanner (cart: Pick<CartProjection, 'has_ready_for_confirmation_items' | 'has_awaiting_confirmation_items' | 'items'>): CartHoldBanner | null {
  if (cart.has_ready_for_confirmation_items) {
    const ready = cart.items
      .filter(line => line.is_ready_for_confirmation && line.confirmation_deadline_iso)
      .sort((a, b) => Date.parse(a.confirmation_deadline_iso!) - Date.parse(b.confirmation_deadline_iso!))
    const first = ready[0] || cart.items.find(line => line.is_ready_for_confirmation)
    return { kind: 'ready', deadlineIso: first?.confirmation_deadline_iso || null, deadlineDisplay: first?.confirmation_deadline_display || null }
  }
  if (cart.has_awaiting_confirmation_items) return { kind: 'awaiting' }
  return null
}

// Cor segue a semântica do estado (semáforo): "tudo pronto" é positivo (success);
// "aguardando confirmação" é um estado de espera/atenção (warning). Sem hardcode
// de variant no template — a cor é derivada do kind.
export function holdBannerVariant (banner: CartHoldBanner | null): 'success' | 'warning' | null {
  if (!banner) return null
  return banner.kind === 'ready' ? 'success' : 'warning'
}

// Swap de substituto em 1 toque: traduz a alternativa numa escrita de carrinho.
// Espelha o docstring do backend (substitutes.py::_target_qty): a quantidade é
// target_qty quando vier; senão min(pedido, disponível); piso 1 para o botão
// sempre fazer algo útil. Retorna null quando não há ação (não-ordenável/sem sku).
export function substituteSwapPlan (
  sub: SubstituteProjection,
  requestedQty: number | null
): { meta: ProductMutationMeta, qty: number } | null {
  if (!sub?.can_order || !sub.sku) return null

  let qty: number
  if (sub.target_qty != null && sub.target_qty > 0) {
    qty = sub.target_qty
  } else {
    const ceiling = sub.available_qty != null ? sub.available_qty : Infinity
    qty = Math.min(requestedQty ?? 1, ceiling)
  }
  qty = Math.max(1, Math.floor(qty))

  return {
    meta: {
      sku: sub.sku,
      name: sub.name,
      price_q: sub.price_q,
      price_display: sub.price_display ?? '',
      image_url: sub.image_url ?? null
    },
    qty
  }
}

// O PUT por SKU mexe na linha SEM opções daquele SKU; linha com opções só muda
// pela `line_id` (applyLineQty), então o otimista também não encosta nela.
function isPlainSkuLine (line: CartItemProjection, sku: string): boolean {
  return line.sku === sku && !line.has_options
}

export function applySkuQty (cart: CartProjection, meta: ProductMutationMeta, qty: number): CartProjection {
  const hasLine = cart.items.some(line => isPlainSkuLine(line, meta.sku))
  let items: CartItemProjection[]
  if (qty <= 0) {
    items = cart.items.filter(line => !isPlainSkuLine(line, meta.sku))
  } else if (hasLine) {
    items = cart.items.map(line => (isPlainSkuLine(line, meta.sku) ? withQty(line, qty) : line))
  } else {
    items = [...cart.items, optimisticLine(meta, qty)]
  }
  return withItems(cart, items)
}

// Linha já gravada muda pela `line_id`: o mesmo SKU pode estar em duas linhas
// (Croque com ovo e Croque sem ovo), e o PUT por SKU acertaria a errada.
export function applyLineQty (cart: CartProjection, lineId: string, qty: number): CartProjection {
  const items = qty <= 0
    ? cart.items.filter(line => line.line_id !== lineId)
    : cart.items.map(line => (line.line_id === lineId ? withQty(line, qty) : line))
  return withItems(cart, items)
}

function withItems (cart: CartProjection, items: CartItemProjection[]): CartProjection {
  const itemsCount = cartItemsCount(items)
  return {
    ...cart,
    items,
    items_count: itemsCount,
    is_empty: itemsCount === 0,
    summary_pending: true
  }
}

/** Quantas unidades do SKU a sacola tem, somando todas as linhas dele. */
export function cartQtyForSku (items: ReadonlyArray<Pick<CartItemProjection, 'sku' | 'qty'>>, sku: string): number {
  return items.reduce((total, line) => (line.sku === sku ? total + line.qty : total), 0)
}

/** A linha SEM opções do SKU (a que o stepper por SKU controla), ou 0. */
export function plainQtyForSku (items: ReadonlyArray<CartItemProjection>, sku: string): number {
  return items.find(line => isPlainSkuLine(line, sku))?.qty || 0
}
