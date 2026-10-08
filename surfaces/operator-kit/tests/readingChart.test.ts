import { describe, expect, it } from "vitest";

import {
  divergingText,
  nextReadingIndex,
  readingChartCsv,
  readingCsvFileName,
  readingCsvText,
  readingLegend,
  readingPointSummary,
  readingTableRows,
  readingTickIndices,
  readingYDomain,
  type ReadingChartPoint,
  type ReadingChartSeries,
  type ReadingDivergingLabels,
} from "../app/presentation/readingChart";

const revenue: ReadingChartSeries[] = [
  { key: "current", label: "Esta semana" },
  { key: "previous", label: "Semana anterior" },
];
const days: ReadingChartPoint[] = [
  { label: "Seg 05/10", values: { current: 3180, previous: 2950 } },
  { label: "Qua 07/10", values: { current: 3310, previous: null } },
];
const overShort: ReadingDivergingLabels = { positive: "Sobrou", negative: "Faltou" };
const difference: ReadingChartSeries[] = [{ key: "difference", label: "Sobra ou falta" }];

describe("a frase do ponto em leitura", () => {
  it("diz o rótulo e cada série com o seu valor", () => {
    expect(readingPointSummary(days[0]!, "comparison", revenue)).toBe(
      "Seg 05/10: Esta semana 3.180; Semana anterior 2.950",
    );
  });

  it("ponto sem dado diz que não tem dado, nunca zero", () => {
    expect(readingPointSummary(days[1]!, "comparison", revenue)).toBe(
      "Qua 07/10: Esta semana 3.310; Semana anterior sem dado",
    );
  });

  it("o divergente diz o lado com a palavra dele e sem sinal", () => {
    const point = (value: number | null): ReadingChartPoint => ({ label: "Croissant", values: { difference: value } });
    expect(readingPointSummary(point(6), "diverging", difference, undefined, overShort)).toBe("Croissant: Sobrou 6");
    expect(readingPointSummary(point(-4), "diverging", difference, undefined, overShort)).toBe("Croissant: Faltou 4");
    expect(readingPointSummary(point(0), "diverging", difference, undefined, overShort)).toBe(
      "Croissant: Sem diferença",
    );
    expect(divergingText(0, { ...overShort, zero: "Vendeu o que fez" }, String)).toBe("Vendeu o que fez");
  });

  it("usa o formato do consumidor", () => {
    const money = (value: number) => `R$ ${value}`;
    expect(readingPointSummary(days[0]!, "bars", revenue.slice(0, 1), money)).toBe("Seg 05/10: Esta semana R$ 3180");
  });
});

describe("legenda", () => {
  it("a comparação desenha a segunda série como traço tracejado", () => {
    expect(readingLegend("comparison", revenue)).toEqual([
      { label: "Esta semana", tone: "primary", dashed: false },
      { label: "Semana anterior", tone: "neutral", dashed: true },
    ]);
  });

  it("o divergente mostra os dois lados, com a cor de cada um", () => {
    expect(readingLegend("diverging", difference, { ...overShort, positiveTone: "warning" })).toEqual([
      { label: "Sobrou", tone: "warning", dashed: false },
      { label: "Faltou", tone: "error", dashed: false },
    ]);
  });
});

describe("eixo e domínio", () => {
  it("até o teto, todo ponto tem rótulo", () => {
    expect(readingTickIndices(6, 6)).toEqual([0, 1, 2, 3, 4, 5]);
  });

  it("trinta dias mostram no máximo o teto, com a primeira e a última pontas", () => {
    const ticks = readingTickIndices(30, 6);
    expect(ticks.length).toBeLessThanOrEqual(6);
    expect(ticks[0]).toBe(0);
    expect(ticks.at(-1)).toBe(29);
  });

  it("o domínio sempre contém o zero, e o divergente fica com os dois lados", () => {
    expect(readingYDomain("bars", revenue, days)).toEqual([0, 3310]);
    const points = [
      { label: "a", values: { difference: 6 } },
      { label: "b", values: { difference: -4 } },
    ];
    expect(readingYDomain("diverging", difference, points)).toEqual([-4, 6]);
    expect(readingYDomain("line", difference, [])).toEqual([0, 1]);
  });
});

describe("teclado", () => {
  it("setas andam um ponto, sem passar das pontas", () => {
    expect(nextReadingIndex(null, "ArrowRight", 3)).toBe(0);
    expect(nextReadingIndex(0, "ArrowRight", 3)).toBe(1);
    expect(nextReadingIndex(2, "ArrowRight", 3)).toBe(2);
    expect(nextReadingIndex(null, "ArrowLeft", 3)).toBe(2);
    expect(nextReadingIndex(0, "ArrowLeft", 3)).toBe(0);
  });

  it("Home e End vão às pontas; Escape solta; tecla alheia segue para o navegador", () => {
    expect(nextReadingIndex(1, "Home", 3)).toBe(0);
    expect(nextReadingIndex(1, "End", 3)).toBe(2);
    expect(nextReadingIndex(1, "Escape", 3)).toBeNull();
    expect(nextReadingIndex(null, "Escape", 3)).toBeUndefined();
    expect(nextReadingIndex(1, "Tab", 3)).toBeUndefined();
    expect(nextReadingIndex(null, "ArrowRight", 0)).toBeUndefined();
  });
});

describe("tabela equivalente e CSV", () => {
  it("a tabela traz os mesmos números, formatados como o gráfico os diz", () => {
    expect(readingTableRows("comparison", revenue, days)).toEqual([
      { label: "Seg 05/10", current: "3.180", previous: "2.950" },
      { label: "Qua 07/10", current: "3.310", previous: "sem dado" },
    ]);
  });

  it("o CSV leva número cru, e o ponto sem dado vira célula vazia", () => {
    expect(readingChartCsv("Dia", revenue, days)).toEqual({
      header: ["Dia", "Esta semana", "Semana anterior"],
      rows: [
        ["Seg 05/10", 3180, 2950],
        ["Qua 07/10", 3310, ""],
      ],
    });
  });

  it("ponto e vírgula, aspas onde precisa, e a marca de ordem de bytes", () => {
    const text = readingCsvText({ header: ["Produto", "Qtd"], rows: [['Pão "da casa"; grande', 2]] });
    expect(text.startsWith("\uFEFF")).toBe(true);
    expect(text.slice(1).split("\n")).toEqual(["Produto;Qtd", '"Pão ""da casa""; grande";2']);
  });

  it("o nome do arquivo sai do título, sem acento", () => {
    expect(readingCsvFileName("Faturamento por dia")).toBe("faturamento-por-dia.csv");
    expect(readingCsvFileName("Pão & Café: Sábado")).toBe("pao-cafe-sabado.csv");
    expect(readingCsvFileName("!!!")).toBe("quadro.csv");
  });
});
