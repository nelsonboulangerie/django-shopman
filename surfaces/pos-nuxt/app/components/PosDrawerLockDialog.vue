<script setup lang="ts">
// A trava da gaveta: o PDV não inicia a próxima venda com a gaveta aberta.
//
// Duas saídas, nada mais. "Já fechei" lê o sensor de novo (é a saída normal:
// fechou, segue). "Gerente libera" é a exceção para a gaveta emperrada — abre o
// PIN do gerente e o destrave vai para o log. Não há terceira porta, nem
// contagem regressiva: carência transformaria a exceção em rotina invisível.
//
// Este diálogo só existe quando o sensor DISSE que a gaveta está aberta. Estado
// desconhecido nunca chega aqui — a trava não age por palpite.
defineProps<{
  open: boolean;
  /** O operador disse "já fechei" e o sensor ainda vê a gaveta aberta. */
  stillOpen?: boolean;
  busy?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  recheck: [];
  manager: [];
}>();
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader class="items-center text-center">
        <div class="mx-auto grid size-12 place-items-center rounded-md border border-warning/40 bg-warning/10 text-amber-600">
          <Icon name="lucide:inbox" class="size-6" />
        </div>
        <UiDialogTitle class="text-lg">Gaveta aberta</UiDialogTitle>
        <UiDialogDescription>
          Feche a gaveta para iniciar a próxima venda.
        </UiDialogDescription>
      </UiDialogHeader>

      <div class="flex flex-col items-stretch gap-3 pb-1">
        <p v-if="stillOpen" class="text-center text-sm font-medium text-destructive" role="alert">
          A gaveta ainda está aberta.
        </p>
        <UiButton class="h-12 text-base" :disabled="busy" @click="emit('recheck')">
          <Icon name="lucide:check" class="size-5" />
          Já fechei
        </UiButton>
        <UiButton variant="outline" class="h-11" :disabled="busy" @click="emit('manager')">
          <Icon name="lucide:shield-check" class="size-4" />
          Gerente libera esta venda
        </UiButton>
        <p class="text-center text-xs text-muted-foreground">
          Se a gaveta emperrou, um gerente libera esta venda com o PIN. A liberação fica registrada.
        </p>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
