<script setup lang="ts">
// O painel de filtros único da suíte (WP-FASE2-UX-OPERADOR, K4), sobre o
// `NuxtCommandPalette` oficial: a busca dentro do painel, o teclado (setas, Enter,
// Backspace volta do submenu) e os grupos vêm de graça.
//
// Ordem fixa (dono, 09/10/2026, referência: o painel do Odoo):
//   1. Favoritos (os seus, fixados primeiro), e "Gerenciar favoritos"
//   2. Filtros rápidos (somam: Atrasados OU Novos)
//   3. Data (o período das LISTAS mora aqui; as setas ficam para o B.I. e o Fechamento)
//   4. Agrupar por (só onde a tela agrupa)
//   5. Filtros completos (cada campo abre a lista dele)
//   e no pé: Limpar e "Salvar como favorito".
// Digitar oferece "Cliente contém …" para as dimensões de texto.
//
// O botão: só o ícone com o número no celular; ícone, "Filtros" e o número na mesa.
// O contêiner: `NuxtDrawer` de baixo no celular, `NuxtPopover` na mesa (a régua do
// kit, lida depois de montar). Na mesa os recortes ativos viram chips ao lado do botão;
// no celular os chips são os do cabeçalho (`active-filters`). O diálogo de salvar e o
// de datas moram FORA do contêiner.
import { createReusableTemplate } from "@vueuse/core";
import { computed, ref } from "vue";

import { useSavedViews } from "../composables/useSavedViews";
import { useScreen } from "../composables/useScreen";
import {
  CUSTOM_PERIOD,
  customPeriod as customRange,
  periodLabel,
  resolvePeriod,
  todayIso,
  withPreset,
  type PeriodSelection,
} from "../presentation/dates";
import { filterBarActiveFilters, optionsFor, setValues, toggleOption } from "../presentation/filterBar";
import {
  activeRecortes,
  containsLabel,
  filterPanelLabel,
  panelDimensions,
  periodOptionLabel,
  queryToSave,
  quickActive,
  samePeriod,
  sameQuery,
  type FilterPanelGroupOption,
  type FilterPanelQuery,
  type FilterPanelQuick,
} from "../presentation/filterPanel";
import type { ActiveFilters, FilterDimension } from "../types/filters";

const props = withDefaults(
  defineProps<{
    dimensions: FilterDimension[];
    quick?: FilterPanelQuick[];
    /** Os períodos que a lista oferece (chaves de `PERIOD_PRESETS`). Vazio: sem Data. */
    periodPresets?: readonly string[];
    /** Aceita "Escolher as datas". */
    customPeriod?: boolean;
    /** O período de quem chega à tela (Limpar volta a ele; fora dele, conta como recorte). */
    defaultPeriod?: PeriodSelection;
    today?: string;
    max?: string;
    groups?: FilterPanelGroupOption[];
    defaultGroup?: string;
    /** Onde mora o favorito: sem `surface`/`screen`, o painel não oferece favoritos. */
    surface?: string;
    screen?: string;
    /** Chips dos recortes ativos ao lado do botão (na mesa). */
    chips?: boolean;
  }>(),
  {
    quick: () => [],
    periodPresets: () => [],
    customPeriod: false,
    defaultPeriod: undefined,
    today: "",
    max: "",
    groups: () => [],
    defaultGroup: "",
    surface: "",
    screen: "",
    chips: true,
  },
);

const filters = defineModel<ActiveFilters>({ required: true });
const period = defineModel<PeriodSelection | undefined>("period", { default: undefined });
const group = defineModel<string>("group", { default: "" });

const { belowSm } = useScreen();
const open = ref(false);
const term = ref("");
const today = computed(() => props.today || todayIso());
const bounds = computed(() => ({ today: today.value, max: props.max || undefined }));

const saved = props.surface && props.screen ? useSavedViews<FilterPanelQuery>(props.surface, props.screen) : null;
const views = computed(() => saved?.views.value ?? []);

const editable = computed(() => panelDimensions(props.dimensions));
const query = computed<FilterPanelQuery>(() => ({
  filters: filters.value,
  ...(period.value ? { period: period.value } : {}),
  ...(group.value ? { group: group.value } : {}),
}));
const defaults = computed(() => ({ period: props.defaultPeriod, group: props.defaultGroup }));
const activeCount = computed(() => activeRecortes(editable.value, query.value, defaults.value));
const buttonLabel = computed(() => filterPanelLabel(activeCount.value));

function apply(next: FilterPanelQuery) {
  filters.value = { ...next.filters };
  if (props.periodPresets.length) period.value = next.period ?? props.defaultPeriod;
  if (props.groups.length) group.value = next.group ?? props.defaultGroup;
}

function clear() {
  apply({ filters: {}, period: props.defaultPeriod, group: props.defaultGroup });
}

const check = (on: boolean) => (on ? "i-lucide-square-check" : "i-lucide-square");
const radio = (on: boolean) => (on ? "i-lucide-circle-dot" : "i-lucide-circle");
const keep = (fn: () => void) => (event: Event) => {
  event.preventDefault();
  fn();
};

// ── os grupos do painel ──────────────────────────────────────────────────
const customOpen = ref(false);
const saveOpen = ref(false);

const groups = computed(() => {
  const typed = term.value.trim();
  const textDimensions = editable.value.filter((dimension) => dimension.type === "text");
  const out: Record<string, unknown>[] = [];

  if (typed && textDimensions.length) {
    out.push({
      id: "text",
      label: "Buscar",
      ignoreFilter: true,
      items: textDimensions.map((dimension) => ({
        label: containsLabel(dimension, typed),
        icon: "i-lucide-text-search",
        onSelect: keep(() => {
          filters.value = setValues(filters.value, dimension.id, [typed]);
          term.value = "";
        }),
      })),
    });
  }

  // Favorito fixado mora nos filtros rápidos (o "Mostrar nos filtros rápidos da tela"
  // do diálogo); os outros, em Favoritos. "Gerenciar" lista todos.
  if (saved) {
    const items = views.value.filter((view) => !view.pinned).map((view) => ({
      label: view.name,
      icon: view.pinned ? "i-lucide-star" : "i-lucide-bookmark",
      active: sameQuery(query.value, view.query),
      suffix: sameQuery(query.value, view.query) ? "Na tela" : undefined,
      "data-operator-filter-favorite": view.id,
      onSelect: keep(() => apply(view.query)),
    }));
    out.push({
      id: "favorites",
      label: "Favoritos",
      items: views.value.length
        ? [
            ...items,
            {
              label: "Gerenciar favoritos",
              icon: "i-lucide-settings-2",
              children: views.value.map((view) => ({
                label: view.name,
                icon: view.pinned ? "i-lucide-star" : "i-lucide-bookmark",
                children: [
                  {
                    label: view.pinned ? "Tirar dos filtros rápidos" : "Mostrar nos filtros rápidos",
                    icon: view.pinned ? "i-lucide-star-off" : "i-lucide-star",
                    onSelect: keep(() => void saved.setPinned(view, !view.pinned)),
                  },
                  {
                    label: "Apagar este favorito",
                    icon: "i-lucide-trash-2",
                    color: "error",
                    onSelect: keep(() => void saved.remove(view)),
                  },
                ],
              })),
            },
          ]
        : [{ label: "Nenhum favorito ainda. Monte o recorte e salve no pé.", icon: "i-lucide-bookmark", disabled: true }],
    });
  }

  const pinnedViews = views.value.filter((view) => view.pinned);
  if (props.quick.length || pinnedViews.length) {
    out.push({
      id: "quick",
      label: "Filtros rápidos",
      items: [
        ...pinnedViews.map((view) => ({
          label: view.name,
          icon: radio(sameQuery(query.value, view.query)),
          onSelect: keep(() => apply(view.query)),
        })),
        ...props.quick.map((quick) => {
          const dimension = props.dimensions.find((item) => item.id === quick.dimension);
          const on = quickActive(filters.value, quick);
          return {
            label: quick.label,
            icon: check(on),
            onSelect: keep(() => {
              if (dimension) filters.value = toggleOption(filters.value, { ...dimension, type: "multi-select" }, quick.value);
            }),
          };
        }),
      ],
    });
  }

  if (props.periodPresets.length && period.value) {
    const current = period.value;
    out.push({
      id: "period",
      label: "Data",
      items: [
        ...props.periodPresets.map((key) => {
          const on = current.preset === key && !current.from && !current.to;
          return {
            label: periodOptionLabel(key),
            icon: radio(on),
            onSelect: keep(() => {
              period.value = withPreset({ preset: key, from: "", to: "" }, key, bounds.value);
            }),
          };
        }),
        ...(props.customPeriod
          ? [
              {
                label: "Escolher as datas",
                icon: radio(current.preset === CUSTOM_PERIOD),
                suffix: current.preset === CUSTOM_PERIOD ? periodLabel(current, resolvePeriod(current, bounds.value), today.value) : "de … até …",
                onSelect: keep(() => {
                  open.value = false;
                  customOpen.value = true;
                }),
              },
            ]
          : []),
      ],
    });
  }

  if (props.groups.length) {
    out.push({
      id: "group",
      label: "Agrupar por",
      items: props.groups.map((option) => ({
        label: option.label,
        icon: radio(group.value === option.value),
        onSelect: keep(() => {
          group.value = option.value;
        }),
      })),
    });
  }

  const lists = editable.value.filter((dimension) => dimension.type !== "text");
  if (lists.length) {
    out.push({
      id: "dimensions",
      label: "Filtros completos",
      items: lists.map((dimension) => {
        const chosen = (filters.value[dimension.id] ?? []).filter(Boolean);
        return {
          label: dimension.label,
          icon: "i-lucide-list-filter",
          suffix: chosen.length ? (chosen.length === 1 ? "1 escolhido" : `${chosen.length} escolhidos`) : undefined,
          placeholder: `Buscar em ${dimension.label.toLowerCase()}`,
          "data-operator-filter-dimension": dimension.id,
          children: optionsFor(dimension).map((option) => {
            const on = chosen.includes(option.value);
            return {
              label: option.label,
              icon: dimension.type === "multi-select" ? check(on) : radio(on),
              suffix: option.count === undefined ? undefined : String(option.count),
              onSelect: keep(() => {
                filters.value = toggleOption(filters.value, dimension, option.value);
              }),
            };
          }),
        };
      }),
    });
  }
  return out;
});

// ── chips (na mesa) ──────────────────────────────────────────────────────
const chipList = computed(() => [
  ...(period.value && props.defaultPeriod && !samePeriod(period.value, props.defaultPeriod)
    ? [
        {
          key: "period",
          label: periodLabel(period.value, resolvePeriod(period.value, bounds.value), today.value),
          remove: () => (period.value = props.defaultPeriod),
        },
      ]
    : []),
  ...(group.value && group.value !== props.defaultGroup
    ? [
        {
          key: "group",
          label: `Agrupado por ${(props.groups.find((option) => option.value === group.value)?.label ?? group.value).toLowerCase()}`,
          remove: () => (group.value = props.defaultGroup),
        },
      ]
    : []),
  ...filterBarActiveFilters(editable.value, filters.value, (next) => (filters.value = next)),
]);

// ── salvar como favorito ────────────────────────────────────────────────
const saveName = ref("");
const savePinned = ref(false);
function startSave() {
  open.value = false;
  saveName.value = "";
  savePinned.value = false;
  saveOpen.value = true;
}
async function confirmSave() {
  if (!saved || !saveName.value.trim()) return;
  const view = await saved.save(saveName.value.trim(), queryToSave(query.value), { pinned: savePinned.value });
  if (view) saveOpen.value = false;
}

// ── escolher as datas ───────────────────────────────────────────────────
const range = ref({ start: "", end: "" });
const rangeValid = computed(() => Boolean(range.value.start && range.value.end));
function confirmRange() {
  if (!rangeValid.value) return;
  period.value = customRange(range.value.start, range.value.end);
  customOpen.value = false;
}

const [DefinePalette, ReusePalette] = createReusableTemplate();

const canSave = computed(() => Boolean(saved) && activeCount.value > 0);
</script>

<template>
  <div class="flex min-w-0 flex-wrap items-center gap-2" data-operator-filter-panel-root>
    <!-- O painel escrito uma vez; o contêiner muda com a largura (o botão vai em cada um,
         filho direto do gatilho). -->
    <DefinePalette>
      <NuxtCommandPalette
        v-model:search-term="term"
        :groups="groups as never"
        placeholder="Buscar um filtro ou digitar um nome"
        :close="false"
        preserve-group-order
        class="max-h-[min(32rem,70dvh)] sm:w-[22rem]"
        data-operator-filter-panel
      >
        <template #footer>
          <div class="flex flex-wrap items-center justify-between gap-2">
            <NuxtButton
              label="Limpar"
              color="neutral"
              variant="outline"
              :disabled="!activeCount"
              data-operator-filter-panel-clear
              @click="clear()"
            />
            <div class="flex items-center gap-2">
              <NuxtButton
                v-if="surface && screen"
                label="Salvar como favorito"
                icon="i-lucide-bookmark-plus"
                color="neutral"
                variant="outline"
                :disabled="!canSave"
                data-operator-filter-panel-save
                @click="startSave()"
              />
              <NuxtButton
                v-if="belowSm"
                label="Pronto"
                color="primary"
                data-operator-filter-panel-done
                @click="open = false"
              />
            </div>
          </div>
        </template>
      </NuxtCommandPalette>
    </DefinePalette>

    <NuxtDrawer
      v-if="belowSm"
      v-model:open="open"
      title="Filtros"
      description="Favoritos, filtros rápidos, data e filtros completos"
    >
      <NuxtButton
        icon="i-lucide-sliders-horizontal"
        color="neutral"
        variant="outline"
        :aria-label="buttonLabel"
        :title="buttonLabel"
        aria-haspopup="dialog"
        :aria-expanded="open"
        data-operator-filter-panel-open
      >
        <span class="max-sm:sr-only">Filtros</span>
        <template v-if="activeCount" #trailing>
          <NuxtBadge color="primary" size="sm" :label="String(activeCount)" data-operator-filter-panel-count />
        </template>
      </NuxtButton>
      <template #body><ReusePalette /></template>
    </NuxtDrawer>
    <NuxtPopover v-else v-model:open="open" :content="{ align: 'start' }">
      <NuxtButton
        icon="i-lucide-sliders-horizontal"
        color="neutral"
        variant="outline"
        :aria-label="buttonLabel"
        :title="buttonLabel"
        aria-haspopup="dialog"
        :aria-expanded="open"
        data-operator-filter-panel-open
      >
        <span class="max-sm:sr-only">Filtros</span>
        <template v-if="activeCount" #trailing>
          <NuxtBadge color="primary" size="sm" :label="String(activeCount)" data-operator-filter-panel-count />
        </template>
      </NuxtButton>
      <template #content><ReusePalette /></template>
    </NuxtPopover>

    <template v-if="chips">
      <NuxtButton
        v-for="chip in chipList"
        :key="chip.key"
        class="max-sm:hidden"
        :label="chip.label"
        trailing-icon="i-lucide-x"
        color="primary"
        variant="ghost"
        active
        active-variant="soft"
        :aria-label="`Tirar o recorte ${chip.label}`"
        data-operator-filter-chip
        @click="chip.remove()"
      />
    </template>

    <NuxtModal
      v-model:open="saveOpen"
      title="Salvar como favorito"
      description="O recorte na tela, com um nome. Só você vê os seus favoritos."
    >
      <template #body>
        <div class="space-y-4" data-operator-filter-save-form>
          <NuxtFormField label="Nome" required>
            <NuxtInput
              v-model="saveName"
              class="w-full"
              autofocus
              placeholder="Cancelados da semana"
              data-operator-filter-save-name
              @keydown.enter.prevent="confirmSave()"
            />
          </NuxtFormField>
          <NuxtSwitch v-model="savePinned" label="Mostrar nos filtros rápidos da tela" />
        </div>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton label="Voltar" color="neutral" variant="outline" @click="saveOpen = false" />
          <NuxtButton
            label="Salvar favorito"
            icon="i-lucide-bookmark-plus"
            :disabled="!saveName.trim()"
            data-operator-filter-save-confirm
            @click="confirmSave()"
          />
        </div>
      </template>
    </NuxtModal>

    <NuxtModal v-if="customPeriod" v-model:open="customOpen" title="Escolher as datas" description="De um dia a outro, os dois incluídos.">
      <template #body>
        <UiDateRangeField v-model="range" :max="max || today" label="Período" />
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton label="Voltar" color="neutral" variant="outline" @click="customOpen = false" />
          <NuxtButton label="Ver este período" :disabled="!rangeValid" @click="confirmRange()" />
        </div>
      </template>
    </NuxtModal>
  </div>
</template>
