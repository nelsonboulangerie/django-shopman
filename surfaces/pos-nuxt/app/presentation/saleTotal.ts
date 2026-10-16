// O total que a tela de VENDA mostra (botão do Pagamento, folha da mesa, resumo
// da folha fechada). Regra do dono (09/10/2026): total que ainda pode mudar não
// aparece como definitivo. A soma local do carrinho não sabe do desconto
// automático, da taxa de entrega nem do desconto manual que o servidor descarta
// quando um maior já ganhou; quem sabe é a revisão do servidor. Sem ela, a tela
// diz "Calculando…" e nenhum número.
import type { POSSaleReviewProjection } from "~/types/pos";

/** `confirmed`: o número é do servidor. `calculating`: a revisão está a caminho.
 *  `failed`: a revisão não respondeu (o Pagamento diz o motivo e oferece
 *  "Tentar de novo"). `hidden`: não há total a mostrar aqui (edição de
 *  encomenda, que tem a prévia própria no "Salvar alterações"). `offline`: sem
 *  conexão, o número é da TELA, pela última leitura de preços (`offlineSaleReview`),
 *  e a tela diz isso ao lado dele. */
export type SaleTotalStatus = "confirmed" | "offline" | "calculating" | "failed" | "hidden";

export interface SaleTotalView {
  status: SaleTotalStatus;
  /** "R$ 11,00" só com `confirmed`; "" em todos os outros estados. */
  display: string;
}

export interface SaleTotalInputs {
  /** O pagamento está aberto: a fonte é a revisão do checkout. */
  checkoutMode: boolean;
  checkoutReview: POSSaleReviewProjection | null;
  checkoutReviewFailed: boolean;
  /** Fora do pagamento: a revisão pedida em silêncio a cada mudança. */
  saleReview: POSSaleReviewProjection | null;
  saleReviewFailed: boolean;
  /** Edição de encomenda: o total vem da prévia do "Salvar alterações". */
  paused: boolean;
  hasItems: boolean;
}

export function saleTotalView(inputs: SaleTotalInputs): SaleTotalView {
  if (!inputs.hasItems || (inputs.paused && !inputs.checkoutMode)) return { status: "hidden", display: "" };
  const review = inputs.checkoutMode ? inputs.checkoutReview : inputs.saleReview;
  if (review) return { status: review.offline ? "offline" : "confirmed", display: review.total_display };
  const failed = inputs.checkoutMode ? inputs.checkoutReviewFailed : inputs.saleReviewFailed;
  return { status: failed ? "failed" : "calculating", display: "" };
}

/** O que a tela escreve no lugar do número. */
export function saleTotalText(view: SaleTotalView): string {
  if (view.status === "confirmed" || view.status === "offline") return view.display;
  if (view.status === "failed") return "Não calculado";
  if (view.status === "calculating") return "Calculando…";
  return "";
}
