// Receipt shaping (spec §D3 — web/CSS print). Pure functions that turn the
// finalized-sale snapshot into the lines a thermal receipt renders. The snapshot
// is captured at finalize (the cart is reset right after), so the receipt is a
// frozen record of what was sold — never recomputed from live state. Formatting
// only; no policy. The print transport (kiosk window.print → ESC-POS / network
// ePOS on real hardware) is validated separately on a device.
import type { POSCartItem, POSPaymentMethodProjection, PosFiscalState } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";
import { lineTotalQ } from "~/presentation/lineDiscounts";
import { methodLabel } from "~/presentation/payment";
import { kgDisplay, lineAmountQ } from "~/presentation/weighed";

export interface PosReceiptItem {
  name: string;
  qty: number;
  price_q: number;
  discountPct: number;
  /** Peça pesada: o peso, em gramas. `price_q` é então o preço do quilo. */
  weightG?: number;
}

export interface PosReceiptPayment {
  method: string;
  /** ONDE foi recebido: "terminal" (gaveta) ou "on_delivery" (na porta). */
  collection?: string;
  amount_q: number;
}

/** Frozen record of a finalized sale, captured before the cart resets. */
export interface PosReceiptSnapshot {
  orderRef: string;
  tabDisplay: string;
  customerName: string;
  items: PosReceiptItem[];
  totalDisplay: string;
  payments: PosReceiptPayment[];
  fulfillmentLabel: string;
  printedAtMs: number;
  /** Com quanto o cliente pagou (dinheiro sozinho no caixa), em centavos. É
   *  MEDIÇÃO: ausente/0 é "não medido", nunca "pagou justo" — a mesma régua do
   *  `tendered_q` do servidor. */
  tenderedQ?: number;
  /** Troco que saiu da gaveta, em centavos. */
  changeQ?: number;
  /** Cobrança na entrega/retirada: o papel sai ANTES do dinheiro. */
  paymentPending?: boolean;
  /** Encomenda paga antes: "A nota fiscal sai na retirada." — a mesma frase
   *  do servidor (`receipt_escpos._fiscal_handoff_line`). */
  fiscalHandoffLine?: string;
}

export interface ReceiptLineView {
  name: string;
  qty: number;
  /** "2×" ou "0,312 kg". */
  qtyLabel: string;
  unitDisplay: string;
  totalDisplay: string;
  discountPct: number;
}

/**
 * Entrou dinheiro NA GAVETA nesta venda?
 *
 * ⚠️ A pergunta parece "teve dinheiro?" e não é: é "teve dinheiro AQUI?". Numa
 * entrega paga na porta o operador ainda precisa lançar uma linha de dinheiro
 * para liberar o Validar — e a gaveta do balcão chutava e abria com o dinheiro
 * ainda na rua. Gaveta aberta sem motivo é caixa exposto e ruído de auditoria.
 *
 * A decisão mora aqui, e não dentro do fluxo de venda, porque ela é uma regra —
 * e regra se prova sem subir a venda inteira.
 */
export function cashLandedInDrawer(payments: readonly PosReceiptPayment[]): boolean {
  return payments.some((tender) => tender.method === "cash" && tender.collection !== "on_delivery");
}

/** Net line total in cents, applying the per-line percentage discount. */
export function receiptLineTotalQ(item: PosReceiptItem): number {
  const line = { qty: item.qty, weighed: item.weightG ? { entry: "weight" as const, weight_g: item.weightG } : null };
  const gross = lineAmountQ(item.price_q, line);
  if (!item.discountPct) return gross;
  const perUnit = Math.min(item.price_q, Math.round((item.price_q * item.discountPct) / 100));
  return Math.max(0, lineAmountQ(item.price_q - perUnit, line));
}

/**
 * Total do carrinho VIVO — o "Total parcial" do painel da comanda e da tela do
 * cliente. Soma as linhas por `lineTotalQ`: preço unitário do SERVIDOR × a
 * quantidade da tela.
 *
 * ⚠️ Ele NÃO aplica mais o percentual de desconto da linha por conta própria.
 * Isso era a tela calculando dinheiro, e calculando DIFERENTE do servidor: a
 * política é "maior desconto ganha, um por item" (`modifiers.py`), então um
 * desconto manual menor que o automático é DESCARTADO lá — e aplicado aqui.
 * Foi assim que a Tabatière com "Hora da Xepa −25%" e "cortesia −10%" exibiu
 * linha de R$ 9,00 e Total parcial de R$ 8,10 na mesma tela, com
 * `pricing.discount.items` vazio no banco provando que os 10% nunca valeram.
 *
 * Somar `charged_price_q` mantém a resposta instantânea ao toque e devolve a
 * invariante que faltava: as linhas somam exatamente o total. A review do
 * orquestrador segue sendo a autoridade final.
 */
export function cartNetTotalQ(items: POSCartItem[]): number {
  return items.reduce((sum, item) => sum + lineTotalQ(item), 0);
}

export function receiptLines(snap: PosReceiptSnapshot): ReceiptLineView[] {
  return snap.items.map((item) => ({
    name: item.name,
    qty: item.qty,
    qtyLabel: item.weightG ? kgDisplay(item.weightG) : `${item.qty}×`,
    unitDisplay: formatBRL(item.price_q) + (item.weightG ? "/kg" : ""),
    totalDisplay: formatBRL(receiptLineTotalQ(item)),
    discountPct: item.discountPct,
  }));
}

/**
 * As linhas de pagamento COMO O SERVIDOR IMPRIME (`receipt_escpos.sale_receipt`):
 * "Dinheiro R$ 42 / Recebido R$ 100 / Troco R$ 58". O recibo do navegador é o
 * fallback da bobina, e imprimia a linha como digitada ("Dinheiro R$ 100,00") —
 * dois papéis da mesma venda dizendo valores diferentes. O troco só existe no
 * dinheiro sozinho (o servidor recusa sobra dentro da lista de tenders), então
 * é da linha de dinheiro que ele sai.
 */
export function receiptPayments(
  snap: PosReceiptSnapshot,
  methods: POSPaymentMethodProjection[],
): { label: string; amountDisplay: string }[] {
  const changeQ = Math.max(0, snap.changeQ ?? 0);
  const tenderedQ = Math.max(0, snap.tenderedQ ?? 0);
  const lines = snap.payments.map((payment) => ({
    label: methodLabel(payment.method, methods),
    amountDisplay: formatBRL(
      payment.method === "cash" && changeQ > 0 ? Math.max(0, payment.amount_q - changeQ) : payment.amount_q,
    ),
  }));
  if (tenderedQ > 0) lines.push({ label: "Recebido", amountDisplay: formatBRL(tenderedQ) });
  if (changeQ > 0) lines.push({ label: "Troco", amountDisplay: formatBRL(changeQ) });
  return lines;
}

/**
 * O papel saiu antes do dinheiro? Cobrança na entrega/retirada carimba
 * "PAGAMENTO PENDENTE", como o servidor — sem a marca, um recibo com total
 * impresso é indistinguível de um comprovante.
 */
/**
 * A frase do recibo quando a NFC-e espera a saída da mercadoria (encomenda
 * paga antes — decisão de 26/09/2026); "" nos outros estados. O recibo é o
 * papel do pagamento, e sem a frase o cliente sai esperando uma nota.
 */
export function receiptFiscalHandoffLine(state: PosFiscalState): string {
  if (state === "awaiting_pickup") return "A nota fiscal sai na retirada.";
  if (state === "awaiting_delivery") return "A nota fiscal sai na entrega.";
  return "";
}

export function receiptPaymentPending(snap: PosReceiptSnapshot): boolean {
  if (snap.paymentPending) return true;
  return snap.payments.length > 0 && snap.payments.every((payment) => payment.collection === "on_delivery");
}
