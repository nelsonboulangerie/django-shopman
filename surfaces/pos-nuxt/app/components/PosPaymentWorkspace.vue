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
  lineTotalQ,
} from "~/presentation/lineDiscounts";
import { managerAuthReason } from "~/presentation/managerAuth";
import { isValidTaxId } from "~/presentation/taxId";
import { scheduledNeedsCustomer, scheduleLabel, selectedWindowConflict, windowLabel } from "~/presentation/schedule";

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
// AVISOS DA REVIEW QUE ESTA TELA NÃO CONSEGUE RENOVAR.
//
// A review só é refeita quando muda o CARRINHO (item, desconto, entrega). Mexer
// nas linhas de pagamento, no troco-para ou no numpad NÃO a renova — então todo
// aviso do servidor que fala de PAGAMENTO nasce com data de validade e não tem
// gesto capaz de calá-lo. O sintoma é sempre o mesmo e sempre o pior possível:
// uma frase congelada dizendo que falta dinheiro, dez centímetros acima de um
// "RESTANTE R$ 0,00" vivo e de um Validar verde. O operador aprende a não ler
// nenhuma das duas.
//
// Quem responde por cada um deles AO VIVO já existe nesta tela:
//   · cobertura e troco → a leitura RESTANTE/TROCO e o herói;
//   · excedente sem troco possível → o bloqueio do Validar (abaixo);
//   · combinado da porta menor que o total → a legenda do próprio campo.
// O contrato do servidor fica como está: outros consumidores da review — e o
// commit, que é quem de fato recusa — continuam recebendo os códigos.
const STALE_BY_CONSTRUCTION = new Set([
  "cash_tendered_amount_blank",
  "tender_overpaid_non_cash",
  "payment_tenders_required",
  "payment_tenders_total_mismatch",
  "change_for_below_total",
]);
// Excedente em cartão/Pix é erro de digitação, e não existe troco para desfazê-lo:
// o operador precisa vê-lo NA HORA em que digita. Conta local (`nonCashExcessQ`)
// sobre o `paymentTotalQ` — com a review em trânsito, o total 0 fazia toda linha
// digital virar "excedente" por meio segundo.
const nonCashExcess = computed(() => nonCashExcessQ(props.paymentTenders, props.paymentTotalQ));
// Agendado sem cliente: o servidor recusa a encomenda anônima
// (`customer_required_for_scheduled`) — o botão trava ANTES, com o motivo.
// A REGRA é a mesma do chip que pulsa na barra do topo, e por isso vem da
// mesma função. O `ref` do cadastro conta: o servidor aceita qualquer um dos
// três identificadores, e o cadastro só-com-CPF (sem telefone) existe.
const scheduledWithoutCustomer = computed(() => scheduledNeedsCustomer({
  deliveryDate: props.deliveryDate,
  today: props.scheduleToday,
  customerName: props.customerName,
  customerPhone: props.customerPhone,
  customerRef: props.customerLookup?.ref || "",
}));
const reviewWarnings = computed(() => {
  const fromServer = (props.review?.warnings ?? []).filter(
    (w) => !STALE_BY_CONSTRUCTION.has(w.code)
      // AGENDADO SEM CLIENTE não fala duas vezes. Quem vigia a condição AO VIVO é
      // o bloqueio do CTA (`scheduledWithoutCustomer`), e é ele que traz o toque
      // que resolve. O aviso do servidor dizia a MESMA coisa, com mais palavras,
      // sem caminho e — porque a review só é refeita quando o CARRINHO muda —
      // podendo ficar defasado ao lado de um cabeçalho já com o nome do cliente.
      // Dois avisos para uma pendência é o que faz o operador parar de ler os dois.
      && w.code !== "customer_required_for_scheduled",
  );
  return fromServer;
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

// A MÁSCARA E O VALOR GUARDADO precisam parar no mesmo dígito. A máscara fazia
// `slice(0, 14)` e o que era emitido não: digitando um 15º dígito a tela seguia
// exibindo um CNPJ completo enquanto o valor guardado tinha 15 — e o eco logo
// abaixo dizia "Documento incompleto" sobre um número que parecia perfeito.
// Guardamos só dígitos (é o que o intent envia de qualquer jeito) e cortamos na
// origem.
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

// "Sai na nota" é uma PROMESSA, e promessa se confere. Onze dígitos quaisquer
// viravam um check verde: o operador lia de volta com confiança, o cliente
// confirmava, e a rejeição da NFC-e chegava com ele já na rua. Contar dígito não
// é conferir documento — quem confere é o dígito verificador.
const taxIdEcho = computed<{ ok: boolean; text: string }>(() => {
  const digits = props.invoiceTaxId.replace(/\D/g, "");
  if (!digits) return { ok: false, text: "Digite o documento — sem ele a nota sai sem CPF." };
  if (digits.length !== 11 && digits.length !== 14) {
    return { ok: false, text: "Documento incompleto — a nota sai sem CPF." };
  }
  if (!isValidTaxId(digits)) {
    return { ok: false, text: "Documento inválido — confira com o cliente." };
  }
  if (digits.length === 11) {
    return { ok: true, text: `Sai na nota: CPF ${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}` };
  }
  return { ok: true, text: `Sai na nota: CNPJ ${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}` };
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
// A ETIQUETA DO BOTÃO diz o que vai ser tirado, não o que foi digitado.
// `R$ ${discountValue}` cru devolvia "R$ 5.5" (ponto, sem centavos) para quem
// digitou 5,5 — e, pior, "R$ 50" numa venda de R$ 20, enquanto o servidor
// aplica `min(subtotal, pedido)` e o resumo à direita (que só existe a partir
// de `lg`) mostrava R$ 20,00. Abaixo de 1280px o operador só via o errado.
const discountSummary = computed(() => {
  if (props.discountType !== "fixed") return `${discountValueNum.value}%`;
  const asked = moneyInputToQ(props.discountValue);
  const cap = props.review?.subtotal_q ?? asked;
  return formatBRL(Math.min(asked, cap));
});

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
// O QUE SEGURA O BOTÃO — na ordem em que o operador resolve, em três partes:
// a frase (curta, é o que ele lê de longe), o porquê (miúdo, é o que ele DIZ ao
// cliente) e o caminho (um toque, quando esta tela sabe abrir a porta).
// Motivo sem caminho é beco sem saída; motivo comprido não é lido. As duas
// coisas custavam a mesma venda.
// O horário escolhido virou impossível sem ninguém tocar nele. Mesmo helper que
// pinta o chip do topo de vermelho — a tela não pode ter duas opiniões sobre a
// mesma janela.
const scheduleConflictReason = computed(
  () => selectedWindowConflict(props.deliverySlots, props.deliveryTimeSlot),
);
// O CPF só viaja no intent quando o switch está ligado (`usePosSale`), e a taxa
// é a RESOLVIDA pelo servidor — as duas metades exatas de
// `_validate_fiscal_delivery_fee`.
const fiscalWithDeliveryFee = computed(
  () => props.wantsCpfOnInvoice
    && !!props.invoiceTaxId.replace(/\D/g, "")
    && props.fulfillmentType === "delivery"
    && props.deliveryFeeQ > 0,
);
// Levar o foco ao campo que resolve. Por `aria-label` porque é o nome que o
// campo já carrega para quem não enxerga — um `ref` a mais seria um segundo
// nome para a mesma coisa, e o primeiro a envelhecer.
function focusByAriaLabel(label: string) {
  if (!import.meta.client) return;
  void nextTick(() => {
    const field = document.querySelector<HTMLInputElement>(`[aria-label="${label}"]`);
    field?.focus();
    field?.scrollIntoView({ block: "center", behavior: "auto" });
  });
}

type CheckoutAction = { label: string; run: () => void };
// TODA RECUSA DO COMMIT TEM QUE TER GÊMEA AQUI. O servidor recusa a venda em
// oito portões; a tela replicava três. Os outros cinco viravam 422 seco com o
// cliente na frente, depois de o combinado já ter sido feito em voz alta — e um
// deles ("Fiscal com taxa de entrega") a tela até CONTRADIZIA, escrevendo "Sai
// na nota: CPF …" enquanto o Validar ficava verde.
//
// A ordem é a da conversa do balcão: quem é o cliente, o que foi prometido, o
// que sai na nota, e só então o dinheiro.
const ctaBlock = computed<{ message: string; hint?: string; action?: CheckoutAction } | null>(() => {
  if (!props.items.length) {
    return {
      message: "Comanda vazia.",
      hint: "Não há o que cobrar.",
      action: { label: "Voltar à comanda", run: () => { emit("back"); } },
    };
  }
  if (props.loading || needsReview.value) return null;
  if (scheduledWithoutCustomer.value) {
    return {
      message: "Encomenda precisa de cliente.",
      hint: "É o contato se algo mudar até a data.",
      action: { label: "Identificar cliente", run: () => { customerSheetOpen.value = true; } },
    };
  }
  // O horário virou impossível SOZINHO (o operador combinou 09:00 e só depois
  // lançou a baguete). O chip do topo já ficava vermelho; o Validar seguia
  // verde, e a recusa (`_validate_schedule`) sobe como 422 sem campo nenhum.
  if (scheduleConflictReason.value) {
    return {
      message: "O horário combinado não cabe mais.",
      hint: scheduleConflictReason.value,
      action: { label: "Escolher horário", run: () => { scheduleSheetOpen.value = true; } },
    };
  }
  // `_validate_fiscal_delivery_fee`: nota com CPF + taxa de entrega ainda passa
  // pela conferência do gestor. É o único portão que a tela não só ignorava como
  // desmentia, com o eco "Sai na nota" logo abaixo do switch.
  if (fiscalWithDeliveryFee.value) {
    return {
      message: "Nota com CPF e taxa de entrega, não.",
      hint: "O gestor precisa conferir antes. Finalize sem o CPF.",
      action: { label: "Tirar o CPF", run: () => { emit("update:wantsCpfOnInvoice", false); } },
    };
  }
  // `receipt_email_required`: o canal ligado sem endereço nenhum. O composable
  // cobre o caso comum (cai no e-mail do cadastro); quando os dois estão vazios,
  // a recusa vinha no Validar.
  if (wantsEmailReceipt.value && !props.receiptEmail.trim() && !props.customerEmail.trim()) {
    return {
      message: "Falta o e-mail do comprovante.",
      action: { label: "Preencher", run: () => { focusByAriaLabel("E-mail que recebe a nota"); } },
    };
  }
  if (!props.paymentTenders.length) return { message: "Escolha a forma de pagamento." };
  // Excedente em cartão/Pix não tem troco que o desfaça: é digitação errada, e
  // o servidor grava o valor inflado como recebido. Era um aviso amarelo ao lado
  // de "Restante R$ 0,00" e de um Validar verde — três estados discordando.
  if (nonCashExcess.value > 0) {
    return {
      message: `Cartão ou Pix ${formatBRL(nonCashExcess.value)} acima do total.`,
      hint: "Não há troco para forma digital; ajuste a linha.",
    };
  }
  if (!props.paymentCovered) {
    return { message: `Faltam ${formatBRL(Math.max(0, props.paymentRemainingQ))} para validar.` };
  }
  return null;
});
// ── A FAIXA DE AVISOS ────────────────────────────────────────────────────────
// UMA faixa, no topo da coluna do valor, com tudo o que a tela tem a dizer — e
// dentro dela uma hierarquia, na ordem em que o operador resolve:
//
//   1. o que TRAVA o Validar, em corpo de leitura e com o toque que resolve;
//   2. o que finalizar VAI fazer (a cozinha, a bobina, o troco do entregador);
//   3. o que a review RESSALVA e não impede.
//
// Ela ficou aqui, e não numa barra no rodapé, porque uma barra atravessando a
// tela para carregar uma frase e dois botões corta o desenho justamente embaixo
// do valor — e rouba a largura das três colunas para isso.
//
// Nada é dito duas vezes na mesma tela.
type CheckoutNotice = {
  key: string;
  icon: string;
  accent?: string;
  message: string;
  hint?: string;
  /** `block` é o que segura o Validar: corpo de leitura, âmbar, e o toque que
   *  resolve. `warn` é ressalva da review. Sem tom, é consequência. */
  tone?: "block" | "warn";
  action?: CheckoutAction;
};

// AVISOS — o bloqueio primeiro, depois as consequências, depois as ressalvas.
// Só entra o que MUDA de venda para venda: uma linha que aparece em toda venda
// vira moldura e some da vista.
const notices = computed<CheckoutNotice[]>(() => {
  const notes: CheckoutNotice[] = [];
  // 1 · O QUE TRAVA. Vem primeiro e é o único com botão: motivo sem caminho é
  //     beco sem saída, e caminho longe do motivo é o operador procurando.
  const block = ctaBlock.value;
  if (block) notes.push({ key: "block", tone: "block", icon: "lucide:triangle-alert", ...block });
  else if (needsAuth.value) {
    // Sem botão próprio de propósito: o caminho É o Validar, que neste estado se
    // chama "Autorizar e validar". Um segundo botão fazendo o mesmo gesto
    // duplicaria a ação mais delicada da tela — a que chama um gerente.
    notes.push({
      key: "auth",
      tone: "block",
      icon: "lucide:shield-check",
      message: "Esta venda precisa de um gerente.",
      // O QUE ele vai assinar. A review manda os códigos (`approval_reasons`) e
      // o diálogo já os traduz; o aviso os ignorava, e o operador tinha de
      // chamar o gerente para só então descobrir o motivo.
      hint: managerAuthReason({ reasons: props.review?.approval_reasons, thresholdQ: managerThresholdQ.value }),
    });
  }
  // Nada trava: entra quanto pedir à pessoa da vez. É a frase que o operador
  // fala em voz alta, e ela some sozinha quando a conta fecha.
  else if (props.splitNote) {
    notes.push({ key: "split", tone: "block", icon: "lucide:users", message: props.splitNote });
  }
  if (props.items.length && kitchenNote.value) {
    notes.push({
      key: "kitchen",
      icon: "lucide:flame",
      accent: firedCount.value ? "text-primary" : "",
      message: kitchenNote.value,
    });
  }
  // O troco que SAI COM O ENTREGADOR. Era legenda do próprio campo, lá na coluna
  // que rola; é consequência de finalizar, e por isso mora aqui.
  if (onDeliveryCash.value && props.changeForInput.trim() && changeForShortfall.value <= 0) {
    notes.push({ key: "courier", icon: "lucide:banknote", message: "O entregador sai com o troco separado." });
  }
  if (wantsPrintedReceipt.value) {
    // A frase não pode PROMETER papel: o auto-print é guardado por
    // `fiscalExpected` (dinheiro sem CPF não gera nota nenhuma), e a tela de
    // resultado se recusa a prometer. Mas a condição não precisa de um "se" —
    // ela já está no "quando a nota autorizar": sem nota, nada autoriza, e a
    // frase segue verdadeira. Duas tentativas anteriores erraram por caminhos
    // opostos: "Sai na bobina" prometia, "Se sair nota…" hesitava, e "Não
    // precisa mandar imprimir" lia-se como desfazer um toque errado.
    notes.push({ key: "print", icon: "lucide:printer", message: "Imprime sozinha quando a nota autorizar." });
  }
  // As ressalvas da review entram na MESMA faixa: são o mesmo gesto de leitura,
  // e uma segunda caixa ao lado só ensina o olho a pular as duas.
  for (const [idx, warning] of reviewWarnings.value.entries()) {
    notes.push({ key: `review-${warning.code || idx}`, tone: "warn", icon: "lucide:triangle-alert", message: warning.message });
  }
  return notes;
});

// O botão está travado sempre que HÁ motivo — não há segunda lista de regras.
// Era assim que o excedente em cartão escapava: ele avisava, e deixava passar.
const ctaDisabled = computed(() => {
  if (!props.items.length || props.loading || needsReview.value) return true;
  return ctaBlock.value !== null;
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
  /** F9 liga/desliga "CPF na nota?" — a pergunta fiscal mais feita no balcão.
   *  E LEVA O FOCO ao campo que acabou de aparecer. Sem isso o foco ficava no
   *  `body`, e o shell captura todo dígito fora de input quando há linha de
   *  pagamento selecionada: o operador apertava F9, digitava o CPF de reflexo, e
   *  os onze dígitos entravam no numpad — R$ 66,30 virava R$ 5.299.822,47 com um
   *  "TROCO" a condizer. Um Enter depois, por hábito, e a venda fechava. */
  toggleCpfOnInvoice: () => {
    const next = !props.wantsCpfOnInvoice;
    emit("update:wantsCpfOnInvoice", next);
    if (next) focusByAriaLabel("CPF que sai na nota");
  },
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
    <div class="flex min-h-0 w-full flex-1 flex-col gap-6 overflow-hidden lg:flex-row">

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
      <div class="order-2 flex min-h-0 flex-col gap-3 overflow-y-auto lg:order-none lg:w-[360px] lg:shrink-0">
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
        <!-- `mt-auto` saiu: ele empurrava a coluna para baixo de quando o
             pagamento era a ÚLTIMA seção. Com a Nota fiscal depois dela, o que
             ele produzia em 1920×1080 era ~170px de espaço morto no topo — e as
             três colunas deixando de compartilhar linha de base. -->
        <section class="grid gap-1.5" aria-label="Forma de pagamento">
          <h3 class="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Forma de pagamento</h3>

          <!-- O DESCONTO NÃO MORA MAIS AQUI. Ele era o primeiro botão de uma
               seção cujo assunto é outro: desconto não é forma de pagamento, é
               uma operação sobre o VALOR da venda. Ficava sob o cabeçalho
               "Forma de pagamento" ensinando a categoria errada — e, pior, era
               o primeiro alvo da coluna do instrumento, acima de Dinheiro.
               Agora vive no RODAPÉ, ao lado das outras ações da venda. -->
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
            <!-- "O entregador sai com o troco separado" é CONSEQUÊNCIA de
                 finalizar, não validação deste campo: subiu para as instruções,
                 no topo da coluna do valor. O que fica aqui é o que só este
                 campo sabe dizer — que o combinado não cobre o total. -->
          </label>

          <div class="flex flex-col gap-1.5">
            <!-- Tocar aqui ADICIONA uma linha; não escolhe "a forma" da venda.
                 O realce seguia `selectedTenderMethod` — o método da linha em
                 EDIÇÃO —, e numa conta dividida em três pagando tudo em dinheiro
                 o "Dinheiro" ficava permanentemente aceso, lendo-se como forma
                 escolhida. Agora o realce é só o anel de foco/hover; quem diz o
                 que está selecionado são as linhas de pagamento, que é onde a
                 seleção de fato mora.

                 NA ENTREGA só dinheiro é aceito (`invalid_on_delivery_tender_payment`,
                 recusado no commit). A tela oferecia cartão e Pix, o operador
                 combinava por telefone, e a recusa vinha no Validar. -->
            <button
              v-for="method in injectableMethods"
              :key="method.ref"
              type="button"
              class="flex h-11 items-center gap-3 rounded-md border bg-card px-3 text-left text-sm font-medium transition hover:border-primary/50 hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="onDeliveryCash && method.ref !== 'cash'"
              :title="onDeliveryCash && method.ref !== 'cash' ? 'Na entrega só dinheiro; receba no caixa para usar esta forma' : undefined"
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
              {{ formatBRL(note) }}
            </button>
          </div>
          </div>
        </section>

        <!-- A NOTA FISCAL SAIU DAQUI. Ela não é instrumento de cobrança: é o
             que sai do pedido, e por isso mora na coluna do PEDIDO, colada
             embaixo do que está sendo cobrado. Aqui ela empurrava o teclado
             para cima e disputava a coluna com ele. -->

        <!-- AÇÕES DA VENDA — o que age sobre o VALOR, embaixo do que age sobre
             a LINHA. Voltaram do rodapé: lá elas dividiam a barra com o Validar,
             e ação de venda perto do botão que fecha a venda é o clique errado
             do balcão cheio. Aqui ficam na mão que já está na coluna, logo
             abaixo do teclado, e a barra fica só com o comando.
             A seção é contratual: some inteira quando a loja não oferece
             desconto nem a conta comporta divisão. -->
        <section v-if="discountTypes.length" class="grid gap-1.5" aria-label="Ações da venda">
          <h3 class="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Ações da venda</h3>

          <button
            type="button"
            class="flex h-11 items-center gap-2 rounded-md border px-3 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            :class="hasDiscount ? 'border-primary bg-primary/5 text-foreground' : 'bg-card text-muted-foreground'"
            @click="discountSheetOpen = true"
          >
            <Icon name="lucide:tag" class="size-4 shrink-0" />
            <span class="min-w-0 truncate">{{ hasDiscount ? `Desconto global ${discountSummary}` : "Desconto global" }}</span>
            <kbd class="ml-auto shrink-0 rounded border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-muted-foreground" aria-hidden="true">F8</kbd>
          </button>

          <!-- DIVIDIR A CONTA — "somos três, cada um paga o seu".
               Ligado, cada toque numa forma de pagamento lança UMA parte, já
               calculada (os centavos fecham sozinhos, e a última parcela leva o
               que restou mesmo depois de o operador editar alguma linha). O
               operador não faz conta de cabeça com os três clientes olhando.
               Tocar de novo no mesmo número desliga: mudar de ideia é rotina.
               Quanto pedir a quem está na frente é a INSTRUÇÃO do momento, e
               por isso vai para o rodapé, em letra que se lê de longe. -->
          <div class="flex items-center gap-1.5 rounded-md border bg-card p-1.5" role="group" aria-label="Dividir conta">
            <span class="shrink-0 px-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">Dividir conta</span>
            <UiButton
              v-for="n in SPLIT_PRESETS"
              :key="n"
              type="button"
              variant="outline"
              size="sm"
              class="h-9 min-w-0 flex-1 p-0 tabular-nums"
              :class="splitCount === n ? 'border-primary bg-primary/10 font-bold' : ''"
              :aria-pressed="splitCount === n"
              :aria-label="`Dividir a conta em ${n} pessoas`"
              @click="$emit('setSplitCount', n)"
            >
              {{ n }}
            </UiButton>
          </div>
        </section>

        <!-- O MOTIVO DO BOTÃO TRAVADO SAIU DAQUI. Ele era um parágrafo de 12px
             preso entre a Nota fiscal e o Validar, no fim de uma coluna que
             ROLA — num monitor de 768px de altura, com a nota aberta, a frase
             que explicava o bloqueio ficava fora da tela junto com o botão que
             ela explicava. Agora mora na faixa de ALERTAS da coluna do valor,
             que não rola, tem largura de sobra e cabe uma ação de um toque.
             O Voltar/Validar foi para o RODAPÉ FIXO, no fim deste arquivo. -->
      </div>

      <!-- MEIO · o EIXO DA TELA, em três faixas de altura estável: INSTRUÇÕES no
           topo (o que finalizar vai fazer), o VALOR no centro (o número que o
           operador diz em voz alta) e os ALERTAS embaixo (o que falta, com o
           caminho), encostados no rodapé onde o Validar mora.

           Antes, esses três assuntos estavam em quatro lugares diferentes: a
           instrução da cozinha era uma linha de 12px sob o total; os avisos da
           review ficavam soltos no meio da coluna; o motivo do botão travado
           estava lá na coluna da esquerda, apertado entre a Nota fiscal e o
           Validar; e as consequências ("sai na bobina", "o entregador leva o
           troco") viviam como legenda dos próprios campos. Nada disso era lido.

           A regra do lugar único: em cima o que ACONTECE, embaixo o que FALTA.
           Nesta coluna espaço é o que mais sobra, então o texto tem corpo de
           leitura — aviso em 12px ao lado de um número em 96px não é aviso.

           A largura é a que resta das duas colunas fixas; por isso o total
           escala com a janela (no `xl` a faixa do meio é a mais estreita das
           três configurações, e um `text-8xl` ali transbordava). -->
      <div class="order-1 flex min-h-0 min-w-0 flex-1 flex-col gap-3 py-1 lg:order-none">

        <!-- AVISOS — o que finalizar VAI fazer, e o que a review RESSALVA.
             Nada aqui pede ação: o que pede ação mora no rodapé, encostado no
             botão que ele destrava. É esse o corte entre as duas faixas, e não
             a severidade — um aviso com botão longe do botão principal é o
             operador olhando para dois lugares na mesma decisão. -->
        <ul
          v-if="notices.length"
          class="flex shrink-0 flex-col gap-1.5"
          aria-label="Avisos"
          aria-live="polite"
        >
          <li
            v-for="note in notices"
            :key="note.key"
            class="flex items-center gap-3 rounded-md border p-3"
            :class="note.tone === 'block'
              ? 'border-warning bg-warning/10 text-amber-700 dark:text-amber-400'
              : note.tone === 'warn'
                ? 'border-warning/60 bg-warning/10 text-amber-700 dark:text-amber-400'
                : 'border-border bg-muted text-muted-foreground'"
          >
            <Icon
              :name="note.icon"
              class="shrink-0"
              :class="[note.tone === 'block' ? 'size-6' : 'size-4', note.accent || '']"
            />
            <span class="min-w-0 flex-1">
              <span
                class="block leading-snug"
                :class="note.tone === 'block' ? 'text-lg font-semibold' : 'text-sm font-medium'"
              >{{ note.message }}</span>
              <span v-if="note.hint" class="mt-0.5 block text-sm leading-snug opacity-80">{{ note.hint }}</span>
            </span>
            <UiButton
              v-if="note.action"
              size="lg"
              variant="outline"
              class="h-11 shrink-0"
              @click="note.action.run()"
            >
              {{ note.action.label }}
            </UiButton>
          </li>
        </ul>

        <!-- O NÚMERO QUE MUDA É O HERÓI. O total é estável — o operador já o leu
             em voz alta na tela de venda, e ele volta nas linhas de pagamento e
             no resumo à direita. O TROCO não: ele nasce agora, é dito agora, e
             é dinheiro que sai da gaveta. Ele ocupava `text-3xl` num canto
             enquanto o total, três vezes maior, dominava a tela — a hierarquia
             invertida bem na hora em que o erro custa dinheiro de verdade.
             Com troco na mesa, os dois trocam de lugar; o total não some, só
             recolhe para uma linha de conferência. -->
        <section
          class="flex min-h-0 flex-1 flex-col items-center justify-center text-center"
          :aria-label="payState === 'change' ? 'Troco' : 'Total a cobrar'"
          aria-live="polite"
        >
          <p class="text-xs font-medium uppercase tracking-wide" :class="payState === 'change' ? 'text-primary' : 'text-muted-foreground'">
            {{ payState === "change" ? "Troco" : "Total a cobrar" }}
          </p>
          <p
            class="text-4xl font-bold tabular-nums tracking-tight xl:text-6xl 2xl:text-8xl"
            :class="payState === 'change' ? 'text-primary' : ''"
          >
            {{ payState === "change" ? formatBRL(paymentChangeQ) : (review ? review.total_display : interimTotalDisplay) }}
          </p>
          <p v-if="payState === 'change'" class="mt-2 text-sm tabular-nums text-muted-foreground">
            Total a cobrar {{ review ? review.total_display : interimTotalDisplay }}
          </p>
        </section>

        <!-- linhas de pagamento + troco/restante -->
        <div v-if="tenderLines.length" class="shrink-0 border-t pt-3">
          <ul class="flex flex-col gap-1.5">
            <!-- SELECIONAR e REMOVER são irmãos, não pai e filho. O remover
                 era um `<button>` dentro do `<button>` da linha: markup
                 inválido, nome acessível da linha contaminado pelo do remover, e
                 o gesto que APAGA uma forma de pagamento dividindo alvo com o
                 que apenas a seleciona — separados só por um `@click.stop`. -->
            <li
              v-for="(tender, idx) in tenderLines"
              :key="idx"
              class="flex h-11 items-center gap-1 rounded-md border pr-1 transition"
              :class="idx === selectedTenderIndex ? 'border-primary bg-primary/5' : 'hover:bg-accent/60'"
            >
              <button
                type="button"
                class="flex h-full min-w-0 flex-1 items-center justify-between gap-2 rounded-l-md px-3 text-left"
                :aria-current="idx === selectedTenderIndex ? 'true' : undefined"
                :aria-label="`Editar ${tender.label} de ${tender.amountDisplay}`"
                @click="$emit('selectTender', idx)"
              >
                <span class="flex min-w-0 items-center gap-2 text-sm font-medium">
                  <Icon :name="tender.icon" class="size-4 shrink-0" />
                  <span class="truncate">{{ tender.label }}</span>
                </span>
                <strong class="shrink-0 text-lg tabular-nums">{{ tender.amountDisplay }}</strong>
              </button>
              <UiButton
                variant="ghost"
                size="icon-sm"
                class="shrink-0"
                :aria-label="`Remover ${tender.label} de ${tender.amountDisplay}`"
                @click="$emit('removeTender', idx)"
              >
                <Icon name="lucide:x" class="size-4 text-destructive" />
              </UiButton>
            </li>
          </ul>
          <!-- O que FALTA. O rótulo e o número precisam concordar: com o total
               coberto era "Pago R$ 0,00", que se lê como "não pagou nada" justo
               quando o cliente acabou de entregar o dinheiro. O que zera ali é o
               que falta, então o rótulo é "Restante".
               Com troco na mesa esta linha se cala — o troco virou o herói ali
               em cima, e o mesmo número em dois tamanhos na mesma coluna é o
               operador procurando qual dos dois vale. -->
          <div v-if="payState !== 'change'" class="mt-2 flex items-center justify-between gap-2 px-1">
            <span class="text-sm font-medium uppercase tracking-wide text-muted-foreground">Restante</span>
            <strong
              class="text-3xl font-bold tabular-nums"
              :class="payState === 'ready' ? 'text-muted-foreground' : ''"
            >
              {{ formatBRL(Math.max(0, paymentRemainingQ)) }}
            </strong>
          </div>
        </div>

        <!-- A FAIXA DE ALERTAS SAIU DAQUI para o RODAPÉ. O que trava o Validar
             tem que ser lido ao lado do Validar: aqui embaixo, a frase e o botão
             que ela explica ficavam a meia tela de distância um do outro, e o
             olho que vai para o botão não passava por ela. -->
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
      <!-- A coluna do PEDIDO deixou de ser `hidden` abaixo de `lg`. Ela guarda
           agora a Nota fiscal, e uma coluna que some leva as três perguntas
           fiscais com ela — abaixo de 1024px o operador não teria onde dizer
           "CPF na nota?". Agora as três colunas empilham em vez de sumir: o
           corte de layout virou `lg`, e abaixo dele a tela é uma coluna só. -->
      <div class="order-3 flex min-h-0 flex-col gap-3 overflow-y-auto lg:order-none lg:w-[360px] lg:shrink-0">
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

            <!-- O BLOCO DE TOTAIS só existe quando há o que EXPLICAR: sem
                 desconto e sem taxa, o total é a soma das linhas e o herói já o
                 diz em 96px — repeti-lo aqui é uma linha que não informa nada.
                 Quando aparece, FECHA a própria conta (termina no Total): um
                 bloco que abre a aritmética e não a fecha obriga o operador a
                 somar de cabeça com o cliente perguntando. -->
            <dl
              v-if="review && (review.discount_q > 0 || review.delivery_fee_q > 0)"
              class="grid gap-1 border-t px-3 py-2 text-sm"
            >
              <!-- ⚠️ HAVIA DUAS LINHAS DE DESCONTO, E ELAS CONTAVAM A MESMA
                   CORTESIA. "Desconto nos itens" era `lineSavingsQ` = etiqueta −
                   COBRADO, e o cobrado já reflete o desconto manual de linha
                   quando ele vence. "Desconto do operador" era `review.
                   discount_q`, que soma o desconto do PEDIDO e o de LINHA. Numa
                   linha com cortesia de 10% e nenhuma promoção automática, as
                   duas exibiam EXATAMENTE o mesmo número, uma acima e outra
                   abaixo do Subtotal, na mesma coluna de valores — e só uma
                   delas fecha a aritmética. O operador somava as duas com o olho.

                   Ficou uma: a do servidor, que é a que leva o subtotal ao
                   total. O desconto que veio da ETIQUETA continua dito onde ele
                   acontece — riscado na linha, com o motivo ao lado —, que é
                   onde o cliente pergunta.

                   ⚠️ Resíduo conhecido: `subtotal_q` do servidor é a soma dos
                   `unit_price_q` (PRÉ-desconto manual de linha) e as linhas aqui
                   em cima mostram o COBRADO (pós). Com cortesia de linha, somar
                   as linhas com o olho não dá o Subtotal — dá o Total. Fechar
                   isso pede a review separar `order_discount_q` de
                   `line_discount_q`, que hoje ela não separa. -->
              <template v-if="review">
                <div class="flex items-baseline justify-between gap-2">
                  <dt class="text-muted-foreground">Subtotal</dt>
                  <dd class="tabular-nums">{{ review.subtotal_display }}</dd>
                </div>
                <div v-if="review.discount_q > 0" class="flex items-baseline justify-between gap-2 text-primary">
                  <dt>Desconto</dt>
                  <dd class="tabular-nums">−{{ review.discount_display }}</dd>
                </div>
                <div v-if="review.delivery_fee_q > 0" class="flex items-baseline justify-between gap-2">
                  <dt class="text-muted-foreground">Taxa de entrega</dt>
                  <dd class="tabular-nums">{{ review.delivery_fee_display }}</dd>
                </div>
                <div class="flex items-baseline justify-between gap-2 border-t pt-1 font-semibold">
                  <dt>Total</dt>
                  <dd class="tabular-nums">{{ review.total_display }}</dd>
                </div>
              </template>
            </dl>
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
        <section v-if="supportsFiscalDocument" class="grid shrink-0 gap-1.5" aria-label="Nota fiscal">
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
                  :maxlength="18"
                  @update:model-value="$emit('update:invoiceTaxId', String($event || '').replace(/\D/g, '').slice(0, 14))"
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
              <!-- A consequência ("sai na bobina") subiu para as instruções: é o
                   que finalizar VAI fazer, e o operador precisa disso à vista, não
                   em 12px dentro de um switch. -->
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

        <!-- VALIDAR — fixo no fim da COLUNA DO PEDIDO, e não numa barra que
             atravessa a tela. A barra inteira roubava a largura das três colunas
             para carregar dois botões, e punha uma faixa horizontal cortando o
             desenho justamente embaixo do valor.
             Aqui ele encerra a coluna que responde "o que estou cobrando": a
             lista, o que ela soma, o que sai na nota e, por fim, o botão que
             fecha. É a ordem da leitura, de cima para baixo, numa coluna só.

             O VOLTAR não está aqui. Ele já existe na barra do topo — a mesma
             setinha de todas as telas do sistema — e um segundo botão de voltar
             ao lado do que FECHA a venda é o clique errado do balcão cheio.
             O Esc continua valendo. -->
        <UiButton
          size="lg"
          class="h-14 w-full shrink-0 gap-2 text-base"
          :disabled="ctaDisabled"
          :loading="loading || needsReview"
          @click="onCta"
        >
          {{ ctaLabel }}
          <kbd class="rounded border border-primary-foreground/30 bg-transparent px-1.5 py-0.5 font-mono text-xs font-medium opacity-80" aria-hidden="true">Enter</kbd>
        </UiButton>
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
        <!-- "backend" era a única palavra de implementação em toda a copy do
             PDV. E o diálogo fechava sem dizer o número que o operador vai falar
             em voz alta — ele aplicava 15% e só descobria o total depois. -->
        <UiDialogDescription>Tipo, valor e motivo. A loja confere e aplica.</UiDialogDescription>
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
        <UiDialogFooter class="sm:flex-col sm:items-stretch sm:gap-2">
          <p v-if="review" class="text-center text-sm text-muted-foreground">
            Fica <strong class="font-semibold tabular-nums text-foreground">{{ review.total_display }}</strong>
          </p>
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
