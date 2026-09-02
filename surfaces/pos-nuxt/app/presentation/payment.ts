// Presentation — payment screen shaping (spec §2.4, Odoo-style tender injection).
//
// Pure transforms for the payment screen: the method affordances, the tender
// line views, the "remaining/change/covered" math, the cash quick-add presets,
// and the digital payment proof (PIX QR / card checkout link). Zero policy: the
// orchestrator's `review` is authoritative for the total; remaining/change/
// covered here are a UX gate over the operator's tender draft, recomputed live
// so the screen can disable Finalize until the total is covered. The backend
// re-derives and seals everything on review/commit.

import type {
  POSCheckoutContractProjection,
  POSPaymentCollectionProjection,
  POSPaymentMethodProjection,
  POSPaymentResultProjection,
  POSPaymentTenderDraft,
} from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";

const PAYMENT_ICONS: Record<string, string> = {
  cash: "lucide:banknote",
  pix: "lucide:qr-code",
  // Três leituras de cartão, dois ícones. `card` (a forma indistinta da loja
  // online, que o balcão não oferece mais) e o CRÉDITO compartilham o cartão
  // clássico; o DÉBITO ganha o ícone de conta, porque o dinheiro sai na hora e é
  // essa a diferença que o operador precisa reconhecer de relance.
  card: "lucide:credit-card",
  credit: "lucide:credit-card",
  debit: "lucide:landmark",
  mixed: "lucide:layers",
  external: "lucide:ellipsis",
  account: "lucide:book-user",
};

/** O método "em conta", que só existe para cliente com conta na casa. */
export const ACCOUNT_METHOD: POSPaymentMethodProjection = { ref: "account", label: "Em conta" };

export function paymentIcon(ref: string): string {
  return PAYMENT_ICONS[ref] || "lucide:wallet";
}

/**
 * Methods the operator can inject as a tender. The derived "mixed" pseudo-method
 * is never a button — the method is derived from the set of tenders, not picked
 * (see `resolvePayment`).
 */
export function injectableMethods(
  methods: POSPaymentMethodProjection[],
  options: { houseAccount?: boolean } = {},
): POSPaymentMethodProjection[] {
  const base = methods.filter((method) => method.ref !== "mixed" && method.ref !== ACCOUNT_METHOD.ref);
  // "Em conta" só aparece para cliente com conta na casa: dado opcional faz a
  // tela crescer; sem a flag a opção nem existe (e o servidor recusa de todo jeito).
  return options.houseAccount ? [...base, ACCOUNT_METHOD] : base;
}

// Fallback pt-BR quando o contrato não conhece o ref — o operador nunca deve
// ler um ref cru tipo "external" numa linha de pagamento.
const METHOD_LABEL_FALLBACKS: Record<string, string> = {
  cash: "Dinheiro",
  pix: "Pix",
  card: "Cartão",
  credit: "Crédito",
  debit: "Débito",
  mixed: "Misto",
  external: "Outro meio",
  account: "Em conta",
};

export function methodLabel(ref: string, methods: POSPaymentMethodProjection[]): string {
  return methods.find((method) => method.ref === ref)?.label
    || METHOD_LABEL_FALLBACKS[ref]
    || "Outro meio";
}

export function tenderSumQ(tenders: POSPaymentTenderDraft[]): number {
  return tenders.reduce((sum, tender) => sum + (tender.amount_q || 0), 0);
}

/**
 * Amount still due. Can go negative once overpaid (cash change) — clamp at the
 * call site for display. Driven by the authoritative `totalQ` from the review.
 */
export function paymentRemainingQ(tenders: POSPaymentTenderDraft[], totalQ: number): number {
  return totalQ - tenderSumQ(tenders);
}

/** Soma das linhas em espécie — a única origem possível de troco. */
export function cashTenderSumQ(tenders: POSPaymentTenderDraft[]): number {
  return tenders.reduce((sum, tender) => sum + (tender.method === "cash" ? tender.amount_q || 0 : 0), 0);
}

/**
 * Troco = o excedente que veio EM DINHEIRO. Somar todas as linhas fazia o PDV
 * anunciar troco por um cartão digitado a mais — numa venda de R$ 42,00 com
 * R$ 5.000,00 na linha do cartão ele mandava devolver R$ 4.958,00 da gaveta.
 * Cartão e Pix cobram o que foi passado na maquininha; não há troco neles.
 */
export function paymentChangeQ(tenders: POSPaymentTenderDraft[], totalQ: number): number {
  return Math.min(Math.max(0, tenderSumQ(tenders) - totalQ), cashTenderSumQ(tenders));
}

/**
 * Excedente em linhas que NÃO são dinheiro: erro de digitação a corrigir, nunca
 * troco. Alimenta o aviso da tela (o servidor manda o mesmo em `warnings`).
 */
export function nonCashExcessQ(tenders: POSPaymentTenderDraft[], totalQ: number): number {
  const excess = Math.max(0, tenderSumQ(tenders) - totalQ);
  return excess - Math.min(excess, cashTenderSumQ(tenders));
}

// ── DIVIDIR A CONTA ──────────────────────────────────────────────────
//
// "Somos três, cada um paga o seu." O trilho de tenders já dava conta disso — o
// que faltava era o operador não ter que dividir 99,45 por 3 de cabeça, com os
// três clientes olhando.
//
// A divisão NÃO cria três linhas de uma vez. Ela muda o tamanho da PRÓXIMA
// linha: com "3 pessoas" ligado, tocar em Dinheiro lança um terço, tocar em
// Cartão lança o segundo terço, e assim por diante. É o fluxo do Odoo (pagamento
// parcial sucessivo), com a conta feita pela máquina — e ele compõe com tudo o
// que já existe: cada pessoa escolhe a SUA forma, o teclado continua editando
// qualquer linha, e "Exato" continua fechando o resto.

/** Quantas pessoas a tela oferece com um toque. Acima disso é caso raro. */
export const SPLIT_PRESETS = [2, 3, 4, 5, 6];

/**
 * Quanto vale a próxima linha numa conta dividida em ``count`` pessoas.
 *
 * A distribuição é por acumulação (``round(total·k/n) − round(total·(k−1)/n)``),
 * que é o único jeito de os centavos fecharem SEMPRE: dividir 100,00 por 3 dá
 * 33,34 + 33,33 + 33,33, e nunca 33,33 três vezes com um centavo órfão que o
 * operador teria que caçar.
 *
 * A ÚLTIMA parcela leva o que restou, não a fração nominal. Isso é o que mantém
 * a conta fechada mesmo depois de o operador editar uma linha no teclado — e
 * editar acontece o tempo todo ("esse aqui vai pagar os R$ 50, o resto divide").
 *
 * ``paidCount`` é quantas linhas já existem; ``remainingQ`` é o que falta.
 */
export function splitShareQ(
  totalQ: number,
  count: number,
  paidCount: number,
  remainingQ: number,
): number {
  const restante = Math.max(0, remainingQ);
  if (count <= 1 || restante <= 0) return restante;
  // Última parcela (ou já passou do combinado): fecha a conta.
  if (paidCount >= count - 1) return restante;
  const share =
    Math.round((totalQ * (paidCount + 1)) / count) - Math.round((totalQ * paidCount) / count);
  return Math.min(Math.max(0, share), restante);
}

/**
 * "R$ 33,34 · 1 de 3" — o estado da divisão em uma linha.
 *
 * O operador precisa saber quanto pedir à PESSOA À SUA FRENTE e quantas faltam,
 * e essas duas coisas mudam a cada linha lançada.
 */
export function splitHint(
  totalQ: number,
  count: number,
  paidCount: number,
  remainingQ: number,
): string {
  if (count <= 1) return "";
  const restante = Math.max(0, remainingQ);
  if (restante <= 0) return `Dividido em ${count}. Total coberto.`;
  const proxima = splitShareQ(totalQ, count, paidCount, restante);
  const pessoa = Math.min(paidCount + 1, count);
  // O verbo entra porque esta frase virou a INSTRUÇÃO do rodapé, lida de longe
     // e dita em voz alta ao cliente que está na frente. "R$ 21,00 · pessoa 3 de
     // 3" é etiqueta de mostrador; "Peça R$ 21,00" é o que fazer agora.
  return `Peça ${formatBRL(proxima)} · pessoa ${pessoa} de ${count}`;
}

/** UX gate: at least one tender and the total fully covered. */
export function isPaymentCovered(tenders: POSPaymentTenderDraft[], totalQ: number): boolean {
  return tenders.length > 0 && paymentRemainingQ(tenders, totalQ) <= 0;
}

/**
 * "Troco para quanto?" do dinheiro na entrega: quanto FALTA para o combinado da
 * porta cobrir o total (>0 = o cliente disse um valor menor que o pedido —
 * aviso na tela, nunca bloqueio; o servidor manda o mesmo na review). O campo
 * é opcional: vazio/zero não avisa nada.
 */
export function changeForShortfallQ(changeForQ: number, totalQ: number): number {
  if (!changeForQ || changeForQ <= 0) return 0;
  return Math.max(0, totalQ - changeForQ);
}

export interface TenderLineView {
  method: string;
  label: string;
  icon: string;
  amountQ: number;
  amountDisplay: string;
}

export function tenderLineView(
  tender: POSPaymentTenderDraft,
  methods: POSPaymentMethodProjection[],
): TenderLineView {
  return {
    method: tender.method,
    label: methodLabel(tender.method, methods),
    icon: paymentIcon(tender.method),
    amountQ: tender.amount_q,
    amountDisplay: formatBRL(tender.amount_q),
  };
}

// The Brazilian cash notes, in cents — the fallback when the channel contract
// does not carry a denomination set. These are the bills the customer hands
// over: tapping a note ADDS it to the received amount (Odoo's +10/+20/+50
// pattern), so two R$50 notes = two taps; "Limpar" resets.
const BRL_CASH_NOTES_Q = [200, 500, 1000, 2000, 5000, 10000];

/**
 * O trilho de cédulas do checkout, vindo do CONTRATO
 * (`cash_tender_delta_presets_q`, só valores positivos) — policy mora na
 * Projection, nunca na tela. Sem contrato (ou vazio), as cédulas BR padrão.
 */
export function cashNotesQ(contract: POSCheckoutContractProjection | null = null): number[] {
  const presets = contract?.cash_tender_delta_presets_q;
  const positive = Array.isArray(presets) ? presets.filter((value) => Number.isFinite(value) && value > 0) : [];
  return positive.length ? positive : BRL_CASH_NOTES_Q;
}

/** Collections offered for the current fulfillment type (e.g. on-delivery vs terminal). */
export function collectionsForFulfillment(
  collections: POSPaymentCollectionProjection[],
  fulfillmentType: string,
): POSPaymentCollectionProjection[] {
  return collections.filter((collection) => collection.fulfillment_types.includes(fulfillmentType as "pickup" | "delivery"));
}

export type PaymentProofTone = "info" | "warning" | "success" | "danger" | "neutral";

const PROOF_TONES: Record<string, PaymentProofTone> = {
  pending: "info",
  unavailable: "warning",
  error: "danger",
};

export interface PaymentProofView {
  method: string;
  icon: string;
  amountDisplay: string;
  status: string;
  tone: PaymentProofTone;
  message: string;
  /** Render-ready `<img src>` for the PIX QR (data URI or http), or "". */
  qrCodeSrc: string;
  copyPaste: string;
  checkoutUrl: string;
  isPix: boolean;
  isCard: boolean;
  /** Link de pagamento: a URL é para ENTREGAR ao cliente, não para abrir aqui. */
  isLink: boolean;
  /** Has gateway data worth surfacing (QR / copy-paste / checkout link). */
  hasProof: boolean;
  /** "amanhã às 9h" — até quando o LINK vale, dito como o operador diz ao
   *  cliente. Só o link: o Pix tem o próprio relógio na tela (polling). */
  expiresDisplay: string;
}

const DIAS_CURTOS = ["dom.", "seg.", "ter.", "qua.", "qui.", "sex.", "sáb."];

/**
 * "hoje às 18h" / "amanhã às 9h" / "sáb. 6/9 às 14h" — quando o link vence.
 *
 * Sem prazo dito, "o link parou de funcionar" vira ligação para o balcão. O
 * prazo é o MESMO que o pedido e o gateway carregam (`payment.expires_at`);
 * aqui só se traduz para a frase que o operador fala ao telefone: "hoje" e
 * "amanhã" por nome, e do dia seguinte em diante o dia da semana, que é o que
 * o cliente pergunta. Minuto só aparece quando não é cheio ("9h30").
 *
 * `now` entra por parâmetro para a função ser pura (e testável em qualquer dia).
 */
export function paymentDeadlineLabel(iso: string, now: Date = new Date()): string {
  if (!iso) return "";
  const deadline = new Date(iso);
  if (Number.isNaN(deadline.getTime())) return "";
  const minutes = deadline.getMinutes();
  const hora = minutes === 0
    ? `${deadline.getHours()}h`
    : `${deadline.getHours()}h${String(minutes).padStart(2, "0")}`;
  // Dias entre as MEIAS-NOITES locais: "amanhã" é o dia civil seguinte, não
  // "daqui a 24 h" — às 23h, um link que vence às 0h30 já é "amanhã".
  const startOfDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const dias = Math.round((startOfDay(deadline) - startOfDay(now)) / 86_400_000);
  if (dias === 0) return `hoje às ${hora}`;
  if (dias === 1) return `amanhã às ${hora}`;
  return `${DIAS_CURTOS[deadline.getDay()]} ${deadline.getDate()}/${deadline.getMonth() + 1} às ${hora}`;
}

/**
 * Normalize the gateway QR field into an `<img src>`. Efi returns the QR as a
 * base64 PNG (sometimes already a data URI); pass through http(s)/data URIs and
 * wrap a bare base64 payload. Empty in, empty out.
 */
export function qrCodeSrc(qrCode: string): string {
  if (!qrCode) return "";
  if (qrCode.startsWith("data:") || qrCode.startsWith("http")) return qrCode;
  return `data:image/png;base64,${qrCode}`;
}

/**
 * Shape the close_sale `payment` result into a render-ready proof, or null when
 * there is nothing to show (cash, or a digital method without gateway data).
 *
 * PCI SAQ A: the screen only DISPLAYS the gateway's QR / copy-paste / checkout
 * link — it never captures card data. The webhook is the authoritative return.
 */
export function paymentProofView(
  result: POSPaymentResultProjection | null | undefined,
  now: Date = new Date(),
): PaymentProofView | null {
  if (!result || !result.method) return null;
  const method = result.method;
  // Só quem gera PROVA REMOTA tem comprovante para mostrar: o Pix (QR + copia e
  // cola), o `card` da loja online e o LINK do pedido remoto (URL hospedada).
  // Crédito e débito do balcão não passam por gateway nenhum — a maquininha é
  // física e o comprovante é o papel que ela imprime.
  if (method !== "pix" && method !== "card" && method !== "link") return null;
  const qrSrc = qrCodeSrc(result.qr_code || "");
  const copyPaste = result.copy_paste || "";
  const checkoutUrl = result.checkout_url || "";
  return {
    method,
    icon: paymentIcon(method),
    amountDisplay: result.amount_display || "",
    status: result.status || "",
    tone: PROOF_TONES[result.status || ""] || "neutral",
    message: result.message || "",
    qrCodeSrc: qrSrc,
    copyPaste,
    checkoutUrl,
    isPix: method === "pix",
    isCard: method === "card",
    // O LINK é para ENTREGAR, não para abrir aqui. O `card` da loja online abre
    // o checkout numa aba — faz sentido lá, onde quem está na frente da tela é
    // quem compra. No balcão quem está na frente é o OPERADOR: abrir a página de
    // pagamento no PDV significaria ele digitando o cartão do cliente, que é
    // exatamente o que a maquininha existe para não acontecer.
    // O que ele precisa é passar a URL adiante — pelo QR que o cliente aponta o
    // celular, ou copiada para o WhatsApp.
    isLink: method === "link",
    hasProof: Boolean(qrSrc || copyPaste || checkoutUrl),
    expiresDisplay: method === "link" ? paymentDeadlineLabel(result.expires_at || "", now) : "",
  };
}


/** A TECLA de cada forma de pagamento — a primeira letra do rótulo, derivada do
 *  CONTRATO e não fixa no código: a casa pode renomear "Dinheiro" ou ganhar uma
 *  forma nova sem que a tela invente atalho errado.
 *
 *  Colisão não vira surpresa: quem chegar primeiro fica com a letra, e o segundo
 *  simplesmente não tem atalho (melhor sem tecla do que com uma que dispara a
 *  linha errada com o cliente na frente). Acento é normalizado — "Cartão" começa
 *  com C, e o teclado do balcão não tem "Ç" fácil.
 */
/**
 * A TECLA DE CADA FORMA — mapa explícito, por `ref`.
 *
 * ⚠️ Ela era DERIVADA da inicial do rótulo, e a derivação morreu no dia em que o
 * balcão passou a distinguir crédito de débito: "Dinheiro" e "Débito" disputam o
 * D, "Cartão" e "Crédito" disputam o C. O desempate era a ordem da lista — quem
 * chegasse depois ficava mudo, sem nada na tela dizendo por quê.
 *
 * As letras foram escolhidas para não colidirem e para caberem na cabeça:
 *
 *   R  Dinheiro   (de Reais — o D já é do débito)
 *   P  Pix
 *   C  Crédito
 *   D  Débito
 *   L  Link de pagamento
 *
 * Formas que o mapa não conhece caem na inicial, como antes: é o caso de "Em
 * conta" (E), que só aparece para cliente com conta na casa. Colisão com uma
 * letra já tomada deixa a forma sem atalho — o botão continua lá.
 */
const METHOD_KEYS: Record<string, string> = {
  cash: "R",
  pix: "P",
  credit: "C",
  debit: "D",
  link: "L",
  card: "C",
};

export function methodShortcuts(
  methods: POSPaymentMethodProjection[],
): Record<string, string> {
  const taken = new Set<string>();
  const out: Record<string, string> = {};
  for (const method of methods) {
    const letter = METHOD_KEYS[method.ref] || (method.label || method.ref)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .charAt(0)
      .toUpperCase();
    if (!/^[A-Z]$/.test(letter) || taken.has(letter)) continue;
    taken.add(letter);
    out[method.ref] = letter;
  }
  return out;
}
