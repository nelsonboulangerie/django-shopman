<script setup lang="ts">
// Payment screen (spec §2.4) — "Conta + Instrumento". Two stable zones, no modes
// that pop in and out:
//   LEFT  (a Conta)       — the charge: the sale total as a stable hero (never
//                           collapses to zero) + one adaptive live readout
//                           (Faltam → Troco → Pronto) + the tender lines, which
//                           accumulate and are editable. Split lives here.
//   RIGHT (o Instrumento) — always present: the method tiles (tap = lança o que
//                           falta na forma) + a persistent numpad that edits the
//                           SELECTED tender + cash cédulas as the cash nuance.
//
// The numpad is universal (every tender, not just cash) — which is exactly what
// split payment needs. Zero arithmetic of policy: total/remaining/change/coverage
// come from the composable (authoritative review via `presentation/payment`).
// This screen renders intent; it does not compute.
import type {
  POSAddressAutocompleteProjection,
  POSCartItem,
  POSCheckoutContractProjection,
  POSCheckoutOptionProjection,
  POSCustomerLookupProjection,
  POSCustomerSearchResult,
  POSFulfillmentOptionProjection,
  POSManagerProjection,
  POSPaymentCollectionProjection,
  POSPaymentMethodProjection,
  POSPaymentTenderDraft,
  POSSaleReviewProjection,
  SavedAddressProjection,
  StructuredAddressProjection,
} from "~/types/pos";
import { formatBRL, moneyInputToQ } from "~/utils/posIntent";
import {
  cashNotesQ as contractCashNotesQ,
  changeForShortfallQ,
  collectionsForFulfillment,
  injectableMethods as toInjectableMethods,
  methodShortcuts,
  nonCashExcessQ,
  paymentIcon,
  SPLIT_PRESETS,
  tenderLineView,
} from "~/presentation/payment";
import {
  lineDiscountBadge,
  lineListTotalDisplay,
  lineSavingsQ,
  lineTotalQ,
} from "~/presentation/lineDiscounts";
import { isScheduled, scheduleLabel, windowLabel } from "~/presentation/schedule";

const props = defineProps<{
  tabDisplay: string;
  items: POSCartItem[];
  hasOpenTab: boolean;
  fulfillmentOptions: POSFulfillmentOptionProjection[];
  paymentMethods: POSPaymentMethodProjection[];
  paymentCollections: POSPaymentCollectionProjection[];
  checkoutContract: POSCheckoutContractProjection | null;
  addressAutocomplete: POSAddressAutocompleteProjection | null;
  customerLookup: POSCustomerLookupProjection | null;
  searchResults: POSCustomerSearchResult[];
  searchBusy: boolean;
  /** O cliente associado foi criado agora (resolve just-in-time). */
  customerResolvedNew?: boolean;
  review: POSSaleReviewProjection | null;
  discountTypes: POSCheckoutOptionProjection[];
  discountReasons: POSCheckoutOptionProjection[];
  discountType: "percent" | "fixed";
  discountValue: string;
  discountReason: string;
  managerUsername: string;
  managerPin: string;
  managerApprovalError: string;
  /** Quem pode assinar a exceção. Vazio = o diálogo cai no campo livre. */
  managers: POSManagerProjection[];
  /** Quem CONTINUA operando depois da assinatura do gerente. Ver PosManagerAuthDialog. */
  operatorName?: string;
  fulfillmentType: "pickup" | "delivery";
  paymentCollection: "terminal" | "on_delivery";
  paymentTenders: POSPaymentTenderDraft[];
  /** Em quantas pessoas a conta está dividida (0 = sem divisão). */
  splitCount: number;
  /** "R$ 33,15 · pessoa 1 de 3" — quanto pedir a quem está na frente. */
  splitNote: string;
  selectedTenderIndex: number;
  selectedTenderMethod: string;
  /** Total a cobrar (review viva → total retido → estimativa líquida local). */
  paymentTotalQ: number;
  paymentRemainingQ: number;
  paymentChangeQ: number;
  paymentCovered: boolean;
  customerName: string;
  customerPhone: string;
  customerTaxId: string;
  /** O CPF PEDIDO para a nota desta venda (o cadastro empresta o inicial). */
  invoiceTaxId: string;
  wantsCpfOnInvoice: boolean;
  customerEmail: string;
  deliveryAddress: string;
  deliveryAddressStructured: StructuredAddressProjection;
  deliveryStreetNumber: string;
  deliveryNeighborhood: string;
  deliveryComplement: string;
  deliveryInstructions: string;
  deliveryDate: string;
  deliveryTimeSlot: string;
  /** A exceção da taxa, quando o operador a assume (ligada por `deliveryFeeOverride`). */
  deliveryFeeOverrideInput: string;
  deliveryFeeOverride: boolean;
  /** A taxa RESOLVIDA pelo servidor, e de onde ela veio. A tela mostra; não decide. */
  deliveryFeeQ: number;
  deliveryFeeSource: string;
  deliveryDistanceKm: number | null;
  /** Janelas do dia escolhido, já anotadas com a prontidão do carrinho. */
  deliverySlots: Array<{ ref: string; label: string; enabled?: boolean; reason?: string }>;
  /** Ainda não há resposta sobre as janelas (a review está a caminho). */
  deliverySlotsPending: boolean;
  /** A data que vale — a escolhida, ou o hoje que o servidor devolveu. */
  deliveryDateEffective: string;
  /** O hoje da LOJA, e as datas que ela realmente opera. */
  scheduleToday: string;
  scheduleAvailableDates: string[];
  /** O item que segura o pedido, e a que horas ele libera. */
  scheduleBottleneckName: string;
  scheduleReadyAt: string;
  /** A busca das janelas falhou — terceiro estado, não é "carregando". */
  scheduleFailed: boolean;
  /** Última data encomendável (Admin: `max_preorder_days`). */
  scheduleMaxDate: string;
  /** "Troco para quanto?" do dinheiro na entrega (entrada livre em reais). */
  changeForInput: string;
  orderNotes: string;
  receiptChannels: string[];
  receiptEmail: string;
  loading: boolean;
  lookupBusy: boolean;
}>();

const emit = defineEmits<{
  "update:discountType": ["percent" | "fixed"];
  "update:discountValue": [string];
  "update:discountReason": [string];
  "update:managerUsername": [string];
  "update:managerPin": [string];
  "update:fulfillmentType": ["pickup" | "delivery"];
  "update:paymentCollection": ["terminal" | "on_delivery"];
  addTender: [string];
  removeTender: [number];
  setSplitCount: [number];
  selectTender: [number];
  /** Numpad edits the SELECTED tender; decimal entry (reais first, comma → centavos). */
  tenderDigit: [string];
  tenderComma: [];
  tenderBackspace: [];
  tenderClear: [];
  tenderAdd: [number];
  tenderExact: [];
  "update:customerName": [string];
  "update:customerPhone": [string];
  "update:customerTaxId": [string];
  "update:invoiceTaxId": [string];
  "update:wantsCpfOnInvoice": [boolean];
  "update:customerEmail": [string];
  "update:deliveryAddress": [string];
  "update:deliveryAddressStructured": [StructuredAddressProjection];
  "update:deliveryStreetNumber": [string];
  "update:deliveryNeighborhood": [string];
  "update:deliveryComplement": [string];
  "update:deliveryInstructions": [string];
  "update:deliveryDate": [string];
  "update:deliveryTimeSlot": [string];
  "update:deliveryFeeOverrideInput": [string];
  "update:deliveryFeeOverride": [boolean];
  "update:changeForInput": [string];
  "update:orderNotes": [string];
  "update:receiptChannels": [string[]];
  "update:receiptEmail": [string];
  back: [];
  submit: [];
  lookupCustomer: [];
  resolveCustomer: [];
  clearCustomer: [];
  search: [string];
  selectResult: [POSCustomerSearchResult];
  applyCustomerFavorite: [];
  repeatCustomerLastOrder: [];
  pickSavedAddress: [SavedAddressProjection];
}>();

// Total interino enquanto a review não chega: o MESMO `paymentTotalQ` do
// composable (líquido, com o último total de review retido) — nunca o bruto do
// carrinho, que fazia o hero saltar durante o debounce da review.
const interimTotalDisplay = computed(() => formatBRL(props.paymentTotalQ));
// Nota fiscal é SECUNDÁRIA: mora no modal do Cliente (não é botãozão no grid) e só
// aparece quando a loja ofereceu NFC-e no PDV E o adapter fiscal está configurado.
const supportsFiscalDocument = computed(() => !!props.checkoutContract?.capabilities?.supports_fiscal_document);
const receiptChannelOptions = computed(() => props.checkoutContract?.receipt_channels || [
  { ref: "print", label: "Imprimir", description: "" },
  { ref: "email", label: "E-mail", description: "" },
]);
const savedAddresses = computed(() => props.customerLookup?.saved_addresses || []);
const needsReview = computed(() => !props.review);
const approvalBlocking = computed(() =>
  !!props.review?.requires_manager_approval
  && (!props.managerUsername.trim() || !props.managerPin.trim()),
);
const managerThresholdQ = computed(() => props.review?.manager_approval_threshold_q || 0);
// Avisos não-bloqueantes da review (disponibilidade no balcão, pagamento): o
// operador VÊ a ressalva antes de finalizar; nunca bloqueiam a venda.
// O aviso "valor recebido em dinheiro não informado" NÃO cabe nesta tela.
// Ele nasce de uma review tirada antes de existir qualquer forma de pagamento
// (sem tender o servidor assume `cash`), e a review só é refeita quando o
// CARRINHO muda — mexer nas linhas de pagamento não a renova. Resultado: a
// frase ficava congelada ao lado de um "TROCO R$ 30,00" vivo, dizendo que o
// fechamento assumiria valor exato. E em pagamento misto era pior, porque não
// havia gesto capaz de calá-la. Quem responde "quanto entrou na mão" aqui é a
// linha de dinheiro, e quanto volta está no RESTANTE/TROCO logo abaixo — este
// aviso só teria dono numa superfície sem tenders. O contrato do servidor fica
// como está (outros consumidores da review continuam recebendo o código).
// Excedente em cartão/Pix é erro de digitação, e o operador precisa vê-lo NA HORA
// em que digita — a review só é refeita quando o carrinho muda, então o aviso do
// servidor chegaria tarde. Mesma conta dos dois lados (`nonCashExcessQ`), sobre
// o `paymentTotalQ` (com a review em trânsito, o total 0 fazia toda linha
// digital virar "excedente" por meio segundo).
const nonCashExcess = computed(() => nonCashExcessQ(props.paymentTenders, props.paymentTotalQ));
const reviewWarnings = computed(() => {
  const fromServer = (props.review?.warnings ?? []).filter(
    (w) => w.code !== "cash_tendered_amount_blank" && w.code !== "tender_overpaid_non_cash",
  );
  if (nonCashExcess.value <= 0) return fromServer;
  return [
    {
      code: "tender_overpaid_non_cash",
      field: "payment_tenders",
      message: `Pagamento sem dinheiro acima do total em ${formatBRL(nonCashExcess.value)}. Não há troco para cartão ou Pix; ajuste o valor da linha.`,
    },
    ...fromServer,
  ];
});

// On-demand sale-data drawers (Odoo-style: customer/fulfillment/discount are
// actions that open a sheet, not a wall of fields next to the payment).
const fulfillmentSheetOpen = ref(false);
const customerSheetOpen = ref(false);
function onSelectResult(result: POSCustomerSearchResult) {
  emit("selectResult", result);
}
// Reset the shared search when the customer modal reopens fresh — e devolve o
// foco ao botão que o abriu (diálogo controlado: sem isto o foco morre no body).
// O botão do Cliente existe em DOIS lugares que nunca aparecem juntos (o chip,
// abaixo de `xl`; a coluna de contexto, a partir dele), então o foco não pode
// morar num `ref` fixo: devolvê-lo ao botão escondido é o mesmo que perdê-lo no
// body. Procura-se o que está visível na hora.
function focusCustomerControl() {
  const candidates = Array.from(
    document.querySelectorAll<HTMLButtonElement>('[data-context-entry="customer"]'),
  );
  (candidates.find((el) => el.offsetParent !== null) || candidates[0])?.focus();
}
watch(customerSheetOpen, async (open) => {
  if (open) return;
  emit("search", "");
  if (!import.meta.client) return;
  await nextTick();
  focusCustomerControl();
});
const scheduleSheetOpen = ref(false);
// O resumo do "quando" para o atalho dentro do Recebimento se explicar sozinho.
const scheduleChipLabel = computed(() => scheduleLabel(
  props.deliveryDate,
  windowLabel(props.deliverySlots, props.deliveryTimeSlot),
  props.scheduleToday,
));
const discountSheetOpen = ref(false);

// Foco automático no modal de Recebimento: com entrega selecionada, quem recebe
// o foco é a busca de endereço (o campo que o operador veio preencher) — tanto
// na abertura do modal quanto ao alternar retirada→entrega com ele aberto.

// The instrument (right zone): the numpad edits the SELECTED tender, so it lights
// up once a tender exists; cédulas are the cash nuance, offered only when the
// selected tender is cash. BR notes (2/5/10/20/50/100) — the first tap after
// selecting a tender SETS (the customer handed R$50), then accumulates.
const digitKeys = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
// Cédulas que o cliente entrega — vêm do CONTRATO (cash_tender_delta_presets_q),
// com as notas BR como fallback; cada toque SOMA na linha de dinheiro
// selecionada (o primeiro toque sobre valor automático substitui).
const cashNotesQ = computed(() => contractCashNotesQ(props.checkoutContract));
const cashSelected = computed(() => props.selectedTenderMethod === "cash");

// De onde a taxa saiu, em português de balcão. Quem cobra é a loja; a frase
// existe para o operador saber DIZER isso ao cliente, em vez de repetir um
// número que ele não sabe justificar.
// "Sem janela neste dia" é um FATO; "ainda não sei" é outra coisa. Dizer o
// primeiro enquanto a resposta não chegou fazia a tela mentir para o operador
// justo no formulário que ele acabara de abrir.
// O CPF de volta na tela, formatado e por INTEIRO. Mostrar só o rabo do número
// não responde a pergunta que o cliente faz — ele quer saber se o documento DELE
// entrou. Quem digitou está com o cliente na frente; esconder metade não protege
// ninguém e deixa os dois no escuro.
// O documento se lê pontuado enquanto se digita — é assim que a pessoa CONFERE
// o próprio CPF, em blocos de três. Cru, "52998224725" obriga a contar dígito a
// dígito, e ninguém confere o que não consegue ler.
// O teclado só vale quando há uma linha de pagamento selecionada para editar.
const numpadActive = computed(() => props.selectedTenderIndex >= 0 && props.selectedTenderIndex < props.paymentTenders.length);

const invoiceTaxIdMasked = computed(() => {
  const d = props.invoiceTaxId.replace(/\D/g, "").slice(0, 14);
  if (d.length <= 11) {
    return d
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/^(\d{3})\.(\d{3})\.(\d{3})(\d)/, "$1.$2.$3-$4");
  }
  return d
    .replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/^(\d{2})\.(\d{3})\.(\d{3})(\d)/, "$1.$2.$3/$4")
    .replace(/^(\d{2})\.(\d{3})\.(\d{3})\/(\d{4})(\d)/, "$1.$2.$3/$4-$5");
});

const taxIdEcho = computed<{ ok: boolean; text: string }>(() => {
  const digits = props.invoiceTaxId.replace(/\D/g, "");
  if (digits.length === 11) {
    return { ok: true, text: `Sai na nota: CPF ${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}` };
  }
  if (digits.length === 14) {
    return { ok: true, text: `Sai na nota: CNPJ ${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}` };
  }
  if (!digits) return { ok: false, text: "Digite o documento — sem ele a nota sai sem CPF." };
  return { ok: false, text: "Documento incompleto — a nota sai sem CPF." };
});

// "Do cadastro" só se o valor ainda É o do cadastro: assim que o operador troca,
// o aviso some, porque aí não é mais o documento do cliente que está ali.
const digitsOf = (value: string) => value.replace(/\D/g, "");
const taxIdIsFromCadastro = computed(
  () => !!props.customerLookup?.tax_id && digitsOf(props.invoiceTaxId) === digitsOf(props.customerLookup.tax_id),
);
const emailIsFromCadastro = computed(
  () => !!props.customerEmail.trim() && props.receiptEmail.trim().toLowerCase() === props.customerEmail.trim().toLowerCase(),
);

// Os canais do comprovante são uma LISTA no contrato; na tela são dois switches.
// Um estado, duas leituras — nada de segundo lugar guardando a mesma verdade.
const wantsEmailReceipt = computed(() => props.receiptChannels.includes("email"));
const wantsPrintedReceipt = computed(() => props.receiptChannels.includes("print"));
function setReceiptChannel(ref: string, on: boolean) {
  const next = on
    ? (props.receiptChannels.includes(ref) ? props.receiptChannels : [...props.receiptChannels, ref])
    : props.receiptChannels.filter((c) => c !== ref);
  emit("update:receiptChannels", next);
}

// The adaptive live readout under the hero — one line that carries the state the
// operator needs right now, so the big number stays the (stable) sale total.
const payState = computed<"idle" | "short" | "change" | "ready">(() => {
  if (props.paymentChangeQ > 0) return "change";
  if (props.paymentCovered) return "ready";
  if (props.paymentTenders.length) return "short";
  return "idle";
});

const discountValueNum = computed(
  () => Number(String(props.discountValue).replace(",", ".").replace(/[^0-9.]/g, "")) || 0,
);
const hasDiscount = computed(() => discountValueNum.value > 0);
const discountSummary = computed(() =>
  props.discountType === "fixed" ? `R$ ${props.discountValue}` : `${props.discountValue}%`,
);

// O RESUMO DO PEDIDO — o que está sendo cobrado. No checkout o operador via só
// o total: um número sem os itens que o compõem, justo na hora em que o cliente
// pergunta "por que deu isso?". Vem do mesmo carrinho da tela de venda; a tela
// mostra, não recalcula.
const summaryLines = computed(() =>
  props.items.map((item) => ({
    sku: item.sku,
    name: item.name,
    qty: item.qty,
    totalDisplay: formatBRL(lineTotalQ(item)),
    /** A etiqueta riscada, quando o que se cobra é menor. "" quando não há. */
    listDisplay: lineListTotalDisplay(item),
    /** POR QUE está mais barato — o desconto que venceu a linha. */
    discountLabel: lineDiscountBadge(item, props.discountReasons),
  })),
);
const summaryUnits = computed(() => props.items.reduce((sum, item) => sum + item.qty, 0));
/** Quanto a venda inteira economizou em relação à etiqueta. 0 quando nada. */
const summarySavingsQ = computed(() => props.items.reduce((sum, item) => sum + lineSavingsQ(item), 0));

// Kitchen clarity: tell the operator, unequivocally, what finalizing will do
// vs what was already fired — so it's never a mystery whether food was sent.
const firedCount = computed(() => props.items.filter((item) => item.fired).length);
const kitchenNote = computed(() => {
  const total = props.items.length;
  if (!total) return "";
  const fired = firedCount.value;
  if (fired === 0) return `Ao finalizar, ${total === 1 ? "o item vai" : "os itens vão"} para a cozinha.`;
  if (fired < total) return `${fired} ${fired === 1 ? "item já está" : "itens já estão"} na cozinha; o restante vai ao finalizar.`;
  return total === 1 ? "O item já está na cozinha." : "Todos os itens já estão na cozinha.";
});

// Payment by injection: methods become "add a tender" buttons; the operator
// covers the total in any combination of forms. No "mixed" selection.
const injectableMethods = computed(() =>
  toInjectableMethods(props.paymentMethods, { houseAccount: Boolean(props.customerLookup?.house_account) }),
);
// D/P/C — a tecla de cada forma, derivada do rótulo do contrato. Escolher a
// forma é o gesto de TODA venda; era o único do checkout que exigia o mouse.
const methodKeys = computed(() => methodShortcuts(injectableMethods.value));
const tenderLines = computed(() => props.paymentTenders.map((tender) => tenderLineView(tender, injectableMethods.value)));
const deliveryCollections = computed(() => collectionsForFulfillment(props.paymentCollections, props.fulfillmentType));

// "Troco para quanto?" só existe no dinheiro NA ENTREGA. O aviso (< total) é o
// mesmo da review do servidor; aqui aparece NA DIGITAÇÃO, sem esperar round-trip.
const onDeliveryCash = computed(
  () => props.fulfillmentType === "delivery" && props.paymentCollection === "on_delivery",
);
const changeForShortfall = computed(() =>
  onDeliveryCash.value
    ? changeForShortfallQ(moneyInputToQ(props.changeForInput), props.paymentTotalQ)
    : 0,
);

// Validar (Odoo's Validate): NO "pay it all" shortcut — the button stays disabled
// until a payment form is consciously chosen and covers the total. This prevents
// the impulse to finalize a sale without paying attention to the method.
// Validar: enabled once a form covers the total. When the review demands manager
// approval and it isn't given yet, the click opens the authorization dialog
// (instead of disabling the button with a cramped inline field).
const needsAuth = computed(() => approvalBlocking.value);
const managerAuthOpen = ref(false);
// Servidor recusou o PIN → reabre o diálogo com a mensagem (o dialog limpa o PIN
// no seu próprio watch de `error`). Sem isto, o operador fica sem caminho.
watch(() => props.managerApprovalError, (message) => {
  if (message) managerAuthOpen.value = true;
});
const ctaLabel = computed(() => {
  if (needsReview.value) return "Atualizando…";
  return needsAuth.value ? "Autorizar e validar" : "Validar";
});
// Agendado sem cliente: o servidor recusa a encomenda anônima
// (`customer_required_for_scheduled`) — o botão trava ANTES, com o motivo.
const scheduledWithoutCustomer = computed(() =>
  isScheduled(props.deliveryDate, props.scheduleToday)
  && !props.customerName.trim()
  && !props.customerPhone.trim());
const ctaDisabled = computed(() => {
  if (!props.items.length || props.loading || needsReview.value) return true;
  if (scheduledWithoutCustomer.value) return true;
  if (!props.paymentCovered) return true; // só habilita quando uma forma cobre o total
  return false;
});
// O motivo, em palavras, do botão travado — na ordem em que o operador resolve.
const ctaBlockReason = computed(() => {
  if (!props.items.length) return "Adicione itens à comanda para cobrar.";
  if (props.loading || needsReview.value) return "";
  if (scheduledWithoutCustomer.value) return "Identifique o cliente para agendar — é o contato se algo mudar até a data.";
  if (!props.paymentTenders.length) return "Escolha a forma de pagamento.";
  if (!props.paymentCovered) return `Faltam ${formatBRL(Math.max(0, props.paymentRemainingQ))} para cobrir o total.`;
  return "";
});
// Motivo sem caminho é beco sem saída: quando o bloqueio se resolve numa tela
// que este componente sabe abrir, a frase vem com o botão que resolve — o
// operador nunca fica só lendo. (Formas de pagamento e itens já estão à mão
// na própria tela; por isso só o cliente ganha atalho aqui.)
const ctaBlockAction = computed(() => {
  if (!props.items.length || props.loading || needsReview.value) return null;
  if (scheduledWithoutCustomer.value) {
    return { label: "Identificar cliente", run: () => { customerSheetOpen.value = true; } };
  }
  return null;
});
function onCta() {
  if (needsAuth.value) { managerAuthOpen.value = true; return; }
  emit("submit");
}
function onManagerAuthorize(username: string, pin: string) {
  emit("update:managerUsername", username);
  emit("update:managerPin", pin);
  managerAuthOpen.value = false;
  emit("submit");
}

// Atalhos do shell (pages/index.vue): Enter valida pelo MESMO caminho do clique
// (passa pela porta da autorização gerencial, nunca por fora dela); F6 abre o
// modal de cliente deste checkout.
// A BARRA DE CONTEXTO (topo, em `pages/index.vue`) é quem abre estes três agora.
// Eles saíram da coluna de trabalho porque não são instrumento: quem compra,
// como recebe e se tem desconto são fatos da VENDA, decididos antes, revisados
// de relance. Ficavam aqui empurrando a Nota fiscal para baixo da dobra — as
// perguntas que se faz com o cliente na frente. Os diálogos continuam morando
// neste componente (é ele que tem o estado); só o gatilho subiu.
defineExpose({
  validate: () => { if (!ctaDisabled.value) onCta(); },
  openCustomer: () => { customerSheetOpen.value = true; },
  openFulfillment: () => { fulfillmentSheetOpen.value = true; },
  openSchedule: () => { scheduleSheetOpen.value = true; },
  openDiscount: () => { discountSheetOpen.value = true; },
  /** Uma letra digitada no checkout lança a forma correspondente. Devolve se
   *  achou dono — o shell só consome a tecla quando ela virou ação. */
  /** F9 liga/desliga "CPF na nota?" — a pergunta fiscal mais feita no balcão. */
  toggleCpfOnInvoice: () => { emit("update:wantsCpfOnInvoice", !props.wantsCpfOnInvoice); },
  pressMethodKey: (letter: string) => {
    const ref = Object.keys(methodKeys.value).find((key) => methodKeys.value[key] === letter);
    if (!ref) return false;
    emit("addTender", ref);
    return true;
  },
});
</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-3">
    <!-- Payment screen (desktop-first, base Odoo POS). Coluna de TRABALHO à
         ESQUERDA em três seções nomeadas — Venda (cliente, desconto),
         Recebimento (retirada/entrega, onde recebe, troco da porta) e
         Pagamento (métodos + numpad com cédulas), com Voltar/Validar no rodapé;
         VALOR gigante à DIREITA (total estável, centrado) + linhas de pagamento
         + troco/restante. -->



    <!-- MAIN — clone Odoo: INSTRUMENTO esquerda, VALOR no meio, CONTEXTO direita.
         As colunas laterais têm LARGURA FIXA de 360px, a mesma do painel do
         carrinho na tela de venda (`md:w-[360px]` em pages/index.vue): a coluna
         de trabalho era uma fração do grid e dava 435px, um instrumento mais
         largo aqui do que lá, com a mesma mão fazendo as duas coisas. Largura
         fixa também é o que faz o teclado não mudar de tamanho conforme a
         janela — músculo de balcão depende de a tecla estar sempre no mesmo
         lugar. O VALOR fica com o resto, que é o que deve respirar.

         A terceira coluna aparece a partir de `lg` e carrega o RESUMO DO PEDIDO.
         Ela ficava em `xl`, e abaixo de 1280px o resumo SUMIA — justo a coluna
         que existe para dizer o que está sendo cobrado. Quem encolhe agora é o
         número do meio, que é grande por ênfase e não por necessidade: ele
         também aparece nas linhas de pagamento e no botão de validar.
         Cliente e recebimento saíram daqui: são fatos do PEDIDO, decididos na
         abertura do atendimento, e agora moram na barra do topo, que segue
         visível durante o checkout. Perguntar de novo aqui era ter o mesmo botão
         em dois lugares da mesma tela. -->
    <div class="flex min-h-0 w-full flex-1 flex-col gap-6 overflow-hidden md:flex-row">

      <!-- LEFT · coluna de trabalho, agrupada por SEMÂNTICA (Hyper Focus: chrome
           espalhado não responde "qual é a próxima ação"). Quatro seções, na
           ORDEM DA CONVERSA do balcão: VENDA (quem compra e a que preço),
           RECEBIMENTO (retirada/entrega, onde se recebe, troco da porta),
           PAGAMENTO (métodos + teclado) e NOTA E COMPROVANTE — que é a última
           pergunta que o operador faz, e por isso a última seção, colada no
           Validar. Botões do mesmo grupo têm o mesmo peso.
           `overflow-y-auto`: com a nota aberta a coluna pode passar da altura
           da tela num monitor baixo, e conteúdo cortado sem rolagem é conteúdo
           inalcançável. -->
      <div class="order-2 flex min-h-0 flex-col gap-3 overflow-y-auto md:order-none md:w-[360px] md:shrink-0">
        <!-- PAGAMENTO — o instrumento: métodos (tap = lança o que falta na forma)
             + teclado de valor. Última seção de propósito: desagua no Validar. -->
        <!-- CONTEXTO DA VENDA — quem compra, como recebe, se tem desconto.
             UMA LINHA de chips, não duas seções com cabeçalho. Os três são
             fatos decididos antes e revisados de relance; ocupavam 132px no topo
             da coluna em TODA venda, sendo que a esmagadora maioria é sem
             cliente, sem desconto e retirada — e empurravam a Nota fiscal para
             baixo da dobra, justo as perguntas que se faz com o cliente na
             frente. Aqui custam 36px e continuam mostrando o ESTADO: ver que é
             entrega não exige abrir nada. -->
        <section class="mt-auto grid gap-1.5" aria-label="Forma de pagamento">
          <h3 class="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Forma de pagamento</h3>

          <!-- DESCONTO — vizinho do pagamento, não do cliente. Ele é uma operação
               sobre o VALOR que está sendo cobrado, e é aqui que o gerente é
               chamado para autorizá-lo.
               Fica ACIMA das formas, e não colado no "Exato"/"Limpar": aqueles
               dois agem sobre a LINHA DE PAGAMENTO selecionada, e este age sobre
               a VENDA. Três botões lado a lado com dois sujeitos diferentes é o
               clique errado do balcão cheio. -->
          <button
            v-if="discountTypes.length"
            type="button"
            class="flex h-11 items-center gap-2 rounded-md border px-3 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            :class="hasDiscount ? 'border-primary bg-primary/5' : 'bg-card text-muted-foreground'"
            @click="discountSheetOpen = true"
          >
            <Icon name="lucide:tag" class="size-4 shrink-0" />
            <span class="min-w-0 truncate">{{ hasDiscount ? `Desconto no pedido ${discountSummary}` : "Desconto no pedido" }}</span>
            <kbd class="ml-auto shrink-0 rounded border bg-muted px-1 py-0.5 font-mono text-xs font-medium text-muted-foreground" aria-hidden="true">F8</kbd>
          </button>
          <!-- ONDE o dinheiro é recebido é FORMA DE PAGAMENTO, não contexto da
               venda: veio da seção "Recebimento", que subiu inteira para a barra
               de contexto. Só aparece quando há mais de uma opção. -->
          <div v-if="deliveryCollections.length > 1" class="grid grid-cols-2 gap-1.5">
            <button
              v-for="collection in deliveryCollections"
              :key="collection.ref"
              type="button"
              class="flex h-11 items-center justify-center gap-2 rounded-md border bg-card px-3 text-sm font-medium transition hover:bg-accent active:translate-y-px"
              :class="paymentCollection === collection.ref ? 'border-primary bg-primary/5' : ''"
              @click="$emit('update:paymentCollection', collection.ref)"
            >
              <span class="min-w-0 truncate">{{ collection.label }}</span>
            </button>
          </div>

          <!-- Dinheiro NA PORTA (COD). Chamava-se "Troco para quanto?" e confundia
               com o TROCO do numpad, ali embaixo — dois campos falando "troco" no
               mesmo checkout. São momentos diferentes: o do numpad é dinheiro que
               já está na mão AGORA; este é com quanto o cliente vai pagar DEPOIS,
               na porta, e por isso não há tender no terminal para calcular nada.
               O número também não é para a tela: `payment.change_for_q` vira
               `change_out_suggested_q` e depois a linha `courier_out` no livro do
               caixa — é assim que o entregador sai com troco separado e
               registrado. O rótulo agora diz o momento; a legenda, a consequência. -->
          <label v-if="onDeliveryCash" class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Com quanto vai pagar na porta?</span>
            <UiInput
              :model-value="changeForInput"
              inputmode="decimal"
              placeholder="Opcional"
              @update:model-value="$emit('update:changeForInput', String($event || ''))"
            />
            <span v-if="changeForShortfall > 0" class="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400">
              <Icon name="lucide:triangle-alert" class="size-3.5 shrink-0" />
              Menor que o total: faltam {{ formatBRL(changeForShortfall) }}.
            </span>
            <span v-else-if="changeForInput.trim()" class="px-1 text-xs text-muted-foreground">
              O entregador sai com o troco separado.
            </span>
          </label>

          <div class="flex flex-col gap-1.5">
            <button
              v-for="method in injectableMethods"
              :key="method.ref"
              type="button"
              class="flex h-11 items-center gap-3 rounded-md border bg-card px-3 text-left text-sm font-medium transition hover:border-primary/50 hover:bg-accent active:translate-y-px"
              :class="method.ref === selectedTenderMethod ? 'border-primary bg-primary/5' : ''"
              @click="$emit('addTender', method.ref)"
            >
              <Icon :name="paymentIcon(method.ref)" class="size-5 shrink-0 text-muted-foreground" />
              <span class="flex-1">{{ method.label }}</span>
              <kbd
                v-if="methodKeys[method.ref]"
                class="shrink-0 rounded border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-muted-foreground"
                aria-hidden="true"
              >{{ methodKeys[method.ref] }}</kbd>
            </button>
          </div>

          <!-- numpad (dígitos: entrada decimal, vírgula nos centavos) + trilho de
               cédulas à direita (só dinheiro: as 6 notas BR que o cliente entrega) -->
          <div class="flex gap-1.5">
          <div class="grid grid-cols-3 gap-1.5" :class="cashSelected ? 'flex-[3] basis-0' : 'flex-1'" role="group" aria-label="Teclado de valor">
            <button
              v-for="digit in digitKeys"
              :key="digit"
              type="button"
              class="grid place-items-center rounded-md border bg-card h-11 text-xl font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:opacity-40"
              :disabled="!numpadActive"
              :aria-label="`Dígito ${digit}`"
              @click="$emit('tenderDigit', digit)"
            >
              {{ digit }}
            </button>
            <button type="button" class="grid place-items-center rounded-md border bg-card h-11 text-xl font-semibold transition hover:bg-accent active:translate-y-px disabled:opacity-40" :disabled="!numpadActive" aria-label="Vírgula (centavos)" @click="$emit('tenderComma')">,</button>
            <button type="button" class="grid place-items-center rounded-md border bg-card h-11 text-xl font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:opacity-40" :disabled="!numpadActive" aria-label="Dígito 0" @click="$emit('tenderDigit', '0')">0</button>
            <button type="button" class="grid place-items-center rounded-md border border-destructive/25 bg-destructive/5 h-11 text-destructive transition hover:bg-destructive/10 active:translate-y-px disabled:opacity-40" :disabled="!numpadActive" aria-label="Apagar um dígito" title="Apaga o último dígito do valor (Backspace)" @click="$emit('tenderBackspace')">
              <Icon name="lucide:delete" class="size-5" />
            </button>
            <!-- Exato: a linha selecionada assume o que as OUTRAS deixam devendo
                 (venda coberta, troco zero) — tecla '='. Limpar (C): zera a linha
                 inteira para digitar; o Backspace apaga um dígito por vez. -->
            <button
              type="button"
              class="col-span-2 flex h-11 items-center justify-center gap-1.5 rounded-md border bg-card text-sm font-semibold transition hover:bg-accent active:translate-y-px disabled:opacity-40"
              :disabled="!numpadActive"
              aria-label="Exato: a linha assume o restante"
              title="A forma selecionada assume o que falta para cobrir o total (=)"
              @click="$emit('tenderExact')"
            >
              <Icon name="lucide:equal" class="size-4 shrink-0 text-muted-foreground" />
              Exato
              <kbd class="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-muted-foreground" aria-hidden="true">=</kbd>
            </button>
            <button
              type="button"
              class="flex h-11 items-center justify-center gap-1.5 rounded-md border bg-card text-sm font-semibold transition hover:bg-accent active:translate-y-px disabled:opacity-40"
              :disabled="!numpadActive"
              aria-label="Limpar: zera o valor da linha"
              title="Zera o valor da linha inteira (o Backspace apaga um dígito)"
              @click="$emit('tenderClear')"
            >
              <Icon name="lucide:eraser" class="size-4 shrink-0 text-muted-foreground" />
              Limpar
            </button>
          </div>
          <!-- cédula rail — 4ª coluna (mesma largura das colunas do teclado);
               verde dinheiro + ícone de nota -->
          <div
            v-if="cashSelected"
            class="grid flex-1 basis-0 gap-1.5"
            :style="{ gridTemplateRows: `repeat(${cashNotesQ.length}, minmax(0, 1fr))` }"
            role="group"
            aria-label="Cédulas recebidas"
          >
            <button
              v-for="note in cashNotesQ"
              :key="note"
              type="button"
              class="flex items-center justify-center gap-1 rounded-md border border-success/30 bg-success/10 text-sm font-semibold tabular-nums text-success transition hover:bg-success/20 active:translate-y-px disabled:opacity-40"
              :disabled="!numpadActive"
              :aria-label="`Recebi nota de ${formatBRL(note)}`"
              @click="$emit('tenderAdd', note)"
            >
              <Icon name="lucide:banknote" class="size-3.5 shrink-0 opacity-70" />
              {{ note / 100 }}
            </button>
          </div>
          </div>
        </section>

        <!-- NOTA FISCAL — a última pergunta do balcão, no lugar em que ela é
             feita, e na ordem em que se fala: "CPF na nota? Impressa? Por
             e-mail?".

             São TRÊS ESTADOS, não três comandos — por isso switch, e não botão
             com check. E nenhum deles é "emitir ou não": isso é da regra do
             servidor. Estes três perguntam o que é do CLIENTE, e o operador só
             transmite. Cada um nasce da preferência dele (`fiscal_prefs`), e o
             campo que revela vem pré-preenchido do cadastro — editável, valendo
             só nesta venda. -->
        <section v-if="supportsFiscalDocument" class="grid gap-1.5" aria-label="Nota fiscal">
          <h3 class="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Nota fiscal</h3>
          <div class="divide-y rounded-md border bg-card">

            <!-- 1 · CPF na nota -->
            <div class="grid gap-2 p-3">
              <label class="flex cursor-pointer items-center justify-between gap-3">
                <span class="flex min-w-0 items-center gap-2 text-sm font-medium">
                  <Icon name="lucide:receipt-text" class="size-4 shrink-0 text-muted-foreground" />
                  CPF na nota?
                </span>
                <kbd class="ml-auto shrink-0 rounded border bg-muted px-1 py-0.5 font-mono text-xs font-medium text-muted-foreground" aria-hidden="true">F9</kbd>
                <UiSwitch
                  :model-value="wantsCpfOnInvoice"
                  aria-label="CPF na nota"
                  @update:model-value="$emit('update:wantsCpfOnInvoice', $event)"
                />
              </label>
              <template v-if="wantsCpfOnInvoice">
                <UiInput
                  :model-value="invoiceTaxIdMasked"
                  inputmode="numeric"
                  class="h-11 tabular-nums"
                  placeholder="000.000.000-00"
                  aria-label="CPF que sai na nota"
                  @update:model-value="$emit('update:invoiceTaxId', String($event || ''))"
                />
                <!-- Eco do documento: o operador lê de volta o que vai sair e diz
                     ao cliente. Sem isto, "pôs o meu?" não tem resposta na tela. -->
                <p class="flex items-center gap-1.5 text-xs" :class="taxIdEcho.ok ? 'text-muted-foreground' : 'text-amber-700 dark:text-amber-400'">
                  <Icon :name="taxIdEcho.ok ? 'lucide:check' : 'lucide:triangle-alert'" class="size-3.5 shrink-0" />
                  {{ taxIdEcho.text }}
                </p>
                <p v-if="taxIdIsFromCadastro" class="text-xs text-muted-foreground">
                  Do cadastro. Trocar aqui vale só nesta venda.
                </p>
              </template>
            </div>

            <!-- 2 · Impressa. Sem campo: a resposta é a bobina. -->
            <div class="p-3">
              <label class="flex cursor-pointer items-center justify-between gap-3">
                <span class="flex min-w-0 items-center gap-2 text-sm font-medium">
                  <Icon name="lucide:printer" class="size-4 shrink-0 text-muted-foreground" />
                  Impressa?
                </span>
                <UiSwitch
                  :model-value="wantsPrintedReceipt"
                  aria-label="Nota impressa"
                  @update:model-value="setReceiptChannel('print', $event)"
                />
              </label>
              <p v-if="wantsPrintedReceipt" class="mt-1.5 text-xs text-muted-foreground">
                Sai sozinha na bobina assim que a nota autorizar.
              </p>
            </div>

            <!-- 3 · Por e-mail -->
            <div class="grid gap-2 p-3">
              <label class="flex cursor-pointer items-center justify-between gap-3">
                <span class="flex min-w-0 items-center gap-2 text-sm font-medium">
                  <Icon name="lucide:mail" class="size-4 shrink-0 text-muted-foreground" />
                  Por e-mail?
                </span>
                <UiSwitch
                  :model-value="wantsEmailReceipt"
                  aria-label="Nota por e-mail"
                  @update:model-value="setReceiptChannel('email', $event)"
                />
              </label>
              <template v-if="wantsEmailReceipt">
                <UiInput
                  :model-value="receiptEmail"
                  type="email"
                  class="h-11"
                  :placeholder="customerEmail || 'cliente@email.com'"
                  aria-label="E-mail que recebe a nota"
                  @update:model-value="$emit('update:receiptEmail', String($event || ''))"
                />
                <p v-if="!receiptEmail.trim() && customerEmail.trim()" class="text-xs text-muted-foreground">
                  Sem preencher, vai para <span class="font-medium text-foreground">{{ customerEmail }}</span>.
                </p>
                <p v-else-if="emailIsFromCadastro" class="text-xs text-muted-foreground">
                  Do cadastro. Trocar aqui vale só nesta venda.
                </p>
              </template>
            </div>

          </div>
        </section>

        <!-- Por que o botão está travado. O aviso do gerente sozinho enganava: com
             o botão desabilitado por falta de forma de pagamento, o único texto na
             tela falava de autorização, e o operador procurava um gerente para um
             problema que era escolher "Dinheiro". Diz-se primeiro o que bloqueia. -->
        <p v-if="ctaBlockReason" class="flex items-center gap-1.5 px-1 text-xs text-muted-foreground">
          <Icon name="lucide:info" class="size-3.5 shrink-0" />
          <span class="min-w-0 flex-1">{{ ctaBlockReason }}</span>
          <UiButton
            v-if="ctaBlockAction"
            variant="outline"
            size="sm"
            class="h-7 shrink-0 px-2 text-xs"
            @click="ctaBlockAction.run()"
          >
            {{ ctaBlockAction.label }}
          </UiButton>
        </p>
        <!-- manager approval: when the review demands it, "Autorizar e validar"
             opens a dedicated PIN authorization screen (PosManagerAuthDialog) -->
        <p v-else-if="needsAuth" class="flex items-center gap-1.5 px-1 text-xs text-muted-foreground">
          <Icon name="lucide:shield-check" class="size-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
          Requer autorização do gerente para finalizar.
        </p>

        <!-- Voltar + Validar (rodapé da coluna, copiando o Back + Validate do Odoo).
             Meio a meio dava 177px para cada um, e "Autorizar e validar" — o
             rótulo do caso que EXIGE leitura, porque chama um gerente — vazava
             do botão. O Voltar cabe no que ele é; o resto é do Validar. -->
        <div class="flex gap-1.5 pt-1">
          <UiButton variant="outline" size="lg" class="h-14 shrink-0 gap-2 px-3 text-sm" title="Voltar para a venda (Esc)" @click="$emit('back')">
            <Icon name="lucide:arrow-left" class="size-5" />
            Voltar
            <kbd class="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-muted-foreground" aria-hidden="true">Esc</kbd>
          </UiButton>
          <UiButton
            size="lg"
            class="h-14 min-w-0 flex-1 gap-2 text-base"
            :disabled="ctaDisabled"
            :loading="loading || needsReview"
            @click="onCta"
          >
            {{ ctaLabel }}
            <kbd class="rounded border border-primary-foreground/30 bg-transparent px-1.5 py-0.5 font-mono text-xs font-medium opacity-80" aria-hidden="true">Enter</kbd>
          </UiButton>
        </div>
      </div>

      <!-- MEIO · VALOR (empilhado: no topo). Fica com a largura que sobra das
           duas colunas fixas — por isso o total escala com a janela em vez de
           ter um tamanho só: no `xl` a faixa do meio é a mais estreita das três
           configurações, e um `text-8xl` ali transbordava. -->
      <div class="order-1 flex min-h-0 min-w-0 flex-1 flex-col gap-3 py-1 md:order-none">
        <!-- valor gigante (estável = total a cobrar), centrado -->
        <section class="flex flex-1 flex-col items-center justify-center text-center" aria-label="Total a cobrar">
          <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Total a cobrar</p>
          <p class="text-4xl font-bold tabular-nums tracking-tight xl:text-6xl 2xl:text-8xl">{{ review ? review.total_display : interimTotalDisplay }}</p>
          <p v-if="items.length" class="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Icon name="lucide:flame" class="size-3.5 shrink-0" :class="firedCount ? 'text-primary' : ''" />
            {{ kitchenNote }}
          </p>
        </section>

        <!-- avisos não-bloqueantes da review (nunca impedem finalizar) -->
        <ul v-if="reviewWarnings.length" class="shrink-0 flex flex-col gap-1.5">
          <li
            v-for="(w, idx) in reviewWarnings"
            :key="idx"
            class="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300"
            role="status"
          >
            <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
            <span>{{ w.message }}</span>
          </li>
        </ul>

        <!-- DIVIDIR A CONTA — "somos três, cada um paga o seu".
             Ligado, cada toque numa forma de pagamento lança UMA parte, já
             calculada (os centavos fecham sozinhos, e a última parcela leva o
             que restou mesmo depois de o operador editar alguma linha). O
             operador não faz conta de cabeça com os três clientes olhando.
             Tocar de novo no mesmo número desliga: mudar de ideia é rotina. -->
        <div class="shrink-0 border-t pt-3">
          <div class="flex flex-wrap items-center gap-1.5">
            <span class="mr-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Dividir em
            </span>
            <UiButton
              v-for="n in SPLIT_PRESETS"
              :key="n"
              type="button"
              variant="outline"
              size="sm"
              class="h-9 w-9 p-0 tabular-nums"
              :class="splitCount === n ? 'border-primary bg-primary/10 font-bold' : ''"
              :aria-pressed="splitCount === n"
              :aria-label="`Dividir a conta em ${n} pessoas`"
              @click="$emit('setSplitCount', n)"
            >
              {{ n }}
            </UiButton>
            <span v-if="splitNote" class="ml-auto text-sm font-semibold tabular-nums">{{ splitNote }}</span>
          </div>
        </div>

        <!-- linhas de pagamento + troco/restante -->
        <div v-if="tenderLines.length" class="shrink-0 border-t pt-3">
          <ul class="flex flex-col gap-1.5">
            <li v-for="(tender, idx) in tenderLines" :key="idx">
              <button
                type="button"
                class="flex h-11 w-full items-center justify-between gap-2 rounded-md border px-3 text-left transition"
                :class="idx === selectedTenderIndex ? 'border-primary bg-primary/5' : 'hover:bg-accent/60'"
                :aria-current="idx === selectedTenderIndex ? 'true' : undefined"
                @click="$emit('selectTender', idx)"
              >
                <span class="flex min-w-0 items-center gap-2 text-sm font-medium">
                  <Icon :name="tender.icon" class="size-4 shrink-0" />
                  <span class="truncate">{{ tender.label }}</span>
                </span>
                <span class="flex shrink-0 items-center gap-2">
                  <strong class="text-lg tabular-nums">{{ tender.amountDisplay }}</strong>
                  <UiButton variant="ghost" size="icon-xs" aria-label="Remover pagamento" @click.stop="$emit('removeTender', idx)">
                    <Icon name="lucide:x" class="size-3.5 text-destructive" />
                  </UiButton>
                </span>
              </button>
            </li>
          </ul>
          <!-- Uma linha, três estados. O rótulo e o número precisam concordar: com
               o total coberto era "Pago R$ 0,00", que se lê como "não pagou nada"
               justo quando o cliente acabou de entregar o dinheiro. O que zera ali
               é o que FALTA, então o rótulo é "Restante". -->
          <div class="mt-2 flex items-center justify-between gap-2 px-1">
            <span class="text-sm font-medium uppercase tracking-wide" :class="payState === 'change' ? 'text-primary' : 'text-muted-foreground'">
              {{ payState === "change" ? "Troco" : "Restante" }}
            </span>
            <strong
              class="text-3xl font-bold tabular-nums"
              :class="payState === 'change' ? 'text-primary' : payState === 'ready' ? 'text-muted-foreground' : ''"
            >
              {{ payState === "change" ? formatBRL(paymentChangeQ) : formatBRL(Math.max(0, paymentRemainingQ)) }}
            </strong>
          </div>
        </div>
      </div>

      <!-- DIREITA · CONTEXTO — a coluna que faltava. Medido em 1440×900 antes
           dela: o bloco do valor ocupava 893×815 para mostrar UM número, e o
           checkout não dizia em momento nenhum O QUE estava sendo cobrado. O
           operador saía da tela de venda, onde via a lista, e chegava numa tela
           onde a lista não existe mais — bem na hora em que o cliente pergunta
           "por que deu isso?".

           Aqui ficam os três fatos da venda (cliente, recebimento, desconto —
           os mesmos `contextEntries` dos chips, agora com rótulo) e o RESUMO DO
           PEDIDO. Largura fixa de 360px, igual à do carrinho na tela de venda:
           é a mesma lista, no mesmo lugar da tela, com a mesma medida. -->
      <div class="order-3 hidden min-h-0 w-[360px] shrink-0 flex-col gap-3 overflow-y-auto md:order-none lg:flex">
        <!-- RESUMO DO PEDIDO — a lista, e o que a soma dela vira. Sem stepper e
             sem lixeira: aqui não se edita o pedido (para isso existe o Voltar),
             só se confere. Rola quando a comanda é grande; subtotal, desconto e
             taxa ficam colados embaixo, fora da rolagem. -->
        <section class="flex min-h-0 flex-1 flex-col gap-1.5" aria-label="Resumo do pedido">
          <h3 class="flex items-baseline gap-2 px-1">
            <span class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Resumo do pedido</span>
            <span v-if="summaryUnits" class="ml-auto text-xs tabular-nums text-muted-foreground">
              {{ summaryUnits }} {{ summaryUnits === 1 ? "item" : "itens" }}
            </span>
          </h3>

          <div class="flex min-h-0 flex-1 flex-col rounded-md border bg-card">
            <ul v-if="summaryLines.length" class="min-h-0 flex-1 divide-y overflow-y-auto">
              <li v-for="line in summaryLines" :key="line.sku" class="px-3 py-2">
                <div class="flex items-baseline gap-2">
                  <span class="w-6 shrink-0 text-sm font-semibold tabular-nums text-muted-foreground">{{ line.qty }}×</span>
                  <span class="min-w-0 flex-1 truncate text-sm">{{ line.name }}</span>
                  <span
                    v-if="line.listDisplay"
                    class="shrink-0 text-xs tabular-nums text-muted-foreground line-through"
                  >{{ line.listDisplay }}</span>
                  <strong class="shrink-0 text-sm font-semibold tabular-nums">{{ line.totalDisplay }}</strong>
                </div>
                <!-- POR QUE está mais barato. Riscar o preço sem dizer o motivo
                     transfere para o operador a pergunta que o cliente acabou de
                     fazer. É o mesmo idioma do resumo da loja. -->
                <p v-if="line.discountLabel" class="mt-0.5 flex items-center gap-1 pl-8 text-xs text-primary">
                  <Icon name="lucide:tag" class="size-3 shrink-0" />
                  {{ line.discountLabel }}
                </p>
              </li>
            </ul>
            <p v-else class="flex flex-1 items-center justify-center px-3 py-6 text-center text-sm text-muted-foreground">
              Nada lançado nesta comanda.
            </p>

            <!-- Só aparece o que EXISTE: subtotal sozinho ao lado de um total
                 igual a ele é uma linha que não informa nada. -->
            <dl
              v-if="summarySavingsQ > 0 || (review && (review.discount_q > 0 || review.delivery_fee_q > 0))"
              class="grid gap-1 border-t px-3 py-2 text-sm"
            >
              <!-- Duas linhas porque são dois fatos, e cada uma diz DE QUEM é o
                   desconto:

                   · "nos itens" é o que já veio na etiqueta (promoção, xepa,
                     lote) — informativo, explica a diferença entre o preço de
                     tabela e o subtotal;
                   · "do operador" é `review.discount_q`, que soma o desconto de
                     LINHA e o do PEDIDO — é ele que sai do subtotal e chega no
                     total, e é ele que chama gerente.

                   ⚠️ Esta linha chamava-se "Desconto no pedido" e mentia: com uma
                   cortesia de 10% numa LINHA, a tela mostrava "Sem desconto" no
                   botão (que controla só o desconto do pedido) e "Desconto no
                   pedido −R$ 1,02" logo ao lado. Duas frases, o mesmo nome, dois
                   escopos. O botão agora também diz o seu escopo. -->
              <div v-if="summarySavingsQ > 0" class="flex items-baseline justify-between gap-2 text-primary">
                <dt class="font-medium">Desconto nos itens</dt>
                <dd class="tabular-nums font-semibold">−{{ formatBRL(summarySavingsQ) }}</dd>
              </div>
              <template v-if="review">
                <div v-if="review.discount_q > 0 || review.delivery_fee_q > 0" class="flex items-baseline justify-between gap-2">
                  <dt class="text-muted-foreground">Subtotal</dt>
                  <dd class="tabular-nums">{{ review.subtotal_display }}</dd>
                </div>
                <div v-if="review.discount_q > 0" class="flex items-baseline justify-between gap-2 text-primary">
                  <dt>Desconto do operador</dt>
                  <dd class="tabular-nums">−{{ review.discount_display }}</dd>
                </div>
                <div v-if="review.delivery_fee_q > 0" class="flex items-baseline justify-between gap-2">
                  <dt class="text-muted-foreground">Taxa de entrega</dt>
                  <dd class="tabular-nums">{{ review.delivery_fee_display }}</dd>
                </div>
              </template>
            </dl>
          </div>
        </section>
      </div>
    </div>

  </section>

  <!-- RECEBIMENTO — a mesma caixa que a abertura da comanda usa. O checkout
       agora REVÊ o que foi decidido no começo do atendimento, em vez de ser o
       único lugar onde a pergunta existe. -->
  <PosFulfillmentModal
    v-model:open="fulfillmentSheetOpen"
    :fulfillment-options="fulfillmentOptions"
    :fulfillment-type="fulfillmentType"
    :saved-addresses="savedAddresses"
    :address-autocomplete="addressAutocomplete"
    :delivery-address="deliveryAddress"
    :delivery-street-number="deliveryStreetNumber"
    :delivery-neighborhood="deliveryNeighborhood"
    :delivery-complement="deliveryComplement"
    :delivery-instructions="deliveryInstructions"
    :schedule-label="scheduleChipLabel"
    :delivery-fee-override="deliveryFeeOverride"
    :delivery-fee-override-input="deliveryFeeOverrideInput"
    :delivery-fee-q="deliveryFeeQ"
    :delivery-fee-source="deliveryFeeSource"
    :delivery-distance-km="deliveryDistanceKm"
    :order-notes="orderNotes"
    @update:fulfillment-type="$emit('update:fulfillmentType', $event)"
    @update:delivery-address="$emit('update:deliveryAddress', $event)"
    @update:delivery-address-structured="$emit('update:deliveryAddressStructured', $event)"
    @update:delivery-street-number="$emit('update:deliveryStreetNumber', $event)"
    @update:delivery-neighborhood="$emit('update:deliveryNeighborhood', $event)"
    @update:delivery-complement="$emit('update:deliveryComplement', $event)"
    @update:delivery-instructions="$emit('update:deliveryInstructions', $event)"
    @update:delivery-fee-override="$emit('update:deliveryFeeOverride', $event)"
    @update:delivery-fee-override-input="$emit('update:deliveryFeeOverrideInput', $event)"
    @update:order-notes="$emit('update:orderNotes', $event)"
    @pick-saved-address="$emit('pickSavedAddress', $event)"
    @open-schedule="scheduleSheetOpen = true"
  />

  <!-- QUANDO — a MESMA caixa que a tela de venda abre. O agendamento é decidido
       na abertura do atendimento; aqui ele é revisto, com as mesmas palavras. -->
  <PosScheduleModal
    v-model:open="scheduleSheetOpen"
    :today="scheduleToday"
    :delivery-date-effective="deliveryDateEffective"
    :delivery-time-slot="deliveryTimeSlot"
    :available-dates="scheduleAvailableDates"
    :windows="deliverySlots"
    :bottleneck-name="scheduleBottleneckName"
    :ready-at="scheduleReadyAt"
    :pending="deliverySlotsPending"
    :failed="scheduleFailed"
    :max-date="scheduleMaxDate"
    @update:delivery-date="$emit('update:deliveryDate', $event)"
    @update:delivery-time-slot="$emit('update:deliveryTimeSlot', $event)"
  />

  <!-- Cliente & fiscal — shared full-screen picker (showFiscal rides the receipt) -->
  <PosCustomerModal
    v-model:open="customerSheetOpen"
    :show-fiscal="supportsFiscalDocument"
    :customer-name="customerName"
    :customer-phone="customerPhone"
    :customer-tax-id="customerTaxId"
    :customer-email="customerEmail"
    :customer-lookup="customerLookup"
    :search-results="searchResults"
    :search-busy="searchBusy"
    :lookup-busy="lookupBusy"
    :resolved-new="customerResolvedNew"
    :receipt-channels="receiptChannels"
    :receipt-channel-options="receiptChannelOptions"
    :receipt-email="receiptEmail"
    @update:customer-name="$emit('update:customerName', $event)"
    @update:customer-phone="$emit('update:customerPhone', $event)"
    @update:customer-tax-id="$emit('update:customerTaxId', $event)"
    @update:customer-email="$emit('update:customerEmail', $event)"
    @update:receipt-channels="$emit('update:receiptChannels', $event)"
    @update:receipt-email="$emit('update:receiptEmail', $event)"
    @search="$emit('search', $event)"
    @select-result="onSelectResult"
    @clear="$emit('clearCustomer')"
    @resolve-customer="$emit('resolveCustomer')"
    @apply-customer-favorite="$emit('applyCustomerFavorite')"
    @repeat-customer-last-order="$emit('repeatCustomerLastOrder')"
  />

  <!-- MODAL: Desconto -->
  <UiDialog v-model:open="discountSheetOpen">
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-md">
      <UiDialogHeader>
        <UiDialogTitle>Desconto</UiDialogTitle>
        <UiDialogDescription>Tipo, valor e motivo. O backend revisa e aplica.</UiDialogDescription>
      </UiDialogHeader>
      <div class="grid gap-4">
        <div class="grid grid-cols-2 gap-2">
            <UiButton
              v-for="option in discountTypes"
              :key="option.ref"
              variant="outline"
              :class="discountType === option.ref ? 'border-primary bg-primary/5' : ''"
              @click="$emit('update:discountType', option.ref === 'fixed' ? 'fixed' : 'percent')"
            >
              {{ option.label }}
            </UiButton>
          </div>
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">{{ discountType === "fixed" ? "Valor (R$)" : "Percentual (%)" }}</span>
            <UiInput :model-value="discountValue" inputmode="decimal" placeholder="0" @update:model-value="$emit('update:discountValue', String($event || ''))" />
          </label>
          <div v-if="discountReasons.length" class="flex flex-wrap gap-2">
            <UiButton
              v-for="reason in discountReasons"
              :key="reason.ref"
              variant="outline"
              size="sm"
              :class="discountReason === reason.ref ? 'border-primary bg-primary/5' : ''"
              @click="$emit('update:discountReason', reason.ref)"
            >
              {{ reason.label }}
            </UiButton>
          </div>
        </div>
        <UiDialogFooter>
          <UiButton class="w-full" @click="discountSheetOpen = false">Concluir</UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

  <!-- AUTORIZAÇÃO DO GERENTE -->
  <PosManagerAuthDialog
    v-model:open="managerAuthOpen"
    action="sale_approval"
    :threshold-q="managerThresholdQ"
    :reasons="review?.approval_reasons"
    :operator-name="operatorName || ''"
    :managers="managers"
    :busy="loading"
    :error="managerApprovalError"
    @authorize="onManagerAuthorize"
  />
</template>
