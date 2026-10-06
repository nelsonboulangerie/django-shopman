<script setup lang="ts">
import CanonicalPage from "@nuxt/ui/components/Page.vue";

defineProps<{ title: string; description?: string; headline?: string }>();
</script>

<template>
  <NuxtContainer class="min-w-0 py-[var(--op-page-block-space)]">
    <CanonicalPage>
      <NuxtPageHeader :title="title" :description="description" :headline="headline">
        <template v-if="$slots.links" #links><slot name="links" /></template>
      </NuxtPageHeader>
      <NuxtPageBody class="min-w-0"><slot /></NuxtPageBody>
      <template v-if="$slots.aside" #right><NuxtPageAside><slot name="aside" /></NuxtPageAside></template>
    </CanonicalPage>
  </NuxtContainer>
</template>
