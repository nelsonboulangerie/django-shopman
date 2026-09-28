<script setup lang="ts">
// "Salvar alterações" da encomenda — a prévia ANTES de gravar (WP-E6).
//
// O servidor calculou tudo (`order_edit.plan`): o total novo, a diferença e o que
// acontece com ela. Aqui a tela só diz, sem o operador precisar completar
// sentido: quanto fica, quem paga ou quem devolve, onde — e a frase que o
// cliente vai receber. Encomenda paga que fica mais barata pede o PIN de um
// gerente, que sobe por cima deste diálogo (na página).
import type { DeliveryPaymentMethod } from "~/presentation/orderEdit";
import { DELIVERY_PAYMENT_METHODS, orderEditSettlementLine, orderEditTotalLine } from "~/presentation/orderEdit";
import type { OrderEditPreview } from "~/types/preorders";

const props = defineProps<{
  open: boolean;
  orderRef: string;
  preview: OrderEditPreview | null;
  busy?: boolean;
  error?: string;
  needsPaymentMethod?: boolean;
  deliveryPaymentMethod?: DeliveryPaymentMethod | "";
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  "update:deliveryPaymentMethod": [DeliveryPaymentMethod];
  confirm: [];
  retry: [];
}>();

const totalLine = computed(() => (props.preview ? orderEditTotalLine(props.preview) : ""));
const settlementLine = computed(() => (props.preview ? orderEditSettlementLine(props.preview) : ""));
const nothingChanged = computed(() => Boolean(props.preview && !props.preview.changed));

function pickMethod(method: DeliveryPaymentMethod) {
  emit("update:deliveryPaymentMethod", method);
  emit("retry");
}
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg" data-order-edit-review>
      <UiDialogHeader>
        <UiDialogTitle>Salvar as alterações da encomenda {{ orderRef }}?</UiDialogTitle>
        <UiDialogDescription>Confira o valor e o que acontece com a diferença antes de confirmar.</UiDialogDescription>
      </UiDialogHeader>

      <p v-if="busy && !preview && !error" class="flex items-center gap-2 text-sm text-muted-foreground">
        <Icon name="line-md:loading-loop" class="size-4" /> Calculando as alterações…
      </p>

      <p
        v-if="error"
        class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
        role="alert"
        data-order-edit-error
      >
        <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
        <span>{{ error }}</span>
      </p>

      <!-- Retirada que vira entrega com saldo: o entregador recebe na porta, e a
           tela precisa saber em quê. -->
      <div v-if="needsPaymentMethod" class="grid gap-2" data-order-edit-payment-method>
        <p class="text-sm font-medium">Como o entregador recebe o que falta?</p>
        <div class="grid grid-cols-3 gap-2">
          <UiButton
            v-for="option in DELIVERY_PAYMENT_METHODS"
            :key="option.key"
            type="button"
            :variant="deliveryPaymentMethod === option.key ? 'default' : 'outline'"
            :disabled="busy"
            :data-order-edit-method="option.key"
            @click="pickMethod(option.key)"
          >
            {{ option.label }}
          </UiButton>
        </div>
      </div>

      <template v-if="preview">
        <p v-if="nothingChanged" class="text-sm text-muted-foreground" data-order-edit-nothing>
          Nada mudou nesta encomenda.
        </p>
        <section v-else class="grid gap-3">
          <p class="text-base font-semibold tabular-nums" data-order-edit-total>{{ totalLine }}</p>
          <p
            class="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-sm"
            data-order-edit-settlement
          >
            <Icon name="lucide:hand-coins" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <span>{{ settlementLine }}</span>
          </p>
          <p v-if="preview.requires_manager_approval" class="text-sm text-muted-foreground">
            Encomenda paga que fica mais barata: um gerente autoriza a devolução.
          </p>
          <div class="grid gap-1">
            <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">O cliente recebe</p>
            <p class="rounded-md border border-border p-3 text-sm" data-order-edit-customer-note>
              {{ preview.customer_note }}.
            </p>
          </div>
        </section>
      </template>

      <UiDialogFooter>
        <UiButton type="button" variant="outline" @click="emit('update:open', false)">Voltar à edição</UiButton>
        <UiButton
          type="button"
          :disabled="busy || !preview || nothingChanged"
          :loading="busy && !!preview"
          data-order-edit-confirm
          @click="emit('confirm')"
        >
          Confirmar alterações
        </UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
