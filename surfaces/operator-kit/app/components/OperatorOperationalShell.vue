<template>
  <NuxtDashboardGroup
    storage-key="operator-operational-shell"
    class="top-[var(--operator-offline-inset,0px)] transition-[top] duration-200 ease-out motion-reduce:transition-none"
    data-operator-operational-shell
  >
    <NuxtDashboardSidebar id="operational-navigation" :default-size="15">
      <slot name="navigation" />
    </NuxtDashboardSidebar>
    <NuxtDashboardPanel id="operational-task">
      <template #header><slot name="header" /></template>
      <template #body
        ><main class="min-w-0"><slot /></main
      ></template>
      <template #footer>
        <NuxtDashboardToolbar
          as="footer"
          class="border-t border-default border-b-0 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
        >
          <slot name="actions" />
        </NuxtDashboardToolbar>
      </template>
    </NuxtDashboardPanel>
  </NuxtDashboardGroup>
</template>
