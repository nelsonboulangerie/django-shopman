<script setup lang="ts">
// Menu do rail da suíte (categoria 2): o app não monta o NavigationMenu canônico
// diretamente (o gate do ledger exige a anatomia no kit). Itens/tema vêm do dono.
import type { NavigationMenuItem, NavigationMenuProps } from "@nuxt/ui";

defineProps<{ items: NavigationMenuItem[]; ui?: NavigationMenuProps["ui"]; label: string }>();
</script>

<template>
  <NuxtNavigationMenu
    orientation="vertical"
    collapsed
    :items="items"
    :ui="ui"
    :aria-label="label"
    class="w-full"
  />
</template>
