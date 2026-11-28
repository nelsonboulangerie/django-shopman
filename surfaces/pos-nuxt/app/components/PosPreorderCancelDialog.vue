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
  /**
   * O que cancelar faz com o dinheiro, com o valor: a frase do servidor (a mesma
   * do Gestor). "" quando ele não sabe dizer, e aí vale a frase geral.
   */
  moneyEffect?: string;
  /** A lista única de motivos de cancelar, a mesma do Gestor. */
  cancelReasons: KeyedReason[];
  busy?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  confirm: [{ reasonKey: string; internalNote: string }];
}>();

// A aprovação de gerente é pedida exatamente quando há (ou pode haver) dinheiro
// recebido (`operator_cancel_policy`). Sem ela, não há o que devolver, e falar de
// devolução numa encomenda sem pagamento confundia (beta test de 05/11/2026, PDV2-20).
// Com o valor na frase (P1-6): quem cancela e o gerente que assina leem quanto
// volta e por onde, antes do gesto.
const description = computed(() => {
  if (!props.requiresApproval) return "Nada foi pago nesta encomenda: não há o que devolver.";
  const effect = props.moneyEffect?.trim();
  if (effect) return `${effect} Encomenda paga: um gerente precisa autorizar.`;
  return "O que já foi pago volta no mesmo meio. Devolução em dinheiro aparece no Caixa, em Precisa de você. Encomenda paga: um gerente precisa autorizar.";
});
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
