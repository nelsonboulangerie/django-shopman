// Portão de qualidade em lote (P19, decisão do dono 03/10): transforms puros
// sobre a projeção do quiosque. A regra de "sem exceção" é do SERVIDOR
// (`quality_exception` no cartão); aqui só se agrupa, soma e escreve.
import type {
  QCDefectProjection,
  QCGradeProjection,
  QCOrderCardProjection,
} from "~/types/production";

export interface QualityGate {
  /** Finalizados, sem revisão e sem exceção: o conjunto de UM ato. */
  clean: QCOrderCardProjection[];
  /** Finalizados, sem revisão, com exceção: um a um. */
  exceptions: QCOrderCardProjection[];
  /** Já revisados (confirmados ou corrigidos). */
  reviewed: QCOrderCardProjection[];
  /** Ainda não finalizados: fora do portão. */
  openCount: number;
}

export function qualityGate(orders: QCOrderCardProjection[]): QualityGate {
  const gate: QualityGate = {
    clean: [],
    exceptions: [],
    reviewed: [],
    openCount: 0,
  };
  for (const order of orders) {
    if (!order.closed) gate.openCount += 1;
    else if (order.quality_reviewed) gate.reviewed.push(order);
    else if (order.quality_exception) gate.exceptions.push(order);
    else gate.clean.push(order);
  }
  return gate;
}

function num(value: string | null | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

// ── Grandezas (UX-P1b) ─────────────────────────────────────────────────────
// Um lote conta na unidade do que produz (`output_unit`, do servidor): pão em
// peças, massa e recheio em gramas. Nunca se soma uma grandeza com outra
// (defeito "grandezas somadas" da copy da casa): cada uma fica no seu grupo.

type Dimension = "count" | "mass" | "volume";

/** Unidade canônica → dimensão e fator para a menor unidade exibida (peça, g, ml). */
const UNIT_FACTORS: Record<string, [Dimension, number]> = {
  "": ["count", 1],
  un: ["count", 1],
  mg: ["mass", 0.001],
  g: ["mass", 1],
  kg: ["mass", 1000],
  ml: ["volume", 1],
  l: ["volume", 1000],
};

function unitInfo(unit: string | null | undefined): [Dimension, number] | null {
  const key = (unit ?? "").trim();
  return UNIT_FACTORS[key] ?? UNIT_FACTORS[key.toLowerCase()] ?? null;
}

/** Número em pt-BR: vírgula decimal, sem separador de milhar (ponto confunde). */
export function formatQuantityNumber(value: number, maxDecimals = 3): string {
  return new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: maxDecimals,
    useGrouping: false,
  }).format(value);
}

/**
 * Uma quantidade na unidade do lote. Contagem sai sem unidade (o texto em
 * volta diz "peças", "perda", "padrão"); massa em g, ou kg a partir de 1000 g;
 * volume em ml, ou L a partir de 1000 ml. Unidade desconhecida vai escrita.
 */
export function quantityMeasure(
  value: number | string | null | undefined,
  unit: string | null | undefined,
  { largeDecimals = 3 }: { largeDecimals?: number } = {},
): string {
  const quantity = typeof value === "number" ? value : num(value);
  const info = unitInfo(unit);
  if (!info) return `${formatQuantityNumber(quantity)} ${unit}`.trim();
  const [dimension, factor] = info;
  if (dimension === "count") return formatQuantityNumber(quantity);
  const base = quantity * factor;
  const [small, large] = dimension === "mass" ? ["g", "kg"] : ["ml", "L"];
  if (Math.abs(base) >= 1000)
    return `${formatQuantityNumber(base / 1000, largeDecimals)} ${large}`;
  return `${formatQuantityNumber(base, 1)} ${small}`;
}

/** O número do chip de um lote: "21 peças", "1,8 kg". */
export function lotQuantityLabel(quantity: number | string, unit: string): string {
  const info = unitInfo(unit);
  if (info && info[0] === "count") {
    const value = typeof quantity === "number" ? quantity : num(quantity);
    return `${formatQuantityNumber(value)} ${value === 1 ? "peça" : "peças"}`;
  }
  return quantityMeasure(quantity, unit);
}

/** O botão do conjunto: o título já diz "16 lotes sem exceção" (KISS, 28/11). */
export function batchConfirmLabel(count: number): string {
  return count === 1 ? "Confirmar o lote" : `Confirmar os ${count}`;
}

/**
 * A fila "Me avise" que a confirmação libera, somada por produto (o mesmo
 * produto em dois lotes conta uma vez). null quando o servidor não conseguiu
 * ler a fila: a tela cala em vez de dizer zero.
 */
export function alertsReleased(
  orders: QCOrderCardProjection[],
): { people: number; products: number } | null {
  const bySku = new Map<string, number>();
  for (const order of orders) {
    if (order.alert_waiting_count === null) return null;
    bySku.set(order.output_sku, order.alert_waiting_count);
  }
  let people = 0;
  let products = 0;
  for (const count of bySku.values()) {
    if (count > 0) {
      people += count;
      products += 1;
    }
  }
  return { people, products };
}

export type ExceptionSegment = {
  kind: "standard" | "discount" | "loss";
  quantity: number;
  label: string;
};

/**
 * A partição de um lote com exceção, em segmentos para a barra e a legenda:
 * padrão, desconto (por grau, com o percentual e o motivo) e perda (com o motivo).
 */
export function exceptionSegments(
  order: QCOrderCardProjection,
  grades: QCGradeProjection[],
  defects: QCDefectProjection[],
): ExceptionSegment[] {
  const defaultRef = grades.find((grade) => grade.is_default)?.ref ?? "";
  const defectLabel = (ref: string) =>
    defects.find((defect) => defect.ref === ref)?.label ?? "";
  const segments: ExceptionSegment[] = [];
  for (const group of order.partition) {
    const quantity = num(group.quantity);
    if (quantity <= 0) continue;
    const reason = group.quality_defect_ref
      ? defectLabel(group.quality_defect_ref)
      : "";
    const quoted = reason ? ` · “${reason}”` : "";
    const amount = quantityMeasure(quantity, order.output_unit);
    if (group.loss) {
      segments.push({ kind: "loss", quantity, label: `${amount} perda${quoted}` });
      continue;
    }
    const grade = grades.find((item) => item.ref === group.quality_grade_ref);
    const isStandard =
      !group.quality_grade_ref || group.quality_grade_ref === defaultRef;
    if (isStandard && !(grade && grade.markdown_percent > 0) && !reason) {
      segments.push({
        kind: "standard",
        quantity,
        label: `${amount} ${grade?.label.toLowerCase() || "padrão"}`,
      });
      continue;
    }
    const markdown =
      grade && grade.markdown_percent > 0 ? ` (−${grade.markdown_percent}%)` : "";
    segments.push({
      kind: "discount",
      quantity,
      label: `${amount} ${grade?.label.toLowerCase() ?? group.quality_grade_ref}${markdown}${quoted}`,
    });
  }
  return segments;
}

/** O selo do cartão de exceção: a exceção maior, com o número. */
export function exceptionBadge(order: QCOrderCardProjection): string {
  const measure = (value: number) => quantityMeasure(value, order.output_unit);
  const loss = num(order.loss_qty);
  const discount = num(order.discounted_qty);
  if (loss > 0 && discount > 0)
    return `Perda ${measure(loss)} · Desconto ${measure(discount)}`;
  if (loss > 0) return `Perda ${measure(loss)}`;
  if (discount > 0) return `Desconto ${measure(discount)}`;
  const counted =
    num(order.full_price_qty) + num(order.discounted_qty) + num(order.loss_qty);
  if (order.started_qty && counted > num(order.started_qty))
    return `Contagem ${measure(counted)} de ${measure(num(order.started_qty))}`;
  return "Classificação";
}

/** A referência para decidir: o que entrou e a perda típica do item. */
export function exceptionReference(order: QCOrderCardProjection): string {
  const anchor = order.started_qty || order.planned_qty;
  const parts = [`Entraram ${quantityMeasure(anchor, order.output_unit)}.`];
  if (order.typical_loss_qty) {
    parts.push(
      `Perda típica de ${order.recipe_name}: ${quantityMeasure(order.typical_loss_qty, order.output_unit)} por lote.`,
    );
  }
  return parts.join(" ");
}

/** A linha de um lote já confirmado: "58 no padrão · 2 de perda". */
export function reviewedSummary(order: QCOrderCardProjection): string {
  const measure = (value: string) => quantityMeasure(value, order.output_unit);
  const bits = [`${measure(order.full_price_qty || "0")} no padrão`];
  if (num(order.discounted_qty) > 0)
    bits.push(`${measure(order.discounted_qty)} com desconto`);
  if (num(order.loss_qty) > 0) bits.push(`${measure(order.loss_qty)} de perda`);
  return bits.join(" · ");
}
