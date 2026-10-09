<script setup lang="ts">
// Protótipo do `OperatorSavedFilters` (K4): "Favoritos" guarda o recorte atual da URL
// com um nome. Um favorito pode virar aba no filtro rápido ("Mostrar como aba"). No
// servidor, o modelo é o `BIView` generalizado (`SavedView`: dono, superfície, tela,
// nome, query, fixado). Se o dono escolher a opção 2 da pergunta 2, ganha `shared`.
import type { SavedView } from "../types/fase2";
import { computed, ref } from "vue";


const props = defineProps<{ views: readonly SavedView[]; currentSummary: string; canSave: boolean }>();
const emit = defineEmits<{
  apply: [id: string];
  save: [name: string, pinned: boolean];
  togglePin: [id: string];
}>();

const saving = ref(false);
const name = ref("");
const pinned = ref(true);

const items = computed(() => [
  props.views.length
    ? props.views.map((view) => ({
        label: view.name,
        description: view.summary,
        icon: view.pinned ? "i-lucide-star" : "i-lucide-bookmark",
        onSelect: () => emit("apply", view.id),
      }))
    : [{ label: "Nenhum favorito ainda", disabled: true }],
  [
    {
      label: "Salvar este recorte",
      icon: "i-lucide-bookmark-plus",
      disabled: !props.canSave,
      onSelect: () => {
        name.value = "";
        pinned.value = true;
        saving.value = true;
      },
    },
  ],
  props.views.length
    ? props.views.map((view) => ({
        label: view.pinned ? `Tirar "${view.name}" das abas` : `Mostrar "${view.name}" como aba`,
        icon: view.pinned ? "i-lucide-star-off" : "i-lucide-star",
        onSelect: () => emit("togglePin", view.id),
      }))
    : [],
]);

function confirm() {
  const value = name.value.trim();
  if (!value) return;
  emit("save", value, pinned.value);
  saving.value = false;
}
</script>

<template>
  <div data-fase2-saved-filters>
    <NuxtDropdownMenu :items="items" :content="{ align: 'end' }">
      <NuxtButton label="Favoritos" icon="i-lucide-bookmark" color="neutral" variant="outline" />
    </NuxtDropdownMenu>
    <NuxtModal v-model:open="saving" title="Salvar este recorte" :description="`Recorte: ${currentSummary}`">
      <template #body>
        <form class="space-y-4" @submit.prevent="confirm">
          <NuxtFormField label="Nome do favorito" required>
            <NuxtInput v-model="name" placeholder="Ex.: iFood atrasados" class="w-full" autofocus />
          </NuxtFormField>
          <NuxtSwitch v-model="pinned" label="Mostrar como aba no filtro rápido" />
        </form>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton label="Cancelar" color="neutral" variant="ghost" @click="saving = false" />
          <NuxtButton label="Salvar favorito" :disabled="!name.trim()" @click="confirm" />
        </div>
      </template>
    </NuxtModal>
  </div>
</template>
