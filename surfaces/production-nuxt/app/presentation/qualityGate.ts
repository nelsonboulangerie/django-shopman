// Portão de qualidade em lote (P19, decisão do dono 03/10): transforms puros
// sobre a projeção do quiosque. A regra de "sem exceção" é do SERVIDOR
// (`quality_exception` no cartão); aqui só se agrupa, soma e escreve.
import type {
  QCDefectProjection,
  QCGradeProjection,
  QCOrderCardProjection,
} from "~/types/production";

export interface QualityGate {
  /** Fechados, sem revisão e sem exceção: o conjunto de UM ato. */
  clean: QCOrderCardProjection[];
  /** Fechados, sem revisão, com exceção: um a um. */
  exceptions: QCOrderCardProjection[];
  /** Já revisados (confirmados ou corrigidos). */
  reviewed: QCOrderCardProjection[];
  /** Ainda não fechados: fora do portão. */
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

/** Peças do conjunto limpo (todas no grau padrão, por definição). */
export function cleanPieces(clean: QCOrderCardProjection[]): number {
  return clean.reduce((total, order) => total + num(order.full_price_qty), 0);
}

/** O rótulo do ato, com o fato escrito: "6 lotes, nenhuma exceção · Confirmar". */
export function batchConfirmLabel(count: number): string {
  return `${plural(count, "lote", "lotes")}, nenhuma exceção · Confirmar`;
}

/** Quem fechou os lotes e a janela de horário ("entre 06:10 e 13:40"). */
export function closersSummary(orders: QCOrderCardProjection[]): {
  names: string;
  window: string;
} {
  const names = [
    ...new Set(orders.map((order) => order.closed_by).filter(Boolean)),
  ];
  const times = orders
    .map((order) => order.closed_at_display)
    .filter(Boolean)
    .sort();
  const first = times[0] ?? "";
  const last = times[times.length - 1] ?? "";
  return {
    names: names.join(" · "),
    window: !first ? "" : first === last ? `às ${first}` : `entre ${first} e ${last}`,
  };
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
    if (group.loss) {
      segments.push({ kind: "loss", quantity, label: `${quantity} perda${quoted}` });
      continue;
    }
    const grade = grades.find((item) => item.ref === group.quality_grade_ref);
    const isStandard =
      !group.quality_grade_ref || group.quality_grade_ref === defaultRef;
    if (isStandard && !(grade && grade.markdown_percent > 0) && !reason) {
      segments.push({
        kind: "standard",
        quantity,
        label: `${quantity} ${grade?.label.toLowerCase() || "padrão"}`,
      });
      continue;
    }
    const markdown =
      grade && grade.markdown_percent > 0 ? ` (−${grade.markdown_percent}%)` : "";
    segments.push({
      kind: "discount",
      quantity,
      label: `${quantity} ${grade?.label.toLowerCase() ?? group.quality_grade_ref}${markdown}${quoted}`,
    });
  }
  return segments;
}

/** O selo do cartão de exceção: a exceção maior, com o número. */
export function exceptionBadge(order: QCOrderCardProjection): string {
  const loss = num(order.loss_qty);
  const discount = num(order.discounted_qty);
  if (loss > 0 && discount > 0) return `Perda ${loss} · Desconto ${discount}`;
  if (loss > 0) return `Perda ${loss}`;
  if (discount > 0) return `Desconto ${discount}`;
  const counted =
    num(order.full_price_qty) + num(order.discounted_qty) + num(order.loss_qty);
  if (order.started_qty && counted > num(order.started_qty))
    return `Contagem ${counted} de ${num(order.started_qty)}`;
  return "Classificação";
}

/** A referência para decidir: o que entrou e a perda típica do item. */
export function exceptionReference(order: QCOrderCardProjection): string {
  const anchor = order.started_qty || order.planned_qty;
  const parts = [`Entraram ${num(anchor)}.`];
  if (order.typical_loss_qty) {
    parts.push(
      `Perda típica de ${order.recipe_name}: ${order.typical_loss_qty} por lote.`,
    );
  }
  return parts.join(" ");
}
