// Gráfico de leitura e quadro de leitura (PR-K1 do WP-BI-CANON-LAUDO): a parte pura.
//
// O componente (`OperatorReadingChart`) só desenha o que sai daqui. A frase que o
// ponto em leitura diz, a legenda, as linhas da tabela equivalente, o CSV do quadro
// e a navegação por teclado são funções sem Vue, testadas em `tests/readingChart.test.ts`.

/** As quatro formas de leitura, e só quatro. */
export type ReadingChartKind =
  /** Barras, uma ou mais séries lado a lado. */
  | "bars"
  /** Barras da primeira série e o traço tracejado da segunda (o período de comparação). */
  | "comparison"
  /** Uma série com sinal: acima de zero numa cor, abaixo noutra (sobrou ou faltou). */
  | "diverging"
  /** Linha com área da primeira série; as demais, só linha. */
  | "line";

/** Cores do tema, nunca hexadecimal: o gráfico segue o claro e o escuro. */
export type ReadingTone = "primary" | "neutral" | "success" | "warning" | "error" | "info";

export const READING_TONE_COLOR: Record<ReadingTone, string> = {
  primary: "var(--ui-primary)",
  neutral: "var(--ui-text-muted)",
  success: "var(--ui-success)",
  warning: "var(--ui-warning)",
  error: "var(--ui-error)",
  info: "var(--ui-info)",
};

export interface ReadingChartSeries {
  key: string;
  /** O nome da grandeza, como o leitor a diz ("Pedidos confirmados"). */
  label: string;
  tone?: ReadingTone;
}

export interface ReadingChartPoint {
  /** O rótulo do eixo horizontal ("12h", "Sex 03/10", "Croissant"). */
  label: string;
  /** Valor por chave de série. `null` é ponto sem dado, nunca zero. */
  values: Record<string, number | null | undefined>;
}

/** Os nomes dos dois lados do divergente. O zero tem nome próprio também. */
export interface ReadingDivergingLabels {
  positive: string;
  negative: string;
  /** Default: "Sem diferença". */
  zero?: string;
  positiveTone?: ReadingTone;
  negativeTone?: ReadingTone;
}

export type ReadingFormat = (value: number) => string;

const NUMBER = new Intl.NumberFormat("pt-BR");
export const defaultReadingFormat: ReadingFormat = (value) => NUMBER.format(value);

export const MISSING_VALUE = "sem dado";
const DEFAULT_ZERO = "Sem diferença";

export function seriesTone(series: ReadingChartSeries, index: number): ReadingTone {
  return series.tone ?? (index === 0 ? "primary" : "neutral");
}

export function pointValue(point: ReadingChartPoint, key: string): number | null {
  const value = point.values[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** O valor de um lado do divergente, dito com a palavra do lado e sem sinal. */
export function divergingText(
  value: number | null,
  labels: ReadingDivergingLabels,
  format: ReadingFormat,
): string {
  if (value === null) return MISSING_VALUE;
  if (value === 0) return labels.zero ?? DEFAULT_ZERO;
  return `${value > 0 ? labels.positive : labels.negative} ${format(Math.abs(value))}`;
}

/** As séries que a forma desenha. Divergente e comparação usam as primeiras. */
export function drawnSeries(kind: ReadingChartKind, series: ReadingChartSeries[]): ReadingChartSeries[] {
  if (kind === "diverging") return series.slice(0, 1);
  if (kind === "comparison") return series.slice(0, 2);
  return series;
}

/**
 * A frase do ponto em leitura (o "tooltip"): o rótulo do eixo e cada série com o
 * seu valor. É o mesmo texto para o mouse, o toque e o teclado, e é o que o leitor
 * de tela anuncia quando as setas mudam o ponto.
 */
export function readingPointSummary(
  point: ReadingChartPoint,
  kind: ReadingChartKind,
  series: ReadingChartSeries[],
  format: ReadingFormat = defaultReadingFormat,
  diverging?: ReadingDivergingLabels,
): string {
  const drawn = drawnSeries(kind, series);
  if (kind === "diverging" && diverging && drawn[0]) {
    return `${point.label}: ${divergingText(pointValue(point, drawn[0].key), diverging, format)}`;
  }
  const parts = drawn.map((item) => {
    const value = pointValue(point, item.key);
    return `${item.label} ${value === null ? MISSING_VALUE : format(value)}`;
  });
  return `${point.label}: ${parts.join("; ")}`;
}

export interface ReadingLegendItem {
  label: string;
  tone: ReadingTone;
  /** Traço tracejado (a série de comparação), não bloco cheio. */
  dashed: boolean;
}

export function readingLegend(
  kind: ReadingChartKind,
  series: ReadingChartSeries[],
  diverging?: ReadingDivergingLabels,
): ReadingLegendItem[] {
  if (kind === "diverging") {
    if (!diverging) return [];
    return [
      { label: diverging.positive, tone: diverging.positiveTone ?? "primary", dashed: false },
      { label: diverging.negative, tone: diverging.negativeTone ?? "error", dashed: false },
    ];
  }
  return drawnSeries(kind, series).map((item, index) => ({
    label: item.label,
    tone: seriesTone(item, index),
    dashed: kind === "comparison" && index === 1,
  }));
}

/**
 * Quais pontos ganham rótulo no eixo. Trinta dias não cabem lado a lado num
 * celular; o eixo mostra no máximo `max`, sempre o primeiro e o último, a passos
 * iguais. O ponto em leitura diz o rótulo dos demais.
 */
export function readingTickIndices(count: number, max = 6): number[] {
  if (count <= 0) return [];
  if (count <= max) return Array.from({ length: count }, (_, index) => index);
  const step = Math.ceil((count - 1) / (max - 1));
  const ticks: number[] = [];
  for (let index = 0; index < count - 1; index += step) ticks.push(index);
  const last = count - 1;
  // O último sempre aparece; se o anterior estiver colado nele, sai o anterior.
  if (ticks.length && last - ticks[ticks.length - 1]! < step / 2) ticks.pop();
  ticks.push(last);
  return ticks;
}

/**
 * Teclado no gráfico: setas andam um ponto, Home e End vão às pontas, Escape
 * solta a leitura. `undefined` é tecla que o gráfico não usa (o navegador segue
 * com ela); `null` é "nenhum ponto em leitura".
 */
export function nextReadingIndex(
  current: number | null,
  key: string,
  count: number,
): number | null | undefined {
  if (count <= 0) return undefined;
  const last = count - 1;
  switch (key) {
    case "ArrowRight":
    case "ArrowDown":
      return current === null ? 0 : Math.min(last, current + 1);
    case "ArrowLeft":
    case "ArrowUp":
      return current === null ? last : Math.max(0, current - 1);
    case "Home":
      return 0;
    case "End":
      return last;
    case "Escape":
      return current === null ? undefined : null;
    default:
      return undefined;
  }
}

export interface ReadingTableRow {
  label: string;
  [key: string]: string;
}

/** As linhas da tabela equivalente, já formatadas como o gráfico as diz. */
export function readingTableRows(
  kind: ReadingChartKind,
  series: ReadingChartSeries[],
  points: ReadingChartPoint[],
  format: ReadingFormat = defaultReadingFormat,
  diverging?: ReadingDivergingLabels,
): ReadingTableRow[] {
  const drawn = drawnSeries(kind, series);
  return points.map((point) => {
    const row: ReadingTableRow = { label: point.label };
    for (const item of drawn) {
      const value = pointValue(point, item.key);
      row[item.key] =
        kind === "diverging" && diverging
          ? divergingText(value, diverging, format)
          : value === null
            ? MISSING_VALUE
            : format(value);
    }
    return row;
  });
}

export type ReadingCsvCell = string | number;

export interface ReadingCsv {
  header: string[];
  rows: ReadingCsvCell[][];
}

/**
 * O CSV de um gráfico: o rótulo do eixo e os números crus de cada série. Número
 * cru, e não a frase formatada, porque quem abre o CSV vai fazer conta com ele.
 */
export function readingChartCsv(
  axisLabel: string,
  series: ReadingChartSeries[],
  points: ReadingChartPoint[],
): ReadingCsv {
  return {
    header: [axisLabel, ...series.map((item) => item.label)],
    rows: points.map((point) => [
      point.label,
      ...series.map((item) => pointValue(point, item.key) ?? ""),
    ]),
  };
}

function csvCell(value: ReadingCsvCell): string {
  const text = String(value);
  return /[";\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/**
 * O texto do arquivo. Ponto e vírgula, porque a planilha em português lê a vírgula
 * como decimal; a marca de ordem de bytes abre o UTF-8 com acento certo.
 */
export function readingCsvText(csv: ReadingCsv): string {
  const lines = [csv.header, ...csv.rows].map((row) => row.map(csvCell).join(";"));
  return `\uFEFF${lines.join("\n")}`;
}

/**
 * O domínio vertical: sempre contém o zero (barra que não parte do zero mente a
 * proporção), e o divergente fica com os dois lados. Sem nenhum valor, [0, 1],
 * para o eixo não colapsar.
 */
export function readingYDomain(
  kind: ReadingChartKind,
  series: ReadingChartSeries[],
  points: ReadingChartPoint[],
): [number, number] {
  let min = 0;
  let max = 0;
  for (const item of drawnSeries(kind, series)) {
    for (const point of points) {
      const value = pointValue(point, item.key);
      if (value === null) continue;
      min = Math.min(min, value);
      max = Math.max(max, value);
    }
  }
  if (min === max) return [0, 1];
  return [min, max];
}

/** "Faturamento por dia" vira `faturamento-por-dia.csv`. */
export function readingCsvFileName(title: string): string {
  const base = title
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `${base || "quadro"}.csv`;
}
