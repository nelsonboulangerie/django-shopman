import { describe, expect, it } from "vitest";
import {
  minutesLabel,
  momentLabel,
  preorderKitchenAnswer,
  preorderKitchenCsv,
  preorderKitchenLines,
  startedHint,
} from "~/presentation/preorderKitchen";

const row = (overrides = {}) => ({
  ref: "NB-1",
  released_at: "2026-11-14T16:15:00-03:00",
  started_at: "2026-11-14T16:27:00-03:00",
  ready_at: "2026-11-14T16:55:00-03:00",
  wait_minutes: 12,
  prep_minutes: 28,
  ...overrides,
});

describe("encomendas na Cozinha: espera e preparo", () => {
  it("tempo que não houve fica escrito, nunca zero", () => {
    expect(minutesLabel(12.5)).toBe("12,5 min");
    expect(minutesLabel(0)).toBe("0 min");
    expect(minutesLabel(null)).toBe("Sem medida");
  });

  it("a hora da loja, como o servidor gravou", () => {
    expect(momentLabel("2026-11-14T16:15:00-03:00")).toBe("14/11 16:15");
    expect(momentLabel(null)).toBe("");
  });

  it("responde com as duas medianas, ou diz o que falta", () => {
    expect(preorderKitchenAnswer({ orders: 0, wait_median_minutes: null, prep_median_minutes: null })).toBe(
      "Nenhuma encomenda chegou à Cozinha no período.",
    );
    expect(preorderKitchenAnswer({ orders: 2, wait_median_minutes: null, prep_median_minutes: null })).toBe(
      "Nenhuma encomenda do período foi iniciada ainda.",
    );
    expect(preorderKitchenAnswer({ orders: 2, wait_median_minutes: 10, prep_median_minutes: null })).toBe(
      "Na mediana, a encomenda esperou 10 min pelo Iniciar.",
    );
    expect(preorderKitchenAnswer({ orders: 2, wait_median_minutes: 10, prep_median_minutes: 24 })).toBe(
      "Na mediana, a encomenda esperou 10 min pelo Iniciar e ficou pronta 24 min depois.",
    );
    expect(startedHint({ started: 1, ready: 0 })).toBe("1 iniciada, 0 prontas");
  });

  it("a linha da encomenda ainda não iniciada não inventa tempo", () => {
    const [done, waiting] = preorderKitchenLines([
      row(),
      row({ ref: "NB-2", started_at: null, ready_at: null, wait_minutes: null, prep_minutes: null }),
    ]);
    expect(done).toMatchObject({ started: "14/11 16:27", ready: "14/11 16:55", wait: "12 min", prep: "28 min" });
    expect(waiting).toMatchObject({ started: "Ainda não iniciada", ready: "", wait: "", prep: "" });
    expect(preorderKitchenCsv([row({ prep_minutes: null })]).rows[0]).toEqual([
      "NB-1",
      "2026-11-14T16:15:00-03:00",
      "2026-11-14T16:27:00-03:00",
      "2026-11-14T16:55:00-03:00",
      12,
      "",
    ]);
  });
});
