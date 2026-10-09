// Gráfico de leitura e quadro de leitura (PR-K1 do WP-BI-CANON-LAUDO): a parte pura.
//
// O componente (`OperatorReadingChart`) só desenha o que sai daqui. A frase que o
// ponto em leitura diz, a legenda, as linhas da tabela equivalente, o CSV do quadro
// e a navegação por teclado são funções sem Vue, testadas em `tests/readingChart.test.ts`.

/** As cinco formas de leitura, e só cinco. */
export type ReadingChartKind =
  /** Barras, uma ou mais séries lado a lado. */
  | "bars"
  /**
   * Barras empilhadas: as séries são PARTES de um todo e somam numa barra só ("vendeu"
   * mais "sobrou" é o que a casa fez). Os segmentos se distinguem também pelo
   * preenchimento (`fill`), não só pela cor.
   */
  | "stacked"
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

/**
 * O preenchimento da barra, a segunda codificação além da cor: `solid` (cheio, o
 * padrão), `tint` (a mesma cor clara, a parte que completa o todo) e `hatch` (listrado,
 * a estimativa). Os tons do tema são quentes e próximos entre si (latão, âmbar,
 * tijolo); a cor sozinha não separa dois segmentos vizinhos para quem não distingue
 * vermelho de verde.
 */
export type ReadingFill = "solid" | "tint" | "hatch";

export interface ReadingChartSeries {
  key: string;
  /** O nome da grandeza, como o leitor a diz ("Pedidos confirmados"). */
  label: string;
  tone?: ReadingTone;
  /** Só nas barras (`bars`, `stacked`). Default: `solid`. */
  fill?: ReadingFill;
}

/** A cor de uma série com o preenchimento dela: o `tint` é o tom a 30% sobre o fundo. */
export function readingFillColor(tone: ReadingTone, fill: ReadingFill = "solid"): string {
  const color = READING_TONE_COLOR[tone];
  return fill === "tint" ? `color-mix(in srgb, ${color} 30%, transparent)` : color;
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

const MONEY = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const MONEY_AXIS = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  // Sem o mínimo explícito, o ICU do Node 22 (o da CI) herda os 2 decimais da moeda e
  // escreve "R$ 15,0 mil"; o do Node 26 escreve "R$ 15 mil". Zero fixa o mesmo texto.
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
});

/**
 * Dinheiro por extenso, em reais: "R$ 15.000,00". É o que a frase do ponto e a tabela
 * dizem. O gráfico recebe reais; quem tem centavos (`_q`) divide por 100 ao montar os
 * pontos.
 */
export const readingMoneyFormat: ReadingFormat = (value) => MONEY.format(value);

/**
 * Dinheiro no eixo, compacto: "R$ 15 mil", "R$ 1,2 mi". O eixo é régua, não leitura:
 * o valor exato está na frase do ponto e na tabela. Cheio, o rótulo quebrava no
 * celular ("R$ 15." numa linha, "000,00" na outra).
 */
export const readingMoneyAxisFormat: ReadingFormat = (value) => MONEY_AXIS.format(value);

/**
 * O formato do eixo quando a tela não diz um (`axis-format`): dinheiro do kit vira o
 * compacto; qualquer outro formato vale para o eixo também.
 */
export function readingAxisFormat(format: ReadingFormat, axisFormat?: ReadingFormat): ReadingFormat {
  if (axisFormat) return axisFormat;
  return format === readingMoneyFormat ? readingMoneyAxisFormat : format;
}

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
  /** O preenchimento do bloco (`stacked` e `bars`); `solid` nas outras formas. */
  fill: ReadingFill;
}

export function readingLegend(
  kind: ReadingChartKind,
  series: ReadingChartSeries[],
  diverging?: ReadingDivergingLabels,
): ReadingLegendItem[] {
  if (kind === "diverging") {
    if (!diverging) return [];
    return [
      { label: diverging.positive, tone: diverging.positiveTone ?? "primary", dashed: false, fill: "solid" },
      { label: diverging.negative, tone: diverging.negativeTone ?? "error", dashed: false, fill: "solid" },
    ];
  }
  return drawnSeries(kind, series).map((item, index) => ({
    label: item.label,
    tone: seriesTone(item, index),
    dashed: kind === "comparison" && index === 1,
    fill: kind === "bars" || kind === "stacked" ? (item.fill ?? "solid") : "solid",
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

export interface ReadingChartCsvOptions {
  /**
   * Os valores são dinheiro, em reais: a célula sai com duas casas ("1500,50") e o
   * cabeçalho ganha a unidade ("Faturamento (R$)"). Sem o símbolo na célula, para a
   * planilha somar.
   */
  money?: boolean;
}

const CSV_NUMBER = new Intl.NumberFormat("pt-BR", { useGrouping: false, maximumFractionDigits: 20 });
const CSV_MONEY = new Intl.NumberFormat("pt-BR", {
  useGrouping: false,
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * Número para a planilha em português: vírgula decimal e nenhum separador de milhar
 * ("1234,5"). O ponto ("1.2") a planilha em português lê como milhar ou como texto.
 */
export function readingCsvNumber(value: number): string {
  return CSV_NUMBER.format(value);
}

/** Reais para a planilha: duas casas, vírgula decimal, sem milhar e sem "R$" ("1500,50"). */
export function readingCsvMoney(value: number): string {
  return CSV_MONEY.format(value);
}

/**
 * O CSV de um gráfico: o rótulo do eixo e os números de cada série. O número, e não
 * a frase formatada, porque quem abre o CSV vai fazer conta com ele; escrito como a
 * planilha em português o lê (vírgula decimal, sem milhar).
 */
export function readingChartCsv(
  axisLabel: string,
  series: ReadingChartSeries[],
  points: ReadingChartPoint[],
  options: ReadingChartCsvOptions = {},
): ReadingCsv {
  const unit = options.money ? " (R$)" : "";
  return {
    header: [axisLabel, ...series.map((item) => `${item.label}${unit}`)],
    rows: points.map((point) => [
      point.label,
      ...series.map((item) => {
        const value = pointValue(point, item.key);
        if (value === null) return "";
        return options.money ? readingCsvMoney(value) : value;
      }),
    ]),
  };
}

function csvCell(value: ReadingCsvCell): string {
  const text = typeof value === "number" ? readingCsvNumber(value) : value;
  return /[";\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/**
 * O texto do arquivo. Ponto e vírgula, porque a planilha em português lê a vírgula
 * como decimal (e é com vírgula que os números saem); a marca de ordem de bytes abre
 * o UTF-8 com acento certo.
 */
export function readingCsvText(csv: ReadingCsv): string {
  const lines = [csv.header, ...csv.rows].map((row) => row.map(csvCell).join(";"));
  return `\uFEFF${lines.join("\n")}`;
}

/** Um trecho contínuo de uma série: do índice `start` ao `end`, todos com valor. */
export interface ReadingRun {
  start: number;
  end: number;
}

/**
 * Os trechos com dado de uma série, na ordem. A linha quebra no buraco sozinha; a
 * área não (o Unovis lê o ponto ausente como zero e desce até a base). Por isso a
 * área é desenhada trecho a trecho, e um ponto isolado não vira área.
 */
export function readingRuns(points: ReadingChartPoint[], key: string): ReadingRun[] {
  const runs: ReadingRun[] = [];
  let start: number | null = null;
  points.forEach((point, index) => {
    const present = pointValue(point, key) !== null;
    if (present && start === null) start = index;
    if (!present && start !== null) {
      runs.push({ start, end: index - 1 });
      start = null;
    }
  });
  if (start !== null) runs.push({ start, end: points.length - 1 });
  return runs.filter((run) => run.end > run.start);
}

/**
 * Onde um índice cai num trecho: dentro, ele mesmo; fora, a ponta mais perto. A área
 * de um trecho leva todos os pontos (o Unovis dá o mesmo `data` a todo componente),
 * e os de fora repetem a ponta: ponto coincidente não desenha nada.
 */
export function readingRunIndex(run: ReadingRun, index: number): number {
  return Math.min(run.end, Math.max(run.start, index));
}

/**
 * O domínio dos valores: sempre contém o zero (barra que não parte do zero mente a
 * proporção), e o divergente fica com os dois lados. No empilhado, a barra é a soma
 * dos segmentos (positivos para cima, negativos para baixo). Sem nenhum valor, [0, 1],
 * para o eixo não colapsar.
 */
export function readingYDomain(
  kind: ReadingChartKind,
  series: ReadingChartSeries[],
  points: ReadingChartPoint[],
): [number, number] {
  let min = 0;
  let max = 0;
  if (kind === "stacked") {
    for (const point of points) {
      let up = 0;
      let down = 0;
      for (const item of series) {
        const value = pointValue(point, item.key) ?? 0;
        if (value > 0) up += value;
        else down += value;
      }
      max = Math.max(max, up);
      min = Math.min(min, down);
    }
    return min === max ? [0, 1] : [min, max];
  }
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

/**
 * A altura do gráfico deitado (`horizontal`): uma faixa por ponto, para cada rótulo
 * caber inteiro (o eixo das categorias mostra TODOS, não salta como o das datas), mais
 * a régua dos valores embaixo.
 */
export const READING_ROW_HEIGHT = 40;
export const READING_AXIS_HEIGHT = 32;

export function readingHorizontalHeight(count: number): number {
  return Math.max(1, count) * READING_ROW_HEIGHT + READING_AXIS_HEIGHT;
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
