<script setup lang="ts">
// ENCOMENDAS · DETALHE — o MESMO detalhe do pedido do Gestor, no balcão.
//
// Decisão do dono (28/09/2026): o detalhe do Gestor e o da encomenda são telas
// IRMÃS. As seções (resumo, cliente, nota fiscal, itens, observação do cliente,
// nota da cozinha, histórico com comentários) são do `OperatorOrderDetail` do
// kit; a leitura é a do Gestor no contexto "pos" (`order.counter` traz o que é
// do balcão). Aqui fica só o que é do balcão, no PAINEL DO BALCÃO (S5 do
// redesenho, P3 do dono em 02/10): à direita e fixo em tela larga, antes do
// detalhe em tela estreita. O PDV não usa os slots `#summary` e `#actions` do
// kit; o Gestor continua usando.
//
// - quem, a situação e o SALDO (quanto falta receber);
// - os gestos (ENCOMENDAS-PDV-PLAN, WP-E3/E4/E6), em três alturas: o principal,
//   **Receber e entregar** (ou só **Entregar**, quando já está paga), na largura
//   inteira; os de uso médio (**Editar**, **Reagendar**, **Imprimir Via Pedido**)
//   lado a lado; **Cancelar** separado, no pé. Cada um só quando o servidor diz
//   que pode (`hand_over`, `edit`, `reschedule`, `cancel`). Quando não pode
//   entregar, a tela diz por quê em vez de mostrar botão apagado. **Editar** abre
//   a própria tela de venda em modo edição (`/?edit=<ref>`); com a NFC-e já
//   autorizada o servidor fecha a edição e o gesto vira **Cancelar e refazer**;
// - o atalho **Comentar no histórico**, que leva ao campo do kit;
// - uma etiqueta de estado só, a do balcão (P5 do dono, 02/10): o resumo do kit
//   vem sem a etiqueta de status do pedido (`show-status`), que o Gestor mantém;
// - os diálogos de cada gesto.
import { toast } from "vue-sonner";

import type { ManagerApproval } from "~/composables/usePosCashSession";
import type { HandOverBody } from "~/presentation/preorderActions";
import { requiresOpenShiftForSale } from "~/presentation/cash";
import { PREORDERS_HOME, preorderBackTarget } from "~/presentation/preorderDetail";
import { handOverCta, redoNotice } from "~/presentation/preorderActions";
import { customerLine, moneyLine, rowShowsSituation, situationTone } from "~/presentation/preorders";
import { canComment, toneBadge } from "../../../../operator-kit/app/presentation/orderDetail";

const route = useRoute();
const ref_ = computed(() => String(route.params.ref || ""));

useHead({ title: () => `Encomenda ${ref_.value}` });

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();

const { detail, pending, error, refresh } = usePosPreorderDetail(ref_);
const counter = computed(() => detail.value?.counter ?? null);
const card = computed(() => counter.value?.card ?? null);
const notFound = computed(() => !!error.value && httpError(error.value).status === 404);

const tickets = usePosOrderTickets(pos);

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
const commentAllowed = computed(() => !!detail.value && canComment(detail.value));
// O atalho do painel leva ao campo do histórico, que mora no fim do detalhe.
const layout = useTemplateRef<HTMLElement>("layout");
const { reveal } = useNextFocus();
function goToComment() {
  reveal(() => layout.value?.querySelector<HTMLElement>("[data-order-comment] textarea"), { align: "center" });
}
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
  <PosPreordersShell :pos="pos" :pending="posPending || pending" wide @refresh="refreshPos(); refresh()">
    <div class="mx-auto grid w-full max-w-3xl gap-4 lg:max-w-6xl">
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
        <!-- Uma árvore só: em tela larga o painel do Balcão fica à direita e FIXO (o
             saldo e os gestos à vista enquanto se conferem os itens); em tela
             estreita ele vem primeiro, e o saldo é a primeira coisa da tela. -->
        <div ref="layout" class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_23rem] lg:items-start" data-preorder-layout>
          <aside
            class="grid gap-3 rounded-md border bg-card p-4 lg:sticky lg:top-6 lg:col-start-2 lg:row-start-1"
            aria-label="Balcão"
            data-preorder-counter-panel
          >
            <!-- QUEM e QUANTO: o que o balcão lê primeiro ("vim buscar a encomenda
                 da Ana"). O número e o canal já estão no resumo do pedido. -->
            <header class="grid min-w-0 gap-1" data-preorder-detail>
              <h1 class="break-words text-lg font-semibold">{{ customerLine(card) }}</h1>
              <p class="flex flex-wrap items-center gap-2">
                <!-- A mesma régua da linha da lista: a etiqueta só quando diz o que o
                     saldo não diz (Pronto, Saiu para entrega, Entregue). "A pagar",
                     "Pago", "Na conta da casa" e "Conferir pagamento" já estão na linha
                     do saldo ao lado. -->
                <span
                  v-if="rowShowsSituation(card.situation)"
                  class="rounded-md border px-2 py-0.5 text-sm font-medium"
                  :class="toneBadge(situationTone(card.situation))"
                  data-preorder-situation
                >{{ card.situation_label }}</span>
                <span class="text-xl font-semibold tabular-nums" data-preorder-money>{{ moneyLine(card) }}</span>
              </p>
            </header>

            <p
              v-if="actions.paidOnline.value && counter.hand_over.allowed && !counter.hand_over.needs_payment"
              class="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-warning"
              role="status"
              data-preorder-paid-online
            >
              <Icon name="lucide:badge-check" class="mt-0.5 size-4 shrink-0" />
              <span>{{ actions.paidOnline.value }}</span>
            </p>

            <!-- O GESTO PRINCIPAL ocupa a largura; quando não pode, a tela diz por quê. -->
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

            <!-- Os gestos de uso médio, lado a lado e menores que o principal: cada um
                 na largura do próprio rótulo, e o que não cabe desce de linha. -->
            <div class="flex flex-wrap gap-2" data-preorder-actions>
              <UiButton
                v-if="counter.reschedule.allowed"
                variant="outline"
                class="flex-auto"
                :disabled="actions.busy.value"
                data-preorder-reschedule
                @click="rescheduleOpen = true"
              >
                <Icon name="lucide:calendar-clock" class="size-4" />
                Reagendar
              </UiButton>
              <!-- A Via Pedido individual: a mesma impressão da Via Pedido – painel. -->
              <UiButton
                variant="outline"
                class="flex-auto"
                :disabled="!!tickets.printingRef.value"
                :loading="tickets.printingRef.value === ref_"
                data-preorder-print
                @click="printTicket"
              >
                <Icon name="lucide:printer" class="size-4" />
                {{ counter.ticket_printed ? "Imprimir a Via Pedido de novo" : "Imprimir Via Pedido" }}
              </UiButton>
              <UiButton
                v-if="counter.edit.allowed"
                variant="outline"
                class="flex-auto"
                :disabled="actions.busy.value"
                data-preorder-edit
                @click="editOrder"
              >
                <Icon name="lucide:pencil" class="size-4" />
                Editar encomenda
              </UiButton>
              <UiButton
                v-else-if="counter.edit.cancel_and_redo && counter.cancel.allowed"
                variant="outline"
                class="flex-auto"
                :disabled="actions.busy.value"
                data-preorder-cancel-and-redo
                @click="cancelAndRedo"
              >
                <Icon name="lucide:rotate-ccw" class="size-4" />
                Cancelar e refazer
              </UiButton>
            </div>
            <p
              v-if="!counter.edit.allowed && counter.edit.cancel_and_redo && counter.cancel.allowed"
              class="text-sm text-muted-foreground"
              data-preorder-edit-blocked
            >{{ counter.edit.block_reason }}</p>
            <p v-if="!tickets.hasPrinter.value" class="text-sm text-muted-foreground">
              {{ tickets.printerUnavailableReason.value }} A Via Pedido sai no balcão que tem impressora.
            </p>

            <!-- Comentar: atalho para o campo do histórico (o campo é do kit, e só
                 existe quando o servidor oferece a ação). -->
            <UiButton
              v-if="commentAllowed"
              variant="ghost"
              class="w-full justify-start"
              data-preorder-comment-shortcut
              @click="goToComment"
            >
              <Icon name="lucide:message-square-plus" class="size-4" />
              Comentar no histórico
            </UiButton>

            <!-- CANCELAR fica separado, no pé, e sem destaque maior que o gesto seguro. -->
            <div v-if="counter.cancel.allowed" class="border-t pt-3" data-preorder-cancel-zone>
              <UiButton
                variant="ghost"
                class="w-full justify-start text-destructive hover:text-destructive"
                :disabled="actions.busy.value"
                data-preorder-cancel
                @click="redoAfterCancel = false; cancelOpen = true"
              >
                <Icon name="lucide:x" class="size-4" />
                Cancelar encomenda
              </UiButton>
            </div>
          </aside>

          <OperatorOrderDetail
            v-model:comment="comment"
            class="min-w-0 lg:col-start-1 lg:row-start-1"
            :order="detail"
            :busy="actions.busy.value"
            :show-status="false"
            @comment="submitComment"
          />
        </div>

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
          :presets="detail.cancellation_presets"
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
    </div>
  </PosPreordersShell>
</template>
