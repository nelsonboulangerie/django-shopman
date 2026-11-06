import { describe, expect, it } from "vitest";
import {
  boardDisplay,
  boardQtyChars,
  boardQtyLabel,
  isStale,
} from "../app/presentation/production";

describe("Letreiro — coluna de quantidade", () => {
  // Beta 05/11: "CROISSANT MANTEIGA 4200 U" perdia o N com 6 palhetas fixas.
  it("cabe a maior quantidade do dia, com a unidade", () => {
    expect(boardQtyLabel("4200")).toBe("4200 UN");
    expect(boardQtyChars([{ qty: "12" }, { qty: "4200" }])).toBe(7);
  });
  it("nunca encolhe abaixo de 999 UN", () => {
    expect(boardQtyChars([])).toBe(6);
    expect(boardQtyChars([{ qty: "8" }])).toBe(6);
  });
});

describe("boardDisplay — stale-tolerant board state", () => {
  it("shows the board whenever there is data, even mid-refresh or after a failed poll", () => {
    expect(boardDisplay({ pending: true, error: false, hasData: true })).toBe("ready");
    expect(boardDisplay({ pending: false, error: true, hasData: true })).toBe("ready");
  });

  it("only shows loading/error/empty when there is NO data to show", () => {
    expect(boardDisplay({ pending: true, error: false, hasData: false })).toBe("loading");
    expect(boardDisplay({ pending: false, error: true, hasData: false })).toBe("error");
    expect(boardDisplay({ pending: false, error: false, hasData: false })).toBe("empty");
  });

  it("prefers loading over error on the very first paint (no data yet)", () => {
    expect(boardDisplay({ pending: true, error: true, hasData: false })).toBe("loading");
  });
});

describe("isStale — honest degradation cue", () => {
  it("is stale only when data is present AND the last refresh errored", () => {
    expect(isStale({ error: true, hasData: true })).toBe(true);
    expect(isStale({ error: true, hasData: false })).toBe(false); // nothing to be stale about
    expect(isStale({ error: false, hasData: true })).toBe(false); // fresh
  });
});
