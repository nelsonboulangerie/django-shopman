<script setup lang="ts">
// Cancelar uma encomenda pelo PDV. A régua, a política e a permissão são as do
// Gestor (a rota é a mesma); aqui o operador confirma e, se quiser, escreve o
// motivo que vai para o cliente. Pedido pago pede o PIN de um gerente, que sobe
// por cima deste diálogo (`OperatorManagerAuth`, na página) — o motivo digitado
// fica.
const props = defineProps<{
  open: boolean;
  customerName: string;
  requiresApproval: boolean;
  busy?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  confirm: [string];
}>();

const reason = ref("");
watch(() => props.open, (open) => { if (open) reason.value = ""; });

function confirm() {
  if (props.busy) return;
  emit("confirm", reason.value);
}
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent class="sm:max-w-md" data-preorder-cancel-dialog>
      <UiDialogHeader>
        <UiDialogTitle>Cancelar a encomenda de {{ customerName }}?</UiDialogTitle>
        <UiDialogDescription>
          O que já foi pago volta no mesmo meio. Devolução em dinheiro aparece na Sessão de caixa, em Precisa de você.
          <template v-if="requiresApproval"> Encomenda paga: um gerente precisa autorizar.</template>
        </UiDialogDescription>
      </UiDialogHeader>

      <form class="grid gap-4" @submit.prevent="confirm">
        <label class="grid gap-1.5">
          <span class="text-sm font-medium">Motivo para o cliente (opcional)</span>
          <UiInput v-model="reason" autocomplete="off" class="h-11 text-base" :maxlength="200" data-preorder-cancel-reason />
        </label>
        <UiDialogFooter>
          <UiButton type="button" variant="outline" @click="emit('update:open', false)">Voltar</UiButton>
          <UiButton type="submit" variant="destructive" :disabled="busy" :loading="busy" data-preorder-cancel-confirm>
            Cancelar encomenda
          </UiButton>
        </UiDialogFooter>
      </form>
    </UiDialogContent>
  </UiDialog>
</template>
