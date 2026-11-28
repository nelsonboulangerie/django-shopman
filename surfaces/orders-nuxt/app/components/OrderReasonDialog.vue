<script setup lang="ts">
// Recusar ou cancelar um pedido no Gestor. O diálogo é o `OperatorReasonDialog` do
// operator-kit, o mesmo do cancelar no PDV. UMA lista de motivos para os dois gestos,
// em qualquer canal (dono, 07/11/2026): a lista única do backend (`cancel_reasons`
// da projeção). Escolher é obrigatório; o cliente lê a frase revisada do motivo, e o
// texto livre é a observação interna.
//
// Recusar sem surpresa (WP-G06): antes de confirmar, o diálogo diz QUAL pedido (no
// painel: código no título, quem pediu e quanto), o que acontece com o dinheiro (a
// frase do servidor, `cancel_money_effect`) e só oferece o motivo que cabe no pedido
// (`presentation/orderReason.ts`). A falha do gesto aparece aqui dentro, e o confirmar
// fica sempre à vista, no rodapé.
//
// No pedido do iFood, a lista esconde o que o iFood não oferece ("O cliente pediu",
// "Pagamento não confirmado": `offered_on_ifood`), e o código que o iFood exige sai
// do motivo, no servidor (`ifood_callbacks.DEFAULT_REASON_CODES`).
import { computed } from "vue";

import type { ReasonChoice } from "../../../operator-kit/app/types/reason";
import {
  MONEY_WHAT,
  reasonDialogView,
  reasonErrorField,
  type MoneyRead,
  type ReasonOrderFacts,
} from "~/presentation/orderReason";
import type { CancelReasonProjection } from "~/types/orders";

const props = withDefaults(
  defineProps<{
    open: boolean;
    mode: "reject" | "cancel";
    cancelReasons: CancelReasonProjection[];
    busy: boolean;
    marketplace: boolean;
    /** Motivo já marcado ao abrir (cancelar o Pix vencido: "Pagamento não confirmado"). */
    initialKey?: string;
    /**
     * O que acontece com o dinheiro ("R$ 5,10 serão estornados no cartão do
     * cliente."), da projeção do pedido. O diálogo falava só do motivo, e o
     * operador cancelava sem saber o destino do dinheiro (beta 06/11, F5).
     */
    moneyEffect?: string;
    /** O pedido do gesto: decide os motivos que cabem e, com `identify`, quem ele é. */
    order?: ReasonOrderFacts | null;
    /** O gesto nasceu num cartão entre vários (painel): o diálogo diz qual pedido. */
    identify?: boolean;
    /** A leitura do destino do dinheiro, quando o diálogo a busca ao abrir. */
    moneyRead?: MoneyRead;
    /** A falha do gesto, dita dentro do diálogo. */
    error?: string;
    /** O `field` que o servidor apontou (dialeto `{detail, field, errors}`). */
    errorField?: string;
  }>(),
  {
    initialKey: "",
    moneyEffect: "",
    order: null,
    identify: false,
    moneyRead: "ready",
    error: "",
    errorField: "",
  },
);

const emit = defineEmits<{
  "update:open": [value: boolean];
  "dirty-change": [value: boolean];
  "retry-money": [];
  confirm: [payload: { reasonKey: string; internalNote: string }];
}>();

const view = computed(() =>
  reasonDialogView({
    mode: props.mode,
    reasons: props.cancelReasons,
    marketplace: props.marketplace,
    order: props.order,
    identify: props.identify,
    moneyEffect: props.moneyEffect,
    moneyRead: props.moneyRead,
    initialKey: props.initialKey,
  }),
);
const hasOrderBlock = computed(() =>
  Boolean(
    view.value.customer ||
      view.value.total ||
      view.value.facts ||
      view.value.money.state === "sentence" ||
      view.value.money.state === "loading",
  ),
);
</script>

<template>
  <OperatorReasonDialog
    :open="open"
    :title="view.title"
    :description="view.description"
    :confirm-label="view.confirmLabel"
    :keyed-reasons="view.reasons"
    :initial-key="initialKey"
    :busy="busy"
    :error="error"
    :error-field="reasonErrorField(errorField)"
    :blocked="view.blocked"
    @update:open="(value: boolean) => emit('update:open', value)"
    @dirty-change="(value: boolean) => emit('dirty-change', value)"
    @confirm="
      (choice: ReasonChoice) =>
        emit('confirm', { reasonKey: choice.key, internalNote: choice.reason })
    "
  >
    <template
      v-if="hasOrderBlock || view.money.state === 'error'"
      #summary
    >
      <div class="flex flex-col gap-3" data-reason-order>
        <div
          v-if="hasOrderBlock"
          class="flex flex-col gap-2 rounded-md bg-elevated p-3"
        >
          <div
            v-if="view.customer || view.total"
            class="flex items-baseline justify-between gap-3"
          >
            <p
              class="min-w-0 text-sm font-medium break-words"
              data-reason-order-customer
            >
              {{ view.customer }}
            </p>
            <p
              v-if="view.total"
              class="shrink-0 text-sm font-medium tabular-nums"
              data-reason-order-total
            >
              {{ view.total }}
            </p>
          </div>
          <p
            v-if="view.facts"
            class="text-xs text-muted"
            data-reason-order-facts
          >
            {{ view.facts }}
          </p>
          <p
            v-if="view.money.state === 'sentence'"
            class="flex items-start gap-2 text-sm font-medium"
            data-reason-money
          >
            <NuxtIcon name="i-lucide-banknote" class="mt-0.5 size-4 shrink-0" />
            <span>{{ view.money.text }}</span>
          </p>
          <p
            v-else-if="view.money.state === 'loading'"
            class="flex items-center gap-2 text-sm text-muted"
            role="status"
            data-reason-money-loading
          >
            <NuxtIcon
              name="i-lucide-loader-circle"
              class="size-4 shrink-0 animate-spin motion-reduce:animate-none"
            />
            <span>{{ view.money.text }}</span>
          </p>
        </div>
        <OperatorScreenState
          v-if="view.money.state === 'error'"
          state="error"
          :what="MONEY_WHAT"
          data-reason-money-error
          @retry="emit('retry-money')"
        />
      </div>
    </template>
  </OperatorReasonDialog>
</template>
