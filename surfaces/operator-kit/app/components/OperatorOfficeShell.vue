<script setup lang="ts">
const navigationOpen = ref(false);
defineExpose({
  closeNavigation: () => {
    navigationOpen.value = false;
  },
});
withDefaults(
  defineProps<{
    storageKey: string;
    title?: string;
    /**
     * Rail fixo da suíte: `DashboardSidebar` em px, sem redimensionar nem colapsar.
     * O padrão (`false`) é o painel percentual de escritório.
     */
    rail?: boolean;
    /** Renderiza a navbar do Dashboard. `false` deixa a página dona do próprio cabeçalho (transição). */
    navbar?: boolean;
    /** Largura do rail (px). 64 = 4rem, o piso oficial do DashboardSidebar (min-w-16). */
    sidebarSize?: number;
    sidebarDefaultSize?: number;
    sidebarMinSize?: number;
    sidebarMaxSize?: number;
  }>(),
  {
    rail: false,
    navbar: true,
    sidebarSize: 64,
    sidebarDefaultSize: 18,
    sidebarMinSize: 14,
    sidebarMaxSize: 24,
  },
);
</script>

<template>
  <NuxtDashboardGroup
    :storage-key="storageKey"
    :unit="rail ? 'px' : '%'"
    class="min-h-dvh"
    data-operator-office-shell
  >
    <NuxtDashboardSidebar
      :id="`${storageKey}-navigation`"
      v-model:open="navigationOpen"
      role="complementary"
      aria-label="Navegação do aplicativo"
      :default-size="rail ? sidebarSize : sidebarDefaultSize"
      :min-size="rail ? sidebarSize : sidebarMinSize"
      :max-size="rail ? sidebarSize : sidebarMaxSize"
      :resizable="!rail"
      :collapsible="!rail"
      :toggle="!rail"
      :ui="
        rail
          ? {
              // O rail fixo é a MESMA sidebar canônica do catálogo (superfície
              // neutra, rótulos escuros). Não sobrescrevemos a paleta: só a
              // arrumação da coluna de 64px (itens centrados, collapsed labels).
              header: 'px-0 justify-center',
              body: 'items-center gap-1 px-0',
              footer: 'flex-col items-center gap-1 px-0',
            }
          : undefined
      "
    >
      <template v-if="$slots['sidebar-header']" #header="{ collapsed }"
        ><slot name="sidebar-header" :collapsed="collapsed"
      /></template>
      <template v-if="$slots['sidebar-footer']" #footer="{ collapsed }"
        ><slot name="sidebar-footer" :collapsed="collapsed"
      /></template>
      <template #default="{ collapsed }"
        ><slot name="sidebar" :collapsed="collapsed"
      /></template>
    </NuxtDashboardSidebar>
    <slot name="search" />
    <NuxtDashboardPanel
      :id="`${storageKey}-content`"
      class="min-w-0"
      :ui="{ body: 'p-0 sm:p-0 gap-0' }"
    >
      <template v-if="navbar" #header>
        <NuxtDashboardNavbar
          as="header"
          class="h-auto min-h-[var(--op-header-min-height)] py-2"
          :title="title"
          :ui="{ title: 'whitespace-normal break-words', root: 'flex-wrap' }"
        >
          <template v-if="!rail" #leading><NuxtDashboardSidebarCollapse /></template>
          <template v-if="$slots.navbar" #title><slot name="navbar" /></template>
          <template #right><slot name="navbar-actions" /></template>
        </NuxtDashboardNavbar>
        <NuxtDashboardToolbar v-if="$slots.toolbar">
          <slot name="toolbar" />
        </NuxtDashboardToolbar>
      </template>
      <template #body>
        <slot />
      </template>
    </NuxtDashboardPanel>
  </NuxtDashboardGroup>
</template>
