<script setup lang="ts">
const colorMode = useColorMode();
const sonnerTheme = computed(() => colorMode.value === "dark" ? "dark" : "light");
</script>

<template>
  <Toaster
    class="toaster group"
    position="top-center"
    rich-colors
    :visible-toasts="3"
    close-button
    :duration="7000"
    :theme="sonnerTheme"
    :style="{
      '--normal-bg': 'var(--popover)',
      '--normal-text': 'var(--popover-foreground)',
      '--normal-border': 'var(--border)',
      '--success-bg': 'var(--success)',
      '--success-text': 'var(--success-foreground)',
      '--success-border': 'var(--success)',
      '--error-bg': 'var(--destructive)',
      '--error-text': 'var(--destructive-foreground)',
      '--error-border': 'var(--destructive)',
      '--warning-bg': 'var(--warning)',
      '--warning-text': 'var(--warning-foreground)',
      '--warning-border': 'var(--warning)',
    }"
    :toast-options="{
      class: 'items-start!',
      classes: {
        icon: 'mt-0.5',
        toast: 'group toast group-[.toaster]:shadow-lg',
        actionButton: 'group-[.toast]:bg-background/20 group-[.toast]:text-current group-[.toast]:font-semibold',
        cancelButton: 'group-[.toast]:bg-background/20 group-[.toast]:text-current',
      },
    }"
  />
</template>
