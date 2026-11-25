import { couponAppliedToast } from '~/utils/checkoutFlow'
import { applyLineQty, applySkuQty, cartQtyForSku, isOptimisticLine, substituteSwapPlan } from '~/presentation/cart'
import { serverClockOffsetMs } from '~/presentation/deadline'
import type { CartItemProjection, CartMutationResponse, CartProjection, CartTransferResponse, ProductMutationMeta, ProductOptionSelection, Action, SubstituteProjection } from '~/types/shopman'

export interface CartIssue {
  title: string
  detail: string
  error_code: string
  sku: string
  name: string
  requested_qty: number | null
  // Teto da LINHA (o que ela já segura + o livre), absoluto: é até onde o botão
  // "Levar N" leva a linha. Na linha nova coincide com o livre.
  available_qty: number | null
  // Quanto a linha tinha antes do pedido recusado (null = linha nova).
  line_qty: number | null
  // A linha que JÁ passou do teto (recusa do envio do pedido, #2687): o teto encolhe
  // ESTA linha e o substituto entra no lugar do que falta. null no 409 da sacola.
  line_id: string | null
  is_paused: boolean
  // Esgotado honesto e assinável: habilita o CTA "Me avise quando disponível" (WP-3).
  isNotifiable: boolean
  // "Me avise" já pedido por este viewer — o sino nasce em "Anotado", como no card.
  isNotifySubscribed: boolean
  is_planned: boolean
  planned_offer_title: string
  planned_offer_message: string
  shortage_title: string
  substitutes_intro: string
  substitutes: SubstituteProjection[]
  actions: Action[]
  items: Array<{
    sku: string
    name: string
    requested_qty: number | null
    available_qty: number | null
    reason: string
  }>
}

interface RateLimitRecovery {
  detail: string
  retryAfterSeconds: number | null
}

interface CartMutationSnapshot {
  meta: ProductMutationMeta
  qty: number
  // Linha já gravada: a mutação mira a `line_id` (PUT /cart/lines/<id>/).
  lineId?: string
  // Inclusão com escolhas: POST /cart/lines/ com estas opções; `qty` é quanto somar.
  options?: ProductOptionSelection[]
}

function isOptionErrorCode (code: unknown): boolean {
  return typeof code === 'string' && code.startsWith('option_')
}

/** A meta de mutação de uma linha da sacola (nome já com o resumo das escolhas). */
export function metaForCartLine (line: CartItemProjection): ProductMutationMeta {
  return {
    sku: line.sku,
    name: line.name,
    price_q: line.unit_price_q,
    price_display: line.price_display,
    image_url: line.image_url
  }
}

function emptyCart (): CartProjection {
  return {
    items: [],
    items_count: 0,
    is_empty: true,
    empty_title: '',
    empty_message: '',
    summary_pending: false,
    subtotal_q: 0,
    subtotal_display: 'R$ 0,00',
    original_subtotal_q: 0,
    discount_total_q: 0,
    discount_total_display: 'R$ 0,00',
    has_discount: false,
    discount_lines: [],
    lines_subtotal_q: 0,
    lines_subtotal_display: 'R$ 0,00',
    promo_savings_q: 0,
    promo_savings_display: null,
    order_discount_lines: [],
    group_savings_message: '',
    delivery_fee_q: null,
    delivery_fee_display: null,
    delivery_is_free: false,
    delivery_zone_error: false,
    delivery_distance_km: null,
    delivery_distance_display: null,
    grand_total_q: 0,
    grand_total_display: 'R$ 0,00',
    loyalty_applied: false,
    coupon_code: null,
    coupon_discount_q: null,
    coupon_discount_display: null,
    coupon_zero_reason: '',
    coupon_missing_q: 0,
    coupon_missing_display: null,
    coupon_fulfillment_types: [],
    has_unavailable_items: false,
    has_awaiting_confirmation_items: false,
    has_ready_for_confirmation_items: false,
    unavailable_banner: '',
    awaiting_confirmation_notice: '',
    reserved_until_iso: null,
    reserved_until_display: null,
    reservation_lapsed_display: null,
    minimum_order_progress: null,
    delivery_minimum_progress: null,
    free_delivery_progress: null,
    upsell: null,
    actions: [
      {
        ref: 'checkout',
        kind: 'link',
        label: 'Finalizar pedido',
        priority: 'primary',
        enabled: false,
        reason: 'Sacola vazia.',
        href: '/finalizar',
        method: '',
        payload_schema: {},
        idempotency: 'none',
        confirmation: {}
      },
      {
        ref: 'continue_shopping',
        kind: 'link',
        label: 'Continuar comprando',
        priority: 'secondary',
        enabled: true,
        reason: '',
        href: '/menu',
        method: '',
        payload_schema: {},
        idempotency: 'none',
        confirmation: {}
      }
    ]
  }
}

/** O teto do 409 só vira ação quando AVANÇA a linha. Teto igual ao que a
 *  linha já tem seria um botão que não faz nada; abaixo dela, encolheria a
 *  sacola de quem pediu mais. */
export function issueAdvancesLine (issue: Pick<CartIssue, 'available_qty' | 'line_qty'> | null | undefined): boolean {
  const ceiling = issue?.available_qty
  if (ceiling == null || ceiling <= 0) return false
  const lineQty = issue?.line_qty
  return lineQty == null || ceiling > lineQty
}

function numberOrNull (value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function normalizeSubstitutes (raw: unknown): SubstituteProjection[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map(asRecord)
    .filter(sub => typeof sub.sku === 'string' && sub.sku)
    .map(sub => ({
      sku: String(sub.sku),
      name: String(sub.name || sub.sku),
      price_q: numberOrNull(sub.price_q) ?? 0,
      price_display: typeof sub.price_display === 'string' ? sub.price_display : null,
      image_url: typeof sub.image_url === 'string' && sub.image_url ? sub.image_url : null,
      available_qty: numberOrNull(sub.available_qty),
      can_order: !!sub.can_order,
      target_qty: numberOrNull(sub.target_qty),
      reason: typeof sub.reason === 'string' && sub.reason ? sub.reason : undefined
    }))
}

function issueFromPayload (data: Record<string, unknown> | null | undefined, meta: ProductMutationMeta): CartIssue {
  const d = asRecord(data)
  const fallbackName = String(d.name || meta.name || d.sku || meta.sku)
  const rawItems = (Array.isArray(d.items) ? d.items : []).map(asRecord)
  const firstItemReason = rawItems.map(item => item.reason).find(reason => typeof reason === 'string' && reason.trim())
  const rawDetail = typeof d.detail === 'string' && !/^insufficient stock\.?$/i.test(d.detail.trim()) ? d.detail : ''
  const fallbackReason = String(firstItemReason || rawDetail || 'Revise a quantidade deste item.')
  const items = rawItems.length
    ? rawItems.map(item => ({
        sku: String(item.sku || d.sku || meta.sku),
        name: String(item.name || fallbackName),
        requested_qty: numberOrNull(item.requested_qty),
        available_qty: numberOrNull(item.available_qty),
        reason: String(item.reason || fallbackReason)
      }))
    : [{
        sku: String(d.sku || meta.sku),
        name: fallbackName,
        requested_qty: numberOrNull(d.requested_qty),
        available_qty: numberOrNull(d.available_qty),
        reason: fallbackReason
      }]

  return {
    title: String(d.title || 'Revise este item'),
    detail: fallbackReason,
    error_code: String(d.error_code || 'cart_issue'),
    sku: String(d.sku || meta.sku),
    name: fallbackName,
    requested_qty: numberOrNull(d.requested_qty),
    available_qty: numberOrNull(d.available_qty),
    line_qty: numberOrNull(d.line_qty),
    line_id: typeof d.line_id === 'string' && d.line_id ? d.line_id : null,
    is_paused: !!d.is_paused,
    isNotifiable: Boolean(d.is_notifiable),
    isNotifySubscribed: Boolean(d.is_notify_subscribed),
    is_planned: !!d.is_planned,
    planned_offer_title: String(d.planned_offer_title || ''),
    planned_offer_message: String(d.planned_offer_message || ''),
    shortage_title: String(d.shortage_title || ''),
    substitutes_intro: String(d.substitutes_intro || ''),
    substitutes: normalizeSubstitutes(d.substitutes),
    actions: Array.isArray(d.actions) ? (d.actions as Action[]) : [],
    items
  }
}

// Fila serial de mutações compartilhada por toda a superfície: toques em rajada
// não se perdem nem chegam fora de ordem no servidor; a fila sobrevive a erros.
let mutationChain: Promise<unknown> = Promise.resolve()
let queueDepth = 0
// Época das mutações: sobe a cada mutação que NASCE. Uma leitura passiva da
// sacola guarda a época do seu disparo e, se outra mutação nasceu enquanto ela
// voava, a resposta é anterior à verdade e não pode ser gravada (lost update:
// o item recém-adicionado sumia da tela e o cliente tocava de novo).
let mutationEpoch = 0

function beginMutation () {
  queueDepth += 1
  mutationEpoch += 1
}

function enqueueMutation<T> (run: () => Promise<T>): Promise<T> {
  const result = mutationChain.then(run)
  mutationChain = result.then(() => undefined, () => undefined)
  return result
}

async function waitForPendingMutations () {
  while (queueDepth > 0) {
    await mutationChain.catch(() => undefined)
    await Promise.resolve()
  }
}

export function useCartState () {
  const cart = useState<CartProjection>('storefront-cart', emptyCart)
  const pendingCountBySku = useState<Record<string, number>>('storefront-cart-pending', () => ({}))
  const lastError = useState<string | null>('storefront-cart-error', () => null)
  const cartIssue = useState<CartIssue | null>('storefront-cart-issue', () => null)
  const rateLimitRecovery = useState<RateLimitRecovery | null>('storefront-cart-rate-limit', () => null)
  const clockOffsetMs = useState<number>('storefront-cart-clock-offset', () => 0)
  const lastMutation = useState<CartMutationSnapshot | null>('storefront-cart-last-mutation', () => null)
  // Última projeção confirmada durante uma rajada. Serve apenas para desfazer a
  // UI otimista se até a reconciliação falhar; nunca é enviada ao servidor.
  const rollbackCart = useState<CartProjection | null>('storefront-cart-rollback', () => null)
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()

  const hasPendingMutations = computed(() => Object.values(pendingCountBySku.value).some(count => count > 0))

  function bumpPending (sku: string) {
    pendingCountBySku.value = { ...pendingCountBySku.value, [sku]: (pendingCountBySku.value[sku] || 0) + 1 }
  }

  function dropPending (sku: string) {
    const count = (pendingCountBySku.value[sku] || 0) - 1
    pendingCountBySku.value = count > 0
      ? { ...pendingCountBySku.value, [sku]: count }
      : omitKey(pendingCountBySku.value, sku)
  }

  // Atualiza só a projeção do carrinho. NÃO mexe em cartIssue/rateLimitRecovery:
  // esses avisos têm ciclo de vida próprio (limpos por mutação bem-sucedida ou
  // pelo início da próxima mutação), e precisam sobreviver a fetches passivos.
  function setCartProjection (next: CartProjection) {
    cart.value = { ...next, summary_pending: false }
  }

  // Relógio do servidor (WP-L11): a diferença para o relógio do aparelho, medida
  // na chegada da leitura da sacola, que traz a hora do servidor no envelope. A
  // sacola abre relendo, então a régua é sempre de agora; a diferença não muda
  // de um gesto para o outro.
  function noteServerClock (serverNowIso: string | null | undefined) {
    if (!import.meta.client || !serverNowIso) return
    clockOffsetMs.value = serverClockOffsetMs(serverNowIso, Date.now())
  }

  // Caminho de mutação bem-sucedida: a verdade do servidor chegou e qualquer
  // aviso pendente (issue/rate-limit) está resolvido — pode limpar.
  function applyServerCart (next: CartProjection) {
    setCartProjection(next)
    rollbackCart.value = null
    cartIssue.value = null
    rateLimitRecovery.value = null
  }

  function setFromServer (next?: CartProjection | null) {
    if (!next) return
    // Snapshots passivos (shell, projeções de página) não podem atropelar o
    // estado otimista enquanto há mutações em voo; a verdade chega no drain da fila.
    if (queueDepth > 0) return
    // PRESERVA cartIssue: um 409 (ex.: adicionar item esgotado pelo menu/PDP)
    // navega pra /sacola, e é justamente o fetch desta página que chegaria aqui.
    // Se limpasse o aviso, o cliente cairia numa sacola vazia muda — sem os
    // substitutos. O banner só some quando uma mutação de fato dá certo.
    setCartProjection(next)
  }

  function clearCart () {
    cart.value = emptyCart()
    cartIssue.value = null
    rateLimitRecovery.value = null
    lastMutation.value = null
    rollbackCart.value = null
  }

  // Soma todas as linhas do SKU: com escolhas, o mesmo produto pode estar em
  // duas linhas (Croque com ovo e Croque sem ovo).
  function qtyForSku (sku: string): number {
    return cartQtyForSku(cart.value.items, sku)
  }

  function isPending (sku: string): boolean {
    return (pendingCountBySku.value[sku] || 0) > 0
  }

  async function refreshCart () {
    // A época vale a do DISPARO: conferir só `queueDepth` na chegada deixava passar
    // a leitura que saiu antes de uma mutação que já drenou.
    const epochAtDispatch = mutationEpoch
    const response = await $fetch<{ cart: CartProjection, server_now_iso?: string }>(apiPath('/api/v1/storefront/cart/'), {
      credentials: 'include'
    })
    // Reconciliação passiva (revert do otimista no catch, poll de holds): preserva
    // cartIssue para o banner de substitutos não sumir enquanto o cliente decide.
    noteServerClock(response.server_now_iso)
    if (queueDepth === 0 && mutationEpoch === epochAtDispatch) setCartProjection(response.cart)
    return response.cart
  }

  async function settleCart () {
    await waitForPendingMutations()
    return refreshCart()
  }

  // Toda mutação de quantidade passa por aqui: otimista (quando há), fila serial,
  // reconciliação no drain e os três ramos de erro (409 substitutos, 429, genérico).
  // Muda só o ALVO: o SKU (produto sem opções), a linha (`line_id`) ou a inclusão
  // com opções (POST, que soma na linha igual).
  async function runQtyMutation (
    snapshot: CartMutationSnapshot,
    optimistic: (current: CartProjection) => CartProjection,
    request: () => Promise<CartMutationResponse>,
    // PUT de quantidade é absoluto: repetir após um soluço de rede é seguro. O
    // POST da inclusão com escolhas SOMA; repetir poderia pôr o item duas vezes.
    { idempotent = true }: { idempotent?: boolean } = {}
  ): Promise<CartMutationResponse> {
    const { meta } = snapshot
    lastError.value = null
    cartIssue.value = null
    rateLimitRecovery.value = null
    lastMutation.value = { ...snapshot, meta: { ...meta } }

    // A primeira mutação da rajada guarda a última verdade visível. Respostas
    // intermediárias avançam esse ponto de recuo sem atropelar otimismos posteriores.
    if (queueDepth === 0) rollbackCart.value = cart.value
    // Otimista: a linha muda na hora; o resumo fica pendente até a verdade do servidor.
    cart.value = optimistic(cart.value)
    bumpPending(meta.sku)
    beginMutation()

    try {
      let response: CartMutationResponse
      try {
        response = await enqueueMutation(async () => (idempotent ? retryWithBackoff(request) : request()))
      } finally {
        // Um decremento só por mutação, venha resposta ou erro. Com o decremento
        // repetido no catch, um erro DEPOIS da resposta descontava duas vezes, a
        // fila ficava negativa e `queueDepth === 0` nunca mais reconciliava.
        queueDepth -= 1
        dropPending(meta.sku)
      }
      if (queueDepth === 0) {
        // Drain da fila: a última resposta é a verdade mais recente.
        applyServerCart(response.cart)
        lastMutation.value = null
      } else {
        rollbackCart.value = response.cart
      }
      return response
    } catch (error: unknown) {
      if (queueDepth === 0) {
        try {
          await refreshCart()
        } catch {
          // Backend ainda indisponível: não deixe uma inclusão sem confirmação
          // aparentar sucesso. A reconexão posterior buscará a verdade canônica.
          if (rollbackCart.value) setCartProjection(rollbackCart.value)
        } finally {
          rollbackCart.value = null
        }
      }
      const { status, data } = httpError(error)
      if (status === 409 && data) {
        // Não navega, e NÃO dispara toast: o SubstituteSheet global sobe no lugar
        // (menu/PDP/sacola) e já comunica tudo — um toast sobreposto atrapalhava.
        cartIssue.value = issueFromPayload(data, meta)
        lastError.value = cartIssue.value.detail
        // A recusa é a verdade mais nova que a loja tem (WP-L04): o produto e os
        // cards abertos releem agora. Ao fechar o aviso, a página já está certa.
        announceStoreChange('refusal')
      } else if (status === 429) {
        // Sem toast: o banner de rate-limit (com countdown) é a UI dedicada.
        const detail = String(data?.detail || 'Muitas tentativas. Aguarde um instante.')
        rateLimitRecovery.value = {
          detail,
          retryAfterSeconds: typeof data?.retry_after_seconds === 'number' ? data.retry_after_seconds : null
        }
        lastError.value = detail
      } else if (status === 400 && isOptionErrorCode(data?.error_code)) {
        // Escolha recusada (obrigatória faltando, opção que saiu): a folha de
        // opções mostra o `detail` no lugar, ao lado do que precisa mudar.
        lastError.value = String(data?.detail || 'Revise as escolhas deste item.')
      } else {
        // Erro genérico não tem UI própria → o toast é a única forma de avisar.
        lastError.value = String(data?.detail || 'Não foi possível atualizar a sacola.')
        if (import.meta.client) useSonner.error(lastError.value)
      }
      throw error
    }
  }

  function putSkuQty (meta: ProductMutationMeta, qty: number) {
    return async () => $fetch<CartMutationResponse>(apiPath(`/api/v1/cart/skus/${encodeURIComponent(meta.sku)}/`), {
      method: 'PUT',
      headers: await csrfHeaders(),
      // EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
      body: meta.date ? { qty, date: meta.date } : { qty },
      credentials: 'include'
    })
  }

  async function setSkuQty (meta: ProductMutationMeta, qty: number): Promise<CartMutationResponse> {
    return runQtyMutation({ meta, qty }, current => applySkuQty(current, meta, qty), putSkuQty(meta, qty))
  }

  // O Adicionar tocado antes de a página hidratar, numa página que a cliente já deixou
  // (#3171, `utils/earlyTap.ts`). Sem preço nem foto para a linha otimista: a sacola
  // espera a verdade do servidor, que chega pela mesma fila das outras mudanças.
  async function replayEarlyAdd (sku: string, name: string, qty: number): Promise<CartMutationResponse> {
    const meta: ProductMutationMeta = { sku, name, price_q: 0, price_display: '', image_url: null }
    return runQtyMutation({ meta, qty }, current => current, putSkuQty(meta, qty))
  }

  function putLineQty (meta: ProductMutationMeta, lineId: string, qty: number): Promise<CartMutationResponse> {
    return runQtyMutation(
      { meta, qty, lineId },
      current => applyLineQty(current, lineId, qty),
      async () => $fetch<CartMutationResponse>(apiPath(`/api/v1/cart/lines/${encodeURIComponent(lineId)}/`), {
        method: 'PUT',
        headers: await csrfHeaders(),
        body: { qty },
        credentials: 'include'
      })
    )
  }

  // Quantidade DAQUELA linha (0 remove). A linha otimista ainda não existe no
  // servidor; ela só nasce de produto sem opções, então segue pelo SKU.
  async function setLineQty (line: CartItemProjection, qty: number): Promise<CartMutationResponse> {
    if (isOptimisticLine(line)) return setSkuQty(metaForCartLine(line), qty)
    return putLineQty(metaForCartLine(line), line.line_id, qty)
  }

  // Inclusão com escolhas: `qty` é quanto SOMAR (linha igual soma; escolhas
  // diferentes viram linha nova). Sem otimismo de linha: o nome com o resumo e o
  // preço com as opções são do servidor, e a folha mostra o "Adicionando".
  async function addLineWithOptions (
    meta: ProductMutationMeta,
    qty: number,
    options: ProductOptionSelection[]
  ): Promise<CartMutationResponse> {
    const chosen = options.map(option => ({ group: option.group, ref: option.ref }))
    return runQtyMutation(
      { meta, qty, options: chosen },
      current => ({ ...current, summary_pending: true }),
      async () => $fetch<CartMutationResponse>(apiPath('/api/v1/cart/lines/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        // EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
        body: meta.date ? { sku: meta.sku, qty, options: chosen, date: meta.date } : { sku: meta.sku, qty, options: chosen },
        credentials: 'include'
      }),
      { idempotent: false }
    )
  }

  // EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
  // O "Trocar" do dia (OC-33 B1): a sacola INTEIRA passa para `date`, ou nada muda.
  // Quem decide é o servidor, num comando só; aqui só se espera a fila de mudanças
  // e se aceita a sacola que ele devolve. Recusa (400 dia que a casa não atende, 409
  // item que não dá no dia) sobe para a tela, que a mostra no lugar da escolha.
  async function changeCartDay (date: string, without: string[] = []): Promise<CartProjection> {
    return enqueueMutation(async () => {
      const response = await $fetch<{ cart: CartProjection }>(apiPath('/api/v1/cart/day/'), {
        method: 'PUT',
        headers: await csrfHeaders(),
        body: { date, without },
        credentials: 'include'
      })
      setCartProjection(response.cart)
      return response.cart
    })
  }

  // `notice`: o cupom entrou no lugar de um desconto que já valia, e a resposta diz
  // de qual (o maior ganha, os descontos não se somam).
  async function mutateCoupon (method: 'POST' | 'DELETE', body?: Record<string, unknown>) {
    beginMutation()
    let response: { cart: CartProjection, notice?: string }
    try {
      response = await enqueueMutation(async () => retryWithBackoff(async () => $fetch<{ cart: CartProjection, notice?: string }>(apiPath('/api/v1/cart/coupon/'), {
        method,
        headers: await csrfHeaders(),
        body,
        credentials: 'include'
      })))
    } finally {
      // Mesmo contrato do setSkuQty: um decremento só, venha resposta ou erro.
      queueDepth -= 1
    }
    if (queueDepth === 0) applyServerCart(response.cart)
    return response
  }

  async function applyCoupon (coupon_code: string) {
    const { cart: nextCart, notice } = await mutateCoupon('POST', { code: coupon_code })
    // "Cupom aplicado" só quando o total caiu (beta SMS-04); com o desconto que o
    // cupom substituiu, quando substituiu.
    if (import.meta.client) {
      const toast = couponAppliedToast(nextCart)
      if (toast.kind === 'success') useSonner.success(notice || toast.message)
      else useSonner.info(toast.message)
    }
    return nextCart
  }

  async function removeCoupon () {
    const { cart: nextCart } = await mutateCoupon('DELETE')
    if (import.meta.client) useSonner('Cupom removido.')
    return nextCart
  }

  // Observação de UM item para a cozinha. Não é otimista: o texto só aparece
  // como salvo depois que o servidor o gravou na linha. Entra na mesma fila das
  // quantidades, para nunca ultrapassar uma mutação anterior da mesma sacola.
  // Vai pela `line_id`: com escolhas, o mesmo SKU pode ter duas linhas.
  async function setLineNotes (lineId: string, notes: string) {
    beginMutation()
    let response: { cart: CartProjection }
    try {
      response = await enqueueMutation(async () => retryWithBackoff(async () => $fetch<{ cart: CartProjection }>(apiPath(`/api/v1/cart/lines/${encodeURIComponent(lineId)}/notes/`), {
        method: 'PUT',
        headers: await csrfHeaders(),
        body: { notes },
        credentials: 'include'
      })))
    } finally {
      queueDepth -= 1
    }
    if (queueDepth === 0) applyServerCart(response.cart)
    return response.cart
  }

  // A passagem da sacola entre a loja e a conversa (OC-16): "Trazer a sacola do
  // WhatsApp". Sem otimista e sem repetir sozinha: quem decide
  // o que chega é o servidor. A recusa (409) também traz a sacola como ficou.
  async function runCartPassage (href: string, body: Record<string, unknown>): Promise<CartTransferResponse> {
    beginMutation()
    let response: CartTransferResponse
    try {
      response = await enqueueMutation(async () => $fetch<CartTransferResponse>(apiPath(href), {
        method: 'POST',
        headers: await csrfHeaders(),
        body,
        credentials: 'include'
      }))
    } catch (error) {
      const data = asRecord((error as { data?: unknown })?.data)
      const refusedCart = data.cart as CartProjection | undefined
      if (refusedCart && queueDepth === 1) applyServerCart(refusedCart)
      throw error
    } finally {
      queueDepth -= 1
    }
    if (queueDepth === 0) applyServerCart(response.cart)
    return response
  }

  function replay (mutation: CartMutationSnapshot, qty: number) {
    if (mutation.options) return addLineWithOptions(mutation.meta, qty, mutation.options)
    if (mutation.lineId) return putLineQty(mutation.meta, mutation.lineId, qty)
    return setSkuQty(mutation.meta, qty)
  }

  async function retryLastMutation () {
    const mutation = lastMutation.value
    if (!mutation) return null
    return replay(mutation, mutation.qty)
  }

  // A linha que a recusa do envio mira, como a sacola a tem agora.
  function shortLine (issue: CartIssue | null): CartItemProjection | null {
    if (!issue?.line_id) return null
    return cart.value.items.find(line => line.line_id === issue.line_id) ?? null
  }

  // Recusa de estoque no ENVIO do pedido (#2687): a folha de alternativas sobe no
  // checkout com o corpo que a recusa trouxe (o mesmo do 409 da sacola). Não há
  // mutação para refazer: o alvo das ações é a linha (`line_id`).
  function raiseStockIssue (data: Record<string, unknown>) {
    const d = asRecord(data)
    lastMutation.value = null
    cartIssue.value = issueFromPayload(d, {
      sku: String(d.sku || ''),
      name: String(d.name || ''),
      price_q: 0,
      price_display: '',
      image_url: null
    })
  }

  async function acceptAvailableQty () {
    const issue = cartIssue.value
    if (issue?.line_id) {
      // A linha passou do teto: "Levar N" a encolhe até o que dá.
      const line = shortLine(issue)
      if (!line || !issueAdvancesLine(issue)) return null
      return setLineQty(line, issue.available_qty!)
    }
    const mutation = lastMutation.value
    if (!mutation || !issue || !issueAdvancesLine(issue)) return null
    // O teto do 409 é ABSOLUTO (até onde a linha vai). A inclusão com escolhas
    // SOMA na linha igual, então manda só a diferença.
    if (mutation.options) {
      const delta = issue.available_qty! - (issue.line_qty ?? 0)
      return delta > 0 ? replay(mutation, delta) : null
    }
    return replay(mutation, issue.available_qty!)
  }

  function dismissCartIssue () {
    cartIssue.value = null
  }

  // Swap em 1 toque: troca o item que faltou por uma alternativa em estoque.
  // Reusa setSkuQty (otimista + fila + 409/429); no sucesso, applyServerCart
  // zera cartIssue e o banner some sozinho.
  async function addSubstitute (sub: SubstituteProjection) {
    const issue = cartIssue.value
    const line = shortLine(issue)
    // Linha que passou do teto (recusa do envio): ela fica com o que dá, ou sai, e o
    // substituto entra no lugar só do que falta. Sem isto a linha seguia acima do
    // teto e o próximo envio caía na mesma recusa.
    const keep = Math.max(0, issue?.available_qty ?? 0)
    const missing = line ? Math.max(1, (issue?.requested_qty ?? line.qty) - keep) : null
    const plan = substituteSwapPlan(sub, line ? missing : (issue?.requested_qty ?? null))
    if (!plan) return null
    if (line) await setLineQty(line, keep)
    const res = await setSkuQty(plan.meta, plan.qty)
    if (import.meta.client) useSonner.success(`Adicionamos ${sub.name} à sua sacola.`)
    return res
  }

  return {
    cart,
    hasPendingMutations,
    pendingCountBySku,
    lastError,
    cartIssue,
    rateLimitRecovery,
    lastMutation,
    clockOffsetMs,
    setFromServer,
    clearCart,
    refreshCart,
    settleCart,
    runCartPassage,
    qtyForSku,
    isPending,
    setSkuQty,
    replayEarlyAdd,
    setLineQty,
    addLineWithOptions,
    // EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
    changeCartDay,
    applyCoupon,
    removeCoupon,
    setLineNotes,
    retryLastMutation,
    acceptAvailableQty,
    addSubstitute,
    raiseStockIssue,
    dismissCartIssue
  }
}
