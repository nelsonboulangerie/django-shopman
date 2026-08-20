<script setup lang="ts">
// Cancelar uma venda fechada é EXCEÇÃO auditada (anti-fraude), não fluxo do
// operador: confirmação destrutiva + desafio gerencial num só diálogo.
//
// ⚠️ A identificação vem do `OperatorIdentify` do operator-kit — a MESMA peça da
// tela de bloqueio e do `PosManagerAuthDialog`. Este era o TERCEIRO componente
// desenhando lista + teclado por conta própria, e o terceiro em que o crachá do
// gerente não valia: quem tem o crachá no pescoço digitava o nome à mão.
//
// A lista de gerentes é a mesma do `PosManagerAuthDialog`; vazia, cai no campo
// de nome, que é a única porta quando ninguém foi provisionado.
import type { POSManagerProjection } from "~/types/pos";

const props = defineProps<{
  open: boolean;
  orderRef: string;
  reason: string;
  maxAgeMinutes?: number;
  managers?: POSManagerProjection[];
  busy?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  "update:reason": [string];
  confirm: [string, string];
  confirmBadge: [string];
}>();

const identify = ref<{ reset: (keepPicked?: boolean) => void } | null>(null);
const managers = computed(() => props.managers ?? []);

watch(() => props.open, (open) => {
  if (open) identify.value?.reset();
});

function onPin(payload: { username: string; pin: string }) {
  if (props.busy || !payload.username || !payload.pin) return;
  emit("confirm", payload.username, payload.pin);
}

function onBadge(token: string) {
  if (props.busy) return;
  emit("confirmBadge", token);
}
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader class="items-center text-center">
        <div class="mx-auto grid size-12 place-items-center rounded-md border border-destructive/40 bg-destructive/10 text-destructive">
          <Icon name="lucide:rotate-ccw" class="size-6" />
        </div>
        <UiDialogTitle class="text-lg">Cancelar venda</UiDialogTitle>
        <UiDialogDescription>
          O pedido {{ orderRef }} será cancelado. Esta operação exige a autorização de um gerente.
          <template v-if="maxAgeMinutes">
            Disponível por até {{ maxAgeMinutes }} minutos após a venda; depois, cancele pelo gestor.
          </template>
        </UiDialogDescription>
      </UiDialogHeader>

      <div class="flex flex-col items-center gap-4 pb-1">
        <UiInput
          :model-value="reason"
          placeholder="Motivo do cancelamento (opcional)"
          autocomplete="off"
          class="h-11 w-full text-center text-base"
          @update:model-value="(value) => emit('update:reason', String(value))"
        />
        <OperatorIdentify
          ref="identify"
          :people="managers"
          :busy="busy"
          :error="error"
          :badge-enabled="open"
          allow-typed-name
          name-label="Nome do gerente"
          prompt="Quem autoriza?"
          change-label="Trocar gerente"
          @pin="onPin"
          @badge="onBadge"
        />
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
