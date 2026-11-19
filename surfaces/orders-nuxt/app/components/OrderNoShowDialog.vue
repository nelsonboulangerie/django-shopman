<script setup lang="ts">
// Não retirado (WP-G11): o pedido pronto que o cliente não veio buscar é encerrado
// aqui. O diálogo mostra, ANTES de confirmar, o destino de cada item (volta à venda
// ou perda), o que acontece com o dinheiro e o texto que o cliente vai receber. O
// gerente assina depois, com o PIN, no `OperatorManagerAuth` de sempre (escolhido
// da lista, nunca digitado), lendo a mesma frase do dinheiro.
//
// A régua é do servidor: a prévia (`no-show/preview/`) diz se o pedido já pode ser
// encerrado, decide o destino de cada linha e escreve as frases. Aqui não há o que
// escolher: o gesto é conferir e confirmar.
import {
  noShowDialogView,
  type OrderNoShowPreview,
} from "~/presentation/orderNoShow";
import type { Action } from "~/generated/ordersContract";

const props = defineProps<{
  open: boolean;
  orderRef: string;
  busy: boolean;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [payload: { contract: Action; moneySentence: string }];
}>();

const preview = ref<OrderNoShowPreview | null>(null);
const loading = ref(false);
const loadError = ref("");

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    preview.value = await $fetch<OrderNoShowPreview>(
      `/api/v1/backstage/orders/${encodeURIComponent(props.orderRef)}/no-show/preview/`,
    );
  } catch (error) {
    preview.value = null;
    loadError.value = httpErrorMessage(
      error,
      "Não deu para ler o que acontece com o pedido.",
    );
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    // Cada abertura lê de novo: a hora, o estoque e o pagamento mudam o destino.
    preview.value = null;
    void load();
  },
  { immediate: true },
);

const view = computed(() =>
  preview.value ? noShowDialogView(preview.value, { busy: props.busy }) : null,
);

function confirm() {
  if (!view.value?.canConfirm || !preview.value) return;
  emit("confirm", {
    contract: preview.value.action,
    moneySentence: preview.value.money_sentence,
  });
}
</script>

<template>
  <NuxtModal
    :open="open"
    title="Não retirado"
    data-order-no-show-dialog
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <template #body>
      <!-- A instrução mora no corpo, não no subtítulo do cabeçalho (lá ela passa por
           baixo do X no celular), como no diálogo de devolução. -->
      <p class="mb-4 text-sm text-muted" data-no-show-instructions>
        O cliente não veio buscar. Confira o que acontece com cada item e com o
        dinheiro. Um gerente autoriza com o PIN.
      </p>
      <OperatorScreenState
        v-if="loading && !preview"
        state="loading"
        what="o que acontece com o pedido"
        in-card
      />
      <OperatorScreenState
        v-else-if="loadError"
        state="error"
        what="o que acontece com o pedido"
        :description="loadError"
        in-card
        data-no-show-load-error
        @retry="load"
      />
      <p v-else-if="view?.blocked" class="text-sm" data-no-show-block>
        {{ view.blockReason }}
      </p>
      <div v-else-if="view" class="flex flex-col gap-4">
        <div class="flex flex-col gap-3">
          <p class="text-sm font-medium">O que acontece com cada item</p>
          <ul class="flex flex-col gap-3" data-no-show-lines>
            <li
              v-for="line in view.lines"
              :key="line.id"
              class="flex flex-wrap items-start justify-between gap-2"
              :data-no-show-line="line.id"
            >
              <div class="min-w-0 flex-1">
                <p class="text-sm font-medium break-words" data-no-show-line-name>
                  {{ line.name }}
                </p>
                <p class="text-xs text-muted">
                  Quantidade: {{ line.qty }} · {{ line.value }}
                </p>
                <p
                  v-if="line.why"
                  class="text-xs text-muted"
                  data-no-show-line-why
                >
                  {{ line.why }}
                </p>
              </div>
              <NuxtBadge
                :label="line.destiny"
                :color="line.tone"
                data-no-show-line-destiny
              />
            </li>
          </ul>
        </div>
        <p
          class="flex items-start gap-2 rounded-md bg-elevated p-3 text-sm font-medium"
          data-no-show-money
        >
          <NuxtIcon name="i-lucide-banknote" class="mt-0.5 size-4 shrink-0" />
          <span>{{ view.moneySentence }}</span>
        </p>
        <div
          v-if="view.customerText"
          class="flex flex-col gap-1"
          data-no-show-customer
        >
          <p class="text-sm font-medium">Mensagem que o cliente vai receber</p>
          <p
            class="rounded-md bg-elevated p-3 text-sm whitespace-pre-line"
            data-no-show-customer-text
          >
            {{ view.customerText }}
          </p>
        </div>
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
          data-no-show-confirm
          @click="confirm"
        />
      </div>
    </template>
  </NuxtModal>
</template>
