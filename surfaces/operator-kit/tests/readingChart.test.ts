import { describe, expect, it } from "vitest";

import {
  divergingText,
  nextReadingIndex,
  readingAxisFormat,
  readingChartCsv,
  readingCsvFileName,
  readingCsvMoney,
  readingCsvNumber,
  readingCsvText,
  readingFillColor,
  readingHorizontalHeight,
  readingMoneyAxisFormat,
  readingMoneyFormat,
  readingRunIndex,
  readingRuns,
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
const madeSold: ReadingChartSeries[] = [
  { key: "sold", label: "Vendeu" },
  { key: "leftover", label: "Sobrou", tone: "primary", fill: "tint" },
  { key: "lost", label: "Vendas perdidas", tone: "error", fill: "hatch" },
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
      { label: "Esta semana", tone: "primary", dashed: false, fill: "solid" },
      { label: "Semana anterior", tone: "neutral", dashed: true, fill: "solid" },
    ]);
  });

  it("o divergente mostra os dois lados, com a cor de cada um", () => {
    expect(readingLegend("diverging", difference, { ...overShort, positiveTone: "warning" })).toEqual([
      { label: "Sobrou", tone: "warning", dashed: false, fill: "solid" },
      { label: "Faltou", tone: "error", dashed: false, fill: "solid" },
    ]);
  });

  it("o empilhado leva o preenchimento de cada segmento, a segunda codificação além da cor", () => {
    expect(readingLegend("stacked", madeSold)).toEqual([
      { label: "Vendeu", tone: "primary", dashed: false, fill: "solid" },
      { label: "Sobrou", tone: "primary", dashed: false, fill: "tint" },
      { label: "Vendas perdidas", tone: "error", dashed: false, fill: "hatch" },
    ]);
  });

  it("o claro é o mesmo tom a 30%; cheio e listrado usam o tom puro", () => {
    expect(readingFillColor("primary")).toBe("var(--ui-primary)");
    expect(readingFillColor("primary", "tint")).toBe("color-mix(in srgb, var(--ui-primary) 30%, transparent)");
    expect(readingFillColor("error", "hatch")).toBe("var(--ui-error)");
  });
});

describe("empilhado", () => {
  const products: ReadingChartPoint[] = [
    { label: "Chausson", values: { sold: 0, leftover: 28, lost: 0 } },
    { label: "Croissant", values: { sold: 44, leftover: 0, lost: 14 } },
  ];

  it("o domínio é a soma dos segmentos da barra mais longa", () => {
    expect(readingYDomain("stacked", madeSold, products)).toEqual([0, 58]);
    expect(readingYDomain("stacked", madeSold, [])).toEqual([0, 1]);
  });

  it("a frase do ponto diz cada segmento, inclusive o zero", () => {
    expect(readingPointSummary(products[0]!, "stacked", madeSold)).toBe(
      "Chausson: Vendeu 0; Sobrou 28; Vendas perdidas 0",
    );
  });

  it("deitado, uma faixa por ponto mais a régua", () => {
    expect(readingHorizontalHeight(8)).toBe(8 * 40 + 32);
    expect(readingHorizontalHeight(0)).toBe(40 + 32);
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

  it("o CSV leva o número, e o ponto sem dado vira célula vazia", () => {
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

  it("número em pt-BR: vírgula decimal, sem separador de milhar", () => {
    expect(readingCsvNumber(1.2)).toBe("1,2");
    expect(readingCsvNumber(1234567.891)).toBe("1234567,891");
    expect(readingCsvNumber(-0.5)).toBe("-0,5");
    expect(readingCsvNumber(3180)).toBe("3180");
    const text = readingCsvText({ header: ["Hora", "Média"], rows: [["12h", 1.2], ["13h", 12345.75]] });
    expect(text.slice(1).split("\n")).toEqual(["Hora;Média", "12h;1,2", "13h;12345,75"]);
  });

  it("dinheiro em reais: duas casas com vírgula, sem R$ na célula, unidade no cabeçalho", () => {
    expect(readingCsvMoney(1500.5)).toBe("1500,50");
    expect(readingCsvMoney(15000)).toBe("15000,00");
    const priced: ReadingChartPoint[] = [
      { label: "Seg 05/10", values: { current: 15000.5, previous: 1234.567 } },
      { label: "Qua 07/10", values: { current: 3310, previous: null } },
    ];
    const csv = readingChartCsv("Dia", revenue, priced, { money: true });
    expect(csv).toEqual({
      header: ["Dia", "Esta semana (R$)", "Semana anterior (R$)"],
      rows: [
        ["Seg 05/10", "15000,50", "1234,57"],
        ["Qua 07/10", "3310,00", ""],
      ],
    });
    expect(readingCsvText(csv).slice(1).split("\n")[1]).toBe("Seg 05/10;15000,50;1234,57");
  });

  it("o nome do arquivo sai do título, sem acento", () => {
    expect(readingCsvFileName("Faturamento por dia")).toBe("faturamento-por-dia.csv");
    expect(readingCsvFileName("Pão & Café: Sábado")).toBe("pao-cafe-sabado.csv");
    expect(readingCsvFileName("!!!")).toBe("quadro.csv");
  });
});

describe("o formato do eixo", () => {
  it("dinheiro no eixo é compacto, sem quebrar em duas linhas", () => {
    // O espaço do Intl é o inseparável (U+00A0); a régua lê o texto, não o byte.
    const plain = (text: string) => text.replace(/\u00a0/g, " ");
    expect(plain(readingMoneyAxisFormat(15000))).toBe("R$ 15 mil");
    expect(plain(readingMoneyAxisFormat(1234567))).toBe("R$ 1,2 mi");
    expect(plain(readingMoneyAxisFormat(500))).toBe("R$ 500");
    expect(plain(readingMoneyFormat(15000))).toBe("R$ 15.000,00");
  });

  it("sem axis-format, o dinheiro do kit vira o compacto e o resto vale para os dois", () => {
    const percent = (value: number) => `${value}%`;
    const axisMoney = (value: number) => `eixo ${value}`;
    expect(readingAxisFormat(readingMoneyFormat)).toBe(readingMoneyAxisFormat);
    expect(readingAxisFormat(percent)).toBe(percent);
    expect(readingAxisFormat(readingMoneyFormat, axisMoney)).toBe(axisMoney);
  });
});

describe("a área com buraco", () => {
  const gaps = (values: Array<number | null>): ReadingChartPoint[] =>
    values.map((value, index) => ({ label: `${index}`, values: { v: value } }));

  it("um trecho por sequência com dado; ponto isolado não vira área", () => {
    expect(readingRuns(gaps([1, 2, null, 4, 5, 6, null, 8]), "v")).toEqual([
      { start: 0, end: 1 },
      { start: 3, end: 5 },
    ]);
    expect(readingRuns(gaps([1, 2, 3]), "v")).toEqual([{ start: 0, end: 2 }]);
    expect(readingRuns(gaps([null, null]), "v")).toEqual([]);
  });

  it("fora do trecho, o índice repete a ponta mais perto (ponto coincidente, sem corcova)", () => {
    const run = { start: 3, end: 5 };
    expect([0, 2, 3, 4, 5, 6, 9].map((index) => readingRunIndex(run, index))).toEqual([3, 3, 3, 4, 5, 5, 5]);
  });
});
