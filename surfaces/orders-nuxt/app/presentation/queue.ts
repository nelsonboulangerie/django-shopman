// A Fila "Precisa de você" (V4-G4, prévia v4 `gestor-fila4.html`): só o que espera um
// fato humano, por urgência (tempo contra a meta da etapa), com o resto resumido num
// número e no agregado "Em andamento". O servidor diz o fato (`attention`), desde quando
// a etapa conta (`attention_since_iso`) e a meta (`goal_minutes`, `goal_label`); aqui só
// se mede contra o relógio e se ordena. Puro: testado em `tests/queue.test.ts`.
import type { OrderCardProjection } from "~/types/orders";
import { cardAffordances, secondsSince, splitRef, type Affordance } from "./board";

export type QueueTone = "ok" | "warning" | "late";

export interface QueueItem {
  card: OrderCardProjection;
  kind: string;
  /** Segundos na etapa (desde `attention_since_iso`). */
  seconds: number;
  /** "27 min" */
  timeLabel: string;
  /** "meta 30" · "no balcão" */
  goalLabel: string;
  tone: QueueTone;
  /** Fração da meta já gasta (1 = venceu). Ordena a Fila. */
  urgency: number;
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

/** Os pedidos que esperam alguém, o mais urgente primeiro (empate: o mais antigo). */
export function queueItems(cards: OrderCardProjection[], nowMs: number): QueueItem[] {
  const seen = new Set<string>();
  const items: QueueItem[] = [];
  for (const card of cards) {
    if (!card.attention || seen.has(card.ref)) continue;
    seen.add(card.ref);
    const seconds = secondsSince(card.attention_since_iso, nowMs) ?? card.elapsed_seconds ?? 0;
    const goal = card.goal_minutes || 0;
    items.push({
      card,
      kind: card.attention,
      seconds,
      timeLabel: minutesLabel(seconds),
      goalLabel: card.goal_label,
      tone: goalTone(seconds, goal),
      urgency: goal ? seconds / (goal * 60) : 0,
    });
  }
  return items.sort((a, b) => b.urgency - a.urgency || b.seconds - a.seconds || a.card.ref.localeCompare(b.card.ref));
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
    { key: "kitchen", label: "Na Cozinha", icon: "lucide:cooking-pot", count: kitchen.length, detail: detail(kitchen.length, oldest(kitchen, (card) => card.created_at_iso)) },
    { key: "road", label: "Na rua", icon: "lucide:bike", count: road.length, detail: detail(road.length, oldest(road, (card) => card.dispatched_at_iso || card.created_at_iso)) },
  ];
}

/** "+7 em andamento, nada pede você: 5 na Cozinha, 2 na rua" (vazio sem resto). */
export function restLine(lines: ProgressLine[]): { count: number; text: string } {
  const count = lines.reduce((n, line) => n + line.count, 0);
  if (!count) return { count: 0, text: "" };
  const parts = lines.filter((line) => line.count).map((line) => `${line.count} ${line.label.toLowerCase()}`);
  return { count, text: `em andamento, nada pede você: ${parts.join(", ")}` };
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

