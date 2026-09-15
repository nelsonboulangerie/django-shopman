<script setup lang="ts">
import type { PwaCopyProjection } from '~/types/shopman'

defineProps<{ copy: PwaCopyProjection }>()
</script>

<template>
  <div class="space-y-4 p-4">
    <p class="text-sm text-muted-foreground">{{ copy.ios_message.message }}</p>
    <ol class="grid gap-3 sm:grid-cols-2">
      <li class="rounded-lg border bg-muted/40 p-4">
        <img
          src="/pwa/ios-share-step.svg"
          :alt="copy.ios_share_step.message"
          class="mx-auto aspect-[4/3] w-full max-w-56"
          width="320"
          height="240"
        >
        <p class="mt-2 text-sm font-semibold">1. {{ copy.ios_share_step.message }}</p>
      </li>
      <li class="rounded-lg border bg-muted/40 p-4">
        <img
          src="/pwa/ios-add-step.svg"
          :alt="copy.ios_add_step.message"
          class="mx-auto aspect-[4/3] w-full max-w-56"
          width="320"
          height="240"
        >
        <p class="mt-2 text-sm font-semibold">2. {{ copy.ios_add_step.message }}</p>
      </li>
    </ol>
  </div>
</template>
