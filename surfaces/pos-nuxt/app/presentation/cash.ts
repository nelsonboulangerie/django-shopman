// Presentation — cash drawer shaping (spec §2.6, blind count).
//
// Pure transforms for the POS cash panel: the movement-kind labels, the
// opened-at formatting, and the terminal-occupied gate. The shift's full
// reconciliation report (expected vs counted, variance) lives in the backoffice
// (Unfold), NOT here — the POS never reveals the expected drawer, so the
// operator counts blind and the system computes the variance server-side.

import type {
  POSCashManagementCapability,
  POSCashRuntimeProjection,
  POSChangeRequestProjection,
} from "~/types/pos";

/**
 * O rótulo que o operador lê. O REF continua `sangria`/`suprimento` — é o
 * identificador do domínio, viaja na API e está no banco.
 *
 * "Sangria" é vocabulário de PDV brasileiro: quem trabalha em varejo sabe, quem
 * lê a filipeta dias depois não. Entrada/Saída não precisa ser aprendido, e a
 * conferência do caixa é feita justamente por quem não estava no balcão.
 */
const MOVEMENT_LABELS: Record<string, string> = {
  sangria: "Saída de caixa",
  suprimento: "Entrada de caixa",
};

export function movementLabel(kind: string): string {
  return MOVEMENT_LABELS[kind] || kind;
}

/**
 * Os motivos comuns de cada tipo, para virarem botão.
 *
 * O motivo é obrigatório e continua sendo — mas exigir DIGITAÇÃO no meio da fila
 * é como se obriga o balcão a escrever "sangria" no campo motivo e seguir a
 * vida: a exigência sobrevive e a informação morre. Com opções para tocar, ele
 * responde a única pergunta que a trilha precisa depois: **para onde foi**
 * (sangria) ou **de onde veio** (suprimento).
 *
 * ⚠️ "Troco" NÃO é motivo de sangria, e a ausência é deliberada — há teste que
 * trava. Trocar uma nota não muda o dinheiro que existe na gaveta: saem R$ 50,
 * entram 5×R$ 10, o total é o mesmo. Lançar como sangria derruba o esperado por
 * um dinheiro que nunca saiu, e o turno fecha com falta fantasma se ninguém
 * lembrar do suprimento gêmeo. Gaveta que abre sem mover dinheiro é "abrir sem
 * venda", que já existe e já pede motivo.
 *
 * Tipo desconhecido devolve lista vazia de propósito: aí a tela cai no campo
 * livre, que é a saída honesta para o que não foi previsto aqui.
 */
const MOVEMENT_REASONS: Record<string, readonly string[]> = {
  sangria: ["Cofre", "Banco", "Fornecedor"],
  suprimento: ["Reforço de troco", "Cofre", "Banco"],
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

// ── Pedido de troco ────────────────────────────────────────────────────────
//
// Quando falta troco, o operador saía do balcão com dinheiro até o cofre: parte
// do trajeto tem câmera, parte não, e a falta só apareceria no fechamento. Aqui
// ele PEDE, alguém traz, e a troca acontece no balcão entre duas pessoas.
//
// ⚠️ Trocar dinheiro é NET ZERO — saem R$ 50, entram 5×R$ 10. Nada nesta seção
// fala de valor esperado, movimento ou fechamento, e não pode passar a falar:
// somar um pedido ao caixa inventaria uma diferença que não existe.

/** O que o balcão pode pedir. Ref em inglês (contrato), rótulo pt-BR na tela. */
export const CHANGE_REQUEST_KINDS = [
  { ref: "coins", label: "Moedas" },
  { ref: "small_bills", label: "Notas pequenas" },
  { ref: "amount", label: "Valor" },
] as const;

export function changeRequestLabel(kind: string): string {
  return CHANGE_REQUEST_KINDS.find((k) => k.ref === kind)?.label || kind;
}

/**
 * Só o pedido por VALOR exige número.
 *
 * "Acabou moeda" já é um pedido inteiro, e exigir um valor ali travaria a fila
 * por um dado que ninguém tem na hora. Já "me traz um valor" sem número não diz
 * nada a quem vai buscar o troco — o servidor recusa, e a tela recusa antes.
 */
export function canRequestChange(kind: string, amount: string): boolean {
  if (!kind) return false;
  return kind === "amount" ? Boolean(amount.trim()) : true;
}

/**
 * A linha que o gerente lê antes de assinar: o que foi pedido, e quanto se o
 * pedido falou de valor. Sem sufixo inventado quando não falou.
 */
export function changeRequestSummary(request: POSChangeRequestProjection): string {
  const label = changeRequestLabel(request.kind);
  return request.amount_display ? `${label} · ${request.amount_display}` : label;
}

/** Format the request timestamp for the pending list (pt-BR, hour and minute). */
export function formatRequestedAt(raw: string | null | undefined): string {
  if (!raw) return "";
  const date = new Date(raw);
  return Number.isNaN(date.getTime())
    ? raw
    : date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/** The lobby's single screen state — drives which card the antesala shows. */
export function sessionScreenState(
  runtime: POSCashRuntimeProjection,
  hasOpenShift: boolean,
): "occupied" | "open" | "closed" {
  if (isTerminalOccupied(runtime, hasOpenShift)) return "occupied";
  return hasOpenShift ? "open" : "closed";
}
