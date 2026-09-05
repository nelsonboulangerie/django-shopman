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
  cashNoteLabel,
  changeForShortfallQ,
  collectionsForFulfillment,
  injectableMethods as toInjectableMethods,
  machineTenderLines,
  methodShortcuts,
  nonCashExcessQ,
  paymentIcon,
  SPLIT_PRESETS,
  splitShareQ,
  tenderLineView,
} from "~/presentation/payment";
import { firedKitchenQty, kitchenHandoffNote, kitchenSurplusQty } from "~/presentation/kitchen";
import {
  lineDiscountBadge,
  lineListTotalDisplay,
  lineTotalQ,
} from "~/presentation/lineDiscounts";
import { managerAuthReason } from "../../../operator-kit/app/presentation/managerAuth";
import type { CustomerDecision } from "~/presentation/customerDecision";
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
  /** A escolha pendente do operador (conflito/correção de contato). */
  customerDecision?: CustomerDecision | null;
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
  /** Quem CONTINUA operando depois da assinatura do gerente. Ver OperatorManagerAuth. */
  operatorName?: string;
  fulfillmentType: "pickup" | "delivery";
  paymentCollection: "terminal" | "on_delivery";
  paymentTenders: POSPaymentTenderDraft[];
  /** Em quantas pessoas a conta está dividida (0 = sem divisão). */
  splitCount: number;
  /** Quantas partes já foram lançadas — é o que separa "armado" de "em uso". */
  splitPaidCount: number;
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
  /** A última revisão FALHOU (rede). Sem isto, a tela ficava com o botão
   *  desabilitado e o spinner de "Atualizando…" para sempre. */
  reviewFailed?: boolean;
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
  decisionConfirm: [];
  decisionCancel: [];
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
const splitSheetOpen = ref(false);

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

// ── AJUSTES DA CONTA: "ativado" e "em uso" são estados DIFERENTES ───────────
//
// O par desconto/divisão age sobre o VALOR, e o operador precisa ler de relance
// se está agindo — um botão que não muda de cara quando está ligado obriga a
// abrir o modal só para conferir, com o cliente na frente.
//
// São dois estados, e o botão mostra os dois: ARMADO (a divisão existe, nada
// lançado ainda) e EM USO (já tem parte paga). A distinção não é preciosismo:
// desarmar uma divisão armada é gratuito, desarmar uma em uso mexe em linhas de
// pagamento que já estão na tela.
const splitActive = computed(() => props.splitCount > 0);
const splitInProgress = computed(() => splitActive.value && props.splitPaidCount > 0);
/** "3" enquanto armado; "1/3" a partir da primeira parte lançada. */
const splitBadge = computed(() => (
  splitInProgress.value ? `${props.splitPaidCount}/${props.splitCount}` : String(props.splitCount)
));
/** Quanto ficaria cada parte se a conta fosse dividida em `n` — preview do modal. */
function splitShareLabel(n: number): string {
  return formatBRL(splitShareQ(props.paymentTotalQ, n, props.splitPaidCount, props.paymentRemainingQ));
}

// O RESUMO DO PEDIDO — o que está sendo cobrado. No checkout o operador via só
// o total: um número sem os itens que o compõem, justo na hora em que o cliente
// pergunta "por que deu isso?". Vem do mesmo carrinho da tela de venda; a tela
// mostra, não recalcula.
const summaryLines = computed(() =>
  props.items.map((item) => ({
    // A CHAVE é a linha, não o produto: duas linhas do mesmo item na comanda
    // (uma já na cozinha, outra nova) davam `:key` repetido, e o Vue passava a
    // reaproveitar o nó errado ao reordenar o resumo.
    lineId: item.line_id,
    name: item.name,
    qty: item.qty,
    totalDisplay: formatBRL(lineTotalQ(item)),
    /** A etiqueta riscada, quando o que se cobra é menor. "" quando não há. */
    listDisplay: lineListTotalDisplay(item),
    /** POR QUE está mais barato — o desconto que venceu a linha. */
    discountLabel: lineDiscountBadge(item, props.discountReasons),
  })),
);
// A review separou os dois escopos do desconto? Um payload antigo (em voo no
// meio de um deploy) traz só o total, e aí o bloco volta a mostrar uma linha só.
const discountByScope = computed(
  () => !!props.review && (props.review.line_discount_q > 0 || props.review.order_discount_q > 0),
);
const summaryUnits = computed(() => props.items.reduce((sum, item) => sum + item.qty, 0));

// Kitchen clarity: tell the operator, unequivocally, what finalizing will do
// vs what was already fired — so it's never a mystery whether food was sent.
/** Unidades que a cozinha já tem em mãos — acende o destaque da frase. */
const firedUnits = computed(() => firedKitchenQty(props.items));
/** Unidades que o fogão está fazendo e a conta não cobra — ver `kitchenSurplusQty`. */
const kitchenSurplus = computed(() => props.items.reduce((total, item) => total + kitchenSurplusQty(item), 0));
// A frase é presentation PURA (`kitchenHandoffNote`): ela conta unidades, como o
// botão de enviar, e não linhas — "1 item já está na cozinha" com três chás numa
// linha só era o número errado no lugar onde o operador confere o que já saiu.
const kitchenNote = computed(() => kitchenHandoffNote(props.items));

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

// ── O LINK COBRA A VENDA INTEIRA ─────────────────────────────────────────
//
// Ele é a única forma do balcão que depende de uma cobrança REMOTA, e ela só é
// criada quando a venda é dele sozinho (`payment.initiate`). Em venda MISTA o
// servidor liquidaria o link como se o dinheiro já tivesse entrado, sem gerar
// URL nenhuma — venda paga, cliente sem link, dinheiro que nunca chega.
//
// A tela impede antes, e SEM apagar o que o operador já digitou: quem estiver
// lançado desabilita o outro lado. O servidor recusa de todo jeito
// (`link_requires_full_payment`); isto aqui é a gêmea, não a trava.
// A CONFERÊNCIA DA MAQUININHA. Crédito e débito não passam por gateway: o
// cartão é passado no terminal físico e o valor é DIGITADO à mão. Errar um
// dígito ali é cobrar do cliente um valor que a venda não conhece — e o sistema
// só descobre no fechamento do dia, quando a adquirente não bate com o livro.
// Um passo visual antes de fechar é o que separa "o operador leu o valor" de
// "o operador lembrou o valor".
//
// ⚠️ Sai de cena inteiro quando o TEF da Stone entrar: ali o terminal recebe o
// valor pela API e não há o que conferir. Ver docs/plans/WP-PAGAMENTO-LINK-E-TEF.md.
const machineTenders = computed(() => machineTenderLines(tenderLines.value));
const machineConfirmOpen = ref(false);

const hasLinkTender = computed(() => props.paymentTenders.some((tender) => tender.method === "link"));
const hasNonLinkTender = computed(() => props.paymentTenders.some((tender) => tender.method !== "link"));
/** Dá para dividir a conta AGORA? O link cobra a venda inteira, então ele fecha
 *  a porta — a não ser que a divisão já esteja armada, e aí o modal é por onde
 *  se desfaz. UMA verdade só: o botão e a tecla F10 leem daqui, senão o teclado
 *  abriria um modal que o dedo não consegue abrir. */
const splitAvailable = computed(() => !(hasLinkTender.value && !splitActive.value));
/** Este método está indisponível AGORA por causa da exclusividade do link? */
function blockedByLink(ref: string): boolean {
  return ref === "link" ? hasNonLinkTender.value : hasLinkTender.value;
}

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
  // A revisão falhou: o botão deixa de fingir que está carregando e vira a
  // própria saída. Girar para sempre é a tela mentindo sobre o que está fazendo.
  if (props.reviewFailed) return "Tentar de novo";
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
  if (props.reviewFailed) {
    return {
      message: "Não deu para atualizar o total.",
      hint: "Confira a conexão e tente de novo.",
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
  // `link_requires_full_payment` — a gêmea. Ver `hasLinkTender` acima.
  if (hasLinkTender.value && hasNonLinkTender.value) {
    return {
      message: "O link cobra a venda inteira.",
      hint: "Remova as outras formas, ou troque o link por uma delas.",
    };
  }
  // `link_requires_customer_contact` — o link é uma URL que alguém precisa
  // RECEBER. Sem telefone nem e-mail, a venda fecha aguardando um pagamento que
  // ninguém vai pedir, e a URL só volta pelo gestor.
  if (hasLinkTender.value && !props.customerPhone.trim() && !props.customerEmail.trim()) {
    return {
      message: "O link precisa de um contato.",
      hint: "Telefone ou e-mail — é por onde ele vai.",
      action: { label: "Identificar cliente", run: () => { customerSheetOpen.value = true; } },
    };
  }
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
  // A COZINHA PREPAROU MAIS DO QUE A CONTA COBRA. Fica ao lado do Validar
  // porque é ali que a diferença vira prejuízo: o operador está prestes a cobrar
  // por 1 o que o fogão fez 3 vezes. Não trava a venda — reduzir a linha é
  // gesto legítimo (o cliente desistiu) —, mas ninguém fecha sem ter lido.
  if (kitchenSurplus.value > 0) {
    notes.push({
      key: "kitchen_surplus",
      tone: "warn",
      icon: "lucide:triangle-alert",
      message: `A cozinha preparou ${kitchenSurplus.value} ${kitchenSurplus.value === 1 ? "item" : "itens"} a mais do que esta conta cobra.`,
      hint: "Cancele o envio da linha, ou avise o preparo — a diferença sai sem pagamento.",
    });
  }
  if (props.items.length && kitchenNote.value) {
    notes.push({
      key: "kitchen",
      icon: "lucide:flame",
      accent: firedUnits.value ? "text-primary" : "",
      message: kitchenNote.value,
    });
  }
  // O troco que SAI COM O ENTREGADOR. Era legenda do próprio campo, lá na coluna
  // que rola; é consequência de finalizar, e por isso mora aqui.
  if (onDeliveryCash.value && props.changeForInput.trim() && changeForShortfall.value <= 0) {
    notes.push({ key: "courier", icon: "lucide:banknote", message: "O entregador sai com o troco separado." });
  }
  if (wantsPrintedReceipt.value) {
    // AGORA A FRASE PODE DIZER QUE A NOTA SAI. Não existe DANFE sem NFC-e
    // autorizada — o papel é o espelho da nota —, então pedir papel é pedir a
    // nota, e a regra fiscal do servidor lê este canal e emite. Antes o toggle
    // não decidia nada: dinheiro sem CPF ligava "Impressa?", não gerava nota
    // nenhuma e nada saía na bobina, calado.
    //
    // O "assim que autorizar" fica: a emissão é assíncrona e quem autoriza é a
    // SEFAZ. Prometer o instante seria a segunda mentira.
    notes.push({ key: "print", icon: "lucide:printer", message: "Pedir papel já pede a nota — imprime sozinha assim que autorizar." });
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
  if (!props.items.length || props.loading) return true;
  // Com a revisão falhada o botão VOLTA a clicar: ele é o retry.
  if (props.reviewFailed) return false;
  if (needsReview.value) return true;
  return ctaBlock.value !== null;
});

function onCta() {
  // O retry passa pelo MESMO `submit` do shell, que já sabe pedir a revisão
  // quando ela falta (`submitSale`: sem review, revisa em vez de fechar). Um
  // caminho paralelo aqui seria um segundo lugar decidindo quando revisar.
  if (props.reviewFailed) { emit("submit"); return; }
  if (needsAuth.value) { managerAuthOpen.value = true; return; }
  proceed();
}
/** O último degrau antes de fechar: a maquininha, quando ela é quem cobra.
 *  Depois da autorização do gerente, nunca antes — o cartão só é passado quando
 *  a venda já está liberada. */
function proceed() {
  if (machineTenders.value.length) { machineConfirmOpen.value = true; return; }
  emit("submit");
}
function onManagerAuthorize(username: string, pin: string) {
  emit("update:managerUsername", username);
  emit("update:managerPin", pin);
  managerAuthOpen.value = false;
  proceed();
}
function onMachineConfirmed() {
  machineConfirmOpen.value = false;
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
  /** O irmão do desconto: os dois Ajustes da conta abrem pela mesma dupla de
   *  teclas. Recusa quando o botão recusa — uma tecla que abre o que o dedo não
   *  abre é a tela dizendo duas coisas ao mesmo tempo. */
  openSplit: () => {
    if (!splitAvailable.value) return;
    splitSheetOpen.value = true;
  },
  /** F liga/desliga "CPF na nota?" — a pergunta fiscal mais feita no balcão.
   *  E LEVA O FOCO ao campo que acabou de aparecer. Sem isso o foco ficava no
   *  `body`, e o shell captura todo dígito fora de input quando há linha de
   *  pagamento selecionada: o operador apertava a tecla, digitava o CPF de
   *  reflexo, e os onze dígitos entravam no numpad — R$ 66,30 virava
   *  R$ 5.299.822,47 com um "TROCO" a condizer. Um Enter depois, por hábito, e a
   *  venda fechava.
   *
   *  Devolve se a tecla teve dono: sem NFC-e no contrato a seção não existe, e
   *  não há o que ligar. */
  toggleCpfOnInvoice: () => {
    if (!supportsFiscalDocument.value) return false;
    const next = !props.wantsCpfOnInvoice;
    emit("update:wantsCpfOnInvoice", next);
    if (next) focusByAriaLabel("CPF que sai na nota");
    return true;
  },
  /** Uma letra digitada no checkout lança a forma correspondente. Devolve se
   *  achou dono — o shell só consome a tecla quando ela virou ação. */
  pressMethodKey: (letter: string) => {
    const ref = Object.keys(methodKeys.value).find((key) => methodKeys.value[key] === letter);
    if (!ref) return false;
    emit("addTender", ref);
    return true;
  },
  /** I e M — os dois canais do comprovante, pela letra. Com o F do CPF, são as
   *  três teclas da seção Nota fiscal, e `methodShortcuts` reserva as três para
   *  que nenhuma forma de pagamento nova as tome pela inicial do rótulo.
   *
   *  Não são teclas de função porque não sobrou nenhuma: F1 é ajuda, F5 é
   *  reload, F11 é tela-cheia (que o quiosque usa) e F12 abre o DevTools ANTES
   *  de a página ver a tecla. De F2 a F10 está tudo tomado.
   *
   *  ⚠️ E não é "E" de e-mail: o E já é a inicial de "Em conta", que aparece
   *  para cliente com conta na casa. Seriam duas ações na mesma tecla, e a
   *  errada dispararia calada — o defeito que as letras das formas de pagamento
   *  acabaram de deixar de ter.
   *
   *  Devolve se a tecla teve dono: sem NFC-e no contrato, a seção não existe e a
   *  letra segue o caminho dela (a busca de produto). */
  pressReceiptKey: (letter: string) => {
    if (!supportsFiscalDocument.value) return false;
    if (letter === "I") { setReceiptChannel("print", !wantsPrintedReceipt.value); return true; }
    if (letter === "M") {
      const next = !wantsEmailReceipt.value;
      setReceiptChannel("email", next);
      // Ligar o canal e não ter onde escrever é um bloqueio a caminho: leva o
      // foco ao campo, como o F faz com o CPF.
      if (next) focusByAriaLabel("E-mail que recebe a nota");
      return true;
    }
    return false;
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
        <!-- AJUSTES DA CONTA — desconto e divisão, ACIMA da forma de pagamento
             porque é essa a ordem da conversa do balcão: primeiro se acerta
             QUANTO a conta vale, depois em QUANTAS PARTES ela sai, e só então
             se encosta num tender. Decidir na ordem inversa é refazer trabalho —
             o desconto muda o valor de cada parte, e ligar a divisão depois de
             lançar dinheiro não reparte o que já está na tela.
             Vinham do rodapé desta coluna, abaixo do teclado: lugar aonde o
             operador só chega DEPOIS de já ter lançado a primeira forma.

             DUAS COLUNAS, e é a forma que os separa. As formas de pagamento são
             uma pilha vertical de linha inteira; estes são um par lado a lado.
             Mesma altura e mesma borda para não virarem outra família visual —
             só o arranjo diz que agem sobre o VALOR, e não que recebem dinheiro.

             O desconto é contratual (a loja pode não oferecer nenhum tipo); a
             divisão não depende de contrato nenhum, é aritmética da tela. As
             duas moravam sob um `v-if="discountTypes.length"` — uma loja sem
             tipo de desconto cadastrado perdia TAMBÉM o dividir conta. -->
        <section class="grid gap-1.5" aria-label="Ajustes da conta">
          <h3 class="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Ajustes da conta</h3>
          <div class="grid grid-cols-2 gap-1.5">
            <button
              v-if="discountTypes.length"
              type="button"
              class="flex h-11 items-center gap-2 rounded-md border px-3 text-sm font-medium transition hover:bg-accent active:translate-y-px"
              :class="hasDiscount ? 'border-primary bg-primary/5 text-foreground' : 'bg-card text-muted-foreground'"
              :aria-pressed="hasDiscount"
              :aria-label="hasDiscount ? `Desconto de ${discountSummary} na venda. Abrir para alterar` : 'Desconto na venda'"
              @click="discountSheetOpen = true"
            >
              <Icon name="lucide:tag" class="size-4 shrink-0" />
              <span class="min-w-0 flex-1 truncate text-left">Desconto</span>
              <!-- O BADGE É O ESTADO. Ligado, o botão diz o quanto — ninguém
                   precisa abrir o modal para conferir se há desconto e de que
                   tamanho. Desligado, o mesmo canto carrega o atalho. -->
              <UiBadge v-if="hasDiscount" class="shrink-0 tabular-nums">−{{ discountSummary }}</UiBadge>
              <kbd
                v-else
                class="shrink-0 rounded border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-muted-foreground"
                aria-hidden="true"
              >F9</kbd>
            </button>

            <button
              type="button"
              class="flex h-11 items-center gap-2 rounded-md border px-3 text-sm font-medium transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
              :class="[
                splitActive ? 'border-primary bg-primary/5 text-foreground' : 'bg-card text-muted-foreground',
                discountTypes.length ? '' : 'col-span-2',
              ]"
              :disabled="!splitAvailable"
              :title="hasLinkTender ? 'O link de pagamento cobra a venda inteira' : undefined"
              :aria-pressed="splitActive"
              :aria-label="splitActive
                ? `Conta dividida em ${splitCount}, ${splitPaidCount} de ${splitCount} lançadas. Abrir para alterar`
                : 'Dividir conta'"
              @click="splitSheetOpen = true"
            >
              <Icon name="lucide:users" class="size-4 shrink-0" />
              <span class="min-w-0 flex-1 truncate text-left">Dividir conta</span>
              <!-- "3" enquanto armado, "1/3" a partir da primeira parte: ARMADO
                   e EM USO são estados diferentes, e o segundo é o que impede o
                   operador de desligar a divisão sem perceber que já lançou. -->
              <UiBadge v-if="splitActive" class="shrink-0 tabular-nums">{{ splitBadge }}</UiBadge>
              <!-- Mesmo canto do vizinho: ligado, o badge diz o estado;
                   desligado, ele carrega o atalho. -->
              <kbd
                v-else
                class="shrink-0 rounded border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-muted-foreground"
                aria-hidden="true"
              >F10</kbd>
            </button>
          </div>
        </section>

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
              :disabled="(onDeliveryCash && method.ref !== 'cash') || blockedByLink(method.ref)"
              :title="onDeliveryCash && method.ref !== 'cash'
                ? 'Na entrega só dinheiro; receba no caixa para usar esta forma'
                : blockedByLink(method.ref)
                  ? 'O link de pagamento cobra a venda inteira'
                  : undefined"
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
          <div class="grid gap-1.5" :class="cashSelected ? 'flex-[3] basis-0' : 'flex-1'">
          <div class="grid grid-cols-3 gap-1.5" role="group" aria-label="Teclado de valor">
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
          </div>
            <!-- Exato: a linha selecionada assume o que as OUTRAS deixam devendo
                 (venda coberta, troco zero) — tecla '='. Limpar (C): zera a linha
                 inteira para digitar; o Backspace apaga um dígito por vez.
                 ⚠️ Os dois saíram de DENTRO da grade de 3 colunas. Lá o "Limpar"
                 vivia numa coluna de dígito — largura de um "7" — com ícone,
                 rótulo e o texto vazando por cima da borda assim que o trilho de
                 cédulas aparecia e estreitava o teclado. Em linha própria, cada
                 um tem metade da largura do teclado e o rótulo cabe em qualquer
                 zoom; `min-w-0` + `truncate` fecham a porta do estouro. -->
            <div class="grid grid-cols-2 gap-1.5">
            <button
              type="button"
              class="flex h-11 min-w-0 items-center justify-center gap-1.5 rounded-md border bg-card px-2 text-sm font-semibold transition hover:bg-accent active:translate-y-px disabled:opacity-40"
              :disabled="!numpadActive"
              aria-label="Exato: a linha assume o restante"
              title="A forma selecionada assume o que falta para cobrir o total (=)"
              @click="$emit('tenderExact')"
            >
              <span class="truncate">Exato</span>
              <kbd class="shrink-0 rounded border bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-muted-foreground" aria-hidden="true">=</kbd>
            </button>
            <button
              type="button"
              class="flex h-11 min-w-0 items-center justify-center gap-1.5 rounded-md border bg-card px-2 text-sm font-semibold transition hover:bg-accent active:translate-y-px disabled:opacity-40"
              :disabled="!numpadActive"
              aria-label="Limpar: zera o valor da linha"
              title="Zera o valor da linha inteira (o Backspace apaga um dígito)"
              @click="$emit('tenderClear')"
            >
              <Icon name="lucide:eraser" class="size-4 shrink-0 text-muted-foreground" />
              <span class="truncate">Limpar</span>
            </button>
            </div>
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
              {{ cashNoteLabel(note) }}
            </button>
          </div>
          </div>
        </section>

        <!-- A NOTA FISCAL SAIU DAQUI. Ela não é instrumento de cobrança: é o
             que sai do pedido, e por isso mora na coluna do PEDIDO, colada
             embaixo do que está sendo cobrado. Aqui ela empurrava o teclado
             para cima e disputava a coluna com ele. -->


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
          <!-- ⚠️ `flex-wrap`: o número é grande e a coluna do meio encolhe. Em
               1024px (e em qualquer zoom que aperte a coluna) "RESTANTE" mais um
               valor em `text-3xl` não cabiam na linha — e como texto não quebra
               nem encolhe sozinho, o valor VAZAVA por cima do botão Validar, na
               coluna vizinha. Quebrando, o número desce para a própria linha em
               vez de invadir o botão que fecha a venda. -->
          <div v-if="payState !== 'change'" class="mt-2 flex flex-wrap items-baseline justify-between gap-x-2 px-1">
            <span class="shrink-0 text-sm font-medium uppercase tracking-wide text-muted-foreground">Restante</span>
            <strong
              class="ml-auto text-3xl font-bold tabular-nums"
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
              <li v-for="line in summaryLines" :key="line.lineId" class="px-3 py-2">
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
              <!-- CADA DESCONTO NA SUA LINHA, com o escopo no rótulo.
                   Um mecanismo, dois escopos: o que o operador deu no ITEM (no
                   carrinho) e o que deu na VENDA (no F8 aqui do lado). Somam o
                   `discount_q`, e o servidor publica os dois separados.

                   ⚠️ Isto fecha um vão que a tela tinha e não explicava: as
                   linhas acima são listadas pelo preço COBRADO, e o `Subtotal` é
                   a soma dos `unit_price_q` — PRÉ desconto manual de linha. Com
                   uma cortesia por item, somar as linhas com o olho não dava o
                   Subtotal, dava o Total. A conta fechava, mas só para quem
                   soubesse que o desconto ali dentro tinha duas origens. Agora a
                   diferença tem nome.

                   ⚠️ E houve um erro pior antes disso: "Desconto nos itens" era
                   calculado na TELA como etiqueta − cobrado, e o cobrado já
                   refletia a cortesia de linha. Ela e "Desconto do operador"
                   exibiam o MESMO número, uma acima e outra abaixo do Subtotal.
                   Os dois números agora vêm do servidor e são disjuntos. -->
              <template v-if="review">
                <div class="flex items-baseline justify-between gap-2">
                  <dt class="text-muted-foreground">Subtotal</dt>
                  <dd class="tabular-nums">{{ review.subtotal_display }}</dd>
                </div>
                <template v-if="discountByScope">
                  <div v-if="review.line_discount_q > 0" class="flex items-baseline justify-between gap-2 text-primary">
                    <dt>Desconto nos itens</dt>
                    <dd class="tabular-nums">−{{ review.line_discount_display }}</dd>
                  </div>
                  <div v-if="review.order_discount_q > 0" class="flex items-baseline justify-between gap-2 text-primary">
                    <dt>Desconto na venda</dt>
                    <dd class="tabular-nums">−{{ review.order_discount_display }}</dd>
                  </div>
                </template>
                <!-- A review não separou os escopos (payload em voo no meio de um
                     deploy): a linha volta a ser uma só. Um bloco que abre
                     "Subtotal" e "Taxa" e ESCONDE o desconto não fica incompleto
                     — fica MENTINDO, porque as três linhas visíveis deixam de
                     somar o total. Somar errado é pior do que detalhar de menos. -->
                <div v-else-if="review.discount_q > 0" class="flex items-baseline justify-between gap-2 text-primary">
                  <dt>Descontos</dt>
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
                <kbd class="ml-auto shrink-0 rounded border bg-muted px-1 py-0.5 font-mono text-xs font-medium text-muted-foreground" aria-hidden="true">F</kbd>
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
                <kbd class="ml-auto shrink-0 rounded border bg-muted px-1 py-0.5 font-mono text-xs font-medium text-muted-foreground" aria-hidden="true">I</kbd>
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
                <kbd class="ml-auto shrink-0 rounded border bg-muted px-1 py-0.5 font-mono text-xs font-medium text-muted-foreground" aria-hidden="true">M</kbd>
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
          :loading="(loading || needsReview) && !reviewFailed"
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
    :customer-decision="customerDecision"
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
    @decision-confirm="$emit('decisionConfirm')"
    @decision-cancel="$emit('decisionCancel')"
    @apply-customer-favorite="$emit('applyCustomerFavorite')"
    @repeat-customer-last-order="$emit('repeatCustomerLastOrder')"
  />

  <!-- MODAL: MAQUININHA — o valor que o operador vai digitar no terminal.
       Um passo, um número, um botão. Existe porque entre a tela e a maquininha
       hoje não há fio nenhum: quem transporta o valor é a memória de quem está
       atendendo, e o erro só aparece no fechamento do dia. Não pergunta se deu
       certo — se a maquininha recusar, o operador fecha o diálogo e troca a
       forma; a venda ainda não foi registrada. -->
  <UiDialog v-model:open="machineConfirmOpen">
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader>
        <UiDialogTitle>Passe na maquininha</UiDialogTitle>
        <UiDialogDescription>Digite este valor no terminal e conclua a operação com o cliente.</UiDialogDescription>
      </UiDialogHeader>
      <div class="grid gap-2">
        <!-- As DUAS coisas que o operador vai reproduzir na maquininha têm o
             mesmo peso: a função (crédito ou débito — teclas diferentes, prazos
             e taxas diferentes) e o valor. A forma vem primeiro, em pastilha
             cheia: é a primeira escolha no teclado do terminal, e a única que a
             maquininha não perdoa em silêncio. -->
        <div
          v-for="line in machineTenders"
          :key="line.method"
          class="grid justify-items-center gap-3 rounded-md border border-primary/30 bg-primary/5 px-4 py-7"
        >
          <p class="flex items-center gap-2 rounded-full bg-primary px-4 py-1.5 text-base font-bold uppercase tracking-widest text-primary-foreground">
            <Icon :name="line.icon" class="size-5 shrink-0" />
            {{ line.label }}
          </p>
          <p class="text-5xl font-bold tabular-nums tracking-tight text-primary">{{ line.amountDisplay }}</p>
        </div>
      </div>
      <UiDialogFooter class="sm:flex-col sm:items-stretch sm:gap-2">
        <UiButton size="lg" class="h-12 text-base" @click="onMachineConfirmed">
          OK, cobrei na maquininha
        </UiButton>
        <UiButton variant="ghost" size="sm" @click="machineConfirmOpen = false">Voltar</UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>

  <!-- MODAL: Dividir conta — o irmão do de Desconto, e de propósito.
       Era um trilho de cinco botões preso na coluna: ocupava altura fixa em
       TODA venda para uma pergunta que quase nunca se faz, e não tinha onde
       dizer quanto cada parte fica. Como modal, o botão guarda o estado no
       badge e o modal guarda a explicação.
       Escolher o número JÁ É a decisão inteira — por isso o toque fecha o
       modal, sem "Concluir". Só o desfazer fica, porque desfazer com partes já
       lançadas merece uma frase antes. -->
  <UiDialog v-model:open="splitSheetOpen">
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-md">
      <UiDialogHeader>
        <UiDialogTitle>Dividir conta</UiDialogTitle>
        <UiDialogDescription>
          Em quantas pessoas. Cada toque numa forma de pagamento lança uma parte já calculada — os centavos fecham sozinhos.
        </UiDialogDescription>
      </UiDialogHeader>
      <div class="grid gap-4">
        <p
          v-if="hasLinkTender"
          class="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-700 dark:text-amber-400"
        >
          <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
          <span>O link de pagamento cobra a venda inteira. Remova a linha do link para dividir.</span>
        </p>
        <div class="grid grid-cols-5 gap-1.5" role="group" aria-label="Em quantas pessoas">
          <!-- Cada preset mostra QUANTO FICA CADA PARTE. Sem isso o operador
               escolhe o número e só descobre o valor ao lançar a primeira
               forma — com o cliente já perguntando "quanto deu o meu?". -->
          <UiButton
            v-for="n in SPLIT_PRESETS"
            :key="n"
            type="button"
            variant="outline"
            class="h-14 flex-col gap-0.5 p-0 tabular-nums"
            :class="splitCount === n ? 'border-primary bg-primary/5' : ''"
            :disabled="hasLinkTender"
            :aria-pressed="splitCount === n"
            :aria-label="`Dividir em ${n} pessoas, ${splitShareLabel(n)} cada`"
            @click="$emit('setSplitCount', n); splitSheetOpen = false"
          >
            <span class="text-lg font-semibold leading-none">{{ n }}</span>
            <span class="text-xs font-normal leading-none text-muted-foreground">{{ splitShareLabel(n) }}</span>
          </UiButton>
        </div>
      </div>
      <UiDialogFooter class="sm:flex-col sm:items-stretch sm:gap-2">
        <p v-if="splitNote" class="text-center text-sm text-muted-foreground">{{ splitNote }}</p>
        <template v-if="splitActive">
          <UiButton variant="outline" class="w-full" @click="$emit('setSplitCount', 0); splitSheetOpen = false">
            Não dividir
          </UiButton>
          <p v-if="splitInProgress" class="text-center text-xs text-muted-foreground">
            As partes já lançadas continuam na conta — remova cada linha de pagamento se quiser recomeçar.
          </p>
        </template>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>

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
  <OperatorManagerAuth
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
