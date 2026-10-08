<script setup lang="ts">
// A barra canônica que os apps montam: camada fina sobre o
// NuxtDashboardToolbar oficial. O ledger (scripts/check_operator_component_ledger.py)
// proíbe a estrutura do Nuxt UI direto nos apps; esta peça é a porta.
// Sem pele própria: a cor vem do tema (app.config.ts, dashboardToolbar.slots.root).
// Os atributos (class, data-*, aria-*) caem no elemento raiz pelo repasse
// padrão do Vue, que o DashboardToolbar entrega ao Primitive.
withDefaults(defineProps<{ as?: "div" | "header" | "footer" }>(), {
  as: "div",
});

defineSlots<{
  default?: () => unknown;
  left?: () => unknown;
  right?: () => unknown;
}>();
</script>

<template>
  <NuxtDashboardToolbar :as="as" data-operator-toolbar>
    <!-- O slot padrão do oficial substitui left/right; só o repassamos
         quando o app o usa, para não apagar as duas colunas. -->
    <template v-if="$slots.default" #default><slot /></template>
    <template #left><slot name="left" /></template>
    <template #right><slot name="right" /></template>
  </NuxtDashboardToolbar>
</template>
