<script setup lang="ts">
// Os filtros rápidos da suíte (WP-FASE2-UX-OPERADOR, K4): a faixa de recortes de todo
// dia e de sub-seções, UM toque com a contagem ao lado. Mora na toolbar do
// `OperatorPageHeader` (`#filters-primary`), à esquerda; o `OperatorFilterPanel` segue
// sendo o lugar dos filtros completos. Regras em `presentation/quickFilters.ts`.
//
//   route     (todo item com `to`)  sub-seções: `NuxtTabs` que navegam; a ativa é a
//             da rota de agora. Setas andam, Enter abre (ativação manual: andar com a
//             seta não troca de página a cada tecla).
//   single    (`v-model` com uma chave)  `NuxtTabs` `pill`: um recorte de cada vez,
//             setas trocam (o padrão das abas).
//   multiple  (`v-model` com várias)  botões que ligam e desligam (`aria-pressed`) num
//             `toolbar`: setas andam, Enter/Espaço ligam. Ligado é o ativo canônico do
//             `NuxtButton` (`active`, `soft` primário), o mesmo do chip do recorte.
//
// A contagem é o `OperatorCountChip` (zero não aparece); na aba ativa preenchida ele
// inverte sozinho (`COUNT_CHIP_INVERTED_ON.tabActive`).
//
// Favoritos fixados (os `SavedView` com `pinned` da mesma `surface`/`screen` do painel)
// entram no FIM da faixa, com a estrela; tocar aplica o recorte inteiro (`apply`).
//
// Celular: a faixa rola na horizontal sem cortar rótulo; com mais de
// `QUICK_FILTERS_PHONE_MAX` opções ela vira um `NuxtSelect`. As duas formas existem e a
// régua é CSS: o servidor e o cliente desenham a mesma árvore.
import { computed, ref } from "vue";

import { useSavedViews } from "../composables/useSavedViews";
import { sameQuery, type FilterPanelQuery } from "../presentation/filterPanel";
import {
  QUICK_FILTERS_PHONE_MAX,
  collapsesOnPhone,
  isQuickActive,
  nextQuickIndex,
  quickFiltersMode,
  quickKeys,
  routeActiveKey,
  toggleQuick,
  type QuickFilterItem,
} from "../presentation/quickFilters";

const props = withDefaults(
  defineProps<{
    items: QuickFilterItem[];
    /** O nome do grupo para leitor de tela ("Recortes das encomendas"). */
    label: string;
    multiple?: boolean;
    /** Onde moram os favoritos (os mesmos do painel). Sem os dois, sem favoritos. */
    surface?: string;
    screen?: string;
    /** O recorte da tela agora, para marcar o favorito ativo. */
    query?: FilterPanelQuery;
    /** Até quantas opções a faixa rola no celular. */
    phoneMax?: number;
  }>(),
  { multiple: false, surface: "", screen: "", query: undefined, phoneMax: QUICK_FILTERS_PHONE_MAX },
);

const model = defineModel<string | string[]>();
const emit = defineEmits<{ apply: [query: FilterPanelQuery] }>();

const route = useRoute();
const mode = computed(() => quickFiltersMode(props.items, props.multiple));

// ── o valor das abas (route e single) ─────────────────────────────────────
const tabValue = computed<string>({
  get: () =>
    mode.value === "route"
      ? routeActiveKey(props.items, { path: route.path, query: route.query })
      : (quickKeys(model.value)[0] ?? ""),
  set: (key) => select(key),
});
const tabItems = computed(() =>
  props.items.map((item) => ({
    label: item.label,
    icon: item.icon,
    value: item.key,
    disabled: item.disabled,
    count: item.count,
  })),
);

function select(key: string) {
  const item = props.items.find((entry) => entry.key === key);
  if (!item || item.disabled) return;
  if (mode.value === "route") {
    if (item.to) void navigateTo(item.to);
    return;
  }
  model.value = toggleQuick(model.value, key, props.items, props.multiple);
}

// ── teclado da faixa de botões (multiple): setas, Home, End ──────────────
const strip = ref<HTMLElement | null>(null);
const focusKey = ref("");
const rovingKey = computed(() => {
  const keys = props.items.filter((item) => !item.disabled).map((item) => item.key);
  if (focusKey.value && keys.includes(focusKey.value)) return focusKey.value;
  return keys.find((key) => isQuickActive(model.value, key)) ?? keys[0] ?? "";
});
const KEY_STEPS: Record<string, number> = {
  ArrowRight: 1,
  ArrowDown: 1,
  ArrowLeft: -1,
  ArrowUp: -1,
  Home: -Infinity,
  End: Infinity,
};
function onStripKey(event: KeyboardEvent) {
  const step = KEY_STEPS[event.key];
  if (step === undefined) return;
  const current = props.items.findIndex((item) => item.key === rovingKey.value);
  const next = nextQuickIndex(props.items, current < 0 ? 0 : current, step);
  const key = props.items[next]?.key;
  if (!key) return;
  event.preventDefault();
  focusKey.value = key;
  strip.value?.querySelector<HTMLElement>(`[data-quick-filter-item="${CSS.escape(key)}"]`)?.focus();
}

// ── favoritos fixados, no fim ────────────────────────────────────────────
const saved = props.surface && props.screen ? useSavedViews<FilterPanelQuery>(props.surface, props.screen) : null;
const pinned = computed(() => (saved?.views.value ?? []).filter((view) => view.pinned));
const favoriteOn = (view: { query: FilterPanelQuery }) => Boolean(props.query) && sameQuery(props.query!, view.query);

// ── celular: mais que o teto vira seletor ────────────────────────────────
const collapses = computed(() => collapsesOnPhone(props.items, props.phoneMax));
const selectItems = computed(() =>
  props.items.map((item) => ({ label: item.label, value: item.key, icon: item.icon, disabled: item.disabled, count: item.count })),
);
const selectValue = computed<string | string[]>({
  get: () => (mode.value === "multiple" ? quickKeys(model.value) : tabValue.value),
  set: (next) => {
    if (mode.value === "multiple") model.value = props.items.map((item) => item.key).filter((key) => quickKeys(next).includes(key));
    else if (typeof next === "string") select(next);
  },
});
const stripClass = computed(() => (collapses.value ? "max-sm:hidden" : ""));
// Favorito fixado não vira aba no celular quando as abas já não cabem: ele está no
// topo do painel de filtros.
const favoritesClass = computed(() =>
  collapses.value || props.items.length + pinned.value.length > props.phoneMax ? "max-sm:hidden" : "",
);
</script>

<template>
  <div class="flex min-w-0 items-center gap-2" data-operator-quick-filters :data-quick-filters-mode="mode">
    <!-- A faixa rola na horizontal de propósito (o contrato do scanner de geometria:
         `data-operator-overflow="horizontal"`). -->
    <div
      class="flex min-w-0 items-center gap-2 overflow-x-auto no-scrollbar"
      :class="stripClass"
      data-operator-overflow="horizontal"
    >
      <NuxtTabs
        v-if="mode !== 'multiple'"
        v-model="tabValue"
        :items="tabItems"
        :content="false"
        variant="pill"
        size="md"
        :activation-mode="mode === 'route' ? 'manual' : 'automatic'"
        :aria-label="label"
        :ui="{ root: 'min-w-0', list: 'w-max', trigger: 'shrink-0 grow-0' }"
        data-quick-filters-strip
      >
        <template #trailing="{ item }">
          <OperatorCountChip :count="(item as { count?: number | null }).count" data-quick-filter-count />
        </template>
      </NuxtTabs>

      <div
        v-else
        ref="strip"
        role="toolbar"
        :aria-label="label"
        class="flex w-max items-center gap-2"
        data-quick-filters-strip
        @keydown="onStripKey"
      >
        <NuxtButton
          v-for="item in items"
          :key="item.key"
          class="shrink-0 whitespace-nowrap"
          :label="item.label"
          :icon="item.icon"
          color="neutral"
          variant="outline"
          :active="isQuickActive(model, item.key)"
          active-color="primary"
          active-variant="soft"
          :disabled="item.disabled"
          :aria-pressed="isQuickActive(model, item.key)"
          :tabindex="item.key === rovingKey ? 0 : -1"
          :data-quick-filter-item="item.key"
          :data-quick-filter-active="isQuickActive(model, item.key) ? '' : undefined"
          @focus="focusKey = item.key"
          @click="select(item.key)"
        >
          <template v-if="item.count" #trailing>
            <OperatorCountChip :count="item.count" data-quick-filter-count />
          </template>
        </NuxtButton>
      </div>

      <div
        v-if="pinned.length"
        role="group"
        aria-label="Favoritos fixados"
        class="flex w-max shrink-0 items-center gap-2"
        :class="favoritesClass"
        data-quick-filters-favorites
      >
        <NuxtButton
          v-for="view in pinned"
          :key="view.id"
          class="shrink-0 whitespace-nowrap"
          :label="view.name"
          icon="i-lucide-star"
          color="neutral"
          variant="ghost"
          :active="favoriteOn(view)"
          active-color="primary"
          active-variant="soft"
          :aria-pressed="favoriteOn(view)"
          :data-quick-filter-favorite="view.id"
          @click="emit('apply', view.query)"
        />
      </div>
    </div>

    <NuxtSelect
      v-if="collapses"
      v-model="selectValue"
      class="min-w-40 sm:hidden"
      :items="selectItems"
      :multiple="mode === 'multiple'"
      :placeholder="label"
      :aria-label="label"
      data-quick-filters-select
    >
      <template #item-trailing="{ item }">
        <OperatorCountChip :count="(item as { count?: number | null }).count" />
      </template>
    </NuxtSelect>
  </div>
</template>
