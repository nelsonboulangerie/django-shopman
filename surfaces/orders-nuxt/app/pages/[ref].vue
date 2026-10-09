<script setup lang="ts">
import OrderIFoodNegotiations from "~/components/OrderIFoodNegotiations.vue";
import ActionList from "~/components/ActionList.vue";
import OrderIFoodSummary from "~/components/OrderIFoodSummary.vue";
import OrderNotificationReceipts from "~/components/OrderNotificationReceipts.vue";
// Detalhe do pedido no GESTOR. As seções (resumo, cliente, nota fiscal, itens,
// observação, nota da cozinha, histórico) são do `OperatorOrderDetail` do kit — a
// MESMA tela do detalhe da encomenda no PDV (decisão do dono, 28/09/2026). Aqui
// fica só o que é do Gestor: a barra de ações do fluxo, o iFood, o entregador, o
// editor da nota da cozinha e os diálogos. Lê a projeção no contexto "orders"
// (useOrderDetail); as ações vão pelo proxy do Django e a leitura se refaz.
import {
  appendTag,
  changeBackSuggestionQ,
  confirmationRemainingLabel,
  lucideIcon,
  moneyInput,
  realtimeIndicator,
  splitRef,
  statusTone,
  undoLine,
} from "~/presentation/board";
import { onMounted, onBeforeUnmount } from "vue";
import { ORDERS_HISTORY_TRAIL, ORDERS_QUEUE_TRAIL } from "~/presentation/orderTrails";
import type { CancellationReason } from "~/types/orders";

definePageMeta({ key: (route) => route.path });
const route = useRoute();
const { location: queueLocation } = useOrdersContext();
// Quem abriu o pedido pelo Histórico volta para o Histórico, com o mesmo recorte.
const historyLocation = useState<{
  path: string;
  query: Record<string, string>;
} | null>("orders-history-location", () => null);
const fromHistory = computed(
  () => route.query?.from === "history" && Boolean(historyLocation.value),
);
const backLocation = computed(
  () => (fromHistory.value && historyLocation.value) || queueLocation.value,
);
const orderRef = computed(() => String(route.params.ref || ""));
// A trilha da lista de origem (`OperatorRecordNav`): a fila e o histórico gravam a
// ordem que mostram; o pedido anda dentro da que trouxe a pessoa, e o próximo pedido
// mantém o caminho de volta (`from=history`).
const recordTrailKey = computed(() =>
  fromHistory.value ? ORDERS_HISTORY_TRAIL : ORDERS_QUEUE_TRAIL,
);
function recordLocation(ref_: string) {
  return {
    path: `/${encodeURIComponent(ref_)}`,
    query: fromHistory.value ? { from: "history" } : {},
  };
}

const {
  readMetadata,
  order,
  pending,
  error,
  refresh,
  busy,
  mutationError,
  confirm,
  advance,
  reject,
  cancel,
  fetchCancellationReasons,
  settleCash,
  equipmentBack,
  undoHandoff,
  undoReady,
  requeueFiscal,
  resendPaymentLink,
  saveNotes,
  addComment,
  courierDispatch,
  courierCancel,
  courierQuote,
  managerChallenge,
  authorize,
  dismissManagerChallenge,
} = useOrderDetail(orderRef.value);

// Realtime: SSE push (filtrado a este pedido) + poll de 30s + wake-on-visibility.
// Mantém o painel da corrida (entregador/status) vivo sem F5.
const { realtime } = useOrderEvents(orderRef.value, () => refresh());

// Próximo foco (F4 do laudo do Gestor): o aviso com prazo ("Responder") e o link da
// Fila chegam com `#ifood-negotiations`. Abrir o pedido não basta: a página vai até a
// resposta e o foco de teclado fica na decisão. O bloco só existe depois da leitura,
// por isso a chave nasce quando as negociações chegam. É chegada com destino, não
// primeira pintura: mesmo que o navegador já tenha rolado pelo `#`, o teclado vai para
// a decisão (o `reveal` explícito; a fonte reativa pularia o foco com o bloco à vista).
const IFOOD_NEGOTIATIONS = "ifood-negotiations";
const focusKey = computed(() =>
  route.hash === `#${IFOOD_NEGOTIATIONS}` &&
  order.value?.ifood_negotiations?.length
    ? IFOOD_NEGOTIATIONS
    : null,
);
const { reveal } = useNextFocus();
watch(
  focusKey,
  (key, previous) => {
    if (key && key !== previous) reveal(key);
  },
  { immediate: true, flush: "post" },
);

// O rascunho do comentário mora aqui (o aviso de texto não salvo é da página);
// o campo é do `OperatorOrderDetail`, que só o mostra com a ação `comment`.
const comment = ref("");
async function submitComment(note: string) {
  const ok = await addComment(note);
  if (ok) comment.value = "";
}

const code = computed(() => splitRef(orderRef.value));

// Cadastro do cliente: o CRUD de cliente ainda mora no Admin, e o Gestor aponta
// para lá (o link "Abrir cadastro" é do `OperatorOrderDetail`).
const adminBaseUrl = useRuntimeConfig().public.adminBaseUrl as string;

// kitchen-note editor (seeded from the projection; saved explicitly). The note —
// preset tags one-tap-appended + free text — is shown on the KDS ticket.
const projectedAction = (ref_: string) =>
  order.value?.actions?.find((action) => action.ref === ref_);
// O avanço que a tela mostra como botão. "Marcar pronto" com a Cozinha
// trabalhando vem como ``priority: "menu"``: o pronto chega sozinho quando ela
// conclui, e o gesto à mão mora no menu do pedido (⋯), não na barra.
const advanceAction = computed(() => {
  const action = projectedAction("advance");
  return action && action.priority !== "menu" ? action : undefined;
});
const menuAdvance = computed(() => {
  const action = projectedAction("advance");
  return action && action.priority === "menu" ? action : undefined;
});
const menuOpen = ref(false);
function onMenuAdvance() {
  menuOpen.value = false;
  advance();
}
// "O sistema fez · desfazer": a mesma linha do card.
const nowMs = useNowTick();
const undo = computed(() =>
  order.value ? undoLine(order.value, nowMs.value) : null,
);
function onUndo() {
  if (undo.value?.action === "undo_handoff") undoHandoff();
  else undoReady();
}

const notes = ref("");
const notesBase = ref("");
const notesRevision = ref("");
const notesDirty = computed(() => notes.value !== notesBase.value);
const notesConflict = computed(
  () =>
    notesDirty.value && (order.value?.kitchen_note || "") !== notesBase.value,
);
function acceptLatestNotesBase() {
  notesBase.value = order.value?.kitchen_note || "";
  notesRevision.value = order.value?.revisions?.kitchen_note || "";
}
function useLatestNotes() {
  acceptLatestNotesBase();
  notes.value = notesBase.value;
}
watch(
  order,
  (o) => {
    if (o && !notesDirty.value) {
      notes.value = o.kitchen_note || "";
      notesBase.value = notes.value;
      notesRevision.value = o.revisions?.kitchen_note || "";
    }
  },
  { immediate: true },
);
async function saveKitchenNote() {
  const submitted = notes.value;
  if (await saveNotes(submitted, notesRevision.value)) {
    notesBase.value = submitted;
    if (notes.value === submitted && !error.value) {
      notes.value = order.value?.kitchen_note || "";
      notesBase.value = notes.value;
    }
    if (!error.value)
      notesRevision.value = order.value?.revisions?.kitchen_note || "";
  }
}
const reasonDirty = ref(false);
const negotiationDirty = ref(false);
const hasUnsavedText = computed(
  () =>
    notesDirty.value ||
    Boolean(comment.value.trim()) ||
    reasonDirty.value ||
    negotiationDirty.value,
);
// Session-only drafts: leaving requires an explicit discard while text is dirty.
const confirmDiscard = useConfirm();
onBeforeRouteLeave(() => {
  if (!hasUnsavedText.value) return true;
  return confirmDiscard({
    title: "Sair sem salvar o texto deste pedido?",
    description:
      "O que você digitou neste pedido e ainda não salvou se perde: observação para a cozinha, comentário, motivo ou resposta ao iFood.",
    confirmLabel: "Descartar e sair",
  });
});
function beforeUnload(event: BeforeUnloadEvent) {
  if (!hasUnsavedText.value) return;
  event.preventDefault();
  event.returnValue = "";
}
onMounted(() => window.addEventListener("beforeunload", beforeUnload));
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload));
// Store-configured kitchen-note tags (Admin/Unfold). One tap appends the tag to the
// note, preserving the free text; already-present tags aren't duplicated.
const noteTags = computed(() => order.value?.kitchen_note_tags ?? []);
function applyNoteTag(tag: string) {
  notes.value = appendTag(notes.value, tag);
}

// reject + cancel + settle dialogs. Reject/cancel share OrderReasonDialog, which is
// marketplace-aware: for an iFood order it shows the provider's required coded reasons
// (fetched live per order); other channels get the store presets + free text.
const dialog = ref<"" | "reject" | "cancel" | "settle" | "dispatch">("");
const cashDrafts = useOrderCashDrafts();
const settlementDraft = computed(
  () =>
    cashDrafts.settlements.value[orderRef.value] ?? {
      amount: "",
      changeBack: order.value?.change_back_pending
        ? moneyInput(changeBackSuggestionQ(order.value))
        : "",
      equipmentBack: false,
      revision: String(settleAction.value?.payload_schema.base_revision || ""),
      custody: String(settleAction.value?.confirmation.description || ""),
    },
);
const dispatchDraft = computed(
  () =>
    cashDrafts.dispatches.value[orderRef.value] ?? {
      amount: moneyInput(order.value?.change_out_suggested_q ?? 0),
      equipment: [] as string[],
    },
);
const amount = computed({
  get: () => settlementDraft.value.amount,
  set: (v: string) => {
    settlementDraft.value.amount = v;
  },
});
const settleAction = computed(() =>
  order.value?.actions.find((action) => action.ref === "settle-delivery-cash"),
);
const settleRevision = computed(() => settlementDraft.value.revision);
const settleCustody = computed(() => settlementDraft.value.custody);
const settleChanged = computed(
  () =>
    settleRevision.value !==
    String(settleAction.value?.payload_schema.base_revision || ""),
);
function reviewSettleCustody() {
  settlementDraft.value.revision = String(
    settleAction.value?.payload_schema.base_revision || "",
  );
  settlementDraft.value.custody = String(
    settleAction.value?.confirmation.description || "",
  );
}
// troco da entrega: o que voltou (acerto) e o que o entregador leva (despacho)
const changeBack = computed({
  get: () => settlementDraft.value.changeBack,
  set: (v: string) => {
    settlementDraft.value.changeBack = v;
  },
});
const changeOut = computed({
  get: () => dispatchDraft.value.amount,
  set: (v: string) => {
    dispatchDraft.value.amount = v;
  },
});
const asksChangeBack = computed(() =>
  Boolean(order.value?.change_back_pending),
);
// Pronto + delivery + a loja sugere troco: o despacho pergunta antes de avançar
// (o servidor recusa com 409 se ninguém disser quanto saiu).
const dispatchAsksChange = computed(
  () =>
    order.value?.status === "ready" &&
    (order.value?.change_out_suggested_q ?? 0) > 0,
);
// ...ou o canal deixa levar a maquininha: o despacho oferece.
const dispatchAsks = computed(
  () =>
    dispatchAsksChange.value ||
    (order.value?.status === "ready" &&
      (order.value?.equipment_options.length ?? 0) > 0),
);
const dispatchEquipment = computed({
  get: () => dispatchDraft.value.equipment,
  set: (v: string[]) => {
    dispatchDraft.value.equipment = v;
  },
});
const dispatchEquipmentOptions = computed(() =>
  (order.value?.equipment_options ?? []).map((option) => ({
    value: option.ref,
    label: option.label,
    hint: option.reason || undefined,
    disabled: option.enabled === false,
  })),
);
const settleEquipmentBack = computed({
  get: () => settlementDraft.value.equipmentBack,
  set: (v: boolean) => {
    settlementDraft.value.equipmentBack = v;
  },
});
const asksEquipmentBack = computed(() =>
  Boolean(order.value?.equipment_back_pending),
);
function updateDispatchEquipment(next: string[]) {
  const added = next.find((ref_) => !dispatchEquipment.value.includes(ref_));
  dispatchEquipment.value = added?.startsWith("card_machine:")
    ? [...next.filter((ref_) => !ref_.startsWith("card_machine:")), added]
    : next;
}
const reasons = ref<CancellationReason[]>([]);
const reasonsLoading = ref(false);
const reasonsError = ref("");
let reasonsRequest = 0;
async function loadReasons() {
  const request = ++reasonsRequest;
  reasonsLoading.value = true;
  reasonsError.value = "";
  try {
    const result = await fetchCancellationReasons();
    if (request === reasonsRequest) reasons.value = result;
  } catch {
    if (request === reasonsRequest)
      reasonsError.value =
        "Não foi possível consultar os motivos. Nenhuma ação foi aplicada.";
  } finally {
    if (request === reasonsRequest) reasonsLoading.value = false;
  }
}

// Store-configured justification presets (Admin/Unfold) for non-marketplace channels.
const presets = computed(() => order.value?.cancellation_presets ?? []);

async function openDialog(kind: "reject" | "cancel" | "settle" | "dispatch") {
  if (kind === "settle")
    cashDrafts.settlement(orderRef.value, settlementDraft.value);
  if (kind === "dispatch")
    cashDrafts.dispatch(orderRef.value, dispatchDraft.value);
  dialog.value = kind;
  if (kind === "reject" || kind === "cancel") {
    // Pull the order's valid cancellation reasons — a coded list for iFood, [] else.
    reasons.value = [];
    await loadReasons();
  }
}

// OrderReasonDialog emits the chosen (trimmed) reason + code; we apply the generic
// fallback text and route to the right action, then reconcile.
async function submitReason(payload: {
  reason: string;
  cancellationCode: string;
}) {
  let ok = false;
  if (dialog.value === "reject")
    ok = await reject(
      payload.reason || "Pedido recusado",
      payload.cancellationCode,
    );
  else if (dialog.value === "cancel")
    ok = await cancel(
      payload.reason || "Cancelado pelo operador",
      payload.cancellationCode,
    );
  if (ok) dialog.value = "";
}

// Cancelar pedido PAGO pede segunda assinatura. O diálogo é o MESMO do PDV
// (`OperatorManagerAuth`, no operator-kit): mesma lista, mesmo teclado, mesmo
// crachá. Antes disto o gerente lia "Falha na ação" e não tinha onde assinar.
//
// ⚠️ Fecha o diálogo do MOTIVO também. `submitReason` só fecha `if (ok)`, e o
// desafio devolve `false` de propósito — o motivo precisa sobreviver por baixo
// da assinatura. Só que, com o cancelamento já feito, ninguém o fechava: o
// gerente assinava, o pedido cancelava, e a tela voltava a mostrar "Cancelar
// pedido" com o Confirmar aceso sobre um pedido JÁ cancelado. Achado na prova
// de navegador — nenhum teste de componente ou de composable alcança este
// estado, porque `dialog` é estado da PÁGINA.
async function signWithPin(username: string, pin: string) {
  if (await authorize({ username, pin })) dialog.value = "";
}
async function signWithBadge(badge: string) {
  if (await authorize({ badge })) dialog.value = "";
}

async function submitSettle() {
  const back = asksChangeBack.value
    ? changeBack.value.trim() || "0"
    : undefined;
  const ok = await settleCash(
    amount.value.trim(),
    back,
    asksEquipmentBack.value && settleEquipmentBack.value,
    settleRevision.value,
  );
  if (ok) {
    cashDrafts.clear("settlement", orderRef.value);
    dialog.value = "";
  }
}

function onAdvance() {
  if (dispatchAsks.value) openDialog("dispatch");
  else advance();
}

async function submitDispatch(value: string | null) {
  const changeOut = dispatchAsksChange.value
    ? (value ?? "").trim() || "0"
    : undefined;
  const ok = await advance(changeOut, dispatchEquipment.value);
  if (ok) {
    cashDrafts.clear("dispatch", orderRef.value);
    dialog.value = "";
  }
}

// Estação travada pelo servidor: não é "pedido não encontrado".
const { denied: stationLocked } = useStationLock();

// ── O cabeçalho de uma linha e o gesto do momento (G14/G15) ─────────────────
// A régua da suíte (`useScreen` do kit): mesa no servidor e na hidratação, a largura
// real depois. Com `useMediaQuery` cru o celular hidratava outra árvore na carga direta.
const { belowMd: isPhone } = useScreen();
function menuDo(fn: () => unknown) {
  menuOpen.value = false;
  void fn();
}
const detailMenuItems = computed(() => [
  {
    label: "Atualizar",
    icon: "i-lucide-refresh-cw",
    loading: pending.value,
    "data-action": "refresh",
    onSelect: () => refresh(),
  },
  ...(menuAdvance.value
    ? [
        {
          label: menuAdvance.value.label,
          description:
            "O pronto vem sozinho quando a Cozinha conclui. Use para a estação sem tela.",
          icon: "i-lucide-check",
          "data-action": "advance",
          disabled: busy.value || !menuAdvance.value.enabled,
          title: menuAdvance.value.reason || undefined,
          onSelect: onMenuAdvance,
        },
      ]
    : []),
  ...(order.value?.can_settle_delivery_cash && primary.value?.key !== "settle"
    ? [
        {
          label:
            order.value.fulfillment_type === "pickup"
              ? "Receber na retirada"
              : "Acertar entrega",
          icon: "i-lucide-banknote",
          "data-action": "settle",
          disabled: busy.value || !settleAction.value?.enabled,
          title: settleAction.value?.reason || undefined,
          onSelect: () => menuDo(() => openDialog("settle")),
        },
      ]
    : []),
  ...(order.value?.equipment_back_pending
    ? [
        {
          label: "Maquininha voltou",
          icon: "i-lucide-smartphone-nfc",
          "data-action": "equipment-back",
          disabled: busy.value || !projectedAction("equipment-back")?.enabled,
          title: projectedAction("equipment-back")?.reason || undefined,
          onSelect: () => menuDo(equipmentBack),
        },
      ]
    : []),
  ...(order.value?.fiscal_status === "failed"
    ? [
        {
          label: "Reprocessar NFC-e",
          icon: "i-lucide-file-text",
          "data-action": "requeue-fiscal",
          disabled: busy.value || !projectedAction("requeue-fiscal")?.enabled,
          title: projectedAction("requeue-fiscal")?.reason || undefined,
          onSelect: () => menuDo(requeueFiscal),
        },
      ]
    : []),
  ...(order.value?.can_resend_payment_link
    ? [
        {
          label: "Reenviar link de pagamento",
          icon: "i-lucide-send",
          "data-action": "resend-payment-link",
          disabled: busy.value,
          onSelect: () => menuDo(resendPaymentLink),
        },
      ]
    : []),
  ...(order.value?.can_cancel
    ? [
        {
          label: order.value.cancel_requires_approval
            ? "Cancelar pedido (pede gerente)"
            : "Cancelar pedido",
          icon: "i-lucide-ban",
          "data-action": "cancel",
          color: "error" as const,
          disabled: busy.value,
          onSelect: () => menuDo(() => openDialog("cancel")),
        },
      ]
    : []),
]);
const rejectAction = computed(() => projectedAction("reject"));
/** A ação primária do pedido agora: aceitar, o próximo passo do fluxo ou o acerto. O
 *  servidor decide se vale; travada, ela continua no lugar dizendo por quê. */
const primary = computed(() => {
  const o = order.value;
  if (!o) return null;
  const confirmAction = projectedAction("confirm");
  if (confirmAction)
    return {
      key: "confirm" as const,
      label: "Aceitar",
      icon: "lucide:check",
      enabled: confirmAction.enabled,
      reason: confirmAction.reason,
    };
  const advance = advanceAction.value;
  if (advance) {
    return advance.enabled
      ? {
          key: "advance" as const,
          label: o.next_action_label || advance.label,
          icon: "lucide:arrow-right",
          enabled: true,
          reason: "",
        }
      : {
          key: "advance" as const,
          label: (o.advance_block_label || advance.label).replace(/…$/, ""),
          icon: "lucide:lock",
          enabled: false,
          reason: advance.reason,
        };
  }
  if (o.can_settle_delivery_cash) {
    return {
      key: "settle" as const,
      label:
        o.fulfillment_type === "pickup"
          ? "Receber na retirada"
          : "Acertar entrega",
      icon: "lucide:banknote",
      enabled: Boolean(settleAction.value?.enabled),
      reason: settleAction.value?.reason || "",
    };
  }
  return null;
});
function runPrimary() {
  const p = primary.value;
  if (!p?.enabled || busy.value) return;
  if (p.key === "confirm") confirm();
  else if (p.key === "advance") onAdvance();
  else openDialog("settle");
}
// O ao vivo do cabeçalho: a hora da última leitura útil e o estado do empurrão (SSE).
const liveTone = computed(() =>
  error.value
    ? "off"
    : realtime.value === "live"
      ? "live"
      : realtime.value === "connecting"
        ? "late"
        : "calm",
);
const liveLabel = computed(() => realtimeIndicator(realtime.value).label);
const liveDetail = computed(() => realtimeIndicator(realtime.value).title);
// A hora sai do relógio do navegador (fuso de quem opera), nunca do servidor no SSR.
const clockReady = ref(false);
onMounted(() => {
  clockReady.value = true;
});
const readClock = computed(() => {
  const at = clockReady.value ? readMetadata?.value?.generated_at : "";
  return at
    ? new Date(at).toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
});
const channelIcon = computed(
  () => `lucide:${lucideIcon(order.value?.channel_icon || "")}`,
);
const statusColor = (status: string) => {
  const tone = statusTone(status);
  return tone === "danger" ? "error" : tone;
};
// "Confirma sozinho em 4:32 se ninguém recusar." — o prazo do pedido novo, no relógio.
const deadlineText = computed(() => {
  const o = order.value;
  if (!o?.confirmation_deadline_iso) return null;
  const left = confirmationRemainingLabel(
    o.confirmation_deadline_iso,
    nowMs.value,
  );
  if (!left || left === "0:00") return null;
  return o.confirmation_action === "cancel"
    ? { before: "Cancela sozinho em", left, after: "se ninguém aceitar." }
    : { before: "Confirma sozinho em", left, after: "se ninguém recusar." };
});
// Bilhete de volta: quem veio de outro app (`?back=<url>&back_label=<texto>`) volta para
// onde estava. Só endereço http(s); sem os dois parâmetros, nada aparece.
const returnTicket = computed(() => {
  const query = route.query ?? {};
  const href = typeof query.back === "string" ? query.back : "";
  const label =
    typeof query.back_label === "string" ? query.back_label.trim() : "";
  return href && label && /^https?:\/\//.test(href) ? { href, label } : null;
});
// Fora da loja (G18): com o consentimento, a posição do dispositivo decide o resumo.
const outside = useOutsideStore(
  () => order.value?.store_location ?? null,
  isPhone,
);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <!-- Cabeçalho de UMA linha (G14, prévia v3 `depois-gestor-detalhe`):
         ‹ Pedidos | Pedido S84 · estado · ao vivo | bilhete de volta | ⋯ | a ação primária.
         No celular (v3 `depois-gestor-celular` (c)): ← U68 · iFood · ⋯, e o gesto desce
         para o polegar. -->
    <OperatorPageHeader
      :title="clockReady && isPhone ? code.code : `Pedido ${code.code}`"
    >
      <template #lead>
        <NuxtButton
          :to="backLocation"
          :icon="isPhone ? 'i-lucide-arrow-left' : 'i-lucide-chevron-left'"
          color="neutral"
          variant="ghost"
          square
          :aria-label="
            fromHistory ? 'Voltar para o histórico' : 'Voltar para a fila'
          "
          data-detail-back
        />
      </template>
      <template #status>
        <!-- Celular e desktop pelo CSS (não pela largura lida no JS): o servidor desenha
             o mesmo que o navegador vai mostrar. -->
        <span
          v-if="order"
          class="inline-flex min-w-0 items-center gap-1 op-micro text-muted-foreground md:hidden"
          data-detail-channel
        >
          <Icon :name="channelIcon" class="size-4 shrink-0" />{{
            order.channel_name || order.channel_ref
          }}
        </span>
        <NuxtBadge
          v-if="order?.status_label"
          :color="statusColor(order.status)"
          :label="order.status_label"
          data-detail-status
        />
        <span class="hidden md:inline-flex">
          <OperatorLiveStatus
            :tone="liveTone"
            :time="readClock"
            :label="error ? 'Atualização falhou' : liveLabel"
            :detail="liveDetail"
          />
        </span>
        <!-- Anterior e próximo DENTRO da lista de onde a pessoa veio (fase 2, K5):
             a fila ou o histórico, com o recorte. Quem chegou por outro app (bilhete de
             volta) não veio de lista nenhuma: sem par. -->
        <OperatorRecordNav
          v-if="!returnTicket"
          class="ms-auto"
          :trail="recordTrailKey"
          :current="orderRef"
          :to="recordLocation"
          previous-label="Pedido anterior"
          next-label="Próximo pedido"
        />
      </template>
      <template v-if="isPhone" #phone-actions>
        <NuxtButton
          type="button"
          icon="i-lucide-ellipsis"
          color="neutral"
          variant="ghost"
          square
          aria-label="Mais ações do pedido"
          :aria-expanded="menuOpen"
          data-action="menu-phone"
          @click="menuOpen = !menuOpen"
        />
      </template>
      <template v-if="!isPhone" #actions>
        <!-- bilhete de volta: quem veio de outro app volta para onde estava -->
        <NuxtButton
          v-if="returnTicket"
          :to="returnTicket.href"
          icon="i-lucide-corner-up-left"
          :label="returnTicket.label"
          color="error"
          data-detail-return
        />
        <NuxtButton
          icon="i-lucide-ellipsis"
          label="Mais ações do pedido"
          color="neutral"
          variant="outline"
          aria-haspopup="dialog"
          :aria-expanded="menuOpen"
          data-action="menu"
          @click="menuOpen = !menuOpen"
        />
        <NuxtButton
          v-if="rejectAction"
          type="button"
          label="Recusar"
          color="error"
          variant="outline"
          :disabled="busy || !rejectAction.enabled"
          data-action="reject"
          @click="openDialog('reject')"
        />
        <NuxtButton
          v-if="primary"
          type="button"
          :icon="primary.icon.replace('lucide:', 'i-lucide-')"
          :label="primary.label"
          :disabled="busy || !primary.enabled"
          :title="primary.reason || undefined"
          :data-action="
            primary.key === 'advance' && !primary.enabled
              ? 'advance-blocked'
              : primary.key
          "
          @click="runPrimary"
        />
      </template>
    </OperatorPageHeader>

    <!-- ⋯ do pedido: atualizar e os gestos que não são o do momento -->
    <NuxtDrawer
      :open="menuOpen"
      :direction="isPhone ? 'bottom' : 'right'"
      title="Ações do pedido"
      description="Atualização e ações auxiliares deste pedido."
      data-detail-menu
      @update:open="(value) => (menuOpen = value)"
    >
      <template #body>
        <ReadFreshness :metadata="readMetadata" :failed="Boolean(error)" />
        <ActionList :items="detailMenuItems" aria-label="Ações do pedido" />
        <NuxtAlert
          v-if="!order?.can_cancel && order?.cancel_block_label"
          color="info"
          variant="subtle"
          :title="order.cancel_block_label"
          data-cancel-block
        />
      </template>
    </NuxtDrawer>

    <div
      class="flex min-h-0 w-full flex-1 flex-col gap-4 overflow-auto p-4 *:shrink-0 sm:p-6"
    >
      <!-- fora da loja: o detalhe mostra só o que pede decisão (G18) -->
      <NuxtAlert
        v-if="outside.askConsent.value"
        color="info"
        variant="subtle"
        icon="i-lucide-map-pin"
        title="Usar a localização deste dispositivo?"
        description="Fora da loja, o Gestor pode mostrar somente o que pede decisão."
        :actions="[
          {
            label: 'Permitir',
            color: 'info',
            variant: 'outline',
            onClick: () => outside.allow(),
          },
          {
            label: 'Agora não',
            color: 'info',
            variant: 'outline',
            onClick: () => outside.decline(),
          },
        ]"
        data-outside-consent
      />
      <NuxtAlert
        v-if="outside.away.value"
        color="info"
        variant="subtle"
        icon="i-lucide-map-pin-off"
        title="Você está fora da loja"
        description="Mostrando somente o que pede decisão."
        :actions="[
          {
            label: 'Ver tudo',
            color: 'info',
            variant: 'outline',
            onClick: () => outside.showAll(),
          },
        ]"
        data-outside-band
      />

      <div
        v-if="pending && !order"
        class="grid gap-3"
        aria-label="Carregando pedido"
      >
        <NuxtSkeleton class="h-24 w-full" />
        <NuxtSkeleton class="h-64 w-full" />
      </div>
      <!-- `!stationLocked`: com a estação travada a leitura volta 403 e este aviso
         dizia "Pedido não encontrado", que é falso e assusta. Nesse estado quem
         fala é a identificação, que sobe por cima. -->
      <NuxtAlert
        v-else-if="(error || !order) && !stationLocked"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Não foi possível carregar o pedido"
        :description="
          order
            ? 'Mantivemos a última leitura e seu rascunho; atualize antes de confirmar ações.'
            : 'Pedido não encontrado ou falha ao carregar.'
        "
        data-order-error
      />

      <OperatorOrderDetail
        v-if="order"
        v-model:comment="comment"
        :order="order"
        :busy="busy"
        :admin-base-url="adminBaseUrl"
        :show-status="false"
        :decision-only="outside.away.value"
        layout="split"
        @comment="submitComment"
      >
        <!-- iFood: o resumo do pagamento/operação; as negociações abertas vêm num
             card próprio logo abaixo do pedido (#after-summary). -->
        <template #summary>
          <OrderIFoodSummary
            :cancellation-notice="order.ifood_cancellation_notice"
            :payment-summary="order.ifood_payment_summary"
            :operation-summary="order.ifood_operation_summary"
          />
        </template>
        <template #after-summary>
          <OrderIFoodNegotiations
            v-if="order.ifood_negotiations?.length"
            :order-ref="order.ref"
            :negotiations="order.ifood_negotiations"
            @refresh="refresh"
            @dirty-change="negotiationDirty = $event"
          />
        </template>

        <!-- O estado do momento, escrito: no celular as pílulas e o prazo (v3 (c)); em todo
           tamanho, o "o sistema fez · desfazer" e o bloqueio do avanço com o motivo. -->
        <template #actions>
          <section
            v-if="
              (isPhone && order.payment_method_label) ||
              deadlineText ||
              undo ||
              (advanceAction &&
                !advanceAction.enabled &&
                order.advance_block_reason)
            "
            class="flex flex-col gap-2.5"
            data-detail-state
          >
            <div
              v-if="isPhone && order.payment_method_label"
              class="flex flex-wrap items-center gap-2"
              data-detail-pills
            >
              <!-- o estado já está no cabeçalho, em toda largura; aqui só o fato -->
              <NuxtBadge
                v-if="order.payment_method_label"
                color="neutral"
                :label="
                  order.payment_status_label
                    ? `${order.payment_method_label} · ${order.payment_status_label}`
                    : order.payment_method_label
                "
              />
            </div>
            <NuxtAlert
              v-if="deadlineText"
              color="warning"
              variant="subtle"
              icon="i-lucide-timer"
              :description="`${deadlineText.before} ${deadlineText.left} ${deadlineText.after}`"
              data-detail-deadline
            />
            <NuxtAlert
              v-if="undo"
              color="success"
              variant="subtle"
              :icon="
                undo.kind === 'handoff' ? 'i-lucide-check' : 'i-lucide-sparkles'
              "
              :title="undo.label"
              :description="
                [undo.detail, undo.alreadyOut].filter(Boolean).join(' · ')
              "
              :actions="
                undo.canUndo
                  ? [
                      {
                        label:
                          undo.kind === 'handoff'
                            ? `Desfazer ${undo.countdown}`
                            : 'Desfazer',
                        color: 'success',
                        variant: 'outline',
                        disabled: busy,
                        onClick: () => onUndo(),
                      },
                    ]
                  : []
              "
              :data-undo="undo.kind"
            />
            <NuxtAlert
              v-if="
                advanceAction &&
                !advanceAction.enabled &&
                order.advance_block_reason
              "
              color="error"
              variant="subtle"
              icon="i-lucide-lock"
              :title="
                order.advance_block_label.replace(/…$/, '') || 'Bloqueado'
              "
              :description="order.advance_block_reason"
              data-detail-block
            />
          </section>
        </template>

        <template v-if="!outside.away.value" #after-profile>
          <!-- corrida de entrega (logística externa) -->
          <OrderCourierPanel
            v-if="order.courier"
            :courier="order.courier"
            :cancel-action="
              order.actions.find((action) => action.ref === 'courier-cancel')
            "
            :quote-action="
              order.actions.find((action) => action.ref === 'courier-quote')
            "
            :dispatch-action="
              order.actions.find((action) => action.ref === 'courier-dispatch')
            "
            :busy="busy"
            @quote="courierQuote"
            @dispatch="courierDispatch"
            @cancel="courierCancel"
          />
          <!-- comprovante de entrega dos avisos ao cliente (D3) -->
          <OrderNotificationReceipts :receipts="order.notification_receipts" />
        </template>

        <!-- A nota da cozinha se EDITA no Gestor: o editor entra no lugar da leitura. -->
        <template v-if="!outside.away.value" #kitchen-note>
          <NuxtCard as="section">
            <div class="flex flex-col gap-2">
              <!-- one-tap tags (configuráveis no Admin) — anexam ao texto, sem duplicar -->
              <div v-if="noteTags.length" class="flex flex-wrap gap-1.5">
                <NuxtButton
                  v-for="(tag, i) in noteTags"
                  :key="i"
                  type="button"
                  icon="i-lucide-plus"
                  :label="tag"
                  color="neutral"
                  variant="outline"
                  @click="applyNoteTag(tag)"
                />
              </div>
              <NuxtFormField
                label="Nota para a cozinha"
                description="Aparece no ticket da cozinha (KDS)."
              >
                <NuxtTextarea
                  id="order-notes"
                  v-model="notes"
                  class="w-full"
                  :rows="3"
                  placeholder="Escreva uma nota…"
                />
              </NuxtFormField>
              <NuxtAlert
                v-if="notesConflict"
                color="warning"
                variant="subtle"
                title="A nota mudou enquanto você escrevia"
                :description="`Seu texto foi preservado. No servidor: ${order.kitchen_note || '(vazia)'}`"
                :actions="[
                  {
                    label: 'Manter meu texto',
                    color: 'warning',
                    variant: 'outline',
                    onClick: () => acceptLatestNotesBase(),
                  },
                  {
                    label: 'Usar texto do servidor',
                    color: 'warning',
                    variant: 'outline',
                    onClick: () => useLatestNotes(),
                  },
                ]"
              />
              <NuxtAlert
                v-if="mutationError"
                color="error"
                variant="subtle"
                icon="i-lucide-triangle-alert"
                :description="mutationError"
              />
              <NuxtButton
                v-if="notesDirty || notesConflict"
                type="button"
                label="Salvar nota"
                :disabled="busy || !notesDirty || notesConflict"
                @click="saveKitchenNote"
              />
            </div>
          </NuxtCard>
        </template>
      </OperatorOrderDetail>
    </div>

    <!-- No celular, a ação pertence ao chrome do painel. Como irmã do scroller ela
         permanece visível sem cobrir a barra de seções da suíte. -->
    <OperatorToolbar
      v-if="isPhone && order && (primary || rejectAction)"
      as="footer"
      data-detail-thumb
    >
      <div class="flex w-full items-center gap-2">
        <NuxtButton
          v-if="rejectAction"
          type="button"
          label="Recusar"
          color="error"
          variant="outline"
          :disabled="busy || !rejectAction.enabled"
          data-action="reject"
          @click="openDialog('reject')"
        />
        <div v-if="primary" class="min-w-0 flex-1">
          <NuxtButton
            block
            type="button"
            :icon="primary.icon.replace('lucide:', 'i-lucide-')"
            :label="primary.label"
            :disabled="busy || !primary.enabled"
            :data-action="primary.key"
            @click="runPrimary"
          />
        </div>
      </div>
    </OperatorToolbar>

    <!-- reject / cancel: marketplace-aware reason dialog (iFood coded reasons or
         store presets + free text) -->
    <OrderReasonDialog
      :open="dialog === 'reject' || dialog === 'cancel'"
      :mode="dialog === 'cancel' ? 'cancel' : 'reject'"
      :loading="reasonsLoading"
      :error="reasonsError"
      :marketplace="order?.channel_ref === 'ifood'"
      :reasons="reasons"
      :presets="presets"
      :busy="busy"
      @dirty-change="reasonDirty = $event"
      @retry="loadReasons"
      @update:open="
        (v) => {
          if (!v) dialog = '';
        }
      "
      @confirm="submitReason"
    />

    <!-- settle delivery cash dialog -->
    <NuxtModal
      :open="dialog === 'settle'"
      :title="
        order?.fulfillment_type === 'pickup'
          ? 'Pagamento na retirada'
          : 'Acerto da entrega'
      "
      :description="
        order?.fulfillment_type === 'pickup'
          ? 'Confirme o recebimento antes de concluir e entregar o pedido ao cliente.'
          : 'Confirme após conferir o dinheiro e os comprovantes da maquininha.'
      "
      @update:open="
        (v) => {
          if (!v) dialog = '';
        }
      "
    >
      <template #body>
        <div class="grid gap-4">
          <p class="text-sm text-muted-foreground">{{ settleCustody }}</p>
          <NuxtAlert
            v-if="settleChanged"
            color="warning"
            variant="subtle"
            title="O pedido ou turno mudou"
            :description="`Confira o contexto atual: ${settleAction?.confirmation.description || ''}`"
            :actions="[
              {
                label: 'Conferir e manter os valores digitados',
                color: 'warning',
                variant: 'outline',
                onClick: () => reviewSettleCustody(),
              },
            ]"
          />
          <NuxtFormField label="Valor recebido">
            <NuxtInput
              v-model="amount"
              class="w-full"
              type="text"
              inputmode="decimal"
              placeholder="Ex.: 15,00"
            />
          </NuxtFormField>
          <NuxtFormField
            v-if="asksChangeBack"
            :label="`${order?.change_label}. Quanto voltou?`"
            data-change-back
          >
            <NuxtInput
              v-model="changeBack"
              class="w-full"
              type="text"
              inputmode="decimal"
              placeholder="0,00"
              aria-label="Troco que voltou"
            />
          </NuxtFormField>
          <NuxtCheckbox
            v-if="asksEquipmentBack"
            v-model="settleEquipmentBack"
            :label="`${order?.equipment_label}. Voltou junto`"
            data-equipment-back
          />
        </div>
      </template>
      <template #footer>
        <NuxtButton
          label="Voltar"
          color="neutral"
          variant="outline"
          @click="dialog = ''"
        />
        <NuxtButton
          label="Confirmar"
          color="primary"
          :disabled="busy || settleChanged || !settleAction?.enabled"
          :loading="busy"
          @click="submitSettle"
        />
      </template>
    </NuxtModal>

    <!-- dispatch dialog: how much change leaves the drawer with the courier -->
    <NuxtModal
      :open="dialog === 'dispatch'"
      :title="
        dispatchAsksChange ? 'Troco para o entregador' : 'Saída para entrega'
      "
      :description="
        dispatchAsksChange
          ? `${order?.change_label}. O valor sai do seu turno de caixa e volta no acerto.`
          : 'O que sai com o entregador.'
      "
      data-dispatch-dialog
      @update:open="
        (v) => {
          if (!v) dialog = '';
        }
      "
    >
      <template #body>
        <div class="grid gap-4">
          <NuxtCheckboxGroup
            v-if="dispatchEquipmentOptions.length"
            :model-value="dispatchEquipment"
            :items="dispatchEquipmentOptions"
            variant="table"
            data-dispatch-equipment
            @update:model-value="updateDispatchEquipment"
          />
          <NuxtFormField
            v-if="dispatchAsksChange"
            label="Troco que o entregador leva"
          >
            <NuxtInput
              v-model="changeOut"
              class="w-full"
              type="text"
              inputmode="decimal"
              placeholder="Ex.: 20,00"
              aria-label="Troco que o entregador leva"
            />
          </NuxtFormField>
        </div>
      </template>
      <template #footer>
        <NuxtButton
          label="Voltar"
          color="neutral"
          variant="outline"
          @click="dialog = ''"
        />
        <NuxtButton
          v-if="dispatchAsksChange"
          label="Saiu sem troco"
          color="neutral"
          variant="outline"
          :disabled="busy"
          @click="submitDispatch('0')"
        />
        <NuxtButton
          :label="dispatchAsksChange ? 'Levou o troco' : 'Saiu para entrega'"
          color="primary"
          :disabled="busy"
          :loading="busy"
          @click="submitDispatch(changeOut)"
        />
      </template>
    </NuxtModal>

    <!-- Segunda assinatura: o mesmo diálogo canônico do PDV, com a MESMA lista de
         gerentes (``managers`` da projeção de detalhe, montada por
         ``pos._manager_cards``). Selecionar, não digitar: nome digitado erra, e o
         servidor resolve a assinatura por username. Lista vazia ainda cai no
         campo livre — é a porta de saída, não o caminho normal. -->
    <OperatorManagerAuth
      :open="!!managerChallenge"
      action="cancel_sale"
      :managers="order?.managers || []"
      :busy="busy"
      :error="
        managerChallenge?.code === 'manager_approval_invalid'
          ? managerChallenge.message
          : ''
      "
      @update:open="
        (aberto: boolean) => {
          if (!aberto) dismissManagerChallenge();
        }
      "
      @authorize="signWithPin"
      @authorize-badge="signWithBadge"
    />
  </main>
</template>
