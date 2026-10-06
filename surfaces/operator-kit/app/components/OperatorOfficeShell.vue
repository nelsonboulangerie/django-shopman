<script setup lang="ts">
withDefaults(
  defineProps<{
    storageKey: string;
    sidebarDefaultSize?: number;
    sidebarMinSize?: number;
    sidebarMaxSize?: number;
  }>(),
  {
    sidebarDefaultSize: 18,
    sidebarMinSize: 14,
    sidebarMaxSize: 24,
  },
);
</script>

<template>
  <NuxtDashboardGroup
    :storage-key="storageKey"
    class="min-h-dvh"
    data-operator-office-shell
  >
    <NuxtDashboardSidebar
      :default-size="sidebarDefaultSize"
      :min-size="sidebarMinSize"
      :max-size="sidebarMaxSize"
      resizable
    >
      <template v-if="$slots['sidebar-header']" #header
        ><slot name="sidebar-header"
      /></template>
      <slot name="sidebar" />
      <template #resize-handle="{ onMouseDown, onTouchStart, onDoubleClick }">
        <NuxtDashboardResizeHandle
          role="presentation"
          data-operator-navigation-resize
          class="w-1 shrink-0 after:absolute after:inset-y-0 after:w-px after:bg-border hover:after:bg-primary"
          @mousedown="onMouseDown"
          @touchstart="onTouchStart"
          @dblclick="onDoubleClick"
        />
      </template>
    </NuxtDashboardSidebar>
    <NuxtDashboardPanel class="min-w-0" :ui="{ body: 'p-0 sm:p-0 gap-0' }">
      <template #header>
        <NuxtDashboardNavbar
          class="h-auto min-h-[var(--op-header-min-height)] py-2"
        >
          <template #left><slot name="navbar" /></template>
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
