import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  BOARD_NAME_MAX_CHARS,
  boardDisplay,
  boardNameChars,
  boardQtyChars,
  boardQtyLabel,
  boardRowSpoken,
  boardStaleNotice,
  isStale,
} from "../app/presentation/production";

describe("Letreiro — coluna de quantidade", () => {
  // Beta 05/11: "CROISSANT MANTEIGA 4200 U" perdia o N com 6 palhetas fixas.
  it("cabe a maior quantidade do dia, com a unidade", () => {
    expect(boardQtyLabel("4200")).toBe("4.200 UN");
    expect(boardQtyChars([{ qty: "12" }, { qty: "4200" }])).toBe(8);
  });
  // P1-21: massa medida em grama aparecia como "18500 UN".
  it("diz a unidade que a projeção traz: massa sempre em quilo", () => {
    expect(boardQtyLabel("12", "un")).toBe("12 UN");
    expect(boardQtyLabel("12", "")).toBe("12 UN");
    expect(boardQtyLabel("18500", "g")).toBe("18,5 KG");
    expect(boardQtyLabel("800", "g")).toBe("0,8 KG");
    expect(boardQtyLabel("3.25", "kg")).toBe("3,25 KG");
    expect(boardQtyLabel("1500", "ml")).toBe("1,5 L");
    expect(boardQtyChars([{ qty: "18500", unit: "g" }])).toBe(7);
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

describe("Letreiro — escala e nome", () => {
  it("a coluna do nome mede o maior nome do dia, com piso e teto", () => {
    expect(boardNameChars([])).toBe(12);
    expect(boardNameChars([{ recipe_name: "Baguete" }])).toBe(12);
    // P2-15: 22 palhetas fixas cortavam o nome.
    expect(
      boardNameChars([{ recipe_name: "Croissant de Amêndoas Tostadas" }]),
    ).toBe(BOARD_NAME_MAX_CHARS);
    expect(boardNameChars([{ recipe_name: "Pão de Forma Artesanal Fatiado" }]))
      .toBeLessThanOrEqual(BOARD_NAME_MAX_CHARS);
    expect(boardNameChars([{ recipe_name: "Croissant de Amêndoas" }])).toBe(21);
  });

  it("a escala cresce com a altura, sem o teto de tablet de 1,5rem", () => {
    const css = readFileSync(resolve(__dirname, "../app/pages/board.vue"), "utf8");
    const row = /--scale-row:\s*max\(([^;]+)\);/.exec(css)?.[1] ?? "";
    expect(row).toContain("5vh");
    expect(row).toContain("var(--row-chars)");
    expect(css).not.toContain("clamp(1.05rem, 2vw, 1.5rem)");
  });

  it("a voz da linha diz a unidade certa", () => {
    expect(
      boardRowSpoken({
        recipe_name: "Massa de Croissant",
        qty: "18500",
        unit: "g",
        eta_display: "8h",
        status_label: "Planejado",
      }),
    ).toBe("Massa de Croissant: 18,5 kg às 8h, Planejado");
    expect(
      boardRowSpoken({
        recipe_name: "Baguete",
        qty: "40",
        unit: "un",
        eta_display: "—",
        status_label: "Planejado",
      }),
    ).toBe("Baguete: 40 unidades, Planejado");
  });

  it("o aviso de conexão diz de quando é o quadro", () => {
    expect(boardStaleNotice("9h05")).toBe("Sem conexão. Lido às 9h05");
    expect(boardStaleNotice("")).toBe("Sem conexão. Mostrando a última leitura");
  });
});
