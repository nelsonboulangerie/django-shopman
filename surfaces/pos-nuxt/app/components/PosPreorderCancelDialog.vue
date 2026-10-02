<script setup lang="ts">
// Cancelar uma encomenda pelo PDV. A régua, a política e a permissão são as do
// Gestor (a rota é a mesma), e o diálogo também: é o `OperatorReasonDialog` do
// operator-kit. Aqui o operador confirma e, se quiser, escreve o motivo que vai
// para o cliente. Pedido pago pede o PIN de um gerente, que sobe por cima deste
// diálogo (`OperatorManagerAuth`, na página); o motivo digitado fica.
import type { ReasonChoice } from "../../../operator-kit/app/types/reason";

const props = defineProps<{
  open: boolean;
  customerName: string;
  requiresApproval: boolean;
  busy?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  confirm: [string];
}>();

const description = computed(() =>
  "O que já foi pago volta no mesmo meio. Devolução em dinheiro aparece na Sessão de caixa, em Precisa de você."
  + (props.requiresApproval ? " Encomenda paga: um gerente precisa autorizar." : ""),
);
</script>

<template>
  <OperatorReasonDialog
    :open="open"
    :title="`Cancelar a encomenda de ${customerName}?`"
    :description="description"
    confirm-label="Cancelar encomenda"
    reason-label="Motivo para o cliente (opcional)"
    :maxlength="200"
    :busy="busy"
    @update:open="(value: boolean) => emit('update:open', value)"
    @confirm="(choice: ReasonChoice) => emit('confirm', choice.reason)"
  />
</template>
