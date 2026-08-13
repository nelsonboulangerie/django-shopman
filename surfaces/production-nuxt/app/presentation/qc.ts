// QC do fournil — transforms puros sobre a projection do quiosque (ADR-012/014).
// A aritmética da fornada (QC-FORNADA §4): previsto = a preço cheio + com
// desconto + perda, três grupos disjuntos por construção. O modelo é
// SUBTRATIVO, como se conta na boca do forno: a tela nasce com tudo a preço
// cheio e cada exceção é retirada dali. Sem I/O, sem refs — tudo testável.
import type { QCGradeProjection } from "~/types/production";

// ── Estado da tela de fechamento ────────────────────────────────────────────

export interface QcEntryState {
  /** Previsto da ordem; null = fornada fora do plano (nasce sem expectativa). */
  planned: number | null;
  fullQty: number;
  /** O operador já digitou no campo "a preço cheio"? Governa os padrões. */
  fullTouched: boolean;
  /** Grau do grupo a preço cheio (markdown 0: excellent | standard). */
  fullGradeRef: string;
  discountQty: number;
  /** Grau do sublote com desconto ("" = não há sublote). */
  discountGradeRef: string;
  discountDefectRef: string;
  lossDefectRef: string;
}

export function initialState(planned: number | null, defaultGradeRef: string): QcEntryState {
  return {
    planned,
    fullQty: planned ?? 0,
    fullTouched: false,
    fullGradeRef: defaultGradeRef,
    discountQty: 0,
    discountGradeRef: "",
    discountDefectRef: "",
    lossDefectRef: "",
  };
}

// ── A escala ────────────────────────────────────────────────────────────────

export function fullPriceGrades(grades: QCGradeProjection[]): QCGradeProjection[] {
  return grades.filter((g) => g.markdown_percent === 0);
}

export function discountGrades(grades: QCGradeProjection[]): QCGradeProjection[] {
  return grades.filter((g) => g.markdown_percent > 0);
}

export function defaultGradeRef(grades: QCGradeProjection[]): string {
  return grades.find((g) => g.is_default)?.ref ?? fullPriceGrades(grades)[0]?.ref ?? "";
}

/**
 * Faixa de cor da coluna da escala — funcional, não decorativa: empilhada ela
 * vira uma régua contínua que se lê como escala antes de se ler como palavra.
 * Derivada da SEMÂNTICA (rank/markdown), nunca do rótulo editável.
 */
export function gradeBandClass(grade: QCGradeProjection, grades: QCGradeProjection[]): string {
  if (grade.markdown_percent === 0) {
    const topRank = Math.max(...grades.map((g) => g.rank));
    return grade.rank === topRank ? "bg-emerald-500" : "bg-zinc-400";
  }
  const discounted = discountGrades(grades).sort((a, b) => b.rank - a.rank);
  return discounted.findIndex((g) => g.ref === grade.ref) <= 0 ? "bg-amber-500" : "bg-orange-600";
}

// ── A aritmética ────────────────────────────────────────────────────────────

/**
 * O padrão de "quantas assim" ao tocar num grau menor: o que ainda não foi
 * contado (previsto − a preço cheio); se o operador não mexeu em nada, o não
 * contado é zero, e aí o padrão vira a fornada inteira. Um enunciado, dois
 * comportamentos (QC-FORNADA §4).
 */
export function discountDefault(state: QcEntryState): number {
  if (state.planned === null) return 0;
  const notCounted = Math.max(0, state.planned - state.fullQty);
  if (!state.fullTouched && notCounted === 0) return state.planned;
  return notCounted;
}

/**
 * Tocar num grau menor seleciona o sublote e aplica o padrão de "quantas
 * assim". No caso "não mexeu em nada" o padrão é a fornada inteira, e o campo
 * "a preço cheio" cede: os grupos são disjuntos, o mesmo pão não conta duas
 * vezes.
 */
export function applyDiscountGrade(state: QcEntryState, gradeRef: string): QcEntryState {
  const qty = state.discountQty > 0 ? state.discountQty : discountDefault(state);
  const next: QcEntryState = { ...state, discountGradeRef: gradeRef, discountQty: qty };
  if (!state.fullTouched && state.planned !== null && qty === state.planned) {
    next.fullQty = 0;
  }
  return next;
}

/** Perda derivada: o que não saiu do forno. Fora do plano não há previsto, logo não há perda derivável. */
export function lossQty(state: QcEntryState): number {
  if (state.planned === null) return 0;
  return Math.max(0, state.planned - state.fullQty - state.discountQty);
}

export function finishedTotal(state: QcEntryState): number {
  return state.fullQty + state.discountQty;
}

// ── Confirmar sempre ativo: as perguntas que faltam ─────────────────────────

export type QcQuestion = "loss_reason" | "discount_reason";

/**
 * O sheet de motivos não custa toque nenhum: Confirmar fecha a fornada e, se
 * falta um motivo, pergunta — um de cada vez, na ordem visual dos cartões
 * (perda à esquerda, sublote à direita) — e fecha na resposta.
 */
export function pendingQuestions(state: QcEntryState): QcQuestion[] {
  const out: QcQuestion[] = [];
  if (lossQty(state) > 0 && !state.lossDefectRef) out.push("loss_reason");
  if (state.discountQty > 0 && state.discountGradeRef && !state.discountDefectRef) {
    out.push("discount_reason");
  }
  return out;
}

/** A fornada precisa de pelo menos um grupo vendável — tudo-perda é void/waste, não fechamento. */
export function canSubmit(state: QcEntryState): boolean {
  return finishedTotal(state) > 0;
}

// ── O payload da partição (contrato do finish — ADR-017 §4) ─────────────────

export interface QcPartitionGroup {
  quantity: string;
  quality_grade_ref?: string;
  quality_defect_ref?: string;
  loss?: boolean;
}

export function buildPartition(state: QcEntryState): QcPartitionGroup[] {
  const groups: QcPartitionGroup[] = [];
  if (state.fullQty > 0) {
    groups.push({ quantity: String(state.fullQty), quality_grade_ref: state.fullGradeRef });
  }
  if (state.discountQty > 0 && state.discountGradeRef) {
    groups.push({
      quantity: String(state.discountQty),
      quality_grade_ref: state.discountGradeRef,
      ...(state.discountDefectRef ? { quality_defect_ref: state.discountDefectRef } : {}),
    });
  }
  const loss = lossQty(state);
  if (loss > 0) {
    groups.push({
      quantity: String(loss),
      ...(state.lossDefectRef ? { quality_defect_ref: state.lossDefectRef } : {}),
      loss: true,
    });
  }
  return groups;
}

// ── Edição por numpad (inteiro, entrada tipo calculadora) ───────────────────

/** Primeiro dígito sobre um valor pré-preenchido SUBSTITUI (o previsto é sugestão, não texto). */
export function typeDigit(current: number, digit: string, fresh: boolean, max = 9999): number {
  const next = fresh ? Number(digit) : Number(`${current}${digit}`);
  if (!Number.isFinite(next)) return current;
  return Math.min(next, max);
}

export function typeBackspace(current: number): number {
  const text = String(current);
  return text.length <= 1 ? 0 : Number(text.slice(0, -1));
}
