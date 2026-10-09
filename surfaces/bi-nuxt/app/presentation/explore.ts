// Presentation pura do Explorar (PR-B6 do WP-BI-CANON-LAUDO): os itens das listas do
// construtor, a legenda do resultado e o CSV do quadro. Sem Vue; testada em
// `tests/explore.test.ts`.
import type {
  ReadingCsv,
  ReadingChartPoint,
} from "../../../operator-kit/app/presentation/readingChart";
import { EXPLORE_DIMENSION_LABELS, csvMoney, shortDate, type BucketSpan } from "./bi";

/**
 * O valor de "nenhum" nas listas. O item de um Select do Nuxt UI (reka-ui) não aceita
 * valor vazio, e o corte guarda "" para "sem cenário" e "sem cruzamento": a página
 * traduz na porta, com estas duas constantes.
 */
export const FREE_SCENARIO = "free";
export const NO_CROSS = "none";

export interface ScenarioViewLike {
  id: number;
  name: string;
  pinned: boolean;
}

export interface ScenarioExampleLike {
  name: string;
}

export interface ScenarioMenuItem {
  label: string;
  value?: string;
  type?: "label";
  icon?: string;
}

/**
 * Os itens do seletor de Cenário, em grupos: o corte livre, "Meus cenários" (só se
 * houver) e "Exemplos". Favorito leva a estrela como ícone do item, e não no texto.
 */
export function scenarioMenuItems(
  views: readonly ScenarioViewLike[],
  examples: readonly ScenarioExampleLike[],
): ScenarioMenuItem[][] {
  const groups: ScenarioMenuItem[][] = [[{ label: "Nenhum (corte livre)", value: FREE_SCENARIO }]];
  if (views.length) {
    groups.push([
      { type: "label", label: "Meus cenários" },
      ...views.map((view) => ({
        label: view.name,
        value: `view:${view.id}`,
        ...(view.pinned ? { icon: "i-lucide-star" } : {}),
      })),
    ]);
  }
  if (examples.length) {
    groups.push([
      { type: "label", label: "Exemplos" },
      ...examples.map((example) => ({ label: example.name, value: `example:${example.name}` })),
    ]);
  }
  return groups;
}

/** As dimensões em itens de lista, com o nome humano (o servidor manda a chave). */
export function dimensionItems(dimensions: readonly string[]): { label: string; value: string }[] {
  return dimensions.map((key) => ({ label: EXPLORE_DIMENSION_LABELS[key] ?? key, value: key }));
}

/** O Cruzamento: "Sem cruzamento" primeiro, depois as dimensões que sobram. */
export function crossItems(dimensions: readonly string[]): { label: string; value: string }[] {
  return [{ label: "Sem cruzamento", value: NO_CROSS }, ...dimensionItems(dimensions)];
}

export interface ExploreReportLike {
  unit: string;
  metric_label: string;
  dimension: string;
  dimension_label: string;
  dimension2: string;
  dimension2_label: string;
  date_from: string;
  date_to: string;
  truncated: number;
  rows: readonly { key: string; label: string; key2: string; label2: string; value: number }[];
}

/** "11/09 a 08/10" e, quando o servidor cortou, quantas linhas ficaram fora. */
export function exploreResultDescription(report: ExploreReportLike): string {
  const window = `${shortDate(report.date_from)} a ${shortDate(report.date_to)}`;
  if (!report.truncated) return window;
  return `${window}. Mostrando as ${report.rows.length} maiores; ${report.truncated} linhas ficaram fora.`;
}

/** O eixo da série no tempo diz o grão do balde: dia, semana ou mês. */
export function exploreAxisLabel(span: BucketSpan): string {
  if (span === "day") return "Dia";
  return span === "week" ? "Semana" : "Mês";
}

/**
 * O valor no CSV. Dinheiro chega em centavos (`_q`) e sai em reais com duas casas
 * ("1500,50", como o `readingChartCsv(..., { money: true })` do kit), porque quem abre o
 * CSV faz conta com ele e não sabe da convenção dos centavos.
 */
export function exploreCsvValue(unit: string, value: number): number | string {
  return unit === "q" ? csvMoney(Math.round(value)) : value;
}

/** O cabeçalho da coluna do valor: a métrica e, no dinheiro, a moeda. */
export function exploreValueHeader(report: Pick<ExploreReportLike, "unit" | "metric_label">): string {
  return report.unit === "q" ? `${report.metric_label} (R$)` : report.metric_label;
}

/**
 * O CSV do quadro: os números que a tela mostra. Na série no tempo, os baldes do
 * gráfico (os mesmos pontos); no ranking e no cruzamento, as linhas do servidor.
 */
export function exploreCsv(
  report: ExploreReportLike,
  timePoints?: { axisLabel: string; points: readonly ReadingChartPoint[] },
): ReadingCsv {
  const valueHeader = exploreValueHeader(report);
  if (timePoints) {
    return {
      header: [timePoints.axisLabel, valueHeader],
      rows: timePoints.points.map((point) => {
        const value = point.values.value;
        return [point.label, typeof value === "number" ? exploreCsvValue(report.unit, value) : ""];
      }),
    };
  }
  if (report.dimension2) {
    return {
      header: [report.dimension_label, report.dimension2_label, valueHeader],
      rows: report.rows.map((row) => [row.label, row.label2, exploreCsvValue(report.unit, row.value)]),
    };
  }
  return {
    header: [report.dimension_label, valueHeader],
    rows: report.rows.map((row) => [row.label, exploreCsvValue(report.unit, row.value)]),
  };
}
