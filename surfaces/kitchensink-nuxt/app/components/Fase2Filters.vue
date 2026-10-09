<script setup lang="ts">
// O botão Filtros da rodada 2: UM painel (`Fase2FilterPanel`), dois contêineres.
//   celular (abaixo de `sm`): só o ÍCONE, com o número de recortes ativos no canto
//     (dono, 09/10); abre um `NuxtDrawer` de baixo, com "Limpar" e "Ver N pedidos" no pé;
//   mesa: ícone + "Filtros" + o mesmo número; abre um `NuxtPopover` alinhado à direita.
// A troca é por CSS (`sm:hidden` / `max-sm:hidden`), nunca por media query em JS: o
// servidor desenha os dois e a hidratação não diverge (regra K0).
// "Salvar como favorito" abre um diálogo FORA do painel: o Popover fecha ao perder o
// foco e levaria o diálogo junto.
import { computed, onMounted, ref } from "vue";

import type { Fase2FilterConfig } from "../data/fase2Filters";
import { emptyState, facetsOf, summaryOf } from "../data/fase2Filters";
import type { Fase2FilterState, SavedView } from "../types/fase2";

const props = withDefaults(
  defineProps<{
    config: Fase2FilterConfig;
    /** Quantos itens o recorte atual mostra ("Ver 7 pedidos"). */
    resultCount: number;
    /** Gerente vê "Publicar para a equipe" no diálogo de salvar. */
    manager?: boolean;
    /** Abre o painel ao montar (retratos da proposta). */
    openOnMount?: boolean;
  }>(),
  { manager: true, openOnMount: false },
);
const state = defineModel<Fase2FilterState>({ required: true });
const views = defineModel<SavedView[]>("views", { required: true });

const count = computed(() => facetsOf(state.value, props.config, views.value).length);
const canSave = computed(() => Boolean(summaryOf(state.value, props.config, views.value)) && !state.value.favorite);
const triggerLabel = computed(() => (count.value ? `Filtros, ${count.value} ativos` : "Filtros"));

const phoneOpen = ref(false);
const deskOpen = ref(false);
onMounted(() => {
  if (!props.openOnMount) return;
  if (window.matchMedia("(max-width: 639.98px)").matches) phoneOpen.value = true;
  else deskOpen.value = true;
});

function clear() {
  state.value = emptyState(props.config.defaultPeriod);
}

const saving = ref(false);
const name = ref("");
const pinned = ref(true);
const shared = ref(false);
const summary = computed(() => summaryOf(state.value, props.config, views.value));
function askSave() {
  name.value = "";
  pinned.value = true;
  shared.value = false;
  deskOpen.value = false;
  phoneOpen.value = false;
  saving.value = true;
}
function confirmSave() {
  const value = name.value.trim();
  if (!value) return;
  const id = `v${Date.now()}`;
  views.value = [
    ...views.value,
    { id, name: value, summary: summary.value, pinned: pinned.value, shared: shared.value, state: { ...state.value, favorite: "" } },
  ];
  state.value = { ...state.value, favorite: id };
  saving.value = false;
}
</script>

<template>
  <div class="flex shrink-0 items-center" data-fase2-filters>
    <!-- Celular: só o ícone, com o número no canto. -->
    <NuxtDrawer
      v-model:open="phoneOpen"
      title="Filtros"
      :description="`O que esta lista mostra. ${count ? `${count} ativos.` : 'Nenhum ativo.'}`"
    >
      <NuxtChip :text="count || undefined" :show="count > 0" size="4xl" :inset="false" class="sm:hidden">
        <NuxtButton
          icon="i-lucide-sliders-horizontal"
          color="neutral"
          variant="outline"
          square
          :aria-label="triggerLabel"
          data-fase2-filters-phone
        />
      </NuxtChip>
      <template #body>
        <Fase2FilterPanel v-model="state" :config="config" :views="views" :can-save="canSave" @save="askSave" />
      </template>
      <template #footer>
        <div class="flex gap-2">
          <NuxtButton label="Limpar" color="neutral" variant="outline" size="xl" :disabled="!count" @click="clear" />
          <NuxtButton :label="`Ver ${resultCount} ${config.noun}`" size="xl" block @click="phoneOpen = false" />
        </div>
      </template>
    </NuxtDrawer>

    <!-- Mesa: ícone, nome e o mesmo número. -->
    <NuxtPopover v-model:open="deskOpen" :content="{ align: 'end' }">
      <NuxtChip :text="count || undefined" :show="count > 0" size="4xl" :inset="false" class="max-sm:hidden">
        <NuxtButton
          icon="i-lucide-sliders-horizontal"
          label="Filtros"
          color="neutral"
          variant="outline"
          :aria-label="triggerLabel"
          data-fase2-filters-desk
        />
      </NuxtChip>
      <template #content>
        <div class="w-96 max-w-[calc(100vw-2rem)]">
          <Fase2FilterPanel
            v-model="state"
            :config="config"
            :views="views"
            :can-save="canSave"
            clearable
            @save="askSave"
            @clear="clear"
          />
        </div>
      </template>
    </NuxtPopover>

    <NuxtModal v-model:open="saving" title="Salvar como favorito" :description="summary">
      <template #body>
        <form class="space-y-4" @submit.prevent="confirmSave">
          <NuxtFormField label="Nome do favorito" required>
            <NuxtInput v-model="name" placeholder="Ex.: iFood atrasados" class="w-full" autofocus />
          </NuxtFormField>
          <NuxtSwitch v-model="pinned" label="Mostrar nos filtros rápidos da tela" />
          <NuxtSwitch
            v-if="manager"
            v-model="shared"
            label="Publicar para a equipe"
            description="Todos da equipe passam a ver este favorito. Só o gerente publica."
          />
        </form>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton label="Cancelar" color="neutral" variant="ghost" @click="saving = false" />
          <NuxtButton label="Salvar favorito" :disabled="!name.trim()" @click="confirmSave" />
        </div>
      </template>
    </NuxtModal>
  </div>
</template>
