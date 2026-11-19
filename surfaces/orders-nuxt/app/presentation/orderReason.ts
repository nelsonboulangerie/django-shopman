// Presentation — o diálogo de recusar e cancelar (WP-G06). Puro.
//
// Quem recusa precisa saber, ANTES de confirmar, qual pedido é e o que acontece com o
// dinheiro (laudo do Gestor, P1-11). Nada aqui decide regra de negócio: a frase do
// dinheiro é a do servidor (`cancel_money_effect`, do detalhe do pedido), a lista de
// motivos é a única do backend, e a tela só deixa de oferecer o motivo que o próprio
// pedido desmente (entrega numa retirada, pagamento não confirmado num pedido pago).
import type { CancelReasonProjection } from "~/generated/ordersContract";
import { splitRef } from "./board";

/** O que a tela sabe do pedido: do cartão (na hora) ou do detalhe (lido ao abrir). */
export interface ReasonOrderFacts {
  ref: string;
  customer_name?: string | null;
  total_display?: string | null;
  fulfillment_type?: string | null;
  fulfillment_label?: string | null;
  payment_method_label?: string | null;
  payment_status?: string | null;
  payment_status_label?: string | null;
  channel_ref?: string | null;
}

/** A leitura do destino do dinheiro: lendo, lida ou não deu para ler. */
export type MoneyRead = "loading" | "ready" | "error";

const DELIVERY_ONLY = "cannot_deliver";
const UNPAID_ONLY = "payment_not_confirmed";
// O dinheiro entrou: os mesmos estados que o servidor chama de pagamento completo
// (`_PAYMENT_COMPLETE`, em `projections/order_queue.py`).
const PAID = new Set(["captured", "paid"]);

/**
 * Os motivos que cabem NESTE pedido.
 *
 * Só sai o que o pedido desmente com certeza: "Não dá para entregar" quando o
 * recebimento é conhecido e não é entrega, e "Pagamento não confirmado" quando o
 * dinheiro já entrou. Sem o fato (pedido ainda não lido), nada é escondido. O motivo
 * que a tela já trouxe marcado (`initialKey`) fica sempre: quem o marcou sabe por quê.
 */
export function reasonsForOrder(
  reasons: readonly CancelReasonProjection[],
  options: {
    order?: ReasonOrderFacts | null;
    marketplace?: boolean;
    initialKey?: string;
  } = {},
): CancelReasonProjection[] {
  const { order, marketplace = false, initialKey = "" } = options;
  const fulfillment = String(order?.fulfillment_type ?? "").trim();
  const pickup = fulfillment !== "" && fulfillment !== "delivery";
  const paid = PAID.has(String(order?.payment_status ?? "").trim().toLowerCase());
  return reasons.filter((reason) => {
    if (marketplace && !reason.offered_on_ifood) return false;
    if (reason.key === initialKey) return true;
    if (reason.key === DELIVERY_ONLY && pickup) return false;
    if (reason.key === UNPAID_ONLY && paid) return false;
    return true;
  });
}

export interface ReasonDialogMoney {
  /** `loading`: lendo · `error`: não leu (a peça de estado do kit escreve a frase) ·
   *  `sentence`: a frase do servidor · `none`: o servidor não disse nada. Hoje é só
   *  o pedido do iFood (o dinheiro é dele) e o pagamento que o servidor não conseguiu
   *  ler; pedido sem nada recebido vem com "Nada foi cobrado do cliente." */
  state: "loading" | "error" | "sentence" | "none";
  text: string;
}

export interface ReasonDialogView {
  title: string;
  description: string;
  confirmLabel: string;
  /** Quem pediu ("Ana Souza"). Vazio quando a tela não identifica o pedido. */
  customer: string;
  total: string;
  /** "Retirada · Pix · Pago": como recebe e como paga, do cartão ou do detalhe. */
  facts: string;
  money: ReasonDialogMoney;
  reasons: CancelReasonProjection[];
  /** Por que o confirmar ainda não acende, além do motivo (só enquanto lê). Vazio libera. */
  blocked: string;
}

/** O que a leitura busca, com artigo: a peça de estado do kit monta a frase do erro. */
export const MONEY_WHAT = "o que acontece com o dinheiro";
export const MONEY_LOADING = "Lendo o que acontece com o dinheiro…";
export const MONEY_BLOCKED = "Falta ler o que acontece com o dinheiro.";

function joined(parts: Array<string | null | undefined>): string {
  return parts
    .map((part) => String(part ?? "").trim())
    .filter(Boolean)
    .join(" · ");
}

/**
 * O diálogo inteiro, já decidido.
 *
 * `identify` é o painel: o gesto nasce num cartão entre vários, então o título leva o
 * código ("Recusar o pedido W33?") e o corpo diz quem pediu e quanto. No detalhe do
 * pedido a página já é o pedido, e o diálogo só acrescenta o destino do dinheiro.
 * Enquanto o dinheiro é lido, o confirmar espera: recusar sem saber para onde ele vai
 * é a surpresa que este diálogo existe para evitar. Leitura que FALHA não prende a
 * recusa: o pedido novo se confirma sozinho quando o prazo vence, e quem queria
 * recusar acabaria aceitando. O diálogo diz que não leu, oferece tentar de novo e
 * deixa confirmar.
 */
export function reasonDialogView(input: {
  mode: "reject" | "cancel";
  reasons: readonly CancelReasonProjection[];
  marketplace?: boolean;
  order?: ReasonOrderFacts | null;
  identify?: boolean;
  moneyEffect?: string | null;
  moneyRead?: MoneyRead;
  initialKey?: string;
}): ReasonDialogView {
  const { mode, order, marketplace = false, identify = false } = input;
  const moneyRead = input.moneyRead ?? "ready";
  const verb = mode === "reject" ? "Recusar" : "Cancelar";
  const code = order?.ref ? splitRef(order.ref).code : "";
  const sentence = String(input.moneyEffect ?? "").trim();
  const money: ReasonDialogMoney =
    moneyRead === "loading"
      ? { state: "loading", text: MONEY_LOADING }
      : moneyRead === "error"
        ? { state: "error", text: "" }
        : sentence
          ? { state: "sentence", text: sentence }
          : { state: "none", text: "" };
  return {
    title: identify && code ? `${verb} o pedido ${code}?` : `${verb} pedido`,
    description: marketplace
      ? "Escolha o motivo. O iFood e o cliente recebem o aviso com ele."
      : "Escolha o motivo. O cliente recebe o aviso com a frase do motivo.",
    confirmLabel: `${verb} pedido`,
    customer: identify ? String(order?.customer_name ?? "").trim() : "",
    total: identify ? String(order?.total_display ?? "").trim() : "",
    facts: identify
      ? joined([
          order?.fulfillment_label,
          order?.payment_method_label,
          order?.payment_status_label,
        ])
      : "",
    money,
    reasons: reasonsForOrder(input.reasons, {
      order,
      marketplace,
      initialKey: input.initialKey,
    }),
    blocked: money.state === "loading" ? MONEY_BLOCKED : "",
  };
}

/**
 * O campo do diálogo que a recusa do servidor aponta (`field` do dialeto
 * `{detail, field, errors}`): `reason_key` é o motivo da lista, `internal_note` a
 * observação. Qualquer outro campo é falha do gesto inteiro.
 */
export function reasonErrorField(field: string | null | undefined): "" | "key" | "reason" {
  if (field === "reason_key") return "key";
  if (field === "internal_note") return "reason";
  return "";
}
