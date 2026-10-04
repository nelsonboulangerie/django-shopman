// A Fila "Precisa de você" (V4-G4, prévia v4 `gestor-fila4.html`): só o que espera um
// fato humano, por urgência (tempo contra a meta da etapa), com o resto resumido num
// número e no agregado "Em andamento". O servidor diz o fato (`attention`), desde quando
// a etapa conta (`attention_since_iso`) e a meta (`goal_minutes`, `goal_label`); aqui só
// se mede contra o relógio e se ordena. Puro: testado em `tests/queue.test.ts`.
import type { OrderCardProjection } from "~/types/orders";
import { cardAffordances, secondsSince, splitRef, type Affordance } from "./board";

export type QueueTone = "ok" | "warning" | "late";

/** O recorte da Fila (v4): "Precisa de você" (o padrão), "Todos" e "Atrasados". */
export type QueueScope = "attention" | "all" | "late";
/** A ordem da Fila ("Urgência ▾"): tempo contra a meta, chegada ou os mais novos. */
export type QueueSort = "urgency" | "arrival" | "recent";

export const QUEUE_SORT_OPTIONS: { key: QueueSort; label: string; hint: string }[] = [
  { key: "urgency", label: "Urgência", hint: "Mais urgente primeiro (tempo contra a meta)" },
  { key: "arrival", label: "Chegada", hint: "Quem chegou primeiro no topo" },
  { key: "recent", label: "Mais recentes", hint: "O que acabou de chegar no topo" },
];

/** Quantos itens a Fila mostra em foco; o resto vira "+N" (SPEC4 §4, densidade pela atenção). */
export const QUEUE_FOCUS = 4;

export interface QueueItem {
  card: OrderCardProjection;
  /** O fato que o pedido espera; ``""`` no recorte "Todos" para o que não pede ninguém. */
  kind: string;
  /** Segundos na etapa (desde `attention_since_iso`). */
  seconds: number;
  /** "27 min" */
  timeLabel: string;
  /** "meta 30" · "no balcão" · o estado ("Em preparo") de quem não pede ninguém */
  goalLabel: string;
  tone: QueueTone;
  /** Fração da meta já gasta (1 = venceu). Ordena a Fila. */
  urgency: number;
  /** Segundos até o sistema CANCELAR sozinho (prazo duro); ``null`` sem prazo de perda. */
  cancelsIn: number | null;
}

/** Minutos inteiros, como a prévia escreve ("27 min", "1h 5 min"). */
export function minutesLabel(seconds: number): string {
  const m = Math.floor(Math.max(0, seconds) / 60);
  if (m < 60) return `${m} min`;
  const rest = m % 60;
  return rest ? `${Math.floor(m / 60)}h ${rest} min` : `${Math.floor(m / 60)}h`;
}

/** O tom do número: passou da meta é atraso; a partir de 80% dela, atenção. */
export function goalTone(seconds: number, goalMinutes: number): QueueTone {
  if (!goalMinutes) return "ok";
  const ratio = seconds / (goalMinutes * 60);
  if (ratio >= 1) return "late";
  if (ratio >= 0.8) return "warning";
  return "ok";
}

/** A cor do tempo (G03). Atenção ao tempo é um número com INTENSIDADE, sempre no âmbar:
 *  vermelho é só "bloqueado com motivo" (a pílula do cadeado), nunca o relógio. */
export function queueToneClass(tone: QueueTone): string {
  if (tone === "late") return "font-bold text-warning";
  if (tone === "warning") return "text-warning";
  return "text-foreground";
}

function cancelSeconds(card: OrderCardProjection, nowMs: number): number | null {
  if (card.confirmation_action !== "cancel" || !card.confirmation_deadline_iso) return null;
  const at = Date.parse(card.confirmation_deadline_iso);
  return Number.isFinite(at) ? Math.max(0, Math.round((at - nowMs) / 1000)) : null;
}

function itemFor(card: OrderCardProjection, nowMs: number): QueueItem {
  if (!card.attention) {
    const seconds = secondsSince(card.created_at_iso, nowMs) ?? card.elapsed_seconds ?? 0;
    return { card, kind: "", seconds, timeLabel: minutesLabel(seconds), goalLabel: card.status_label, tone: "ok", urgency: 0, cancelsIn: null };
  }
  const seconds = secondsSince(card.attention_since_iso, nowMs) ?? card.elapsed_seconds ?? 0;
  const goal = card.goal_minutes || 0;
  return {
    card,
    kind: card.attention,
    seconds,
    timeLabel: minutesLabel(seconds),
    goalLabel: card.goal_label,
    tone: goalTone(seconds, goal),
    urgency: goal ? seconds / (goal * 60) : 0,
    cancelsIn: cancelSeconds(card, nowMs),
  };
}

/** A ordem "mais urgente primeiro" (G11): o pedido que o sistema vai CANCELAR sozinho
 *  passa à frente (perder a venda não se desfaz), o de prazo mais curto primeiro; depois,
 *  o tempo contra a meta; empate, o mais antigo. */
function byUrgency(a: QueueItem, b: QueueItem): number {
  if (a.cancelsIn !== null || b.cancelsIn !== null) {
    if (a.cancelsIn === null) return 1;
    if (b.cancelsIn === null) return -1;
    if (a.cancelsIn !== b.cancelsIn) return a.cancelsIn - b.cancelsIn;
  }
  return b.urgency - a.urgency || b.seconds - a.seconds || a.card.ref.localeCompare(b.card.ref);
}

/** Os pedidos do recorte, na ordem pedida. "Precisa de você": só o que espera alguém;
 *  "Atrasados": desses, os que passaram da meta; "Todos": também o que está andando. */
export function queueItems(
  cards: OrderCardProjection[],
  nowMs: number,
  opts: { scope?: QueueScope; sort?: QueueSort } = {},
): QueueItem[] {
  const scope = opts.scope ?? "attention";
  const seen = new Set<string>();
  const items: QueueItem[] = [];
  for (const card of cards) {
    if (seen.has(card.ref) || (!card.attention && scope !== "all")) continue;
    seen.add(card.ref);
    const item = itemFor(card, nowMs);
    if (scope === "late" && item.tone !== "late") continue;
    items.push(item);
  }
  const sort = opts.sort ?? "urgency";
  if (sort === "arrival") return items.sort((a, b) => a.card.created_at_iso.localeCompare(b.card.created_at_iso));
  if (sort === "recent") return items.sort((a, b) => b.card.created_at_iso.localeCompare(a.card.created_at_iso));
  // No "Todos", o que pede alguém vem antes do que só está andando.
  return items.sort((a, b) => Number(!a.kind) - Number(!b.kind) || byUrgency(a, b));
}

/** As contagens dos recortes: "Precisa de você N · Todos N · ● Atrasados N". */
export function queueScopeCounts(cards: OrderCardProjection[], nowMs: number): Record<QueueScope, number> {
  const attention = queueItems(cards, nowMs);
  return {
    attention: attention.length,
    late: attention.filter((item) => item.tone === "late").length,
    all: new Set(cards.map((card) => card.ref)).size,
  };
}

export interface ProgressLine {
  key: "kitchen" | "road";
  label: string;
  icon: string;
  count: number;
  /** "o mais antigo há 18 min" · "" sem pedido */
  detail: string;
}

const KITCHEN = new Set(["accepted", "preparing"]);
const ROAD = new Set(["dispatched", "delivered"]);

/** "Em andamento": o que não pede ninguém, agregado (Na Cozinha, Na rua). */
export function inProgress(cards: OrderCardProjection[], nowMs: number): ProgressLine[] {
  const quiet = cards.filter((card) => !card.attention);
  const oldest = (list: OrderCardProjection[], since: (card: OrderCardProjection) => string) => {
    const ages = list.map((card) => secondsSince(since(card), nowMs) ?? card.elapsed_seconds ?? 0);
    return ages.length ? Math.max(...ages) : 0;
  };
  const kitchen = quiet.filter((card) => KITCHEN.has(card.status));
  const road = quiet.filter((card) => ROAD.has(card.status));
  const detail = (count: number, seconds: number) => (count ? `o mais antigo há ${minutesLabel(seconds)}` : "");
  return [
    { key: "kitchen", label: "Na Cozinha", icon: "lucide:cooking-pot", count: kitchen.length, detail: kitchenDetail(kitchen, nowMs, oldest(kitchen, (card) => card.created_at_iso)) },
    { key: "road", label: "Na rua", icon: "lucide:bike", count: road.length, detail: detail(road.length, oldest(road, (card) => card.dispatched_at_iso || card.created_at_iso)) },
  ];
}

/** "próximo pronto em ~4 min" (G10): a previsão mais próxima entre os pedidos na Cozinha
 *  (`ready_eta_iso`, do início real mais o tempo que os preparos estão levando). Sem
 *  previsão, ou com ela vencida, o fato que se sabe: o mais antigo e há quanto tempo. */
export function kitchenDetail(kitchen: OrderCardProjection[], nowMs: number, oldestSeconds: number): string {
  if (!kitchen.length) return "";
  const etas = kitchen.map((card) => Date.parse(card.ready_eta_iso || "")).filter((at) => Number.isFinite(at));
  const oldest = `o mais antigo há ${minutesLabel(oldestSeconds)}`;
  if (!etas.length) return oldest;
  const left = (Math.min(...etas) - nowMs) / 1000;
  if (left <= 0) return `${oldest} · passou da previsão`;
  return `próximo pronto em ~${Math.max(1, Math.ceil(left / 60))} min`;
}

/** O excedente da Fila num número só (nunca paginação): os que ainda pedem você além dos
 *  em foco e o que está andando. "+7 em andamento, nada pede você: 5 na Cozinha, 2 na rua";
 *  com fila escondida, "+12: mais 5 pedem você · em andamento: 5 na Cozinha, 2 na rua". */
export function restLine(lines: ProgressLine[], hidden = 0): { count: number; text: string } {
  const moving = lines.reduce((n, line) => n + line.count, 0);
  const count = moving + hidden;
  if (!count) return { count: 0, text: "" };
  const parts = lines.filter((line) => line.count).map((line) => `${line.count} ${line.label.toLowerCase()}`);
  if (!hidden) return { count, text: `em andamento, nada pede você: ${parts.join(", ")}` };
  const ask = `mais ${hidden} ${hidden === 1 ? "pede" : "pedem"} você`;
  return { count, text: parts.length ? `${ask} · em andamento: ${parts.join(", ")}` : ask };
}

export interface QueueGesture {
  /** O gesto principal: o fato humano, com o verbo da v4 ("Aceitar", "Saiu", "Retirou"). */
  primary: (Affordance & { verb: string }) | null;
  /** O secundário, quando a prévia mostra um ("Recusar"). */
  secondary: Affordance | null;
  /** Atalho impresso no botão. */
  shortcut: string;
}

/** O botão da linha: só o fato humano é botão (v4). O rótulo do servidor vira `title`. */
export function queueGesture(item: QueueItem): QueueGesture {
  if (!item.kind) return { primary: null, secondary: null, shortcut: "" };
  const affordances = cardAffordances(item.card);
  const primary = affordances.find((aff) => aff.priority === "primary" || aff.disabled) ?? null;
  const secondary = item.kind === "confirm" ? affordances.find((aff) => aff.ref === "reject") ?? null : null;
  if (!primary) return { primary: null, secondary, shortcut: "" };
  let verb = primary.label;
  if (!primary.disabled) {
    if (primary.ref === "confirm") verb = "Aceitar";
    else if (item.kind === "dispatch" && primary.ref === "advance") verb = "Saiu";
    else if (item.kind === "handoff" && primary.ref === "advance") verb = item.card.fulfillment_type === "delivery" ? "Entregue" : "Retirou";
  }
  return { primary: { ...primary, verb }, secondary, shortcut: primary.ref === "confirm" && !primary.disabled ? "A" : "Enter" };
}

/** "João Oliveira" e o resto da linha ("Entrega · Rua Paranaguá, 800 · iFood"). */
export function queueWho(card: OrderCardProjection, channel: string): { name: string; rest: string } {
  const parts = [card.fulfillment_label];
  if (card.delivery_address) parts.push(card.delivery_address);
  if (channel) parts.push(channel);
  return { name: card.customer_name || "Sem cliente", rest: parts.filter(Boolean).join(" · ") };
}

/** O código curto da linha ("R7K"). */
export function queueCode(card: Pick<OrderCardProjection, "ref">): string {
  return splitRef(card.ref).code;
}

