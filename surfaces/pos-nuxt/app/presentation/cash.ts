// Presentation — cash drawer shaping (spec §2.6, blind count).
//
// Pure transforms for the POS cash panel: the movement-kind labels, the
// opened-at formatting, and the terminal-occupied gate. The shift's full
// reconciliation report (expected vs counted, variance) lives in the backoffice
// (Unfold), NOT here — the POS never reveals the expected drawer, so the
// operator counts blind and the system computes the variance server-side.

import type { POSCashManagementCapability, POSCashRuntimeProjection } from "~/types/pos";

const MOVEMENT_LABELS: Record<string, string> = {
  sangria: "Sangria",
  suprimento: "Suprimento",
  ajuste: "Ajuste",
};

export function movementLabel(kind: string): string {
  return MOVEMENT_LABELS[kind] || kind;
}

/**
 * Os motivos comuns de cada tipo de movimento, para virarem botão.
 *
 * O motivo é obrigatório e continua sendo — mas exigir DIGITAÇÃO no meio da fila
 * é como se obriga o balcão a escrever "sangria" no campo motivo e seguir a vida:
 * a exigência sobrevive e a informação morre. Com opções para tocar, o motivo
 * responde o que a trilha precisa saber depois — PARA ONDE o dinheiro foi — em
 * vez de repetir o tipo que já está registrado ao lado.
 *
 * Tipo desconhecido devolve lista vazia de propósito: aí a tela cai no campo
 * livre, que é a saída honesta para o que não foi previsto aqui.
 */
const MOVEMENT_REASONS: Record<string, readonly string[]> = {
  sangria: ["Cofre", "Banco", "Fornecedor", "Troco"],
  suprimento: ["Troco", "Reforço"],
  ajuste: ["Sobra", "Falta", "Erro de lançamento"],
};

export function movementReasons(kind: string): readonly string[] {
  return MOVEMENT_REASONS[kind] || [];
}

/**
 * Se o movimento pode ser registrado: tipo, valor e motivo, os três presentes.
 *
 * O motivo é exigência da SUPERFÍCIE, não do servidor (`reason` é `blank=True`).
 * Fica aqui, puro, porque é regra de negócio da tela e não detalhe de template:
 * afrouxar isto por engano deixaria passar sangria sem motivo, e sangria sem
 * motivo é exatamente o buraco que o comprovante e o PIN do gerente fecham.
 */
export function canRegisterMovement(kind: string, amount: string, reason: string): boolean {
  return Boolean(kind && amount.trim() && reason.trim());
}

/**
 * Format the shift opening timestamp for the panel header (pt-BR, short). Falls
 * back to the raw string if it is not a parseable date, and to an em dash when
 * absent.
 */
export function formatOpenedAt(raw: string | null | undefined): string {
  if (!raw) return "—";
  const date = new Date(raw);
  return Number.isNaN(date.getTime())
    ? raw
    : date.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/**
 * Whether the terminal is held by another operator's open shift — the panel
 * blocks selling and tells the operator to use the right operator or close the
 * shift in the backoffice. Driven by the runtime Projection, never inferred.
 */
export function isTerminalOccupied(
  runtime: POSCashRuntimeProjection,
  hasOpenShift: boolean,
): boolean {
  return runtime.status === "terminal_occupied"
    || (!hasOpenShift && Boolean(runtime.blocking_operator_username));
}

/**
 * Whether selling requires an open cash shift — the sale screen redirects to
 * the session lobby (`/session`) when there is none. Contract-driven via the
 * checkout capability (absent flag = required, the safe default).
 */
export function requiresOpenShiftForSale(
  cashManagement: POSCashManagementCapability | null | undefined,
): boolean {
  return cashManagement?.requires_open_shift_for_sale !== false;
}

/** The lobby's single screen state — drives which card the antesala shows. */
export function sessionScreenState(
  runtime: POSCashRuntimeProjection,
  hasOpenShift: boolean,
): "occupied" | "open" | "closed" {
  if (isTerminalOccupied(runtime, hasOpenShift)) return "occupied";
  return hasOpenShift ? "open" : "closed";
}
