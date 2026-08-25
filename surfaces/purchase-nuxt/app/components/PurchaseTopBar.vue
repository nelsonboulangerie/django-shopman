<script setup lang="ts">
import type { PurchaseView } from "~/types/purchase";

defineProps<{
  view: PurchaseView;
  metrics: {
    urgentMaterials: number;
    missingPreferred: number;
    approximatePreferred: number;
  };
}>();

const emit = defineEmits<{ "update:view": [value: PurchaseView] }>();

const tabs: { key: PurchaseView; label: string; icon: string }[] = [
  { key: "panel", label: "Painel", icon: "lucide:layout-dashboard" },
  { key: "buy", label: "Comprar", icon: "lucide:shopping-cart" },
  { key: "receive", label: "Receber", icon: "lucide:package-check" },
  { key: "base", label: "Base", icon: "lucide:database" },
];

const chipClass = (active: boolean) =>
  active
    ? "bg-card font-semibold text-foreground shadow-sm"
    : "text-muted-foreground hover:bg-card/60 hover:text-foreground";
</script>

<template>
  <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2.5 print:hidden">
    <RailToggle />
    <div class="h-6 w-px shrink-0 bg-border"></div>
    <nav class="flex min-w-0 items-center gap-0.5 overflow-x-auto rounded-md bg-muted p-1" aria-label="Seções de compras">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-3 text-sm transition-all"
        :class="chipClass(view === tab.key)"
        @click="emit('update:view', tab.key)"
      >
        <Icon :name="tab.icon" class="size-4" :class="view === tab.key ? 'text-foreground' : 'text-muted-foreground'" />
        <span>{{ tab.label }}</span>
      </button>
    </nav>

    <div class="ml-auto hidden shrink-0 items-center gap-2 xl:flex">
      <span class="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-xs font-medium text-foreground">
        <Icon name="lucide:triangle-alert" class="size-3.5 text-warning" />
        {{ metrics.urgentMaterials }} reposições
      </span>
      <span class="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-xs font-medium text-foreground">
        <Icon name="lucide:badge-alert" class="size-3.5 text-info" />
        {{ metrics.missingPreferred }} sem preferencial
      </span>
      <span class="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-xs font-medium text-foreground">
        <Icon name="lucide:equal-approximately" class="size-3.5 text-muted-foreground" />
        {{ metrics.approximatePreferred }} estimados
      </span>
    </div>
  </header>
</template>
