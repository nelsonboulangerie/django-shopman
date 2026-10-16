<script setup lang="ts">
// Cancelar uma encomenda pelo PDV. A régua, a política e a permissão são as do
// Gestor (a rota é a mesma), e o diálogo também: é o `OperatorReasonDialog` do
// operator-kit. O operador escolhe o motivo da lista única do backend (o cliente lê
// a frase revisada dele) e, se quiser, escreve uma observação interna, que nunca
// vai ao cliente. Encomenda paga pede o PIN de um gerente, que sobe por cima deste
// diálogo (`OperatorManagerAuth`, na página); a escolha fica.
import type { KeyedReason, ReasonChoice } from "../../../operator-kit/app/types/reason";

const props = defineProps<{
  open: boolean;
  customerName: string;
  requiresApproval: boolean;
  /** A lista única de motivos de cancelar, a mesma do Gestor. */
  cancelReasons: KeyedReason[];
  busy?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  confirm: [{ reasonKey: string; internalNote: string }];
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
    :maxlength="200"
    :keyed-reasons="cancelReasons"
    :busy="busy"
    @update:open="(value: boolean) => emit('update:open', value)"
    @confirm="(choice: ReasonChoice) => emit('confirm', { reasonKey: choice.key, internalNote: choice.reason })"
  />
</template>
