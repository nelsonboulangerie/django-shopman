<script setup lang="ts">
import OrderIFoodNegotiations from "~/components/OrderIFoodNegotiations.vue";
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
  moneyInput,
  splitRef,
  undoLine,
} from "~/presentation/board";
import { onMounted, onBeforeUnmount } from "vue";
import type { CancellationReason } from "~/types/orders";

definePageMeta({ key: (route) => route.path });
const route = useRoute();
const { location: queueLocation } = useOrdersContext();
const orderRef = computed(() => String(route.params.ref || ""));

const { readMetadata, order, pending, error, refresh, busy, mutationError, confirm, advance, reject, cancel, fetchCancellationReasons, settleCash, equipmentBack, undoHandoff, undoReady, requeueFiscal, resendPaymentLink, saveNotes, addComment, courierDispatch, courierCancel, courierQuote, managerChallenge, authorize, dismissManagerChallenge } =
  useOrderDetail(orderRef.value);

// Realtime: SSE push (filtrado a este pedido) + poll de 30s + wake-on-visibility.
// Mantém o painel da corrida (entregador/status) vivo sem F5.
useOrderEvents(orderRef.value, () => refresh());

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
const projectedAction = (ref_: string) => order.value?.actions?.find((action) => action.ref === ref_);
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
const undo = computed(() => order.value ? undoLine(order.value, nowMs.value) : null);
function onUndo() {
  if (undo.value?.action === "undo_handoff") undoHandoff();
  else undoReady();
}

const notes = ref("");
const notesBase = ref("");
const notesRevision = ref("");
const notesDirty = computed(() => notes.value !== notesBase.value);
const notesConflict = computed(() => notesDirty.value && (order.value?.kitchen_note || "") !== notesBase.value);
function acceptLatestNotesBase() {
  notesBase.value = order.value?.kitchen_note || "";
  notesRevision.value = order.value?.revisions?.kitchen_note || "";
}
function useLatestNotes() {
  acceptLatestNotesBase();
  notes.value = notesBase.value;
}
watch(order, (o) => {
  if (o && !notesDirty.value) {
    notes.value = o.kitchen_note || "";
    notesBase.value = notes.value;
    notesRevision.value = o.revisions?.kitchen_note || "";
  }
}, { immediate: true });
async function saveKitchenNote() {
  const submitted = notes.value;
  if (await saveNotes(submitted, notesRevision.value)) {
    notesBase.value = submitted;
    if (notes.value === submitted && !error.value) {
      notes.value = order.value?.kitchen_note || "";
      notesBase.value = notes.value;
    }
    if (!error.value) notesRevision.value = order.value?.revisions?.kitchen_note || "";
  }
}
const reasonDirty = ref(false);
const negotiationDirty = ref(false);
const hasUnsavedText = computed(() => notesDirty.value || Boolean(comment.value.trim()) || reasonDirty.value || negotiationDirty.value);
// Session-only drafts: leaving requires an explicit discard while text is dirty.
const confirmDiscard = useConfirm();
onBeforeRouteLeave(() => {
  if (!hasUnsavedText.value) return true;
  return confirmDiscard({
    title: "Sair sem salvar o texto deste pedido?",
    description: "O que você digitou neste pedido e ainda não salvou se perde: observação para a cozinha, comentário, motivo ou resposta ao iFood.",
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
const settlementDraft = computed(() => cashDrafts.settlements.value[orderRef.value] ?? ({
  amount: "", changeBack: order.value?.change_back_pending ? moneyInput(changeBackSuggestionQ(order.value)) : "", equipmentBack: false,
  revision: String(settleAction.value?.payload_schema.base_revision || ""), custody: String(settleAction.value?.confirmation.description || ""),
}));
const dispatchDraft = computed(() => cashDrafts.dispatches.value[orderRef.value] ?? ({ amount: moneyInput(order.value?.change_out_suggested_q ?? 0), equipment: [] as string[] }));
const amount = computed({ get: () => settlementDraft.value.amount, set: (v: string) => { settlementDraft.value.amount = v; } });
const settleAction = computed(() => order.value?.actions.find((action) => action.ref === "settle-delivery-cash"));
const settleRevision = computed(() => settlementDraft.value.revision);
const settleCustody = computed(() => settlementDraft.value.custody);
const settleChanged = computed(() => settleRevision.value !== String(settleAction.value?.payload_schema.base_revision || ""));
function reviewSettleCustody() {
  settlementDraft.value.revision = String(settleAction.value?.payload_schema.base_revision || "");
  settlementDraft.value.custody = String(settleAction.value?.confirmation.description || "");
}
// troco da entrega: o que voltou (acerto) e o que o entregador leva (despacho)
const changeBack = computed({ get: () => settlementDraft.value.changeBack, set: (v: string) => { settlementDraft.value.changeBack = v; } });
const changeOut = computed({ get: () => dispatchDraft.value.amount, set: (v: string) => { dispatchDraft.value.amount = v; } });
const asksChangeBack = computed(() => Boolean(order.value?.change_back_pending));
// Pronto + delivery + a loja sugere troco: o despacho pergunta antes de avançar
// (o servidor recusa com 409 se ninguém disser quanto saiu).
const dispatchAsksChange = computed(
  () => order.value?.status === "ready" && (order.value?.change_out_suggested_q ?? 0) > 0,
);
// ...ou o canal deixa levar a maquininha: o despacho oferece.
const dispatchAsks = computed(
  () => dispatchAsksChange.value || (order.value?.status === "ready" && (order.value?.equipment_options.length ?? 0) > 0),
);
const dispatchEquipment = computed({ get: () => dispatchDraft.value.equipment, set: (v: string[]) => { dispatchDraft.value.equipment = v; } });
const settleEquipmentBack = computed({ get: () => settlementDraft.value.equipmentBack, set: (v: boolean) => { settlementDraft.value.equipmentBack = v; } });
const asksEquipmentBack = computed(() => Boolean(order.value?.equipment_back_pending));
function toggleDispatchEquipment(ref_: string) {
  dispatchEquipment.value = dispatchEquipment.value.includes(ref_)
    ? dispatchEquipment.value.filter((r) => r !== ref_)
    : [...dispatchEquipment.value.filter(r => !ref_.startsWith("card_machine:") || !r.startsWith("card_machine:")), ref_];
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
    if (request === reasonsRequest) reasonsError.value = "Não foi possível consultar os motivos. Nenhuma ação foi aplicada.";
  } finally {
    if (request === reasonsRequest) reasonsLoading.value = false;
  }
}

// Store-configured justification presets (Admin/Unfold) for non-marketplace channels.
const presets = computed(() => order.value?.cancellation_presets ?? []);

async function openDialog(kind: "reject" | "cancel" | "settle" | "dispatch") {
  if (kind === "settle") cashDrafts.settlement(orderRef.value, settlementDraft.value);
  if (kind === "dispatch") cashDrafts.dispatch(orderRef.value, dispatchDraft.value);
  dialog.value = kind;
  if (kind === "reject" || kind === "cancel") {
    // Pull the order's valid cancellation reasons — a coded list for iFood, [] else.
    reasons.value = [];
    await loadReasons();
  }
}

// OrderReasonDialog emits the chosen (trimmed) reason + code; we apply the generic
// fallback text and route to the right action, then reconcile.
async function submitReason(payload: { reason: string; cancellationCode: string }) {
  let ok = false;
  if (dialog.value === "reject") ok = await reject(payload.reason || "Pedido recusado", payload.cancellationCode);
  else if (dialog.value === "cancel") ok = await cancel(payload.reason || "Cancelado pelo operador", payload.cancellationCode);
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
  const back = asksChangeBack.value ? changeBack.value.trim() || "0" : undefined;
  const ok = await settleCash(amount.value.trim(), back, asksEquipmentBack.value && settleEquipmentBack.value, settleRevision.value);
  if (ok) { cashDrafts.clear("settlement", orderRef.value); dialog.value = ""; }
}

function onAdvance() {
  if (dispatchAsks.value) openDialog("dispatch");
  else advance();
}

async function submitDispatch(value: string | null) {
  const changeOut = dispatchAsksChange.value ? (value ?? "").trim() || "0" : undefined;
  const ok = await advance(changeOut, dispatchEquipment.value);
  if (ok) { cashDrafts.clear("dispatch", orderRef.value); dialog.value = ""; }
}

// Estação travada pelo servidor: não é "pedido não encontrado".
const { denied: stationLocked } = useStationLock();
</script>

<template>
  <main class="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-4 p-4 md:p-6">
    <!-- header -->
    <header class="flex items-center gap-3">
      <NuxtLink :to="queueLocation" class="grid min-h-control min-w-control shrink-0 place-items-center rounded-md border bg-card text-foreground transition hover:bg-accent" aria-label="Voltar para a fila">
        <Icon name="lucide:arrow-left" class="size-4" />
      </NuxtLink>
      <div class="min-w-0">
        <p class="text-xs text-muted-foreground">{{ code.prefix }}</p>
        <h1 class="truncate text-3xl font-bold leading-tight tabular-nums">{{ code.code }}</h1>
      </div>
      <button type="button" class="min-h-control min-w-control ml-auto grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent" aria-label="Atualizar" @click="refresh()">
        <Icon name="lucide:refresh-cw" class="size-4" />
      </button>
    </header>
    <ReadFreshness :metadata="readMetadata" :failed="Boolean(error)" />

    <p v-if="pending && !order" class="text-sm text-muted-foreground">Carregando…</p>
    <!-- `!stationLocked`: com a estação travada a leitura volta 403 e este aviso
         dizia "Pedido não encontrado", que é falso e assusta. Nesse estado quem
         fala é a identificação, que sobe por cima. -->
    <p v-else-if="(error || !order) && !stationLocked" class="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive dark:text-orange-400" data-order-error>
      {{ order ? "Falha ao atualizar. Mantivemos a última leitura e seu rascunho; atualize antes de confirmar ações." : "Pedido não encontrado ou falha ao carregar." }}
    </p>

    <OperatorOrderDetail
      v-if="order"
      v-model:comment="comment"
      :order="order"
      :busy="busy"
      :admin-base-url="adminBaseUrl"
      @comment="submitComment"
    >
      <!-- iFood: o resumo do pagamento/operação e as negociações abertas. -->
      <template #summary>
        <OrderIFoodSummary :cancellation-notice="order.ifood_cancellation_notice" :payment-summary="order.ifood_payment_summary" :operation-summary="order.ifood_operation_summary" />
        <OrderIFoodNegotiations v-if="order.ifood_negotiations?.length" :order-ref="order.ref" :negotiations="order.ifood_negotiations" @refresh="refresh" @dirty-change="negotiationDirty = $event" />
      </template>

      <template #actions>
        <!-- actions — as MESMAS regras do board (cardAffordances), lidas da mesma
             projection. A guarda do "Avançar" era `can_settle_delivery_cash !==
             undefined`, sempre verdadeira, e o "Aceitar" não tinha guarda: num
             pedido `new` os dois apareciam cheios e o clique levava 400. Aqui o
             que decide é o servidor, e quando ele bloqueia o lugar do botão
             continua ocupado dizendo o motivo, em vez de sumir. -->
        <section class="flex flex-wrap gap-2">
          <div v-if="undo" class="flex w-full flex-wrap items-center gap-2 text-sm" :data-undo="undo.kind">
            <span class="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-medium">
              <Icon :name="undo.kind === 'handoff' ? 'lucide:check' : 'lucide:sparkles'" class="size-3.5" />
              {{ undo.label }}
            </span>
            <span class="text-muted-foreground" data-undo-detail>{{ undo.detail }}</span>
            <span v-if="undo.alreadyOut" class="text-muted-foreground" data-undo-already-out>· {{ undo.alreadyOut }}</span>
            <button v-if="undo.canUndo" type="button" :disabled="busy" class="inline-flex min-h-action min-w-action items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-semibold transition hover:bg-accent disabled:opacity-50" data-action="undo" @click="onUndo">
              <Icon name="lucide:undo-2" class="size-4" /> <span class="tabular-nums">{{ undo.kind === "handoff" ? `Desfazer ${undo.countdown}` : "Desfazer" }}</span>
            </button>
          </div>
          <button v-if="projectedAction('confirm')" type="button" :disabled="busy || !projectedAction('confirm')?.enabled" :title="projectedAction('confirm')?.reason" class="inline-flex min-h-action min-w-action items-center gap-1.5 rounded-md border border-transparent bg-primary px-3.5 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50" data-action="confirm" @click="confirm">
            <Icon name="lucide:check" class="size-4" /> Aceitar
          </button>
          <button v-else-if="advanceAction?.enabled" type="button" :disabled="busy" class="inline-flex min-h-action min-w-action items-center gap-1.5 rounded-md border border-transparent bg-primary px-3.5 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50" data-action="advance" @click="onAdvance">
            <Icon name="lucide:arrow-right" class="size-4" /> {{ order.next_action_label }}
          </button>
          <button v-else-if="advanceAction" type="button" disabled :title="advanceAction?.reason" class="inline-flex min-h-control min-w-control cursor-not-allowed items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-semibold text-muted-foreground opacity-60" data-action="advance-blocked">
            <Icon name="lucide:clock" class="size-4" /> {{ advanceAction?.reason }}
          </button>
          <button v-if="order.can_settle_delivery_cash" type="button" :disabled="busy || !settleAction?.enabled" :title="settleAction?.reason" class="inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-semibold transition hover:bg-accent disabled:opacity-50" @click="openDialog('settle')">
            <Icon name="lucide:banknote" class="size-4" /> {{ order.fulfillment_type === "pickup" ? "Receber na retirada" : "Acertar entrega" }}
          </button>
          <button v-if="order.equipment_back_pending" type="button" :disabled="busy || !projectedAction('equipment-back')?.enabled" :title="projectedAction('equipment-back')?.reason || (projectedAction('equipment-back')?.enabled ? '' : 'Atualize o pedido para conferir esta ação.')" class="inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-semibold transition hover:bg-accent disabled:opacity-50" @click="equipmentBack">
            <Icon name="lucide:smartphone-nfc" class="size-4" /> Maquininha voltou
          </button>
          <button v-if="order.fiscal_status === 'failed'" type="button" :disabled="busy || !projectedAction('requeue-fiscal')?.enabled" :title="projectedAction('requeue-fiscal')?.reason || (projectedAction('requeue-fiscal')?.enabled ? '' : 'Atualize o pedido para conferir esta ação.')" class="inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-semibold transition hover:bg-accent disabled:opacity-50" @click="requeueFiscal">
            <Icon name="lucide:file-text" class="size-4" /> Reprocessar NFC-e
          </button>
          <!-- Só para o pedido de LINK ainda cobrável (forma link com URL, vivo,
               não pago, não vencido) — o servidor decide, a tela obedece. A
               cadência (cedo demais, envio em andamento) é recusa da hora do
               clique, com o motivo no toast. -->
          <button v-if="order.can_resend_payment_link" type="button" :disabled="busy" class="inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-semibold transition hover:bg-accent disabled:opacity-50" data-action="resend-payment-link" @click="resendPaymentLink">
            <Icon name="lucide:send" class="size-4" /> Reenviar link de pagamento
          </button>
          <!-- Recusar é a resposta ao pedido que ACABOU de chegar; depois de
               aceito o gesto certo é Cancelar. -->
          <button v-if="projectedAction('reject')" type="button" :disabled="busy || !projectedAction('reject')?.enabled" class="inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border border-destructive/40 px-3.5 py-2 text-sm font-semibold text-destructive transition hover:bg-destructive/10 disabled:opacity-50 dark:text-orange-300" data-action="reject" @click="openDialog('reject')">
            <Icon name="lucide:x" class="size-4" /> Recusar
          </button>
          <!-- `can_cancel` já é régua + política + permissão, resolvidas no
               servidor. O botão ficava sempre visível e o servidor respondia
               "ok" sem cancelar; agora, quando não dá, a tela diz por quê em vez
               de oferecer um gesto que não acontece. -->
          <button v-if="order.can_cancel" type="button" :disabled="busy" class="inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border px-3.5 py-2 text-sm font-medium text-muted-foreground transition hover:bg-accent disabled:opacity-50" data-action="cancel" @click="openDialog('cancel')">
            <Icon name="lucide:ban" class="size-4" />
            {{ order.cancel_requires_approval ? "Cancelar (gerente)" : "Cancelar" }}
          </button>
          <p v-else-if="order.cancel_block_label" class="self-center text-sm text-muted-foreground">
            {{ order.cancel_block_label }}
          </p>
          <!-- Menu do pedido (⋯): o gesto à mão do que o sistema faz sozinho. Hoje,
               "Marcar pronto" enquanto a Cozinha trabalha (estação sem tela, caso
               que o sistema não viu). -->
          <div v-if="menuAdvance" class="relative ml-auto">
            <button type="button" class="grid min-h-control min-w-control place-items-center rounded-md border transition hover:bg-accent" aria-label="Mais ações do pedido" :aria-expanded="menuOpen" data-action="menu" @click="menuOpen = !menuOpen">
              <Icon name="lucide:ellipsis" class="size-4" />
            </button>
            <div v-if="menuOpen" class="fixed inset-0 z-10" aria-hidden="true" @click="menuOpen = false" />
            <div v-if="menuOpen" class="absolute right-0 z-20 mt-1 w-64 rounded-md border bg-popover p-1 text-popover-foreground shadow-md" role="menu">
              <button type="button" role="menuitem" :disabled="busy || !menuAdvance.enabled" :title="menuAdvance.reason || undefined" class="flex min-h-control w-full flex-col items-start rounded px-2.5 py-2 text-left text-sm transition hover:bg-accent disabled:opacity-50" data-action="menu-advance" @click="onMenuAdvance">
                <span class="font-semibold">{{ menuAdvance.label }}</span>
                <span class="text-xs text-muted-foreground">O pronto vem sozinho quando a Cozinha conclui. Use para a estação sem tela.</span>
              </button>
            </div>
          </div>
        </section>
      </template>

      <template #after-profile>
        <!-- corrida de entrega (logística externa) -->
        <OrderCourierPanel
          v-if="order.courier"
          :courier="order.courier"
          :cancel-action="order.actions.find(action => action.ref === 'courier-cancel')"
          :quote-action="order.actions.find(action => action.ref === 'courier-quote')"
          :dispatch-action="order.actions.find(action => action.ref === 'courier-dispatch')"
          :busy="busy"
          @quote="courierQuote"
          @dispatch="courierDispatch"
          @cancel="courierCancel"
        />
        <!-- comprovante de entrega dos avisos ao cliente (D3) -->
        <OrderNotificationReceipts :receipts="order.notification_receipts" />
      </template>

      <!-- A nota da cozinha se EDITA no Gestor: o editor entra no lugar da leitura. -->
      <template #kitchen-note>
        <section class="flex flex-col gap-2 rounded-lg border bg-card p-4">
          <label class="text-sm font-bold uppercase tracking-wide" for="order-notes">Nota da cozinha</label>
          <!-- one-tap tags (configuráveis no Admin) — anexam ao texto, sem duplicar -->
          <div v-if="noteTags.length" class="flex flex-wrap gap-1.5">
            <button
              v-for="(tag, i) in noteTags"
              :key="i"
              type="button"
              class="min-h-control min-w-control inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
              @click="applyNoteTag(tag)"
            >
              <Icon name="lucide:plus" class="size-3" />{{ tag }}
            </button>
          </div>
          <textarea
            id="order-notes"
            v-model="notes"
            rows="3"
            placeholder="Instruções de preparo para a cozinha…"
            class="min-h-control w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          />
          <p class="text-xs text-muted-foreground">Aparece no ticket da cozinha (KDS).</p>
          <div v-if="notesConflict" role="alert" class="rounded-md border p-3 text-sm">
            <p>A nota mudou enquanto você escrevia. Seu texto está preservado acima.</p>
            <p class="my-2 whitespace-pre-wrap">No servidor: {{ order.kitchen_note || "(vazia)" }}</p>
            <div class="flex gap-2">
              <button type="button" class="min-h-control min-w-control rounded border px-2 py-1" @click="acceptLatestNotesBase">Manter meu texto</button>
              <button type="button" class="min-h-control min-w-control rounded border px-2 py-1" @click="useLatestNotes">Usar texto do servidor</button>
            </div>
          </div>
          <p v-if="mutationError" role="alert" class="text-sm text-destructive">{{ mutationError }}</p>
          <button
            type="button"
            :disabled="busy || !notesDirty || notesConflict"
            class="min-h-action min-w-action self-end rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-40"
            @click="saveKitchenNote"
          >
            Salvar nota
          </button>
        </section>
      </template>
    </OperatorOrderDetail>

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
      @update:open="(v) => { if (!v) dialog = '' }"
      @confirm="submitReason"
    />

    <!-- settle delivery cash dialog -->
    <UiDialog :open="dialog === 'settle'" @update:open="(v) => { if (!v) dialog = '' }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>{{ order?.fulfillment_type === "pickup" ? "Pagamento na retirada" : "Acerto da entrega" }}</UiDialogTitle>
          <UiDialogDescription>{{ order?.fulfillment_type === "pickup" ? "Confirme o recebimento antes de concluir e entregar o pedido ao cliente." : "Confirme após conferir o dinheiro e os comprovantes da maquininha." }}</UiDialogDescription>
        </UiDialogHeader>
        <p class="text-sm text-muted-foreground">{{ settleCustody }}</p>
        <p v-if="settleChanged" role="alert" class="text-sm text-destructive">O pedido ou turno mudou. Confira o contexto atual: {{ settleAction?.confirmation.description }}
          <button type="button" class="min-h-control min-w-control underline" @click="reviewSettleCustody">Conferir e manter os valores digitados</button>
        </p>
        <input
          v-model="amount"
          type="text"
          inputmode="decimal"
          placeholder="Ex.: 15,00"
          class="min-h-control w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Valor recebido"
        />
        <label v-if="asksChangeBack" class="flex flex-col gap-1 text-sm" data-change-back>
          <span class="text-muted-foreground">{{ order?.change_label }}. Quanto voltou?</span>
          <input
            v-model="changeBack"
            type="text"
            inputmode="decimal"
            placeholder="0,00"
            class="min-h-control w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
            aria-label="Troco que voltou"
          />
        </label>
        <label v-if="asksEquipmentBack" class="flex min-h-control items-center gap-2 text-sm" data-equipment-back>
          <input v-model="settleEquipmentBack" type="checkbox" />
          <span>{{ order?.equipment_label }}. Voltou junto</span>
        </label>
        <UiDialogFooter>
          <button type="button" class="min-h-control min-w-control rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="dialog = ''">Voltar</button>
          <button
            type="button"
            :disabled="busy || settleChanged || !settleAction?.enabled"
            class="min-h-action min-w-action rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="submitSettle"
          >
            Confirmar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- dispatch dialog: how much change leaves the drawer with the courier -->
    <UiDialog :open="dialog === 'dispatch'" @update:open="(v) => { if (!v) dialog = '' }">
      <UiDialogContent class="sm:max-w-md" data-dispatch-dialog>
        <UiDialogHeader>
          <UiDialogTitle>{{ dispatchAsksChange ? "Troco para o entregador" : "Saída para entrega" }}</UiDialogTitle>
          <UiDialogDescription>
            <template v-if="dispatchAsksChange">{{ order?.change_label }}. O valor sai do seu turno de caixa e volta no acerto.</template>
            <template v-else>O que sai com o entregador.</template>
          </UiDialogDescription>
        </UiDialogHeader>
        <div v-if="order?.equipment_options.length" class="flex flex-col gap-1.5" data-dispatch-equipment>
          <label v-for="opt in order.equipment_options" :key="opt.ref" class="flex min-h-control items-center gap-2 rounded-md border px-3 py-2 text-sm">
            <input type="checkbox" :disabled="opt.enabled === false" :checked="dispatchEquipment.includes(opt.ref)" @change="toggleDispatchEquipment(opt.ref)" />
            <span>{{ opt.label }}<span v-if="opt.reason"> · {{ opt.reason }}</span></span>
          </label>
        </div>
        <label v-if="dispatchAsksChange" class="flex items-center gap-2 text-sm">
          <span class="text-muted-foreground">R$</span>
          <input
            v-model="changeOut"
            type="text"
            inputmode="decimal"
            placeholder="Ex.: 20,00"
            class="min-h-control w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
            aria-label="Troco que o entregador leva"
          />
        </label>
        <UiDialogFooter>
          <button type="button" class="min-h-control min-w-control rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="dialog = ''">Voltar</button>
          <button v-if="dispatchAsksChange" type="button" :disabled="busy" class="min-h-control min-w-control rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent disabled:opacity-50" @click="submitDispatch('0')">Saiu sem troco</button>
          <button
            type="button"
            :disabled="busy"
            class="min-h-action min-w-action rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="submitDispatch(changeOut)"
          >
            {{ dispatchAsksChange ? "Levou o troco" : "Saiu para entrega" }}
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

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
      :error="managerChallenge?.code === 'manager_approval_invalid' ? managerChallenge.message : ''"
      @update:open="(aberto: boolean) => { if (!aberto) dismissManagerChallenge(); }"
      @authorize="signWithPin"
      @authorize-badge="signWithBadge"
    />
  </main>
</template>
