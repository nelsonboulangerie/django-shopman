<script setup lang="ts">
defineProps<{
  cancellationNotice?: string;
  paymentSummary?: readonly string[];
  operationSummary?: readonly string[];
}>();
</script>

<template>
  <div
    v-if="
      cancellationNotice || paymentSummary?.length || operationSummary?.length
    "
    class="contents"
    data-ifood-summary
  >
    <!-- Mesmo desenho das outras linhas do resumo (ícone + texto muted, text-sm do
         grid pai); o Alert ganha respiro para não colar nas linhas (dono, 08/10/2026). -->
    <NuxtAlert
      v-if="cancellationNotice"
      class="my-2"
      color="warning"
      variant="subtle"
      icon="i-lucide-triangle-alert"
      :description="cancellationNotice"
      data-ifood-cancellation
    />
    <p
      v-for="(line, index) in paymentSummary"
      :key="index"
      class="flex items-center gap-2 text-muted-foreground"
      data-ifood-payment
    >
      <Icon name="lucide:credit-card" class="size-4 shrink-0" />
      {{ line }}
    </p>
    <p
      v-for="(line, index) in operationSummary"
      :key="`operation-${index}`"
      class="flex items-center gap-2 text-muted-foreground"
      data-ifood-operation
    >
      <Icon name="lucide:bike" class="size-4 shrink-0" />
      {{ line }}
    </p>
  </div>
</template>
