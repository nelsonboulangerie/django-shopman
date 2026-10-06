<script setup lang="ts">
import CanonicalPage from "@nuxt/ui/components/Page.vue";

defineProps<{ title: string; description?: string; headline?: string }>();
</script>

<template>
  <NuxtContainer
    class="min-w-0 px-[var(--op-page-inline-space)] py-[var(--op-page-block-space)]"
  >
    <CanonicalPage>
      <NuxtPageHeader
        :title="title"
        :description="description"
        :headline="headline"
        :ui="{
          root: 'py-0 pb-3',
          title: 'text-xl sm:text-2xl',
          description: 'mt-1 text-sm',
        }"
      >
        <template v-if="$slots.links" #links><slot name="links" /></template>
      </NuxtPageHeader>
      <NuxtPageBody class="min-w-0 mt-4 space-y-6"><slot /></NuxtPageBody>
      <template v-if="$slots.aside" #right
        ><NuxtPageAside><slot name="aside" /></NuxtPageAside
      ></template>
    </CanonicalPage>
  </NuxtContainer>
</template>
