// A agenda com cobertura na lista de Encomendas (WP-G10): o que o cabeçalho de cada dia
// diz e o que o detalhe do dia mostra por produto. Puro, testado em
// `tests/preorderCoverage.test.ts`.
//
// A soma é do servidor (`projections/preorder_coverage.py`): por dia e por produto, o
// prometido nas encomendas aceitas ao lado do que os lotes daquela data somam. As frases
// também são dele ("Faltam 6 Baguete de tradição.", "Sem lote para Ciabatta"): aqui
// ninguém soma, compara nem reescreve. A tela só decide três coisas:
//
//   1. o TOM do dia: quem falta ou não tem lote pede alguém, e pede mais quando o dia
//      está em cima; dia coberto e dia que não depende de lote ficam quietos;
//   2. o que a linha do produto repete: a conta por extenso ("As encomendas somam 16x e
//      os lotes, 10x.") some quando os dois números já estão lado a lado;
//   3. onde mora "Abrir a Produção": no cabeçalho do dia que pede alguém, dentro do
//      detalhe nos demais.
import type {
  OrderCardProjection,
  PreorderCoverageDayProjection,
  PreorderCoverageProductProjection,
  PreorderCoverageProjection,
} from "~/types/orders";

/** Quem pede alguém agora, quem pede alguém com folga, quem não pede ninguém. */
export type CoverageTone = "urgent" | "attention" | "quiet";

/** Até quantos dias de distância a falta é de agora: hoje e amanhã. Depois disso ainda
 *  dá tempo de planejar mais um lote, e o tom é o de aviso. */
export const URGENT_WITHIN_DAYS = 1;

/** O dia (e o produto) que pede alguém: há lote que não cobre, ou não há lote. */
const NEEDS_SOMEONE = new Set(["short", "no_batch"]);
/** Estados em que `detail` é a conta dos dois números que a linha já mostra. */
const ACCOUNT_IN_FIGURES = new Set(["short", "covered"]);

export const PROMISED_CAPTION = "Prometido";
export const PLANNED_CAPTION = "Planejado";
export const COVERAGE_READ_FAILED =
  "Não foi possível ler se a produção cobre as encomendas.";
export const COVERAGE_RETRY_LABEL = "Tentar de novo";

export interface ProductCoverageView {
  sku: string;
  name: string;
  state: string;
  /** "16x", "0,35 kg": o que as encomendas do dia somam. */
  promised: string;
  /** "10x": o que os lotes da data somam. Vazio em quem não depende de lote (feito na
   *  hora, revenda): ali não há número para pôr ao lado. */
  planned: string;
  /** "Faltam 6 Baguete de tradição" · "Sem lote para Ciabatta". Vazio nos demais. */
  label: string;
  /** O porquê ("Nenhum lote planejado para o dia.", "Feito na hora: não depende de
   *  lote."). Vazio quando seria só a conta dos dois números ao lado. */
  detail: string;
  /** O tom do dia em quem pede alguém; quieto nos demais, sem cor de falta. */
  tone: CoverageTone;
}

export interface DayCoverageView {
  date: string;
  /** A frase pronta do servidor: "Faltam 6 Baguete de tradição." */
  headline: string;
  tone: CoverageTone;
  /** Falta ou não tem lote: o cabeçalho ganha cor e o atalho da Produção. */
  needsSomeone: boolean;
  products: ProductCoverageView[];
  /** "Abrir a Produção" naquele dia. `null` sem endereço (a Produção não está
   *  configurada, ou quem lê não a opera). */
  production: { href: string; label: string } | null;
}

type DaySource = Pick<
  PreorderCoverageDayProjection,
  | "date"
  | "days_ahead"
  | "state"
  | "headline"
  | "products"
  | "production_url"
  | "production_label"
>;
type ProductSource = Pick<
  PreorderCoverageProductProjection,
  | "sku"
  | "name"
  | "state"
  | "promised_display"
  | "planned_display"
  | "label"
  | "detail"
>;

/** O tom do dia: só a falta e o dia sem lote ganham cor, e a distância decide qual. */
export function coverageTone(
  day: Pick<PreorderCoverageDayProjection, "state" | "days_ahead">,
): CoverageTone {
  if (!NEEDS_SOMEONE.has(day.state)) return "quiet";
  return day.days_ahead <= URGENT_WITHIN_DAYS ? "urgent" : "attention";
}

function productView(
  product: ProductSource,
  dayTone: CoverageTone,
): ProductCoverageView {
  return {
    sku: product.sku,
    name: product.name,
    state: product.state,
    promised: product.promised_display,
    planned: product.planned_display,
    label: product.label,
    detail: ACCOUNT_IN_FIGURES.has(product.state) ? "" : product.detail,
    tone: NEEDS_SOMEONE.has(product.state) ? dayTone : "quiet",
  };
}

/** O que o cabeçalho e o detalhe de um dia mostram. A ordem dos produtos é a do
 *  servidor: primeiro quem pede alguém. */
export function dayCoverage(day: DaySource): DayCoverageView {
  const tone = coverageTone(day);
  const href = String(day.production_url ?? "").trim();
  const label = String(day.production_label ?? "").trim();
  return {
    date: day.date,
    headline: String(day.headline ?? "").trim(),
    tone,
    needsSomeone: tone !== "quiet",
    products: (day.products ?? []).map((product) => productView(product, tone)),
    production: href && label ? { href, label } : null,
  };
}

/** A cobertura de cada dia pela data do grupo da lista (`commitment_date`). Sem
 *  leitura, vazio: o cabeçalho do dia só não mostra a cobertura. */
export function coverageByDate(
  coverage: Pick<PreorderCoverageProjection, "days"> | null | undefined,
): Record<string, DayCoverageView> {
  const byDate: Record<string, DayCoverageView> = {};
  for (const day of coverage?.days ?? []) byDate[day.date] = dayCoverage(day);
  return byDate;
}

/**
 * O conjunto de encomendas da lista, numa linha: muda quando uma encomenda entra, sai
 * ou muda de dia. É o gatilho da releitura da cobertura; a ordem da fila não conta.
 * Vazio sem encomenda: aí não há cabeçalho de dia, e nada é lido.
 */
export function coverageSignature(
  cards: Pick<OrderCardProjection, "ref" | "commitment_date">[],
): string {
  return cards
    .map((card) => `${card.ref}@${card.commitment_date || ""}`)
    .sort()
    .join("|");
}

/** O nome do gesto que abre e fecha o detalhe do dia. */
export function coverageToggleLabel(open: boolean): string {
  return open ? "Recolher" : "Ver por produto";
}

/**
 * Onde "Abrir a Produção" aparece: no cabeçalho do dia que pede alguém (a um toque de
 * quem leu a falta) e no fim do detalhe nos demais (o dia coberto não precisa do atalho
 * à vista). Nunca nos dois ao mesmo tempo.
 */
export function productionLinkPlace(
  day: Pick<DayCoverageView, "production" | "needsSomeone">,
): "header" | "detail" | null {
  if (!day.production) return null;
  return day.needsSomeone ? "header" : "detail";
}
