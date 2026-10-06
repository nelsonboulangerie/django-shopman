<script setup lang="ts">
// Bottom tab bar canônica da suíte (categoria 2): NavigationMenu com o `ui` oficial
// do padrão "With bottom tab bar". Mora no kit para toda superfície de operador herdar.
import type { NavigationMenuItem, NavigationMenuProps } from "@nuxt/ui";

defineProps<{ items: NavigationMenuItem[]; ui?: NavigationMenuProps["ui"]; label: string }>();
</script>

<template>
  <nav class="fixed inset-x-0 bottom-0 z-40 border-t border-default bg-card lg:hidden print:hidden">
    <NuxtNavigationMenu :items="items" :ui="ui" :aria-label="label" class="w-full" />
  </nav>
</template>
