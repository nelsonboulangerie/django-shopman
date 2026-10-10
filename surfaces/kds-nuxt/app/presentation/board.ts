// Presentation — KDS board shaping (Arc 2). Pure transforms over the board
// Projection (served by shopman/backstage/api/kds.py). The projection is already
// screen-ready (timer_class, status_label pre-resolved); this layer
// only derives the view shape + the functional-color tone for the semaphore. No
// time/SLA arithmetic (the backend owns elapsed/target/timer_class).
import type { KDSBoardProjection, KDSChangeKind, KDSTicketProjection, KDSTimerClass } from "~/types/kds";

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

/** A pílula do card ("Atrasado", "Novo", "Em preparo", "Bloqueado"; a posição na fila mora no rótulo acima do código).
 *  Um estilo só, a cor diz a natureza: vermelho trava ou atrasa, azul é novo, latão
 *  está em preparo. */
export function ticketPill(
  ticket: Pick<KDSTicketProjection, "status" | "timer_class"> & Partial<Pick<KDSTicketProjection, "changes">>,
  state: { next?: boolean; blocked?: boolean },
): { label: string; tone: KDSPillTone } | null {
  // O cancelado inteiro não tem estado de preparo a mostrar: o "Cancelado" mora acima
  // do código (no lugar da posição na fila), como o "Mudou" do card que mudou.
  if (ticket.status === "cancelled") return null;
  // Bloqueado = o servidor recusaria o Pronto por outro motivo (pagamento): `locked`.
  if (state.blocked) return { label: "Bloqueado", tone: "destructive" };
  const tone = ticketTone(ticket.timer_class as KDSTimerClass);
  // O de agora já diz a posição no rótulo acima do código ("Agora"); a pílula diz só o
  // prazo, para "Próximo" não nomear dois tickets na mesma tela.
  if (state.next) {
    if (tone === "late") return { label: "Atrasado", tone: "destructive" };
    if (tone === "warning") return { label: "Perto da meta", tone: "warning" };
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

const TONE_RANK: Record<KDSTone, number> = { late: 0, warning: 1, ok: 2 };

/** Auto-sort prep tickets by urgency (KDS best practice — work on what's due
 *  first): late before warning before ok, then oldest first within a tone. */
export function sortByUrgency(cards: KDSTicketProjection[]): KDSTicketProjection[] {
  return [...cards].sort((a, b) => {
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
export function allDayCounts(cards: KDSTicketProjection[]): KDSAllDayCount[] {
  const counts = new Map<string, number>();
  for (const card of cards) {
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
// depois "Pronto W07". O ato de terminar se chama Pronto em todo tamanho (decisão
// do dono, 04/10/2026): no card do tablet e do desktop (`cardActionLabel`) e no
// polegar do celular (`cozinha-celular` b, `thumbActionLabel`). A área grande do card (cabeçalho + itens) faz o
// que é SEGURO — abre o detalhe. O ato que sai da cozinha exige o botão
// rotulado. O preparo é estado do TICKET (o servidor guarda e todos os tablets
// veem), nunca do item.

/** Tempo mínimo entre "entrou em preparo" e aceitar o toque de Pronto. O
 *  botão fica no MESMO lugar nos dois estados, então um toque duplo (ou o dedo
 *  que quica na tela molhada) iniciaria e marcaria Pronto no mesmo pedido em 300 ms.
 *  Durante o intervalo o rótulo já é "Pronto" — o que muda é só ele
 *  não aceitar o toque, e isso não pisca rótulo na cara de ninguém. */
export const KDS_ARM_DELAY_MS = 900;

/** Janela de "Desfazer" do Pronto. O Pronto tem efeito fora da cozinha
 *  (o pedido vira PRONTO e o cliente é avisado), e o "Reabrir" não desavisa
 *  ninguém — então o POST só sai quando a janela fecha. Durante a janela o card
 *  FICA NO LUGAR, apagado, com o Desfazer no mesmo ponto onde o dedo acabou de
 *  tocar: um aviso no topo da tela não se alcança com a mão ocupada. */
export const KDS_UNDO_WINDOW_MS = 5000;

export type KDSTicketActionKind = "seen" | "start" | "finish" | "locked" | "undo" | "none";

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
 *  - `undo`  — Pronto há menos de 5 s; o POST ainda não saiu.
 *  - `seen` — o pedido mudou depois de chegar à cozinha (item cancelado, outra
 *    quantidade, observação nova, outro nome) ou caiu inteiro: o único ato é a
 *    ciência ("Recebi o cancelamento" / "Visto"), antes de iniciar ou dar Pronto. O
 *    servidor também recusa o Pronto enquanto há item cancelado sem ciência.
 *  - `locked` — o servidor recusaria o Pronto por outro motivo (pagamento digital
 *    ainda não capturado, pedido sem confirmação: `finish_block_label`). O botão fica
 *    no lugar, tracejado e com cadeado, e o toque diz o motivo em vez de fingir que
 *    deu Pronto. Iniciar continua livre: "pode adiantar".
 */
export function ticketAction(
  ticket: Pick<KDSTicketProjection, "status"> &
    Partial<Pick<KDSTicketProjection, "changes" | "is_cancelled">> & { finish_block_label?: string },
  state: { armed: boolean; finishing?: boolean },
): KDSTicketAction {
  if (state.finishing)
    return { kind: "undo", label: "Desfazer", icon: "lucide:undo-2", enabled: true };
  // A mudança vem antes de qualquer ato: a cozinha precisa ver o que mudou antes de
  // continuar (dono, 10/10/2026: "com alarde, a cada mudança").
  if (ticket.is_cancelled || ticket.status === "cancelled" || hasChanges(ticket))
    return { kind: "seen", label: changeAckLabel(ticket), icon: "lucide:eye", enabled: true };
  if (ticket.status === "pending")
    return { kind: "start", label: "Iniciar preparo", icon: "lucide:play", enabled: true };
  if (ticket.status !== "in_progress") return NO_ACTION;
  if (ticket.finish_block_label)
    return { kind: "locked", label: "Pronto", icon: "lucide:lock", enabled: true };
  return {
    kind: "finish",
    label: "Pronto",
    icon: "lucide:check",
    enabled: state.armed,
  };
}

// ── Mudança no que já está na cozinha (dono, 10/10/2026) ────────────────────
// O PDV ajusta sozinho o que já foi enviado (remove, diminui, observação nova, libera a
// comanda, transfere, a comanda vira pedido) e a cozinha recebe CADA mudança com alarde,
// nunca em silêncio: o card afetado fica vermelho, diz o que mudou ("Cancelado: 1×
// Croissant", "Pão de queijo: agora 1, eram 3", "Observação nova em Tapioca: sem
// glúten", "Era a comanda Mesa 5") e o único botão dele é a ciência, até alguém tocar.
// O pedido que caiu inteiro não some: vira um card "Cancelado", riscado, no topo.

export function hasChanges(ticket: Partial<Pick<KDSTicketProjection, "changes">>): boolean {
  return Boolean(ticket.changes?.length);
}

/** Card que pede ciência agora: cancelado inteiro, ou vivo com mudança sem Visto. */
export function needsAcknowledgement(
  ticket: Partial<Pick<KDSTicketProjection, "changes" | "is_cancelled" | "status">>,
): boolean {
  return Boolean(ticket.is_cancelled) || ticket.status === "cancelled" || hasChanges(ticket);
}

/** O nome do gesto de ciência (suite-vocabulary §2.1 e §4): item que saiu é
 *  **Recebi o cancelamento** (é o que destrava o Pronto); o resto é **Visto**. */
export function changeAckLabel(
  ticket: Partial<Pick<KDSTicketProjection, "changes" | "is_cancelled" | "status">>,
): string {
  const cancels =
    ticket.is_cancelled ||
    ticket.status === "cancelled" ||
    (ticket.changes ?? []).some((change) => change.kind === "cancelled");
  return cancels ? "Recebi o cancelamento" : "Visto";
}

const CHANGE_ICONS: Record<KDSChangeKind, string> = {
  cancelled: "lucide:ban",
  qty: "lucide:hash",
  note: "lucide:message-square-warning",
  resent: "lucide:repeat",
  moved: "lucide:arrow-right-left",
};

export function changeIcon(kind: string): string {
  return CHANGE_ICONS[kind as KDSChangeKind] ?? "lucide:triangle-alert";
}

/** O que o card cancelado inteiro diz, em cima dos itens riscados. */
export function cancelledHeadline(ticket: Pick<KDSTicketProjection, "cancelled_at_display">): string {
  return ticket.cancelled_at_display
    ? `Pedido cancelado às ${ticket.cancelled_at_display}. Não preparar.`
    : "Pedido cancelado. Não preparar.";
}

/** A ordem da grade: o que pede ciência vem antes da fila de trabalho, sem perder a
 *  ordem de urgência entre os outros. */
export function alarmsFirst<T extends Partial<Pick<KDSTicketProjection, "changes" | "is_cancelled" | "status">>>(
  cards: T[],
): T[] {
  return [...cards.filter(needsAcknowledgement), ...cards.filter((card) => !needsAcknowledgement(card))];
}

/** O botão do card no tablet e no desktop: o Pronto leva o código do pedido ("Pronto
 *  W07"), como no celular; os outros atos ficam como estão ("Iniciar preparo"). */
export function cardActionLabel(action: KDSTicketAction, code: string): string {
  if (action.kind === "finish" || action.kind === "locked") return `Pronto ${code}`;
  return action.label;
}

/** O ato no polegar do celular (prévia v4 `cozinha-celular` b): o mesmo botão do card,
 *  com o código do pedido no rótulo, porque o card em foco fica longe do dedo.
 *  "Pronto W07", e os outros atos também levam o código junto. */
export function thumbActionLabel(action: KDSTicketAction, code: string): string {
  if (action.kind === "finish" || action.kind === "locked") return `Pronto ${code}`;
  if (action.kind === "seen") return `${action.label} ${code}`;
  if (action.kind === "start") return `Iniciar ${code}`;
  if (action.kind === "undo") return `Desfazer ${code}`;
  return action.label;
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

/** "Entrega" ou "Retirada", derivada do ícone que o ticket traz. */
export function fulfillmentLabel(fulfillmentIcon: string): string {
  return fulfillmentIcon === "local_shipping" ? "Entrega" : "Retirada";
}

/** A linha de baixo do código (prévia v4, nota 6): "Card sem canal, telefone nem
 *  cliente". A venda do dia diz só "Retirada"/"Entrega"; a encomenda diz "Encomenda"
 *  e o cliente, porque é com ele que a hora foi combinada ("Encomenda · Café
 *  Parisiense"). O nome do cliente nunca é telefone. */
export function ticketOverline(
  ticket: Pick<KDSTicketProjection, "fulfillment_icon" | "is_preorder" | "customer_name" | "previous_tab_ref">,
): string {
  if (!ticket.is_preorder) return fulfillmentLabel(ticket.fulfillment_icon);
  const name = (ticket.customer_name || "").trim();
  const showName = name && name !== ticket.previous_tab_ref && !looksLikePhone(name);
  return showName ? `Encomenda · ${name}` : "Encomenda";
}

function looksLikePhone(value: string): boolean {
  return /^[+\d\s().-]{8,}$/.test(value);
}

/** "iniciado por Rafael às 21:56 · retira às 22:30" (prévia v4, nota 7: "quem iniciou
 *  aparece no card"). Vazio quando não há nada a dizer. */
export function ticketStartLine(
  ticket: Pick<KDSTicketProjection, "started_by" | "started_at_display" | "due_time_display">,
): string {
  const parts: string[] = [];
  if (ticket.started_by) {
    parts.push(
      ticket.started_at_display
        ? `iniciado por ${ticket.started_by} às ${ticket.started_at_display}`
        : `iniciado por ${ticket.started_by}`,
    );
  }
  if (ticket.due_time_display) parts.push(ticket.due_time_display);
  return parts.join(" · ");
}

/** Tickets que são ADICIONAL de um pedido que já passou por esta estação.
 *  Item novo numa comanda nunca altera o ticket que já está em preparo: o
 *  servidor dispara só o delta, num ticket novo. A tela diz isso, para a
 *  cozinha não achar que é pedido repetido. */
export function additionTicketPks(cards: KDSTicketProjection[], recentDone: KDSTicketProjection[]): Set<number> {
  const firstPkByRef = new Map<string, number>();
  for (const ticket of [...cards, ...recentDone]) {
    const first = firstPkByRef.get(ticket.order_ref);
    if (first === undefined || ticket.pk < first) firstPkByRef.set(ticket.order_ref, ticket.pk);
  }
  const additions = new Set<number>();
  for (const card of cards) {
    if (firstPkByRef.get(card.order_ref) !== card.pk) additions.add(card.pk);
  }
  return additions;
}

export interface KDSBoardView {
  instanceRef: string;
  instanceName: string;
  /** Active tickets: os que mudaram primeiro, depois a ordem de urgência. */
  cards: KDSTicketProjection[];
  /** Pedidos que caíram inteiros nesta estação, sem ciência: card próprio, no topo. */
  cancelled: KDSTicketProjection[];
  /** Concluídos recentes (≤30min) — para recall (desfazer o Pronto). */
  recentDone: KDSTicketProjection[];
  allDay: KDSAllDayCount[];
  counts: Record<string, number>;
  total: number;
  /** Tickets que são adicional de um pedido já visto nesta estação. */
  additionPks: Set<number>;
  /** Marcados Pronto com a janela de "Desfazer" aberta: continuam na grade, apagados. */
  finishingPks: Set<number>;
  /** O ticket que a estação deve pegar agora (o 1º da ordem de urgência que
   *  ainda é trabalho). Nunca um que está saindo. */
  nextPk: number | null;
  /** Como a estação provisionada se mostra (prévia v4, nota 1): o cadastro guarda. */
  density: KDSDensity;
  soundEnabled: boolean;
}

/** O ticket "próximo" da grade: o primeiro da ordem de urgência que ainda é trabalho
 *  (o que mudou pede ciência antes, e não é o "próximo" de ninguém). */
export function nextTicketPk(cards: KDSTicketProjection[]): number | null {
  return cards.find((card) => !hasChanges(card))?.pk ?? null;
}

export function stationDensity(value: string): KDSDensity {
  return value === "compact" || value === "roomy" ? value : "cozy";
}

/** `finishingPks`: tickets marcados Pronto cuja janela de "Desfazer" ainda está
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
  const cards = alarmsFirst(sortByUrgency([...board.tickets]));
  const working = cards.filter((card) => !finishingPks.has(card.pk));
  const recentDone = [...(board.recent_done ?? [])];
  const counts = { ...(board.counts || {}) };
  counts.pending = working.filter((t) => t.status === "pending").length;
  counts.in_progress = working.filter((t) => t.status === "in_progress").length;
  counts.total = working.length;
  return {
    instanceRef: board.instance_ref,
    instanceName: board.instance_name,
    cards,
    cancelled: [...board.cancelled_tickets],
    recentDone,
    allDay: allDayCounts(working),
    counts,
    total: working.length,
    additionPks: additionTicketPks(cards, recentDone),
    finishingPks: new Set(finishingPks),
    nextPk: nextTicketPk(working),
    density: stationDensity(board.density),
    soundEnabled: board.sound_enabled !== false,
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
// deixa a linha mais alta em vez de cortar a lista; a ordem de leitura não muda.

export type KDSBoardFilter = "all" | "delivery" | "late";

type PrepCard = KDSTicketProjection;

export function isDeliveryTicket(card: PrepCard): boolean {
  return card.fulfillment_icon === "local_shipping";
}

export function isLateTicket(card: PrepCard): boolean {
  return card.timer_class === "timer-late";
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

export interface KDSFocusPlacement {
  pk: number;
  column: number;
  row: number;
}

export interface KDSFocusSlice<T extends { pk: number }> {
  visible: T[];
  rest: T[];
  placements: Map<number, KDSFocusPlacement>;
}

/** Quantos tickets cabem em foco e onde cada um mora, na ORDEM de ataque (dono,
 *  09/10/2026): a ordem é UMA e se lê como texto, da esquerda para a direita, linha a
 *  linha. Cada ticket ocupa uma célula; o ticket longo deixa a SUA linha mais alta
 *  (as linhas seguem alinhadas pelo topo) em vez de ocupar duas alturas e empurrar os
 *  vizinhos para buracos. Nada de mosaico: o cozinheiro nunca precisa adivinhar qual
 *  vem depois. O que não cabe vai inteiro para o "+N", na mesma ordem. */
export function focusSlice<T extends PrepCard>(
  cards: T[],
  layout: { columns: number; rows: number },
): KDSFocusSlice<T> {
  const columns = Math.max(1, Math.floor(layout.columns));
  const rows = Math.max(1, Math.floor(layout.rows));
  const visible = cards.slice(0, columns * rows);
  const placements = new Map<number, KDSFocusPlacement>(
    visible.map((card, index) => [
      card.pk,
      { pk: card.pk, column: index % columns, row: Math.floor(index / columns) },
    ]),
  );
  return { visible, rest: cards.slice(visible.length), placements };
}

/** A posição na fila, escrita no ticket, a mesma em toda largura: o primeiro é o de
 *  "Agora", o segundo o "Próximo", os outros "Depois". */
export function queuePositionLabel(index: number): string {
  if (index === 0) return "Agora";
  return index === 1 ? "Próximo" : "Depois";
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
  const [first, ...others] = card.items;
  if (!first) return "";
  const head = `${first.qty}× ${first.name}`;
  return others.length ? `${head} +${others.length}` : head;
}
