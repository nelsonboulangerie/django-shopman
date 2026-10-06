<script setup lang="ts">
withDefaults(defineProps<{ scrollBody?: boolean }>(), { scrollBody: true });
</script>

<template>
  <NuxtApp :scroll-body="scrollBody" :toaster="{ position: 'top-right' }">
    <slot />
  </NuxtApp>
</template>
