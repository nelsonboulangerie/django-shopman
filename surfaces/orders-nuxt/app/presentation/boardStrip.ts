// A coluna recolhida do quadro (D, dono 13/11/2026): uma tira estreita que guarda o
// lugar da coluna e diz, sem abrir, se ela pede olho. De cima para baixo: abrir, o
// número, os sinais e o nome em pé. Os sinais são só os que mudam o que o gerente faz:
//
// - "precisam de você": o servidor marcou o pedido (`attention`). Em Novos recolhido
//   é o que não pode sumir atrás da coluna fechada;
// - "atrasados": passaram da meta da etapa, ou (na Cozinha) da previsão de pronto;
// - "próximo pronto": em Em preparo, a previsão mais próxima (`ready_eta_iso`).
//
// Sem sinal, nada aparece: a tira fica com o número e o nome. Puro: testado em
// `tests/boardStrip.test.ts`.
import type { OrderCardProjection } from "~/types/orders";
import type { ZoneView } from "./board";
import { liveAge } from "./queue";

export type StripSignalKind = "need" | "late" | "next";

export interface StripSignal {
  kind: StripSignalKind;
  icon: string;
  /** O que cabe na tira: "2", "6′". */
  short: string;
  /** A frase inteira, para o nome acessível e o título. */
  label: string;
}

export interface BoardStrip {
  key: ZoneView["key"];
  title: string;
  count: number;
  signals: StripSignal[];
  /** O nome acessível do botão que abre a coluna. */
  label: string;
}

function isLate(
  card: OrderCardProjection,
  zone: ZoneView["key"],
  nowMs: number,
): boolean {
  if (liveAge(card, nowMs).tone === "late") return true;
  if (zone !== "prep") return false;
  const eta = Date.parse(card.ready_eta_iso || "");
  return Number.isFinite(eta) && eta < nowMs;
}

function nextReadyMinutes(
  cards: OrderCardProjection[],
  nowMs: number,
): number | null {
  const ahead = cards
    .map((card) => Date.parse(card.ready_eta_iso || ""))
    .filter((at) => Number.isFinite(at) && at > nowMs);
  if (!ahead.length) return null;
  return Math.max(1, Math.ceil((Math.min(...ahead) - nowMs) / 60_000));
}

export function boardStrip(
  zone: ZoneView,
  cards: OrderCardProjection[],
  nowMs: number,
): BoardStrip {
  const signals: StripSignal[] = [];
  const need = cards.filter((card) => Boolean(card.attention)).length;
  if (need)
    signals.push({
      kind: "need",
      icon: "i-lucide-hand",
      short: String(need),
      label: need === 1 ? "1 precisa de você" : `${need} precisam de você`,
    });
  const late = cards.filter((card) => isLate(card, zone.key, nowMs)).length;
  if (late)
    signals.push({
      kind: "late",
      icon: "i-lucide-alarm-clock",
      short: String(late),
      label: late === 1 ? "1 atrasado" : `${late} atrasados`,
    });
  if (zone.key === "prep") {
    const next = nextReadyMinutes(cards, nowMs);
    if (next !== null)
      signals.push({
        kind: "next",
        icon: "i-lucide-timer",
        short: `${next}′`,
        label: `próximo pronto em ~${next} min`,
      });
  }
  const facts = [`${cards.length} ${cards.length === 1 ? "pedido" : "pedidos"}`, ...signals.map((s) => s.label)];
  return {
    key: zone.key,
    title: zone.title,
    count: cards.length,
    signals,
    label: `Abrir ${zone.title}: ${facts.join(", ")}`,
  };
}
