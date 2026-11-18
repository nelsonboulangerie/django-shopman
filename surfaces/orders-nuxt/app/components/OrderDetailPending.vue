<script setup lang="ts">
// "O que falta neste pedido" (WP-G05): a faixa do Gestor acima do detalhe do kit.
//
// O servidor manda a lista pronta (`projections/order_pending.py`): cada linha com o
// fato, o motivo e a ação que já existe para resolvê-la. Aqui a linha ganha o ícone do
// tom e o botão ao lado; o toque sobe para a página (`act`), que já tem o gesto.
// Não é aviso que se dispensa: é a lista de trabalho do pedido, e some sozinha quando
// nada falta. Espera saudável não usa cor de erro.
// `data-detail-block` marca a linha do avanço travado (pagamento ou espera): é o gancho
// que as jornadas de navegador já usavam para o aviso de bloqueio que esta faixa absorveu.
import { computed } from "vue";

import type {
  CancelledMoneyProjection,
  OrderPendingProjection,
} from "~/generated/ordersContract";
import { pendingLines, settledMoney } from "~/presentation/orderPending";

const props = withDefaults(
  defineProps<{
    pending?: readonly OrderPendingProjection[];
    money?: CancelledMoneyProjection | null;
    /** Uma gravação do pedido em andamento. */
    busy?: boolean;
    /** A DANFE deste pedido está indo para a impressora. */
    danfePrinting?: boolean;
  }>(),
  { pending: () => [], money: null, busy: false, danfePrinting: false },
);

const emit = defineEmits<{ act: [ref: string] }>();

const lines = computed(() =>
  pendingLines(props.pending, {
    busy: props.busy,
    danfePrinting: props.danfePrinting,
  }),
);
const money = computed(() => settledMoney(props.money));
</script>

<template>
  <NuxtCard v-if="lines.length || money" as="section" data-order-pending>
    <div class="flex flex-col gap-3">
      <template v-if="lines.length">
        <div class="flex items-center justify-between gap-3">
          <h2 class="op-title">O que falta neste pedido</h2>
          <OperatorCountChip :count="lines.length" />
        </div>
        <ul class="flex flex-col gap-3">
          <li
            v-for="line in lines"
            :key="line.key"
            class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4"
            :data-pending="line.key"
            :data-pending-tone="line.tone"
            :data-detail-block="
              line.key === 'payment' || line.key === 'advance' ? '' : undefined
            "
          >
            <div class="flex min-w-0 items-start gap-2">
              <Icon
                :name="line.icon"
                class="mt-0.5 size-4 shrink-0"
                :class="line.iconClass"
              />
              <div class="flex min-w-0 flex-col gap-0.5">
                <p class="text-sm font-medium text-highlighted">
                  <span class="sr-only">{{ line.spoken }}: </span
                  >{{ line.label }}
                </p>
                <p
                  v-if="line.reason"
                  class="text-sm text-muted"
                  data-pending-reason
                >
                  {{ line.reason }}
                </p>
                <p
                  v-for="reason in line.blockedReasons"
                  :key="reason"
                  class="text-xs text-muted"
                  data-pending-blocked
                >
                  {{ reason }}
                </p>
              </div>
            </div>
            <div
              v-if="line.buttons.length"
              class="flex shrink-0 flex-wrap gap-2 ps-6 sm:ps-0"
            >
              <template v-for="button in line.buttons" :key="button.ref">
                <NuxtButton
                  v-if="button.href"
                  :to="button.href"
                  target="_blank"
                  :icon="button.icon"
                  :label="button.label"
                  :color="button.color"
                  :variant="button.variant"
                  :data-pending-action="button.ref"
                />
                <NuxtButton
                  v-else
                  type="button"
                  :icon="button.icon"
                  :label="button.label"
                  :color="button.color"
                  :variant="button.variant"
                  :disabled="button.disabled"
                  :data-pending-action="button.ref"
                  @click="emit('act', button.ref)"
                />
              </template>
            </div>
          </li>
        </ul>
      </template>
      <div
        v-if="money"
        class="flex items-start gap-2"
        data-order-money
        :data-order-money-state="props.money?.state"
      >
        <Icon
          name="lucide:circle-check"
          class="mt-0.5 size-4 shrink-0 text-success"
        />
        <div class="flex min-w-0 flex-col gap-0.5">
          <p class="text-sm font-medium text-highlighted">{{ money.title }}</p>
          <p v-if="money.customerLine" class="text-sm text-muted">
            {{ money.customerLine }}
          </p>
        </div>
      </div>
    </div>
  </NuxtCard>
</template>
