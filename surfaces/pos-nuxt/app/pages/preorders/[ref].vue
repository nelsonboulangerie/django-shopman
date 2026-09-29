<script setup lang="ts">
// ENCOMENDAS · DETALHE — o MESMO detalhe do pedido do Gestor, no balcão.
//
// Decisão do dono (28/09/2026): o detalhe do Gestor e o da encomenda são telas
// IRMÃS. As seções (resumo, cliente, nota fiscal, itens, observação do cliente,
// nota da cozinha, histórico com comentários) são do `OperatorOrderDetail` do
// kit; a leitura é a do Gestor no contexto "pos" (`order.counter` traz o que é
// do balcão). Aqui fica só o que é do balcão:
//
// - o SALDO no resumo (situação e quanto falta receber);
// - a barra de ações (ENCOMENDAS-PDV-PLAN, WP-E3/E4/E6): **Receber e entregar**
//   (ou só **Entregar**, quando já está paga), **Editar**, **Reagendar**,
//   **Cancelar** e **Imprimir Via Pedido**, cada um só quando o servidor diz que
//   pode (`hand_over`, `edit`, `reschedule`, `cancel`). Quando não pode entregar,
//   a tela diz por quê em vez de mostrar botão apagado. **Editar** abre a própria
//   tela de venda em modo edição (`/?edit=<ref>`); com a NFC-e já autorizada o
//   servidor fecha a edição e o gesto vira **Cancelar e refazer** (28/09);
// - os diálogos de cada gesto.
import { toast } from "vue-sonner";

import type { ManagerApproval } from "~/composables/usePosCashSession";
import type { HandOverBody } from "~/presentation/preorderActions";
import { requiresOpenShiftForSale } from "~/presentation/cash";
import { PREORDERS_HOME, preorderBackTarget } from "~/presentation/preorderDetail";
import { handOverCta, redoNotice } from "~/presentation/preorderActions";
import { customerLine, moneyLine, situationTone } from "~/presentation/preorders";

const route = useRoute();
const ref_ = computed(() => String(route.params.ref || ""));

useHead({ title: () => `Encomenda ${ref_.value}` });

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();

const { detail, pending, error, refresh } = usePosPreorderDetail(ref_);
const counter = computed(() => detail.value?.counter ?? null);
const card = computed(() => counter.value?.card ?? null);
const notFound = computed(() => !!error.value && httpError(error.value).status === 404);

const tickets = usePosOrderTickets(pos, { loadBatch: false });

async function printTicket() {
  if (await tickets.printOne(ref_.value)) await refresh();
}

// ── Os gestos ──
const { operator: activeOperator } = useOperatorLock("cashman.operate_pos");
const actions = usePosPreorderActions({ detail, pos, refresh });
const handOverOpen = ref(false);
const cancelOpen = ref(false);
const rescheduleOpen = ref(false);

// O rascunho do comentário no histórico (o campo é do `OperatorOrderDetail`).
const comment = ref("");
async function submitComment(note: string) {
  if (await actions.comment(note)) comment.value = "";
}

async function confirmReschedule(choice: { date: string; slot: string; reason: string }) {
  if (await actions.reschedule(choice)) rescheduleOpen.value = false;
}
const cancelReason = ref("");
// "Cancelar e refazer": o cancelamento é o de sempre (política e PIN); depois
// dele a venda abre numa comanda comum pré-montada com a encomenda cancelada,
// para o operador ajustar e fechar a venda nova (a nota autorizada não se edita).
const redoAfterCancel = ref(false);

function editOrder() {
  if (!detail.value) return;
  void navigateTo({ path: "/", query: { edit: detail.value.ref } });
}

function cancelAndRedo() {
  redoAfterCancel.value = true;
  cancelOpen.value = true;
}

async function confirmHandOver(body: HandOverBody) {
  const done = await actions.handOver(body);
  // Entregou, ou o cliente acabou de pagar online (o aviso fica na página).
  if (done || actions.paidOnline.value) handOverOpen.value = false;
}

async function confirmCancel(reason: string, managerApproval: ManagerApproval | null = null) {
  cancelReason.value = reason;
  if (!(await actions.cancel(reason, managerApproval))) return;
  cancelOpen.value = false;
  if (redoAfterCancel.value) {
    redoAfterCancel.value = false;
    const redo = await actions.redo(ref_.value);
    if (!redo) {
      await navigateTo("/");
      return;
    }
    // A mesma régua da tela de venda (`index.vue`): sem turno, ela manda à
    // antesala antes de abrir a comanda.
    const needsOpenShift = requiresOpenShiftForSale(pos.value?.checkout?.capabilities?.cash_management)
      && !pos.value?.has_open_cash_session;
    toast.info(redoNotice(redo.redo, { needsOpenShift }));
    await navigateTo({ path: "/", query: { redo: ref_.value } });
  }
}

// O PIN do gerente sobe por cima do diálogo de cancelar; assinado, o mesmo
// gesto é repetido com a assinatura e o motivo que já estava digitado.
function signWithPin(username: string, pin: string) {
  void confirmCancel(cancelReason.value, { username, pin });
}
function signWithBadge(badge: string) {
  void confirmCancel(cancelReason.value, { badge });
}

const TONE_CLASS: Record<string, string> = {
  warning: "border-warning/40 bg-warning/10 text-warning",
  success: "border-success/40 bg-success/10 text-success",
  info: "border-info/40 bg-info/10 text-info",
  neutral: "border-border bg-muted text-muted-foreground",
};

// A volta respeita de onde o operador veio: o recorte da lista (modo, data,
// filtros) mora na URL dela — `?back=` ou o histórico —, e só sem nenhum dos
// dois a volta é a casa da seção.
function goBack() {
  const target = preorderBackTarget(route.query.back);
  if (target) void navigateTo(target);
  else if (import.meta.client && window.history.length > 1) window.history.back();
  else void navigateTo(PREORDERS_HOME);
}
</script>

<template>
  <PosPreordersShell current="" :pos="pos" :pending="posPending || pending" @refresh="refreshPos(); refresh()">
    <div>
      <UiButton variant="ghost" size="sm" data-preorder-back @click="goBack">
        <Icon name="lucide:arrow-left" class="size-4" />
        Voltar
      </UiButton>
    </div>

    <p v-if="pending && !detail" class="p-4 text-sm text-muted-foreground">Carregando a encomenda…</p>

    <section
      v-else-if="notFound"
      class="grid justify-items-center gap-2 rounded-md border border-dashed border-border p-8 text-center"
      data-preorder-not-found
    >
      <Icon name="lucide:search-x" class="size-6 text-muted-foreground" />
      <p class="text-sm text-muted-foreground">
        O pedido {{ ref_ }} não é uma encomenda: não existe, foi cancelado ou foi venda de Balcão.
      </p>
      <UiButton variant="outline" size="sm" :to="PREORDERS_HOME">Procurar outra encomenda</UiButton>
    </section>

    <p
      v-else-if="error"
      class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
      <span>{{ httpErrorMessage(error, "Não deu para ler a encomenda agora.") }} Tente de novo em Atualizar, no menu ao lado.</span>
    </p>

    <template v-else-if="detail && counter && card">
      <!-- QUEM: o que o balcão lê primeiro ("vim buscar a encomenda da Ana"). -->
      <header class="grid min-w-0 gap-0.5" data-preorder-detail>
        <h1 class="truncate text-lg font-semibold">{{ customerLine(card) }}</h1>
        <p class="text-sm text-muted-foreground">{{ card.ref }} · {{ card.channel_label }}</p>
      </header>

      <OperatorOrderDetail
        v-model:comment="comment"
        :order="detail"
        :busy="actions.busy.value"
        @comment="submitComment"
      >
        <!-- O SALDO: a situação da encomenda e quanto falta receber no balcão. -->
        <template #summary>
          <p class="flex flex-wrap items-center gap-2 pt-1">
            <span
              class="rounded-md border px-2 py-0.5 text-sm font-medium"
              :class="TONE_CLASS[situationTone(card.situation)]"
              data-preorder-situation
            >{{ card.situation_label }}</span>
            <span class="text-base font-semibold tabular-nums" data-preorder-money>{{ moneyLine(card) }}</span>
          </p>
        </template>

        <!-- OS GESTOS DO BALCÃO: entregar é o óbvio; cancelar fica ao lado, menor. -->
        <template #actions>
          <section class="grid gap-2" data-preorder-actions>
            <p
              v-if="actions.paidOnline.value && counter.hand_over.allowed && !counter.hand_over.needs_payment"
              class="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-warning"
              role="status"
              data-preorder-paid-online
            >
              <Icon name="lucide:badge-check" class="mt-0.5 size-4 shrink-0" />
              <span>{{ actions.paidOnline.value }}</span>
            </p>
            <UiButton
              v-if="counter.hand_over.allowed"
              size="lg"
              class="w-full"
              :disabled="actions.busy.value"
              data-preorder-hand-over
              @click="handOverOpen = true"
            >
              <Icon :name="counter.hand_over.needs_payment ? 'lucide:hand-coins' : 'lucide:package-check'" class="size-5" />
              {{ handOverCta(counter.hand_over) }}
            </UiButton>
            <p
              v-else-if="card.situation !== 'delivered'"
              class="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground"
              data-preorder-hand-over-blocked
            >
              <Icon name="lucide:info" class="mt-0.5 size-4 shrink-0" />
              <span>{{ counter.hand_over.block_reason }}</span>
            </p>
            <UiButton
              v-if="counter.edit.allowed"
              variant="outline"
              class="w-full"
              :disabled="actions.busy.value"
              data-preorder-edit
              @click="editOrder"
            >
              <Icon name="lucide:pencil" class="size-4" />
              Editar encomenda
            </UiButton>
            <template v-else-if="counter.edit.cancel_and_redo && counter.cancel.allowed">
              <p class="text-sm text-muted-foreground" data-preorder-edit-blocked>{{ counter.edit.block_reason }}</p>
              <UiButton
                variant="outline"
                class="w-full"
                :disabled="actions.busy.value"
                data-preorder-cancel-and-redo
                @click="cancelAndRedo"
              >
                <Icon name="lucide:rotate-ccw" class="size-4" />
                Cancelar e refazer
              </UiButton>
            </template>
            <UiButton
              v-if="counter.reschedule.allowed"
              variant="outline"
              class="w-full"
              :disabled="actions.busy.value"
              data-preorder-reschedule
              @click="rescheduleOpen = true"
            >
              <Icon name="lucide:calendar-clock" class="size-4" />
              Reagendar
            </UiButton>
            <UiButton
              v-if="counter.cancel.allowed"
              variant="outline"
              class="w-full text-destructive"
              :disabled="actions.busy.value"
              data-preorder-cancel
              @click="redoAfterCancel = false; cancelOpen = true"
            >
              <Icon name="lucide:x" class="size-4" />
              Cancelar encomenda
            </UiButton>
            <!-- A Via Pedido individual: a mesma impressão da Via Pedido – painel. -->
            <UiButton
              variant="outline"
              class="w-full"
              :disabled="!!tickets.printingRef.value"
              :loading="tickets.printingRef.value === ref_"
              data-preorder-print
              @click="printTicket"
            >
              <Icon name="lucide:printer" class="size-4" />
              {{ counter.ticket_printed ? "Imprimir a Via Pedido de novo" : "Imprimir Via Pedido" }}
            </UiButton>
            <p v-if="!tickets.hasPrinter.value" class="text-sm text-muted-foreground">
              {{ tickets.printerUnavailableReason.value }} A Via Pedido sai no balcão que tem impressora.
            </p>
          </section>
        </template>
      </OperatorOrderDetail>

      <PosPreorderHandOverDialog
        v-model:open="handOverOpen"
        :hand-over="counter.hand_over"
        :customer-name="customerLine(card)"
        :busy="actions.busy.value"
        @confirm="confirmHandOver"
      />
      <PosPreorderRescheduleDialog
        v-model:open="rescheduleOpen"
        :customer-name="customerLine(card)"
        :current-date="counter.reschedule.date"
        :current-slot="counter.reschedule.slot"
        :skus="counter.reschedule.skus"
        :busy="actions.busy.value"
        @confirm="confirmReschedule"
      />
      <PosPreorderCancelDialog
        v-model:open="cancelOpen"
        :customer-name="customerLine(card)"
        :requires-approval="counter.cancel.requires_approval"
        :busy="actions.busy.value"
        @confirm="(reason: string) => confirmCancel(reason)"
      />
      <OperatorManagerAuth
        :open="!!actions.managerChallenge.value"
        action="cancel_sale"
        :operator-name="activeOperator?.name || ''"
        :managers="detail.managers"
        :busy="actions.busy.value"
        :error="actions.managerChallenge.value?.code === 'manager_approval_invalid' ? actions.managerChallenge.value.message : ''"
        @update:open="(isOpen: boolean) => { if (!isOpen) actions.dismissManagerChallenge(); }"
        @authorize="signWithPin"
        @authorize-badge="signWithBadge"
      />
    </template>
  </PosPreordersShell>
</template>
