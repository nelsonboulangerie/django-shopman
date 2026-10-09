<script setup lang="ts">
// Protótipo do painel de filtros do K4, rodada 2 (dono, 09/10: "filtro repensado e IGUAL
// no celular e no desktop"; referência: o painel do Odoo, com Filtros, Agrupar por e
// Favoritos no mesmo lugar). É UM `NuxtCommandPalette` oficial: a busca dentro do painel,
// o teclado (setas, Enter, Backspace volta do submenu) e os grupos vêm de graça. O
// contêiner muda com o dispositivo (Drawer de baixo no celular, Popover na mesa); o
// conteúdo é o mesmo, na mesma ordem:
//   1. Favoritos (os seus; depois os da equipe)
//   2. Filtros rápidos (somam entre si: Atrasados OU Novos)
//   3. Data
//   4. Agrupar por (só onde a tela agrupa)
//   5. Filtros completos (cada campo abre a lista dele)
//   e no pé: "Salvar como favorito".
// Digitar oferece "Cliente contém …", como o "Search Customer for" do Odoo.
import { computed, ref } from "vue";

import type { Fase2FilterConfig } from "../data/fase2Filters";
import { applyView, edit, toggle } from "../data/fase2Filters";
import type { Fase2FilterState, SavedView } from "../types/fase2";

const props = defineProps<{
  config: Fase2FilterConfig;
  views: readonly SavedView[];
  /** O pé do painel: "Salvar como favorito" só com recorte. */
  canSave: boolean;
  /** "Limpar" no pé (na mesa; no celular ele mora no pé do Drawer). */
  clearable?: boolean;
}>();
const state = defineModel<Fase2FilterState>({ required: true });
const emit = defineEmits<{ save: []; clear: [] }>();

const term = ref("");

const on = (active: boolean) => (active ? "i-lucide-square-check" : "i-lucide-square");
const radio = (active: boolean) => (active ? "i-lucide-circle-dot" : "i-lucide-circle");

const groups = computed(() => {
  const s = state.value;
  const typed = term.value.trim();
  const own = props.views.filter((view) => !view.shared);
  const team = props.views.filter((view) => view.shared);
  const favorite = (view: SavedView) => ({
    label: view.name,
    description: view.summary,
    icon: s.favorite === view.id ? "i-lucide-star" : "i-lucide-bookmark",
    suffix: view.shared ? "Equipe" : undefined,
    active: s.favorite === view.id,
    "data-fase2-favorite": view.id,
    onSelect: (event: Event) => {
      event.preventDefault();
      state.value = applyView(view, props.config.defaultPeriod);
    },
  });
  return [
    ...(typed
      ? [
          {
            id: "text",
            label: "Buscar",
            ignoreFilter: true,
            items: props.config.textFields.map((field) => ({
              label: `${field.label} contém “${typed}”`,
              icon: "i-lucide-text-search",
              onSelect: (event: Event) => {
                event.preventDefault();
                state.value = edit(s, { text: [...s.text, { field: field.value, term: typed }] });
                term.value = "";
              },
            })),
          },
        ]
      : []),
    {
      id: "favorites",
      label: "Favoritos",
      items: own.length || team.length ? [...own.map(favorite), ...team.map(favorite)] : [{ label: "Nenhum favorito ainda", disabled: true }],
    },
    {
      id: "quick",
      label: "Filtros rápidos",
      items: props.config.quick.map((item) => ({
        label: item.label,
        icon: on(s.quick.includes(item.value)),
        active: s.quick.includes(item.value),
        onSelect: (event: Event) => {
          event.preventDefault();
          state.value = edit(s, { quick: toggle(s.quick, item.value) });
        },
      })),
    },
    ...(props.config.periods.length
      ? [
          {
            id: "period",
            label: "Data",
            items: [
              ...props.config.periods.map((item) => ({
                label: item.label,
                icon: radio(s.period === item.value),
                active: s.period === item.value,
                onSelect: (event: Event) => {
                  event.preventDefault();
                  state.value = edit(s, { period: item.value });
                },
              })),
              { label: "Escolher as datas", icon: "i-lucide-calendar-range", suffix: "de … até …" },
            ],
          },
        ]
      : []),
    ...(props.config.groups.length
      ? [
          {
            id: "group",
            label: "Agrupar por",
            items: props.config.groups.map((item) => ({
              label: item.label,
              icon: radio(s.groupBy === item.value),
              active: s.groupBy === item.value,
              onSelect: (event: Event) => {
                event.preventDefault();
                state.value = edit(s, { groupBy: item.value });
              },
            })),
          },
        ]
      : []),
    {
      id: "dimensions",
      label: "Filtros completos",
      items: props.config.dimensions.map((dimension) => {
        const chosen = s.values[dimension.id] ?? [];
        return {
          label: dimension.label,
          icon: "i-lucide-list-filter",
          suffix: chosen.length ? `${chosen.length} escolhido${chosen.length > 1 ? "s" : ""}` : undefined,
          children: dimension.options.map((option) => ({
            label: option.label,
            icon: on(chosen.includes(option.value)),
            suffix: option.count === undefined ? undefined : String(option.count),
            onSelect: (event: Event) => {
              event.preventDefault();
              const current = state.value.values[dimension.id] ?? [];
              state.value = edit(state.value, {
                values: { ...state.value.values, [dimension.id]: toggle(current, option.value) },
              });
            },
          })),
        };
      }),
    },
  ];
});
</script>

<template>
  <NuxtCommandPalette
    v-model:search-term="term"
    :groups="groups"
    placeholder="Buscar um filtro ou digitar um nome"
    :close="false"
    preserve-group-order
    class="max-h-[min(32rem,70dvh)]"
    data-fase2-filter-panel
  >
    <template #footer>
      <div class="flex items-center justify-between gap-2">
        <NuxtButton
          v-if="clearable"
          label="Limpar"
          color="neutral"
          variant="ghost"
          :disabled="!canSave"
          @click="emit('clear')"
        />
        <span v-else />
        <NuxtButton
          label="Salvar como favorito"
          icon="i-lucide-bookmark-plus"
          color="neutral"
          variant="ghost"
          :disabled="!canSave"
          data-fase2-save-favorite
          @click="emit('save')"
        />
      </div>
    </template>
  </NuxtCommandPalette>
</template>
