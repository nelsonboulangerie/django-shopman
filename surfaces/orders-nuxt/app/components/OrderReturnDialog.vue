<script setup lang="ts">
// Registrar devolução (WP-G12, decisão 2 do dono, 17/11/2026): o que volta, quanto
// e por quê. O valor que volta e o destino do dinheiro estão escritos ANTES de
// confirmar; o gerente assina depois, com o PIN, no `OperatorManagerAuth` de sempre
// (escolhido da lista, nunca digitado). O dinheiro volta pelo caminho que já existe
// para cada meio: o gateway estorna sozinho, dinheiro e maquininha ficam pendentes
// no PDV. Este diálogo nunca pergunta forma de pagamento nem troco.
//
// A régua é do servidor: a prévia (`return/preview/`) diz se o pedido aceita
// devolução, o que ainda pode voltar de cada item e o preço pago de cada unidade.
import {
  clampReturnQty,
  lineRefundQ,
  returnLineHint,
  returnMoneySentence,
  returnRefundQ,
  returnSubmitItems,
  type OrderReturnPreview,
  type ReturnQuantities,
} from "~/presentation/orderReturn";
import type { Action } from "~/generated/ordersContract";
import { formatBRL } from "../../../operator-kit/app/utils/money";

const props = defineProps<{
  open: boolean;
  orderRef: string;
  busy: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [
    payload: {
      items: { line_id: string; qty: string }[];
      reason: string;
      contract: Action;
      moneySentence: string;
    },
  ];
}>();

const preview = ref<OrderReturnPreview | null>(null);
const loading = ref(false);
const loadError = ref("");
const qtys = ref<ReturnQuantities>({});
const reason = ref("");

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    preview.value = await $fetch<OrderReturnPreview>(
      `/api/v1/backstage/orders/${encodeURIComponent(props.orderRef)}/return/preview/`,
    );
  } catch (error) {
    preview.value = null;
    loadError.value = httpErrorMessage(
      error,
      "Não deu para ler o que pode voltar.",
    );
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    qtys.value = {};
    reason.value = "";
    void load();
  },
  { immediate: true },
);

const lines = computed(() =>
  (preview.value?.lines ?? []).filter((line) => Number(line.returnable_qty) > 0),
);
const totalQ = computed(() => returnRefundQ(lines.value, qtys.value));
const items = computed(() => returnSubmitItems(lines.value, qtys.value));
const moneySentence = computed(() =>
  preview.value ? returnMoneySentence(preview.value, totalQ.value) : "",
);
const canConfirm = computed(
  () =>
    Boolean(preview.value?.allowed) &&
    items.value.length > 0 &&
    reason.value.trim().length > 0 &&
    !props.busy,
);

function setQty(lineId: string, value: number | null | undefined) {
  const line = lines.value.find((item) => item.line_id === lineId);
  if (!line) return;
  qtys.value = { ...qtys.value, [lineId]: clampReturnQty(line, value) };
}

function returnEverything() {
  qtys.value = Object.fromEntries(
    lines.value.map((line) => [line.line_id, Number(line.returnable_qty)]),
  );
}

function confirm() {
  if (!canConfirm.value || !preview.value) return;
  emit("confirm", {
    items: items.value,
    reason: reason.value.trim(),
    contract: preview.value.action,
    moneySentence: moneySentence.value,
  });
}
</script>

<template>
  <NuxtModal
    :open="open"
    title="Registrar devolução"
    description="Escolha o que volta, quanto e o motivo. Um gerente autoriza com o PIN."
    data-order-return-dialog
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <template #body>
      <OperatorScreenState
        v-if="loading && !preview"
        state="loading"
        what="o que pode voltar"
        in-card
      />
      <OperatorScreenState
        v-else-if="loadError"
        state="error"
        what="o que pode voltar"
        :description="loadError"
        in-card
        data-return-load-error
        @retry="load"
      />
      <p
        v-else-if="preview && !preview.allowed"
        class="text-sm"
        data-return-block
      >
        {{ preview.block_reason }}
      </p>
      <div v-else-if="preview" class="flex flex-col gap-4">
        <div class="flex items-center justify-between gap-2">
          <p class="text-sm font-medium">O que volta</p>
          <NuxtButton
            label="Devolver tudo"
            color="neutral"
            variant="outline"
            data-return-everything
            @click="returnEverything"
          />
        </div>
        <ul class="flex flex-col gap-3" data-return-lines>
          <li
            v-for="line in lines"
            :key="line.line_id"
            class="flex flex-wrap items-center justify-between gap-2"
            :data-return-line="line.line_id"
          >
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium">{{ line.name }}</p>
              <p class="text-xs text-muted">
                {{ returnLineHint(line) }} · {{ line.unit_refund_display }} cada
              </p>
            </div>
            <div class="flex items-center gap-2">
              <NuxtInputNumber
                :model-value="qtys[line.line_id] ?? 0"
                class="w-32"
                :min="0"
                :max="Number(line.returnable_qty)"
                :step="line.by_weight ? 0.05 : 1"
                :aria-label="`Quanto volta de ${line.name}`"
                :data-return-qty="line.line_id"
                @update:model-value="(value: number | null) => setQty(line.line_id, value)"
              />
              <span class="w-20 text-right text-sm tabular-nums">
                {{ formatBRL(lineRefundQ(line, qtys[line.line_id] ?? 0)) }}
              </span>
            </div>
          </li>
        </ul>
        <NuxtFormField label="Motivo" required>
          <NuxtTextarea
            v-model="reason"
            :rows="2"
            class="w-full"
            placeholder="Ex.: croissant cru por dentro"
            data-return-reason
          />
        </NuxtFormField>
        <p
          class="flex items-start gap-2 rounded-md bg-elevated p-3 text-sm font-medium"
          aria-live="polite"
          data-return-money
        >
          <NuxtIcon name="i-lucide-banknote" class="mt-0.5 size-4 shrink-0" />
          <span>{{ moneySentence }}</span>
        </p>
      </div>
    </template>
    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <NuxtButton
          label="Voltar"
          color="neutral"
          variant="outline"
          @click="emit('update:open', false)"
        />
        <NuxtButton
          v-if="preview?.allowed"
          label="Registrar devolução"
          color="error"
          :disabled="!canConfirm"
          :loading="busy"
          data-return-confirm
          @click="confirm"
        />
      </div>
    </template>
  </NuxtModal>
</template>
