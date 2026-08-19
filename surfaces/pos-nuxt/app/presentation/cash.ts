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
  POSChangeDenomination,
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
 * Os motivos que viram botão, por tipo de movimento — vindos do SERVIDOR.
 *
 * O motivo é obrigatório na saída e quem cobra é o servidor. Exigir DIGITAÇÃO
 * no meio da fila é como se obriga o balcão a escrever "sangria" no campo e
 * seguir a vida: a exigência sobrevive e a informação morre. Com opções para
 * tocar, ele responde a única pergunta que a trilha precisa depois: **para onde
 * foi**.
 *
 * ⚠️ A ENTRADA vem com lista vazia, e isso é deliberado: "entrada de caixa" já
 * é a resposta inteira, e um campo com uma opção só ensina o balcão a preencher
 * qualquer coisa para passar.
 *
 * ⚠️ "Troco" NÃO é motivo de saída, e a ausência é deliberada — há teste que
 * trava, no servidor. Trocar uma nota não muda o dinheiro que existe na gaveta:
 * saem R$ 50, entram 5×R$ 10, o total é o mesmo. Lançar como saída derruba o
 * esperado por um dinheiro que nunca saiu, e o turno fecha com falta fantasma.
 * Quem precisa de troco PEDE troco, que é outro fluxo e é net zero.
 */
export function movementReasons(
  cashManagement: POSCashManagementCapability | null | undefined,
  kind: string,
): readonly string[] {
  return cashManagement?.movement_reasons?.[kind] || [];
}

/**
 * Se o movimento pode ser registrado.
 *
 * A tela reprova ANTES para o operador não convocar o gerente e só então
 * descobrir que faltava um campo. O servidor reprova de novo, e é lá que a
 * regra vale: contrato que só a superfície cobra não é contrato.
 *
 * O motivo é exigido só na SAÍDA. Na entrada não há o que perguntar.
 */
export function canRegisterMovement(kind: string, amount: string, reason: string): boolean {
  if (!kind || !amount.trim()) return false;
  return kind === "sangria" ? Boolean(reason.trim()) : true;
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

/**
 * As cédulas e moedas que o balcão pode pedir — vindas do SERVIDOR.
 *
 * Repetir os números aqui seria assinar uma divergência para o dia em que uma
 * moeda saísse de circulação: o pedido passaria a falar de um dinheiro que não
 * existe, e ninguém descobriria pela tela.
 */
export function changeDenominations(
  cashManagement: POSCashManagementCapability | null | undefined,
): readonly POSChangeDenomination[] {
  return cashManagement?.change_denominations || [];
}

/**
 * O valor é sempre exigido, e é EXATO.
 *
 * Antes havia um pedido "aproximado" ao lado de "moedas" e "notas pequenas":
 * quem ia buscar o troco lia "moedas", tinha de adivinhar quanto, e voltava com
 * o que achou. Um número pedido de verdade é o que faz a viagem valer.
 *
 * As denominações NÃO são exigidas: "me traz R$ 100" é um pedido completo, e
 * travar a fila por um refino que o gerente resolve com o que tem no cofre
 * seria trocar a fila por nada.
 */
export function canRequestChange(amount: string): boolean {
  return Boolean(amount.trim()) && parseAmountToQ(amount) > 0;
}

/** "120,50" / "120.50" / "120" → centavos. Ilegível vira 0, e o CTA não arma. */
export function parseAmountToQ(raw: string): number {
  const limpo = String(raw ?? "").trim().replace(/\s/g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(limpo)) return 0;
  return Math.round(Number(limpo) * 100);
}

/** Como a denominação se lê num resumo de uma linha: "R$ 20", "0,50". */
export function denominationLabel(
  cashManagement: POSCashManagementCapability | null | undefined,
  q: number,
): string {
  return changeDenominations(cashManagement).find((d) => d.q === q)?.label || String(q);
}

/**
 * A linha que o gerente lê antes de sair para buscar: quanto, e em quê.
 *
 * Sem denominação escolhida, o resumo é só o valor — e isso é um pedido
 * inteiro, não um pedido pela metade.
 */
export function changeRequestSummary(
  request: POSChangeRequestProjection,
  cashManagement?: POSCashManagementCapability | null,
): string {
  const valor = request.amount_display || "";
  const partes = (request.denominations || []).map((q) => denominationLabel(cashManagement, q));
  if (!partes.length) return valor;
  return valor ? `${valor} · em ${partes.join(", ")}` : `em ${partes.join(", ")}`;
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
