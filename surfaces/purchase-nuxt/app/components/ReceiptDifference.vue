<script setup lang="ts">
import type { ReceiptLinePreview } from "~/types/purchase";
import {
  RECEIPT_DIFFERENCE_REASONS,
  formatQty,
  receiptDifferenceConsequence,
  receiptLineDifference,
} from "~/presentation/purchase";

/**
 * O item que não bate com a nota: nota × chegou × diferença, lado a lado, o
 * motivo de lista curta e o que acontece ao confirmar.
 *
 * Só aparece quando há diferença. O motivo grava na ocorrência da linha, que é o
 * que o servidor já guarda no lote e no movimento; sem motivo, a entrada não sai
 * (`receipt_difference_reason_required`).
 */
const props = defineProps<{ preview: ReceiptLinePreview }>();
const emit = defineEmits<{ reason: [reason: string] }>();

const difference = computed(() => receiptLineDifference(props.preview.line));
const unit = computed(() => props.preview.purchaseUnitLabel || props.preview.material.unit);
const consequence = computed(() => receiptDifferenceConsequence(props.preview));
const reasonOptions = RECEIPT_DIFFERENCE_REASONS.map((reason) => ({ value: reason, label: reason }));
type DifferenceReason = (typeof RECEIPT_DIFFERENCE_REASONS)[number];
const chosen = computed<DifferenceReason | undefined>(() => {
  const note = props.preview.line.lineNote.trim();
  return RECEIPT_DIFFERENCE_REASONS.find((reason) => reason === note);
});

function signed(value: number): string {
  const text = formatQty(Math.abs(value), unit.value);
  return value < 0 ? `−${text}` : `+${text}`;
}
</script>

<template>
  <NuxtCard v-if="difference" variant="soft" data-receipt-difference>
    <div class="space-y-3">
      <dl class="grid grid-cols-3 overflow-hidden rounded-md border border-border bg-card text-center">
        <div class="p-2">
          <dt class="text-xs text-muted-foreground">Nota</dt>
          <dd class="mt-0.5 text-base font-semibold tabular-nums">{{ formatQty(difference.invoiceQty, unit) }}</dd>
        </div>
        <div class="border-x border-border p-2">
          <dt class="text-xs font-semibold text-warning">Chegou</dt>
          <dd class="mt-0.5 text-base font-semibold tabular-nums">{{ formatQty(difference.arrivedQty, unit) }}</dd>
        </div>
        <div class="p-2">
          <dt class="text-xs text-muted-foreground">Diferença</dt>
          <dd class="mt-0.5 text-base font-semibold tabular-nums" :class="difference.difference < 0 ? 'text-destructive' : 'text-warning'">
            {{ signed(difference.difference) }}
          </dd>
        </div>
      </dl>
      <NuxtRadioGroup
        legend="Por quê?"
        variant="card"
        :model-value="chosen"
        :items="reasonOptions"
        data-receipt-difference-reason
        @update:model-value="emit('reason', String($event))"
      />
      <p v-if="consequence" class="flex items-start gap-1.5 text-xs text-muted-foreground">
        <Icon name="lucide:send" class="mt-0.5 size-3.5 shrink-0" />
        {{ consequence }}
      </p>
    </div>
  </NuxtCard>
</template>
