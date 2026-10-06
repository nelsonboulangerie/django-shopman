<script setup lang="ts">
// Cabeçalho canônico do operador (Nuxt UI): DashboardNavbar + DashboardToolbar.
//
// Primitiva de kit (categoria 2 — o Nuxt UI não cobre): a barra mobile de 56px com
// selo/lupa/Avisos e a busca da suíte no navbar não existem como componente oficial.
// Em vez de hack local por app, a anatomia mora aqui e os oito apps herdam ao adotar.
// O par legado é o OperatorPageHeader (markup próprio); este é o caminho canônico.
//
// Por dispositivo (mesma régua do OperatorPageHeader):
//   - celular (<md): a busca vira lupa no #right (abre a busca da suíte em tela cheia)
//     e os Avisos vão para a barra; os controles descem para a toolbar;
//   - tablet/desktop: busca no centro, controles no #right, recortes na toolbar.
import { computed } from "vue";

import type { OperatorSession } from "../types/operator";

const props = withDefaults(defineProps<{
  title: string;
  eyebrow?: string;
  filtersWrap?: boolean;
  inbox?: boolean;
  search?: boolean;
  searchPlaceholder?: string;
}>(), { eyebrow: "", filtersWrap: true, inbox: true, search: true, searchPlaceholder: "Buscar pedido, cliente, produto ou tela" });

const config = useRuntimeConfig().public as { operatorHubUrl?: string };
const hubUrl = config.operatorHubUrl || "";

const railShown = useSuiteRailShown();

const { data: operatorSession } = useNuxtData<OperatorSession>("operator-session");
const eyebrowText = computed(() => {
  if (props.eyebrow) return props.eyebrow;
  const context = operatorSession.value?.workstation?.context_label ?? "";
  return context ? `${context} · este dispositivo` : "";
});

const { request: openSearch } = useSuiteSearchRequest();
</script>

<template>
  <NuxtDashboardNavbar
    as="header"
    data-operator-page-header
    :toggle="false"
    class="h-auto min-h-[var(--op-header-min-height)] shrink-0 border-b border-border bg-card print:hidden"
    :ui="{
      root: 'flex-wrap gap-x-2 gap-y-2 px-4 py-2.5',
      left: 'min-w-0 flex-none basis-0 gap-2 md:gap-3',
      center: 'hidden md:flex flex-1',
      right: 'flex items-center gap-2',
    }"
  >
    <template #left>
      <OperatorAppSeal v-if="hubUrl && !$slots.lead" />
      <slot name="lead" />
      <div class="min-w-0">
        <p v-if="eyebrowText" class="op-eyebrow truncate text-muted-foreground" data-page-header-eyebrow>{{ eyebrowText }}</p>
        <h1 class="truncate text-[19px] leading-none font-semibold tracking-[-0.01em] outline-none md:text-[22px]">{{ title }}</h1>
        <slot name="subtitle" />
      </div>
      <slot name="status" />
    </template>

    <template v-if="$slots.search || search" #default>
      <div class="hidden w-full md:block" data-page-header-search>
        <slot name="search"><OperatorSuiteSearch :placeholder="searchPlaceholder" /></slot>
      </div>
    </template>

    <template #right>
      <div class="flex items-center md:hidden">
        <button
          v-if="$slots.search || search"
          type="button"
          class="grid size-11 place-items-center rounded-md text-foreground"
          aria-label="Buscar"
          aria-haspopup="dialog"
          data-page-header-search-toggle
          @click="openSearch"
        >
          <Icon name="lucide:search" class="size-6" />
        </button>
        <slot name="phone-actions" />
      </div>
      <slot name="actions" />
      <ClientOnly v-if="inbox">
        <div v-if="!railShown" class="-mr-1 flex shrink-0 items-center" data-page-header-inbox>
          <OperatorInbox placement="header" />
        </div>
      </ClientOnly>
    </template>
  </NuxtDashboardNavbar>

  <NuxtDashboardToolbar v-if="$slots.filters || $slots.below" class="bg-card">
    <div
      v-if="$slots.filters"
      class="flex flex-wrap items-center gap-2 px-4 pb-2.5 *:shrink-0"
      :class="filtersWrap ? 'md:flex-wrap md:overflow-visible' : ''"
      data-page-header-filters
    >
      <slot name="filters" />
    </div>
    <slot name="below" />
  </NuxtDashboardToolbar>
</template>
