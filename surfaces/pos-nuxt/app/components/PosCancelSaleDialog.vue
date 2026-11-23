<script setup lang="ts">
// Cancelar uma venda fechada é EXCEÇÃO auditada (anti-fraude), não fluxo do
// operador: confirmação destrutiva + desafio gerencial num só diálogo.
//
// ⚠️ O diálogo É o `OperatorManagerAuth` do operator-kit, a mesma autorização de
// gerente de toda a suíte. Este componente só põe o contexto do ato (qual pedido,
// o prazo, o motivo) no slot `context`. Antes ele montava a própria moldura em
// volta do `OperatorIdentify`, e cada moldura repetia a decisão de cair num campo
// de nome digitado quando a lista chegava vazia (dono, 28/10/2026).
import type { POSManagerProjection } from "~/types/pos";

const props = defineProps<{
  open: boolean;
  orderRef: string;
  /**
   * O valor da venda que o gerente assina ("R$ 42,00"), na frente do PIN. Sem
   * ele, o diálogo dizia só o número do pedido, e o gerente assinava o
   * cancelamento de uma venda de R$ 4,00 ou de R$ 400,00 do mesmo jeito (P1-6).
   */
  totalDisplay: string;
  reason: string;
  /** O que foi registrado: a venda de balcão ou a encomenda. O nome do ato segue o
   *  objeto, e o gerente lê "Cancelar a encomenda" quando é encomenda (P2-7, #3192). */
  noun?: "venda" | "encomenda";
  maxAgeMinutes?: number;
  managers?: POSManagerProjection[];
  /** Quem CONTINUA operando depois da assinatura. Ver OperatorManagerAuth. */
  operatorName?: string;
  busy?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  "update:reason": [string];
  confirm: [string, string];
  confirmBadge: [string];
}>();
</script>

<template>
  <OperatorManagerAuth
    :open="props.open"
    action="cancel_sale"
    :operator-name="props.operatorName"
    :managers="props.managers ?? []"
    :busy="props.busy"
    :error="props.error"
    @update:open="(value: boolean) => emit('update:open', value)"
    @authorize="(username: string, pin: string) => emit('confirm', username, pin)"
    @authorize-badge="(token: string) => emit('confirmBadge', token)"
  >
    <template #context>
      <p class="text-base font-semibold text-highlighted" data-cancel-sale-total>
        Cancelar a {{ props.noun ?? "venda" }} de <span class="tabular-nums">{{ props.totalDisplay }}</span>
      </p>
      <p class="text-sm text-muted-foreground">
        Pedido {{ props.orderRef }}.
        <template v-if="props.maxAgeMinutes">
          Disponível por até {{ props.maxAgeMinutes }} minutos após a {{ props.noun ?? "venda" }}; depois, cancele pelo Gestor.
        </template>
      </p>
      <NuxtInput
        :model-value="props.reason"
        placeholder="Motivo do cancelamento (opcional)"
        aria-label="Motivo do cancelamento (opcional)"
        autocomplete="off"
        class="w-full"
        @update:model-value="(value: string | number) => emit('update:reason', String(value))"
      />
    </template>
  </OperatorManagerAuth>
</template>
