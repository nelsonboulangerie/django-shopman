<script setup lang="ts">
// Estornar UM pedido (#2727, item 5): a exceção financeira do Gerente. O diálogo lê a
// prévia (`refund/preview/`) a cada abertura e mostra os valores DESTA cobrança: o
// que foi pago, o que já voltou e o que ainda pode voltar. O valor vem com o
// disponível inteiro; parcial vale. A segunda confirmação é a mesma marca do diálogo
// do Admin ("Confirmo o estorno, que não tem desfazer"): sem ela, o botão não acende.
import {
  initialRefundAmount,
  refundDialogView,
  type OrderRefundPreview,
} from "~/presentation/orderRefund";
import type { Action } from "~/generated/ordersContract";

const props = defineProps<{
  open: boolean;
  orderRef: string;
  busy: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [payload: { contract: Action; amountQ: number }];
}>();

const preview = ref<OrderRefundPreview | null>(null);
const loading = ref(false);
const loadError = ref("");
const amount = ref("");
const confirmed = ref(false);

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    preview.value = await $fetch<OrderRefundPreview>(
      `/api/v1/backstage/orders/${encodeURIComponent(props.orderRef)}/refund/preview/`,
    );
    amount.value = initialRefundAmount(preview.value);
  } catch (error) {
    preview.value = null;
    loadError.value = httpErrorMessage(
      error,
      "Não deu para ler o valor desta cobrança.",
    );
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    // Cada abertura lê de novo: outro estorno pode ter mudado o disponível.
    preview.value = null;
    confirmed.value = false;
    void load();
  },
  { immediate: true },
);

const view = computed(() =>
  preview.value
    ? refundDialogView(preview.value, {
        amount: amount.value,
        confirmed: confirmed.value,
        busy: props.busy,
      })
    : null,
);

function confirm() {
  const contract = preview.value?.action;
  if (!view.value?.canConfirm || !contract || !view.value.amountQ) return;
  emit("confirm", { contract, amountQ: view.value.amountQ });
}
</script>

<template>
  <NuxtModal
    :open="open"
    title="Estornar"
    data-order-refund-dialog
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <template #body>
      <p class="mb-4 text-sm text-muted" data-refund-instructions>
        O dinheiro volta ao cliente pelo mesmo meio do pagamento. No Pix, volta em
        instantes; no cartão, aparece na fatura em alguns dias, conforme o banco do
        cartão. Não há desfazer.
      </p>
      <OperatorScreenState
        v-if="loading && !preview"
        state="loading"
        what="o valor desta cobrança"
        in-card
      />
      <OperatorScreenState
        v-else-if="loadError"
        state="error"
        what="o valor desta cobrança"
        :description="loadError"
        in-card
        data-refund-load-error
        @retry="load"
      />
      <p v-else-if="view?.blocked" class="text-sm" data-refund-block>
        {{ view.blockReason }}
      </p>
      <div v-else-if="view" class="flex flex-col gap-4">
        <ul
          class="flex flex-col gap-1 rounded-md bg-elevated p-3 text-sm"
          data-refund-values
        >
          <li data-refund-paid>{{ view.paidLine }}</li>
          <li v-if="view.returnedLine" data-refund-returned>
            {{ view.returnedLine }}
          </li>
          <li class="font-medium" data-refund-available>
            {{ view.availableLine }}
          </li>
        </ul>
        <NuxtFormField
          label="Valor a estornar"
          :error="amount ? view.amountError || false : false"
          data-refund-amount
        >
          <NuxtInput
            v-model="amount"
            class="w-full"
            type="text"
            inputmode="decimal"
            :disabled="!view.partialAllowed"
            aria-label="Valor a estornar"
          />
        </NuxtFormField>
        <NuxtCheckbox
          v-model="confirmed"
          label="Confirmo o estorno, que não tem desfazer"
          data-refund-confirm-check
        />
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
          v-if="view && !view.blocked"
          :label="view.confirmLabel"
          color="error"
          :disabled="!view.canConfirm"
          :loading="busy"
          data-refund-confirm
          @click="confirm"
        />
      </div>
    </template>
  </NuxtModal>
</template>
