// Presentation — tela de resultado pós-venda.
//
// Transforms puros da tela que sucede o Validar: o título (caloroso quando há
// cliente vinculado), o troco congelado e a decisão de avanço (auto-avanço
// curto e Enter). Zero política de dinheiro: o troco chega CONGELADO do
// fechamento (`result.changeQ`, capturado pelo usePosSale) — aqui só se decide
// como a tela se comporta com ele.

import type { PaymentProofView } from "~/presentation/payment";
import type { PosFiscalState, POSPaymentDeliveryProjection } from "~/types/pos";
import type { PosReceiptSnapshot } from "~/presentation/receipt";
import { firstName } from "~/presentation/customerDisplay";
import { formatBRL } from "~/utils/posIntent";

export type PixPollStatus = "idle" | "polling" | "paid" | "expired";

/**
 * O resultado congelado da venda fechada — nasce no `submitSale` (usePosSale) e
 * fica de pé enquanto a tela de resultado existe. `changeQ` é o troco capturado
 * no instante do commit (o cart reseta logo depois): uma fonte só para o palco
 * do operador, a tela do cliente e o recibo.
 */
export interface PosSaleResultSnapshot {
  salesMode?: "counter" | "order";
  orderRef: string;
  /** Link do pedido no Gestor de Pedidos (orders app). */
  nextUrl: string;
  payment: PaymentProofView | null;
  paymentDelivery?: POSPaymentDeliveryProjection | null;
  receipt: PosReceiptSnapshot;
  fiscalExpected: boolean;
  /** Onde a NFC-e está AGORA. Vem do close; sem ele, deriva de `fiscalExpected`
   *  (`resolveFiscalState`). Promovida pela própria tela quando o 409 da bobina
   *  vira 200 (`authorized`) e quando o Pix confirma (`awaiting_payment` →
   *  `queued`). */
  fiscalState: PosFiscalState;
  /** Troco que SAIU DA GAVETA nesta venda, em centavos. Zero na cobrança na
   *  entrega/retirada: o dinheiro ainda não entrou, e o herói "Confira o troco"
   *  travava Enter e auto-avanço por um troco que ninguém tinha em mãos. */
  changeQ: number;
  /** Troco que o entregador/balcão vai LEVAR para o hand-off (cobrança na
   *  entrega/retirada) — informativo, sem herói e sem travar a tela. */
  courierChangeQ?: number;
  /** O cliente pediu a nota IMPRESSA? Congelado aqui porque o carrinho já
   *  zerou quando a nota autoriza — e é dela que a impressão automática vive. */
  wantsPrintedInvoice: boolean;
  /** ENCOMENDA: como e quando o pedido será recebido, congelados no commit —
   *  é o que o operador lê de volta ao cliente antes de desligar o telefone. */
  fulfillmentLabel?: string;
  scheduleLabel?: string;
}

/**
 * A LEITURA DE VOLTA da encomenda: "Retirada · sáb, 20/09, 10:00 às 10:30".
 *
 * Só existe no modo encomenda — na venda de balcão o pedido já foi entregue na
 * mão. Congelada no `result` porque o carrinho zera logo depois do commit, e a
 * tela de resultado é a última chance de o operador confirmar em voz alta o
 * combinado com o cliente na frente (ou ao telefone).
 */
export function orderReadback(result: Pick<PosSaleResultSnapshot, "salesMode" | "fulfillmentLabel" | "scheduleLabel">): { fulfillment: string; schedule: string } | null {
  if (result.salesMode !== "order") return null;
  const fulfillment = (result.fulfillmentLabel || "").trim();
  const schedule = (result.scheduleLabel || "").trim();
  if (!fulfillment && !schedule) return null;
  return { fulfillment, schedule };
}

export interface SaleResultAdvanceInputs {
  /** Troco congelado no fechamento, em centavos. 0 = pagamento exato/digital. */
  changeQ: number;
  payment: PaymentProofView | null;
  pixStatus: PixPollStatus;
  /** ENCOMENDA: a tela é a leitura de volta ao cliente — Enter não a dispensa. */
  salesMode?: "counter" | "order";
}

/**
 * O estado fiscal que a tela usa quando o servidor ainda não fala `fiscal_state`:
 * nota esperada = "na fila" (ela ainda não existe no instante do fechamento);
 * não esperada = nada a imprimir.
 */
export function resolveFiscalState(
  response: { fiscal_state?: PosFiscalState | null; fiscal_expected?: boolean | null },
): PosFiscalState {
  if (response.fiscal_state) return response.fiscal_state;
  return response.fiscal_expected ? "queued" : "not_expected";
}

/** O rótulo curto do estado da NFC-e — chip das Últimas vendas e da tela de resultado. */
export function fiscalStateLabel(state: PosFiscalState): string {
  switch (state) {
    case "authorized": return "NFC-e autorizada";
    case "queued": return "NFC-e na fila";
    case "awaiting_payment": return "NFC-e aguarda o pagamento";
    case "failed": return "NFC-e falhou";
    default: return "Sem NFC-e";
  }
}

export type DanfeOffer =
  | { kind: "print"; label: "Imprimir DANFE" }
  | { kind: "queued"; label: "NFC-e na fila…" }
  | { kind: "awaiting_payment"; label: "NFC-e sai quando o pagamento confirmar" }
  | { kind: "failed"; label: "NFC-e falhou — veja Últimas vendas" }
  | null;

/**
 * O que a tela OFERECE sobre a DANFE — por existência da nota, não por previsão.
 *
 * O botão "Imprimir DANFE" aparecia por `fiscalExpected`, e o endpoint responde
 * 409 até a SEFAZ autorizar (no Pix, durante toda a espera): o operador tocava e
 * lia um erro por uma nota que ainda não existia. Só `authorized` ganha o botão
 * vivo; `queued` mostra o botão desabilitado (a impressão automática promove
 * quando o 409 vira 200); `awaiting_payment` e `failed` dizem o próximo passo.
 */
export function danfeOffer(state: PosFiscalState): DanfeOffer {
  switch (state) {
    case "authorized": return { kind: "print", label: "Imprimir DANFE" };
    case "queued": return { kind: "queued", label: "NFC-e na fila…" };
    case "awaiting_payment": return { kind: "awaiting_payment", label: "NFC-e sai quando o pagamento confirmar" };
    case "failed": return { kind: "failed", label: "NFC-e falhou — veja Últimas vendas" };
    default: return null;
  }
}

/** "Troco a separar: R$ 58" — a linha discreta da cobrança na entrega; "" sem troco. */
export function courierChangeLine(courierChangeQ: number | undefined): string {
  return courierChangeQ && courierChangeQ > 0 ? `Troco a separar: ${formatBRL(courierChangeQ)}` : "";
}

/** Com cliente vinculado o obrigado é nominal (frase completa, com ponto e
 *  maiúscula); sem, a confirmação seca. */
export function saleResultTitle(customerName: string, payment: PaymentProofView | null = null): string {
  // Cobrança falhada não recebe frase de despedida: a venda existe, o dinheiro
  // não entrou, e o título é a primeira coisa que o operador lê.
  if (paymentFailed(payment)) return "Venda registrada, cobrança não criada";
  const nome = firstName(customerName);
  return nome ? `Venda concluída. Obrigado, ${nome}!` : "Venda concluída";
}

/**
 * A COBRANÇA FALHOU — o gateway recusou, ou não devolveu nada exibível.
 *
 * ⚠️ Isto não é detalhe de status: a venda COMMITOU (pedido criado, linha no
 * livro-caixa) e o dinheiro NÃO foi cobrado. Foi assim que o Pix do balcão
 * sumia em silêncio: o gateway devolvia 403, `hasProof` ficava falso, o bloco
 * da prova não renderizava, e a tela mostrava o check verde de "Venda
 * concluída" e se fechava sozinha em 5 s. O operador via uma venda paga onde
 * ninguém tinha cobrado nada.
 */
export function paymentFailed(payment: PaymentProofView | null): boolean {
  const status = payment?.status || "";
  return status === "error" || status === "unavailable";
}

/** PIX com prova na tela e confirmação ainda não chegada (polling vivo). */
export function pixAwaiting(payment: PaymentProofView | null, pixStatus: PixPollStatus): boolean {
  return Boolean(payment?.isPix && payment?.hasProof) && pixStatus === "polling";
}

/** Troco pronto para exibir; "" quando não há troco. */
export function changeDisplay(changeQ: number): string {
  return changeQ > 0 ? formatBRL(changeQ) : "";
}

export const AUTO_ADVANCE_SECONDS = 5;

/**
 * Auto-avanço para a próxima venda: só quando NADA na tela pede gesto.
 *
 * - Troco a conferir → NUNCA: a tela não some sozinha em cima do dinheiro.
 * - PIX aguardando ou expirado → NUNCA: prova pendente/não resolvida não é
 *   descartada em silêncio (sair exige toque explícito).
 * - COBRANÇA FALHADA → NUNCA: a venda ficou sem cobrança, e essa é a única
 *   tela que diz isso. Sair dali é decisão de quem vai cobrar de outro jeito.
 * - LINK DE PAGAMENTO → NUNCA: a URL existe para ser COPIADA e mandada ao
 *   cliente. Uma tela que se fecha sozinha em cima do único lugar onde aquele
 *   link aparece não é auto-avanço, é perda: o pedido fica aguardando um
 *   pagamento que ninguém pediu, e recuperar a URL exige ir ao gestor.
 * - `prefers-reduced-motion` → desliga a contagem (a tela espera o toque).
 *
 * Retorna os segundos da contagem, ou 0 = não avança sozinho.
 */
export function autoAdvanceSeconds(
  inputs: SaleResultAdvanceInputs & { reducedMotion: boolean },
): number {
  if (inputs.reducedMotion) return 0;
  if (inputs.changeQ > 0) return 0;
  if (paymentFailed(inputs.payment)) return 0;
  if (inputs.payment?.isPix && inputs.payment.hasProof && inputs.pixStatus !== "paid") return 0;
  if (inputs.payment?.isLink && inputs.payment.hasProof) return 0;
  return AUTO_ADVANCE_SECONDS;
}

/**
 * Enter avança? Nunca com troco pendente de confirmação (o Enter que validou a
 * venda não pode engolir a tela do troco) nem com PIX ainda aguardando — nesses
 * dois casos sair é gesto deliberado no CTA (ou F2).
 */
export function enterAdvances(inputs: SaleResultAdvanceInputs): boolean {
  // ENCOMENDA: a tela é a leitura de volta ("era sábado, não sexta") e a saída
  // das fichas. O Enter que validou não pode engoli-la por hábito — sair é F2
  // ou o CTA, como o auto-avanço já não corre aqui.
  if (inputs.salesMode === "order") return false;
  if (inputs.changeQ > 0) return false;
  // O Enter que validou a venda não pode passar por cima do aviso de que a
  // cobrança não foi criada.
  if (paymentFailed(inputs.payment)) return false;
  if (pixAwaiting(inputs.payment, inputs.pixStatus)) return false;
  // Mesmo motivo do auto-avanço: o Enter que validou a venda não pode engolir a
  // tela onde o link mora. Sair dali é gesto deliberado no CTA (ou F2).
  if (inputs.payment?.isLink && inputs.payment.hasProof) return false;
  return true;
}
