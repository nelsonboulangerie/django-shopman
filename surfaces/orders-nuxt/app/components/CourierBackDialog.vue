<script setup lang="ts">
// "Entregador voltou": antes de fechar a saída, a lista curta do que deve estar
// na mão do operador. Um toque fecha tudo (entrega, dinheiro, troco e maquininha);
// se voltou diferente, o acerto à mão continua no detalhe/diálogo de acerto.
import type { OrderCardProjection } from "~/types/orders";
import { courierReturnOrders } from "~/presentation/board";

defineProps<{ card: OrderCardProjection | null; busy?: boolean }>();
const emit = defineEmits<{ (e: "confirm" | "different" | "close"): void }>();
</script>

<template>
  <NuxtModal
    :open="card != null"
    title="Entregador voltou"
    :description="`${card ? courierReturnOrders(card) : ''} Confira:`"
    data-courier-back-dialog
    @update:open="
      (v) => {
        if (!v) emit('close');
      }
    "
  >
    <template #body>
      <NuxtAlert
        color="info"
        variant="subtle"
        icon="i-lucide-list-checks"
        title="Conferir no retorno"
      >
        <template #description>
          <ul class="list-inside list-disc text-sm" data-courier-back-lines>
            <li v-for="line in card?.courier_return_lines ?? []" :key="line">
              {{ line }}
            </li>
          </ul>
        </template>
      </NuxtAlert>
    </template>
    <template #footer>
      <NuxtButton
        label="Voltou diferente"
        color="neutral"
        variant="outline"
        @click="emit('different')"
      />
      <NuxtButton
        label="Conferido"
        color="primary"
        :disabled="busy"
        :loading="busy"
        @click="emit('confirm')"
      />
    </template>
  </NuxtModal>
</template>
