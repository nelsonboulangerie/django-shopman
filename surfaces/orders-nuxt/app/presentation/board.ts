// Presentation — order board shaping. Pure transforms over the order queue
// projection (served by shopman/backstage/api/operations.py). The projection is
// already screen-ready (status_label, timer_class, next_action_label, can_* flags
// pre-resolved); this layer only derives the view shape, the functional-color tone,
// and the action affordances. No status arithmetic (the backend owns the lifecycle).
import type { EquipmentOptionProjection } from "~/generated/ordersContract";
import type {
  OrderCardProjection,
  OrderTimerClass,
  TwoZoneQueueProjection,
} from "~/types/orders";

// ── Status tone, ícone do canal e "fatos numa linha" ──────────────────────
// Moram no kit (`operator-kit/app/presentation/orderDetail.ts`) porque o detalhe
// do pedido é o mesmo no Gestor e no PDV; o board lê as mesmas peças.
import { joinFacts } from "../../../operator-kit/app/presentation/orderDetail";

export {
  joinFacts,
  lucideIcon,
  statusTone,
  toneBadge,
} from "../../../operator-kit/app/presentation/orderDetail";
export type { Tone } from "../../../operator-kit/app/presentation/orderDetail";

// ── Timer tone (urgency of the elapsed clock) ──────────────────────────────

export type TimerTone = "ok" | "warning" | "late" | "muted";

export function timerTone(timerClass: OrderTimerClass): TimerTone {
  if (timerClass === "timer-urgent") return "late";
  if (timerClass === "timer-warning") return "warning";
  if (timerClass === "timer-muted") return "muted";
  return "ok";
}

/** Tonal chip classes for the live timer. Atenção ao tempo é número com intensidade,
 *  sempre no âmbar (G03): o vermelho é só "bloqueado com motivo", nunca o relógio. */
export function timerChip(tone: TimerTone): string {
  switch (tone) {
    case "late":
      return "border-warning/60 bg-warning/20 font-bold text-warning";
    case "warning":
      return "border-warning/40 bg-warning/10 text-warning";
    case "muted":
      return "border-transparent bg-transparent text-muted-foreground";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

/** Split an order ref into the repetitive {channel-date-} prefix and the short
 *  CODE the operator actually calls (the suffix after the last hyphen). */
export function splitRef(ref: string): { prefix: string; code: string } {
  const i = ref.lastIndexOf("-");
  if (i < 0) return { prefix: "", code: ref };
  return { prefix: ref.slice(0, i + 1), code: ref.slice(i + 1) };
}

/** Elapsed seconds → compact label. Seconds only in the first minute, then whole
 *  minutes, then "1h 5m", then days ("4d 23h") — calmer and glanceable. Capar em
 *  dias evita o "119h" que grita sem informar. */
export function elapsedLabel(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
  const d = Math.floor(h / 24);
  return h % 24 ? `${d}d ${h % 24}h` : `${d}d`;
}

/**
 * Countdown regressivo até o prazo da confirmação otimista.
 * Retorna "" quando não há prazo; "0:00" quando já venceu; senão "M:SS".
 * Puro e testável — o card passa um `nowMs` que tica no cliente.
 */
/**
 * Tom do prazo pelo que FALTA, não pelo que passou.
 *
 * O decorrido nunca fica vermelho sozinho — um pedido de 7 minutos com 10 de prazo
 * está tranquilo, e um de 7 com 8 de prazo está para vencer. Os cortes valem para
 * qualquer canal: o prazo do iFood e o timer da casa pedem a mesma leitura.
 */
export function deadlineTone(deadlineIso: string, nowMs: number): TimerTone {
  if (!deadlineIso) return "muted";
  const deadlineMs = Date.parse(deadlineIso);
  if (Number.isNaN(deadlineMs)) return "muted";
  const secondsLeft = (deadlineMs - nowMs) / 1000;
  if (secondsLeft <= 60) return "late";
  if (secondsLeft <= 180) return "warning";
  return "ok";
}

export function confirmationRemainingLabel(
  deadlineIso: string,
  nowMs: number,
): string {
  if (!deadlineIso) return "";
  const deadlineMs = Date.parse(deadlineIso);
  if (Number.isNaN(deadlineMs)) return "";
  const left = Math.max(0, Math.round((deadlineMs - nowMs) / 1000));
  const m = Math.floor(left / 60);
  return `${m}:${String(left % 60).padStart(2, "0")}`;
}

// ── O sistema fez · desfazer (SUITE-UX §5.1) ───────────────────────────────

export interface UndoLine {
  kind: "auto_ready" | "handoff";
  /** O fato: "Pronto · automático", "Entregue às 14:02". */
  label: string;
  /** O que a janela segura, ou o carimbo depois dela. */
  detail: string;
  /** Segundos que faltam; 0 = janela fechada (o fato fica, o gesto some). */
  secondsLeft: number;
  /** "0:24" (pronto automático) ou "5 s" (saída). Vazio sem janela. */
  countdown: string;
  canUndo: boolean;
  action: AffordanceRef;
  /** O que não esperou a janela e já saiu ("iFood já avisado"); vazio se nada. */
  alreadyOut: string;
}

type UndoSource = Pick<OrderCardProjection, "undo" | "actions">;

/** A linha "o sistema fez · desfazer" do card e do detalhe, ou ``null``.
 *
 *  O servidor decide o fato e a janela (``undo``); a tela só conta o tempo. O
 *  gesto existe enquanto há segundos e a ação projetada está habilitada. */
export function undoLine(source: UndoSource, nowMs: number): UndoLine | null {
  const undo = source.undo;
  if (!undo) return null;
  const kind = undo.kind === "handoff" ? "handoff" : "auto_ready";
  const deadline = undo.undo_until_iso ? Date.parse(undo.undo_until_iso) : NaN;
  const secondsLeft = Number.isNaN(deadline)
    ? 0
    : Math.max(0, Math.ceil((deadline - nowMs) / 1000));
  const action = (source.actions ?? []).find((a) => a.ref === undo.action_ref);
  const canUndo = secondsLeft > 0 && Boolean(action?.enabled);
  let detail = undo.detail;
  let countdown = "";
  if (secondsLeft > 0) {
    if (kind === "auto_ready") {
      countdown = confirmationRemainingLabel(undo.undo_until_iso, nowMs);
      detail = `aviso ao cliente sai em ${countdown}`;
    } else {
      countdown = `${secondsLeft} s`;
    }
  }
  return {
    kind,
    label: undo.label,
    detail,
    secondsLeft,
    countdown,
    canUndo,
    action: kind === "handoff" ? "undo_handoff" : "undo_ready",
    alreadyOut: undo.already_out ?? "",
  };
}

// ── Zones (Entrada / Preparo / Saída) ──────────────────────────────────────

export interface ZoneView {
  key: "intake" | "prep" | "expedition";
  title: string;
  subtitle: string;
  icon: string;
  cards: OrderCardProjection[];
  count: number;
}

/** O estado vazio de cada coluna, nomeando a zona.
 *
 *  As três colunas repetiam "Nada por aqui agora." — a mesma frase três vezes na
 *  mesma tela, e "aqui" nunca dizia qual das três estava vazia. Quem olha de longe
 *  precisa saber se o que acabou foi a entrada, o preparo ou a saída. */
export function zoneEmptyText(key: ZoneView["key"]): string {
  switch (key) {
    case "intake":
      return "Nenhum pedido novo agora.";
    case "prep":
      return "Nenhum pedido em preparo agora.";
    default:
      return "Nenhum pedido para retirada ou entrega agora.";
  }
}

/** Group the two-zone queue projection into the three action columns the board
 *  renders. Expedition merges pickup + delivery (ready) + delivery-in-transit. */
export function zonesView(queue: TwoZoneQueueProjection): ZoneView[] {
  const expedition = [
    ...queue.expedition_pickup,
    ...queue.expedition_delivery,
    ...queue.expedition_delivery_transit,
  ];
  return [
    {
      key: "intake",
      title: "Entrada",
      subtitle: "Novos: aceitar ou recusar",
      icon: "lucide:inbox",
      cards: queue.intake,
      count: queue.intake.length,
    },
    {
      key: "prep",
      title: "Preparo",
      subtitle: "Confirmados e em preparo",
      icon: "lucide:cooking-pot",
      cards: queue.prep,
      count: queue.prep.length,
    },
    {
      key: "expedition",
      title: "Saída",
      subtitle: "Retirada, coleta e entrega",
      icon: "lucide:package-check",
      cards: expedition,
      count: expedition.length,
    },
  ];
}

// ── Encomendas (pedidos confirmados para datas futuras) ────────────────────

export interface PreorderGroup {
  /** ISO date the group is committed to (sort key). */
  date: string;
  /** Operator-facing label ("amanhã", "sáb, 19/07"). */
  label: string;
  cards: OrderCardProjection[];
}

/** Group the queue's future preorders by commitment date, soonest first.
 *  The server already sorts cards by (commitment_date, created_at). */
export function preorderGroups(
  queue: Pick<TwoZoneQueueProjection, "preorders">,
): PreorderGroup[] {
  const groups = new Map<string, PreorderGroup>();
  for (const card of queue.preorders ?? []) {
    const date = card.commitment_date || "";
    const existing = groups.get(date);
    if (existing) {
      existing.cards.push(card);
    } else {
      groups.set(date, {
        date,
        label: card.commitment_date_display || date,
        cards: [card],
      });
    }
  }
  return [...groups.values()];
}

// ── Action affordances ─────────────────────────────────────────────────────

export type AffordanceRef =
  | "confirm"
  | "advance"
  | "reject"
  | "settle_cash"
  | "equipment_back"
  | "courier_back"
  | "undo_handoff"
  | "undo_ready";

export interface Affordance {
  ref: AffordanceRef;
  label: string;
  icon: string;
  priority: "primary" | "secondary" | "danger";
  /** Needs a typed reason/amount → the surface opens a small dialog first. */
  needsInput: boolean;
  /** Afordância informativa: mostra o porquê, não aceita clique. */
  disabled?: boolean;
  /** Motivo completo (title/tooltip) quando desabilitada. */
  reason?: string;
}

/** The actions a card offers, derived from the projection's pre-resolved flags.
 *  Order = visual priority (primary first). Mirrors the Admin action cell. */
export function cardAffordances(card: OrderCardProjection): Affordance[] {
  const projected = card.actions ?? [];
  // Saída tocada e ainda na janela: o gesto do card é o "Desfazer" da linha do
  // fato (``undoLine``), nenhum outro. Avançar de novo repetiria a saída.
  if (projected.some((a) => a.ref === "undo-handoff")) return [];
  const icons: Record<string, string> = {
    confirm: "lucide:check",
    advance: "lucide:arrow-right",
    reject: "lucide:x",
  };
  // ``priority: "menu"``: o "Marcar pronto" enquanto a Cozinha trabalha. O
  // pronto vem sozinho quando ela conclui (L1); o gesto à mão fica no menu do
  // pedido (detalhe), para a estação sem tela e o caso que o sistema não viu.
  const out: Affordance[] = projected
    .filter(
      (a) => a.ref !== "reject" && a.ref in icons && a.priority !== "menu",
    )
    .map((a) => ({
      ref: a.ref as AffordanceRef,
      label: a.label,
      icon: a.enabled ? icons[a.ref]! : "lucide:clock",
      priority: a.enabled
        ? (a.priority as Affordance["priority"])
        : "secondary",
      needsInput: false,
      disabled: !a.enabled,
      reason: a.reason,
    }));
  // "Entregador voltou" fecha a saída inteira (entrega, dinheiro, troco e
  // maquininha): quando existe, é o ÚNICO gesto do card — os passos avulsos
  // (entregue, acertar, maquininha voltou) ficam no detalhe, para exceção.
  const courierBack = projected.find((a) => a.ref === "courier-back");
  if (courierBack) {
    return [
      {
        ref: "courier_back",
        label: courierBack.label,
        icon: "lucide:undo-2",
        priority: "primary",
        needsInput: true,
        disabled: !courierBack.enabled,
        reason: courierBack.reason,
      },
    ];
  }
  if (card.can_settle_delivery_cash) {
    const settle = projected.find(
      (action) => action.ref === "settle-delivery-cash",
    );
    out.push({
      ref: "settle_cash",
      label:
        card.fulfillment_type === "pickup"
          ? "Receber na retirada"
          : "Acertar entrega",
      icon: "lucide:banknote",
      priority: "secondary",
      needsInput: true,
      disabled: !settle?.enabled,
      reason:
        settle?.reason ||
        (!settle ? "Atualize o pedido para conferir o caixa." : ""),
    });
  }
  // A maquininha saiu e não voltou; sem acerto em dinheiro para marcar, o card
  // oferece o gesto sozinho (pedido em cartão, ou acerto já feito sem ela).
  if (card.equipment_back_pending) {
    out.push({
      ref: "equipment_back",
      label: "Maquininha voltou",
      icon: "lucide:smartphone-nfc",
      priority: "secondary",
      needsInput: false,
    });
  }
  const reject = projected.find((a) => a.ref === "reject");
  if (reject) {
    out.push({
      ref: "reject",
      label: reject.label,
      icon: "lucide:x",
      priority: "danger",
      needsInput: true,
      disabled: !reject.enabled,
      reason: reject.reason,
    });
  }
  return out;
}

/** Filter cards by a free-text query over ref, customer and items summary. */
export function matchesQuery(
  card: OrderCardProjection,
  rawQuery: string,
): boolean {
  const q = rawQuery.trim().toLowerCase();
  if (!q) return true;
  return [card.ref, card.customer_name, card.items_summary]
    .join(" ")
    .toLowerCase()
    .includes(q);
}

// ── Triage: channel filter, sort, view-mode (Arc 1) ─────────────────────────

/** Friendly channel labels. Unknown channels fall back to a capitalised ref so
 *  a new channel never renders blank. */
const CHANNEL_LABEL: Record<string, string> = {
  web: "Loja online",
  whatsapp: "WhatsApp",
  ifood: "iFood",
  pdv: "PDV",
  pos: "PDV",
};

export function channelLabel(ref: string): string {
  if (CHANNEL_LABEL[ref]) return CHANNEL_LABEL[ref];
  return ref ? ref.charAt(0).toUpperCase() + ref.slice(1) : "—";
}

export interface ChannelOption {
  ref: string;
  label: string;
  count: number;
}

/** Distinct channels present in the queue, with counts, for the filter control.
 *  Derived from the data so the control only ever offers channels that exist. */
export function channelOptions(cards: OrderCardProjection[]): ChannelOption[] {
  const counts = new Map<string, number>();
  for (const c of cards)
    counts.set(c.channel_ref, (counts.get(c.channel_ref) ?? 0) + 1);
  return [...counts.entries()]
    .map(([ref, count]) => ({ ref, label: channelLabel(ref), count }))
    .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
}

/** `"all"` (or empty) matches everything; otherwise exact channel match. */
export function matchesChannel(
  card: OrderCardProjection,
  channel: string,
): boolean {
  return !channel || channel === "all" || card.channel_ref === channel;
}

// Fulfillment é o eixo que muda o FLUXO (rota vs balcão) — por isso é filtro de
// primeira classe no board, ao lado do canal (que é só a origem).
export type FulfillmentFilter = "all" | "delivery" | "pickup";

/** `"all"` matches everything; senão bate o fulfillment_type do card. */
export function matchesFulfillment(
  card: OrderCardProjection,
  mode: FulfillmentFilter,
): boolean {
  return mode === "all" || card.fulfillment_type === mode;
}

export type RealtimeState = "connecting" | "live" | "polling";

export interface RealtimeIndicatorView {
  label: string;
  /** true SÓ quando o SSE está aberto — a bolinha verde não mente. */
  live: boolean;
  dotClass: string;
  title: string;
}

/**
 * Como apresentar o estado de realtime do board (honestidade da resiliência): "ao vivo"
 * (verde) só com SSE aberto; caso contrário um sinal neutro de que o board ainda atualiza
 * sozinho, a cada 30s (poll) — nunca prometendo tempo-real que não há.
 */
export function realtimeIndicator(state: RealtimeState): RealtimeIndicatorView {
  if (state === "live") {
    return {
      label: "Ao vivo",
      live: true,
      dotClass: "bg-success",
      title: "Recebendo atualizações em tempo real",
    };
  }
  if (state === "connecting") {
    return {
      label: "Conectando…",
      live: false,
      dotClass: "bg-warning",
      title: "Estabelecendo tempo real; enquanto isso, atualiza a cada 30s",
    };
  }
  return {
    label: "Atualiza a cada 30 s",
    live: false,
    dotClass: "bg-muted-foreground/40",
    title: "Sem tempo real; o board atualiza sozinho a cada 30s",
  };
}

/** A fonte do som é a projeção canônica após o refresh, nunca o sinal SSE cru. */
export function treatableOrderRefs(
  queue: TwoZoneQueueProjection | null,
): Set<string> {
  if (!queue) return new Set();
  // Encomenda futura pode até ter ação administrativa disponível (aceitar,
  // corrigir, cancelar), mas não é trabalho do turno de agora. Incluí-la aqui
  // fazia o sino do Gestor tocar no instante da venda, embora o próprio board a
  // colocasse corretamente em "Encomendas". Quando a data chega, a projeção (e,
  // quando aplicável, o despertador do lifecycle) leva o card ao fluxo do dia;
  // só então ele entra neste conjunto e a atenção toca uma única vez.
  const cards = [
    ...queue.intake,
    ...queue.prep,
    ...queue.expedition_pickup,
    ...queue.expedition_delivery,
    ...queue.expedition_delivery_transit,
    ...(queue.ifood_negotiation_orders ?? []),
  ];
  return new Set(
    cards
      .filter(
        (card) =>
          card.can_confirm ||
          card.can_advance ||
          card.can_settle_delivery_cash ||
          card.equipment_back_pending,
      )
      .map((card) => card.ref),
  );
}

/** Refs que passaram de espera passiva para trabalho possível no Gestor. */
export function newlyTreatableOrderRefs(
  before: TwoZoneQueueProjection | null,
  after: TwoZoneQueueProjection | null,
): string[] {
  const prior = treatableOrderRefs(before);
  return [...treatableOrderRefs(after)].filter((ref) => !prior.has(ref));
}

/** Contagem por fulfillment na fila corrente (para os selos dos filtros). */
export function fulfillmentCounts(cards: OrderCardProjection[]): {
  delivery: number;
  pickup: number;
} {
  let delivery = 0;
  let pickup = 0;
  for (const c of cards) {
    if (c.fulfillment_type === "delivery") delivery++;
    else pickup++;
  }
  return { delivery, pickup };
}

export type SortKey = "arrival" | "urgency" | "recent";

export interface SortOption {
  key: SortKey;
  label: string;
}

// Um gesto, um nome: sair do modo de seleção chama-se assim no ⋯ e na barra de lote.
// "Concluir" ali mentia: no mesmo app é o rótulo de concluir o pedido entregue.
export const EXIT_SELECTION_LABEL = "Sair da seleção";

export const SORT_OPTIONS: SortOption[] = [
  { key: "arrival", label: "Chegada" },
  { key: "urgency", label: "Urgência" },
  { key: "recent", label: "Mais recentes" },
];

/** Order cards for display. `arrival` keeps the projection's own order (oldest
 *  first, as the backend serves it); `urgency` puts the longest-waiting on top;
 *  `recent` puts the newest arrivals on top. Pure — never mutates the input. */
export function sortCards(
  cards: OrderCardProjection[],
  key: SortKey,
): OrderCardProjection[] {
  const out = [...cards];
  if (key === "urgency") {
    out.sort((a, b) => b.elapsed_seconds - a.elapsed_seconds);
  } else if (key === "recent") {
    out.sort((a, b) => b.created_at_iso.localeCompare(a.created_at_iso));
  }
  return out;
}

/** Apply channel filter + free-text query + sort to one zone's cards. The board
 *  and the table both render through this, so they always agree. */
export function triageCards(
  cards: OrderCardProjection[],
  opts: {
    query: string;
    channel: string;
    sort: SortKey;
    fulfillment?: FulfillmentFilter;
  },
): OrderCardProjection[] {
  const fulfillment = opts.fulfillment ?? "all";
  const filtered = cards.filter(
    (c) =>
      matchesChannel(c, opts.channel) &&
      matchesFulfillment(c, fulfillment) &&
      matchesQuery(c, opts.query),
  );
  return sortCards(filtered, opts.sort);
}

/** "queue": a Grade, os cartões da Fila "Precisa de você" (abre nela no desktop);
 *  "board": o quadro de três colunas; "table": a Lista, a tabela densa. */
export type ViewMode = "queue" | "board" | "table";

export interface FlatRow {
  card: OrderCardProjection;
  zoneKey: ZoneView["key"];
  zoneTitle: string;
}

/** Flatten the three zones into one list (with the zone each card belongs to)
 *  for the dense table view. Preserves zone order, then per-zone order. */
export function flattenZones(zones: ZoneView[]): FlatRow[] {
  return zones.flatMap((z) =>
    z.cards.map((card) => ({ card, zoneKey: z.key, zoneTitle: z.title })),
  );
}

/** Serialise the (already triaged) queue rows to CSV — the operator's "saída"
 *  for a shift handover or a quick print. Pure so the columns/escaping are
 *  testable; the page owns the download. */
export function rowsToCsv(rows: FlatRow[]): string {
  const header = [
    "Código",
    "Situação",
    "Canal",
    "Cliente",
    "Itens",
    "Total",
    "Tempo",
    "Atendente",
  ];
  const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const body = rows.map((r) =>
    [
      r.card.ref,
      r.zoneTitle,
      channelLabel(r.card.channel_ref),
      r.card.customer_name,
      r.card.items_summary,
      r.card.total_display,
      elapsedLabel(r.card.elapsed_seconds),
      r.card.assigned_operator,
    ]
      .map(esc)
      .join(","),
  );
  return [header.map(esc).join(","), ...body].join("\n");
}

// ── Keyboard shortcuts (Arc 3) ──────────────────────────────────────────────

export type BoardShortcut =
  | "focus-search"
  | "refresh"
  | "toggle-view"
  | "cycle-sort"
  | "clear-filters";

/** Map a keydown's `key` to a board shortcut, or null if none. Pure so the
 *  mapping is testable; the page owns the side effects (focus, refresh, …) and
 *  the "ignore while typing" guard. */
export function resolveShortcut(key: string): BoardShortcut | null {
  switch (key) {
    case "/":
      return "focus-search";
    case "r":
    case "R":
      return "refresh";
    case "v":
    case "V":
      return "toggle-view";
    case "s":
    case "S":
      return "cycle-sort";
    case "Escape":
      return "clear-filters";
    default:
      return null;
  }
}

/** Cycle the sort key in the order the control lists them. */
export function nextSort(current: SortKey): SortKey {
  const i = SORT_OPTIONS.findIndex((o) => o.key === current);
  return SORT_OPTIONS[(i + 1) % SORT_OPTIONS.length]!.key;
}

// ── Bulk actions (Arc 4) ────────────────────────────────────────────────────

export type BulkAction = "confirm" | "advance";

/** Refs among the selected cards that can take the given bulk action right now,
 *  read from the projection's pre-resolved flags (the backend owns the gate, as
 *  always). Pure → the batch bar's enabled/count state is testable. */
export function bulkableRefs(
  cards: OrderCardProjection[],
  selected: ReadonlySet<string>,
  action: BulkAction,
): string[] {
  // Despacho que pede troco não entra no lote: precisa de um valor por pedido
  // (o servidor recusa sem ele), e o lote não tem onde perguntar. Nem o que sai
  // com maquininha: a escolha (ou a saída junto) mora no diálogo de saída.
  const can =
    action === "confirm"
      ? (c: OrderCardProjection) => c.can_confirm
      : (c: OrderCardProjection) =>
          c.can_advance && !dispatchAsksChange(c) && !c.dispatch_needs_machine;
  return cards.filter((c) => selected.has(c.ref) && can(c)).map((c) => c.ref);
}

// ── Troco da entrega (WP-9) ─────────────────────────────────────────────────
// O livro do caixa é a fonte (courier_out/courier_in); o card só traz os números
// e a frase pronta. Aqui mora o que a tela decide com eles: quando perguntar.

/** O próximo passo é "saiu para entrega" e a loja sugere troco: perguntar o
 *  valor antes de avançar (o servidor recusa com 409 se ninguém disser). */
export function dispatchAsksChange(
  card: Pick<OrderCardProjection, "next_status" | "change_out_suggested_q">,
): boolean {
  return card.next_status === "dispatched" && card.change_out_suggested_q > 0;
}

/** Um pedido pronto para sair para entrega pelas mãos do operador (candidato a ir junto). */
export function readyToDispatch(card: OrderCardProjection): boolean {
  const advance = (card.actions ?? []).find((a) => a.ref === "advance");
  return (
    card.status === "ready" &&
    card.fulfillment_type === "delivery" &&
    card.next_status === "dispatched" &&
    Boolean(advance?.enabled)
  );
}

/** Os outros pedidos prontos que podem ir na MESMA saída deste. */
export function tripCandidates(
  card: OrderCardProjection,
  cards: OrderCardProjection[],
): OrderCardProjection[] {
  return cards.filter(
    (other) => other.ref !== card.ref && readyToDispatch(other),
  );
}

export function freeMachines(
  options: EquipmentOptionProjection[],
): EquipmentOptionProjection[] {
  return options.filter(
    (opt) => opt.ref.startsWith("card_machine:") && opt.enabled !== false,
  );
}

export interface DispatchStep {
  ref: string;
  changeOut?: string;
  equipment?: string[];
  tripRef?: string;
}

/** A saída em passos: quem precisa de maquininha abre a saída (reserva a
 *  escolhida); os outros entram nela (``tripRef``) e a compartilham. */
export function dispatchSteps(
  cards: OrderCardProjection[],
  opts: { machineRef?: string; changeOut?: Record<string, string> } = {},
): DispatchStep[] {
  const anchor = cards.find((c) => c.dispatch_needs_machine) ?? cards[0];
  if (!anchor) return [];
  const change = (c: OrderCardProjection) =>
    dispatchAsksChange(c)
      ? {
          changeOut:
            (opts.changeOut?.[c.ref] ?? "").trim() ||
            moneyInput(c.change_out_suggested_q),
        }
      : {};
  return [
    {
      ref: anchor.ref,
      ...change(anchor),
      ...(anchor.dispatch_needs_machine && opts.machineRef
        ? { equipment: [opts.machineRef] }
        : {}),
    },
    ...cards
      .filter((c) => c.ref !== anchor.ref)
      .map((c) => ({ ref: c.ref, ...change(c), tripRef: anchor.ref })),
  ];
}

/** Um toque: sem troco a informar, sem outro pedido pronto para ir junto e,
 *  se precisa de maquininha, exatamente UMA livre (o sistema escolhe). Nulo = diálogo. */
export function oneTapDispatch(
  card: OrderCardProjection,
  cards: OrderCardProjection[],
): DispatchStep[] | null {
  if (dispatchAsksChange(card) || tripCandidates(card, cards).length)
    return null;
  if (!card.dispatch_needs_machine) return dispatchSteps([card]);
  const free = freeMachines(card.equipment_options);
  return free.length === 1
    ? dispatchSteps([card], { machineRef: free[0]!.ref })
    : null;
}

function joinRefs(refs: string[]): string {
  return refs.length <= 1
    ? (refs[0] ?? "")
    : `${refs.slice(0, -1).join(", ")} e ${refs[refs.length - 1]}`;
}

/** Nenhuma livre: onde elas estão ("As duas maquininhas estão na rua: pedidos 0415 e 0418."). */
export function machinesOutSentence(
  options: EquipmentOptionProjection[],
): string {
  const out = options.filter(
    (opt) => opt.ref.startsWith("card_machine:") && opt.order_ref,
  );
  if (!out.length) return "Nenhuma maquininha livre.";
  const refs = [...new Set(out.map((opt) => splitRef(opt.order_ref).code))];
  const subject =
    out.length === 1
      ? "A maquininha está na rua"
      : out.length === 2
        ? "As duas maquininhas estão na rua"
        : `As ${out.length} maquininhas estão na rua`;
  return `${subject}: ${refs.length === 1 ? "pedido" : "pedidos"} ${joinRefs(refs)}.`;
}

/** "Saiu com a maquininha Azul" (o rótulo pode já começar com "Maquininha"). */
export function machinePhrase(label: string): string {
  const clean = label.trim();
  if (!clean) return "maquininha";
  return clean.toLowerCase().startsWith("maquininha")
    ? clean[0]!.toLowerCase() + clean.slice(1)
    : `maquininha ${clean}`;
}

/** Os pedidos que "Entregador voltou" fecha, para a confirmação ("Fecha os pedidos 0415 e 0418."). */
export function courierReturnOrders(
  card: Pick<OrderCardProjection, "courier_return_orders">,
): string {
  const refs = (card.courier_return_orders ?? []).map(
    (ref) => splitRef(ref).code,
  );
  return refs.length > 1 ? `Fecha a saída dos pedidos ${joinRefs(refs)}.` : "";
}

/** A linha do card na rua: "Saiu com a maquininha Azul · junto com 0415". */
export function onRoadLine(
  card: Pick<OrderCardProjection, "equipment_label" | "trip_with">,
): string {
  const others = card.trip_with ?? [];
  const together = others.length
    ? `junto com ${joinRefs(others.map((ref) => splitRef(ref).code))}`
    : "";
  if (!card.equipment_label) return together ? `Saiu ${together}` : "";
  return joinFacts(card.equipment_label, together);
}

/** Sugestão do que deve ter voltado: TUDO o que saiu.
 *
 *  Regra da casa: o entregador nunca fica com troco, ele só leva e traz. Numa
 *  entrega de R$ 26 paga com nota de R$ 50 ele leva R$ 24 da gaveta, entrega os
 *  R$ 24 ao cliente e volta com a nota de R$ 50: R$ 26 são a venda
 *  (`cod_settled`) e R$ 24 são o troco voltando (`courier_in`). O que voltou é
 *  o valor integral que saiu.
 *
 *  ⚠️ Antes daqui saía `change_out_q − change_out_suggested_q`, que é zero no
 *  caso normal (levou exatamente o troco devido). O livro então registrava
 *  −24 · +26 · +0 = +2, enquanto a gaveta ganhava R$ 26 de verdade: R$ 24 de
 *  SOBRA FANTASMA a cada entrega com troco, e sobra fantasma é o esconderijo
 *  perfeito de uma falta real na contagem cega. O campo continua editável — o
 *  entregador pode voltar com menos, e aí a diferença tem dono e motivo. */
export function changeBackSuggestionQ(
  card: Pick<OrderCardProjection, "change_out_q">,
): number {
  return Math.max(0, card.change_out_q);
}

/** Centavos → "20,00" (para preencher o campo; o rótulo "R$" fica na tela). */
export function moneyInput(amountQ: number): string {
  const cents = Math.max(0, Math.round(amountQ));
  return `${Math.floor(cents / 100)},${String(cents % 100).padStart(2, "0")}`;
}

// ── Kitchen note tags ───────────────────────────────────────────────────────

/** Append a preset tag to the operator's kitchen note, preserving the free text.
 *  One tap stacks tags separated by ", ". Idempotent: a tag already present in the
 *  note isn't added again (case-insensitive), so repeated taps don't duplicate it.
 *  Pure → the tag buttons' behaviour is testable without a DOM. */
export function appendTag(current: string, tag: string): string {
  const t = tag.trim();
  const base = current.trim();
  if (!t) return base;
  if (!base) return t;
  if (base.toLowerCase().includes(t.toLowerCase())) return base;
  return `${base}, ${t}`;
}

// ── O cartão no desenho da v4 (UX-KIT-V2, `gestor-colunas4.html` e `gestor-fila4.html`) ──
//
// Seis significados de estado, só eles (SPEC4 §2): precisa de você (primary), em
// andamento (info), feito (success), bloqueado com motivo (error), o sistema fez
// (neutro, com ícone de automático) e atenção ao tempo (um número com intensidade).
// Aqui se decide só a palavra e o tom; o ciclo continua do servidor.

export type SealTone =
  | "primary"
  | "info"
  | "success"
  | "warning"
  | "error"
  | "muted";

export interface CardSeal {
  label: string;
  tone: SealTone;
}

const SEAL_TONE: Record<string, SealTone> = {
  new: "primary",
  accepted: "info",
  preparing: "info",
  dispatched: "info",
  ready: "success",
  delivered: "success",
  completed: "success",
  cancelled: "error",
};

type SealSource = Pick<
  OrderCardProjection,
  "status" | "status_label" | "can_confirm" | "advance_block_reason" | "actions"
>;

/** Selo do canto do cartão. Bloqueio primeiro (o motivo vem escrito no cartão); depois
 *  "Novo" (a decisão pendente) e "Próximo" (o primeiro da Saída a sair); senão o estado. */
export function cardSeal(
  card: SealSource,
  opts: { next?: boolean } = {},
): CardSeal {
  const advance = (card.actions ?? []).find(
    (a) => a.ref === "advance" && a.priority !== "menu",
  );
  if (card.advance_block_reason && advance && !advance.enabled)
    return { label: "Bloqueado", tone: "error" };
  if (card.can_confirm) return { label: "Novo", tone: "primary" };
  if (opts.next) return { label: "Próximo", tone: "primary" };
  return { label: card.status_label, tone: SEAL_TONE[card.status] ?? "muted" };
}

/** "há 9 min": o tempo do pedido em palavras, como na v4. Abaixo de um minuto, "agora". */
export function agoLabel(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return "agora";
  const m = Math.floor(s / 60);
  if (m < 60) return `há ${m} min`;
  return `há ${elapsedLabel(s).replace(/(\d+)m$/, "$1 min")}`;
}

export interface CardClock {
  text: string;
  tone: TimerTone;
  /** Prazo correndo (confirmação otimista): o leitor de tela ouve como relógio. */
  countdown: boolean;
}

type ClockSource = Pick<
  OrderCardProjection,
  | "confirmation_deadline_iso"
  | "confirmation_action"
  | "elapsed_seconds"
  | "timer_class"
> &
  Partial<Pick<OrderCardProjection, "ready_at_iso" | "dispatched_at_iso">>;

/** Segundos desde um instante ISO do servidor; `null` quando o instante não existe. */
export function secondsSince(
  iso: string | undefined,
  nowMs: number,
): number | null {
  const at = iso ? Date.parse(iso) : Number.NaN;
  return Number.isFinite(at)
    ? Math.max(0, Math.round((nowMs - at) / 1000))
    : null;
}

/** A linha do tempo do canto: o prazo, quando há ("aceita sozinho em 2:40"); no pronto,
 *  desde quando está pronto ("pronto há 6 min"); na rua, desde a saída ("na rua há 18
 *  min"); senão, o decorrido desde a chegada ("há 9 min"). Um relógio só: quanto falta
 *  decide; quanto passou, não. */
export function cardClock(card: ClockSource, nowMs: number): CardClock {
  const left = confirmationRemainingLabel(
    card.confirmation_deadline_iso,
    nowMs,
  );
  if (left) {
    const verb =
      card.confirmation_action === "cancel"
        ? "cancela sozinho em"
        : "aceita sozinho em";
    return {
      text: `${verb} ${left}`,
      tone: deadlineTone(card.confirmation_deadline_iso, nowMs),
      countdown: true,
    };
  }
  const tone = timerTone(card.timer_class as OrderTimerClass);
  const ready = secondsSince(card.ready_at_iso, nowMs);
  if (ready !== null)
    return {
      text: ready < 60 ? "pronto agora" : `pronto ${agoLabel(ready)}`,
      tone,
      countdown: false,
    };
  const road = secondsSince(card.dispatched_at_iso, nowMs);
  if (road !== null)
    return {
      text: road < 60 ? "saiu agora" : `na rua ${agoLabel(road)}`,
      tone,
      countdown: false,
    };
  return { text: agoLabel(card.elapsed_seconds), tone, countdown: false };
}

/** "3 volumes" quando quem embalou declarou; senão a contagem de itens ("2 itens").
 *  Volume nunca é deduzido: sem declaração, o cartão conta itens. */
export function packLabel(
  card: Pick<OrderCardProjection, "items_count"> &
    Partial<Pick<OrderCardProjection, "volumes">>,
): string {
  const volumes = card.volumes ?? 0;
  if (volumes > 0) return `${volumes} ${volumes === 1 ? "volume" : "volumes"}`;
  if (!card.items_count) return "";
  return `${card.items_count} ${card.items_count === 1 ? "item" : "itens"}`;
}

/** O primeiro nome, quando o "nome" do cliente é mesmo um nome (não telefone nem vazio). */
export function customerFirstName(name: string): string {
  const clean = (name || "").trim();
  if (!clean || /\d/.test(clean)) return "";
  return clean.split(/\s+/)[0] ?? "";
}

type VerbSource = Pick<
  OrderCardProjection,
  "ref" | "status" | "fulfillment_type" | "next_status" | "customer_name"
>;

/** O verbo do botão largo, com o nome (v4: "Entregar a Ana", "Despachar M09").
 *
 *  Só muda o rótulo da SAÍDA, onde o fato é entregar à pessoa ou despachar: o rótulo do
 *  servidor ("Marcar como retirado") fica no `title` do botão. Os outros passos seguem
 *  com o rótulo do servidor, que é a fonte única. */
export function primaryVerb(
  card: VerbSource,
  aff: Pick<Affordance, "ref" | "label" | "disabled">,
): string {
  if (aff.ref !== "advance" || aff.disabled) return aff.label;
  if (card.next_status === "dispatched")
    return `Despachar ${splitRef(card.ref).code}`;
  if (card.status === "ready" && card.fulfillment_type === "pickup") {
    const name = customerFirstName(card.customer_name);
    return name ? `Entregar a ${name}` : `Entregar ${splitRef(card.ref).code}`;
  }
  return aff.label;
}

export type SegmentState = "done" | "working" | "waiting" | "alert";

export interface StationProgress {
  segments: Array<{ ref: string; state: SegmentState; title: string }>;
  /** "Forno e Café prontos" · "2 de 3 prontos" */
  summary: string;
  /** "falta Café" (o que ainda segura o pedido), vazio quando todas terminaram. */
  missing: string;
  /** Nomes do que falta, para "Aguardando Café". */
  missingNames: string;
  done: boolean;
}

function joinNames(names: string[]): string {
  return names.length <= 1
    ? (names[0] ?? "")
    : `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

/** A barra de progresso por estação (um traço por estação) e a frase dela. */
export function stationProgress(
  kitchen: OrderCardProjection["kitchen"],
): StationProgress | null {
  if (!kitchen || !kitchen.stations.length) return null;
  const segments = kitchen.stations.map((station) => {
    const state: SegmentState =
      station.state === "done"
        ? "done"
        : station.prints && station.paper_failed
          ? "alert"
          : station.state === "in_progress"
            ? "working"
            : "waiting";
    return {
      ref: station.station_ref,
      state,
      title: `${station.station_name}: ${station.state_label}`,
    };
  });
  const doneNames = kitchen.stations
    .filter((s) => s.state === "done")
    .map((s) => s.station_name);
  const missingNames = kitchen.stations
    .filter((s) => s.state !== "done")
    .map((s) => s.station_name);
  const done = missingNames.length === 0;
  const total = kitchen.stations.length;
  const summary = done
    ? `${joinNames(doneNames)} ${total === 1 ? "pronto" : "prontos"}`
    : `${doneNames.length} de ${total} ${doneNames.length === 1 ? "pronto" : "prontos"}`;
  const label = kitchen.missing_label || "";
  const missing = label ? label.charAt(0).toLowerCase() + label.slice(1) : "";
  return {
    segments,
    summary,
    missing,
    missingNames: joinNames(missingNames),
    done,
  };
}

/** A Saída: o primeiro cartão com o gesto da saída à mão é o "Próximo". */
export function nextOutRef(cards: OrderCardProjection[]): string {
  const first = cards.find(
    (card) =>
      card.status === "ready" &&
      (card.actions ?? []).some(
        (a) => a.ref === "advance" && a.enabled && a.priority !== "menu",
      ),
  );
  return first?.ref ?? "";
}

/** O gesto da saída de um cartão no celular (F7, dono 09/10/2026): o mesmo ato do botão
 *  largo, com o código, porque no deslize e no polegar o cartão não está todo à vista.
 *  "Entregar U13 a Ana", "Entregar U13" (sem nome), "Despachar M09". Nulo quando o
 *  cartão não tem a saída à mão (ainda não pronto, pagamento segurando, já saiu). */
export function exitGesture(
  card: OrderCardProjection,
): { action: AffordanceRef; label: string } | null {
  if (card.status !== "ready") return null;
  const advance = cardAffordances(card).find(
    (aff) =>
      aff.ref === "advance" && aff.priority === "primary" && !aff.disabled,
  );
  if (!advance) return null;
  const code = splitRef(card.ref).code;
  if (card.next_status === "dispatched")
    return { action: "advance", label: `Despachar ${code}` };
  if (card.fulfillment_type === "pickup") {
    const name = customerFirstName(card.customer_name);
    return {
      action: "advance",
      label: name ? `Entregar ${code} a ${name}` : `Entregar ${code}`,
    };
  }
  return { action: "advance", label: `${advance.label} ${code}` };
}

/** A dica dos gestos no fim da coluna do celular: só o que vale ali, com o verbo de
 *  cada lado. "Deslize à direita para entregar, à esquerda para Atender · puxe para
 *  atualizar". Sem gesto nenhum, só o puxar. */
export function swipeHint(
  zoneKey: string,
  cards: OrderCardProjection[],
  canManage: boolean,
): string {
  const verbs = [
    ...new Set(
      cards.flatMap((card) => {
        const gesture = exitGesture(card);
        return gesture ? [gesture.label.split(" ")[0]!.toLowerCase()] : [];
      }),
    ),
  ];
  const right = verbs.length ? `à direita para ${verbs.join(" ou ")}` : "";
  const left = canManage
    ? zoneKey === "intake"
      ? "Atender ou Recusar"
      : "Atender"
    : "";
  if (right && left)
    return `Deslize ${right}, à esquerda para ${left} · puxe para atualizar`;
  if (right) return `Deslize ${right} · puxe para atualizar`;
  if (left) return `Deslize para ${left} · puxe para atualizar`;
  return "Puxe para atualizar";
}

/** O excedente da Saída larga vira número: "prontos esperando (K44, T18)". */
export function waitingStripText(cards: OrderCardProjection[]): string {
  if (!cards.length) return "";
  const codes = cards.slice(0, 4).map((card) => splitRef(card.ref).code);
  const more = cards.length > 4 ? ", …" : "";
  // "prontos" só quando todos estão prontos (a Saída também guarda o que saiu para entrega).
  const ready = cards.every((card) => card.status === "ready");
  const noun = ready
    ? cards.length === 1
      ? "pronto esperando"
      : "prontos esperando"
    : "esperando";
  return `${noun} (${codes.join(", ")}${more})`;
}

/** A frase curta da coluna recolhida: a urgência que sobrevive ao recolher.
 *  Atrasados primeiro; na Entrada, o prazo mais curto ("aceita sozinho em 1:10"). */
export function stripSummary(
  zoneKey: ZoneView["key"],
  cards: OrderCardProjection[],
  nowMs: number,
): { text: string; tone: "warning" | "late" | "" } {
  const late = cards.filter(
    (card) => timerTone(card.timer_class as OrderTimerClass) === "late",
  ).length;
  if (late)
    return {
      text: late === 1 ? "1 atrasado" : `${late} atrasados`,
      tone: "late",
    };
  if (zoneKey === "intake") {
    let best: { left: number; card: OrderCardProjection } | null = null;
    for (const card of cards) {
      const ms = Date.parse(card.confirmation_deadline_iso || "");
      if (Number.isNaN(ms)) continue;
      const left = ms - nowMs;
      if (left > 0 && (!best || left < best.left)) best = { left, card };
    }
    if (best)
      return { text: cardClock(best.card, nowMs).text, tone: "warning" };
  }
  return { text: "", tone: "" };
}
