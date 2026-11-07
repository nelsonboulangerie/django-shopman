<script setup lang="ts">
// Recusar ou cancelar um pedido no Gestor. O diálogo é o `OperatorReasonDialog` do
// operator-kit, o mesmo do cancelar no PDV. UMA lista de motivos para os dois gestos,
// em qualquer canal (dono, 07/11/2026): a lista única do backend (`cancel_reasons`
// da projeção). Escolher é obrigatório; o cliente lê a frase revisada do motivo, e o
// texto livre é a observação interna.
//
// No pedido do iFood, a lista esconde o que o iFood não oferece ("O cliente pediu",
// "Pagamento não confirmado": `offered_on_ifood`), e o código que o iFood exige sai
// do motivo, no servidor (`ifood_callbacks.DEFAULT_REASON_CODES`).
import type { ReasonChoice } from "../../../operator-kit/app/types/reason";
import type { CancelReasonProjection } from "~/types/orders";

const props = defineProps<{
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
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  "dirty-change": [value: boolean];
  confirm: [payload: { reasonKey: string; internalNote: string }];
}>();

const reasons = computed(() =>
  props.marketplace
    ? props.cancelReasons.filter((reason) => reason.offered_on_ifood)
    : props.cancelReasons,
);

const title = computed(() =>
  props.mode === "reject" ? "Recusar pedido" : "Cancelar pedido",
);
const description = computed(() => {
  const base = props.marketplace
    ? "Escolha o motivo. O iFood e o cliente recebem o aviso com ele."
    : "Escolha o motivo. O cliente recebe o aviso com a frase do motivo.";
  const money = String(props.moneyEffect ?? "").trim();
  return money ? `${money} ${base}` : base;
});
</script>

<template>
  <OperatorReasonDialog
    :open="open"
    :title="title"
    :description="description"
    :confirm-label="mode === 'reject' ? 'Recusar pedido' : 'Cancelar pedido'"
    :keyed-reasons="reasons"
    :initial-key="initialKey ?? ''"
    :busy="busy"
    @update:open="(value: boolean) => emit('update:open', value)"
    @dirty-change="(value: boolean) => emit('dirty-change', value)"
    @confirm="
      (choice: ReasonChoice) =>
        emit('confirm', { reasonKey: choice.key, internalNote: choice.reason })
    "
  />
</template>
