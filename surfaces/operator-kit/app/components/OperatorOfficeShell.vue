<script setup lang="ts">
withDefaults(defineProps<{
  storageKey: string;
  sidebarDefaultSize?: number;
  sidebarMinSize?: number;
  sidebarMaxSize?: number;
}>(), {
  sidebarDefaultSize: 18,
  sidebarMinSize: 14,
  sidebarMaxSize: 24,
});
</script>

<template>
  <NuxtDashboardGroup :storage-key="storageKey" class="min-h-dvh" data-operator-office-shell>
    <NuxtDashboardSidebar
      :default-size="sidebarDefaultSize"
      :min-size="sidebarMinSize"
      :max-size="sidebarMaxSize"
      resizable
    >
      <slot name="sidebar" />
    </NuxtDashboardSidebar>
    <NuxtDashboardPanel class="min-w-0">
      <template #header>
        <NuxtDashboardNavbar>
          <slot name="navbar" />
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
