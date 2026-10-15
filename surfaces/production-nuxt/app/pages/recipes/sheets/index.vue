<script setup lang="ts">
import { alertActions } from "../../../../../operator-kit/app/utils/alertActions";
// Fichas de execução (/recipes/sheets) — o cadastro DIRETO de craftsman.Recipe
// + RecipeItem, distinto do inventário de fórmulas (/recipes). A lista busca,
// recorta por situação e ordena no servidor; o casco canônico do kit conduz o
// criar/editar e o duplicar. É o cadastro que o Admin sempre teve e que a
// Produção passa a ter; a publicação de uma versão continua reescrevendo a
// ficha pelo mesmo caminho canônico.
import type { RecipeSheetCardProjection, RecipeSheetDetailProjection, RecipeSheetDuplicatePayload, RecipeSheetPayload } from "~/types/recipeBook";
import { isStale } from "~/presentation/production";
import { SHEET_ACTIVE_OPTIONS, SHEET_SORT_OPTIONS } from "~/presentation/recipeSheet";

useHead({ title: "Fichas de execução" });

const route = useRoute();
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
const active = ref("");
const sort = ref("updated");
const page = ref(1);

const { cards, total, pageSize, canEdit, forbidden, pending, error, refresh, busy, createSheet, updateSheet, duplicateSheet, fetchSheet } =
  useRecipeSheets(query, { active, sort, page });

const stale = computed(() => isStale({ error: !!error.value, hasData: cards.value.length > 0 }));
const sortItems = [...SHEET_SORT_OPTIONS];
const activeItems = [...SHEET_ACTIVE_OPTIONS];
watch([query, active, sort], () => {
  page.value = 1;
});

const formOpen = ref(false);
const editing = ref<RecipeSheetDetailProjection | null>(null);
const duplicateOpen = ref(false);
const duplicating = ref<RecipeSheetDetailProjection | null>(null);
const duplicateKey = ref(newMutationKey());

function newMutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? Date.now() + "-" + Math.random().toString(16).slice(2);
}

function openCreate() {
  editing.value = null;
  formOpen.value = true;
}
async function openEdit(card: RecipeSheetCardProjection) {
  const detail = await fetchSheet(card.ref);
  if (!detail) return;
  editing.value = detail;
  formOpen.value = true;
}
async function openDuplicate(card: RecipeSheetCardProjection) {
  const detail = await fetchSheet(card.ref);
  if (!detail) return;
  duplicating.value = detail;
  duplicateKey.value = newMutationKey();
  duplicateOpen.value = true;
}

async function saveForm(payload: RecipeSheetPayload) {
  const result = editing.value ? await updateSheet(editing.value.ref, payload) : await createSheet(payload);
  if (!result.ok) return;
  formOpen.value = false;
  useSonner.success(editing.value ? "Ficha salva." : "Ficha criada.");
}
async function saveDuplicate(payload: RecipeSheetDuplicatePayload) {
  if (!duplicating.value) return;
  const result = await duplicateSheet(duplicating.value.ref, payload, duplicateKey.value);
  if (!result.ok && !result.uncertain) duplicateKey.value = newMutationKey();
  if (result.ok) {
    duplicateOpen.value = false;
    useSonner.success("Cópia criada inativa.");
  }
}

// O link "Abrir ficha" da receita chega com ?open=<ref> e abre a edição direto.
onMounted(async () => {
  const wanted = typeof route.query.open === "string" ? route.query.open : "";
  if (!wanted) return;
  const detail = await fetchSheet(wanted);
  if (!detail) return;
  editing.value = detail;
  formOpen.value = true;
});
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <RecipeHeader
      v-model:query="query"
      title="Fichas de execução"
      subtitle="o BOM que a produção executa"
      back="/recipes"
      searchable
      search-label="Buscar ficha por nome, ref ou SKU"
      :pending="pending"
      :primary="canEdit ? { label: 'Nova ficha', icon: 'i-lucide-plus', onSelect: openCreate } : undefined"
      @refresh="refresh()"
    />

    <section v-if="forbidden" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-md border border-dashed p-10">
        <Icon name="lucide:lock" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Área da produção</p>
        <p class="text-sm text-muted-foreground">As fichas de execução pedem uma permissão que este operador não tem.</p>
        <NuxtLink to="/" class="mt-1 text-sm text-primary underline-offset-2 hover:underline">Voltar para a produção</NuxtLink>
      </div>
    </section>

    <section v-else class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <NuxtSelect v-model="active" :items="activeItems" value-key="value" label-key="label" class="w-40" aria-label="Situação da ficha" />
        <NuxtSelect v-model="sort" :items="sortItems" value-key="value" label-key="label" class="w-56" aria-label="Ordenar fichas" />
        <NuxtLink to="/recipes" class="ml-auto text-sm text-primary underline-offset-2 hover:underline">Inventário de fórmulas</NuxtLink>
      </div>

      <NuxtAlert
        v-if="stale"
        class="mb-3"
        color="warning"
        variant="subtle"
        icon="i-lucide-wifi-off"
        title="Sem atualizar. Mostrando a última lista carregada."
        :actions="alertActions('warning', [{ label: 'Tentar de novo', onClick: () => refresh() }])"
        role="status"
        aria-live="polite"
      />

      <p v-if="pending && !cards.length" class="text-sm text-muted-foreground">Carregando…</p>

      <div
        v-else-if="error && !cards.length"
        class="grid place-items-center gap-2 rounded-md border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
        <p class="text-base font-medium text-foreground">Não foi possível carregar as fichas.</p>
        <NuxtButton class="mt-1" color="neutral" variant="outline" icon="i-lucide-refresh-cw" label="Tentar de novo" @click="refresh()" />
      </div>

      <div v-else-if="!cards.length" class="grid place-items-center gap-2 rounded-md border border-dashed py-16 text-center text-muted-foreground">
        <Icon name="lucide:clipboard-list" class="size-8" />
        <p class="text-base font-medium">Nenhuma ficha ainda.</p>
        <p class="text-sm">A ficha é o BOM que a produção executa; a fórmula publicada também a escreve.</p>
      </div>

      <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        <NuxtCard v-for="card in cards" :key="card.ref" :ui="{ body: 'grid gap-2 p-3' }">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="truncate font-bold">{{ card.name }}</p>
              <p class="truncate font-mono text-xs text-muted-foreground">{{ card.ref }}</p>
            </div>
            <NuxtBadge :color="card.is_active ? 'success' : 'neutral'" :label="card.is_active ? 'Ativa' : 'Inativa'" />
          </div>

          <p class="flex items-center gap-1.5 text-sm">
            <Icon name="lucide:tag" class="size-3.5 shrink-0 text-muted-foreground" />
            <template v-if="card.output_sku">
              <span class="truncate">{{ card.output_name || card.output_sku }}</span>
              <span v-if="card.output_name" class="hidden truncate font-mono text-xs text-muted-foreground sm:inline">{{ card.output_sku }}</span>
            </template>
            <span v-else class="text-warning">Sem SKU</span>
          </p>

          <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span class="tabular-nums">Rende <b class="text-foreground">{{ card.batch_size }}</b></span>
            <span>{{ card.item_count === 1 ? '1 ingrediente' : card.item_count + ' ingredientes' }}</span>
            <NuxtBadge v-if="card.has_entry" color="neutral" label="Do inventário" />
          </div>

          <div class="mt-1 flex flex-wrap items-center gap-1.5">
            <NuxtButton v-if="canEdit" color="neutral" variant="outline" icon="i-lucide-pencil" label="Editar" @click="openEdit(card)" />
            <NuxtButton v-if="canEdit" color="neutral" variant="outline" icon="i-lucide-copy-plus" label="Duplicar" @click="openDuplicate(card)" />
          </div>
        </NuxtCard>
      </div>

      <div v-if="total > pageSize" class="mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <p class="text-xs text-muted-foreground tabular-nums">{{ total }} fichas · página {{ page }}</p>
        <NuxtPagination v-model:page="page" :total="total" :items-per-page="pageSize" :sibling-count="1" aria-label="Páginas de fichas" />
      </div>
    </section>

    <RecipeSheetFormPanel v-model:open="formOpen" :sheet="editing" :busy="busy" @save="saveForm" />
    <RecipeSheetDuplicatePanel v-model:open="duplicateOpen" :source="duplicating" :busy="busy" @save="saveDuplicate" />
  </main>
</template>
