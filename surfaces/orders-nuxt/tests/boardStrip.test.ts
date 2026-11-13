// A coluna recolhida do quadro (D, dono 13/11/2026): número, sinais que pedem olho e o
// nome acessível com a frase inteira.
import { describe, expect, it } from "vitest";

import { boardStrip } from "../app/presentation/boardStrip";
import type { ZoneView } from "../app/presentation/board";
import type { OrderCardProjection } from "../app/types/orders";

const NOW = Date.parse("2026-11-13T15:00:00Z");
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const ahead = (s: number) => new Date(NOW + s * 1000).toISOString();

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "WEB-261113-A1", status: "preparing", attention: "", attention_since_iso: "", goal_minutes: 0,
    goal_label: "", elapsed_seconds: 60, created_at_iso: ago(60), ready_eta_iso: "",
    ...over,
  } as OrderCardProjection;
}
const zone = (key: ZoneView["key"], title: string): ZoneView =>
  ({ key, title, subtitle: "", icon: "", cards: [], count: 0 }) as ZoneView;

describe("boardStrip", () => {
  it("Preparo: atrasados e o próximo pronto, sem 'precisa de você' quando ninguém espera", () => {
    const strip = boardStrip(zone("prep", "Preparo"), [
      card({ ref: "A", ready_eta_iso: ago(60) }),
      card({ ref: "B", ready_eta_iso: ahead(5 * 60 + 10) }),
      card({ ref: "C", ready_eta_iso: ahead(12 * 60) }),
      card({ ref: "D" }),
    ], NOW);
    expect(strip.count).toBe(4);
    expect(strip.signals.map((s) => [s.kind, s.short])).toEqual([["late", "1"], ["next", "6′"]]);
    expect(strip.label).toBe("Abrir Preparo: 4 pedidos, 1 atrasado, próximo pronto em ~6 min");
  });

  it("Entrada: o que precisa de você não some atrás da coluna fechada", () => {
    const strip = boardStrip(zone("intake", "Entrada"), [
      card({ ref: "A", attention: "confirm", attention_since_iso: ago(60), goal_minutes: 5 }),
      card({ ref: "B", attention: "confirm", attention_since_iso: ago(8 * 60), goal_minutes: 5 }),
      card({ ref: "C" }),
    ], NOW);
    expect(strip.signals.map((s) => [s.kind, s.short])).toEqual([["need", "2"], ["late", "1"]]);
    // A previsão de pronto é só do Preparo.
    expect(strip.signals.some((s) => s.kind === "next")).toBe(false);
  });

  it("sem sinal, a tira fica com o número e o nome", () => {
    const strip = boardStrip(zone("expedition", "Saída"), [card()], NOW);
    expect(strip.signals).toEqual([]);
    expect(strip.label).toBe("Abrir Saída: 1 pedido");
  });
});
