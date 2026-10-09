<script setup lang="ts">
import { tabTitleView } from "~/presentation/tabTitle";
import { toast } from "vue-sonner";

import type { ManagerApproval } from "~/composables/usePosCashSession";
import { resolveAffordance } from "~/presentation/actions";
import { openShiftGate, requiresOpenShiftForSale } from "~/presentation/cash";
import { ORDER_EDIT_CUSTOMER_LOCKED, ORDER_EDIT_LINE_ADJUSTMENTS_BLOCKED, orderEditTitle } from "~/presentation/orderEdit";
import { wantsNewOrder } from "~/presentation/orderSetup";
import { redoTabLabel } from "~/presentation/preorderActions";
import type { PreorderRedoResponse } from "~/types/preorders";
import { rollStyle } from "~/presentation/printGeometry";
import { scheduleChipTone, scheduledNeedsCustomer, scheduleLabel, selectedWindowConflict } from "~/presentation/schedule";
import { enterAdvances, paymentFailed, pixAwaiting } from "~/presentation/saleResult";
import { POS_SHORTCUT_GROUPS, POS_SHORTCUTS_DESCRIPTION } from "~/presentation/shortcuts";
import { globalKeysBlocked } from "~/utils/keyboardGuard";
// Tela de VENDA — wires the read-side (usePosTerminal) and write-side (usePosSale)
// composables to the three core screens (PosTabBoard / PosProductGrid /
// PosPaymentWorkspace). O chrome comum (login, lock, offline) vive no shell
// (app.vue); a sessão de caixa (abrir/fechar/movimentos) vive na antesala
// (`/session`) — sem turno aberto, esta página manda o operador pra lá.

// Mantém a divisória do carrinho alinhada ao contexto, inclusive quando as pills quebram linha.
const contextHeader = ref<HTMLElement | null>(null);
const { height: contextHeaderHeight } = useElementSize(contextHeader, undefined, { box: "border-box" });
// Rail da suíte oculto pelo menu das iniciais: a barra de contexto mostra o caminho de volta.
const { isCollapsed: railCollapsed, set: setRail } = useRailState();
// O ao vivo discreto da barra de contexto: estado do push e hora da última leitura.
const liveStatus = usePosLiveStatus();
// Tablet em pé e celular (v4 `pos-tablet.jpg`): a grade é a tela e a comanda vira a
// folha de baixo. Do desktop (1024px) para cima ela segue como coluna.
const ticketAsSheet = useMediaQuery("(max-width: 1023.98px)");

const apiPath = useApiPath();
const action = usePosAction();
const runtimeConfig = useRuntimeConfig();
// The Django admin (login) lives on its own operator host (api.<zona>), a different
// subdomain from the POS — so the DANFE link must be ABSOLUTE to that host, not
// relative to the POS origin.
const djangoOrigin = computed(() => String(runtimeConfig.public.djangoBaseUrl || ""));
// Gestor de Pedidos (orders-nuxt) — destino do link pós-venda "Abrir no gestor".
const ordersUrl = computed(() => String(runtimeConfig.public.ordersUrl || ""));
// Link de um app de operador para OUTRO: instalado, o destino tem janela
// própria. Quem decide `target`/`rel` é o kit — nunca um `_blank` escrito à mão.
const { attrsFor: crossAppAttrs } = useOperatorAppLink();
const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

const { pos, tabs, actions, pending, refresh } = await usePosTerminal();

// MODO EDIÇÃO (WP-E6): `/?edit=<ref>` abre esta mesma tela como o editor da
// encomenda — carrinho, grade, F7 e F8 —, com "Salvar alterações" no lugar do
// pagamento. Editar não mexe na gaveta: não pede turno aberto.
const editRef = String(useRoute().query.edit || "").trim();
// CANCELAR E REFAZER (WP-E6): `/?redo=<ref>` abre a venda na comanda comum
// "Refazer <ref>", que o detalhe da encomenda já montou no servidor depois do
// cancelamento. Sem caixa aberto a antesala manda abrir o caixa antes, como em
// qualquer venda — a comanda espera no quadro.
const redoRef = String(useRoute().query.redo || "").trim();
// NOVA ENCOMENDA: `/?new=order` (o botão da seção Encomendas) abre a próxima
// comanda livre já no modo Encomendas, com o assistente na primeira etapa que
// falta. A venda que estava em andamento continua na comanda dela, no quadro.
const newOrder = wantsNewOrder(useRoute().query);
const router = useRouter();

// ANTESALA (benchmark Odoo): sem turno aberto não há venda — o operador cai no
// lobby de sessão para abrir o caixa. O gate lê o contrato da Projection.
if (
  pos.value
  && !editRef
  && requiresOpenShiftForSale(pos.value.checkout?.capabilities?.cash_management)
  && !pos.value.has_open_cash_session
) {
  // `open=1`: quem veio vender cai direto no diálogo de abertura, com o
  // campo do fundo de troco focado — um toque a menos no começo do dia.
  // `next`: o que ele veio fazer (Nova encomenda, Refazer) espera do outro
  // lado; aberto o caixa, a antesala volta para cá com a mesma query.
  await navigateTo(openShiftGate(useRoute().fullPath), { replace: true });
}

// Identidade do operador — mesmo estado compartilhado do shell (useFetch deduplicado).
const OPERATOR_PERM = "cashman.operate_pos";
const { operator: activeOperator, locked, lock } = useOperatorLock(OPERATOR_PERM);

async function goToCashSession() {
  await navigateTo("/session");
}

// Tela do cliente: segunda janela desta máquina, para arrastar ao monitor virado ao
// cliente. A abertura (e a sonda de versão que vai junto) mora no composable.
const customerDisplayWindow = useCustomerDisplayWindow();
function openCustomerDisplay() {
  if (!customerDisplayWindow.open()) toast.error("O navegador bloqueou a Tela do Cliente.", {
    description: "Permita pop-ups para este site e tente novamente.",
  });
}

function notifyCustomerLocked(reason: string) {
  toast.info(reason);
}

// Write-side of the open sale: cart draft + every session command.
const {
  cart,
  orderSetupPending,
  orderSetupIssue,
  completeOrderSetup,
  setSalesMode,
  openNewOrder,
  itemCount,
  tabInput,
  busy,
  saving,
  unsaved,
  tabConflict,
  reloadConflictingTab,
  firing,
  cancellingSale,
  cancelSaleReason,
  cancelSaleDialogOpen,
  cancelSaleError,
  lookupBusy,
  managerApprovalError,
  customerFocusNonce,
  result,
  closeGuardNotice,
  restoreUncertainClose,
  acknowledgeUncertainClose,
  pendingPixOrderRef,
  pixStatus,
  checkoutMode,
  moveDialogOpen,
  movePreparing,
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
  deliveryFeeQ,
  deliveryFeeSource,
  deliveryFeeStatus,
  deliveryDistanceKm,
  deliverySlots,
  deliverySlotsPending,
  canonicalDeliverySlots,
  deliveryWindowLabel,
  deliveryDateEffective,
  scheduleToday,
  scheduleAvailableDates,
  scheduleBottleneckName,
  scheduleReadyAt,
  scheduleFailed,
  scheduleMaxDate,
  refreshSchedule,
  splitCount,
  splitPaidCount,
  splitNote,
  setSplitCount,
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
  lineQty,
  addProduct,
  weighedPrompt,
  addWeighedProduct,
  cancelWeighedPrompt,
  optionsPrompt,
  addOptionsProduct,
  cancelOptionsPrompt,
  setQty,
  restoreItem,
  setLineNotes,
  setLineDiscount,
  requestTabAssociation,
  openTab,
  openTabFromDialog,
  applySavedAddress,
  lookupCustomer,
  resolveCustomer,
  customerDecision,
  confirmCustomerDecision,
  cancelCustomerDecision,
  pickConflictCandidate,
  mergeConflictCustomers,
  customerMergeBusy,
  releaseConflictContact,
  customerReleaseBusy,
  customerSearchResults,
  customerSearchBusy,
  customerResolvedNew,
  pendingCustomerPrefs,
  applyCustomerPreference,
  searchCustomers,
  selectCustomerResult,
  clearCustomer,
  applyCustomerFavorite,
  repeatCustomerLastOrder,
  prepareCheckout,
  reviewCheckout,
  reviewFailed,
  reviewFailureReason,
  submitSale,
  dismissResult,
  markFiscalState,
  resendingLink,
  sendPaymentNotice,
  onExternalSaleCancelled,
  clearCurrentTab,
  loadPreparedTab,
  editIntent,
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
  drawerOpening,
} = usePosSale({ pos, tabs, actions, refresh, action, apiPath, requestHeaders, ordersUrl });

// ── Editar a encomenda (WP-E6) ────────────────────────────────────────────
const orderEdit = usePosOrderEdit();
const {
  editing,
  orderRef: editOrderRef,
  preview: editPreview,
  reviewOpen: editReviewOpen,
  busy: editBusy,
  error: editError,
  needsPaymentMethod: editNeedsMethod,
  deliveryPaymentMethod: editPaymentMethod,
  needsTaxId: editNeedsTaxId,
  deliveryTaxId: editTaxId,
  managerChallenge: editChallenge,
} = orderEdit;
const editManagerOpen = ref(false);

async function startOrderEdit(ref: string) {
  const tab = await orderEdit.start(ref);
  if (!tab) {
    toast.error(editError.value);
    await navigateTo(`/preorders/${encodeURIComponent(ref)}`);
    return;
  }
  await loadPreparedTab(tab);
}

/** Abre a comanda do refazer (idempotente: o servidor retoma a mesma) e limpa a URL. */
async function openRedoTab(ref: string) {
  try {
    const response = await action.call<PreorderRedoResponse>(
      `/api/v1/backstage/pos/preorders/${encodeURIComponent(ref)}/redo-tab/`,
      { body: {} },
    );
    // Abrir a venda nova é INICIAR uma venda: a trava da gaveta vale aqui.
    await drawerLock.guard(() => loadPreparedTab(response.tab));
    await refresh();
  } catch (err) {
    toast.error(`${httpErrorMessage(err, "Não deu para abrir a venda nova.")} Busque a comanda "${redoTabLabel(ref)}" no quadro.`);
  } finally {
    // Recarregar a página não pode montar a venda de novo.
    void router.replace({ path: "/", query: {} });
  }
}

/** Abre a encomenda nova e limpa a URL (recarregar não abre outra comanda). */
async function startNewOrder() {
  try {
    await openNewOrder();
  } finally {
    void router.replace({ path: "/", query: {} });
  }
}

/** F4 / "Salvar alterações": a prévia do servidor, antes de gravar. */
function saveOrderEdit() {
  if (!editing.value || !cart.items.length) return;
  void orderEdit.review(editIntent());
}

async function confirmOrderEdit(managerApproval: ManagerApproval | null = null) {
  // Encomenda paga que fica mais barata: o PIN sobe antes da ida ao servidor.
  if (editPreview.value?.requires_manager_approval && !managerApproval) {
    editManagerOpen.value = true;
    return;
  }
  const response = await orderEdit.confirm(editIntent(), managerApproval);
  if (!response) {
    editManagerOpen.value = Boolean(editChallenge.value);
    return;
  }
  editManagerOpen.value = false;
  const ref = editOrderRef.value;
  toast.success(response.changed ? `Encomenda ${ref} atualizada. O cliente foi avisado.` : "Nada mudou na encomenda.");
  await leaveOrderEdit(ref);
}

async function leaveOrderEdit(ref: string) {
  // A comanda virtual some; o pedido fica como o servidor gravou (ou como
  // estava, no descarte).
  await clearCurrentTab();
  orderEdit.reset();
  await navigateTo(`/preorders/${encodeURIComponent(ref)}`);
}

function discardOrderEdit() {
  void leaveOrderEdit(editOrderRef.value);
}

function clearOrDiscard() {
  if (editing.value) discardOrderEdit();
  else void clearCurrentTab();
}

const confirmCounterMode = ref(false);
const uncertainCloseRecoveryOpen = ref(false);
const uncertainCloseReviewed = ref(false);
const uncertainCloseRecoveryBusy = ref(false);
function openUncertainCloseRecovery() {
  uncertainCloseReviewed.value = false;
  uncertainCloseRecoveryOpen.value = true;
}
async function confirmUncertainCloseRecovery() {
  if (!uncertainCloseReviewed.value || uncertainCloseRecoveryBusy.value) return;
  uncertainCloseRecoveryBusy.value = true;
  try {
    if (await acknowledgeUncertainClose()) uncertainCloseRecoveryOpen.value = false;
    else uncertainCloseReviewed.value = false;
  } finally {
    uncertainCloseRecoveryBusy.value = false;
  }
}
function requestSalesMode(mode: "counter" | "order") {
  if (mode === (cart.salesMode || "counter")) return;
  if (editing.value) {
    toast.info("Na edição, a encomenda continua encomenda. Para vender no balcão, descarte as alterações.");
    return;
  }
  if (mode === "counter") { confirmCounterMode.value = true; return; }
  void setSalesMode(mode);
}
function convertToCounter() {
  confirmCounterMode.value = false;
  void setSalesMode("counter");
}

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

// RECARREGAR SOZINHO para entrar na versão nova é uma pergunta mais larga do que
// travar a tela: o auto-lock só adia por pagamento em curso, mas um reload apaga
// qualquer rascunho. O PDV declara aqui, pelo nome, tudo que ele tem na mão — e o
// `usePwaAutoUpdate` do kit não aplica nada enquanto uma dessas razões estiver de
// pé. Balcão vazio (carrinho limpo, sem comanda, sem resultado na tela) é o único
// momento em que a troca é invisível para quem opera.
const { hold: holdReload } = useOperatorReloadHold();
watchEffect(() => {
  holdReload("sale_open", cart.items.length > 0 || unsaved.value);
  holdReload("tab_open", Boolean(cart.tabRef));
  holdReload("payment_open", checkoutMode.value || pixStatus.value === "polling");
  holdReload("sale_result", Boolean(result.value));
  holdReload("writing", busy.value || saving.value || firing.value || cancellingSale.value);
});
onBeforeUnmount(() => {
  for (const reason of ["sale_open", "tab_open", "payment_open", "sale_result", "writing"]) {
    holdReload(reason, false);
  }
});

// Kitchen handoff affordances (spec §2.5): the fire/unfire CTAs come from the
// Projection's Actions (label + enabled), never invented in the screen.
// Na edição de encomenda não há cozinha a disparar: o pedido já existe e a
// cozinha acompanha a edição pelo servidor.
const fireAction = computed(() => resolveAffordance(editing.value ? [] : actions.value, "fire_tab"));
const unfireAction = computed(() => resolveAffordance(actions.value, "unfire_tab"));

// Top context bar title (unified layout language, Arc 5): one band names the
// current work-area screen across Board / Sale / Payment.
const screenTitle = computed(() => {
  // A barra do topo não pode discordar da tela: com a cobrança recusada pelo
  // gateway, "Venda concluída" ali em cima desmente o aviso vermelho logo
  // abaixo — e é a barra que fica na periferia da visão do operador. Mesma
  // razão para o Pix pendente: o dinheiro ainda não entrou.
  if (result.value) {
    if (paymentFailed(result.value.payment)) return "Cobrança não criada";
    if (result.value.salesMode === "order") return "Encomenda registrada";
    return pixAwaiting(result.value.payment, pixStatus.value) ? "Aguardando Pix" : "Venda concluída";
  }
  if (checkoutMode.value) return cart.tabDisplay ? `Pagamento · #${cart.tabDisplay}` : "Pagamento";
  if (editing.value) return orderEditTitle(editOrderRef.value);
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
const { printOne: printOrderTicket, printingRef: printingOrderRef } = usePosOrderTickets(pos);

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
  if (agent.canPrint.value) {
    printingReceipt.value = true;
    try {
      const receipt = await fetchPrintable(result.value.orderRef, "receipt-escpos");
      const outcome = await agent.print(receipt.payload_b64, receipt.title);
      if (outcome.status === "printed") return;
      toast.warning(`A impressora do balcão não respondeu: ${outcome.detail || "sem detalhe"}. O recibo saiu pelo diálogo do navegador.`);
    } catch (error) {
      toast.warning(`${httpErrorMessage(error, "O recibo para a bobina não ficou pronto.")} O recibo saiu pelo diálogo do navegador.`);
    } finally {
      printingReceipt.value = false;
    }
  }
  window.print();
}

// A nota aberta na tela (host do Django): a mesma DANFE da bobina, em formato de
// leitura. Porta secundária — link só para quem o servidor diz que entra.
function danfeScreenUrl(orderRef: string): string {
  return `${djangoOrigin.value}/fiscal/danfe/${encodeURIComponent(orderRef)}/`;
}

// IMPRESSÃO AUTOMÁTICA — o switch "Imprimir nota?" promete bobina sem clique, e
// esta é a parte que cumpre. Não dá para imprimir no fechamento: a NFC-e é
// assíncrona e no instante da tela de confirmação ela ainda não autorizou (o
// endpoint responde 409 até lá). Então a tela espera a nota ficar pronta.
//
// Espera com fim: ~90s (30 tentativas de 3s). Nota que demora mais que isso não
// vai aparecer enquanto o cliente está no balcão, e insistir para sempre
// deixaria um timer vivo atrás de cada venda. Quando desiste, não desiste
// calado — cai no MESMO aviso do caminho manual, que já diz o próximo passo
// (reimprimir nas Últimas vendas).
const AUTO_PRINT_TRIES = 30;
const AUTO_PRINT_INTERVAL_MS = 3000;
let autoPrintTimer: ReturnType<typeof setTimeout> | null = null;

function stopAutoPrint() {
  if (autoPrintTimer) clearTimeout(autoPrintTimer);
  autoPrintTimer = null;
}

async function autoPrintDanfe(orderRef: string, tries = 0) {
  if (!import.meta.client) return;
  // Saiu da tela de resultado (nova venda) — a promessa era daquela venda, mas
  // a impressão segue: quem pediu papel quer papel, esteja o operador onde
  // estiver. Só paramos se a página inteira sair.
  try {
    const danfe = await fetchPrintable(orderRef, "danfe-escpos");
    // O 409 virou 200: a nota EXISTE. A tela de resultado promove "NFC-e na
    // fila…" para "Imprimir DANFE" — por existência, não por previsão.
    markFiscalState(orderRef, "authorized");
    const outcome = await agent.print(danfe.payload_b64, danfe.title);
    if (outcome.status === "printed") {
      toast.success("DANFE impressa.");
      return;
    }
    danfeFallbackToast(orderRef, outcome.detail || "impressão indisponível nesta estação");
  } catch {
    // 409 enquanto a SEFAZ não autoriza: tentar de novo é o comportamento certo.
    if (tries + 1 < AUTO_PRINT_TRIES) {
      autoPrintTimer = setTimeout(() => autoPrintDanfe(orderRef, tries + 1), AUTO_PRINT_INTERVAL_MS);
      return;
    }
    danfeFallbackToast(orderRef, "a nota demorou mais que o esperado para autorizar");
  }
}

// A venda fechou pedindo papel: começa a esperar a nota. Sem nota esperada
// (dinheiro sem CPF, por exemplo) não há o que imprimir — e prometer papel ali
// seria mentir duas vezes.
//
// A espera começa quando a nota está NA FILA. Aguardando o Pix (`awaiting_
// payment`) ela nem foi pedida — insistir no 409 durante toda a espera do Pix
// esgotava as 30 tentativas e desistia com "a nota demorou", mentindo. Quando
// o polling do Pix confirma, o estado vira `queued` e a espera começa aqui.
// A promoção para `authorized` (o próprio auto-print) NÃO reinicia a espera.
watch(
  () => [result.value?.orderRef, result.value?.fiscalState] as const,
  ([orderRef, fiscalState], previous) => {
    const [previousRef, previousState] = previous ?? [undefined, undefined];
    if (orderRef !== previousRef) stopAutoPrint();
    if (!orderRef || !result.value?.wantsPrintedInvoice) return;
    if (fiscalState !== "queued") return;
    if (orderRef === previousRef && previousState === "queued") return;
    stopAutoPrint();
    autoPrintDanfe(orderRef);
  },
);
onBeforeUnmount(stopAutoPrint);

async function printDanfe() {
  if (!import.meta.client || !result.value) return;
  const orderRef = result.value.orderRef;
  printingDanfe.value = true;
  try {
    const danfe = await fetchPrintable(orderRef, "danfe-escpos");
    markFiscalState(orderRef, "authorized");
    const outcome = await agent.print(danfe.payload_b64, danfe.title);
    if (outcome.status === "printed") {
      toast.success("DANFE na impressora.");
      return;
    }
    danfeFallbackToast(orderRef, outcome.detail || "impressão indisponível nesta estação");
  } catch (error) {
    // 409 = a emissão é assíncrona e a nota ainda não autorizou.
    // Fragmento: entra dentro de "A DANFE não saiu na bobina: …", e é o
    // `danfeFallbackToast` que traz a saída (ver a nota dele logo abaixo).
    danfeFallbackToast(orderRef, httpErrorMessage(error, "a DANFE não ficou pronta"));
  } finally {
    printingDanfe.value = false;
  }
}

// Falha nunca termina em "indisponível" seco: quem tem acesso ganha a nota na
// tela como ação; quem não tem ganha o próximo passo.
function danfeFallbackToast(orderRef: string, reason: string) {
  if (pos.value?.danfe_screen_allowed && djangoOrigin.value) {
    toast.error(`A DANFE não saiu na bobina: ${reason}`, {
      action: {
        label: "Ver a nota na tela",
        onClick: () => window.open(danfeScreenUrl(orderRef), "_blank", "noopener"),
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
const orderEntryRef = ref<{ focusCurrent: () => void } | null>(null);
function focusOrderEntry() {
  if (orderSetupPending.value) void nextTick(() => orderEntryRef.value?.focusCurrent());
}
const tabHeaderRef = ref<{ openCustomer: (seed?: string) => void; askRelease: () => void } | null>(null);

// O Recebimento agora é perguntado na TELA DE VENDA (chip da barra e abertura da
// comanda), não só no checkout. O estado mora aqui porque as duas superfícies
// abrem a MESMA caixa — o checkout tem o seu próprio, para o F7 continuar
// funcionando lá dentro sem passar por cima desta.
const fulfillmentSheetOpen = ref(false);
// QUANDO — terceira caixa da barra, irmã de Cliente e Recebimento. Vive na tela
// de venda porque agendar acontece na ABERTURA do atendimento (o operador está no
// telefone), não no fim. O checkout abre a MESMA caixa.
const scheduleSheetOpen = ref(false);
watch([fulfillmentSheetOpen, scheduleSheetOpen], ([fulfillment, schedule]) => {
  if (!fulfillment && !schedule) focusOrderEntry();
});

// O chip da barra abre a caixa de quem é dono dela na tela atual: no checkout, a
// da tela de pagamento (mesmo componente, outro estado) — assim F7 e o chip
// nunca abrem duas caixas diferentes.
// NO BALCÃO os dois chips existem (v4: "Consumir aqui F7", "Agora F8") e são a
// porta para a encomenda: entregar ou agendar É encomenda, então o gesto troca o
// modo e abre a mesma pergunta já no modo certo. Se a troca for recusada (edição
// de encomenda), nada abre.
// "vai à cozinha" na linha nova (v4): para onde o roteamento real mandaria cada
// produto (`kitchen_station` do catálogo, `services/kds.kitchen_routes_for_skus`).
const kitchenStations = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  for (const product of pos.value?.products || []) {
    if (product.kitchen_station) map[product.sku] = product.kitchen_station;
  }
  return map;
});
// PIX e Maquininha direto na folha (v4 tablet b): os meios que o PDV já tem,
// lidos da projeção; um meio que o canal não oferece não aparece.
const quickPayments = computed(() => {
  const methods = pos.value?.payment_methods || [];
  const out: Array<{ ref: string; label: string; icon: string; hint?: string; secondary?: boolean }> = [];
  if (methods.some((m) => m.ref === "pix")) out.push({ ref: "pix", label: "PIX", icon: "lucide:qr-code" });
  const card = methods.find((m) => m.ref === "credit") || methods.find((m) => m.ref === "card") || methods.find((m) => m.ref === "debit");
  if (card) out.push({ ref: card.ref, label: "Maquininha", icon: "lucide:credit-card" });
  // V6-CAIXA: o dinheiro recebido na mesa. A venda fecha aqui e vira o cartão
  // "Abrir gaveta do Balcão" (useDrawerOpening, pulso pelo relay); a gaveta nunca
  // abre sozinha longe do Balcão.
  if (methods.some((m) => m.ref === "cash")) {
    out.push({ ref: "cash", label: "Dinheiro", icon: "lucide:banknote", hint: "abre a gaveta do Balcão", secondary: true });
  }
  return out;
});
// Pagar pela folha: abre o Pagamento já com o meio escolhido lançado (a mesma
// tecla do checkout, `pressMethodKey`), sem o operador escolher de novo.
const QUICK_PAYMENT_KEYS: Record<string, string> = { pix: "P", credit: "C", card: "C", debit: "D", cash: "R" };
async function payOnSheet(method: string) {
  await prepareCheckout();
  if (!checkoutMode.value) return;
  await nextTick();
  const letter = QUICK_PAYMENT_KEYS[method];
  if (letter) paymentWorkspaceRef.value?.pressMethodKey(letter);
}
// ENVIO AUTOMÁTICO (opcional por estação, desligado por padrão; dono, plano §13
// item 3): a linha nova de uma estação com o interruptor ligado vai sozinha quando
// o operador sai da comanda ou ela fica parada. Nunca no meio do lançamento, nunca
// na encomenda (que espera a data) e nunca na edição.
const AUTO_FIRE_IDLE_MS = 90_000;
const autoFireSkus = computed(() => new Set((pos.value?.products || []).filter((p) => p.kitchen_auto_fire).map((p) => p.sku)));
const autoFireOn = computed(() => cart.items.some((item) => autoFireSkus.value.has(item.sku)));
async function autoFireLeftovers() {
  if (!hasOpenTab.value || editing.value || cart.salesMode === "order" || firing.value) return;
  if (!fireAction.value.present || !fireAction.value.enabled) return;
  const unfired = cart.items.filter((item) => !item.fired);
  const auto = unfired.filter((item) => autoFireSkus.value.has(item.sku)).map((item) => item.line_id);
  if (!auto.length) return;
  // Tudo o que falta é automático: o envio de sempre (grava e manda o delta).
  // Senão, só as linhas automáticas; as outras esperam o "Enviar à cozinha".
  await fireTab(auto.length === unfired.length ? undefined : auto);
}
let autoFireTimer: ReturnType<typeof setTimeout> | null = null;
watch(
  () => [cart.tabSessionKey, cart.items.map((item) => `${item.line_id}:${item.qty}:${item.fired ? 1 : 0}`).join("|")],
  () => {
    if (autoFireTimer) clearTimeout(autoFireTimer);
    autoFireTimer = null;
    if (!autoFireSkus.value.size || !inSaleView.value) return;
    autoFireTimer = setTimeout(() => { void autoFireLeftovers(); }, AUTO_FIRE_IDLE_MS);
  },
);
watch(inSaleView, (now, was) => {
  if (was && !now) void autoFireLeftovers();
});
onBeforeUnmount(() => { if (autoFireTimer) clearTimeout(autoFireTimer); });
const contextMoreOpen = ref(false);
const CONTEXT_SALES_MODES = [
  { ref: "counter", label: "Balcão", icon: "lucide:store" },
  { ref: "order", label: "Encomendas", icon: "lucide:calendar-clock" },
] as const;
function leaveCounterThen(next: () => void) {
  requestSalesMode("order");
  if (cart.salesMode === "order") next();
}
function openFulfillmentHere() {
  if (cart.salesMode === "counter") { leaveCounterThen(openFulfillmentHere); return; }
  if (orderSetupPending.value && orderSetupIssue.value === "customer") {
    tabHeaderRef.value?.openCustomer();
    return;
  }
  if (checkoutMode.value) paymentWorkspaceRef.value?.openFulfillment();
  else fulfillmentSheetOpen.value = true;
}
// ENTREGA identifica o cliente. Num pedido que sai da loja o telefone é praxe —
// é por ele que se liga quando o entregador não acha o portão —, e a faixa de
// preço do cadastro precisa valer ANTES de o primeiro item ser lançado, não
// depois. Só é oferecido: fechar o diálogo segue sendo uma resposta.
watch(fulfillmentSheetOpen, (open, wasOpen) => {
  if (open || !wasOpen) return;
  if (cart.fulfillmentType !== "delivery") return;
  if (cart.customerRef || cart.customerName.trim() || cart.customerPhone.trim()) return;
  void nextTick(() => tabHeaderRef.value?.openCustomer());
});
// AGENDADO também identifica o cliente — o servidor recusa encomenda anônima
// (é o contato se algo mudar até a data), então a pergunta vem já na agenda,
// não como surpresa no Validar. Mesmo desenho do irmão acima: só oferecido.
watch(scheduleSheetOpen, (open, wasOpen) => {
  if (open || !wasOpen) return;
  if (!customerRequiredForSchedule.value) return;
  if (cart.customerRef || cart.customerName.trim() || cart.customerPhone.trim()) return;
  void nextTick(() => tabHeaderRef.value?.openCustomer());
});
// O servidor recusou pedindo o CLIENTE (`focus: "customer"`): abre a
// identificação de quem é dona dela na tela atual — motivo sem caminho de um
// toque é beco sem saída (mesmo desvio de `openFulfillmentHere`).
watch(customerFocusNonce, () => {
  void nextTick(() => {
    if (checkoutMode.value) paymentWorkspaceRef.value?.openCustomer();
    else tabHeaderRef.value?.openCustomer();
  });
});

// O chip da barra abre a caixa de quem é DONO dela na tela atual — no checkout, a
// da tela de pagamento. As duas estão montadas ao mesmo tempo; sem este desvio,
// o chip abriria a da tela de venda por cima do pagamento, e o "Quando" dentro do
// Recebimento abriria a outra. Duas caixas para a mesma pergunta na mesma tela é
// exatamente o que a barra de contexto veio desfazer (mesmo desvio de
// `openFulfillmentHere`).
function openScheduleHere() {
  if (cart.salesMode === "counter") { leaveCounterThen(openScheduleHere); return; }
  if (orderSetupPending.value && ["customer", "fulfillment", "address"].includes(orderSetupIssue.value)) {
    openFulfillmentHere();
    return;
  }
  // A grade do dia só é buscada quando alguém vai agendar de fato — a venda
  // dominante do balcão é para agora e não paga por essa pergunta.
  void refreshSchedule();
  if (checkoutMode.value) paymentWorkspaceRef.value?.openSchedule();
  else scheduleSheetOpen.value = true;
}
// O rótulo do terceiro chip. "Para hoje" é o padrão e é uma AFIRMAÇÃO, não um
// campo vazio: a esmagadora maioria das vendas é para agora, e a barra não pode
// parecer que falta preencher alguma coisa.
const scheduleChipLabel = computed(() => scheduleLabel(
  cart.deliveryDate,
  deliveryWindowLabel.value,
  scheduleToday.value,
));
const scheduleChipActive = computed(() => Boolean(cart.deliveryDate || cart.deliveryTimeSlot));
// ENCOMENDA ANÔNIMA — o servidor recusa (`customer_required_for_scheduled`), e o
// checkout trava o Validar por isso. A barra é quem tem o botão que resolve, e
// portanto é ela que chama: o chip pulsa. A REGRA é a mesma do bloqueio do CTA
// porque as duas chamam a mesma função — um dono só, em `presentation/schedule`.
const customerRequiredForSchedule = computed(() => scheduledNeedsCustomer({
  deliveryDate: cart.deliveryDate,
  deliveryTimeSlot: cart.deliveryTimeSlot,
  fulfillmentType: cart.fulfillmentType,
  today: scheduleToday.value,
  customerName: cart.customerName,
  customerPhone: cart.customerPhone,
  customerRef: cart.customerRef,
}));
// A escolha que virou impossível SOZINHA (o operador marcou 09:00 e só depois
// lançou a baguete). O chip é onde ele olha de relance; sem isto ele só
// descobria num 422 seco no Finalizar, com o cliente já tendo ouvido o horário.
const scheduleChipConflict = computed(
  () => scheduleChipTone(deliverySlots.value, cart.deliveryTimeSlot) === "conflict",
);
const scheduleConflictReason = computed(
  () => selectedWindowConflict(deliverySlots.value, cart.deliveryTimeSlot),
);

// O rótulo do chip: com entrega, o BAIRRO diz mais que a palavra "entrega" — é o
// que o operador confere de relance quando o cliente muda de ideia no meio.
const fulfillmentChipLabel = computed(() => {
  if (!cart.fulfillmentConfirmed) return "Entrega ou retirada?";
  const base = pos.value?.fulfillment_options.find((o) => o.ref === cart.fulfillmentType)?.label
    || (cart.fulfillmentType === "delivery" ? "Entrega" : "Retirada");
  if (cart.fulfillmentType !== "delivery") return base;
  const bairro = cart.deliveryNeighborhood.trim() || cart.deliveryAddressStructured?.neighborhood?.trim() || "";
  return bairro ? `${base} · ${bairro}` : base;
});
const paymentWorkspaceRef = ref<{
  validate: () => void;
  openCustomer: () => void;
  openFulfillment: () => void;
  openSchedule: () => void;
  openDiscount: () => void;
  openSplit: () => void;
  pressMethodKey: (letter: string) => boolean;
  pressExact: () => boolean;
  pressReceiptKey: (letter: string) => boolean;
  toggleCpfOnInvoice: () => boolean;
} | null>(null);
// A ajuda de atalhos é a do kit (V6-KIT): "Atalhos" no pé do rail e "?"; o PDV entrega
// o dicionário das teclas dele.
const { open: shortcutsHelpOpen } = useOperatorShortcuts();
provideOperatorShortcuts(POS_SHORTCUT_GROUPS, POS_SHORTCUTS_DESCRIPTION);
const railShown = useSuiteRailShown();
// Transferir a partir do modo seleção da comanda (v4): o diálogo nasce com as linhas
// marcadas. Pelo F10 (toda a venda) ele nasce vazio, como sempre.
const movePreselected = ref<string[]>([]);
function openMoveWith(lineIds?: string[]) {
  movePreselected.value = lineIds ?? [];
  void openMoveDialog();
}

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

// "Ver a nota" na tela de resultado: só para quem o servidor deixa.
const resultDanfeScreenUrl = computed(() =>
  result.value && pos.value?.danfe_screen_allowed && djangoOrigin.value
    ? danfeScreenUrl(result.value.orderRef)
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
      && enterAdvances({ changeQ: result.value.changeQ, payment: result.value.payment, pixStatus: pixStatus.value, salesMode: result.value.salesMode })
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
    // "=" é o Exato do teclado físico: a linha selecionada assume o que as
    // outras deixam devendo (total coberto, troco zero) — o mesmo botão da tela,
    // pela mesma porta: com a revisão do total em trânsito, ele espera.
    if (event.key === "=") {
      event.preventDefault();
      paymentWorkspaceRef.value?.pressExact();
      return;
    }
  }

  // LETRA no checkout = forma de pagamento (D/P/C, derivadas do contrato). É o
  // gesto de TODA venda e era o único do checkout que ainda exigia o mouse. As
  // letras estão livres aqui: o search-as-you-type é da tela de VENDA, e sob
  // campo de texto o `isEditing` acima já cala tudo isto.
  if (
    checkoutMode.value && !isEditing
    && !event.metaKey && !event.ctrlKey && !event.altKey
    && /^[a-zA-Z]$/.test(event.key)
  ) {
    const letra = event.key.toUpperCase();
    if (paymentWorkspaceRef.value?.pressMethodKey(letra)) {
      event.preventDefault();
      return;
    }
    // F (CPF na nota), I (impressa) e M (e-mail) — as três perguntas da seção
    // Nota fiscal, pela letra. Vêm DEPOIS das formas de pagamento de propósito:
    // lançar dinheiro é o gesto de toda venda. E nenhuma forma pode tomar estas
    // três letras: `methodShortcuts` as reserva, para que cadastrar um "Fiado"
    // não roube o F em silêncio.
    if (letra === "F" && paymentWorkspaceRef.value?.toggleCpfOnInvoice()) {
      event.preventDefault();
      return;
    }
    if (paymentWorkspaceRef.value?.pressReceiptKey(letra)) {
      event.preventDefault();
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
      // ⚠️ DENTRO DE UM CAMPO, Esc SAI DO CAMPO — não da tela.
      //
      // As letras de atalho são desligadas enquanto se digita, e têm que ser:
      // sem isso, escrever "cliente@email.com" ligaria e desligaria coisas pelo
      // caminho. Mas o operador que entra no CPF ficava PRESO ali, porque o
      // gesto instintivo de sair (Esc) derrubava o checkout inteiro — perder o
      // pagamento por querer apertar "I" é caro demais para um reflexo.
      // Agora Esc tira o foco do campo e a tela continua de pé; o Esc seguinte,
      // já fora do campo, é que volta para a venda.
      if (isEditing) {
        event.preventDefault();
        (event.target as HTMLElement | null)?.blur();
        return;
      }
      if (checkoutMode.value) {
        event.preventDefault();
        checkoutMode.value = false;
      }
      return;
    case "F2":
      event.preventDefault();
      if (editing.value) return; // a edição sai por Salvar ou Descartar, nunca pelo quadro
      gotoTabInput();
      return;
    case "F3":
      event.preventDefault();
      gotoProductSearch();
      return;
    case "F4":
      event.preventDefault();
      if (editing.value) saveOrderEdit();
      else if (checkoutMode.value) reviewCheckout();
      else if (cart.items.length) prepareCheckout();
      return;
    case "F6":
      event.preventDefault();
      if (checkoutMode.value) paymentWorkspaceRef.value?.openCustomer();
      else if (inSaleView.value) tabHeaderRef.value?.openCustomer();
      return;
    // ── F6·F7·F8 — OS TRÊS FATOS DO PEDIDO, na ordem dos chips da barra ──
    //
    // Quem compra · como recebe · quando quer. É a ordem da conversa do balcão,
    // é a ordem em que os três aparecem no topo da tela, e agora é a ordem das
    // teclas. O "Quando" era o único dos três sem tecla — nasceu depois dos
    // outros dois e ficou órfão —, então ele entra no F8 e as duas ações do
    // checkout (desconto, CPF) andam uma casa. Pré-go-live, ninguém decorou
    // nada, e o dicionário (tecla `?`) é quem ensina.
    //
    // Os três valem na VENDA também: são fatos decididos na abertura do
    // atendimento, revistos de relance daí em diante — não são assunto do
    // checkout.
    case "F7":
      if (!inSaleView.value) return;
      event.preventDefault();
      openFulfillmentHere();
      return;
    case "F8":
      if (!inSaleView.value) return;
      event.preventDefault();
      openScheduleHere();
      return;
    // ── F9·F10 — AS DUAS AÇÕES DA TELA EM QUE SE ESTÁ ───────────────────
    //
    // Na comanda: mandar para a cozinha e transferir linhas. No pagamento: os
    // dois Ajustes da conta — desconto e dividir a conta —, que são o par de
    // botões vizinhos na tela, agindo sobre o VALOR. As duas telas nunca
    // coexistem, e o par sempre significa a mesma coisa: "as duas ações daqui".
    // Foi a saída possível: de F2 a F8 está tudo tomado, F5 é reload, F11 é
    // tela-cheia (que o quiosque usa) e F12 abre o DevTools antes de a página
    // ver a tecla. O que a seção Nota fiscal pergunta anda pelas letras F·I·M.
    case "F9":
      event.preventDefault();
      if (checkoutMode.value) paymentWorkspaceRef.value?.openDiscount();
      else if (inSaleView.value && cart.items.length && !editing.value) fireTab();
      return;
    case "F10":
      event.preventDefault();
      if (checkoutMode.value) paymentWorkspaceRef.value?.openSplit();
      else if (inSaleView.value && cart.items.length && !editing.value) openMoveWith();
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

function restoreUncertainCloseFromStorage() {
  void restoreUncertainClose();
}
onMounted(() => {
  if (editRef) void startOrderEdit(editRef);
  else if (redoRef) void openRedoTab(redoRef);
  else if (newOrder) void startNewOrder();
  void restoreUncertainClose();
  window.addEventListener("storage", restoreUncertainCloseFromStorage);
  window.addEventListener("keydown", onGlobalKeydown);
});
onBeforeUnmount(() => {
  window.removeEventListener("storage", restoreUncertainCloseFromStorage);
  window.removeEventListener("keydown", onGlobalKeydown);
});
</script>

<template>
  <main :style="{ '--pos-context-header-height': `${contextHeaderHeight || 53}px` }" class="flex flex-wrap content-start min-h-dvh bg-background text-foreground norail:pb-16 max-md:overflow-x-clip md:h-[100dvh] md:min-h-0 md:flex-nowrap md:overflow-hidden">
    <PosFunctionRail
      v-if="pos"
      :pos="pos"
      :has-open-cash-session="pos.has_open_cash_session"
      :operator-name="activeOperator?.name || ''"
      :pending="pending"
      :view="checkoutMode ? 'checkout' : (inSaleView ? 'sale' : 'board')"
      @board="goToTabs"
      @cash="goToCashSession"
      @display="openCustomerDisplay"
      @lock="lock()"
      @refresh="refresh()"
    />

    <!-- `max-md:basis-full`: no celular a coluna ocupa a linha inteira; com a base 0 ela
         dividia a primeira linha com a comanda e ficava com 24px. -->
    <div class="flex min-w-0 flex-1 flex-col max-md:basis-full md:min-h-0 md:overflow-hidden">
      <!-- Barra de contexto da v4 (`pos-sale4.html`): 56px, voltar, modo, a comanda,
           os três fatos do pedido (F6 · F7 · F8), o ao vivo, Últimas vendas e Liberar.
           Atalhos e Terminal foram para o pé do rail. -->
      <!-- A busca da suíte na Venda: o campo e o `/` são do produto (F3), então a suíte
           abre no Ctrl K, num diálogo, sem um segundo campo na tela. -->
      <OperatorSuiteSearch v-if="pos" variant="hotkey" placeholder="Buscar pedido, cliente, produto ou tela" />
      <header v-if="pos" ref="contextHeader" class="flex min-h-14 shrink-0 flex-wrap items-center gap-2 border-b border-border bg-card px-3 py-2" data-pos-context-header>
        <!-- Rail oculto (menu das iniciais): o caminho de volta para ele. -->
        <button
          v-if="railCollapsed"
          type="button"
          class="hidden size-10 shrink-0 place-items-center rounded-md border border-border bg-card text-muted-foreground transition hover:bg-accent hover:text-foreground rail:grid"
          aria-label="Mostrar a barra lateral"
          title="Mostrar a barra lateral"
          data-page-header-show-rail
          @click="setRail('compact')"
        >
          <Icon name="lucide:panel-left-open" class="size-5" />
        </button>
        <!-- Celular e tablet em pé, fora da venda: o selo do app (volta à Central). -->
        <OperatorAppSeal v-if="!inSaleView" />
        <button
          v-if="inSaleView && !editing"
          type="button"
          class="grid size-10 shrink-0 place-items-center rounded-md border border-border bg-card transition hover:bg-accent"
          :aria-label="checkoutMode ? 'Voltar à comanda' : 'Voltar para comandas'"
          :title="checkoutMode ? 'Voltar à comanda' : 'Voltar para comandas'"
          @click="checkoutMode ? (checkoutMode = false) : goToTabs()"
        >
          <Icon name="lucide:arrow-left" class="size-5" />
        </button>
        <span
          v-if="inSaleView && !checkoutMode && unsaved"
          class="inline-flex shrink-0 items-center gap-1 rounded-md border border-warning/50 bg-warning/10 px-2 py-1 text-xs font-medium text-warning"
          role="status"
          :title="tabConflict ? 'A comanda mudou em outro dispositivo. Confira antes de salvar.' : 'A comanda não foi salva. Tentando de novo.'"
        >
          <Icon name="lucide:cloud-off" class="size-3.5" /> Não salvo
        </span>
        <UiButton v-if="inSaleView && tabConflict" variant="ghost" size="sm" :disabled="busy" @click="reloadConflictingTab">
          Descartar minhas alterações e atualizar
        </UiButton>
        <!-- A BARRA CARREGA OS FATOS DO PEDIDO — cliente e recebimento — e segue
             carregando durante o checkout. Antes ela sumia ali, e a informação
             tinha de ser reconstruída dentro da coluna de trabalho do pagamento;
             agora ela acompanha a venda inteira, do primeiro item ao troco. -->
        <!-- MODO EDIÇÃO: o que está sendo mexido é a encomenda, não uma venda nova. -->
        <div
          v-if="inSaleView && editing"
          class="flex shrink-0 items-center gap-2 rounded-md border border-info/40 bg-info/10 py-1 pl-2 pr-1 text-sm font-medium text-info"
          role="status"
          data-order-edit-banner
        >
          <Icon name="lucide:pencil" class="size-4" />
          {{ orderEditTitle(editOrderRef) }}
          <UiButton
            variant="ghost"
            size="sm"
            :disabled="busy || editBusy"
            data-order-edit-discard
            @click="discardOrderEdit"
          >
            Descartar alterações
          </UiButton>
        </div>
        <PosTabHeader
          v-if="inSaleView"
          ref="tabHeaderRef"
          v-model:customer-name="cart.customerName"
          v-model:customer-phone="cart.customerPhone"
          v-model:customer-tax-id="cart.customerTaxId"
          v-model:customer-email="cart.customerEmail"
          class="min-w-0 flex-1"
          :tab-display="cart.tabDisplay"
          :tab-number="cart.tabNumber"
          :opened-at="cart.tabOpenedAt"
          :seating-spots="pos.seating_spots || []"
          :seating-spot-ref="cart.tabSeatingSpot"
          :occupied-spot-refs="tabs.filter((tab) => tab.seating_spot_ref && tab.ref !== cart.tabRef).map((tab) => tab.seating_spot_ref!)"
          :sales-mode="cart.salesMode"
          :has-open-tab="hasOpenTab"
          :can-rename="canRenameTab"
          :customer-lookup="customerLookup"
          :lookup-busy="lookupBusy"
          :search-results="customerSearchResults"
          :search-busy="customerSearchBusy"
          :customer-resolved-new="customerResolvedNew"
          :new-customer-prefs="pendingCustomerPrefs"
          :customer-decision="customerDecision"
          :customer-merge-busy="customerMergeBusy"
          :customer-release-busy="customerReleaseBusy"
          :read-only="checkoutMode"
          :fulfillment-type="cart.fulfillmentType"
          :fulfillment-label="fulfillmentChipLabel"
          :schedule-label="scheduleChipLabel"
          :scheduled="scheduleChipActive"
          :has-fired-items="cart.items.some((item) => item.fired)"
          :customer-required="customerRequiredForSchedule"
          :customer-locked-reason="editing ? ORDER_EDIT_CUSTOMER_LOCKED : undefined"
          :schedule-conflict="scheduleChipConflict"
          :schedule-conflict-reason="scheduleConflictReason"
          :loading="busy"
          @sales-mode-change="requestSalesMode"
          @customer-closed="focusOrderEntry"
          @customer-locked="notifyCustomerLocked"
          @rename="(ref: string, spot?: string) => { if (!editing) void renameTab(ref, spot); }"
          @clear="clearOrDiscard"
          @clear-customer="clearCustomer"
          @lookup-customer="lookupCustomer"
          @resolve-customer="(done) => { void resolveCustomer().then(done) }"
          @decision-confirm="confirmCustomerDecision"
          @decision-cancel="cancelCustomerDecision"
          @decision-merge="mergeConflictCustomers"
          @decision-release="releaseConflictContact"
          @decision-pick="pickConflictCandidate"
          @search="searchCustomers"
          @select-result="selectCustomerResult"
          @apply-customer-favorite="applyCustomerFavorite"
          @apply-preference="applyCustomerPreference"
          @repeat-customer-last-order="repeatCustomerLastOrder"
          @open-fulfillment="openFulfillmentHere"
          @open-schedule="openScheduleHere"
          @open-customer="paymentWorkspaceRef?.openCustomer()"
        />
        <h1 v-else class="min-w-0 truncate pl-1 op-heading">{{ screenTitle }}</h1>
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
        <div class="ml-auto flex shrink-0 items-center gap-2">
          <OperatorLiveStatus
            :tone="liveStatus.view.value.tone"
            :time="liveStatus.time.value"
            :label="liveStatus.view.value.label"
            :detail="liveStatus.view.value.detail"
            class="px-1"
          />
          <button
            type="button"
            class="grid size-10 shrink-0 place-items-center rounded-md border border-border bg-card transition hover:bg-accent"
            :class="inSaleView ? 'max-xl:hidden' : ''"
            aria-label="Últimas vendas"
            title="Últimas vendas (status fiscal, DANFE, reenvio)"
            @click="recentSalesOpen = true"
          >
            <Icon name="lucide:history" class="size-5" />
          </button>
          <!-- Liberar comanda: o gesto mora no `PosTabHeader` (com a confirmação dele);
               aqui fica a porta, no fim da barra, como na v4. -->
          <button
            v-if="inSaleView && hasOpenTab && !checkoutMode"
            type="button"
            class="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-md border border-border bg-card px-2.5 op-label text-muted-foreground transition hover:bg-accent hover:text-foreground max-xl:hidden"
            title="Liberar comanda (pede confirmação)"
            data-pos-release-tab
            @click="tabHeaderRef?.askRelease()"
          >
            <Icon name="lucide:x" class="size-4" />
            <span class="max-2xl:sr-only">Liberar comanda</span>
          </button>
          <!-- Abaixo do desktop a barra é de UMA linha (v3 tablet 2, v4 tablet): o que
               não cabe mora no ⋯. No tablet deitado, Últimas vendas e Liberar; no
               tablet em pé e no celular, também o modo e o Quando. -->
          <UiPopover v-if="inSaleView && !checkoutMode" v-model:open="contextMoreOpen">
            <UiPopoverTrigger as-child>
              <button
                type="button"
                class="grid size-10 shrink-0 place-items-center rounded-md border border-border bg-card transition hover:bg-accent xl:hidden"
                aria-label="Mais ações da comanda"
                title="Mais ações da comanda"
                data-pos-context-more
              >
                <Icon name="lucide:ellipsis-vertical" class="size-5" />
              </button>
            </UiPopoverTrigger>
            <UiPopoverContent align="end" class="w-64 p-1.5">
              <div class="grid gap-0.5" data-pos-context-more-menu>
                <div v-if="!editing" class="mb-1 grid grid-cols-2 gap-1 rounded-md bg-secondary p-1 lg:hidden" role="group" aria-label="Modo de atendimento">
                  <button
                    v-for="mode in CONTEXT_SALES_MODES"
                    :key="mode.ref"
                    type="button"
                    class="inline-flex h-11 items-center justify-center gap-1.5 rounded op-label transition"
                    :class="(cart.salesMode || 'counter') === mode.ref ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground'"
                    :aria-pressed="(cart.salesMode || 'counter') === mode.ref"
                    @click="contextMoreOpen = false; requestSalesMode(mode.ref)"
                  >
                    <Icon :name="mode.icon" class="size-4" />{{ mode.label }}
                  </button>
                </div>
                <button v-if="hasOpenTab" type="button" class="flex h-11 items-center gap-2.5 rounded-md px-2.5 text-left op-label hover:bg-accent sm:hidden" @click="contextMoreOpen = false; openFulfillmentHere()">
                  <Icon :name="cart.salesMode === 'order' ? 'lucide:store' : 'lucide:utensils'" class="size-4 text-muted-foreground" />
                  {{ cart.salesMode === "order" ? `Recebimento: ${fulfillmentChipLabel}` : "Consumir aqui (entregar vira encomenda)" }}
                </button>
                <button v-if="hasOpenTab" type="button" class="flex h-11 items-center gap-2.5 rounded-md px-2.5 text-left op-label hover:bg-accent xl:hidden" @click="contextMoreOpen = false; openScheduleHere()">
                  <Icon name="lucide:clock" class="size-4 text-muted-foreground" />
                  {{ cart.salesMode === "order" ? `Quando: ${scheduleChipLabel}` : "Agendar (vira encomenda)" }}
                </button>
                <button type="button" class="flex h-11 items-center gap-2.5 rounded-md px-2.5 text-left op-label hover:bg-accent" @click="contextMoreOpen = false; recentSalesOpen = true">
                  <Icon name="lucide:history" class="size-4 text-muted-foreground" />
                  Últimas vendas
                </button>
                <button v-if="hasOpenTab" type="button" class="flex h-11 items-center gap-2.5 rounded-md px-2.5 text-left op-label text-destructive hover:bg-destructive/10" data-pos-release-tab-more @click="contextMoreOpen = false; tabHeaderRef?.askRelease()">
                  <Icon name="lucide:x" class="size-4" />
                  Liberar comanda
                </button>
              </div>
            </UiPopoverContent>
          </UiPopover>
          <!-- Onde o rail não existe (celular e tablet em pé): Avisos, a caixa do kit,
               no fim da barra (V6-KIT, T-06). -->
          <ClientOnly>
            <OperatorInbox v-if="!railShown" placement="header" />
          </ClientOnly>
        </div>
      </header>

      <UiAlert
        v-if="closeGuardNotice"
        variant="destructive"
        icon="lucide:triangle-alert"
        class="mx-4 mt-3 shrink-0"
        role="alert"
      >
        <UiAlertTitle>{{ closeGuardNotice.title }}</UiAlertTitle>
        <UiAlertDescription class="gap-3">
          <p>{{ closeGuardNotice.body }}</p>
          <div class="flex flex-wrap gap-2">
            <UiButton variant="outline" size="sm" @click="recentSalesOpen = true">Conferir últimas vendas</UiButton>
            <!-- O corpo dizia "confira no Gestor" e não levava. Agora leva: a
                 fila, porque o que está em dúvida é se o pedido nasceu — não há
                 `ref` para apontar. -->
            <UiButton
              v-if="closeGuardNotice.link"
              variant="outline"
              size="sm"
              class="gap-1.5"
              :href="closeGuardNotice.link.href"
              v-bind="crossAppAttrs(closeGuardNotice.link.href)"
              data-close-guard-orders-link
            >
              <Icon name="lucide:external-link" class="size-4" />
              {{ closeGuardNotice.link.label }}
            </UiButton>
            <UiButton v-if="closeGuardNotice.canRelease" size="sm" @click="openUncertainCloseRecovery">Já conferi · liberar tentativa</UiButton>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <!-- Abaixo do desktop a comanda é a folha de baixo: a grade ganha o respiro dela. -->
      <div class="flex min-h-0 w-full flex-1 flex-col gap-3 px-3 pt-2.5 pb-3 md:min-h-0 md:overflow-hidden" :class="ticketAsSheet && inSaleView && !checkoutMode && !orderSetupPending ? 'max-lg:pb-40' : ''">
      <!-- O dinheiro das vendas do tablet que ainda não chegou à gaveta: o
           cartão segue de pé depois da "Nova venda", até o atendente abrir a
           gaveta do Balcão na frente dela (pos-tablet-fluxo.jpg, passo 3). -->
      <div v-if="!result && drawerOpening.pendingCash.value.length" class="grid gap-2" data-pending-cash>
        <PosDrawerPulseCard
          v-for="pending in drawerOpening.pendingCash.value"
          :key="pending.orderRef"
          compact
          :pending="pending"
          :terminal-label="drawerOpening.terminalLabel.value"
          :state="drawerOpening.openingRef.value === pending.orderRef ? drawerOpening.state.value : 'idle'"
          :message="drawerOpening.openingRef.value === pending.orderRef ? drawerOpening.message.value : ''"
          :relay-warning="drawerOpening.relay.value?.online ? '' : drawerOpening.relay.value?.reason"
          @open="drawerOpening.open({ purpose: 'sale', orderRef: pending.orderRef })"
          @dismiss="drawerOpening.dismissPendingCash(pending.orderRef)"
        />
      </div>
      <div class="flex-1 md:min-h-0 md:overflow-hidden">
      <!-- TELA DE RESULTADO — substitui o banner de antes: tela cheia no fluxo
           de venda, com o troco congelado como herói e "Nova venda" dominante. -->
      <div v-if="result" class="h-full md:overflow-y-auto">
        <PosSaleResult
          :result="result"
          :pix-status="pixStatus"
          :can-cancel="canCancelRecentSale"
          :danfe-screen-url="resultDanfeScreenUrl"
          :printing-receipt="printingReceipt"
          :printing-danfe="printingDanfe"
          :resending-link="resendingLink"
          :printing-ticket="Boolean(printingOrderRef)"
          @new-sale="startNextSale"
          @print-ticket="printOrderTicket(result.orderRef)"
          @print-receipt="printReceipt"
          @print-danfe="printDanfe"
          @cancel-sale="openCancelSaleDialog"
          @payment-notice="sendPaymentNotice"
        >
          <template #drawer>
            <PosDrawerPulseCard
              v-for="pending in drawerOpening.pendingCash.value.filter((item) => item.orderRef === result?.orderRef)"
              :key="pending.orderRef"
              :pending="pending"
              :terminal-label="drawerOpening.terminalLabel.value"
              :state="drawerOpening.openingRef.value === pending.orderRef ? drawerOpening.state.value : 'idle'"
              :message="drawerOpening.openingRef.value === pending.orderRef ? drawerOpening.message.value : ''"
              :relay-warning="drawerOpening.relay.value?.online ? '' : drawerOpening.relay.value?.reason"
              @open="drawerOpening.open({ purpose: 'sale', orderRef: pending.orderRef })"
              @dismiss="drawerOpening.dismissPendingCash(pending.orderRef)"
            />
          </template>
        </PosSaleResult>
      </div>

      <div v-else-if="checkoutMode" class="h-full md:overflow-y-auto">
      <PosPaymentWorkspace
        ref="paymentWorkspaceRef"
        :sales-mode="cart.salesMode"
        v-model:discount-type="cart.discountType"
        v-model:discount-value="cart.discountValue"
        v-model:discount-reason="cart.discountReason"
        v-model:manager-username="cart.managerUsername"
        v-model:manager-pin="cart.managerPin"
        :manager-approval-error="managerApprovalError"
        v-model:fulfillment-type="cart.fulfillmentType"
        v-model:fulfillment-confirmed="cart.fulfillmentConfirmed"
        v-model:payment-collection="cart.paymentCollection"
        v-model:customer-name="cart.customerName"
        v-model:customer-phone="cart.customerPhone"
        v-model:customer-tax-id="cart.customerTaxId"
        v-model:invoice-tax-id="cart.invoiceTaxId"
        v-model:wants-cpf-on-invoice="cart.wantsCpfOnInvoice"
        v-model:customer-email="cart.customerEmail"
        v-model:delivery-address="cart.deliveryAddress"
        v-model:delivery-address-structured="cart.deliveryAddressStructured"
        v-model:delivery-street-number="cart.deliveryStreetNumber"
        v-model:delivery-neighborhood="cart.deliveryNeighborhood"
        v-model:delivery-complement="cart.deliveryComplement"
        v-model:delivery-instructions="cart.deliveryInstructions"
        v-model:delivery-date="cart.deliveryDate"
        v-model:delivery-time-slot="cart.deliveryTimeSlot"
        v-model:delivery-fee-override-input="cart.deliveryFeeOverrideInput"
        v-model:delivery-fee-override="cart.deliveryFeeOverride"
        :delivery-fee-q="deliveryFeeQ"
        :delivery-fee-source="deliveryFeeSource"
        :delivery-distance-km="deliveryDistanceKm"
        :delivery-slots="deliverySlots"
        :canonical-delivery-slots="canonicalDeliverySlots"
        :delivery-slots-pending="deliverySlotsPending"
        :delivery-date-effective="deliveryDateEffective"
        v-model:change-for-input="cart.changeForInput"
        v-model:order-notes="cart.orderNotes"
        v-model:receipt-channels="cart.receiptChannels"
        v-model:receipt-email="cart.receiptEmail"
        v-model:save-receipt-contact="cart.saveReceiptContact"
        v-model:save-receipt-tax-id="cart.saveReceiptTaxId"
        v-model:confirm-receipt-tax-id="cart.confirmReceiptTaxId"
        :schedule-today="scheduleToday"
        :schedule-available-dates="scheduleAvailableDates"
        :schedule-bottleneck-name="scheduleBottleneckName"
        :schedule-ready-at="scheduleReadyAt"
        :schedule-failed="scheduleFailed"
        :schedule-max-date="scheduleMaxDate"
        :split-count="splitCount"
        :split-paid-count="splitPaidCount"
        :split-note="splitNote"
        :managers="pos?.managers || []"
        :operator-name="activeOperator?.name || ''"
        :tab-display="cart.tabDisplay"
        :items="cart.items"
        :has-open-tab="hasOpenTab"
        :fulfillment-options="pos?.fulfillment_options || []"
        :payment-methods="pos?.payment_methods || []"
        :payment-constraints="pos?.payment_constraints || {}"
        :payment-collections="pos?.payment_collections || []"
        :checkout-contract="checkoutContract"
        :address-autocomplete="addressAutocomplete"
        :customer-ref="cart.customerRef"
        :customer-lookup="customerLookup"
        :search-results="customerSearchResults"
        :search-busy="customerSearchBusy"
        :customer-resolved-new="customerResolvedNew"
        :new-customer-prefs="pendingCustomerPrefs"
        :customer-decision="customerDecision"
        :customer-merge-busy="customerMergeBusy"
        :customer-release-busy="customerReleaseBusy"
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
        :review-failed="reviewFailed"
        :review-failure-reason="reviewFailureReason"
        @back="checkoutMode = false"
        @submit="submitSale"
        @add-tender="addTender"
        @remove-tender="removeTender"
        @select-tender="selectTender"
        @set-split-count="setSplitCount"
        @tender-digit="tenderDigit"
        @tender-comma="tenderComma"
        @tender-backspace="tenderBackspace"
        @tender-clear="tenderClear"
        @tender-add="tenderAdd"
        @tender-exact="tenderExact"
        @lookup-customer="lookupCustomer"
        @resolve-customer="(done) => { void resolveCustomer().then(done) }"
        @decision-confirm="confirmCustomerDecision"
        @decision-cancel="cancelCustomerDecision"
        @decision-merge="mergeConflictCustomers"
        @decision-release="releaseConflictContact"
        @decision-pick="pickConflictCandidate"
        @search="searchCustomers"
        @select-result="selectCustomerResult"
        @clear-customer="clearCustomer"
        @apply-customer-favorite="applyCustomerFavorite"
        @apply-preference="applyCustomerPreference"
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
        <PosStoreNetworkNotice v-if="!inSaleView && pos" class="mb-3" />
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
        <PosOrderEntry
          ref="orderEntryRef"
          v-else-if="inSaleView && orderSetupPending"
          :issue="orderSetupIssue"
          :delivery="cart.fulfillmentConfirmed && cart.fulfillmentType === 'delivery'"
          :item-count="itemCount"
          :customer-name="cart.customerName"
          :fulfillment-label="fulfillmentChipLabel"
          :schedule-label="scheduleChipLabel"
          :schedule-window="deliveryWindowLabel"
          :loading="busy"
          @customer="tabHeaderRef?.openCustomer()"
          @fulfillment="openFulfillmentHere"
          @schedule="openScheduleHere"
          @complete="completeOrderSetup"
        />
        <PosProductGrid
          v-else
          ref="productGridRef"
          :products="pos?.products || []"
          :collections="pos?.collections || []"
          :favorite-refs="pos?.favorite_collection_refs || []"
          :cart-items="cart.items"
          :pending="pending"
          :tabs="tabs"
          :current-tab-ref="cart.tabRef"
          :customer-search="!editing"
          @add="addProduct"
          @open-tab="openTab"
          @find-customer="(query: string) => tabHeaderRef?.openCustomer(query)"
        />
      </div>
      </div>
      </div>
    </div>

    <!-- TICKET / COMANDA — full-height right flank (cart-direita, reaches the top
         edge alongside the rail; on mobile it wraps below the product grid). -->
    <aside
      v-if="pos && inSaleView && !checkoutMode && !orderSetupPending"
      class="flex shrink-0 flex-col max-lg:fixed max-lg:right-0 max-lg:left-0 max-lg:z-30 max-lg:bottom-16 rail:max-lg:bottom-0 lg:h-full lg:bg-card lg:w-[360px] lg:border-l lg:border-border xl:w-[400px]"
      :class="railCollapsed ? '' : 'rail:max-lg:left-[76px]'"
    >
        <div class="min-h-0 flex-1 md:overflow-hidden">
          <PosCartPanel
            :sheet="ticketAsSheet"
            :tab-title="hasOpenTab ? tabTitleView(cart.tabDisplay, cart.tabNumber).title : ''"
            :kitchen-stations="kitchenStations"
            :quick-payments="quickPayments"
            :auto-fire="autoFireOn"
            :items="cart.items"
            :requires-tab="tabRequiredForCart"
            :has-open-tab="hasOpenTab"
            :loading="busy"
            :saving="saving"
            :fire-action="fireAction"
            :unfire-action="unfireAction"
            :firing="firing"
            :discount-reasons="checkoutContract?.discount_reasons || []"
            :line-adjustments-blocked-reason="editing ? ORDER_EDIT_LINE_ADJUSTMENTS_BLOCKED : undefined"
            :primary-label="editing ? 'Salvar alterações' : undefined"
            :primary-icon="editing ? 'lucide:save' : undefined"
            :hide-move="editing"
            @increment="(lineId) => setQty(lineId, lineQty(lineId) + 1)"
            @decrement="(lineId) => setQty(lineId, lineQty(lineId) - 1)"
            @remove="(lineId) => setQty(lineId, 0)"
            @restore="restoreItem"
            @set-qty="(lineId, qty) => setQty(lineId, qty)"
            @set-notes="setLineNotes"
            @set-discount="setLineDiscount"
            @prepare="editing ? saveOrderEdit() : prepareCheckout()"
            @move="openMoveWith"
            @fire="fireTab"
            @pay="payOnSheet"
            @auto-fire-settings="navigateTo('/settings/kitchen')"
            @unfire="unfireTab"
            @fire-lines="(ids, complete) => fireTab(ids).then(complete)"
            @unfire-lines="(ids, complete) => unfireSelected(ids).then(complete)"
            @request-tab="requestTabAssociation('start')"
          />
        </div>
    </aside>

    <!-- Celular e tablet em pé: as seções na barra de baixo (kit), presa ao pé da tela
         (P28): a página reserva o lugar dela com `norail:pb-16`. -->
    <PosFunctionRail place="bar" class="w-full norail:fixed norail:inset-x-0 norail:bottom-0" :pos="pos" :pending="pending" :operator-name="activeOperator?.name || ''" @board="goToTabs" @cash="goToCashSession" @display="openCustomerDisplay" @lock="lock()" @refresh="refresh()" />

    <!-- RECEBIMENTO na tela de venda. É fato do PEDIDO, não do pagamento:
         entrega acrescenta taxa e depende de endereço, e perguntar isso só no
         checkout faz o total dar um pulo na última tela. Mesma caixa que o
         checkout abre — o operador não reaprende nada. -->
    <PosFulfillmentModal
      v-model:open="fulfillmentSheetOpen"
      v-model:fulfillment-type="cart.fulfillmentType"
      v-model:fulfillment-confirmed="cart.fulfillmentConfirmed"
      v-model:delivery-address="cart.deliveryAddress"
      v-model:delivery-address-structured="cart.deliveryAddressStructured"
      v-model:delivery-street-number="cart.deliveryStreetNumber"
      v-model:delivery-neighborhood="cart.deliveryNeighborhood"
      v-model:delivery-complement="cart.deliveryComplement"
      v-model:delivery-instructions="cart.deliveryInstructions"
      v-model:delivery-fee-override="cart.deliveryFeeOverride"
      v-model:delivery-fee-override-input="cart.deliveryFeeOverrideInput"
      v-model:order-notes="cart.orderNotes"
      :fulfillment-options="pos?.fulfillment_options || []"
      :saved-addresses="customerLookup?.saved_addresses || []"
      :address-autocomplete="addressAutocomplete"
      :schedule-label="scheduleChipLabel"
      :delivery-fee-q="deliveryFeeQ"
      :delivery-fee-source="deliveryFeeSource"
      :delivery-fee-status="deliveryFeeStatus"
      :delivery-distance-km="deliveryDistanceKm"
      @pick-saved-address="applySavedAddress"
      @open-schedule="openScheduleHere"
    />

    <!-- QUANDO — data e janela, para retirada E entrega. Extraído do formulário
         de entrega, onde a retirada agendada era literalmente impossível. -->
    <PosScheduleModal
      :sales-mode="cart.salesMode"
      v-model:open="scheduleSheetOpen"
      v-model:delivery-date="cart.deliveryDate"
      v-model:delivery-time-slot="cart.deliveryTimeSlot"
      :today="scheduleToday"
      :fulfillment-type="cart.fulfillmentConfirmed ? cart.fulfillmentType : undefined"
      :delivery-date-effective="deliveryDateEffective"
      :available-dates="scheduleAvailableDates"
      :windows="deliverySlots"
      :bottleneck-name="scheduleBottleneckName"
      :ready-at="scheduleReadyAt"
      :pending="deliverySlotsPending"
      :failed="scheduleFailed"
      :max-date="scheduleMaxDate"
    />

    <UiDialog v-model:open="confirmCounterMode">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Converter para atendimento de balcão?</UiDialogTitle>
          <UiDialogDescription>A entrega, o agendamento e a cobrança na entrega serão removidos. Os itens e o cliente continuam neste atendimento.</UiDialogDescription>
        </UiDialogHeader>
        <UiDialogFooter class="gap-2">
          <UiButton variant="outline" @click="confirmCounterMode = false">Continuar encomenda</UiButton>
          <UiButton :disabled="busy" @click="convertToCounter">Converter para balcão</UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <UiDialog v-model:open="uncertainCloseRecoveryOpen">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Você conferiu pedido e pagamento?</UiDialogTitle>
          <UiDialogDescription>Verifique primeiro em Últimas vendas ou no Gestor. Liberar sem conferir pode repetir uma cobrança cujo resultado não chegou a esta tela.</UiDialogDescription>
        </UiDialogHeader>
        <label class="flex cursor-pointer items-center gap-3 rounded-md border p-3 text-sm">
          <UiSwitch v-model="uncertainCloseReviewed" />
          <span>Conferi o pedido e o pagamento e sei se esta venda precisa ser tentada novamente.</span>
        </label>
        <UiDialogFooter class="gap-2">
          <UiButton variant="outline" @click="uncertainCloseRecoveryOpen = false">Voltar e conferir</UiButton>
          <UiButton :disabled="!uncertainCloseReviewed || uncertainCloseRecoveryBusy" @click="confirmUncertainCloseRecovery">{{ uncertainCloseRecoveryBusy ? 'Verificando…' : 'Liberar tentativa' }}</UiButton>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

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
         A saída normal não é botão nenhum — a tela sonda o sensor e sai sozinha
         quando a gaveta fecha. Fechar o diálogo desiste da venda que esperava; o
         PIN do gerente é a EXCEÇÃO (gaveta emperrada, sensor morto) e vai para o
         livro marcado como tal. -->
    <PosDrawerLockDialog
      :open="drawerLock.open.value"
      :sensor-lost="drawerLock.sensorLost.value"
      :busy="drawerLock.busy.value"
      @update:open="(value) => { if (!value) drawerLock.dismiss(); }"
      @manager="drawerLock.askManager"
    />
    <OperatorManagerAuth
      :open="drawerLock.managerOpen.value"
      action="drawer_unlock"
      :operator-name="activeOperator?.name || ''"
      :managers="pos?.managers || []"
      :busy="drawerLock.busy.value"
      :error="drawerLock.managerError.value"
      @update:open="(value) => { if (!value) drawerLock.backToLock(); }"
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
      :operator-name="activeOperator?.name || ''"
      @confirm="cancelRecentSale"
      @confirm-badge="cancelRecentSaleWithBadge"
    />

    <!-- Venda por peso: o tile do queijo fracionado pede a etiqueta. -->
    <PosWeighedEntryDialog
      :product="weighedPrompt"
      :weight-entry-enabled="Boolean(pos?.weighed_weight_entry)"
      @confirm="addWeighedProduct"
      @cancel="cancelWeighedPrompt"
    />

    <!-- Escolhas no produto: sabor obrigatório, adicionais com preço. -->
    <PosProductOptionsDialog
      :product="optionsPrompt"
      @confirm="addOptionsProduct"
      @cancel="cancelOptionsPrompt"
    />

    <PosMoveLinesDialog
      v-model:open="moveDialogOpen"
      :tab-display="cart.tabDisplay"
      :items="cart.items"
      :suggested-split-ref="suggestedSplitRef"
      :preselected="movePreselected"
      :other-tabs="otherOpenTabs"
      :capability="tabManipulation"
      :busy="busy"
      :preparing="movePreparing"
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
    <!-- EDIÇÃO DA ENCOMENDA: a prévia do servidor antes de gravar, e o PIN do
         gerente quando a encomenda paga fica mais barata. -->
    <PosOrderEditReview
      v-if="editing"
      v-model:delivery-payment-method="editPaymentMethod"
      v-model:delivery-tax-id="editTaxId"
      :open="editReviewOpen"
      :order-ref="editOrderRef"
      :preview="editPreview"
      :busy="editBusy"
      :error="editError"
      :needs-payment-method="editNeedsMethod"
      :needs-tax-id="editNeedsTaxId"
      @update:open="(isOpen: boolean) => { if (!isOpen) orderEdit.closeReview(); }"
      @retry="saveOrderEdit"
      @confirm="confirmOrderEdit()"
    />
    <OperatorManagerAuth
      v-if="editing"
      :open="editManagerOpen"
      action="order_edit_refund"
      :operator-name="activeOperator?.name || ''"
      :managers="pos?.managers || []"
      :busy="editBusy"
      :error="editChallenge?.code === 'manager_approval_invalid' ? editChallenge.message : ''"
      @update:open="(isOpen: boolean) => { editManagerOpen = isOpen; }"
      @authorize="(username: string, pin: string) => confirmOrderEdit({ username, pin })"
      @authorize-badge="(badge: string) => confirmOrderEdit({ badge })"
    />
    <PosDisplayPublisher :sources="displaySources" />
  </main>
</template>
