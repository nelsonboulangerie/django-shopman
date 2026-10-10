// Presentation: como as linhas da grade se arrumam na tela (V4-PROD, prévia v4
// `plano-porque4.html`, pinos 7 e 8). Puro: recebe as linhas do quadro e devolve os
// grupos; quem desenha é a grade.
//
// Planejamento:
//   - EM FOCO: o que ainda não tem plano e pede um olhar (um sinal na sugestão, pedidos
//     comprometidos, ou nenhuma sugestão para seguir);
//   - SEM RESSALVA: o que ainda não tem plano, tem sugestão e nada a notar. Vira um
//     conjunto ("+16 produtos sem ressalva"), com "um sim para todos" ou "ver um a um".
//     Só agrupa a partir de `CLEAN_GROUP_MIN`: "+1 produto" seria uma linha a mais, não
//     uma a menos;
//   - PLANEJADOS: o que já tem plano (ou já foi assumido pela produção) vira estado,
//     no fim, com as correções no menu da linha.
//   - SEM SUGESTÃO: o que não tem plano, nem sugestão para o dia, nem encomenda (bases,
//     recheios, o que não vende neste dia). Também vira conjunto, que se abre para
//     planejar à mão: não esconde nada, só tira do caminho.
// Recortes: Todos (os três grupos), A planejar (tudo sem plano, um a um), Com ressalva
// (só o que tem sinal) e Planejados.
//
// Abertura: A confirmar (há lote planejado esperando o previsto) e Abertos (o previsto
// já foi dito e o lote segue para o Fechamento).
import type { ProductionMatrixRowProjection } from "~/types/production";
import { rowCommittedUnits } from "~/presentation/production";
import { suggestionSignal } from "~/presentation/planningReason";

export type PlanFilter = "all" | "todo" | "flagged" | "done";
export type OpenFilter = "all" | "pending" | "opened";

/** A partir de quantas linhas "sem ressalva" a tela as junta num conjunto. */
export const CLEAN_GROUP_MIN = 4;

function qty(value: string | undefined | null): number {
  return parseFloat((value ?? "0").replace(",", ".")) || 0;
}

/** A linha já tem plano no dia (ou a produção já assumiu parte dele). */
export function isPlannedRow(row: ProductionMatrixRowProjection): boolean {
  return (
    row.planned_qty !== "0" ||
    row.started_qty !== "0" ||
    row.finished_qty !== "0"
  );
}

/** Tem algo a notar: o sinal da sugestão ou pedidos que dependem do lote. */
export function rowHasCaveat(row: ProductionMatrixRowProjection): boolean {
  return Boolean(suggestionSignal(row.suggestion)) || rowCommittedUnits(row) > 0;
}

/** Sem plano, com sugestão acima de zero e nada a notar: pode ir no conjunto. */
export function isCleanRow(row: ProductionMatrixRowProjection): boolean {
  return (
    !isPlannedRow(row) &&
    row.recipe_pk != null &&
    qty(row.suggestion?.quantity) > 0 &&
    !rowHasCaveat(row)
  );
}

/** Sem plano, sem sugestão acima de zero e sem encomenda: planeja-se à mão, se precisar. */
export function isManualRow(row: ProductionMatrixRowProjection): boolean {
  return (
    !isPlannedRow(row) &&
    qty(row.suggestion?.quantity) <= 0 &&
    !rowHasCaveat(row)
  );
}

export interface PlanRowGroups {
  /** Linhas uma a uma (stepper e "Planejar N"). */
  focus: ProductionMatrixRowProjection[];
  /** O conjunto "sem ressalva" (vazio quando não agrupa). */
  clean: ProductionMatrixRowProjection[];
  /** O conjunto "sem sugestão" (vazio quando não agrupa). */
  manual: ProductionMatrixRowProjection[];
  /** O que já tem plano, no fim. */
  planned: ProductionMatrixRowProjection[];
  counts: Record<PlanFilter, number>;
}

export function planRowGroups(
  rows: ProductionMatrixRowProjection[],
  filter: PlanFilter,
  options: {
    expandClean?: boolean;
    expandManual?: boolean;
    searching?: boolean;
  } = {},
): PlanRowGroups {
  const planned = rows.filter(isPlannedRow);
  const todo = rows.filter((row) => !isPlannedRow(row));
  const flagged = todo.filter((row) => Boolean(suggestionSignal(row.suggestion)));
  const counts: Record<PlanFilter, number> = {
    all: rows.length,
    todo: todo.length,
    flagged: flagged.length,
    done: planned.length,
  };
  if (filter === "done") return { focus: [], clean: [], manual: [], planned, counts };
  if (filter === "flagged")
    return { focus: flagged, clean: [], manual: [], planned: [], counts };
  if (filter === "todo")
    return { focus: todo, clean: [], manual: [], planned: [], counts };

  const collapsible = !options.searching;
  const cleanRows = todo.filter(isCleanRow);
  const manualRows = todo.filter(isManualRow);
  const clean =
    collapsible && !options.expandClean && cleanRows.length >= CLEAN_GROUP_MIN
      ? cleanRows
      : [];
  const manual =
    collapsible && !options.expandManual && manualRows.length >= CLEAN_GROUP_MIN
      ? manualRows
      : [];
  return {
    focus: todo.filter((row) => !clean.includes(row) && !manual.includes(row)),
    clean,
    manual,
    planned,
    counts,
  };
}

/** "Pain de Campagne 34, Kuro Pan 12, Baguete 30, Focaccia 10 e mais 12". */
export function cleanPreview(
  rows: ProductionMatrixRowProjection[],
  label: (row: ProductionMatrixRowProjection) => string,
  shown = 4,
): string {
  const head = rows
    .slice(0, shown)
    .map((row) => `${label(row)} ${row.suggestion?.quantity ?? ""}`.trim());
  const rest = rows.length - head.length;
  return rest > 0 ? `${head.join(", ")} e mais ${rest}` : head.join(", ");
}

// ── Abertura ───────────────────────────────────────────────────────────────

export function openRowPending(row: ProductionMatrixRowProjection): boolean {
  return row.planned_orders.length > 0;
}

export function openRowGroups(
  rows: ProductionMatrixRowProjection[],
  filter: OpenFilter,
): { rows: ProductionMatrixRowProjection[]; counts: Record<OpenFilter, number> } {
  const pending = rows.filter(openRowPending);
  const opened = rows.filter((row) => !openRowPending(row));
  const counts: Record<OpenFilter, number> = {
    all: rows.length,
    pending: pending.length,
    opened: opened.length,
  };
  if (filter === "pending") return { rows: pending, counts };
  if (filter === "opened") return { rows: opened, counts };
  return { rows, counts };
}
