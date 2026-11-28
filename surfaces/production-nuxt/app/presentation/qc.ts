// QC do fournil — transforms puros sobre a projection do quiosque (ADR-012/014).
// A aritmética da fornada (QC-FORNADA §4): previsto = a preço cheio + com
// desconto + perda, três grupos disjuntos por construção. O modelo é
// SUBTRATIVO, como se conta na boca do forno: a tela nasce com tudo a preço
// cheio e cada exceção é retirada dali. Sem I/O, sem refs — tudo testável.
import type { QCGradeProjection } from "~/types/production";

const LOWER_QUALITY_GRADE_REFS = new Set(["fair", "minimal"]);

export function isLowerQualityGrade(gradeRef: string): boolean {
  return LOWER_QUALITY_GRADE_REFS.has(gradeRef);
}

// ── Estado da tela de finalização ────────────────────────────────────────────

export interface QcEntryState {
  /**
   * A âncora da finalização: o que ENTROU no forno (started quando existe,
   * senão o previsto da ordem — ver ovenAnchor). null = fornada avulsa
   * (nasce sem expectativa).
   */
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
  /** O operador confirmou que saiu MAIS que o previsto (guarda anti-typo). */
  overshootConfirmed: boolean;
  /** Explicação auditável para o realizado acima do previsto. */
  overshootReason: string;
}

/**
 * A âncora do modelo subtrativo é a fornada REAL que entrou no forno
 * (QC-FORNADA §1: "a quantidade prevista que chega ao forno é quente").
 *
 * E, na Finalização, essa É a quantidade prevista: o que entrou no forno é o
 * que se espera que saia dele, salvo ocorrência. O plano da produção
 * (planejou 10, enfornou 11) já cumpriu seu papel na tela anterior — aqui
 * ele não é mais informação, é ruído; e ancorar nele pré-preencheria 10,
 * gravando 1 de perda que nunca existiu.
 */
export interface QcAnchor {
  /** O previsto DESTA tela: o que entrou no forno, senão o planejado. */
  anchor: number | null;
}

export function ovenAnchor(
  planned: number | null,
  started: number | null,
): QcAnchor {
  return { anchor: started !== null ? started : planned };
}

export function initialState(
  planned: number | null,
  defaultGradeRef: string,
): QcEntryState {
  return {
    planned,
    fullQty: planned ?? 0,
    fullTouched: false,
    fullGradeRef: defaultGradeRef,
    discountQty: 0,
    discountGradeRef: "",
    discountDefectRef: "",
    lossDefectRef: "",
    overshootConfirmed: false,
    overshootReason: "",
  };
}

// ── A escala ────────────────────────────────────────────────────────────────

export function fullPriceGrades(
  grades: QCGradeProjection[],
): QCGradeProjection[] {
  return grades.filter((g) => !isLowerQualityGrade(g.ref));
}

export function discountGrades(
  grades: QCGradeProjection[],
): QCGradeProjection[] {
  return grades.filter((g) => isLowerQualityGrade(g.ref));
}

export function defaultGradeRef(grades: QCGradeProjection[]): string {
  return (
    grades.find((g) => g.is_default)?.ref ??
    fullPriceGrades(grades)[0]?.ref ??
    ""
  );
}

/**
 * Faixa de cor da coluna da escala — funcional, não decorativa: empilhada ela
 * vira uma régua contínua que se lê como escala antes de se ler como palavra.
 * Derivada da SEMÂNTICA (rank/markdown), nunca do rótulo editável.
 */
export function gradeBandClass(
  grade: QCGradeProjection,
  grades: QCGradeProjection[],
): string {
  if (!isLowerQualityGrade(grade.ref)) {
    const topRank = Math.max(...grades.map((g) => g.rank));
    return grade.rank === topRank ? "bg-emerald-500" : "bg-zinc-400";
  }
  const discounted = discountGrades(grades).sort((a, b) => b.rank - a.rank);
  return discounted.findIndex((g) => g.ref === grade.ref) <= 0
    ? "bg-amber-500"
    : "bg-orange-600";
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
export function applyDiscountGrade(
  state: QcEntryState,
  gradeRef: string,
): QcEntryState {
  const qty =
    state.discountQty > 0 ? state.discountQty : discountDefault(state);
  const next: QcEntryState = {
    ...state,
    discountGradeRef: gradeRef,
    discountQty: qty,
  };
  if (!state.fullTouched && state.planned !== null && qty === state.planned) {
    next.fullQty = 0;
  }
  return next;
}

/** Perda derivada: o que não ficou pronto. Fora do plano não há previsto, logo não há perda derivável. */
export function lossQty(state: QcEntryState): number {
  if (state.planned === null) return 0;
  return Math.max(0, state.planned - state.fullQty - state.discountQty);
}

export function finishedTotal(state: QcEntryState): number {
  return state.fullQty + state.discountQty;
}

/** Total contabilizado na finalização: vendável + perda declarada. */
export function reportedTotal(state: QcEntryState): number {
  return finishedTotal(state) + lossQty(state);
}

// ── Confirmar sempre ativo: as perguntas que faltam ─────────────────────────

export type QcQuestion = "overshoot" | "loss_reason" | "discount_reason";

/** Saiu MAIS que o previsto — quase sempre é um dígito a mais, não milagre. */
export function overshootQty(state: QcEntryState): number {
  if (state.planned === null) return 0;
  return Math.max(0, finishedTotal(state) - state.planned);
}

/**
 * O sheet de perguntas não custa toque nenhum: Confirmar fecha a fornada e,
 * se falta resposta, pergunta — uma de cada vez — e fecha na última. A
 * plausibilidade vem primeiro (total acima do previsto pede confirmação: o
 * typo de 222 no lugar de 22 morre aqui), depois os motivos na ordem visual
 * dos cartões (perda à esquerda, sublote à direita).
 */
export function pendingQuestions(state: QcEntryState): QcQuestion[] {
  const out: QcQuestion[] = [];
  if (
    overshootQty(state) > 0 &&
    (!state.overshootConfirmed || !state.overshootReason.trim())
  )
    out.push("overshoot");
  if (lossQty(state) > 0 && !state.lossDefectRef) out.push("loss_reason");
  if (
    state.discountQty > 0 &&
    state.discountGradeRef &&
    !state.discountDefectRef
  ) {
    out.push("discount_reason");
  }
  return out;
}

/** Realizado ou perda contabilizada fecha o lote; perda total não é cancelamento. */
export function canSubmit(state: QcEntryState): boolean {
  return reportedTotal(state) > 0;
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
    groups.push({
      quantity: String(state.fullQty),
      quality_grade_ref: state.fullGradeRef,
    });
  }
  if (state.discountQty > 0 && state.discountGradeRef) {
    groups.push({
      quantity: String(state.discountQty),
      quality_grade_ref: state.discountGradeRef,
      ...(state.discountDefectRef
        ? { quality_defect_ref: state.discountDefectRef }
        : {}),
    });
  }
  const loss = lossQty(state);
  if (loss > 0) {
    groups.push({
      quantity: String(loss),
      ...(state.lossDefectRef
        ? { quality_defect_ref: state.lossDefectRef }
        : {}),
      loss: true,
    });
  }
  return groups;
}

// ── A unidade do lote (P1-22) ───────────────────────────────────────────────
// Pão se conta por peça; massa e creme se pesam, com vírgula. A tela recebe a
// unidade do lote e escreve cada quantidade com ela. Sem conversão de escala:
// o número digitado é o número mostrado, na unidade em que o lote foi aberto.

const COUNT_UNITS = new Set(["", "un", "un.", "und", "pc", "pç", "unidade"]);

/** Peça inteira (sem vírgula no teclado) ou grandeza que se pesa ou mede. */
export function isCountUnit(unit: string | null | undefined): boolean {
  return COUNT_UNITS.has((unit ?? "").trim().toLowerCase());
}

/** Casas decimais aceitas pelo teclado: nenhuma na peça, três no peso. */
export function quantityDecimals(unit: string | null | undefined): number {
  return isCountUnit(unit) ? 0 : 3;
}

/** O teto do teclado. Passar dele avisa; nunca corta em silêncio. */
export const QUANTITY_MAX = 9999;

/** Arredonda na casa do teclado: soma de 0,1 + 0,2 não vira 0,30000000000000004. */
export function roundQuantity(value: number, decimals = 3): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

const NUMBER_FORMAT = new Intl.NumberFormat("pt-BR", {
  maximumFractionDigits: 3,
});

/** "32", "2,5": o número na voz da tela, sem unidade. */
export function formatQcNumber(value: number): string {
  return NUMBER_FORMAT.format(roundQuantity(value));
}

/** "32 un.", "2,5 kg": a quantidade com a unidade do lote escrita. */
export function formatQcQuantity(
  value: number,
  unit: string | null | undefined,
): string {
  const normalized = (unit ?? "").trim().toLowerCase();
  return `${formatQcNumber(value)} ${isCountUnit(normalized) ? "un." : normalized}`;
}

/** Texto do teclado ("2,5") para número (2.5). Vírgula pendurada vale o inteiro. */
export function parseQuantityText(text: string): number {
  const value = Number.parseFloat(text.replace(",", "."));
  return Number.isFinite(value) ? value : 0;
}

/** Número para o texto do teclado: 2.5 → "2,5"; 0 → "0". */
export function quantityText(value: number): string {
  return String(roundQuantity(value)).replace(".", ",");
}

export type QuantityKeyResult =
  | { ok: true; text: string }
  | { ok: false; reason: "max" | "decimals" | "no_decimal" };

/**
 * Uma tecla sobre o texto do teclado, como numa calculadora: o primeiro dígito
 * sobre um valor sugerido o SUBSTITUI; a vírgula só existe onde o lote se pesa,
 * uma vez, e com o número de casas da unidade. Passar do teto não corta calado:
 * devolve o motivo para a tela dizer.
 */
export function typeQuantityKey(
  current: string,
  key: string,
  fresh: boolean,
  decimals: number,
  max = QUANTITY_MAX,
): QuantityKeyResult {
  const base = fresh ? "" : current === "0" ? "" : current;
  if (key === ",") {
    if (decimals === 0) return { ok: false, reason: "no_decimal" };
    if (base.includes(",")) return { ok: true, text: base };
    return { ok: true, text: `${base || "0"},` };
  }
  if (!/^\d$/.test(key)) return { ok: true, text: current };
  const [, fraction] = base.split(",");
  if (fraction !== undefined && fraction.length >= decimals) {
    return { ok: false, reason: "decimals" };
  }
  const next = `${base}${key}`;
  if (parseQuantityText(next) > max) return { ok: false, reason: "max" };
  return { ok: true, text: next.includes(",") ? next : String(Number(next)) };
}

/** Apaga o último caractere; o vazio é zero. */
export function backspaceQuantityText(current: string): string {
  const next = current.slice(0, -1);
  return next === "" ? "0" : next;
}

// ── Rendeu diferente do previsto: o motivo em um toque (P1-07) ──────────────
// A decisão de 05/11 (#2150) pede o motivo; não pede teclado. Mesmo desenho dos
// motivos da perda: um toque escolhe e segue; "Outro" abre o texto.

// Cada motivo diz a CAUSA, nunca repete a pergunta. A lista segue a unidade do
// lote: "peça maior que o padrão" não existe num creme pesado em quilo.
const YIELD_REASONS = {
  shortfall: {
    count: [
      "Peças maiores que o padrão",
      "Massa perdida antes do forno",
      "Receita feita com menos massa",
    ],
    measured: [
      "Ficou na bacia e no batedor",
      "Evaporou mais no cozimento",
      "Receita feita com menos insumo",
    ],
  },
  overshoot: {
    count: [
      "Peças menores que o padrão",
      "Sobra de massa aproveitada",
      "Receita feita com mais massa",
    ],
    measured: [
      "Evaporou menos no cozimento",
      "Sobra aproveitada no preparo",
      "Receita feita com mais insumo",
    ],
  },
} as const;

/** Os motivos prontos de "rendeu menos" ou "rendeu mais", na unidade do lote. */
export function yieldReasons(
  kind: "shortfall" | "overshoot",
  unit: string | null | undefined,
): readonly string[] {
  return YIELD_REASONS[kind][isCountUnit(unit) ? "count" : "measured"];
}
