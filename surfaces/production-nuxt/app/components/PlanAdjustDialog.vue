<script setup lang="ts">
// O diálogo de planejar, nos três sentidos do gesto (planejar, ajustar o planejado,
// somar um lote novo). O estado e as contas moram na grade (`ProductionStageGrid`);
// aqui só se mostra e se avisa.
import { computed, ref } from "vue";

import LotVoidStakes from "./LotVoidStakes.vue";

import type {
  ProductionMatrixRowProjection,
  WorkOrderCardProjection,
} from "~/types/production";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

const props = defineProps<{
  row: ProductionMatrixRowProjection | null;
  title: string;
  description: string;
  mode: "plan" | "adjust" | "new-batch";
  selectedOrder: WorkOrderCardProjection | null;
  source: "manual" | "suggested";
  outsized: string | null;
  needsDoubleCheck: boolean;
  submitting: boolean;
  qtyValid: boolean;
  actionAllowed: boolean;
  removes: boolean;
}>();

const qty = defineModel<string>("qty", { required: true });
// Zerar um lote que existe é cancelar o lote (#3400): pede o motivo de quem decide.
const removeReason = defineModel<string>("removeReason", { required: true });

// Tirar do plano é com quem pode cancelar lote (o mesmo `can_void` do "Cancelar
// lote…"). Para os outros, a tela diz quem cancela no lugar do botão, em vez de
// deixar tocar e recusar depois.
const removeAllowed = computed(
  () => !props.removes || !!props.selectedOrder?.can_void,
);

const emit = defineEmits<{
  close: [];
  cancel: [];
  select: [workOrder: WorkOrderCardProjection];
  bump: [delta: number];
  confirm: [];
  acknowledge: [];
}>();

// O campo de quantidade é `NuxtInput`: o foco vai ao `<input>` que ele expõe.
const qtyInput = ref<{ inputRef?: HTMLInputElement | null } | null>(null);
defineExpose({
  focusQty: () => qtyInput.value?.inputRef?.focus(),
});
</script>

<template>
  <!-- planejar -->
  <NuxtModal
    :open="row != null"
    :title="title"
    :description="description"
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
            Selecione o lote exato que deseja ajustar.
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
        <p
          v-if="mode === 'adjust' && selectedOrder"
          class="text-sm text-muted-foreground"
        >
          Substitui #{{ selectedOrder.ref }} ({{
            selectedOrder.planned_qty
          }}). Com 0, o lote sai do plano.
        </p>
        <p
          v-else-if="mode === 'new-batch'"
          class="text-sm text-muted-foreground"
        >
          Soma ao dia<template v-if="row?.started_qty !== '0'">
            · {{ row?.started_qty }} previstas</template
          ><template v-if="row?.finished_qty !== '0'">
            · {{ row?.finished_qty }} realizadas</template
          >.
        </p>
        <div
          v-if="!row?.planned_orders.length || selectedOrder"
          class="flex items-center gap-2"
        >
          <NuxtButton
            icon="i-lucide-minus"
            color="neutral"
            variant="outline"
            size="xl"
            square
            :disabled="source === 'suggested'"
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
            :readonly="source === 'suggested'"
            aria-label="Quantidade planejada"
            @keydown.enter.prevent="emit('confirm')"
          />
          <NuxtButton
            icon="i-lucide-plus"
            color="neutral"
            variant="outline"
            size="xl"
            square
            :disabled="source === 'suggested'"
            aria-label="Aumentar"
            @click="emit('bump', 1)"
          />
        </div>
        <LotVoidStakes
          v-if="removes && selectedOrder?.can_void"
          v-model:reason="removeReason"
          :commitments="selectedOrder.order_commitments ?? []"
          :unit="row?.output_unit"
          consequence="O lote planejado sai do dia."
        />
        <NuxtAlert
          v-if="outsized"
          color="warning"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :description="outsized"
          data-plan-outsized
          :actions="
            alertActions('warning', [
              needsDoubleCheck && { label: 'O número está certo', onClick: () => emit('acknowledge') },
            ])
          "
        />
      </div>
    </template>
    <template #footer>
      <div class="flex w-full flex-wrap items-center justify-end gap-2">
        <!-- No lugar do "Remover do plano", quem cancela; à esquerda, longe do
             "Fechar", para não ler como um botão só. -->
        <p
          v-if="!removeAllowed"
          class="op-label mr-auto text-muted-foreground"
          data-remove-hint
        >
          Cancelar lote é com o gerente.
        </p>
        <NuxtButton
          color="neutral"
          variant="outline"
          size="xl"
          label="Fechar"
          @click="emit('cancel')"
        />
        <NuxtButton
          v-if="removeAllowed"
          size="xl"
          :disabled="
            !qty.trim() ||
            !qtyValid ||
            !actionAllowed ||
            submitting ||
            needsDoubleCheck ||
            (removes && !removeReason.trim()) ||
            (!!row?.planned_orders.length && !selectedOrder)
          "
          aria-keyshortcuts="Enter"
          :color="removes ? 'error' : undefined"
          :label="
            submitting
              ? 'Confirmando…'
              : removes
                ? 'Remover do plano'
                : mode === 'new-batch'
                  ? 'Confirmar novo lote'
                  : 'Confirmar'
          "
          @click="emit('confirm')"
        />
      </div>
    </template>
  </NuxtModal>
</template>
