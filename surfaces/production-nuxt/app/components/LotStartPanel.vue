<script setup lang="ts">
// "Quanto está previsto?": o previsto abre o lote e segue para a Finalização. Duas
// formas, o mesmo gesto: o painel encaixado à direita no tablet deitado (`panel`) e o
// diálogo nas outras telas (`modal`). O estado e as contas moram na grade
// (`ProductionStageGrid`); aqui só se mostra e se avisa.
import { ref } from "vue";

import { formatQtyUnit, rowLabel } from "~/presentation/production";
import type {
  ProductionMatrixRowProjection,
  WorkOrderCardProjection,
} from "~/types/production";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

defineProps<{
  variant: "panel" | "modal";
  open?: boolean;
  row: ProductionMatrixRowProjection | null;
  selectedPk: number | null;
  selectedOrder: WorkOrderCardProjection | null;
  submitting: boolean;
  ready: boolean;
  outsized: string | null;
  needsDoubleCheck: boolean;
  diverges: boolean;
}>();

const qty = defineModel<string>("qty", { required: true });

const emit = defineEmits<{
  close: [];
  cancel: [];
  select: [workOrder: WorkOrderCardProjection];
  bump: [delta: number];
  confirm: [];
  acknowledge: [];
  digit: [digit: string];
  backspace: [];
  clear: [];
}>();

// O campo de quantidade é `NuxtInput`: o foco vai ao `<input>` que ele expõe.
const qtyInput = ref<{ inputRef?: HTMLInputElement | null } | null>(null);
defineExpose({
  focusQty: () => qtyInput.value?.inputRef?.focus(),
});
</script>

<template>
  <!-- Painel de confirmação encaixado (tablet deitado): lote em blocos, quantidade
       com − / + no tamanho do toque, numérico na tela e "Confirmar N un." no polegar. -->
  <aside
    v-if="variant === 'panel' && row"
    class="flex w-[392px] shrink-0 flex-col border-l border-border bg-card"
    aria-label="Confirmar o previsto"
    data-open-confirm-panel
  >
    <header class="flex items-start gap-3 border-b border-border px-5 pt-4 pb-3.5">
      <div class="min-w-0 flex-1">
        <p class="op-eyebrow text-muted-foreground">Quanto está previsto?</p>
        <h2 class="truncate op-heading leading-tight">
          {{ rowLabel(row) }}
        </h2>
        <p class="op-micro text-muted-foreground">
          {{ row.output_sku }} · esta quantidade segue para a Finalização.
        </p>
      </div>
      <NuxtButton
        icon="i-lucide-x"
        color="neutral"
        variant="ghost"
        size="xl"
        square
        aria-label="Fechar"
        @click="emit('close')"
      />
    </header>
    <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
      <template v-if="row.planned_orders.length > 1">
        <p class="op-label text-muted-foreground">Lote que vai confirmar</p>
        <div class="grid grid-cols-2 gap-2">
          <NuxtButton
            v-for="workOrder in row.planned_orders"
            :key="workOrder.pk"
            color="neutral"
            variant="outline"
            size="xl"
            block
            :active="selectedPk === workOrder.pk"
            active-color="primary"
            active-variant="outline"
            :ui="{ base: 'h-auto flex-col items-start justify-start text-left' }"
            :aria-pressed="selectedPk === workOrder.pk"
            @click="emit('select', workOrder)"
          >
            <span class="op-title">#{{ workOrder.ref }}</span>
            <span class="op-micro text-muted-foreground"
              >planejado {{ workOrder.planned_qty }} un.</span
            >
          </NuxtButton>
        </div>
      </template>
      <p v-else-if="selectedOrder" class="op-label text-muted-foreground">
        Lote #{{ selectedOrder.ref }} · planejado {{ selectedOrder.planned_qty }} un.
      </p>
      <template v-if="selectedOrder">
        <div class="flex items-center gap-2">
          <NuxtButton
            icon="i-lucide-minus"
            color="neutral"
            variant="outline"
            size="xl"
            square
            aria-label="Diminuir"
            @click="emit('bump', -1)"
          />
          <NuxtInput
            ref="qtyInput"
            v-model="qty"
            inputmode="none"
            size="xl"
            color="primary"
            highlight
            class="w-full"
            :ui="{ base: 'text-center text-3xl font-bold tabular-nums' }"
            aria-label="Quantidade prevista"
            @keydown.enter.prevent="emit('confirm')"
          />
          <NuxtButton
            icon="i-lucide-plus"
            color="neutral"
            variant="outline"
            size="xl"
            square
            aria-label="Aumentar"
            @click="emit('bump', 1)"
          />
        </div>
        <NuxtAlert
          v-if="outsized"
          color="warning"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :description="outsized"
          data-start-outsized
          :actions="
            alertActions('warning', [
              needsDoubleCheck && { label: 'O número está certo', onClick: () => emit('acknowledge') },
            ])
          "
        />
        <p v-else-if="diverges" class="op-label text-muted-foreground">
          Diferente do planejado ({{ selectedOrder.planned_qty }}). É rendimento, não perda.
        </p>
        <OperatorNumpad
          class="[&_button]:h-14! [&_button]:op-figure"
          subject="quantidade prevista"
          @digit="(digit: string) => emit('digit', digit)"
          @backspace="emit('backspace')"
          @clear="emit('clear')"
        />
      </template>
    </div>
    <footer class="flex gap-2 border-t border-border px-5 py-4">
      <NuxtButton
        color="neutral"
        variant="outline"
        size="xl"
        block
        class="flex-1"
        label="Cancelar"
        @click="emit('close')"
      />
      <NuxtButton
        size="xl"
        block
        class="flex-[1.6]"
        icon="i-lucide-check"
        :disabled="submitting || !ready || needsDoubleCheck"
        :label="
          submitting
            ? 'Confirmando…'
            : `Confirmar ${formatQtyUnit(qty || '0', row.output_unit)}`
        "
        data-open-confirm-submit
        @click="emit('confirm')"
      />
    </footer>
  </aside>

  <!-- Confirmar: o previsto abre o lote e segue para a Finalização (evento interno: start) -->
  <NuxtModal
    v-else-if="variant === 'modal'"
    :open="open"
    :title="`Quanto está previsto? · ${row ? rowLabel(row) : ''}`"
    :description="`${row?.output_sku ?? ''} · esta quantidade abre o lote e segue para a Finalização.`"
    :ui="{ content: 'sm:max-w-sm' }"
    @update:open="
      (v: boolean) => {
        if (!v) emit('close');
      }
    "
  >
    <template #body>
      <div class="flex flex-col gap-3">
        <div
          v-if="
            row &&
            row.planned_orders.length > 1 &&
            !selectedOrder
          "
          class="grid gap-2"
        >
          <p class="text-sm text-muted-foreground">
            Selecione o lote que vai confirmar.
          </p>
          <!-- O bloco do lote carrega referência e quantidade; é seleção de registro. -->
          <NuxtButton
            v-for="workOrder in row.planned_orders"
            :key="workOrder.pk"
            color="neutral"
            variant="outline"
            size="xl"
            block
            :ui="{ base: 'justify-between' }"
            @click="emit('select', workOrder)"
          >
            <span class="font-medium">#{{ workOrder.ref }}</span>
            <span class="tabular-nums text-muted-foreground"
              >{{ workOrder.planned_qty }} un.</span
            >
          </NuxtButton>
        </div>
        <p v-if="selectedOrder" class="text-sm text-muted-foreground">
          Lote #{{ selectedOrder.ref }} · planejado
          {{ selectedOrder.planned_qty }}
        </p>
        <div v-if="selectedOrder" class="flex items-center gap-2">
          <NuxtButton
            icon="i-lucide-minus"
            color="neutral"
            variant="outline"
            size="xl"
            square
            aria-label="Diminuir"
            @click="emit('bump', -1)"
          />
          <NuxtInput
            ref="qtyInput"
            v-model="qty"
            inputmode="decimal"
            size="xl"
            class="w-full"
            :ui="{ base: 'text-center text-3xl font-bold tabular-nums' }"
            aria-label="Quantidade prevista"
            @keydown.enter.prevent="emit('confirm')"
          />
          <NuxtButton
            icon="i-lucide-plus"
            color="neutral"
            variant="outline"
            size="xl"
            square
            aria-label="Aumentar"
            @click="emit('bump', 1)"
          />
        </div>
        <!-- Divergiu do planejado? A tela avisa e segue: é rendimento, não perda.
             Um zero a mais (3x) se confere antes de abrir. -->
        <NuxtAlert
          v-if="outsized"
          color="warning"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :description="outsized"
          data-start-outsized
          :actions="
            alertActions('warning', [
              needsDoubleCheck && { label: 'O número está certo', onClick: () => emit('acknowledge') },
            ])
          "
        />
        <p
          v-else-if="selectedOrder && diverges"
          class="text-sm text-muted-foreground"
        >
          Diferente do planejado ({{ selectedOrder.planned_qty }}).
        </p>
      </div>
    </template>
    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <NuxtButton
          color="neutral"
          variant="outline"
          size="xl"
          label="Cancelar"
          @click="emit('cancel')"
        />
        <NuxtButton
          size="xl"
          :disabled="submitting || !ready || needsDoubleCheck"
          aria-keyshortcuts="Enter"
          :label="submitting ? 'Confirmando…' : 'Confirmar'"
          @click="emit('confirm')"
        />
      </div>
    </template>
  </NuxtModal>
</template>
