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
  <UiDialog :open="card != null" @update:open="(v) => { if (!v) emit('close') }">
    <UiDialogContent class="sm:max-w-sm" data-courier-back-dialog>
      <UiDialogHeader>
        <UiDialogTitle>Entregador voltou</UiDialogTitle>
        <UiDialogDescription>{{ card ? courierReturnOrders(card) : "" }} Confira:</UiDialogDescription>
      </UiDialogHeader>
      <ul class="flex flex-col gap-1.5 text-sm" data-courier-back-lines>
        <li v-for="line in card?.courier_return_lines ?? []" :key="line" class="flex items-start gap-2 rounded-md border px-3 py-2 font-medium">
          <Icon name="lucide:check" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span>{{ line }}</span>
        </li>
      </ul>
      <UiDialogFooter>
        <button type="button" class="min-h-control min-w-control rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="emit('different')">Voltou diferente</button>
        <button
          type="button"
          class="min-h-action min-w-action rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          :disabled="busy"
          @click="emit('confirm')"
        >Conferido</button>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
