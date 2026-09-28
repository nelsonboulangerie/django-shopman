<script setup lang="ts">
defineProps<{
  open: boolean;
  title: string;
  description: string;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
}>();
</script>

<template>
  <UiDialog :open="open" @update:open="emit('update:open', $event)">
    <UiDialogContent
      class="flex h-dvh max-h-dvh w-screen max-w-none flex-col gap-0 overflow-hidden rounded-none border-0 p-0 sm:h-[min(900px,calc(100dvh-3rem))] sm:max-h-[calc(100dvh-3rem)] sm:w-[min(1280px,calc(100vw-3rem))] sm:max-w-[min(1280px,calc(100vw-3rem))] sm:rounded-2xl sm:border"
    >
      <UiDialogHeader
        class="shrink-0 border-b border-border bg-card px-4 py-4 pr-14 text-left sm:px-6 sm:py-5 sm:pr-16"
      >
        <UiDialogTitle class="text-lg sm:text-xl">{{ title }}</UiDialogTitle>
        <UiDialogDescription class="max-w-3xl">
          {{ description }}
        </UiDialogDescription>
      </UiDialogHeader>

      <div class="min-h-0 overflow-y-auto overscroll-contain bg-background/40">
        <div class="mx-auto w-full max-w-6xl p-4 sm:p-6 lg:p-8">
          <slot />
        </div>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
