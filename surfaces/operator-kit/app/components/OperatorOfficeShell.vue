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
    rail?: boolean;
    navbar?: boolean;
    sidebarSize?: number;
    sidebarDefaultSize?: number;
    sidebarMinSize?: number;
    sidebarMaxSize?: number;
  }>(),
  {
    rail: false,
    navbar: true,
    sidebarSize: 72,
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
    <NuxtDashboardPanel v-if="navbar" :id="`${storageKey}-content`">
      <template v-if="navbar" #header>
        <NuxtDashboardNavbar as="header" :title="title">
          <template v-if="!rail" #leading
            ><NuxtDashboardSidebarCollapse
          /></template>
          <template v-if="$slots.navbar" #title
            ><slot name="navbar"
          /></template>
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
    <!-- The DashboardPanel default slot intentionally replaces its padded,
         scrollable body. Operational apps own the header/content/footer regions
         below; wrapping that whole composition in #body creates nested scrolling
         and an inset footer. This is the official full-bleed panel composition. -->
    <NuxtDashboardPanel v-else :id="`${storageKey}-content`">
      <slot />
    </NuxtDashboardPanel>
  </NuxtDashboardGroup>
</template>
