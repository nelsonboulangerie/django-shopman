import { computed, ref } from "vue";
import { toast } from "vue-sonner";

import type { PosPaymentCollection } from "~/generated/posContract";
import type { POSPaymentTenderDraft } from "~/types/pos";
import {
  isPaymentCovered,
  paymentChangeQ as computeChangeQ,
  paymentRemainingQ as computeRemainingQ,
  splitDraftTender,
  splitHint,
  splitShareQ,
} from "~/presentation/payment";

/**
 * AS LINHAS DE PAGAMENTO — o instrumento da tela de Pagamento, num lugar só.
 *
 * Gesto de dinheiro tem UMA tela (dono, 16/11/2026): a venda e o "Receber e
 * entregar" da encomenda usam o mesmo `PosPaymentWorkspace`, e por isso o mesmo
 * estado por trás dele. As formas lançadas, o teclado, as cédulas, o Exato e a
 * divisão da conta moram aqui; quem usa (`usePosSale`, `PosPreorderBalancePayment`)
 * diz só qual é o total, se ele já é o do servidor e onde o dinheiro é recebido.
 *
 * Pagamento por injeção (estilo Odoo): o operador lança linhas em qualquer forma;
 * o método é derivado (não existe "misto" para escolher). Validar só libera
 * quando a soma cobre o total.
 */
export function usePosTenders(options: {
  /** As linhas. Getter porque quem usa pode TROCAR o array (`cart.paymentTenders = []`). */
  tenders: () => POSPaymentTenderDraft[];
  /** O total que a conta usa (pode ser o interino: ver `totalStatus`). */
  totalQ: () => number;
  /** De quem é o total agora. Sem `confirmed`, nenhuma linha nasce do tamanho dele. */
  totalStatus: () => "confirmed" | "calculating" | "failed";
  /** O que dizer quando o operador toca numa forma antes de o total chegar. */
  totalPendingMessage: () => string;
  /** Onde o dinheiro é recebido: cada linha nasce com ele. */
  collection: () => PosPaymentCollection;
}) {
  const paymentTotalQ = computed(() => options.totalQ());
  const paymentRemainingQ = computed(() => computeRemainingQ(options.tenders(), paymentTotalQ.value));
  const paymentChangeQ = computed(() => computeChangeQ(options.tenders(), paymentTotalQ.value));
  const paymentCovered = computed(() => isPaymentCovered(options.tenders(), paymentTotalQ.value));

  // Odoo-style payment: tapping a method adds a tender for the remaining due
  // (the first one = the total). The numpad then edits the SELECTED line.
  const selectedTenderIndex = ref(-1);
  // In-progress decimal entry (Odoo): digits build the integer REAIS first, the
  // comma switches to centavos (max 2 places). So "2","5" → R$25,00 and only
  // "2","5",",","5" → R$25,50 — far less error-prone than cents-first (where 25
  // would mean R$0,25). null = no keyed entry yet; the first digit/comma starts a
  // fresh entry (so it replaces the shown amount, then appends).
  const tenderEntry = ref<string | null>(null);
  function entryToQ(entry: string): number {
    const n = Number.parseFloat((entry || "0").replace(",", "."));
    if (!Number.isFinite(n) || n < 0) return 0;
    return Math.min(99_999_999, Math.round(n * 100));
  }
  // Virginity is PER-TENDER (the `_virgin` flag on the tender), NOT global: a
  // tender is virgin while its amount is still the untouched system auto-fill.
  // The first cédula on a virgin tender REPLACES it (the operator starts counting
  // the cash handed over); thereafter cédulas ACCUMULATE. Crucially, just
  // SELECTING a tender (tapping its line) must NOT change its virginity — only
  // editing the amount does. (`_virgin` is internal; stripped before the intent.)
  const selectedTender = () => options.tenders()[selectedTenderIndex.value];

  // DIVIDIR A CONTA — "somos três, cada um paga o seu".
  //
  // A divisão não cria três linhas de uma vez: ela muda o tamanho da PRÓXIMA.
  // Com "3 pessoas" ligado, tocar em Dinheiro lança um terço, tocar em Cartão
  // lança o segundo, e o terceiro fecha a conta. É o fluxo do Odoo (parcial
  // sucessivo) com a aritmética feita pela máquina — e compõe com tudo que já
  // existe: cada pessoa escolhe a SUA forma, o teclado edita qualquer linha, e
  // "Exato" continua fechando o resto.
  //
  // 0 = sem divisão (a próxima linha leva o restante inteiro, como sempre foi).
  const splitCount = ref(0);
  // ⚠️ PESSOAS, não linhas — e a diferença não é sutil.
  //
  // Isto já foi `tenders.length`, e quebrava na variação mais comum do balcão:
  // uma pessoa que paga "R$ 20 em dinheiro e o resto no cartão" gastava DOIS
  // slots. A tela pulava para "pessoa 3 de 3", o operador lia o valor errado em
  // voz alta, e a terceira pessoa ficava sem ser cobrada. O caixa fechava (a
  // última parcela absorve o resto); os três clientes não.
  //
  // Quem conta é o gesto de cobrar a próxima pessoa, então o contador é
  // avançado só por `addTender` — a segunda forma da MESMA pessoa entra pelo
  // teclado ou pelas cédulas, que não mexem aqui.
  const splitPaidCount = ref(0);
  const splitNextShareQ = computed(() => splitShareQ(
    paymentTotalQ.value,
    splitCount.value,
    splitPaidCount.value,
    paymentRemainingQ.value,
  ));
  // A parte de cada pessoa é fração do total: sem total confirmado, não há parte.
  const splitNote = computed(() => options.totalStatus() !== "confirmed" ? "" : splitHint(
    paymentTotalQ.value,
    splitCount.value,
    splitPaidCount.value,
    paymentRemainingQ.value,
  ));
  function setSplitCount(count: number) {
    // Tocar de novo no mesmo número DESLIGA. Um botão que só liga obriga o
    // operador a caçar um "cancelar" quando o cliente muda de ideia — e mudar de
    // ideia sobre dividir a conta é rotina.
    splitCount.value = splitCount.value === count ? 0 : Math.max(0, count);
    // Trocar o número de pessoas recomeça a contagem: "na verdade somos quatro"
    // é dito ANTES de alguém pagar, e herdar a contagem antiga faria a próxima
    // parcela sair do lugar errado da fila.
    splitPaidCount.value = 0;
    // A forma que o sistema lançou com o total inteiro, sem ninguém tocar, é
    // rascunho: vira a parte da PRIMEIRA pessoa, como as prévias do modal
    // prometeram (beta test de 05/11/2026: o modal oferecia "R$ 0,00").
    const draft = options.totalStatus() === "confirmed"
      ? splitDraftTender(options.tenders(), paymentTotalQ.value)
      : null;
    if (draft && splitCount.value > 0) {
      draft.amount_q = splitShareQ(paymentTotalQ.value, splitCount.value, 0, paymentTotalQ.value);
      splitPaidCount.value = 1;
      tenderEntry.value = null;
    }
  }
  /** Sem divisão, e a contagem zerada (a conta acabou, ou a tela saiu de cena). */
  function resetSplit() {
    splitCount.value = 0;
    splitPaidCount.value = 0;
  }
  /** Uma pessoa a menos na fila — some junto com a linha que ela pagou. */
  function splitUnwind() {
    splitPaidCount.value = Math.max(0, splitPaidCount.value - 1);
  }

  function addTender(method: string) {
    // A linha nasce do tamanho do total: sem total confirmado, ela nasceria do
    // interino e ninguém a redimensionaria depois. A tela já trava os botões;
    // esta é a mesma porta para qualquer outro caminho (tecla, folha da mesa).
    if (options.totalStatus() !== "confirmed") {
      toast.info(options.totalPendingMessage());
      return;
    }
    const amountQ = Math.max(0, splitNextShareQ.value);
    if (amountQ <= 0) {
      // Tocar num método com o total já coberto era silêncio absoluto — o
      // operador tocava de novo achando que o botão quebrou. Diz o porquê e o
      // próximo passo.
      toast.info("Total já coberto. Remova uma forma para trocar.");
      return;
    }
    const tenders = options.tenders();
    tenders.push({ method, amount_q: amountQ, collection: options.collection(), _virgin: true });
    selectedTenderIndex.value = tenders.length - 1;
    tenderEntry.value = null;
    // Uma pessoa a mais atendida — só aqui, que é o gesto de cobrar a PRÓXIMA.
    if (splitCount.value > 0) splitPaidCount.value += 1;
  }

  // A cash bill with no tender yet opens a cash line at that bill's value — the
  // operator already started counting, so it's NOT virgin (next bill accumulates).
  function addCashTender(amountQ: number) {
    if (!amountQ || amountQ <= 0) return;
    const tenders = options.tenders();
    tenders.push({ method: "cash", amount_q: amountQ, collection: options.collection(), _virgin: false });
    selectedTenderIndex.value = tenders.length - 1;
    tenderEntry.value = null;
  }

  function removeTender(index: number) {
    const tenders = options.tenders();
    tenders.splice(index, 1);
    splitUnwind();
    if (selectedTenderIndex.value >= tenders.length) {
      selectedTenderIndex.value = tenders.length - 1;
    }
    tenderEntry.value = null;
  }

  /** Nenhuma linha selecionada, nenhum valor sendo digitado (a conta recomeça). */
  function clearSelection() {
    selectedTenderIndex.value = -1;
    tenderEntry.value = null;
  }

  /**
   * O gesto "Recebi o Pix" da venda mista (P1-7): o operador conferiu que o Pix
   * entrou. Marca as linhas de Pix logo antes de validar; o servidor recusa o
   * Pix misto sem a marca (`pix_mixed_unconfirmed`) e carimba quem e quando.
   */
  function confirmPixTenders() {
    for (const tender of options.tenders()) {
      if (tender.method === "pix") tender.pix_confirmed = true;
    }
  }

  function selectTender(index: number) {
    selectedTenderIndex.value = index;
    tenderEntry.value = null; // typing on it starts fresh; its _virgin is untouched
  }

  // A digit grows the decimal entry (reais first; ≤2 places after the comma).
  function tenderDigit(digit: string) {
    const tender = selectedTender();
    if (!tender) return;
    let entry = tenderEntry.value ?? "";
    if (entry.includes(",")) {
      if ((entry.split(",")[1] ?? "").length >= 2) return; // centavos full
    } else if (entry.replace(/^0+/, "").length >= 7) {
      return; // keep the integer part sane
    }
    entry += digit;
    tenderEntry.value = entry;
    tender._virgin = false;
    tender.amount_q = entryToQ(entry);
  }
  // The comma key (USD would be a dot): switch to centavos.
  function tenderComma() {
    const tender = selectedTender();
    if (!tender) return;
    let entry = tenderEntry.value ?? "";
    if (entry === "") entry = "0";
    if (!entry.includes(",")) entry += ",";
    tenderEntry.value = entry;
    tender._virgin = false;
    tender.amount_q = entryToQ(entry);
  }
  function tenderBackspace() {
    const tender = selectedTender();
    if (!tender) return;
    // First backspace over an auto amount clears it (Odoo), then trims the entry.
    const entry = (tenderEntry.value ?? "").slice(0, -1);
    tenderEntry.value = entry;
    tender._virgin = false;
    tender.amount_q = entryToQ(entry);
  }
  function tenderClear() {
    const tender = selectedTender();
    if (!tender) return;
    tenderEntry.value = "";
    tender._virgin = false;
    tender.amount_q = 0;
  }
  // A cédula tap reflects a note the customer handed over. On a VIRGIN tender the
  // first tap REPLACES the auto value (start counting the cash handed: total
  // R$66,30 → +R$50 = R$50,00, restante; +R$50 = R$100,00, troco R$33,70).
  // Thereafter it ACCUMULATES. No tender yet → opens a cash line at that note.
  function tenderAdd(cents: number) {
    if (!cents) return;
    const tender = selectedTender();
    if (!tender) {
      addCashTender(cents);
      return;
    }
    const base = tender._virgin ? 0 : tender.amount_q;
    tender.amount_q = Math.min(99_999_999, base + cents);
    tender._virgin = false;
    tenderEntry.value = null;
  }

  // "Exato": set the selected tender to settle exactly what the OTHER tenders
  // still leave owed (so the sale is covered, change zero). Snaps a split line
  // back to the remainder after typing a partial amount.
  function tenderExact() {
    const tenders = options.tenders();
    const tender = tenders[selectedTenderIndex.value];
    if (!tender) return;
    if (options.totalStatus() !== "confirmed") {
      toast.info(options.totalPendingMessage());
      return;
    }
    const others = tenders.reduce(
      (sum, line, idx) => (idx === selectedTenderIndex.value ? sum : sum + line.amount_q),
      0,
    );
    tender.amount_q = Math.max(0, paymentTotalQ.value - others);
    tender._virgin = true; // a system value again: a following cédula replaces it
    tenderEntry.value = null;
  }

  // The method of the line the instrument (numpad/cédulas) is editing, or "" when
  // none is selected — drives whether the cash cédulas are offered.
  const selectedTenderMethod = computed(
    () => options.tenders()[selectedTenderIndex.value]?.method || "",
  );

  return {
    paymentTotalQ,
    paymentRemainingQ,
    paymentChangeQ,
    paymentCovered,
    selectedTenderIndex,
    selectedTenderMethod,
    splitCount,
    splitPaidCount,
    splitNextShareQ,
    splitNote,
    setSplitCount,
    resetSplit,
    addTender,
    addCashTender,
    removeTender,
    clearSelection,
    confirmPixTenders,
    selectTender,
    tenderDigit,
    tenderComma,
    tenderBackspace,
    tenderClear,
    tenderAdd,
    tenderExact,
  };
}
