<script setup lang="ts">
import { toast } from "vue-sonner";

import { resolveAffordance } from "~/presentation/actions";
import { requiresOpenShiftForSale } from "~/presentation/cash";
import { rollStyle } from "~/presentation/printGeometry";
import { enterAdvances } from "~/presentation/saleResult";
import { globalKeysBlocked } from "~/utils/keyboardGuard";
// Tela de VENDA — wires the read-side (usePosTerminal) and write-side (usePosSale)
// composables to the three core screens (PosTabBoard / PosProductGrid /
// PosPaymentWorkspace). O chrome comum (login, lock, offline) vive no shell
// (app.vue); a sessão de caixa (abrir/fechar/movimentos) vive na antesala
// (`/session`) — sem turno aberto, esta página manda o operador pra lá.
useHead({ title: "Shopman POS" });

const apiPath = usePosApiPath();
const action = usePosAction();
const runtimeConfig = useRuntimeConfig();
// The Django admin (login) lives on its own operator host (api.<zona>), a different
// subdomain from the POS — so the DANFE link must be ABSOLUTE to that host, not
// relative to the POS origin.
const djangoOrigin = computed(() => String(runtimeConfig.public.djangoPublicBaseUrl || ""));
// Gestor de Pedidos (orders-nuxt) — destino do link pós-venda "Abrir no gestor".
const ordersUrl = computed(() => String(runtimeConfig.public.ordersUrl || ""));
const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

const { pos, tabs, actions, pending, refresh } = await usePosTerminal();

// ANTESALA (benchmark Odoo): sem turno aberto não há venda — o operador cai no
// lobby de sessão para abrir o caixa. O gate lê o contrato da Projection.
if (
  pos.value
  && requiresOpenShiftForSale(pos.value.checkout?.capabilities?.cash_management)
  && !pos.value.has_open_cash_session
) {
  await navigateTo("/session", { replace: true });
}

// Identidade do operador — mesmo estado compartilhado do shell (useFetch deduplicado).
const OPERATOR_PERM = "cashman.operate_pos";
const { operator: activeOperator, locked, lock } = useOperatorLock(OPERATOR_PERM);

async function goToCashSession() {
  await navigateTo("/session");
}

// Write-side of the open sale: cart draft + every session command.
const {
  cart,
  tabInput,
  busy,
  saving,
  unsaved,
  firing,
  cancellingSale,
  cancelSaleReason,
  cancelSaleDialogOpen,
  cancelSaleError,
  lookupBusy,
  managerApprovalError,
  result,
  pendingPixOrderRef,
  pixStatus,
  checkoutMode,
  moveDialogOpen,
  review,
  customerLookup,
  tabDialogOpen,
  selectedTenderIndex,
  checkoutContract,
  canRenameTab,
  tabManipulation,
  canCancelRecentSale,
  saleCorrection,
  tabMaxLength,
  tabPlaceholder,
  tabDisallowedChars,
  tabZeroPadTo,
  tabDraftTargetStates,
  tabRequiredForCart,
  addressAutocomplete,
  hasOpenTab,
  inSaleView,
  hasDraftWithoutTab,
  canUseCart,
  paymentTotalQ,
  paymentRemainingQ,
  paymentChangeQ,
  paymentCovered,
  selectedTenderMethod,
  tabDialogTitle,
  tabDialogDescription,
  sortedTabs,
  otherOpenTabs,
  suggestedSplitRef,
  goToTabs,
  addTender,
  removeTender,
  selectTender,
  tenderDigit,
  tenderComma,
  tenderBackspace,
  tenderClear,
  tenderAdd,
  tenderExact,
  productQty,
  addProduct,
  setQty,
  restoreItem,
  setLineNotes,
  setLineDiscount,
  setLinePrice,
  requestTabAssociation,
  openTab,
  openTabFromDialog,
  applySavedAddress,
  lookupCustomer,
  resolveCustomer,
  customerSearchResults,
  customerSearchBusy,
  customerResolvedNew,
  searchCustomers,
  selectCustomerResult,
  clearCustomer,
  applyCustomerFavorite,
  repeatCustomerLastOrder,
  prepareCheckout,
  reviewCheckout,
  submitSale,
  dismissResult,
  onExternalSaleCancelled,
  clearCurrentTab,
  openMoveDialog,
  submitMove,
  fireTab,
  unfireTab,
  unfireSelected,
  renameTab,
  openCancelSaleDialog,
  cancelRecentSale,
  cancelRecentSaleWithBadge,
  drawerLock,
} = usePosSale({ pos, tabs, actions, refresh, action, apiPath, requestHeaders, ordersUrl });

// Tela do cliente (segundo monitor): fontes lidas por getter; publicação e
// transformação vivem inteiras no <PosDisplayPublisher> (renderless). O troco
// congelado já viaja dentro do `result` (`changeQ`).
const displaySources = { pos: () => pos.value, items: () => cart.items, review: () => review.value, result: () => result.value, pixStatus: () => pixStatus.value, checkoutMode: () => checkoutMode.value };

// Auto-lock ciente do pagamento: o shell (app.vue) lê este sinal e ADIA o lock
// de ociosidade enquanto o checkout está aberto ou um PIX segue aguardando —
// travar no meio do pagamento derrubava o operador com o cliente na frente.
const paymentHold = useState("pos-payment-hold", () => false);
watchEffect(() => {
  paymentHold.value = checkoutMode.value || pixStatus.value === "polling";
});
onBeforeUnmount(() => {
  paymentHold.value = false;
});

// Kitchen handoff affordances (spec §2.5): the fire/unfire CTAs come from the
// Projection's Actions (label + enabled), never invented in the screen.
const fireAction = computed(() => resolveAffordance(actions.value, "fire_tab"));
const unfireAction = computed(() => resolveAffordance(actions.value, "unfire_tab"));

// Top context bar title (unified layout language, Arc 5): one band names the
// current work-area screen across Board / Sale / Payment.
const screenTitle = computed(() => {
  if (result.value) return "Venda concluída";
  if (checkoutMode.value) return cart.tabDisplay ? `Pagamento · #${cart.tabDisplay}` : "Pagamento";
  if (inSaleView.value) return cart.tabDisplay || "Venda";
  return "Comandas";
});

// Últimas vendas: a nota autoriza DEPOIS da tela de confirmação passar; o
// painel é onde imprimir/reenviar/reprocessar moram, a qualquer hora do turno.
const recentSalesOpen = ref(false);

// Impressão pós-venda: o agente do balcão é o caminho primário (ESC/POS que o
// SERVIDOR compôs, na bobina), tanto para o recibo quanto para a DANFE — o
// mesmo transporte e leiaute das Últimas vendas, para o papel sair igual não
// importa de onde se imprime.
const agent = useCounterAgent(pos);
const printingReceipt = ref(false);
const printingDanfe = ref(false);

async function fetchPrintable(orderRef: string, endpoint: "receipt-escpos" | "danfe-escpos") {
  return await $fetch<{ payload_b64: string; title: string }>(
    apiPath(`/api/v1/backstage/pos/orders/${encodeURIComponent(orderRef)}/${endpoint}/`),
    { credentials: "include" },
  );
}

// Recibo da venda: agente primeiro; sem agente (ou com ele caído), o caminho é
// o D3 de sempre — window.print sobre o #pos-print-area — só que AVISADO. O
// fallback silencioso fazia o operador achar que a bobina imprimiu.
async function printReceipt() {
  if (!import.meta.client || !result.value) return;
  if (agent.canKick.value) {
    printingReceipt.value = true;
    try {
      const receipt = await fetchPrintable(result.value.orderRef, "receipt-escpos");
      const outcome = await agent.print(receipt.payload_b64, receipt.title);
      if (outcome.status === "printed") return;
      toast.warning(`A impressora do balcão não respondeu: ${outcome.detail || "sem detalhe"}. O recibo saiu pelo diálogo do navegador.`);
    } catch (error) {
      toast.warning(`${httpErrorMessage(error, "Falha ao compor o recibo no servidor.")} O recibo saiu pelo diálogo do navegador.`);
    } finally {
      printingReceipt.value = false;
    }
  }
  window.print();
}

// DANFE em bobina, mesma rota das Últimas vendas. A prévia web (host do
// Django) virou porta secundária: link só para quem o servidor diz que entra.
function danfePreviewUrl(orderRef: string): string {
  return `${djangoOrigin.value}/fiscal/danfe/${encodeURIComponent(orderRef)}/`;
}

async function printDanfe() {
  if (!import.meta.client || !result.value) return;
  const orderRef = result.value.orderRef;
  printingDanfe.value = true;
  try {
    const danfe = await fetchPrintable(orderRef, "danfe-escpos");
    const outcome = await agent.print(danfe.payload_b64, danfe.title);
    if (outcome.status === "printed") {
      toast.success("DANFE na impressora.");
      return;
    }
    danfeFallbackToast(orderRef, outcome.detail || "impressão indisponível nesta estação");
  } catch (error) {
    // 409 = a emissão é assíncrona e a nota ainda não autorizou.
    danfeFallbackToast(orderRef, httpErrorMessage(error, "Falha ao compor a DANFE."));
  } finally {
    printingDanfe.value = false;
  }
}

// Falha nunca termina em "indisponível" seco: quem tem acesso ganha a prévia
// web como ação; quem não tem ganha o próximo passo.
function danfeFallbackToast(orderRef: string, reason: string) {
  if (pos.value?.danfe_preview_allowed && djangoOrigin.value) {
    toast.error(`A DANFE não saiu na bobina: ${reason}`, {
      action: {
        label: "Abrir prévia web",
        onClick: () => window.open(danfePreviewUrl(orderRef), "_blank", "noopener"),
      },
    });
  } else {
    toast.error(`A DANFE não saiu na bobina: ${reason}. Reimprima nas últimas vendas quando o agente voltar.`);
  }
}

// Geometria do rolo: o terminal declara, o `@page` obedece. Vai no `<html>`
// porque as custom properties do print CSS moram no `:root` — e fica aqui, na
// tela que imprime, e não no shell, para a var existir exatamente onde o recibo
// existe. Terminal que não declara devolve "", e aí o default de 80mm do CSS
// manda (o default tem um dono só, que é o CSS).
useHead({ htmlAttrs: { style: computed(() => rollStyle(pos.value)) } });

// Keyboard and scanner (spec: F2 tab board, F3 product search, F4 checkout/review,
// F6 customer modal, Enter validates a covered checkout, Escape backs out of
// checkout, "/" focuses product search when not editing, "?" opens the help).
const tabBoardRef = ref<{ focus: () => void } | null>(null);
const productGridRef = ref<{ focusSearch: (seed?: string) => void } | null>(null);
const tabHeaderRef = ref<{ openCustomer: () => void } | null>(null);
const paymentWorkspaceRef = ref<{ validate: () => void; openCustomer: () => void } | null>(null);
const shortcutsHelpOpen = ref(false);

async function gotoTabInput() {
  checkoutMode.value = false;
  await nextTick();
  tabBoardRef.value?.focus();
}

// Sai da tela de resultado para o quadro de comandas — o CTA "Nova venda", o
// F2 e o Enter passam todos por aqui (PIX pendente vira chip no composable).
async function startNextSale() {
  dismissResult();
  await nextTick();
  tabBoardRef.value?.focus();
}

// Prévia web da DANFE na tela de resultado: só para quem o servidor deixa.
const resultDanfePreviewUrl = computed(() =>
  result.value && pos.value?.danfe_preview_allowed && djangoOrigin.value
    ? danfePreviewUrl(result.value.orderRef)
    : "",
);

async function gotoProductSearch() {
  if (!canUseCart.value) return;
  checkoutMode.value = false;
  await nextTick();
  productGridRef.value?.focusSearch();
}

function onGlobalKeydown(event: KeyboardEvent) {
  if (locked.value || !pos.value) return;
  // Terminal travado ou diálogo aberto: NENHUM atalho global age. A página
  // continua montada sob o overlay de identificação e sob qualquer diálogo —
  // sem a guarda, o crachá (token com dígitos) e o PIN do gerente digitados ali
  // alimentavam o numpad de tender, e Esc/F2/F3/F4 agiam por baixo do modal
  // (Esc fechava o diálogo E derrubava o checkout).
  if (globalKeysBlocked()) return;
  const target = event.target as HTMLElement | null;
  const isEditing = !!target
    && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);

  // TELA DE RESULTADO: F2 avança sempre (gesto explícito); Enter só quando não
  // há troco pendente de confirmação nem PIX aguardando (o Enter que validou a
  // venda não pode engolir a tela do troco). Os demais atalhos não agem — a
  // tela por baixo (board) não é o que o operador vê.
  if (result.value) {
    if (event.key === "F2") {
      event.preventDefault();
      startNextSale();
      return;
    }
    if (
      event.key === "Enter" && !isEditing
      && enterAdvances({ changeQ: result.value.changeQ, payment: result.value.payment, pixStatus: pixStatus.value })
    ) {
      event.preventDefault();
      startNextSale();
      return;
    }
    if (event.key === "?" && !isEditing) {
      event.preventDefault();
      shortcutsHelpOpen.value = true;
    }
    return;
  }

  // On the payment screen, the physical keyboard drives the value numpad of the
  // SELECTED tender (like the order screen's numpad): digits type, comma/period
  // enters centavos, Backspace trims. Requires a form already chosen.
  if (checkoutMode.value && !isEditing && !event.metaKey && !event.ctrlKey && !event.altKey && selectedTenderIndex.value >= 0) {
    if (event.key >= "0" && event.key <= "9") {
      event.preventDefault();
      tenderDigit(event.key);
      return;
    }
    if (event.key === "," || event.key === "." || event.key === "Decimal") {
      event.preventDefault();
      tenderComma();
      return;
    }
    if (event.key === "Backspace") {
      event.preventDefault();
      tenderBackspace();
      return;
    }
  }

  // Search-as-you-type (Odoo): na tela de venda, uma LETRA digitada fora de
  // input começa a busca de produto com aquele caractere (dígitos seguem
  // editando a linha ativa — comportamento do numpad do carrinho).
  if (
    inSaleView.value && !checkoutMode.value && !isEditing
    && !event.metaKey && !event.ctrlKey && !event.altKey
    && event.key.length === 1 && /\p{L}/u.test(event.key)
  ) {
    event.preventDefault();
    productGridRef.value?.focusSearch(event.key);
    return;
  }

  switch (event.key) {
    case "Escape":
      if (checkoutMode.value) {
        event.preventDefault();
        checkoutMode.value = false;
      }
      return;
    case "F2":
      event.preventDefault();
      gotoTabInput();
      return;
    case "F3":
      event.preventDefault();
      gotoProductSearch();
      return;
    case "F4":
      event.preventDefault();
      if (checkoutMode.value) reviewCheckout();
      else if (cart.items.length) prepareCheckout();
      return;
    case "F6":
      event.preventDefault();
      if (checkoutMode.value) paymentWorkspaceRef.value?.openCustomer();
      else if (inSaleView.value) tabHeaderRef.value?.openCustomer();
      return;
    case "Enter":
      // Total coberto + review fresca → Enter valida, pelo MESMO caminho do
      // clique (inclusive a porta da autorização gerencial). Review velha ou
      // total descoberto seguem no F4/no botão — Enter nunca finaliza no escuro.
      if (checkoutMode.value && !isEditing && review.value && paymentCovered.value && !busy.value) {
        event.preventDefault();
        paymentWorkspaceRef.value?.validate();
      }
      return;
    case "?":
      if (!isEditing) {
        event.preventDefault();
        shortcutsHelpOpen.value = true;
      }
      return;
    case "/":
      if (!isEditing) {
        event.preventDefault();
        gotoProductSearch();
      }
  }
}

onMounted(() => window.addEventListener("keydown", onGlobalKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onGlobalKeydown));
</script>

<template>
  <main class="flex flex-wrap content-start min-h-dvh bg-background text-foreground md:h-[100dvh] md:min-h-0 md:flex-nowrap md:overflow-hidden">
    <PosFunctionRail
      v-if="pos"
      :pos="pos"
      :has-open-cash-session="pos.has_open_cash_session"
      :operator-name="activeOperator?.name || ''"
      :pending="pending"
      :view="checkoutMode ? 'checkout' : (inSaleView ? 'sale' : 'board')"
      @board="goToTabs"
      @cash="goToCashSession"
      @lock="lock()"
      @refresh="refresh()"
    />

    <div class="flex min-w-0 flex-1 flex-col md:min-h-0 md:overflow-hidden">
      <header v-if="pos" class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2">
        <!-- Controle do rail (kit): cicla colapsado/compacto/estendido; mora no cabeçalho
             para que o rail suma por inteiro quando colapsado. -->
        <RailToggle />
        <UiButton
          v-if="inSaleView"
          variant="ghost"
          size="icon-sm"
          class="-ml-1 shrink-0"
          :aria-label="checkoutMode ? 'Voltar à comanda' : 'Voltar para comandas'"
          :title="checkoutMode ? 'Voltar à comanda' : 'Comandas'"
          @click="checkoutMode ? (checkoutMode = false) : goToTabs()"
        >
          <Icon name="lucide:arrow-left" class="size-5" />
        </UiButton>
        <span
          v-if="inSaleView && !checkoutMode && unsaved"
          class="inline-flex shrink-0 items-center gap-1 rounded-md border border-warning/50 bg-warning/10 px-2 py-1 text-xs font-medium text-amber-700 dark:text-amber-400"
          role="status"
          title="A comanda não pôde ser salva — tentando de novo"
        >
          <Icon name="lucide:cloud-off" class="size-3.5" /> Não salvo
        </span>
        <PosTabHeader
          v-if="inSaleView && !checkoutMode"
          ref="tabHeaderRef"
          v-model:customer-name="cart.customerName"
          v-model:customer-phone="cart.customerPhone"
          v-model:customer-tax-id="cart.customerTaxId"
          v-model:customer-email="cart.customerEmail"
          class="min-w-0 flex-1"
          :tab-display="cart.tabDisplay"
          :has-open-tab="hasOpenTab"
          :can-rename="canRenameTab"
          :customer-lookup="customerLookup"
          :lookup-busy="lookupBusy"
          :search-results="customerSearchResults"
          :search-busy="customerSearchBusy"
          :customer-resolved-new="customerResolvedNew"
          :loading="busy"
          @rename="renameTab"
          @clear="clearCurrentTab"
          @clear-customer="clearCustomer"
          @lookup-customer="lookupCustomer"
          @resolve-customer="resolveCustomer"
          @search="searchCustomers"
          @select-result="selectCustomerResult"
          @apply-customer-favorite="applyCustomerFavorite"
          @repeat-customer-last-order="repeatCustomerLastOrder"
        />
        <h1 v-else class="min-w-0 truncate text-lg font-semibold leading-tight tracking-tight">{{ screenTitle }}</h1>
        <!-- PIX pendente que saiu da tela de resultado: chip compacto, com o
             polling seguindo por baixo até resolver/expirar (aí vira toast). -->
        <span
          v-if="pendingPixOrderRef"
          class="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-info/40 bg-info/10 px-2 py-1 text-xs font-medium text-info"
          role="status"
          :title="`PIX do pedido ${pendingPixOrderRef} aguardando confirmação`"
        >
          <Icon name="lucide:loader-circle" class="size-3.5 animate-spin motion-reduce:animate-none" />
          PIX aguardando · <span class="font-mono">{{ pendingPixOrderRef }}</span>
        </span>
        <UiButton
          variant="ghost"
          size="icon-sm"
          class="ml-auto shrink-0"
          aria-label="Atalhos do teclado"
          title="Atalhos do teclado (?)"
          @click="shortcutsHelpOpen = true"
        >
          <Icon name="lucide:keyboard" class="size-5" />
        </UiButton>
        <UiButton
          variant="ghost"
          size="icon-sm"
          class="shrink-0"
          aria-label="Últimas vendas"
          title="Últimas vendas (status fiscal, DANFE, reenvio)"
          @click="recentSalesOpen = true"
        >
          <Icon name="lucide:history" class="size-5" />
        </UiButton>
      </header>

      <div class="flex min-h-0 w-full flex-1 flex-col gap-3 px-4 py-3 md:min-h-0 md:overflow-hidden">
      <div class="flex-1 md:min-h-0 md:overflow-hidden">
      <!-- TELA DE RESULTADO — substitui o banner de antes: tela cheia no fluxo
           de venda, com o troco congelado como herói e "Nova venda" dominante. -->
      <div v-if="result" class="h-full md:overflow-y-auto">
        <PosSaleResult
          :result="result"
          :pix-status="pixStatus"
          :can-cancel="canCancelRecentSale"
          :danfe-preview-url="resultDanfePreviewUrl"
          :printing-receipt="printingReceipt"
          :printing-danfe="printingDanfe"
          @new-sale="startNextSale"
          @print-receipt="printReceipt"
          @print-danfe="printDanfe"
          @cancel-sale="openCancelSaleDialog"
        />
      </div>

      <div v-else-if="checkoutMode" class="h-full md:overflow-y-auto">
      <PosPaymentWorkspace
        ref="paymentWorkspaceRef"
        v-model:discount-type="cart.discountType"
        v-model:discount-value="cart.discountValue"
        v-model:discount-reason="cart.discountReason"
        v-model:manager-username="cart.managerUsername"
        v-model:manager-pin="cart.managerPin"
        :manager-approval-error="managerApprovalError"
        v-model:fulfillment-type="cart.fulfillmentType"
        v-model:payment-collection="cart.paymentCollection"
        v-model:customer-name="cart.customerName"
        v-model:customer-phone="cart.customerPhone"
        v-model:customer-tax-id="cart.customerTaxId"
        v-model:customer-email="cart.customerEmail"
        v-model:delivery-address="cart.deliveryAddress"
        v-model:delivery-address-structured="cart.deliveryAddressStructured"
        v-model:delivery-street-number="cart.deliveryStreetNumber"
        v-model:delivery-neighborhood="cart.deliveryNeighborhood"
        v-model:delivery-complement="cart.deliveryComplement"
        v-model:delivery-instructions="cart.deliveryInstructions"
        v-model:delivery-date="cart.deliveryDate"
        v-model:delivery-time-slot="cart.deliveryTimeSlot"
        v-model:delivery-fee-input="cart.deliveryFeeInput"
        v-model:order-notes="cart.orderNotes"
        v-model:issue-fiscal-document="cart.issueFiscalDocument"
        v-model:receipt-channels="cart.receiptChannels"
        v-model:receipt-email="cart.receiptEmail"
        :managers="pos?.managers || []"
        :tab-display="cart.tabDisplay"
        :items="cart.items"
        :has-open-tab="hasOpenTab"
        :fulfillment-options="pos?.fulfillment_options || []"
        :payment-methods="pos?.payment_methods || []"
        :payment-collections="pos?.payment_collections || []"
        :checkout-contract="checkoutContract"
        :address-autocomplete="addressAutocomplete"
        :customer-lookup="customerLookup"
        :search-results="customerSearchResults"
        :search-busy="customerSearchBusy"
        :customer-resolved-new="customerResolvedNew"
        :review="review"
        :discount-types="checkoutContract?.discount_types || []"
        :discount-reasons="checkoutContract?.discount_reasons || []"
        :payment-tenders="cart.paymentTenders"
        :selected-tender-index="selectedTenderIndex"
        :selected-tender-method="selectedTenderMethod"
        :payment-total-q="paymentTotalQ"
        :payment-remaining-q="paymentRemainingQ"
        :payment-change-q="paymentChangeQ"
        :payment-covered="paymentCovered"
        :loading="busy"
        :lookup-busy="lookupBusy"
        @back="checkoutMode = false"
        @submit="submitSale"
        @add-tender="addTender"
        @remove-tender="removeTender"
        @select-tender="selectTender"
        @tender-digit="tenderDigit"
        @tender-comma="tenderComma"
        @tender-backspace="tenderBackspace"
        @tender-clear="tenderClear"
        @tender-add="tenderAdd"
        @tender-exact="tenderExact"
        @lookup-customer="lookupCustomer"
        @resolve-customer="resolveCustomer"
        @search="searchCustomers"
        @select-result="selectCustomerResult"
        @clear-customer="clearCustomer"
        @apply-customer-favorite="applyCustomerFavorite"
        @repeat-customer-last-order="repeatCustomerLastOrder"
        @pick-saved-address="applySavedAddress"
      />
      </div>

      <div v-else class="h-full min-h-0">
        <!-- TABS VIEW — a tela de Comandas/Tabs é a PRIMEIRA (benchmark Odoo: tabs/mesas antes do pedido) -->
        <!-- `pos` nulo = ainda não sabemos o que existe (carregando, ou leitura
             negada). Mostrar o quadro nesse estado afirmaria "nenhuma comanda"
             sobre uma pergunta que nem foi respondida — e um balcão com comandas
             abertas leria isso como perda de dados. -->
        <PosTabBoard
          v-if="!inSaleView && pos"
          ref="tabBoardRef"
          v-model="tabInput"
          :tabs="tabs"
          :selected-tab-ref="cart.tabRef"
          :has-draft="hasDraftWithoutTab"
          :busy="busy"
          :max-length="tabMaxLength"
          :placeholder="tabPlaceholder"
          :disallowed-chars="tabDisallowedChars"
          :zero-pad-to="tabZeroPadTo"
          @open="openTab"
          @request-association="requestTabAssociation('start')"
        />
        <!-- Leitura ainda sem resposta: um aviso calmo, nunca um quadro vazio que
             finge saber.
             `!locked` porque antes do destravamento por PIN toda leitura volta
             403 `station_locked`, e este aviso desenhava wifi-off com "Não foi
             possível ler as comandas agora" — ou seja, mandava chamar suporte de
             rede na abertura de todo turno e a cada auto-lock. Não é falha de
             rede: é "você ainda não se identificou", e quem diz isso é a
             identificação que sobe por cima. -->
        <div v-else-if="!inSaleView && !locked" class="grid place-items-center p-8" data-tabs-unavailable>
          <p class="flex items-center gap-2 rounded-md border border-dashed px-4 py-6 text-sm text-muted-foreground">
            <Icon :name="pending ? 'line-md:loading-loop' : 'lucide:wifi-off'" class="size-4 shrink-0" />
            {{ pending ? "Carregando as comandas…" : "Não foi possível ler as comandas agora." }}
          </p>
        </div>

        <!-- SALE VIEW · product grid (the ticket/comanda is a full-height sibling
             of the work column, so it reaches the top edge like the rail) -->
        <PosProductGrid
          v-else
          ref="productGridRef"
          :products="pos?.products || []"
          :collections="pos?.collections || []"
          :favorite-refs="pos?.favorite_collection_refs || []"
          :cart-items="cart.items"
          :pending="pending"
          @add="addProduct"
        />
      </div>
      </div>
      </div>
    </div>

    <!-- TICKET / COMANDA — full-height right flank (cart-direita, reaches the top
         edge alongside the rail; on mobile it wraps below the product grid). -->
    <aside
      v-if="pos && inSaleView && !checkoutMode"
      class="flex w-full shrink-0 flex-col border-t border-border bg-card md:order-none md:h-full md:w-[360px] md:border-l md:border-t-0"
    >
        <div class="min-h-0 flex-1 md:overflow-hidden">
          <PosCartPanel
            :items="cart.items"
            :requires-tab="tabRequiredForCart"
            :has-open-tab="hasOpenTab"
            :loading="busy"
            :saving="saving"
            :fire-action="fireAction"
            :unfire-action="unfireAction"
            :firing="firing"
            :discount-reasons="checkoutContract?.discount_reasons || []"
            @increment="(sku) => setQty(sku, productQty(sku) + 1)"
            @decrement="(sku) => setQty(sku, productQty(sku) - 1)"
            @remove="(sku) => setQty(sku, 0)"
            @restore="restoreItem"
            @set-qty="(sku, qty) => setQty(sku, qty)"
            @set-notes="setLineNotes"
            @set-discount="setLineDiscount"
            @set-price="setLinePrice"
            @prepare="prepareCheckout"
            @move="openMoveDialog"
            @fire="fireTab"
            @unfire="unfireTab"
            @fire-lines="fireTab"
            @unfire-lines="unfireSelected"
            @request-tab="requestTabAssociation('start')"
          />
        </div>
    </aside>

    <PosTabPickerDialog
      v-model:open="tabDialogOpen"
      v-model="tabInput"
      :tabs="sortedTabs"
      :busy="busy || saving"
      :has-draft="hasDraftWithoutTab"
      :allowed-target-states="tabDraftTargetStates"
      :title="tabDialogTitle"
      :description="tabDialogDescription"
      :max-length="tabMaxLength"
      :placeholder="tabPlaceholder"
      :disallowed-chars="tabDisallowedChars"
      @confirm="openTabFromDialog"
      @select="openTabFromDialog"
    />

    <!-- A trava da gaveta: só aparece quando o sensor DISSE que está aberta.
         Fechar o diálogo desiste da venda que esperava; "já fechei" relê o
         sensor; o gerente libera pelo PIN e o destrave vai para o log. -->
    <PosDrawerLockDialog
      :open="drawerLock.open.value"
      :still-open="drawerLock.stillOpen.value"
      :busy="drawerLock.busy.value"
      @update:open="(value) => { if (!value) drawerLock.dismiss(); }"
      @recheck="drawerLock.recheck"
      @manager="drawerLock.askManager"
    />
    <PosManagerAuthDialog
      :open="drawerLock.managerOpen.value"
      reason-text="Liberar a próxima venda com a gaveta aberta."
      :managers="pos?.managers || []"
      :busy="drawerLock.busy.value"
      :error="drawerLock.managerError.value"
      @update:open="(value) => { if (!value) drawerLock.managerOpen.value = false; }"
      @authorize="drawerLock.unlock"
      @authorize-badge="drawerLock.unlockWithBadge"
    />

    <PosCancelSaleDialog
      v-model:open="cancelSaleDialogOpen"
      v-model:reason="cancelSaleReason"
      :order-ref="result?.orderRef || ''"
      :max-age-minutes="saleCorrection?.max_age_minutes || 0"
      :busy="cancellingSale"
      :error="cancelSaleError"
      :managers="pos?.managers"
      @confirm="cancelRecentSale"
      @confirm-badge="cancelRecentSaleWithBadge"
    />

    <PosMoveLinesDialog
      v-model:open="moveDialogOpen"
      :tab-display="cart.tabDisplay"
      :items="cart.items"
      :suggested-split-ref="suggestedSplitRef"
      :other-tabs="otherOpenTabs"
      :capability="tabManipulation"
      :busy="busy"
      @submit="submitMove"
    />

    <!-- D3 print surface: hidden on screen, the only thing printed in @media print.
         Vai para o `body` por Teleport de propósito — como irmão do app, o print
         CSS esconde o resto com `display: none` e a impressão pagina pelo recibo.
         Aninhado aqui dentro, só dava para escondê-lo com `visibility`, que mantém
         os boxes e fazia sair papel em branco depois do recibo. -->
    <Teleport to="body">
      <div v-if="result" id="pos-print-area">
        <PosReceipt
          :receipt="result.receipt"
          :terminal-label="pos?.terminal_label || 'Ponto de venda'"
          :payment-methods="pos?.payment_methods || []"
        />
      </div>
    </Teleport>
    <PosRecentSales v-model:open="recentSalesOpen" :pos="pos" @cancelled="onExternalSaleCancelled" />
    <PosShortcutsHelp v-model:open="shortcutsHelpOpen" />
    <PosDisplayPublisher :sources="displaySources" />
  </main>
</template>
