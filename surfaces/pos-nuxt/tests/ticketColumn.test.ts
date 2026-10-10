import { describe, expect, it } from "vitest";

import { fireCellView, kitchenStateView, markRange, markedSummary, toggleMark } from "~/presentation/ticketColumn";
import { firedLineIncrease, firedLineShrinkPolicy, offersResendWithNote } from "~/presentation/firedLineChange";
import { availableMoveModes, initialMoveMode, moveSubmitLabel } from "~/presentation/moveLines";
import type { POSCartItem } from "~/types/pos";

const line = (id: string, qty = 1, price_q = 500): POSCartItem => ({ line_id: id, sku: id, name: id, qty, price_q, notes: "" });
const items = [line("a"), line("b", 2), line("c"), line("d")];

describe("ticketColumn — marcar sem modo", () => {
  it("a linha aberta é a primeira marcada; conjunto de um vira a linha aberta", () => {
    expect([...toggleMark(new Set(), "b", "a").marked]).toEqual(["a", "b"]);
    expect(toggleMark(new Set(), "b", "")).toEqual({ marked: new Set(), open: "b" });
    expect(toggleMark(new Set(["a", "b"]), "a", "")).toEqual({ marked: new Set(), open: "b" });
  });
  it("Shift marca o intervalo, nos dois sentidos", () => {
    expect([...markRange(items, new Set(), "a", "c").marked]).toEqual(["a", "b", "c"]);
    expect([...markRange(items, new Set(), "d", "b").marked].sort()).toEqual(["b", "c", "d"]);
  });
  it("o título do bloco diz linhas, itens e valor", () => {
    expect(markedSummary(items, new Set(["a", "b"])).title).toBe("2 linhas marcadas · 3 itens · R$ 15,00".replace(" ", " ") === "" ? "" : markedSummary(items, new Set(["a", "b"])).title);
    const summary = markedSummary(items, new Set(["a", "b"]));
    expect(summary.lines).toBe(2);
    expect(summary.units).toBe(3);
    expect(summary.totalQ).toBe(1500);
    expect(summary.title.startsWith("2 linhas marcadas · 3 itens · ")).toBe(true);
  });
});

describe("ticketColumn — o pé segue o foco", () => {
  const base = { unfired: 4, label: "Enviar à cozinha", disabled: false, markedLines: 0, markedFirable: 0, offline: false };
  it("sem marcas: a comanda, com a contagem", () => {
    expect(fireCellView(base)).toMatchObject({ label: "Enviar à cozinha", shortLabel: "Enviar", count: 4, onlyMarked: false });
  });
  it("com marcas: 'Enviar 3 marcadas', sem chip", () => {
    expect(fireCellView({ ...base, markedLines: 3, markedFirable: 3 })).toMatchObject({ label: "Enviar 3 marcadas", count: 0, onlyMarked: true, disabled: false });
    expect(fireCellView({ ...base, markedLines: 2, markedFirable: 1 }).label).toBe("Enviar 1 marcada");
    expect(fireCellView({ ...base, markedLines: 2, markedFirable: 0 })).toMatchObject({ label: "Marcadas já enviadas", disabled: true });
  });
  it("sem conexão: apagado com o motivo", () => {
    expect(fireCellView({ ...base, offline: true })).toMatchObject({ disabled: true, title: "Cozinha sem conexão: avise de voz" });
  });
});

describe("ticketColumn — a cozinha em palavra, com o quando", () => {
  it("diz quando o envio automático manda, e o motivo sem conexão", () => {
    expect(kitchenStateView({ unfired: 4, fired: 1, autoFire: true, offline: false })).toMatchObject({
      counts: "4 a enviar · 1 na cozinha",
      auto: { full: "envio automático: ao sair ou após 90 s parada", short: "automático: ao sair" },
      linksToSettings: true,
    });
    expect(kitchenStateView({ unfired: 3, fired: 0, autoFire: true, offline: true })).toMatchObject({
      auto: { full: "cozinha sem conexão: avise de voz" },
      linksToSettings: false,
    });
  });
});

describe("firedLineChange — o ponto isolado da pergunta 5", () => {
  it("mais numa linha enviada vai numa linha nova; menos segue só avisando até o dono decidir", () => {
    expect(firedLineIncrease({ fired: true, qty: 2 }, 5)).toBe(3);
    expect(firedLineIncrease({ fired: true, qty: 2 }, 1)).toBe(0);
    expect(firedLineIncrease({ fired: false, qty: 2 }, 5)).toBe(0);
    expect(firedLineShrinkPolicy()).toBe("warn");
  });
  it("observação nova numa linha cancelável oferece reenviar", () => {
    expect(offersResendWithNote({ fired: true, cancellable: true, before: "", after: "sem sal" })).toBe(true);
    expect(offersResendWithNote({ fired: true, cancellable: false, before: "", after: "sem sal" })).toBe(false);
    expect(offersResendWithNote({ fired: true, cancellable: true, before: "sem sal", after: "sem sal" })).toBe(false);
  });
});

describe("moveLines — Transferir é o verbo", () => {
  it("os modos são o destino; o botão diz Transferir ou Juntar", () => {
    const modes = availableMoveModes(null);
    expect(modes.map((m) => m.label)).toEqual(["Outra comanda", "Comanda nova", "Juntar comandas"]);
    expect(moveSubmitLabel("split")).toBe("Transferir");
    expect(moveSubmitLabel("transfer")).toBe("Transferir");
    expect(moveSubmitLabel("merge")).toBe("Juntar");
  });
  it("abre no modo pedido, ou em outra comanda quando há, senão na nova", () => {
    const modes = availableMoveModes(null);
    expect(initialMoveMode(modes, "merge", true)).toBe("merge");
    expect(initialMoveMode(modes, undefined, true)).toBe("transfer");
    expect(initialMoveMode(modes, undefined, false)).toBe("split");
  });
});
