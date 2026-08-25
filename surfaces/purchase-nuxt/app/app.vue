<script setup lang="ts">
const OPERATOR_PERM = "backstage.operate_purchase";
const { canIdentify, locked, mustChange, operator, lock } = useOperatorLock(OPERATOR_PERM);
const { view, metrics } = usePurchaseDesk();
const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

const railItems = [
  { key: "panel", label: "Painel", icon: "layout-dashboard" },
  { key: "buy", label: "Comprar", icon: "shopping-cart" },
  { key: "receive", label: "Receber", icon: "package-check" },
  { key: "base", label: "Base", icon: "database" },
] as const;

useHead({ title: "Compras" });
</script>

<template>
  <div class="flex min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <OfflineBanner />
    <div v-if="canIdentify" class="sticky top-0 hidden h-screen shrink-0 print:hidden md:flex">
      <OperatorRail
        app-icon="shopping-basket"
        app-label="Compras"
        :central-url="hubUrl"
        :operator-name="operator?.name"
        @lock="lock"
      >
        <template #nav>
          <RailItem
            v-for="item in railItems"
            :key="item.key"
            :icon="item.icon"
            :label="item.label"
            :active="view === item.key"
            :attention="item.key === 'buy' && metrics.urgentMaterials > 0"
            @activate="view = item.key"
          />
        </template>
      </OperatorRail>
    </div>
    <div class="flex min-w-0 flex-1 flex-col">
      <PurchaseTopBar v-if="canIdentify" :view="view" :metrics="metrics" @update:view="view = $event" />
      <div v-show="canIdentify" class="min-w-0 flex-1">
        <NuxtPage />
      </div>
    </div>
    <nav v-if="canIdentify" class="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-border bg-card/95 px-2 py-1.5 backdrop-blur md:hidden" aria-label="Navegação principal">
      <button
        v-for="item in railItems"
        :key="item.key"
        type="button"
        class="flex h-14 flex-col items-center justify-center gap-1 rounded-md text-xs"
        :class="view === item.key ? 'bg-primary/10 font-semibold text-primary' : 'text-muted-foreground'"
        @click="view = item.key"
      >
        <Icon :name="`lucide:${item.icon}`" class="size-5" />
        <span>{{ item.label }}</span>
      </button>
    </nav>
    <OperatorLogin v-if="!canIdentify" />
    <OperatorLock v-else-if="locked || mustChange" :perm="OPERATOR_PERM" />
    <UiSonner />
  </div>
</template>
