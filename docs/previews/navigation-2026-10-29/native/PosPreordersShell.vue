<script setup lang="ts">
// Experimento de composição, exclusivo de docs/previews.
// Parte do PosPreordersShell de origin/main e0c22ba1f.
// Mantém componentes, props, slots e callbacks. Nenhuma regra de negócio nova.
import type { OperatorActiveFilter, OperatorHeaderAction } from "../../../operator-kit/app/presentation/pageHeader";
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";
import type { POSProjection } from "~/types/pos";

const props = withDefaults(defineProps<{
  pos: POSProjection | null;
  pending: boolean;
  /** Largura do conteúdo: a grade semanal precisa da tela inteira. */
  wide?: boolean;
  /** As ações da tela no ⋯ (na mesa); "Atualizar" entra sempre no fim. */
  actions?: OperatorHeaderAction[];
  /** As ações do ⋯ no celular, quando diferem das da mesa; "Atualizar" no fim. */
  phoneActions?: OperatorHeaderAction[];
  alerts?: OperatorScreenAlert[];
  activeFilters?: OperatorActiveFilter[];
  /** O título do cabeçalho; o detalhe diz qual encomenda ("Encomenda PDV-…"). */
  title?: string;
}>(), {
  title: "Encomendas",
  wide: false,
  actions: () => [],
  phoneActions: undefined,
  alerts: () => [],
  activeFilters: () => [],
});

const emit = defineEmits<{ refresh: [] }>();

const refreshAction: OperatorHeaderAction = {
  label: "Atualizar",
  icon: "i-lucide-refresh-cw",
  onSelect: () => emit("refresh"),
};
const headerActions = computed<OperatorHeaderAction[]>(() => [...props.actions, refreshAction]);
const headerPhoneActions = computed<OperatorHeaderAction[] | undefined>(() =>
  props.phoneActions ? [...props.phoneActions, refreshAction] : undefined,
);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-preorders-shell data-preview-native-proposal>
    <div class="relative min-h-0 flex-1 overflow-y-auto">
      <OperatorPageHeader
        :title="title" :search="!$slots.search"
        :actions="headerActions" :phone-actions="headerPhoneActions"
        actions-label="Mais ações das Encomendas"
        :alerts="alerts" :active-filters="activeFilters"
      >
        <template v-if="$slots.primary" #actions><slot name="primary" /></template>
      </OperatorPageHeader>
      <div class="mx-auto grid w-full gap-3 p-3 sm:gap-4 sm:p-4 md:py-6" :class="wide ? 'max-w-screen-2xl' : 'max-w-3xl'">
        <NuxtCard v-if="$slots.search || $slots['filters-primary']" variant="outline"
          :ui="{body:'grid gap-2 p-2 sm:gap-3 sm:p-4'}" data-preview-preorders-tools>
          <div class="flex min-w-0 flex-wrap items-center gap-2" data-preview-period>
            <slot name="filters-primary" />
          </div>
          <div class="flex min-w-0 items-center gap-2" data-preview-search-row>
            <slot name="filter-panel" />
            <div class="min-w-0 flex-1"><slot name="search" /></div>
            <slot name="filters" />
          </div>
          <div v-if="$slots['filters-end']" class="border-t border-default pt-2 sm:pt-3"><slot name="filters-end" /></div>
        </NuxtCard>
        <slot />
        <MoreBelow :key="$slots.footer ? 'with-footer' : 'no-footer'" />
      </div>
    </div>
    <slot name="footer" />
  </main>
</template>
<style>
/* Experimento isolado: tokens, componentes e callbacks nativos permanecem. */
[data-preview-native-proposal] [data-operator-page-header] {
  position: sticky; top: 0; z-index: 20; background: var(--ui-bg);
}
[data-preview-search-row] [data-preorders-layout] { flex-shrink: 0; }
[data-preview-preorders-tools] [data-preorders-search] { width: 100%; }
@media (max-width: 639px) {
  [data-preview-search-row] [data-preorders-layout] { display: none; }
  [data-preview-period] { align-items: stretch; }
  [data-preview-period] [data-preorders-period] { flex: 0 1 auto; }
  [data-preview-period] [data-preorders-quick] { flex: 1 1 6rem; min-width: 0; max-width: 100%; }
  [data-preview-period] [data-quick-filters-select] { width: 100%; min-width: 0; }
}
</style>
