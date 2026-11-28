<script setup lang="ts">
// O lote em produção (ou planejado) abre para conferência e cancelamento, sem etapas e
// sem gestão. O estado (qual linha, qual lote, se está confirmando o cancelamento)
// mora na grade (`ProductionStageGrid`); aqui só se mostra e se avisa.
import LotVoidStakes from "./LotVoidStakes.vue";
import { formatQtyUnit } from "~/presentation/production";
import type {
  ProductionActionProjection,
  ProductionKDSCardProjection,
  ProductionMatrixRowProjection,
  WorkOrderCardProjection,
} from "~/types/production";

defineProps<{
  row: ProductionMatrixRowProjection | null;
  title: string;
  description: string;
  orders: WorkOrderCardProjection[];
  selectedOrder: WorkOrderCardProjection | null;
  voidConfirming: boolean;
  /** O cancelamento está correndo: o botão fica ocupado até o servidor responder (#3393). */
  voidSubmitting: boolean;
  oldDoughAction: ProductionActionProjection | undefined;
  deviationAction: ProductionActionProjection | undefined;
  kdsCard: ProductionKDSCardProjection | undefined;
}>();

const voidReason = defineModel<string>("voidReason", { required: true });

const emit = defineEmits<{
  close: [];
  select: [pk: number];
  "ask-void": [];
  "confirm-void": [];
  "register-old-dough": [];
  "authorize-deviation": [];
}>();
</script>

<template>
  <!-- lote em produção: conferência e cancelamento, sem etapas, sem gestão -->
  <NuxtModal
    :open="row != null"
    :title="title"
    :description="description"
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
            orders.length > 1 &&
            !selectedOrder
          "
          class="grid gap-2"
        >
          <!-- O bloco do lote carrega referência e quantidade; é seleção de registro. -->
          <NuxtButton
            v-for="workOrder in orders"
            :key="workOrder.pk"
            color="neutral"
            variant="outline"
            size="xl"
            block
            :ui="{ base: 'justify-between' }"
            @click="emit('select', workOrder.pk)"
          >
            <span class="font-medium">#{{ workOrder.ref }}</span>
            <span class="tabular-nums text-muted-foreground"
              >{{ workOrder.started_qty || workOrder.planned_qty }} un.</span
            >
          </NuxtButton>
        </div>

        <div
          v-if="selectedOrder"
          class="flex flex-col gap-2"
          data-lot-summary
        >
          <p class="op-body text-muted-foreground">
            {{
              selectedOrder.started_qty
                ? "Lote em produção"
                : "Lote planejado"
            }}<template v-if="selectedOrder.started_at_display">
              · Em produção desde
              {{ selectedOrder.started_at_display }}</template
            >
          </p>
          <p class="text-3xl font-bold tabular-nums" data-lot-quantity>
            {{
              formatQtyUnit(
                selectedOrder.started_qty ||
                  selectedOrder.planned_qty,
                row?.output_unit,
              )
            }}
            {{
              selectedOrder.started_qty ? "previstas" : "planejadas"
            }}
          </p>
          <p
            v-if="selectedOrder.started_qty"
            class="op-body text-muted-foreground"
          >
            Seguem para a Finalização.
          </p>
        </div>

        <LotVoidStakes
          v-if="voidConfirming && selectedOrder"
          v-model:reason="voidReason"
          :orders="selectedOrder.promised?.orders ?? []"
          :unit="row?.output_unit"
          :consequence="
            selectedOrder.started_qty
              ? 'O lote volta atrás.'
              : 'O lote planejado sai do dia.'
          "
        />
      </div>
    </template>
    <template #footer>
      <div class="flex w-full flex-wrap gap-2">
        <NuxtButton
          v-if="selectedOrder && oldDoughAction"
          color="primary"
          variant="outline"
          icon="i-lucide-package-plus"
          label="Registrar massa velha"
          :disabled="!oldDoughAction.enabled"
          :title="oldDoughAction.reason || undefined"
          @click="emit('register-old-dough')"
        />
        <NuxtButton
          v-if="
            selectedOrder &&
            deviationAction?.enabled &&
            kdsCard?.formula_limits.length
          "
          color="primary"
          variant="outline"
          icon="i-lucide-shield-check"
          label="Autorizar desvio"
          @click="emit('authorize-deviation')"
        />
        <!-- O botão só existe para quem pode cancelar (o mesmo can_void do
             menu da linha); para os outros, a tela diz quem cancela. -->
        <NuxtButton
          v-if="selectedOrder?.can_void && !voidConfirming"
          color="error"
          variant="outline"
          label="Cancelar lote…"
          @click="emit('ask-void')"
        />
        <NuxtButton
          v-else-if="selectedOrder?.can_void"
          color="error"
          :label="voidSubmitting ? 'Cancelando…' : 'Confirmar cancelamento'"
          :loading="voidSubmitting"
          :disabled="voidSubmitting || !voidReason.trim()"
          :aria-busy="voidSubmitting"
          :title="!voidReason.trim() ? 'Escolha o motivo' : undefined"
          data-confirm-void
          @click="emit('confirm-void')"
        />
        <p
          v-else-if="selectedOrder"
          class="op-label self-center text-muted-foreground"
          data-void-hint
        >
          Cancelar lote é com o gerente.
        </p>
        <NuxtButton
          color="neutral"
          variant="outline"
          class="ml-auto"
          label="Fechar"
          @click="emit('close')"
        />
      </div>
    </template>
  </NuxtModal>
</template>
