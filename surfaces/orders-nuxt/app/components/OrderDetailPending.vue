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
// Cada linha é alvo do próximo foco (`data-focus-target`): quem chega com `#promise` é
// levado à linha da promessa em risco, com o teclado no primeiro gesto dela. O gesto
// dessa linha é "Resolver": sobe para a página (`act`), que abre o diálogo das escolhas.
import { computed } from "vue";

import type {
  CancelledMoneyProjection,
  OrderPendingProjection,
  OrderPromiseProjection,
} from "~/generated/ordersContract";
import {
  PROMISE_PENDING_KEY,
  pendingFocusKey,
  pendingLines,
  settledMoney,
} from "~/presentation/orderPending";
import { promiseRisk, promiseSuggestionGroups } from "~/presentation/orderPromise";
import OrderPromiseSuggestions from "./OrderPromiseSuggestions.vue";
import { useOperatorAppLink } from "../../../operator-kit/app/composables/useOperatorAppLink";

const props = withDefaults(
  defineProps<{
    pending?: readonly OrderPendingProjection[];
    money?: CancelledMoneyProjection | null;
    /** A promessa do pedido: a linha "Promessa em risco" lista as sugestões dela. */
    promise?: OrderPromiseProjection | null;
    /** Uma gravação do pedido em andamento. */
    busy?: boolean;
    /** A DANFE deste pedido está indo para a impressora. */
    danfePrinting?: boolean;
    /** O estorno deste pedido está sendo pedido de novo ao meio de pagamento (WP-G13). */
    refundRetrying?: boolean;
  }>(),
  {
    pending: () => [],
    money: null,
    promise: null,
    busy: false,
    danfePrinting: false,
    refundRetrying: false,
  },
);

const emit = defineEmits<{ act: [ref: string] }>();

const lines = computed(() =>
  pendingLines(props.pending, {
    busy: props.busy,
    danfePrinting: props.danfePrinting,
    refundRetrying: props.refundRetrying,
  }),
);
const money = computed(() => settledMoney(props.money));
// A linha da promessa escreve os itens numa frase; as sugestões vêm em lista, por item.
const suggestionGroups = computed(() =>
  promiseSuggestionGroups(promiseRisk({ promise: props.promise })),
);
// "Abrir a Produção" abre outro app de operador: na janela dele quando instalado.
const { attrsFor } = useOperatorAppLink();
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
            :data-focus-target="pendingFocusKey(line.key)"
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
                <!-- O que a casa pode oferecer no lugar do item que falta, uma por linha. -->
                <template v-if="line.key === PROMISE_PENDING_KEY">
                  <OrderPromiseSuggestions
                    v-for="group in suggestionGroups"
                    :key="group.key"
                    class="mt-1 text-sm text-highlighted"
                    :heading="group.heading"
                    :options="group.options"
                  />
                </template>
                <!-- A frase do servidor, quando a lista e o botão cheio não dizem tudo. -->
                <p
                  v-if="line.nextStep"
                  class="text-sm font-medium text-highlighted"
                  data-pending-next-step
                >
                  {{ line.nextStep }}
                </p>
                <!-- A tentativa que não deu certo fica escrita na linha (WP-G13): quem
                     abre o pedido depois lê o que o meio de pagamento respondeu. -->
                <p
                  v-if="line.failure"
                  class="text-sm text-error"
                  role="status"
                  data-pending-failure
                >
                  {{ line.failure }}
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
              <template
                v-for="(button, index) in line.buttons"
                :key="button.ref"
              >
                <!-- A Produção abre na janela dela (outro app de operador). -->
                <NuxtButton
                  v-if="button.href && button.crossApp"
                  :to="button.href"
                  :target="attrsFor(button.href).target"
                  :rel="attrsFor(button.href).rel"
                  external
                  :icon="button.icon"
                  :label="button.label"
                  :color="button.color"
                  :variant="button.variant"
                  :data-focus-control="index === 0 ? '' : undefined"
                  :data-pending-action="button.ref"
                />
                <!-- A conversa com o cliente abre fora da casa, em outra janela. -->
                <NuxtButton
                  v-else-if="button.href"
                  :to="button.href"
                  target="_blank"
                  :icon="button.icon"
                  :label="button.label"
                  :color="button.color"
                  :variant="button.variant"
                  :data-focus-control="index === 0 ? '' : undefined"
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
                  :data-focus-control="index === 0 ? '' : undefined"
                  :loading="button.loading"
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
