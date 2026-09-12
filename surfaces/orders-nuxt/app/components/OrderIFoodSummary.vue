<script setup lang="ts">
defineProps<{ cancellationNotice?: string; paymentSummary?: readonly string[] }>();
</script>

<template>
  <div v-if="cancellationNotice || paymentSummary?.length" class="space-y-1 text-xs" data-ifood-summary>
    <p v-if="cancellationNotice" class="rounded-md border border-warning/40 bg-warning/10 p-2" role="status" data-ifood-cancellation>
      {{ cancellationNotice }}
    </p>
    <p v-for="(line, index) in paymentSummary" :key="index" class="text-muted-foreground" data-ifood-payment>
      {{ line }}
    </p>
  </div>
</template>
