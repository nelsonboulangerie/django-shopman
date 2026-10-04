// Presentation — KDS board shaping (Arc 2). Pure transforms over the board
// Projection (served by shopman/backstage/api/kds.py). The projection is already
// screen-ready (timer_class, status_label pre-resolved); this layer
// only derives the view shape + the functional-color tone for the semaphore. No
// time/SLA arithmetic (the backend owns elapsed/target/timer_class).
import type {
  KDSBoardProjection,
  KDSExitPreparingCardProjection,
  KDSExpeditionCardProjection,
  KDSTicketProjection,
  KDSTimerClass,
} from "~/types/kds";

/** Functional tone for a ticket's urgency (cor só onde tem significado). */
export type KDSTone = "ok" | "warning" | "late";

export function ticketTone(timerClass: KDSTimerClass): KDSTone {
  if (timerClass === "timer-late") return "late";
  if (timerClass === "timer-warning") return "warning";
  return "ok";
}

/** Fill for the time-to-SLA bar by tone — o ÚNICO elemento de cor de urgência do
 *  card (cor + comprimento numa peça só, sem o "L" de duas barras). No prazo é um
 *  cinza calmo que só mostra o avanço até a meta; âmbar/vermelho acendem quando
 *  importa. Color só onde tem significado. */
export function toneBar(tone: KDSTone): string {
  if (tone === "late") return "bg-red-500";
  if (tone === "warning") return "bg-amber-500";
  return "bg-muted-foreground/30";
}

/** Superfície do card "PRÓXIMO" (prévia v4, `cozinha-estacao4.html`): borda de 2px e
 *  tinta levíssima no tom do próprio semáforo, com um halo de 4px na mesma cor. Não cria
 *  um significado de cor competindo, amplifica o que já existe ("é o próximo E está
 *  atrasado"). É o único card pintado da grade, então ele se destaca sem posição nem
 *  tamanho especial.
 *
 *  ⚠️ Sem `ring`: o canon do kit (operator-base.css, "SELEÇÃO / ATIVO") reserva o ring
 *  ao FOCO DE TECLADO. O halo é sombra (`shadow-[0_0_0_4px_…]`), não ring. */
export function toneNextSurface(tone: KDSTone): string {
  if (tone === "late")
    return "border-2 border-destructive bg-destructive/8 shadow-[0_0_0_4px_color-mix(in_oklab,var(--destructive)_15%,transparent)]";
  if (tone === "warning")
    return "border-2 border-warning bg-warning/8 shadow-[0_0_0_4px_color-mix(in_oklab,var(--warning)_15%,transparent)]";
  return "border-2 border-primary bg-primary/5 shadow-[0_0_0_4px_color-mix(in_oklab,var(--primary)_12%,transparent)]";
}

/** O relógio do card na v4 (`.tm`): o tempo contra a meta num número só. Atrasado é
 *  o único sólido (fundo vermelho, texto claro); perto da meta, contorno e texto âmbar;
 *  no prazo, contorno neutro. */
export function toneTimerChip(tone: KDSTone): string {
  if (tone === "late") return "border border-destructive bg-destructive text-destructive-foreground";
  if (tone === "warning") return "border border-warning/60 text-warning";
  return "border border-border text-foreground";
}

export type KDSPillTone = "destructive" | "warning" | "info" | "primary" | "muted";

/** A pílula do card (v4: "Próximo · atrasado", "Novo", "Em preparo", "Bloqueado").
 *  Um estilo só, a cor diz a natureza: vermelho trava ou atrasa, azul é novo, latão
 *  está em preparo. */
export function ticketPill(
  ticket: Pick<KDSTicketProjection, "status" | "is_scheduled" | "timer_class">,
  state: { next?: boolean; blocked?: boolean },
): { label: string; tone: KDSPillTone } | null {
  if (ticket.is_scheduled) return null;
  if (state.blocked) return { label: "Bloqueado", tone: "destructive" };
  const tone = ticketTone(ticket.timer_class as KDSTimerClass);
  if (state.next) {
    if (tone === "late") return { label: "Próximo · atrasado", tone: "destructive" };
    if (tone === "warning") return { label: "Próximo · perto da meta", tone: "warning" };
    return { label: "Próximo", tone: "primary" };
  }
  if (ticket.status === "pending") return { label: "Novo", tone: "info" };
  if (ticket.status === "in_progress") return { label: "Em preparo", tone: "primary" };
  return null;
}

const PILL_CLASSES: Record<KDSPillTone, string> = {
  destructive: "pill-destructive",
  warning: "pill-warning",
  info: "pill-info",
  primary: "pill-primary",
  muted: "pill-muted",
};

export function pillClass(tone: KDSPillTone): string {
  return PILL_CLASSES[tone];
}

/** Tonal chip classes for the live timer (border+tint+text), shared by card+modal. */
export function toneTimer(tone: KDSTone): string {
  if (tone === "late") return "border-red-500/40 bg-red-500/15 text-red-300";
  if (tone === "warning")
    return "border-amber-500/40 bg-amber-500/15 text-amber-300";
  return "border-white/10 bg-white/5 text-muted-foreground";
}

/** Type guard: expedition boards hold expedition cards, prep boards hold tickets.
 *  Discriminated by the explicit `is_expedition` flag — never by field presence
 *  (sniffing `items` broke when the expedition card gained an items list). */
export function isExpeditionCard(
  card: KDSTicketProjection | KDSExpeditionCardProjection,
): card is KDSExpeditionCardProjection {
  return card.is_expedition;
}

const TONE_RANK: Record<KDSTone, number> = { late: 0, warning: 1, ok: 2 };

/** Auto-sort prep tickets by urgency (KDS best practice — work on what's due
 *  first): late before warning before ok, then oldest first within a tone.
 *  Expedition boards keep projection order. */
export function sortByUrgency(
  cards: (KDSTicketProjection | KDSExpeditionCardProjection)[],
): (KDSTicketProjection | KDSExpeditionCardProjection)[] {
  if (cards.some(isExpeditionCard)) return [...cards];
  return [...(cards as KDSTicketProjection[])].sort((a, b) => {
    const ra = TONE_RANK[ticketTone(a.timer_class)];
    const rb = TONE_RANK[ticketTone(b.timer_class)];
    return ra !== rb ? ra - rb : b.elapsed_seconds - a.elapsed_seconds;
  });
}

export interface KDSAllDayCount {
  name: string;
  qty: number;
}

/** "All-day" aggregate (KDS best practice — mise en place / batch prep): how many
 *  of each item are still to make across all active prep tickets. */
export function allDayCounts(
  cards: (KDSTicketProjection | KDSExpeditionCardProjection)[],
): KDSAllDayCount[] {
  const counts = new Map<string, number>();
  for (const card of cards) {
    if (isExpeditionCard(card)) continue;
    for (const item of card.items) {
      counts.set(item.name, (counts.get(item.name) || 0) + Number(item.qty));
    }
  }
  return [...counts.entries()]
    .map(([name, qty]) => ({ name, qty: Number(qty.toFixed(9)) }))
    .sort((a, b) => b.qty - a.qty);
}

// ── Os dois gestos da cozinha ───────────────────────────────────────────────
// O card tem UM botão, e o botão diz o ato pelo nome: "Iniciar preparo" e
// depois "Finalizar preparo". A área grande do card (cabeçalho + itens) faz o
// que é SEGURO — abre o detalhe. O ato que sai da cozinha exige o botão
// rotulado. O preparo é estado do TICKET (o servidor guarda e todos os tablets
// veem), nunca do item.

/** Tempo mínimo entre "entrou em preparo" e aceitar o toque de finalizar. O
 *  botão fica no MESMO lugar nos dois estados, então um toque duplo (ou o dedo
 *  que quica na tela molhada) iniciaria e finalizaria o mesmo pedido em 300 ms.
 *  Durante o intervalo o rótulo já é "Finalizar preparo" — o que muda é só ele
 *  não aceitar o toque, e isso não pisca rótulo na cara de ninguém. */
export const KDS_ARM_DELAY_MS = 900;

/** Janela de "Desfazer" do finalizar. Finalizar tem efeito fora da cozinha
 *  (o pedido vira PRONTO e o cliente é avisado), e o "Reabrir" não desavisa
 *  ninguém — então o POST só sai quando a janela fecha. Durante a janela o card
 *  FICA NO LUGAR, apagado, com o Desfazer no mesmo ponto onde o dedo acabou de
 *  tocar: um aviso no topo da tela não se alcança com a mão ocupada. */
export const KDS_UNDO_WINDOW_MS = 5000;

export type KDSTicketActionKind = "start" | "finish" | "blocked" | "locked" | "undo" | "none";

export interface KDSTicketAction {
  kind: KDSTicketActionKind;
  /** O rótulo do botão — o ATO, não o estado. Vazio quando não há botão. */
  label: string;
  icon: string;
  /** `false` = o botão aparece mas ainda não aceita o toque (janela anti-quique). */
  enabled: boolean;
}

const NO_ACTION: KDSTicketAction = { kind: "none", label: "", icon: "", enabled: false };

/** O que o botão do card oferece, dado o estado do ticket.
 *
 *  - `undo`  — finalizado há menos de 5 s; o POST ainda não saiu.
 *  - `blocked` — há item cancelado deste pedido esperando confirmação: o servidor
 *    recusaria o finalizar, então a tela recusa antes e diz PARA ONDE ir. Iniciar
 *    nunca é bloqueado — começar o que sobrou é seguro.
 *  - `locked` — o servidor recusaria o Finalizar por outro motivo (pagamento digital
 *    ainda não capturado, pedido sem confirmação: `finish_block_label`). O botão fica
 *    no lugar, tracejado e com cadeado, e o toque diz o motivo em vez de fingir que
 *    finalizou. Iniciar continua livre: "pode adiantar".
 *  - agendado não tem botão: é prévia, e prévia não age. */
export function ticketAction(
  ticket: Pick<KDSTicketProjection, "status" | "is_scheduled"> & { finish_block_label?: string },
  state: { armed: boolean; blocked: boolean; finishing?: boolean },
): KDSTicketAction {
  if (state.finishing)
    return { kind: "undo", label: "Desfazer", icon: "lucide:undo-2", enabled: true };
  if (ticket.is_scheduled) return NO_ACTION;
  if (ticket.status === "pending")
    return { kind: "start", label: "Iniciar preparo", icon: "lucide:play", enabled: true };
  if (ticket.status !== "in_progress") return NO_ACTION;
  if (state.blocked)
    return {
      kind: "blocked",
      label: "Item cancelado: veja o cartão vermelho",
      icon: "lucide:ban",
      enabled: true,
    };
  if (ticket.finish_block_label)
    return { kind: "locked", label: "Finalizar preparo", icon: "lucide:lock", enabled: true };
  return {
    kind: "finish",
    label: "Finalizar preparo",
    icon: "lucide:check",
    enabled: state.armed,
  };
}

// ── A moldura comum dos cards ───────────────────────────────────────────────
// Estação e Saída são o MESMO card com funções diferentes: a mesma margem
// em volta, o mesmo ritmo entre os blocos, o mesmo código herói e o mesmo botão
// na base. Uma escala só, para as duas telas não derivarem de novo.

export type KDSDensity = "compact" | "cozy" | "roomy";

export interface KDSCardScale {
  /** Tamanho do código herói (papéis do canon: title → display). */
  code: string;
  /** Margem lateral, do topo e da base da moldura. */
  inset: string;
  padT: string;
  padB: string;
  /** Ritmo vertical entre os blocos do card. */
  gap: string;
  /** Altura + corpo do botão da base. Escada do canon do kit (operator-base.css,
   *  "ALTURAS DE CONTROLE"): nunca abaixo de h-11, porque é o alvo de toque. */
  action: string;
}

// Padrão = a medida da prévia v4 (`.tk`: 12px em cima e embaixo, 14px dos lados, 6px
// entre os blocos; código de 30px; botão de 56px com 18px). Compacta e Ampla escalam a
// partir dela.
const CARD_SCALE: Record<KDSDensity, KDSCardScale> = {
  compact: { code: "text-xl", inset: "px-3", padT: "pt-2.5", padB: "pb-2.5", gap: "gap-1.5", action: "h-11 text-base" },
  cozy: { code: "text-3xl", inset: "px-3.5", padT: "pt-3", padB: "pb-3", gap: "gap-1.5", action: "h-14 text-lg" },
  roomy: { code: "text-4xl", inset: "px-4", padT: "pt-4", padB: "pb-4", gap: "gap-2", action: "h-16 text-xl" },
};

export function cardScale(density: KDSDensity): KDSCardScale {
  return CARD_SCALE[density];
}

/** "Entrega" ou "Retirada" — a mesma palavra que a Saída recebe pronta da
 *  projection (`fulfillment_label`), derivada aqui do ícone que o ticket traz. */
export function fulfillmentLabel(fulfillmentIcon: string): string {
  return fulfillmentIcon === "local_shipping" ? "Entrega" : "Retirada";
}

/** Dia/mês de uma data ISO ("2026-09-19" → "19/09"). O card agendado precisa
 *  DIZER a data: "libera na data" obriga o operador a lembrar do seletor que
 *  está no topo do cabeçalho, longe do card e de um minuto atrás. Fatiar a
 *  string (em vez de `new Date`) evita o fuso virar a data um dia. */
export function shortDateLabel(iso: string): string {
  const [, month, day] = iso.split("-");
  return month && day ? `${day}/${month}` : iso;
}

/** Pedidos com item cancelado ainda sem "Ciente" nesta estação. O servidor
 *  bloqueia o finalizar por pedido+estação; a referência exibida é a mesma
 *  para o ticket vivo e o cancelado da mesma venda. */
export function blockedOrderRefs(cancelled: KDSTicketProjection[]): Set<string> {
  return new Set(cancelled.map((ticket) => ticket.order_ref));
}

/** Tickets que são ADICIONAL de um pedido que já passou por esta estação.
 *  Item novo numa comanda nunca altera o ticket que já está em preparo: o
 *  servidor dispara só o delta, num ticket novo. A tela diz isso, para a
 *  cozinha não achar que é pedido repetido. */
export function additionTicketPks(
  cards: (KDSTicketProjection | KDSExpeditionCardProjection)[],
  recentDone: KDSTicketProjection[],
): Set<number> {
  const firstPkByRef = new Map<string, number>();
  for (const ticket of [...cards, ...recentDone]) {
    if (isExpeditionCard(ticket) || ticket.is_scheduled) continue;
    const first = firstPkByRef.get(ticket.order_ref);
    if (first === undefined || ticket.pk < first) firstPkByRef.set(ticket.order_ref, ticket.pk);
  }
  const additions = new Set<number>();
  for (const card of cards) {
    if (isExpeditionCard(card) || card.is_scheduled) continue;
    if (firstPkByRef.get(card.order_ref) !== card.pk) additions.add(card.pk);
  }
  return additions;
}

export interface KDSBoardView {
  instanceRef: string;
  instanceName: string;
  isExpedition: boolean;
  /** Active cards, auto-sorted by urgency (prep) / projection order (expedition).
   *  Na Saída, é a coluna "Prontos para sair" — e só ela toca o som. */
  cards: (KDSTicketProjection | KDSExpeditionCardProjection)[];
  /** Só na Saída: a coluna "Em preparo" (pedidos que esperam alguma estação). */
  preparing: KDSExitPreparingCardProjection[];
  cancelled: KDSTicketProjection[];
  /** Concluídos recentes (≤30min) — para recall (desfazer finalização). */
  recentDone: KDSTicketProjection[];
  allDay: KDSAllDayCount[];
  counts: Record<string, number>;
  total: number;
  /** Pedidos com cancelado sem confirmação — finalizar espera. */
  blockedRefs: Set<string>;
  /** Tickets que são adicional de um pedido já visto nesta estação. */
  additionPks: Set<number>;
  /** Finalizados com a janela de "Desfazer" aberta: continuam na grade, apagados. */
  finishingPks: Set<number>;
  /** O ticket que a estação deve pegar agora (o 1º da ordem de urgência que
   *  ainda é trabalho). Nunca um agendado nem um que está saindo. */
  nextPk: number | null;
  serviceDate: string;
  serviceDateDisplay: string;
  today: string;
  availableDates: string[];
}

/** O ticket "próximo" da grade: o primeiro da ordem de urgência que ainda é
 *  trabalho de verdade. Agendado é prévia e não se pega; a Saída não tem
 *  "próximo" (a ordem ali é a da projection). */
export function nextTicketPk(
  cards: (KDSTicketProjection | KDSExpeditionCardProjection)[],
  isExpedition: boolean,
): number | null {
  if (isExpedition) return null;
  const first = cards.find((card) => !isExpeditionCard(card) && !card.is_scheduled);
  return first ? first.pk : null;
}

/** `finishingPks`: tickets finalizados cuja janela de "Desfazer" ainda está
 *  aberta. Eles CONTINUAM na grade, no mesmo lugar, apagados e carregando o
 *  botão de desfazer — sumir e oferecer o desfazer num aviso lá no topo da tela
 *  era pedir que a cozinha atravessasse a tela com a mão ocupada. O que eles
 *  deixam de ser é TRABALHO: saem dos contadores, saem do "a fazer" e nunca são
 *  o próximo. Os contadores de preparo são recontados sobre o que a tela mostra,
 *  para que o toque otimista mude o cabeçalho junto com o card. */
export function boardView(
  board: KDSBoardProjection,
  finishingPks: ReadonlySet<number> = new Set(),
): KDSBoardView {
  const cards = sortByUrgency([...board.tickets]);
  const working = cards.filter((card) => !finishingPks.has(card.pk));
  const recentDone = [...(board.recent_done ?? [])];
  const counts = { ...(board.counts || {}) };
  if (!board.is_expedition) {
    const tickets = working as KDSTicketProjection[];
    counts.pending = tickets.filter((t) => t.status === "pending").length;
    counts.in_progress = tickets.filter((t) => t.status === "in_progress").length;
    counts.total = tickets.length;
  } else if (finishingPks.size) {
    counts.total = working.length;
  }
  return {
    instanceRef: board.instance_ref,
    instanceName: board.instance_name,
    isExpedition: board.is_expedition,
    cards,
    preparing: [...(board.preparing ?? [])],
    cancelled: [...board.cancelled_tickets],
    recentDone,
    allDay: allDayCounts(working),
    counts,
    total: counts.total ?? working.length,
    blockedRefs: blockedOrderRefs(board.cancelled_tickets),
    additionPks: additionTicketPks(cards, recentDone),
    finishingPks: new Set(finishingPks),
    nextPk: nextTicketPk(working, board.is_expedition),
    serviceDate: board.service_date,
    serviceDateDisplay: board.service_date_display,
    today: board.today,
    availableDates: [...(board.available_dates ?? [])],
  };
}

/** Map the projection's Material-Symbol icon names (channel + fulfillment) onto
 *  this surface's lucide vocabulary. The KDS Nuxt app renders lucide; the shared
 *  backend projection speaks Material (it also feeds the HTMX queue). Owning the
 *  translation here keeps the projection surface-agnostic. */
const MATERIAL_TO_LUCIDE: Record<string, string> = {
  language: "globe",
  chat: "message-circle",
  fastfood: "utensils-crossed",
  storefront: "store",
  shopping_bag: "shopping-bag",
  local_shipping: "bike",
};

export function lucideIcon(name: string): string {
  return MATERIAL_TO_LUCIDE[name] || name || "circle";
}

/** Split an order ref into the repetitive {channel-date-} prefix and the short
 *  CODE the kitchen actually calls (the suffix after the last hyphen). The code
 *  gets the visual weight; the prefix recedes. */
export function splitRef(ref: string): { prefix: string; code: string } {
  const i = ref.lastIndexOf("-");
  if (i < 0) return { prefix: "", code: ref };
  return { prefix: ref.slice(0, i + 1), code: ref.slice(i + 1) };
}

/** Elapsed seconds → compact timer label. Segundos só no 1º minuto ("45s"); a partir
 *  de 1 min some o tique-taque e mostra minutos inteiros ("24m"), depois "1h 5m" —
 *  mais calmo e glanceável numa cozinha (a barra de SLA já dá o "quão perto da meta"). */
export function elapsedLabel(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
}

/** Compact target-SLA label ("alvo 12m") — recessive companion to the live timer
 *  so the operator reads elapsed *against* the promise, not in a vacuum. */
export function targetLabel(targetSeconds: number): string {
  const m = Math.max(0, Math.round(targetSeconds / 60));
  return m >= 60
    ? `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ""}`
    : `${m}m`;
}

/** Elapsed-vs-target fill for the time-to-SLA bar — the at-a-glance urgency cue
 *  winning KDS products lean on (Toast/Fresh). Clamped to 0–100 so the bar fills
 *  as the ticket approaches its promise and pins full once it's overdue; the tone
 *  (verde→âmbar→vermelho) carries the over-SLA escalation. */
export function slaPercent(
  elapsedSeconds: number,
  targetSeconds: number,
): number {
  if (targetSeconds <= 0) return 0;
  return Math.min(100, Math.max(0, (elapsedSeconds / targetSeconds) * 100));
}

// ── Honestidade de tempo-real (mesmo padrão do Gestor) ──────────────────────
// O painel do cliente diz a VERDADE sobre a atualização: verde "ao vivo" só quando o
// SSE está de fato conectado; senão âmbar (conectando) ou neutro (atualiza sozinho pelo
// poll). Nunca uma bolinha verde mentirosa piscando sobre um quadro que só faz poll.
export type RealtimeState = "connecting" | "live" | "polling";

export interface RealtimeIndicatorView {
  label: string;
  live: boolean;
  dotClass: string;
  title: string;
}

export function realtimeIndicator(state: RealtimeState): RealtimeIndicatorView {
  if (state === "live") {
    return {
      label: "Ao vivo",
      live: true,
      dotClass: "bg-green-500",
      title: "Recebendo atualizações em tempo real",
    };
  }
  if (state === "connecting") {
    return {
      label: "Conectando…",
      live: false,
      dotClass: "bg-amber-500",
      title: "Estabelecendo tempo real; enquanto isso, atualiza sozinho",
    };
  }
  return {
    label: "Atualiza sozinho",
    live: false,
    dotClass: "bg-muted-foreground/40",
    title: "O painel atualiza sozinho a cada poucos segundos",
  };
}

// ── A fila do cozinheiro (prévia v4, SUITE-UX §10.3) ────────────────────────
// 4 a 6 tickets em foco (3×2 no tablet deitado); o resto vira "+N na fila" e entra
// no "A fazer". A profundidade vira agregado, nunca card minúsculo. Ticket longo
// ocupa duas alturas em vez de cortar a lista.

export type KDSBoardFilter = "all" | "delivery" | "late";

type PrepCard = KDSTicketProjection | KDSExpeditionCardProjection;

export function isDeliveryTicket(card: PrepCard): boolean {
  return card.fulfillment_icon === "local_shipping";
}

export function isLateTicket(card: PrepCard): boolean {
  return !isExpeditionCard(card) && !card.is_scheduled && card.timer_class === "timer-late";
}

export function matchesBoardFilter(card: PrepCard, filter: KDSBoardFilter): boolean {
  if (filter === "delivery") return isDeliveryTicket(card);
  if (filter === "late") return isLateTicket(card);
  return true;
}

export function boardFilterCounts(cards: PrepCard[]): Record<KDSBoardFilter, number> {
  return {
    all: cards.length,
    delivery: cards.filter(isDeliveryTicket).length,
    late: cards.filter(isLateTicket).length,
  };
}

/** Ticket que ocupa duas alturas: lista longa (com as observações contando como
 *  linha). A v4 mostra a encomenda de 7 itens assim, "em vez de cortar a lista". */
export function isTallTicket(card: PrepCard): boolean {
  if (isExpeditionCard(card)) return false;
  const notes =
    card.items.filter((item) => item.notes || item.stock_warning).length +
    (card.kitchen_note ? 1 : 0) +
    (card.customer_note ? 1 : 0) +
    (card.finish_block_label ? 1 : 0) +
    (card.test_order_label ? 1 : 0);
  return card.items.length + notes >= 6;
}

export interface KDSFocusPlacement {
  pk: number;
  column: number;
  row: number;
  span: 1 | 2;
}

export interface KDSFocusSlice<T extends { pk: number }> {
  visible: T[];
  rest: T[];
  placements: Map<number, KDSFocusPlacement>;
}

/** Quantos tickets cabem em foco e onde cada um mora, na ORDEM de urgência: o
 *  primeiro que não couber leva a fila inteira para o "+N" (nunca se pula um mais
 *  urgente para mostrar um menos urgente). Mesma regra do posicionamento automático
 *  do CSS Grid (o cursor só anda para a frente), com o limite de linhas que a tela
 *  tem. Em uma coluna ninguém ocupa duas alturas. */
export function focusSlice<T extends PrepCard>(
  cards: T[],
  layout: { columns: number; rows: number },
): KDSFocusSlice<T> {
  const columns = Math.max(1, Math.floor(layout.columns));
  const rows = Math.max(1, Math.floor(layout.rows));
  const taken = new Set<string>();
  const placements = new Map<number, KDSFocusPlacement>();
  const visible: T[] = [];
  let cursor = 0;
  let index = 0;
  for (; index < cards.length; index++) {
    const card = cards[index]!;
    const span: 1 | 2 = columns > 1 && rows > 1 && isTallTicket(card) ? 2 : 1;
    let placed: KDSFocusPlacement | null = null;
    for (let cell = cursor; cell < columns * rows; cell++) {
      const row = Math.floor(cell / columns);
      const column = cell % columns;
      if (row + span > rows) continue;
      if (taken.has(`${row}:${column}`) || (span === 2 && taken.has(`${row + 1}:${column}`))) continue;
      placed = { pk: card.pk, column, row, span };
      cursor = cell + 1;
      break;
    }
    if (!placed) break;
    taken.add(`${placed.row}:${placed.column}`);
    if (span === 2) taken.add(`${placed.row + 1}:${placed.column}`);
    placements.set(card.pk, placed);
    visible.push(card);
  }
  return { visible, rest: cards.slice(index), placements };
}

/** Quantas colunas e linhas de tickets cabem na área da grade. A largura mínima é a
 *  da densidade; a altura mínima é a de um ticket curto legível. Sem medida (SSR,
 *  primeira pintura), 2 linhas. */
export function focusGrid(
  size: { width: number; height: number },
  minWidth: number,
  gap = 12,
): { columns: number; rows: number } {
  const MIN_ROW = 230;
  const columns = Math.min(5, Math.max(1, Math.floor((size.width + gap) / (minWidth + gap))));
  if (!size.height) return { columns, rows: 2 };
  const rows = Math.min(3, Math.max(1, Math.floor((size.height + gap) / (MIN_ROW + gap))));
  return { columns, rows };
}

/** A frase do excedente: "+7 na fila" e "todos no prazo, já somados em "A fazer"". */
export function restSummary(rest: PrepCard[]): { count: string; detail: string } {
  const late = rest.filter(isLateTicket).length;
  const status = late === 0 ? "todos no prazo" : late === 1 ? "1 atrasado" : `${late} atrasados`;
  return {
    count: `+${rest.length} na fila`,
    detail: `${status}, já somados em "A fazer" · entram aqui quando um ticket sair`,
  };
}

/** A linha compacta da fila no celular ("1× Cappuccino", "2× Croissant +1"). */
export function queueLine(card: PrepCard): string {
  if (isExpeditionCard(card)) return "";
  const [first, ...others] = card.items;
  if (!first) return "";
  const head = `${first.qty}× ${first.name}`;
  return others.length ? `${head} +${others.length}` : head;
}

/** O cancelamento na faixa de avisos: se o pedido continua na estação, foi um ITEM
 *  que saiu ("Item cancelado 22:01", "o resto continua"); senão, o pedido inteiro. */
export function cancelledSummary(
  cancelled: Pick<KDSTicketProjection, "order_ref" | "cancelled_at_display">,
  activeRefs: ReadonlySet<string>,
): { label: string; rest: string } {
  const time = cancelled.cancelled_at_display ? ` ${cancelled.cancelled_at_display}` : "";
  return activeRefs.has(cancelled.order_ref)
    ? { label: `Item cancelado${time}`, rest: "o resto continua" }
    : { label: `Cancelado${time}`, rest: "" };
}
