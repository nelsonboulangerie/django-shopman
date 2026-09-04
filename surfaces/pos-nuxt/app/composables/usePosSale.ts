import type { ComputedRef } from "vue";

import type {
  Action,
  POSAddressAutocompleteProjection,
  POSCartItem,
  POSCheckoutCapabilities,
  POSCloseSaleResponse,
  POSCustomerLookupProjection,
  POSCustomerLookupResponse,
  POSCustomerSearchResponse,
  POSCustomerSearchResult,
  POSProductProjection,
  POSProjection,
  POSSaleReviewProjection,
  POSScheduleResponse,
  POSSaleReviewResponse,
  POSTabPayload,
  POSTabProjection,
  SavedAddressProjection,
  StructuredAddressProjection,
} from "~/types/pos";
import {
  actionHref,
  buildPosSaleIntent,
  cartTotalQ,
  concreteActionHref,
  formatBRL,
  moneyInputToQ,
  resolvePayment,
} from "~/utils/posIntent";
import { sanitizeTabRef as sanitizeTabRefShape, sortTabs } from "~/presentation/tabBoard";
import type { ScheduleWindow } from "~/presentation/schedule";
import {
  isPaymentCovered,
  paymentChangeQ as computeChangeQ,
  paymentProofView,
  paymentRemainingQ as computeRemainingQ,
  splitHint,
  splitShareQ,
} from "~/presentation/payment";
import {
  draftAssociationTargetStates,
  numericRefsZeroPaddedTo,
  requiresOpenTabForCart,
  requiresTabBeforeSave,
  tabRefDisallowedChars,
  tabRefMaxLength,
  tabRefPlaceholder,
} from "~/utils/posTabLifecycle";
import { cartNetTotalQ, cashLandedInDrawer, type PosReceiptSnapshot } from "~/presentation/receipt";
import { manualDiscountWasOverridden, winningDiscountLabel } from "~/presentation/lineDiscounts";
import type { PosSaleResultSnapshot } from "~/presentation/saleResult";
import type { CustomerDecision, ServerConflictCandidate } from "~/presentation/customerDecision";
import { conflictDecision, contactChangeDecision } from "~/presentation/customerDecision";
import { toast } from "vue-sonner";

type FulfillmentType = "pickup" | "delivery";
type PaymentCollection = "terminal" | "on_delivery";

interface PosSaleDeps {
  /** Read-side slices of the terminal Projection (from usePosTerminal). */
  pos: ComputedRef<POSProjection | null>;
  tabs: ComputedRef<POSTabProjection[]>;
  actions: ComputedRef<Action[]>;
  refresh: () => Promise<void>;
  /** Command transport (REST + Action) — created in the shell setup. */
  action: {
    call: <T = unknown>(
      path: string,
      options?: { method?: "POST" | "PUT" | "PATCH" | "DELETE"; body?: Record<string, unknown> },
    ) => Promise<T>;
  };
  apiPath: (path: string) => string;
  requestHeaders: Record<string, string> | undefined;
  /** Absolute Gestor de Pedidos (orders app) origin for the post-sale "open in gestor" link. */
  ordersUrl: ComputedRef<string>;
}

/**
 * Write-side of the POS sale: the open comanda's draft (`cart`) and every
 * session command (add/qty/discount, open/save/clear/rename/move/fire,
 * checkout/close, cash shift) emitted as idempotent intents via `action.call`
 * over the Projection's `Action[]`. The shell owns the Nuxt-bound primitives
 * (`action`/`apiPath`/`requestHeaders`/`ordersUrl`) and passes them in, so
 * this stays a plain composable (no Nuxt composable runs after the shell's
 * `await`). It emits commands and tracks local draft state; the orchestrator
 * decides lifecycle/policy. Screens bind to the returned state and handlers.
 */
export function usePosSale(deps: PosSaleDeps) {
  const { pos, tabs, actions, refresh, action, apiPath, requestHeaders, ordersUrl } = deps;

  // O momento mais comum de abrir a gaveta é dar troco. Antes o único jeito era
  // a chave física — ou o gancho "abrir ao imprimir" do driver, que só dispara
  // se o operador lembrar de clicar imprimir. Falha silenciosa exatamente no
  // momento em que a mão já está esperando.
  const drawer = useCounterAgent(pos);
  // A trava da gaveta: o PDV recusa INICIAR a próxima venda enquanto SABE que a
  // gaveta está aberta. Vive num composable próprio (regras + diálogo); aqui só
  // se decide ONDE ela morde — no `openTab` E no primeiro item de uma venda sem
  // comanda, que neste balcão é a venda comum (ver `addProduct`).
  const drawerLock = useDrawerLock({ drawer, actions, action });
  // O olho da hora morta: a trava só age quando alguém tenta vender, e gaveta
  // aberta no balcão parado não seria vista por ninguém.
  useDrawerIdleWatch({
    drawer,
    actions,
    action,
    minutes: computed(() => Number(pos.value?.cash_drawer?.idle_open_alert_minutes ?? 0)),
    blocked: computed(() => drawerLock.open.value),
  });

  const tabInput = ref("");
  const busy = ref(false);
  const saving = ref(false);
  // Autosave FALHOU (wi-fi caiu): a comanda tem itens não persistidos. Antes o
  // erro era engolido (.catch(() => {})) e o operador seguia lançando itens numa
  // comanda que não estava sendo salva. A UI mostra um chip "não salvo".
  const unsaved = ref(false);
  // Auto-persist the comanda (Odoo-style): no manual "Salvar". tabLoading guards
  // against re-saving right after a programmatic load (setFromTabPayload).
  const tabLoading = ref(false);
  const firing = ref(false);
  const renamingTab = ref(false);
  const cancellingSale = ref(false);
  const cancelSaleReason = ref("");
  const cancelSaleDialogOpen = ref(false);
  const cancelSaleError = ref("");
  const lookupBusy = ref(false);
  const serverError = ref("");
  // Errors surface as a dismissible floating toast (UI Thing Sonner), not an
  // inline banner. Clear the ref after showing so it doesn't linger.
  watch(serverError, (message) => {
    if (!message) return;
    toast.error(message);
    serverError.value = "";
  });
  // Falha de aprovação gerencial (PIN inválido/necessário): NÃO é um toast que some
  // — reabre o diálogo de autorização com a mensagem, senão o CTA vira "Validar" e
  // reenvia o mesmo PIN errado para sempre (beco sem saída).
  const managerApprovalError = ref("");
  // O servidor recusou com `focus: "customer"` (ex.: agendado sem cliente):
  // além do toast, a tela ABRE a identificação — motivo sem caminho de um
  // toque é beco sem saída, mesma filosofia do diálogo do gerente. Nonce, não
  // boolean: duas recusas seguidas precisam abrir duas vezes.
  const customerFocusNonce = ref(0);
  // O resultado da venda fechada — a TELA DE RESULTADO fica de pé enquanto ele
  // existe. `changeQ` é o troco CONGELADO no instante do fechamento (o cart
  // reseta logo depois e o troco computado voltaria a zero): uma fonte só para
  // o palco do operador e a tela do cliente.
  const result = ref<PosSaleResultSnapshot | null>(null);

  // PIX no PDV: o proof mostra o QR e "aguarde confirmação", mas sem polling o
  // operador nunca via a confirmação chegar (tinha de ir ao gestor). Aqui pollamos
  // o status por-order (endpoint gateado por operate_pos). O estado é explícito
  // ('polling'|'paid'|'expired') para a UI nunca girar "aguardando…" no vácuo: ao
  // desistir (terminal/timeout) a tela acusa honestamente ([[feedback_transparent_timeouts]]).
  const pixStatus = ref<"idle" | "polling" | "paid" | "expired">("idle");
  // De qual pedido é o polling atual — o chip pendente compara com ele.
  const pixOrderRef = ref("");
  // Sair da tela de resultado com o PIX ainda aguardando NÃO descarta a prova:
  // o pedido vira um chip compacto no header e o polling segue até resolver.
  const pendingPixOrderRef = ref("");
  let pixPollTimer: ReturnType<typeof setInterval> | null = null;
  function stopPixPolling() {
    if (pixPollTimer) { clearInterval(pixPollTimer); pixPollTimer = null; }
  }
  function startPixPolling(orderRef: string) {
    stopPixPolling();
    pixOrderRef.value = orderRef;
    pixStatus.value = "polling";
    let attempts = 0;
    pixPollTimer = setInterval(async () => {
      attempts += 1;
      if (attempts > 240) { pixStatus.value = "expired"; return stopPixPolling(); } // ~10 min a 2,5s → desiste
      try {
        const status = await $fetch<{ is_paid?: boolean; is_terminal?: boolean }>(
          apiPath(`/api/v1/backstage/pos/payment/${encodeURIComponent(orderRef)}/status/`),
          { credentials: "include" },
        );
        if (status?.is_paid) { pixStatus.value = "paid"; stopPixPolling(); }
        else if (status?.is_terminal) { pixStatus.value = "expired"; stopPixPolling(); } // cancelado/expirado
      } catch { /* falha transiente de rede — segue tentando */ }
    }, 2500);
  }

  // O chip pendente resolve em voz alta, nunca em silêncio: confirmou → toast
  // de sucesso; desistimos (expirado/cancelado) → aviso honesto com o próximo
  // passo. Em ambos, o chip sai do header.
  watch(pixStatus, (status) => {
    if (!pendingPixOrderRef.value || pixOrderRef.value !== pendingPixOrderRef.value) return;
    if (status === "paid") {
      toast.success(`PIX do pedido ${pendingPixOrderRef.value} confirmado.`);
      pendingPixOrderRef.value = "";
    } else if (status === "expired") {
      toast.warning(`Não confirmamos o PIX do pedido ${pendingPixOrderRef.value}. Confira no gestor ou gere um novo pagamento.`);
      pendingPixOrderRef.value = "";
    }
  });

  /**
   * Fecha a tela de resultado (CTA "Nova venda", F2, Enter). PIX ainda
   * aguardando não é descartado: vira o chip pendente no header e o polling
   * continua até resolver/expirar. Sem prova pendente, o polling encerra.
   */
  function dismissResult() {
    if (!result.value) return;
    const proof = result.value.payment;
    const pixStillPending = Boolean(proof?.isPix && proof?.hasProof) && pixStatus.value === "polling";
    if (pixStillPending) {
      pendingPixOrderRef.value = result.value.orderRef;
    } else if (!pendingPixOrderRef.value) {
      stopPixPolling();
      pixStatus.value = "idle";
    }
    result.value = null;
  }

  // Reenvio do link de pagamento — "não chegou". O servidor enfileira UMA
  // Directive nova (mesma URL, mesma cadeia WhatsApp → e-mail → SMS) e recusa
  // com motivo quando não deve: link vencido, pedido pago/cancelado, envio
  // ainda em andamento, clique cedo demais. A recusa é toast com o `detail`
  // do servidor; o botão não some, porque o motivo muda com o tempo.
  const resendingLink = ref(false);
  async function resendPaymentLink(): Promise<boolean> {
    const orderRef = result.value?.orderRef;
    if (!orderRef || resendingLink.value) return false;
    resendingLink.value = true;
    try {
      await action.call(`/api/v1/backstage/pos/orders/${encodeURIComponent(orderRef)}/resend-payment-link/`);
      toast.success("Link reenviado ao cliente");
      return true;
    } catch (error) {
      toast.error(httpErrorMessage(error, "Não foi possível reenviar o link. Copie e mande você."));
      return false;
    } finally {
      resendingLink.value = false;
    }
  }

  /**
   * Uma venda cancelada FORA da tela de resultado (Últimas vendas): se era a
   * venda em cena — palco, chip ou polling — o vestígio dela sai junto.
   */
  function onExternalSaleCancelled(orderRef: string) {
    if (pendingPixOrderRef.value === orderRef) pendingPixOrderRef.value = "";
    if (pixOrderRef.value === orderRef) {
      stopPixPolling();
      pixStatus.value = "idle";
    }
    if (result.value?.orderRef === orderRef) result.value = null;
    void refresh();
  }

  const checkoutMode = ref(false);
  // Odoo-style: the Tabs screen is the first screen; opening a tab moves to the
  // sale workspace. "Comandas" returns to the Tabs screen with the tab still open.
  const showTabs = ref(true);
  const moveDialogOpen = ref(false);
  // O diálogo de mover abre imediatamente; isto marca a fase de preparo
  // (persist + reload dos line_ids) para o spinner interno do diálogo.
  const movePreparing = ref(false);
  const review = ref<POSSaleReviewProjection | null>(null);
  const customerLookup = ref<POSCustomerLookupProjection | null>(null);
  const tabDialogOpen = ref(false);
  const tabDialogReason = ref<"start" | "save" | "cart">("start");

  const cart = reactive({
    tabRef: "",
    tabDisplay: "",
    tabSessionKey: "",
    items: [] as POSCartItem[],
    customerName: "",
    customerRef: "",
    customerPhone: "",
    customerTaxId: "",
    invoiceTaxId: "",
    /** "CPF na nota?" — pergunta do cliente, lembrada por `fiscal_prefs`. */
    wantsCpfOnInvoice: false,
    customerEmail: "",
    customerMemoryAction: "",
    fulfillmentType: "pickup" as FulfillmentType,
    deliveryAddress: "",
    deliveryAddressStructured: {} as StructuredAddressProjection,
    deliveryStreetNumber: "",
    deliveryNeighborhood: "",
    deliveryComplement: "",
    deliveryInstructions: "",
    deliveryDate: "",
    deliveryTimeSlot: "",
    // A EXCEÇÃO da taxa, quando o operador a assume. Vazio = sem exceção, e a
    // taxa é a que o servidor resolveu pelo endereço.
    deliveryFeeOverrideInput: "",
    deliveryFeeOverride: false,
    orderNotes: "",
    paymentMethod: "",
    paymentCollection: "terminal" as PaymentCollection,
    paymentTenders: [] as Array<{ method: string; amount_q: number; collection: PaymentCollection; reference?: string; _virgin?: boolean }>,
    tenderedAmountInput: "",
    /** "Troco para quanto?" do dinheiro na entrega (entrada livre, "50" / "50,00"). */
    changeForInput: "",
    receiptChannels: [] as string[],
    receiptEmail: "",
    discountType: "percent" as "percent" | "fixed",
    discountValue: "",
    discountReason: "",
    managerUsername: "",
    managerPin: "",
    clientRequestId: "",
  });

  const checkoutContract = computed(() => pos.value?.checkout || null);
  const checkoutCapabilities = computed<POSCheckoutCapabilities>(
    () => (checkoutContract.value?.capabilities ?? {}) as POSCheckoutCapabilities,
  );
  const kitchenHandoff = computed(() => checkoutCapabilities.value.kitchen_handoff ?? null);
  const canFireTab = computed(() => Boolean(kitchenHandoff.value?.fire_action_ref));
  const tabManipulation = computed(() => checkoutCapabilities.value.tab_manipulation ?? null);
  const canRenameTab = computed(() => Boolean(tabManipulation.value?.rename_action_ref));
  const saleCorrection = computed(() => checkoutCapabilities.value.sale_correction ?? null);
  const canCancelRecentSale = computed(() => Boolean(saleCorrection.value?.cancel_recent_action_ref));
  const tabMaxLength = computed(() => tabRefMaxLength(checkoutCapabilities.value));
  const tabPlaceholder = computed(() => tabRefPlaceholder(checkoutCapabilities.value));
  const tabDisallowedChars = computed(() => tabRefDisallowedChars(checkoutCapabilities.value));
  const tabZeroPadTo = computed(() => numericRefsZeroPaddedTo(checkoutCapabilities.value));
  const tabDraftTargetStates = computed(() => draftAssociationTargetStates(checkoutCapabilities.value));
  const tabRequiredForCart = computed(() => requiresOpenTabForCart(checkoutCapabilities.value));
  const tabRequiredForSave = computed(() => requiresTabBeforeSave(checkoutCapabilities.value));
  const addressAutocomplete = computed<POSAddressAutocompleteProjection | null>(() => {
    const raw = checkoutContract.value?.capabilities?.address_autocomplete;
    return raw && typeof raw === "object" ? raw as POSAddressAutocompleteProjection : null;
  });
  const totalDisplay = computed(() => formatBRL(cartTotalQ(cart.items)));
  const itemCount = computed(() => cart.items.reduce((sum, item) => sum + item.qty, 0));
  const hasOpenTab = computed(() => Boolean(cart.tabSessionKey));
  const inSaleView = computed(() => !showTabs.value && hasOpenTab.value);
  function goToTabs() {
    showTabs.value = true;
  }
  const hasDraftWithoutTab = computed(() => !hasOpenTab.value && cart.items.length > 0);
  const canUseCart = computed(() => !tabRequiredForCart.value || hasOpenTab.value);
  // A taxa EXIBIDA vem da review (o servidor resolveu pelo endereço); a exceção
  // digitada só existe quando o operador a liga. Uma pergunta, um dono.
  const deliveryFeeOverrideQ = computed<number | null>(
    () => (cart.deliveryFeeOverride ? moneyInputToQ(cart.deliveryFeeOverrideInput) : null),
  );
  const deliveryFeeQ = computed(() => review.value?.delivery_fee_q ?? 0);
  const deliveryFeeSource = computed(() => review.value?.delivery_fee_source ?? "");
  const deliveryDistanceKm = computed(() => review.value?.delivery_distance_km ?? null);
  // A data que vale: a escolhida, a que a review usou, ou o HOJE da loja. O
  // último termo é o que faz o formulário abrir já respondendo — a review só
  // existe depois que há endereço, e até lá o campo ficava vazio, que é
  // exatamente o defeito que o dono apontou.
  const deliveryDateEffective = computed(
    () => cart.deliveryDate || review.value?.delivery_date || pos.value?.delivery_today || "",
  );
  // AGENDAMENTO — as datas que a casa opera e as janelas do dia escolhido, já
  // anotadas com a prontidão DESTE carrinho.
  //
  // A review responde isso, mas só no checkout — e o agendamento acontece na
  // ABERTURA do atendimento, com o operador no telefone e o carrinho ainda pela
  // metade. Ficar sem resposta até a tela de pagamento é o que empurrava a data
  // para o fim do fluxo, onde ela nunca deveria ter morado.
  const schedule = ref<POSScheduleResponse | null>(null);
  const scheduleBusy = ref(false);
  /** A última busca falhou — a tela diz isso em vez de "carregando" para sempre. */
  const scheduleFailed = ref(false);
  let scheduleTimer: ReturnType<typeof setTimeout> | null = null;
  let scheduleSeq = 0;

  async function fetchSchedule() {
    const seq = ++scheduleSeq;
    scheduleBusy.value = true;
    scheduleFailed.value = false;
    try {
      const skus = [...new Set(cart.items.map((item) => item.sku).filter(Boolean))].join(",");
      const query = new URLSearchParams();
      if (cart.deliveryDate) query.set("date", cart.deliveryDate);
      if (skus) query.set("skus", skus);
      const response = await $fetch<POSScheduleResponse>(
        apiPath(`/api/v1/backstage/pos/schedule/?${query.toString()}`),
        { method: "GET", credentials: "include", headers: requestHeaders },
      );
      // Resposta velha chegando depois da nova reescreveria as janelas do dia
      // ERRADO — o operador troca de data mais rápido que a rede responde.
      if (seq !== scheduleSeq) return;
      schedule.value = response;
    } catch {
      // Falhar aqui não pode travar a venda — mas também não pode se disfarçar
      // de "carregando" para sempre. A tela dizia "Carregando os horários…"
      // eternamente quando o endpoint errava, e nada distinguia falha de
      // pendência. O servidor recusa a janela impossível de qualquer jeito.
      if (seq === scheduleSeq) {
        schedule.value = null;
        scheduleFailed.value = true;
      }
    } finally {
      if (seq === scheduleSeq) scheduleBusy.value = false;
    }
  }

  function scheduleRefreshSchedule() {
    if (scheduleTimer) clearTimeout(scheduleTimer);
    scheduleTimer = setTimeout(() => {
      scheduleTimer = null;
      void fetchSchedule();
    }, 200);
  }

  // O carrinho entra na pergunta: lançar a baguete de tradição DEPOIS de marcar
  // as 09:00 tem que apagar aquela janela na hora. Sem isto a escolha virava
  // impossível em silêncio e o servidor só recusava no fim, com o cliente já
  // tendo ouvido o horário.
  //
  // Mas só quando há agendamento em jogo. A venda dominante do balcão é para
  // agora e sem hora marcada: buscar a grade a cada item lançado seria uma
  // requisição por toque no produto para responder uma pergunta que ninguém fez.
  // Abrir o diálogo também busca (`refreshSchedule`), então quem VAI agendar
  // encontra a resposta pronta.
  watch(
    () => [cart.deliveryDate, cart.deliveryTimeSlot, cart.items.map((item) => item.sku).join(",")].join("|"),
    () => {
      if (!cart.deliveryDate && !cart.deliveryTimeSlot) return;
      scheduleRefreshSchedule();
    },
  );

  const scheduleToday = computed(() => schedule.value?.today || pos.value?.delivery_today || "");
  const scheduleAvailableDates = computed(() => schedule.value?.available_dates ?? []);
  const scheduleBottleneckName = computed(() => schedule.value?.bottleneck_name || "");
  const scheduleReadyAt = computed(() => schedule.value?.ready_at || "");
  /** A última data encomendável. O servidor sempre recusa além dela; isto só
   *  evita que o operador chegue a digitá-la. */
  const scheduleMaxDate = computed(() => {
    const dates = schedule.value?.available_dates ?? [];
    return dates.length ? dates[dates.length - 1]! : "";
  });

  // A data que vale: a escolhida, a que a review usou, ou o HOJE da loja. O
  // último termo é o que faz o formulário abrir já respondendo.
  // As janelas do dia escolhido. A review manda quando existe (ela conhece o
  // endereço e a taxa); fora do checkout, o agendamento responde. Nunca se diz
  // "sem janela" só porque a resposta ainda não chegou.
  const deliverySlots = computed<ScheduleWindow[]>(() => {
    if (review.value?.delivery_slots?.length) return review.value.delivery_slots;
    if (schedule.value && schedule.value.date === deliveryDateEffective.value) {
      return schedule.value.windows ?? [];
    }
    const today = pos.value?.delivery_today || "";
    if (today && deliveryDateEffective.value === today) return pos.value?.delivery_slots_today ?? [];
    return [];
  });
  const deliverySlotsPending = computed(
    () => scheduleBusy.value || (!review.value && !schedule.value && !scheduleFailed.value),
  );

  // Payment by injection (Odoo-style): the operator adds tender lines in any form;
  // the method is derived (no "mixed" selection). Finalize is gated until covered.
  //
  // Total interino: enquanto a review não chega (debounce de 450ms + round-trip),
  // o total NÃO cai no bruto do carrinho — cair no bruto fazia o `addTender`
  // lançar a linha acima do total real e o hero saltar. A ordem é: review viva →
  // último total de review desta sessão de checkout (mudou desconto/entrega e a
  // review foi invalidada) → estimativa líquida local (a mesma conta do "Total
  // parcial" do carrinho, descontos de linha aplicados).
  const lastReviewTotalQ = ref(0);
  watch(review, (value) => {
    if (value) lastReviewTotalQ.value = value.total_q;
  });
  watch(checkoutMode, (open) => {
    // Fora do checkout o carrinho volta a mudar (itens novos): o total retido
    // ficaria mentindo — zera e a próxima entrada recomeça do zero.
    if (!open) {
      lastReviewTotalQ.value = 0;
      // A divisão é desta conta. Sair do checkout com "3 pessoas" ligado faria a
      // PRÓXIMA venda lançar um terço no primeiro toque, sem ninguém ter pedido.
      splitCount.value = 0;
      splitPaidCount.value = 0;
    }
  });
  const paymentTotalQ = computed(
    () => review.value?.total_q ?? (lastReviewTotalQ.value || cartNetTotalQ(cart.items)),
  );
  const paymentRemainingQ = computed(() => computeRemainingQ(cart.paymentTenders, paymentTotalQ.value));
  const paymentChangeQ = computed(() => computeChangeQ(cart.paymentTenders, paymentTotalQ.value));
  const paymentCovered = computed(() => isPaymentCovered(cart.paymentTenders, paymentTotalQ.value));

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
  const selectedTender = () => cart.paymentTenders[selectedTenderIndex.value];

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
  // Isto já foi `cart.paymentTenders.length`, e quebrava na variação mais comum
  // do balcão: uma pessoa que paga "R$ 20 em dinheiro e o resto no cartão"
  // gastava DOIS slots. A tela pulava para "pessoa 3 de 3", o operador lia o
  // valor errado em voz alta, e a terceira pessoa ficava sem ser cobrada. O
  // caixa fechava (a última parcela absorve o resto); os três clientes não.
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
  const splitNote = computed(() => splitHint(
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
  }
  /** Uma pessoa a menos na fila — some junto com a linha que ela pagou. */
  function splitUnwind() {
    splitPaidCount.value = Math.max(0, splitPaidCount.value - 1);
  }

  // ⚠️ ONDE O DINHEIRO É RECEBIDO É DA VENDA, e as linhas TÊM que acompanhar.
  //
  // A `collection` era congelada no instante em que a linha nascia. Numa entrega
  // paga em misto: o operador lança Dinheiro R$ 40 + Cartão R$ 26,30 com "No
  // caixa" marcado, o cliente então diz que paga na porta, ele troca para "Na
  // entrega" — e as duas linhas continuavam `terminal`. O servidor grava
  // `status: "received"`, carimba `received_at` e soma os R$ 40 no LIVRO-CAIXA:
  // dinheiro que nunca entrou na gaveta, e sobra falsa no fechamento do turno.
  //
  // A tela oferece UM seletor de coleta para a venda inteira, então nunca há
  // motivo legítimo para uma linha discordar dele. Trocar reescreve todas.
  watch(() => cart.paymentCollection, (collection) => {
    for (const tender of cart.paymentTenders) tender.collection = collection;
  });

  function addTender(method: string) {
    const amountQ = Math.max(0, splitNextShareQ.value);
    if (amountQ <= 0) {
      // Tocar num método com o total já coberto era silêncio absoluto — o
      // operador tocava de novo achando que o botão quebrou. Diz o porquê e o
      // próximo passo.
      toast.info("Total já coberto. Remova uma forma para trocar.");
      return;
    }
    cart.paymentTenders.push({ method, amount_q: amountQ, collection: cart.paymentCollection, _virgin: true });
    selectedTenderIndex.value = cart.paymentTenders.length - 1;
    tenderEntry.value = null;
    // Uma pessoa a mais atendida — só aqui, que é o gesto de cobrar a PRÓXIMA.
    if (splitCount.value > 0) splitPaidCount.value += 1;
  }

  // A cash bill with no tender yet opens a cash line at that bill's value — the
  // operator already started counting, so it's NOT virgin (next bill accumulates).
  function addCashTender(amountQ: number) {
    if (!amountQ || amountQ <= 0) return;
    cart.paymentTenders.push({ method: "cash", amount_q: amountQ, collection: cart.paymentCollection, _virgin: false });
    selectedTenderIndex.value = cart.paymentTenders.length - 1;
    tenderEntry.value = null;
  }

  function removeTender(index: number) {
    cart.paymentTenders.splice(index, 1);
    splitUnwind();
    if (selectedTenderIndex.value >= cart.paymentTenders.length) {
      selectedTenderIndex.value = cart.paymentTenders.length - 1;
    }
    tenderEntry.value = null;
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
    const tender = cart.paymentTenders[selectedTenderIndex.value];
    if (!tender) return;
    const others = cart.paymentTenders.reduce(
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
    () => cart.paymentTenders[selectedTenderIndex.value]?.method || "",
  );
  const tabDialogTitle = computed(() => {
    if (tabDialogReason.value === "save") return "Associar comanda";
    return "Abrir comanda";
  });
  const tabDialogDescription = computed(() => {
    if (hasDraftWithoutTab.value) {
      return "Escolha uma comanda livre ou digite uma nova referência para salvar este atendimento sem perder recuperação no caixa.";
    }
    return "Digite uma referência de comanda ou busque uma comanda salva para iniciar o atendimento.";
  });

  const sortedTabs = computed(() => sortTabs(tabs.value));
  const otherOpenTabs = computed(() =>
    sortedTabs.value.filter((tab) => tab.state === "in_use" && tab.session_key && tab.ref !== cart.tabRef),
  );
  const suggestedSplitRef = computed(() => (cart.tabDisplay ? `${cart.tabDisplay}-2` : ""));

  const availablePaymentCollections = computed(() =>
    (pos.value?.payment_collections || []).filter((collection) =>
      collection.fulfillment_types.includes(cart.fulfillmentType)
      && collection.payment_method_refs.includes(cart.paymentMethod),
    ),
  );

  watch(pos, (projection) => {
    if (!projection) return;
    if (!cart.paymentMethod) cart.paymentMethod = projection.payment_methods[0]?.ref || "cash";
    const defaultFulfillment = projection.terminal_default_fulfillment_type === "delivery" ? "delivery" : "pickup";
    if (!cart.fulfillmentType) cart.fulfillmentType = defaultFulfillment;
    if (!projection.fulfillment_options.some((option) => option.ref === cart.fulfillmentType)) {
      cart.fulfillmentType = projection.fulfillment_options[0]?.ref || "pickup";
    }
  }, { immediate: true });

  watch(availablePaymentCollections, (collections) => {
    if (!collections.some((collection) => collection.ref === cart.paymentCollection)) {
      cart.paymentCollection = collections[0]?.ref || "terminal";
    }
  }, { immediate: true });

  // Odoo has no manual "review" step — the total is live. When something that
  // affects the TOTAL changes during checkout (discount/fulfillment/delivery
  // fee), auto re-review (debounced) so the total updates on its own. Finalize
  // stays disabled while the fresh total is in flight. Payment tenders, method,
  // fiscal/receipt and customer metadata do NOT change the total → no re-review.
  let autoReviewTimer: ReturnType<typeof setTimeout> | null = null;
  function scheduleAutoReview() {
    if (!checkoutMode.value) return;
    review.value = null;
    reviewFailed.value = false;
    if (autoReviewTimer) clearTimeout(autoReviewTimer);
    autoReviewTimer = setTimeout(() => {
      autoReviewTimer = null;
      if (checkoutMode.value && cart.items.length) reviewCheckout();
    }, 450);
  }
  watch(() => [
    cart.fulfillmentType,
    cart.deliveryAddress,
    cart.deliveryAddressStructured,
    cart.deliveryStreetNumber,
    cart.deliveryNeighborhood,
    cart.deliveryComplement,
    cart.deliveryInstructions,
    cart.deliveryDate,
    cart.deliveryTimeSlot,
    cart.deliveryFeeOverrideInput,
    cart.deliveryFeeOverride,
    cart.discountType,
    cart.discountValue,
    cart.discountReason,
  ], () => scheduleAutoReview());

  function productQty(sku: string): number {
    return cart.items.find((item) => item.sku === sku)?.qty || 0;
  }

  /**
   * ⚠️ A trava da gaveta morde AQUI, e não só no `openTab`.
   *
   * A trava nasceu presa ao `openTab` — "o único portão de entrada na venda".
   * Isso era verdade quando a comanda era obrigatória, e deixou de ser: este
   * balcão roda com `requires_open_tab_for_cart: false` e
   * `allows_direct_checkout_without_tab: true`, ou seja, a venda comum de
   * balcão (toca o produto, cobra, entrega) NUNCA passa por `openTab`. A trava
   * existia e não agia na venda que mais acontece.
   *
   * O ponto certo é o PRIMEIRO item de uma venda nova sem comanda: é o
   * equivalente exato do `openTab` neste fluxo. A regra decidida não muda —
   * trava ao INICIAR, nunca no meio: `setQty`, `restoreItem` e os itens
   * seguintes seguem livres, porque venda começada não vira refém.
   */
  function addProduct(product: POSProductProjection) {
    if (!canUseCart.value) {
      requestTabAssociation("cart");
      return;
    }
    // Balcão sem agente não tem trava nenhuma (gaveta de chave): pular o
    // `guard` aqui não muda o resultado — `readState` responderia "não sei", que
    // nunca trava — e evita atravessar um `await` no gesto mais quente do PDV.
    const startsNewSale = drawer.canKick.value && !hasOpenTab.value && !cart.items.length;
    if (startsNewSale) {
      void drawerLock.guard(async () => pushProduct(product));
      return;
    }
    pushProduct(product);
  }

  function pushProduct(product: POSProductProjection) {
    // Lançar item é sair da tela de resultado: pelo mesmo caminho do CTA
    // (PIX aguardando vira chip, nunca é descartado calado).
    dismissResult();
    review.value = null;
    checkoutMode.value = false;
    const existing = cart.items.find((item) => item.sku === product.sku);
    if (existing) {
      existing.qty += 1;
      return;
    }
    cart.items.push({
      sku: product.sku,
      name: product.name,
      price_q: product.price_q,
      qty: 1,
      notes: "",
    });
  }

  function setQty(sku: string, qty: number) {
    if (!canUseCart.value) return;
    review.value = null;
    checkoutMode.value = false;
    const existing = cart.items.find((item) => item.sku === sku);
    if (!existing) return;
    if (qty <= 0) {
      cart.items = cart.items.filter((item) => item.sku !== sku);
      return;
    }
    existing.qty = qty;
  }

  // Observação da linha (Odoo Note): o autosave persiste e o fire leva ao KDS.
  function setLineNotes(sku: string, notes: string) {
    const item = cart.items.find((entry) => entry.sku === sku);
    if (!item) return;
    item.notes = notes;
  }

  // "Desfazer" da remoção direta: devolve a linha como estava (qty, desconto,
  // observação). Idempotente: se a linha voltou por outro caminho, não duplica.
  function restoreItem(item: POSCartItem) {
    if (!canUseCart.value) return;
    if (cart.items.some((entry) => entry.sku === item.sku)) return;
    review.value = null;
    cart.items.push({ ...item });
  }

  function setLineDiscount(sku: string, value: number, reason: string, type: "percent" | "fixed" = "percent") {
    const item = cart.items.find((entry) => entry.sku === sku);
    if (!item) return;
    review.value = null;
    if (value > 0) {
      item.discount = { value, reason, type };
      // "Maior desconto ganha, um por item": o servidor DESCARTA um manual menor
      // que o automático que já venceu a linha. Sem aviso, o operador digitava a
      // cortesia, o preço não mudava e ele não tinha como saber por quê. A linha
      // mostra só o vencedor; o descarte se diz aqui, no momento do pedido.
      if (manualDiscountWasOverridden(item)) {
        toast.info(
          `Desconto não aplicado em ${item.name}: "${winningDiscountLabel(item)}" é maior, e só um desconto vale por item.`,
        );
      }
    } else {
      delete item.discount;
    }
  }

  function resetCart() {
    cart.tabRef = "";
    cart.tabDisplay = "";
    cart.tabSessionKey = "";
    cart.items = [];
    cart.customerName = "";
    cart.customerRef = "";
    cart.customerPhone = "";
    cart.customerTaxId = "";
    cart.invoiceTaxId = "";
    cart.wantsCpfOnInvoice = false;
    cart.customerEmail = "";
    cart.customerMemoryAction = "";
    cart.deliveryAddress = "";
    cart.deliveryAddressStructured = {};
    cart.deliveryStreetNumber = "";
    cart.deliveryNeighborhood = "";
    cart.deliveryComplement = "";
    cart.deliveryInstructions = "";
    cart.deliveryDate = "";
    cart.deliveryTimeSlot = "";
    cart.deliveryFeeOverrideInput = "";
    cart.deliveryFeeOverride = false;
    cart.orderNotes = "";
    cart.paymentCollection = "terminal";
    cart.paymentTenders = [];
    selectedTenderIndex.value = -1;
    cart.tenderedAmountInput = "";
    cart.changeForInput = "";
    cart.receiptChannels = [];
    cart.receiptEmail = "";
    cart.discountType = "percent";
    cart.discountValue = "";
    cart.discountReason = "";
    cart.managerUsername = "";
    cart.managerPin = "";
    cart.clientRequestId = "";
    customerLookup.value = null;
    checkoutMode.value = false;
    review.value = null;
    showTabs.value = true;
  }

  function sanitizeTabRef(value: string): string {
    return sanitizeTabRefShape(value, {
      maxLength: tabMaxLength.value,
      disallowedChars: tabDisallowedChars.value,
    });
  }

  function assignTabIdentityFromPayload(payload: POSTabPayload) {
    cart.tabRef = payload.tab_ref;
    cart.tabDisplay = payload.tab_display;
    cart.tabSessionKey = payload.tab_session_key || payload.session_key;
    showTabs.value = false;
  }

  function setFromTabPayload(payload: POSTabPayload, options: { preserveCheckout?: boolean } = {}) {
    tabLoading.value = true;
    assignTabIdentityFromPayload(payload);
    cart.items = (payload.items || []).map((item) => ({ ...item }));
    cart.customerName = payload.customer_name || "";
    cart.customerRef = payload.customer_ref || "";
    cart.customerPhone = payload.customer_phone || "";
    cart.customerTaxId = payload.customer_tax_id || "";
    cart.customerEmail = payload.customer_email || "";
    cart.fulfillmentType = payload.fulfillment_type === "delivery" ? "delivery" : "pickup";
    cart.deliveryAddress = payload.delivery_address || "";
    cart.deliveryAddressStructured = payload.delivery_address_structured || {};
    cart.deliveryStreetNumber = payload.delivery_address_structured?.street_number || "";
    cart.deliveryNeighborhood = payload.delivery_address_structured?.neighborhood || "";
    cart.deliveryComplement = payload.delivery_address_structured?.complement || "";
    cart.deliveryInstructions = payload.delivery_address_structured?.delivery_instructions || payload.delivery_address_structured?.reference || "";
    cart.deliveryDate = payload.delivery_date || "";
    cart.deliveryTimeSlot = payload.delivery_time_slot || "";
    cart.deliveryFeeOverride = payload.delivery_fee_override_q != null;
    cart.deliveryFeeOverrideInput = payload.delivery_fee_override_q != null
      ? (Number(payload.delivery_fee_override_q) / 100).toFixed(2).replace(".", ",")
      : "";
    cart.orderNotes = payload.order_notes || "";
    // preserveCheckout: o operador pode JÁ estar lançando o pagamento (método,
    // tenders, valor recebido) enquanto a comanda recarrega por baixo do shell —
    // sobrescrever aqui apagava a entrada dele no meio do gesto. Os campos de
    // ENTRADA do checkout são do operador; o payload só manda fora do checkout.
    if (!options.preserveCheckout) {
      cart.paymentMethod = payload.payment_method || cart.paymentMethod || pos.value?.payment_methods[0]?.ref || "cash";
      cart.paymentCollection = payload.payment_collection === "on_delivery" ? "on_delivery" : "terminal";
      // Spec: do not replay saved/default tender lines as operator payment input.
      cart.paymentTenders = [];
      selectedTenderIndex.value = -1;
      cart.tenderedAmountInput = payload.tendered_q ? (Number(payload.tendered_q) / 100).toFixed(2).replace(".", ",") : "";
      cart.changeForInput = "";
      cart.invoiceTaxId = cart.invoiceTaxId || String(payload.fiscal_tax_id || "");
      cart.receiptChannels = [...(payload.receipt_channels || [])];
      cart.receiptEmail = payload.receipt_email || "";
      cart.discountType = "percent";
      cart.discountValue = "";
      cart.discountReason = "";
      cart.managerUsername = "";
      cart.managerPin = "";
    }
    cart.clientRequestId = "";
    customerLookup.value = null;
    // preserveCheckout: o checkout otimista recarrega a comanda POR BAIXO do shell
    // de pagamento já aberto — sair do modo aqui devolveria o operador à venda.
    if (!options.preserveCheckout) {
      checkoutMode.value = false;
      review.value = null;
    }
    void nextTick(() => { tabLoading.value = false; });
  }

  function requestTabAssociation(reason: "start" | "save" | "cart" = "start") {
    tabDialogReason.value = reason;
    serverError.value = "";
    tabDialogOpen.value = true;
  }

  async function openTab(
    tab: POSTabProjection | string,
    options: { preserveDraft?: boolean; drawerChecked?: boolean } = {},
  ) {
    if (busy.value) return; // guarda de reentrância
    const tabRef = sanitizeTabRef(typeof tab === "string" ? tab : tab.ref);
    if (!tabRef) return;
    if (hasDraftWithoutTab.value && !options.preserveDraft) {
      tabInput.value = tabRef;
      requestTabAssociation("start");
      return;
    }
    // A trava morde AQUI, no toque que inicia a próxima venda — e só aqui.
    // `preserveDraft` é uma venda JÁ começada escolhendo comanda: não vira refém.
    // `drawerChecked` é a volta pela trava (fechou ou o gerente liberou): não
    // pergunta duas vezes.
    if (!options.preserveDraft && !options.drawerChecked) {
      await drawerLock.guard(() => openTab(tab, { ...options, drawerChecked: true }));
      return;
    }
    serverError.value = "";
    // Abrir comanda com a tela de resultado ainda de pé é sair dela: passa pelo
    // mesmo caminho do CTA (PIX aguardando vira chip, nunca é descartado).
    dismissResult();
    busy.value = true;
    try {
      const path = concreteActionHref(
        actions.value,
        "open_tab",
        "/api/v1/backstage/pos/tabs/{tab_ref}/open/",
        { tab_ref: tabRef },
      );
      const payload = await action.call<POSTabPayload>(path);
      if (options.preserveDraft && cart.items.length) {
        if ((payload.items || []).length) {
          throw new Error("Esta comanda já possui pedido. Abra a comanda separadamente ou escolha uma comanda livre.");
        }
        assignTabIdentityFromPayload(payload);
        checkoutMode.value = false;
        review.value = null;
      } else {
        setFromTabPayload(payload);
      }
      tabInput.value = "";
      await refresh();
    } catch (error) {
      serverError.value = httpErrorMessage(error, "Não foi possível abrir a comanda. Confira a referência ou escolha uma no quadro.");
    } finally {
      busy.value = false;
    }
  }

  async function openTabFromDialog(tab: POSTabProjection | string) {
    const reason = tabDialogReason.value;
    const preserveDraft = hasDraftWithoutTab.value;
    const proceed = async () => {
      await openTab(tab, { preserveDraft, drawerChecked: true });
      if (!cart.tabSessionKey) return;
      tabDialogOpen.value = false;
      if (reason === "save" && cart.items.length) {
        await saveTab();
      }
    };
    // A trava passa por fora do `openTab` aqui para que, liberada, o fechamento
    // do seletor venha junto — senão o diálogo ficaria aberto sobre a venda.
    if (preserveDraft) {
      await proceed();
      return;
    }
    await drawerLock.guard(proceed);
  }

  function currentIntentState() {
    const structured: StructuredAddressProjection = {
      ...cart.deliveryAddressStructured,
      route: cart.deliveryAddress.trim() || cart.deliveryAddressStructured.route || "",
      street_number: cart.deliveryStreetNumber.trim() || cart.deliveryAddressStructured.street_number || "",
      neighborhood: cart.deliveryNeighborhood.trim() || cart.deliveryAddressStructured.neighborhood || "",
      complement: cart.deliveryComplement.trim() || cart.deliveryAddressStructured.complement || "",
      delivery_instructions: cart.deliveryInstructions.trim() || cart.deliveryAddressStructured.delivery_instructions || "",
      reference: cart.deliveryInstructions.trim() || cart.deliveryAddressStructured.reference || "",
    };
    const deliveryAddressParts = [
      structured.formatted_address || "",
      structured.route || "",
      structured.street_number || "",
      structured.neighborhood || "",
    ]
      .filter(Boolean);
    const deliveryAddress = structured.formatted_address || deliveryAddressParts.join(", ");
    const discountValueNum = Number(String(cart.discountValue).replace(",", ".").replace(/[^0-9.]/g, "")) || 0;
    const manualDiscount = discountValueNum > 0
      ? { type: cart.discountType, value: discountValueNum, reason: cart.discountReason || "cortesia" }
      : null;
    const managerApproval = cart.managerUsername.trim() && cart.managerPin.trim()
      ? { username: cart.managerUsername.trim(), pin: cart.managerPin.trim() }
      : null;
    const resolvedPayment = resolvePayment(cart.paymentTenders, paymentTotalQ.value);
    return {
      tabRef: cart.tabRef,
      tabSessionKey: cart.tabSessionKey,
      items: cart.items,
      customerName: cart.customerName,
      customerRef: cart.customerRef,
      customerPhone: cart.customerPhone,
      customerTaxId: cart.customerTaxId,
      // O switch é que decide se o documento viaja. Desligado, o valor fica
      // guardado na tela (religar devolve) mas NÃO vai para a nota.
      invoiceTaxId: cart.wantsCpfOnInvoice ? cart.invoiceTaxId : "",
      customerEmail: cart.customerEmail,
      customerMemoryAction: cart.customerMemoryAction,
      fulfillmentType: cart.fulfillmentType,
      deliveryAddress,
      deliveryAddressStructured: structured,
      deliveryComplement: cart.deliveryComplement,
      deliveryInstructions: cart.deliveryInstructions,
      deliveryDate: cart.deliveryDate,
      deliveryTimeSlot: cart.deliveryTimeSlot,
      deliveryFeeOverrideQ: deliveryFeeOverrideQ.value,
      orderNotes: cart.orderNotes,
      paymentMethod: resolvedPayment.paymentMethod,
      paymentCollection: cart.paymentCollection,
      paymentTenders: resolvedPayment.paymentTenders,
      tenderedQ: resolvedPayment.tenderedQ,
      changeForQ: cart.fulfillmentType === "delivery" && cart.paymentCollection === "on_delivery"
        ? moneyInputToQ(cart.changeForInput)
        : 0,
      receiptChannels: cart.receiptChannels,
      receiptEmail: cart.receiptEmail || cart.customerEmail,
      manualDiscount,
      managerApproval,
      clientRequestId: cart.clientRequestId || newClientRequestId(),
    };
  }

  function applyStructuredAddress(address: StructuredAddressProjection) {
    cart.deliveryAddressStructured = {
      ...cart.deliveryAddressStructured,
      ...address,
    };
    cart.deliveryAddress = address.route || address.formatted_address || cart.deliveryAddress;
    cart.deliveryStreetNumber = address.street_number || cart.deliveryStreetNumber;
    cart.deliveryNeighborhood = address.neighborhood || cart.deliveryNeighborhood;
    cart.deliveryComplement = address.complement || cart.deliveryComplement;
    cart.deliveryInstructions = address.delivery_instructions || address.reference || cart.deliveryInstructions;
  }

  function applySavedAddress(address: SavedAddressProjection) {
    applyStructuredAddress(address);
    cart.deliveryAddress = address.route || address.formatted_address;
  }

  async function lookupCustomer() {
    // O ref vence: é a chave exata do cadastro (cliente sem telefone existe, e
    // dois cadastros podem dividir um telefone de recado). O telefone segue
    // como fallback do fluxo antigo (digitou o fone no form e pediu lookup).
    const customerRef = cart.customerRef.trim();
    const phone = cart.customerPhone.trim();
    if (!customerRef && !phone) return;
    lookupBusy.value = true;
    serverError.value = "";
    try {
      const path = concreteActionHref(
        actions.value,
        "customer_lookup",
        "/api/v1/backstage/pos/customer/lookup/?phone={phone}&ref={ref}",
        { phone, ref: customerRef },
      );
      const response = await $fetch<POSCustomerLookupResponse>(apiPath(path), {
        method: "GET",
        credentials: "include",
        headers: requestHeaders,
      });
      customerLookup.value = response.customer;
      if (!response.customer) return;
      cart.customerRef = response.customer.ref;
      cart.customerName = response.customer.name || cart.customerName;
      cart.customerPhone = response.customer.phone || cart.customerPhone;
      cart.customerEmail = response.customer.email || cart.customerEmail;
      // CPF conhecido entra como DEFAULT; o campo continua editável — o cliente
      // pode pedir outro CPF nesta venda sem tocar no cadastro.
      cart.customerTaxId = cart.customerTaxId || response.customer.tax_id || "";
      // O cliente que já optou uma vez chega com o checkout PRÉ-MARCADO — e o
      // operador pode desligar nesta venda ("hoje não"): pré-marcar não é impor.
      // O CPF do cadastro entra como DEFAULT do campo da nota; o switch é que
      // decide se ele viaja.
      const prefs = response.customer.fiscal_prefs || {};
      cart.invoiceTaxId = cart.invoiceTaxId || response.customer.tax_id || "";
      if (prefs.cpf_na_nota) cart.wantsCpfOnInvoice = true;
      if (prefs.email_receipt && !cart.receiptChannels.includes("email")) {
        cart.receiptChannels = [...cart.receiptChannels, "email"];
      }
      // Aniversário HOJE: aviso elegante e discreto ao operador — omotenashi de
      // balcão. Só promete desconto se uma promoção de aniversariante EXISTE
      // configurada (o Core a aplica sozinho no reprice); sem promoção, o aviso
      // é só o parabéns.
      if (response.customer.is_birthday_today) {
        const nome = (response.customer.name || "").split(" ")[0] || "o cliente";
        toast.info(`🎂 Hoje é aniversário de ${nome}!`, {
          description: response.customer.birthday_promo_label
            ? `A promoção "${response.customer.birthday_promo_label}" se aplica sozinha na venda.`
            : "Um parabéns cai bem.",
          duration: 8000,
        });
      }
      if (response.customer.is_staff) cart.customerMemoryAction = "";
      if (cart.fulfillmentType === "delivery" && response.customer.default_address && !cart.deliveryAddress.trim()) {
        applySavedAddress(response.customer.default_address);
      }
    } catch (error) {
      serverError.value = httpErrorMessage(error, "Falha ao buscar cliente.");
    } finally {
      lookupBusy.value = false;
    }
  }

  // Just-in-time get-or-create: when the operator finishes defining a customer
  // (picks a result, or types a new name+phone and concludes), resolve OR create
  // the record NOW — not deferred to order commit — so the customer (ref, memory,
  // address) exists and attaches to the cart/tab immediately. Idempotent: an
  // existing customer is found, a fresh one is created once.
  // A escolha que é DO OPERADOR: conflito de contato (o WhatsApp digitado já é
  // de outro cadastro) ou correção de contato (o do cliente associado vai
  // mudar). Enquanto ela existe, o modal fica aberto esperando a resposta.
  const customerDecision = ref<CustomerDecision | null>(null);

  async function resolveCustomer(options: { contactCorrection?: boolean } = {}) {
    const customerRef = cart.customerRef.trim();
    const name = cart.customerName.trim();
    const phone = cart.customerPhone.trim();
    const taxId = cart.customerTaxId.trim();
    const email = cart.customerEmail.trim();
    if (!customerRef && !name && !phone && !taxId && !email) return;

    // CORRIGIR o contato do cliente associado é mudar a identidade de contato
    // de um cadastro — o número por onde ele recebe aviso de pronto. Isso é dito
    // ANTES de acontecer, com os dois valores nomeados. Sem a palavra do
    // operador, o servidor segue só preenchendo lacuna.
    if (!options.contactCorrection) {
      const change = contactChangeDecision({
        customerRef,
        customerName: name || customerLookup.value?.name || "",
        registeredPhone: customerLookup.value?.phone || "",
        typedPhone: phone,
        registeredEmail: customerLookup.value?.email || "",
        typedEmail: email,
      });
      if (change) {
        customerDecision.value = change;
        return;
      }
    }

    lookupBusy.value = true;
    serverError.value = "";
    try {
      const path = actionHref(actions.value, "customer_resolve", "/api/v1/backstage/pos/customer/resolve/");
      const response = await action.call<POSCustomerLookupResponse>(path, {
        body: {
          // ⚠️ O cliente JÁ ASSOCIADO viaja. Sem ele o servidor achava um único
          // candidato pelo telefone digitado e TROCAVA o dono do pedido em
          // silêncio — com o ref, os dois candidatos aparecem e a recusa
          // devolve a escolha para quem está no balcão.
          customer_ref: customerRef,
          customer_name: name,
          customer_phone: phone,
          customer_tax_id: taxId,
          customer_email: email,
          ...(options.contactCorrection ? { customer_contact_correction: true } : {}),
        },
      });
      customerDecision.value = null;
      if (!response.customer) return;
      // "Criei agora" ≠ "achei": a confirmação visual do modal distingue.
      customerResolvedNew.value = !!response.created;
      customerLookup.value = response.customer;
      cart.customerRef = response.customer.ref;
      cart.customerName = response.customer.name || cart.customerName;
      cart.customerPhone = response.customer.phone || cart.customerPhone;
      cart.customerEmail = response.customer.email || cart.customerEmail;
      // CPF conhecido entra como DEFAULT; o campo continua editável — o cliente
      // pode pedir outro CPF nesta venda sem tocar no cadastro.
      cart.customerTaxId = cart.customerTaxId || response.customer.tax_id || "";
      // O cliente que já optou uma vez chega com o checkout PRÉ-MARCADO — e o
      // operador pode desligar nesta venda ("hoje não"): pré-marcar não é impor.
      // O CPF do cadastro entra como DEFAULT do campo da nota; o switch é que
      // decide se ele viaja.
      const prefs = response.customer.fiscal_prefs || {};
      cart.invoiceTaxId = cart.invoiceTaxId || response.customer.tax_id || "";
      if (prefs.cpf_na_nota) cart.wantsCpfOnInvoice = true;
      if (prefs.email_receipt && !cart.receiptChannels.includes("email")) {
        cart.receiptChannels = [...cart.receiptChannels, "email"];
      }
      // Aniversário HOJE: aviso elegante e discreto ao operador — omotenashi de
      // balcão. Só promete desconto se uma promoção de aniversariante EXISTE
      // configurada (o Core a aplica sozinho no reprice); sem promoção, o aviso
      // é só o parabéns.
      if (response.customer.is_birthday_today) {
        const nome = (response.customer.name || "").split(" ")[0] || "o cliente";
        toast.info(`🎂 Hoje é aniversário de ${nome}!`, {
          description: response.customer.birthday_promo_label
            ? `A promoção "${response.customer.birthday_promo_label}" se aplica sozinha na venda.`
            : "Um parabéns cai bem.",
          duration: 8000,
        });
      }
      if (cart.fulfillmentType === "delivery" && response.customer.default_address && !cart.deliveryAddress.trim()) {
        applySavedAddress(response.customer.default_address);
      }
    } catch (error) {
      const data = (httpError(error).data || {}) as { error?: { field?: string; candidates?: ServerConflictCandidate[] } };
      if (httpErrorCode(error) === "customer_conflict") {
        const decision = conflictDecision({
          field: data.error?.field,
          candidates: data.error?.candidates,
          typed: phone || email || taxId,
        });
        if (decision) {
          customerDecision.value = decision;
          return;
        }
      }
      serverError.value = httpErrorMessage(error, "Falha ao salvar o cliente.");
    } finally {
      lookupBusy.value = false;
    }
  }

  /** O operador assumiu a mudança. Trocar de cliente pelo caminho EXPLÍCITO —
   *  o mesmo destino da busca, e nunca um efeito colateral de digitar. */
  async function confirmCustomerDecision() {
    const decision = customerDecision.value;
    if (!decision) return;
    customerDecision.value = null;
    if (decision.kind === "contact_change") {
      await resolveCustomer({ contactCorrection: true });
      return;
    }
    const other = decision.other;
    if (!other) return;
    cart.customerRef = other.ref;
    cart.customerName = other.name;
    // Os campos do cliente ANTERIOR não podem sobrar: o CPF da nota era dele, e
    // o `lookupCustomer` pelo ref repõe tudo que é do cadastro novo.
    cart.customerPhone = "";
    cart.customerEmail = "";
    cart.customerTaxId = "";
    cart.invoiceTaxId = "";
    cart.wantsCpfOnInvoice = false;
    cart.customerMemoryAction = "";
    customerLookup.value = null;
    customerSearchResults.value = [];
    customerResolvedNew.value = false;
    await lookupCustomer();
  }

  /** O operador ficou com o que estava: o valor digitado é DESCARTADO e o campo
   *  volta ao do cadastro associado. */
  function cancelCustomerDecision() {
    const decision = customerDecision.value;
    customerDecision.value = null;
    if (!decision) return;
    const restored = decision.current?.value || "";
    if (decision.field === "phone") cart.customerPhone = restored;
    else if (decision.field === "email") cart.customerEmail = restored;
    else cart.customerTaxId = restored;
  }

  // Multi-key customer search (name/phone/CPF/email): the customer modal's search
  // field hits this; results are a list to pick from. Picking one fills the cart
  // and runs the full lookup (memory + saved address).
  const customerSearchResults = ref<POSCustomerSearchResult[]>([]);
  const customerSearchBusy = ref(false);
  // O cliente associado foi CRIADO agora (resolve just-in-time devolveu
  // created=true) — a confirmação do modal distingue novo × encontrado.
  const customerResolvedNew = ref(false);
  async function searchCustomers(query: string) {
    const q = (query || "").trim();
    if (q.length < 2) { customerSearchResults.value = []; return; }
    customerSearchBusy.value = true;
    try {
      const path = concreteActionHref(
        actions.value,
        "customer_search",
        "/api/v1/backstage/pos/customer/search/?q={query}",
        { query: q },
      );
      const response = await $fetch<POSCustomerSearchResponse>(apiPath(path), {
        method: "GET",
        credentials: "include",
        headers: requestHeaders,
      });
      customerSearchResults.value = response.results || [];
    } catch {
      customerSearchResults.value = [];
    } finally {
      customerSearchBusy.value = false;
    }
  }
  async function selectCustomerResult(result: POSCustomerSearchResult) {
    cart.customerRef = result.ref;
    cart.customerName = result.name;
    cart.customerPhone = result.phone || cart.customerPhone;
    cart.customerEmail = result.email || cart.customerEmail;
    cart.customerTaxId = result.document || cart.customerTaxId;
    customerSearchResults.value = [];
    customerResolvedNew.value = false; // escolhido da lista = cadastro existente
    // Load memory + saved address for the chosen customer — pelo ref, que é a
    // chave exata (o gate por telefone deixava cliente sem fone sem memória).
    await lookupCustomer();
  }

  // Disassociate the customer from the tab (Odoo's UNSELECT): drop every customer
  // field + the loaded lookup so nothing lingers (clearing only the name would
  // leave customerRef attached). The debounced autosave then persists the removal.
  function clearCustomer() {
    cart.customerRef = "";
    cart.customerName = "";
    cart.customerPhone = "";
    cart.customerEmail = "";
    cart.customerTaxId = "";
    cart.invoiceTaxId = "";
    cart.wantsCpfOnInvoice = false;
    cart.customerMemoryAction = "";
    customerLookup.value = null;
    customerSearchResults.value = [];
    customerResolvedNew.value = false;
    customerDecision.value = null;
  }

  function productFromMemoryItem(item: Record<string, unknown>): POSProductProjection | null {
    const sku = String(item.sku || "");
    return pos.value?.products.find((product) => product.sku === sku) || null;
  }

  function addProductQty(product: POSProductProjection, qty: number) {
    for (let idx = 0; idx < Math.max(1, qty); idx += 1) addProduct(product);
  }

  function applyCustomerFavorite() {
    const item = customerLookup.value?.memory.favorite_item;
    if (!item) return;
    const product = productFromMemoryItem(item);
    if (!product) return;
    addProductQty(product, 1);
    cart.customerMemoryAction = "favorite_item";
  }

  function repeatCustomerLastOrder() {
    const items = customerLookup.value?.memory.last_order_items || [];
    for (const item of items) {
      const product = productFromMemoryItem(item);
      if (!product) continue;
      const qty = Number.parseInt(String(item.qty || 1), 10);
      addProductQty(product, Number.isFinite(qty) ? qty : 1);
    }
    if (items.length) cart.customerMemoryAction = "last_order";
  }

  function buildCurrentIntent() {
    return buildPosSaleIntent(
      currentIntentState(),
      checkoutContract.value?.intent_version,
    );
  }

  // Serialize all tab persistence so the debounced autosave can never race the
  // explicit save inside checkout/fire/move (concurrent save_tab → DB lock).
  let persistQueue: Promise<unknown> = Promise.resolve();
  function persistTab(quiet = false): Promise<void> {
    const run = async () => {
      const state = currentIntentState();
      cart.clientRequestId = state.clientRequestId;
      await action.call(actionHref(actions.value, "save_tab", "/api/v1/backstage/pos/tabs/save/"), {
        body: buildPosSaleIntent(state, checkoutContract.value?.intent_version),
      });
      unsaved.value = false; // persistiu de verdade
      if (!quiet) await refresh();
    };
    persistQueue = persistQueue.then(run, run);
    return persistQueue as Promise<void>;
  }

  // Retry do autosave: numa rede instável, uma comanda parada com save falho
  // precisa tentar de novo sozinha (o próximo lançamento também reagenda).
  let autosaveRetryTimer: ReturnType<typeof setTimeout> | null = null;
  function onAutosaveFailed() {
    unsaved.value = true;
    if (autosaveRetryTimer) return;
    autosaveRetryTimer = setTimeout(() => {
      autosaveRetryTimer = null;
      if (hasOpenTab.value && !checkoutMode.value && !busy.value && !saving.value) {
        persistTab(true).catch(() => onAutosaveFailed());
      }
    }, 5000);
  }

  // Debounced auto-persist: fires on cart/sale-data changes while a tab is open,
  // outside checkout. Quiet save (no projection refresh) to stay light.
  let autosaveTimer: ReturnType<typeof setTimeout> | null = null;
  function scheduleAutosave() {
    if (tabLoading.value || !hasOpenTab.value || checkoutMode.value) return;
    if (autosaveTimer) clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(() => {
      autosaveTimer = null;
      if (!hasOpenTab.value || checkoutMode.value || busy.value || saving.value) return;
      persistTab(true).catch(() => onAutosaveFailed());
    }, 1200);
  }
  watch(() => [
    cart.items,
    cart.customerName,
    cart.customerRef,
    cart.customerPhone,
    cart.customerTaxId,
    cart.customerEmail,
    cart.fulfillmentType,
    cart.deliveryAddress,
    cart.deliveryStreetNumber,
    cart.deliveryNeighborhood,
    cart.deliveryComplement,
    cart.deliveryInstructions,
    cart.deliveryDate,
    cart.deliveryTimeSlot,
    cart.deliveryFeeOverrideInput,
    cart.deliveryFeeOverride,
    cart.orderNotes,
  ], () => scheduleAutosave(), { deep: true });

  async function saveTab() {
    if (tabRequiredForSave.value && !hasOpenTab.value) {
      requestTabAssociation("save");
      return;
    }
    serverError.value = "";
    saving.value = true;
    try {
      await persistTab();
    } catch (error) {
      serverError.value = httpErrorMessage(error, "Não foi possível salvar a comanda. Os itens seguem na tela; confira a conexão e tente de novo.");
    } finally {
      saving.value = false;
    }
  }

  async function reloadCurrentTab(options: { preserveCheckout?: boolean } = {}) {
    if (!cart.tabRef) return;
    const path = concreteActionHref(
      actions.value,
      "open_tab",
      "/api/v1/backstage/pos/tabs/{tab_ref}/open/",
      { tab_ref: cart.tabRef },
    );
    const payload = await action.call<POSTabPayload>(path);
    setFromTabPayload(payload, options);
    await refresh();
  }

  async function reviewSale() {
    if (!cart.items.length) return null;
    const state = currentIntentState();
    cart.clientRequestId = state.clientRequestId;
    const response = await action.call<POSSaleReviewResponse>(
      actionHref(actions.value, "review_sale", "/api/v1/backstage/pos/sale/review/"),
      { body: buildPosSaleIntent(state, checkoutContract.value?.intent_version) },
    );
    review.value = response.review;
    return response.review;
  }

  async function prepareCheckout() {
    if (!cart.items.length) return;
    serverError.value = "";
    dismissResult();
    busy.value = true;
    // Otimista: o shell de pagamento abre JÁ (total interino, review por baixo) em
    // vez de segurar o operador na tela de venda durante os round-trips de
    // persistência — era isso que fazia a tela "piscar" duas vezes no Cobrar.
    checkoutMode.value = true;
    review.value = null;
    try {
      if (hasOpenTab.value) {
        await persistTab();
        await reloadCurrentTab({ preserveCheckout: true });
      }
      await reviewSale();
    } catch (error) {
      // O checkout não abriu de verdade: volta à venda com o motivo no toast.
      checkoutMode.value = false;
      serverError.value = httpErrorMessage(error, "Falha ao revisar checkout.");
    } finally {
      busy.value = false;
    }
  }

  /** A última revisão FALHOU e não há total válido na tela. Ver `reviewCheckout`. */
  const reviewFailed = ref(false);

  async function reviewCheckout() {
    if (busy.value) return; // guarda de reentrância
    if (!cart.items.length) return;
    serverError.value = "";
    dismissResult();
    busy.value = true;
    try {
      await reviewSale();
      reviewFailed.value = false;
    } catch (error) {
      // ⚠️ SEM ISTO O PDV TRAVAVA PARA SEMPRE. `scheduleAutoReview` zera a
      // `review` e agenda o refetch; se ele lançasse (um piscar de Wi-Fi), o
      // catch emitia um toast que some em segundos e a `review` ficava `null`
      // sem ninguém reagendar. Resultado: botão desabilitado, com spinner,
      // escrito "Atualizando…", e o motivo do bloqueio devolvia string vazia
      // justo nesse ramo — zero explicação na tela, com o cliente na frente. A
      // única saída era F4 (não documentado) ou Esc, que derruba o checkout.
      reviewFailed.value = true;
      serverError.value = httpErrorMessage(error, "Falha ao revisar venda.");
    } finally {
      busy.value = false;
    }
  }

  async function submitSale() {
    if (busy.value) return; // guarda de reentrância: duplo-toque não dispara 2 close_sale
    if (!cart.items.length) return;
    if (!checkoutMode.value) {
      await prepareCheckout();
      return;
    }
    // Spec: the commit click must not hide an implicit review. If the review is
    // stale (sale data changed), return to review instead of committing.
    if (!review.value) {
      await reviewCheckout();
      return;
    }
    serverError.value = "";
    managerApprovalError.value = "";
    result.value = null;
    busy.value = true;
    try {
      const response = await action.call<POSCloseSaleResponse>(
        actionHref(actions.value, "close_sale", "/api/v1/backstage/pos/sale/close/"),
        { body: buildCurrentIntent() },
      );
      if (response.ok && response.order_ref) {
        const orderRef = response.order_ref;
        // Freeze a receipt snapshot before the cart resets (spec §D3): the
        // printed receipt is a record of what was sold, not live state.
        const receipt: PosReceiptSnapshot = {
          orderRef,
          tabDisplay: cart.tabDisplay,
          customerName: cart.customerName,
          items: cart.items.map((item) => ({
            name: item.name,
            qty: item.qty,
            price_q: item.price_q,
            discountPct: item.discount?.value || 0,
          })),
          totalDisplay: review.value?.total_display || "",
          payments: cart.paymentTenders.map((tender) => ({
            method: tender.method,
            amount_q: tender.amount_q,
            // ONDE foi recebido viaja com a linha: é o que separa dinheiro na
            // gaveta de dinheiro que sai com o entregador.
            collection: tender.collection,
          })),
          fulfillmentLabel: pos.value?.fulfillment_options.find((option) => option.ref === cart.fulfillmentType)?.label || cart.fulfillmentType,
          printedAtMs: Date.now(),
        };
        const proof = paymentProofView(response.payment);
        result.value = {
          orderRef,
          nextUrl: `${ordersUrl.value.replace(/\/+$/, "")}/${encodeURIComponent(orderRef)}`,
          payment: proof,
          receipt,
          // O botão da DANFE segue a REGRA fiscal, não o toggle: cartão e pix
          // emitem por forma de pagamento, sem o operador marcar nada.
          fiscalExpected: !!response.fiscal_expected,
          // Troco congelado AGORA — o resetCart logo abaixo apaga os tenders e
          // o troco computado voltaria a zero. Uma fonte só: a tela de
          // resultado do operador e a tela do cliente leem daqui.
          changeQ: Math.max(0, paymentChangeQ.value),
          // Congelado pelo mesmo motivo do troco: o `resetCart` logo abaixo
          // apaga os canais, e a nota autoriza depois — segundos ou minutos.
          wantsPrintedInvoice: cart.receiptChannels.includes("print"),
        };
        // PIX pendente → polla até confirmar; outros métodos já saem resolvidos.
        if (proof?.isPix && proof?.hasProof) {
          if (pendingPixOrderRef.value) {
            // Um só polling por estação: a prova anterior ainda pendente não
            // pode ser abandonada calada — acusa e aponta o gestor.
            toast.warning(`Não confirmamos o PIX do pedido ${pendingPixOrderRef.value}. Confira no gestor ou gere um novo pagamento.`);
            pendingPixOrderRef.value = "";
          }
          startPixPolling(orderRef);
        } else if (!pendingPixOrderRef.value) {
          // Sem prova nova e sem chip pendente: nada a pollar. (Com chip, o
          // polling da venda anterior segue vivo até resolver/expirar.)
          stopPixPolling();
          pixStatus.value = "idle";
        }
        // Entrou dinheiro na gaveta → ela precisa abrir para sair troco. Lido
        // do snapshot congelado, não do cart, que a linha abaixo já zerou.
        // Sem await: a venda terminou, e a tela não espera o spooler.
        // SÓ o dinheiro que entrou NA GAVETA a faz abrir — ver `cashLandedInDrawer`.
        if (cashLandedInDrawer(receipt.payments) && drawer.opensOnCashSale.value) {
          void drawer.kick("cash_sale");
        }
        resetCart();
        await refresh();
      }
    } catch (error) {
      const failure = (httpError(error).data as { error?: { code?: string; message?: string; recovery?: string; focus?: string } } | null)?.error;
      if (failure?.code === "manager_approval_invalid" || failure?.code === "manager_approval_required") {
        // Aprovação recusada: limpa o gerente/PIN e reabre o diálogo com a mensagem,
        // em vez de deixar o CTA reenviar as mesmas credenciais erradas.
        cart.managerUsername = "";
        cart.managerPin = "";
        managerApprovalError.value = failure.recovery || failure.message || "Aprovação gerencial inválida.";
      } else if (failure?.focus === "customer") {
        // Recusa que se resolve identificando o cliente (ex.: agendado sem
        // cliente): o toast diz o porquê e a tela abre a identificação.
        serverError.value = failure.recovery || failure.message || "Identifique o cliente para finalizar a venda.";
        customerFocusNonce.value += 1;
      } else {
        serverError.value = httpErrorMessage(error, "Não foi possível finalizar a venda. O pedido não foi fechado; revise o pagamento e valide de novo.");
      }
    } finally {
      busy.value = false;
    }
  }

  async function clearCurrentTab() {
    if (!cart.tabSessionKey) {
      resetCart();
      return;
    }
    serverError.value = "";
    busy.value = true;
    try {
      const path = concreteActionHref(
        actions.value,
        "clear_tab",
        "/api/v1/backstage/pos/tabs/{session_key}/clear/",
        { session_key: cart.tabSessionKey },
      );
      await action.call(path, { method: "DELETE" });
      resetCart();
      await refresh();
    } catch (error) {
      serverError.value = httpErrorMessage(error, "Falha ao liberar comanda.");
    } finally {
      busy.value = false;
    }
  }

  function newClientRequestId(): string {
    const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `pos:${random}`;
  }

  async function openMoveDialog() {
    if (!hasOpenTab.value || !cart.items.length) return;
    // O diálogo abre JÁ, com spinner interno — os dois round-trips (persist +
    // reload, que renovam os line_ids que o move exige) rodam por baixo. Antes
    // eles vinham ANTES do diálogo e o botão parecia morto por um segundo.
    serverError.value = "";
    moveDialogOpen.value = true;
    movePreparing.value = true;
    busy.value = true;
    try {
      await persistTab();
      await reloadCurrentTab();
    } catch (error) {
      moveDialogOpen.value = false;
      serverError.value = httpErrorMessage(error, "Falha ao preparar a comanda para mover itens.");
    } finally {
      movePreparing.value = false;
      busy.value = false;
    }
  }

  async function submitMove(payload: {
    mode: "split" | "transfer" | "merge";
    lineIds: string[];
    toTabRef?: string;
    toSessionKey?: string;
    closeSource?: boolean;
  }) {
    if (!cart.tabSessionKey) return;
    serverError.value = "";
    busy.value = true;
    try {
      const body: Record<string, unknown> = {
        from_session_key: cart.tabSessionKey,
        line_ids: payload.lineIds,
      };
      if (payload.toTabRef) body.to_tab_ref = payload.toTabRef;
      if (payload.toSessionKey) body.to_session_key = payload.toSessionKey;
      if (payload.closeSource) body.close_source_when_empty = true;
      const response = await action.call<{ source_closed: boolean; source: POSTabPayload | null }>(
        actionHref(actions.value, "move_tab_lines", "/api/v1/backstage/pos/tabs/move-lines/"),
        { body },
      );
      moveDialogOpen.value = false;
      if (response.source_closed || !response.source) {
        resetCart();
      } else {
        setFromTabPayload(response.source);
      }
      await refresh();
    } catch (error) {
      serverError.value = httpErrorMessage(error, "Falha ao mover itens.");
    } finally {
      busy.value = false;
    }
  }

  // Resolve the live server line_ids for a set of cart skus after persisting:
  // save_tab regenerates line_ids, so we persist + reload (same pattern as the
  // move dialog) and read the fresh ids the kitchen endpoints expect.
  async function freshLineIdsForSkus(skus: string[], firedState: "fired" | "unfired"): Promise<string[]> {
    await persistTab(true);
    await reloadCurrentTab();
    const wantFired = firedState === "fired";
    return cart.items
      .filter((item) => skus.includes(item.sku) && item.line_id && Boolean(item.fired) === wantFired)
      .map((item) => item.line_id as string);
  }

  async function fireTab(selectedSkus?: string[]) {
    if (!cart.tabSessionKey) return;
    serverError.value = "";
    firing.value = true;
    try {
      const body: Record<string, unknown> = { client_request_id: newClientRequestId() };
      if (selectedSkus && selectedSkus.length) {
        // Multi-select (spec §2.2): fire exactly the chosen lines. Resolve their
        // fresh line_ids (persist regenerates them) before targeting.
        const lineIds = await freshLineIdsForSkus(selectedSkus, "unfired");
        if (!lineIds.length) return;
        body.line_ids = lineIds;
      } else {
        // Delta fire: persist on-screen items so the server fires exactly what the
        // operator sees, then fire all unfired lines (no line_ids = the delta).
        await persistTab(true);
      }
      body.session_key = cart.tabSessionKey;
      const response = await action.call<{ tab: POSTabPayload | null }>(
        actionHref(actions.value, "fire_tab", "/api/v1/backstage/pos/tabs/fire/"),
        { body },
      );
      if (response.tab) setFromTabPayload(response.tab);
      await refresh();
    } catch (error) {
      serverError.value = httpErrorMessage(error, "Falha ao enviar à cozinha.");
    } finally {
      firing.value = false;
    }
  }

  async function unfireLineIds(ids: string[]) {
    if (!cart.tabSessionKey || !ids.length) return;
    const response = await action.call<{ tab: POSTabPayload | null }>(
      actionHref(actions.value, "unfire_tab", "/api/v1/backstage/pos/tabs/unfire/"),
      { body: { session_key: cart.tabSessionKey, line_ids: ids } },
    );
    if (response.tab) setFromTabPayload(response.tab);
    await refresh();
  }

  async function unfireTab(lineId: string) {
    if (!cart.tabSessionKey || !lineId) return;
    serverError.value = "";
    firing.value = true;
    try {
      await unfireLineIds([lineId]);
    } catch (error) {
      serverError.value = httpErrorMessage(error, "Falha ao cancelar envio à cozinha.");
    } finally {
      firing.value = false;
    }
  }

  // Multi-select unfire (spec §2.2): resolve the chosen lines' fresh, fired
  // line_ids, then cancel their kitchen handoff in one call.
  async function unfireSelected(selectedSkus: string[]) {
    if (!cart.tabSessionKey || !selectedSkus.length) return;
    serverError.value = "";
    firing.value = true;
    try {
      const ids = await freshLineIdsForSkus(selectedSkus, "fired");
      if (!ids.length) return;
      await unfireLineIds(ids);
    } catch (error) {
      serverError.value = httpErrorMessage(error, "Falha ao cancelar envio à cozinha.");
    } finally {
      firing.value = false;
    }
  }

  async function renameTab(newTabRef: string) {
    if (!cart.tabSessionKey || !newTabRef) return;
    serverError.value = "";
    renamingTab.value = true;
    try {
      const response = await action.call<{ tab: POSTabPayload | null }>(
        actionHref(actions.value, "rename_tab", "/api/v1/backstage/pos/tabs/rename/"),
        { body: { session_key: cart.tabSessionKey, new_tab_ref: newTabRef } },
      );
      if (response.tab) setFromTabPayload(response.tab);
      await refresh();
    } catch (error) {
      serverError.value = httpErrorMessage(error, "Falha ao renomear comanda.");
    } finally {
      renamingTab.value = false;
    }
  }

  function openCancelSaleDialog() {
    cancelSaleError.value = "";
    cancelSaleReason.value = "";
    cancelSaleDialogOpen.value = true;
  }

  async function cancelRecentSale(managerUsername: string, managerPin: string) {
    return cancelarComAprovacao({ username: managerUsername, pin: managerPin });
  }

  /** Mesma exceção auditada, autorizada pelo crachá em vez do PIN. */
  async function cancelRecentSaleWithBadge(badge: string) {
    return cancelarComAprovacao({ badge });
  }

  async function cancelarComAprovacao(aprovacao: Record<string, string>) {
    if (!result.value) return;
    serverError.value = "";
    cancelSaleError.value = "";
    cancellingSale.value = true;
    try {
      const orderRef = result.value.orderRef;
      const reason = cancelSaleReason.value.trim();
      await action.call(
        actionHref(actions.value, "cancel_recent_sale", "/api/v1/backstage/pos/sale/recent/cancel/"),
        {
          body: {
            order_ref: orderRef,
            manager_approval: aprovacao,
            ...(reason ? { reason } : {}),
          },
        },
      );
      result.value = null;
      cancelSaleReason.value = "";
      cancelSaleDialogOpen.value = false;
      // A venda cancelada não deixa polling nem chip para trás.
      if (pendingPixOrderRef.value === orderRef) pendingPixOrderRef.value = "";
      if (pixOrderRef.value === orderRef) {
        stopPixPolling();
        pixStatus.value = "idle";
      }
      // Confirmação como toast padrão de sucesso — o banner fixo de antes nunca
      // expirava e ficava na tela até a próxima venda.
      toast.success("Venda cancelada", {
        description: "O pedido foi cancelado dentro da janela do operador.",
      });
      await refresh();
    } catch (error) {
      // QUALQUER falha fica inline no diálogo (aberto): um toast passageiro com o
      // diálogo fechando lê como sucesso — o operador clicava no link de um pedido
      // que continuava vivo. O PIN é limpo pelo próprio diálogo quando há erro.
      const failure = (httpError(error).data as { error?: { code?: string; message?: string; recovery?: string } } | null)?.error;
      cancelSaleError.value =
        failure?.recovery || failure?.message || httpErrorMessage(error, "Falha ao cancelar venda.");
    } finally {
      cancellingSale.value = false;
    }
  }

  onScopeDispose(() => stopPixPolling());

  return {
    // draft + flags
    cart,
    tabInput,
    busy,
    drawerLock,
    saving,
    pixStatus,
    unsaved,
    firing,
    renamingTab,
    cancellingSale,
    cancelSaleReason,
    cancelSaleDialogOpen,
    cancelSaleError,
    lookupBusy,
    serverError,
    managerApprovalError,
    customerFocusNonce,
    result,
    pendingPixOrderRef,
    checkoutMode,
    showTabs,
    moveDialogOpen,
    movePreparing,
    review,
    reviewFailed,
    customerLookup,
    tabDialogOpen,
    tabDialogReason,
    selectedTenderIndex,
    // derived
    checkoutContract,
    canFireTab,
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
    tabRequiredForSave,
    addressAutocomplete,
    totalDisplay,
    itemCount,
    hasOpenTab,
    inSaleView,
    hasDraftWithoutTab,
    canUseCart,
    paymentTotalQ,
    paymentRemainingQ,
    paymentChangeQ,
    paymentCovered,
    // entrega — o que o servidor respondeu, para a tela PERGUNTAR em vez de pedir
    deliveryFeeQ,
    deliveryFeeSource,
    deliveryDistanceKm,
    deliverySlots,
    deliverySlotsPending,
    deliveryDateEffective,
    scheduleToday,
    scheduleAvailableDates,
    scheduleBottleneckName,
    scheduleReadyAt,
    scheduleFailed,
    scheduleMaxDate,
    refreshSchedule: fetchSchedule,
    selectedTenderMethod,
    splitCount,
    splitPaidCount,
    splitNextShareQ,
    splitNote,
    setSplitCount,
    tabDialogTitle,
    tabDialogDescription,
    sortedTabs,
    otherOpenTabs,
    suggestedSplitRef,
    // commands / handlers
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
    sanitizeTabRef,
    requestTabAssociation,
    openTab,
    openTabFromDialog,
    applySavedAddress,
    lookupCustomer,
    resolveCustomer,
    customerDecision,
    confirmCustomerDecision,
    cancelCustomerDecision,
    customerSearchResults,
    customerSearchBusy,
    customerResolvedNew,
    searchCustomers,
    selectCustomerResult,
    clearCustomer,
    applyCustomerFavorite,
    repeatCustomerLastOrder,
    saveTab,
    prepareCheckout,
    reviewCheckout,
    submitSale,
    dismissResult,
    resendingLink,
    resendPaymentLink,
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
  };
}
