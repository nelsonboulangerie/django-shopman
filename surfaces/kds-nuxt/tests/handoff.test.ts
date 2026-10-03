// UX-G2: a Saída lê do servidor a janela do desfazer de Entregar/Despachar.
import { describe, expect, it } from "vitest";

import { handoffFromResponse, handoffSecondsLeft } from "../app/presentation/board";

describe("handoffFromResponse", () => {
  it("lê os campos da saída pedida", () => {
    expect(handoffFromResponse({ ok: true, handoff_label: "Saiu às 15:00", handoff_undo_until_iso: "2026-10-03T15:00:05Z", handoff_token: "tok" }))
      .toEqual({ handoff_label: "Saiu às 15:00", handoff_undo_until_iso: "2026-10-03T15:00:05Z", handoff_token: "tok" });
  });

  it("sem token = gravou na hora (casa sem janela)", () => {
    expect(handoffFromResponse({ ok: true, action: "dispatch" })).toBeNull();
    expect(handoffFromResponse(null)).toBeNull();
    expect(handoffFromResponse({ handoff_token: "" })).toBeNull();
  });

  it("campos tortos viram vazio, nunca undefined", () => {
    expect(handoffFromResponse({ handoff_token: "t", handoff_label: 3 })).toEqual({ handoff_label: "", handoff_undo_until_iso: "", handoff_token: "t" });
  });
});

describe("handoffSecondsLeft", () => {
  const now = Date.parse("2026-10-03T15:00:00Z");
  it("arredonda para cima os segundos que faltam", () => {
    expect(handoffSecondsLeft({ handoff_undo_until_iso: "2026-10-03T15:00:04.200Z" }, now)).toBe(5);
  });
  it("vencido ou vazio: 0", () => {
    expect(handoffSecondsLeft({ handoff_undo_until_iso: "2026-10-03T14:59:59Z" }, now)).toBe(0);
    expect(handoffSecondsLeft({ handoff_undo_until_iso: "" }, now)).toBe(0);
  });
});
