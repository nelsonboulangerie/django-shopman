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
    class="space-y-1 text-xs"
    data-ifood-summary
  >
    <NuxtAlert
      v-if="cancellationNotice"
      color="warning"
      variant="subtle"
      icon="i-lucide-triangle-alert"
      :description="cancellationNotice"
      data-ifood-cancellation
    />
    <p
      v-for="(line, index) in paymentSummary"
      :key="index"
      class="text-muted-foreground"
      data-ifood-payment
    >
      {{ line }}
    </p>
    <p
      v-for="(line, index) in operationSummary"
      :key="`operation-${index}`"
      class="text-muted-foreground"
      data-ifood-operation
    >
      {{ line }}
    </p>
  </div>
</template>
