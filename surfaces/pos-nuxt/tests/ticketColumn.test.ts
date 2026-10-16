import { describe, expect, it } from "vitest";

import { fireCellView, kitchenStateView, markRange, markedSummary, toggleMark } from "~/presentation/ticketColumn";
import { firedLineIncrease, firedLineShrink, firedLineShrinkPolicy, offersResendWithNote } from "~/presentation/firedLineChange";
import type { POSCartItem } from "~/types/pos";

const line = (id: string, qty = 1, price_q = 500): POSCartItem => ({ line_id: id, sku: id, name: id, qty, price_q, notes: "" });
const items = [line("a"), line("b", 2), line("c"), line("d")];

describe("ticketColumn — marcar sem modo", () => {
  it("a marca é literal: só a linha clicada muda, e uma marca é uma marca (dono, 13/10)", () => {
    expect([...toggleMark(new Set(), "b")]).toEqual(["b"]);
    expect([...toggleMark(new Set(["a"]), "b")]).toEqual(["a", "b"]);
    expect([...toggleMark(new Set(["a", "b"]), "a")]).toEqual(["b"]);
    expect([...toggleMark(new Set(["b"]), "b")]).toEqual([]);
  });
  it("Shift marca o intervalo, nos dois sentidos", () => {
    expect([...markRange(items, new Set(), "a", "c")]).toEqual(["a", "b", "c"]);
    expect([...markRange(items, new Set(), "d", "b")].sort()).toEqual(["b", "c", "d"]);
  });
  it("o título do bloco diz itens (nunca linhas) e o valor", () => {
    const summary = markedSummary(items, new Set(["a", "b"]));
    expect(summary.lines).toBe(2);
    expect(summary.units).toBe(3);
    expect(summary.totalQ).toBe(1500);
    expect(summary.headline).toBe("3 itens marcados");
    expect(summary.totalDisplay.replace(/\s/g, " ")).toBe("R$ 15,00");
    expect(markedSummary(items, new Set(["a"])).headline).toBe("1 item marcado");
  });
});

describe("ticketColumn — o pé segue o foco", () => {
  const base = { unfired: 4, label: "Enviar à cozinha", disabled: false, markedLines: 0, markedFirable: 0, offline: false };
  it("sem marcas: a comanda, com a contagem", () => {
    expect(fireCellView(base)).toMatchObject({ label: "Enviar à cozinha", shortLabel: "Enviar", count: 4, onlyMarked: false });
  });
  it("com marcas: 'Enviar marcados', sem chip (o título do bloco diz quantos)", () => {
    expect(fireCellView({ ...base, markedLines: 3, markedFirable: 3 })).toMatchObject({ label: "Enviar marcados", shortLabel: "Enviar", count: 0, onlyMarked: true, disabled: false });
    expect(fireCellView({ ...base, markedLines: 1, markedFirable: 1 })).toMatchObject({ label: "Enviar marcados", onlyMarked: true });
    expect(fireCellView({ ...base, markedLines: 2, markedFirable: 1 }).title).toContain("que ainda não foram");
    expect(fireCellView({ ...base, markedLines: 2, markedFirable: 0 })).toMatchObject({ label: "Marcados já na cozinha", disabled: true });
  });
  it("sem conexão: apagado com o motivo", () => {
    expect(fireCellView({ ...base, offline: true })).toMatchObject({ disabled: true, title: "Cozinha sem conexão: avise de voz" });
  });
});

describe("ticketColumn — a cozinha em palavra", () => {
  it("diz o que falta e o que já foi (o modo do envio é controle, não frase)", () => {
    expect(kitchenStateView({ unfired: 4, fired: 1 })).toEqual({ counts: "4 a enviar · 1 na cozinha" });
    expect(kitchenStateView({ unfired: 0, fired: 0 })).toEqual({ counts: "" });
  });
});

describe("firedLineChange — a decisão 5 do dono", () => {
  it("mais numa linha enviada vai numa linha nova", () => {
    expect(firedLineIncrease({ fired: true, qty: 2 }, 5)).toBe(3);
    expect(firedLineIncrease({ fired: true, qty: 2 }, 1)).toBe(0);
    expect(firedLineIncrease({ fired: false, qty: 2 }, 5)).toBe(0);
  });
  it("menos ou remover cancela na cozinha (só a diferença); pronto sai só da conta", () => {
    expect(firedLineShrinkPolicy()).toBe("cancel");
    expect(firedLineShrink({ fired: true, qty: 3, fired_qty: 3 }, 1, true)).toEqual({ kind: "cancel", units: 2, whole: false });
    expect(firedLineShrink({ fired: true, qty: 3, fired_qty: 3 }, 0, true)).toEqual({ kind: "cancel", units: 3, whole: true });
    expect(firedLineShrink({ fired: true, qty: 3, fired_qty: 3 }, 1, false)).toEqual({ kind: "account-only" });
    // A conta tinha mais do que a cozinha recebeu: tirar o excesso não cancela nada lá.
    expect(firedLineShrink({ fired: true, qty: 4, fired_qty: 2 }, 3, true)).toEqual({ kind: "none" });
    expect(firedLineShrink({ fired: false, qty: 3 }, 1, true)).toEqual({ kind: "none" });
  });
  it("observação nova numa linha cancelável oferece reenviar", () => {
    expect(offersResendWithNote({ fired: true, cancellable: true, before: "", after: "sem sal" })).toBe(true);
    expect(offersResendWithNote({ fired: true, cancellable: false, before: "", after: "sem sal" })).toBe(false);
    expect(offersResendWithNote({ fired: true, cancellable: true, before: "sem sal", after: "sem sal" })).toBe(false);
  });
});

