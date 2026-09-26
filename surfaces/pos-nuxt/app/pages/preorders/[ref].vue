<script setup lang="ts">
// ENCOMENDAS · DETALHE — uma encomenda, com o que o balcão precisa para entregar:
// quem, como recebe, quando, o que leva, quanto é e quanto falta.
//
// Os gestos (ENCOMENDAS-PDV-PLAN, WP-E3/E4): **Receber e entregar** (ou só
// **Entregar**, quando já está paga), **Reagendar** e **Cancelar**, cada um só
// quando o servidor diz que pode (`hand_over`, `reschedule`, `cancel`). Quando não
// pode entregar, a tela diz por quê em vez de mostrar botão apagado. Editar ainda
// não existe no PDV (depende do contador) — e não há botão para ele: botão que não
// faz nada ensina o balcão a desconfiar dos que fazem.
import type { ManagerApproval } from "~/composables/usePosCashSession";
import type { HandOverBody } from "~/presentation/preorderActions";
import { handOverCta } from "~/presentation/preorderActions";
import { fulfillmentIcon } from "~/presentation/orderTickets";
import { customerLine, moneyLine, situationTone } from "~/presentation/preorders";

const route = useRoute();
const ref_ = computed(() => String(route.params.ref || ""));

useHead({ title: () => `Encomenda ${ref_.value}` });

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();

const { detail, pending, error, refresh } = usePosPreorderDetail(ref_);
const card = computed(() => detail.value?.card ?? null);
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

async function confirmReschedule(choice: { date: string; slot: string; reason: string }) {
  if (await actions.reschedule(choice)) rescheduleOpen.value = false;
}
const cancelReason = ref("");

async function confirmHandOver(body: HandOverBody) {
  const done = await actions.handOver(body);
  // Entregou, ou o cliente acabou de pagar online (o aviso fica na página).
  if (done || actions.paidOnline.value) handOverOpen.value = false;
}

async function confirmCancel(reason: string, managerApproval: ManagerApproval | null = null) {
  cancelReason.value = reason;
  if (await actions.cancel(reason, managerApproval)) cancelOpen.value = false;
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

function goBack() {
  if (import.meta.client && window.history.length > 1) window.history.back();
  else void navigateTo("/preorders/today");
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
      <UiButton variant="outline" size="sm" to="/preorders">Procurar outra encomenda</UiButton>
    </section>

    <p
      v-else-if="error"
      class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
      <span>{{ httpErrorMessage(error, "Não deu para ler a encomenda agora.") }} Tente de novo em Atualizar, no menu ao lado.</span>
    </p>

    <template v-else-if="detail && card">
      <!-- QUEM e a SITUAÇÃO: o que se lê primeiro. -->
      <section class="grid gap-2 rounded-md border border-border bg-card p-4" data-preorder-detail>
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="grid min-w-0 gap-0.5">
            <h1 class="truncate text-lg font-semibold">{{ customerLine(card) }}</h1>
            <p class="text-sm text-muted-foreground">{{ card.ref }} · {{ card.channel_label }}</p>
          </div>
          <span
            class="rounded-md border px-2 py-0.5 text-sm font-medium"
            :class="TONE_CLASS[situationTone(card.situation)]"
            data-preorder-situation
          >{{ card.situation_label }}</span>
        </div>
        <p class="text-base font-semibold tabular-nums" data-preorder-money>{{ moneyLine(card) }}</p>
        <p class="text-sm text-muted-foreground">{{ detail.payment_method_label }}</p>
      </section>

      <!-- OS GESTOS: entregar é o óbvio; cancelar fica ao lado, menor. -->
      <section class="grid gap-2" data-preorder-actions>
        <p
          v-if="actions.paidOnline.value && detail.hand_over.allowed && !detail.hand_over.needs_payment"
          class="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-warning"
          role="status"
          data-preorder-paid-online
        >
          <Icon name="lucide:badge-check" class="mt-0.5 size-4 shrink-0" />
          <span>{{ actions.paidOnline.value }}</span>
        </p>
        <UiButton
          v-if="detail.hand_over.allowed"
          size="lg"
          class="w-full"
          :disabled="actions.busy.value"
          data-preorder-hand-over
          @click="handOverOpen = true"
        >
          <Icon :name="detail.hand_over.needs_payment ? 'lucide:hand-coins' : 'lucide:package-check'" class="size-5" />
          {{ handOverCta(detail.hand_over) }}
        </UiButton>
        <p
          v-else-if="card.situation !== 'delivered'"
          class="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground"
          data-preorder-hand-over-blocked
        >
          <Icon name="lucide:info" class="mt-0.5 size-4 shrink-0" />
          <span>{{ detail.hand_over.block_reason }}</span>
        </p>
        <UiButton
          v-if="detail.reschedule.allowed"
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
          v-if="detail.cancel.allowed"
          variant="outline"
          class="w-full text-destructive"
          :disabled="actions.busy.value"
          data-preorder-cancel
          @click="cancelOpen = true"
        >
          <Icon name="lucide:x" class="size-4" />
          Cancelar encomenda
        </UiButton>
      </section>

      <!-- COMO e QUANDO recebe. -->
      <section class="grid gap-2 rounded-md border border-border bg-card p-4">
        <h2 class="flex items-center gap-2 text-sm font-semibold">
          <Icon :name="fulfillmentIcon(card.fulfillment_type)" class="size-4 text-muted-foreground" />
          {{ card.fulfillment_label }}
        </h2>
        <p class="text-sm">
          <span class="capitalize">{{ card.commitment_date_display }}</span>
          <template v-if="card.window_label"> · {{ card.window_label }}</template>
          <template v-else> · sem horário combinado</template>
        </p>
        <p v-if="detail.delivery_address" class="text-sm">{{ detail.delivery_address }}</p>
        <p v-if="detail.delivery_instructions" class="text-sm text-muted-foreground">{{ detail.delivery_instructions }}</p>
        <p v-if="detail.customer_phone" class="text-sm">
          <a v-if="detail.customer_phone_uri" :href="detail.customer_phone_uri" class="underline underline-offset-2">{{ detail.customer_phone }}</a>
          <template v-else>{{ detail.customer_phone }}</template>
        </p>
        <p v-else-if="detail.customer_relay_phone" class="text-sm text-muted-foreground">
          Telefone da central do iFood: {{ detail.customer_relay_phone }}<template v-if="detail.customer_relay_code">, código {{ detail.customer_relay_code }}</template>
        </p>
      </section>

      <!-- O QUE leva. -->
      <section class="grid gap-2 rounded-md border border-border bg-card p-4">
        <h2 class="text-sm font-semibold">Itens</h2>
        <ul class="grid gap-1 text-sm">
          <li v-for="(item, index) in detail.items" :key="index" class="flex justify-between gap-3">
            <span class="min-w-0"><span class="tabular-nums">{{ item.qty_display }}x</span> {{ item.name }}</span>
            <span class="shrink-0 tabular-nums text-muted-foreground">{{ item.line_total_display }}</span>
          </li>
        </ul>
        <p class="flex justify-between border-t border-border pt-2 text-sm font-semibold">
          <span>Total</span>
          <span class="tabular-nums">{{ card.total_display }}</span>
        </p>
      </section>

      <section v-if="detail.customer_note" class="grid gap-1 rounded-md border border-border bg-card p-4">
        <h2 class="text-sm font-semibold">Observação do cliente</h2>
        <p class="text-sm">{{ detail.customer_note }}</p>
      </section>

      <!-- A Via Pedido individual: a mesma impressão da Via Pedido – painel. -->
      <section class="grid gap-2">
        <UiButton
          size="lg"
          variant="outline"
          class="w-full"
          :disabled="!!tickets.printingRef.value"
          :loading="tickets.printingRef.value === ref_"
          data-preorder-print
          @click="printTicket"
        >
          <Icon name="lucide:printer" class="size-5" />
          {{ detail.ticket_printed ? "Imprimir a Via Pedido de novo" : "Imprimir Via Pedido" }}
        </UiButton>
        <p v-if="!tickets.hasPrinter.value" class="text-sm text-muted-foreground">
          {{ tickets.printerUnavailableReason.value }} A Via Pedido sai no balcão que tem impressora.
        </p>
      </section>

      <PosPreorderHandOverDialog
        v-model:open="handOverOpen"
        :hand-over="detail.hand_over"
        :customer-name="customerLine(card)"
        :busy="actions.busy.value"
        @confirm="confirmHandOver"
      />
      <PosPreorderRescheduleDialog
        v-model:open="rescheduleOpen"
        :customer-name="customerLine(card)"
        :current-date="detail.reschedule.date"
        :current-slot="detail.reschedule.slot"
        :skus="detail.reschedule.skus"
        :busy="actions.busy.value"
        @confirm="confirmReschedule"
      />
      <PosPreorderCancelDialog
        v-model:open="cancelOpen"
        :customer-name="customerLine(card)"
        :requires-approval="detail.cancel.requires_approval"
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
