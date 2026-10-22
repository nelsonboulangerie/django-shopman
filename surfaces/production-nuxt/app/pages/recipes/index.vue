<script setup lang="ts">
import { alertActions } from "../../../../operator-kit/app/utils/alertActions";
import type { QuickFilterItem } from "../../../../operator-kit/app/presentation/quickFilters";
import type { ActiveFilters, FilterDimension } from "../../../../operator-kit/app/types/filters";
// Inventário de receitas (/recipes) — a lista do conhecimento da casa. Busca,
// chips por tipo, os dois toggles que importam ("sem SKU" = receita ainda só
// conhecimento; "com rascunho" = alguém começou e não publicou) e as arquivadas
// fora da vista por padrão. O cartão diz o que o gestor procura de relance: tipo,
// SKU/produto, versão atual, hidratação. "Nova receita" só com `can_edit`. A estrela
// é de cada operador (pede só a leitura), e "Favoritas" filtra as dele.
import { isStale } from "~/presentation/production";
import {
  PRODUCTION_MODE_ALL,
  PRODUCTION_MODE_FILTER_OPTIONS,
  PRODUCTION_MODE_MADE_TO_ORDER,
  favoriteActionHint,
  favoriteToggleLabel,
  filterEntries,
  needsReview,
} from "~/presentation/recipeBook";

useHead({ title: "Receitas" });

const route = useRoute();
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
const kind = ref(typeof route.query.kind === "string" ? route.query.kind : "");
const archived = ref(false);
const onlyWithoutSku = ref(false);
const onlyWithDraft = ref(false);
const onlyFavorites = ref(false);
const onlyUnreviewed = ref(route.query.unreviewed === "1");
const mode = ref(typeof route.query.mode === "string" ? route.query.mode : PRODUCTION_MODE_ALL);
const modeItems = [...PRODUCTION_MODE_FILTER_OPTIONS];
const sort = ref("updated");
const page = ref(1);

const { entries, kinds, total, pageSize, canEdit, forbidden, pending, error, refresh, toggleFavorite, isFavoriteBusy } = useRecipeBook(
  query,
  kind,
  archived,
  {
    withoutSku: onlyWithoutSku,
    withDraft: onlyWithDraft,
    favorites: onlyFavorites,
    unreviewed: onlyUnreviewed,
    mode,
    sort,
    page,
  },
);

// O servidor entrega só a página e o recorte pedidos. Repetir o predicado aqui
// evita um flash incoerente enquanto a próxima resposta está em voo.
const visible = computed(() => filterEntries(
  entries.value,
  query.value,
  kind.value,
  onlyWithoutSku.value,
  onlyWithDraft.value,
  onlyFavorites.value,
  onlyUnreviewed.value,
  mode.value,
));
const hasFilters = computed(
  () =>
    !!query.value.trim() ||
    !!kind.value ||
    onlyWithoutSku.value ||
    onlyWithDraft.value ||
    onlyFavorites.value ||
    onlyUnreviewed.value ||
    archived.value ||
    mode.value !== PRODUCTION_MODE_ALL,
);
const stale = computed(() => isStale({ error: !!error.value, hasData: entries.value.length > 0 }));

function clearFilters() {
  query.value = "";
  kind.value = "";
  onlyWithoutSku.value = false;
  onlyWithDraft.value = false;
  onlyFavorites.value = false;
  onlyUnreviewed.value = false;
  archived.value = false;
  mode.value = PRODUCTION_MODE_ALL;
  page.value = 1;
}
const sortItems = [
  { value: "updated", label: "Atualizadas recentemente" },
  { value: "name", label: "Nome" },
  { value: "kind", label: "Tipo e nome" },
];
const quickItems = [
  { key: "favorites", label: "Favoritas", icon: "i-lucide-star" },
  { key: "unreviewed", label: "Não conferidas", icon: "i-lucide-badge-alert" },
  { key: "without_sku", label: "Sem SKU", icon: "i-lucide-tag" },
  { key: "with_draft", label: "Com rascunho", icon: "i-lucide-file-pen-line" },
] satisfies QuickFilterItem[];
const quickSelection = computed<string[]>({
  get: () => [
    ...(onlyFavorites.value ? ["favorites"] : []),
    ...(onlyUnreviewed.value ? ["unreviewed"] : []),
    ...(onlyWithoutSku.value ? ["without_sku"] : []),
    ...(onlyWithDraft.value ? ["with_draft"] : []),
  ],
  set: (next) => {
    onlyFavorites.value = next.includes("favorites");
    onlyUnreviewed.value = next.includes("unreviewed");
    onlyWithoutSku.value = next.includes("without_sku");
    onlyWithDraft.value = next.includes("with_draft");
  },
});
const panelDimensions = computed<FilterDimension[]>(() => [
  { id: "kind", label: "Tipo de receita", type: "single-select", options: kinds.value },
  {
    id: "mode",
    label: "Modo de produção",
    type: "single-select",
    options: modeItems.filter((option) => option.value !== PRODUCTION_MODE_ALL),
  },
  { id: "archived", label: "Arquivadas", type: "boolean", options: [] },
]);
const panelFilters = computed<ActiveFilters>({
  get: () => ({
    ...(kind.value ? { kind: [kind.value] } : {}),
    ...(mode.value !== PRODUCTION_MODE_ALL ? { mode: [mode.value] } : {}),
    ...(archived.value ? { archived: ["true"] } : {}),
  }),
  set: (next) => {
    kind.value = next.kind?.[0] ?? "";
    mode.value = next.mode?.[0] ?? PRODUCTION_MODE_ALL;
    archived.value = next.archived?.[0] === "true";
  },
});
const activeFilters = computed(() => {
  const filters = quickItems
    .filter((item) => quickSelection.value.includes(item.key))
    .map((item) => ({
      key: item.key,
      label: item.label,
      remove: () => { quickSelection.value = quickSelection.value.filter((key) => key !== item.key); },
    }));
  if (kind.value) filters.push({
    key: "kind",
    label: `Tipo: ${kinds.value.find((option) => option.value === kind.value)?.label ?? kind.value}`,
    remove: () => { kind.value = ""; },
  });
  if (mode.value !== PRODUCTION_MODE_ALL) filters.push({
    key: "mode",
    label: modeItems.find((option) => option.value === mode.value)?.label ?? mode.value,
    remove: () => { mode.value = PRODUCTION_MODE_ALL; },
  });
  if (archived.value) filters.push({
    key: "archived",
    label: "Inclui arquivadas",
    remove: () => { archived.value = false; },
  });
  return filters;
});
watch([query, kind, archived, onlyWithoutSku, onlyWithDraft, onlyFavorites, onlyUnreviewed, mode, sort], () => {
  page.value = 1;
});

// A trilha da lista (`OperatorRecordNav` na receita): grava a ordem que a pessoa vê,
// com o recorte e a busca dela, para a receita oferecer anterior e próxima.
const { remember: rememberTrail } = useRecordTrail("production-recipes");
const trailLabel = computed(
  () => kinds.value.find((option) => option.value === kind.value)?.label ?? (onlyFavorites.value ? "Favoritas" : "Receitas"),
);
const trailFrom = computed(() => {
  const params = new URLSearchParams();
  if (query.value.trim()) params.set("q", query.value.trim());
  if (kind.value) params.set("kind", kind.value);
  if (onlyWithoutSku.value) params.set("without_sku", "1");
  if (onlyWithDraft.value) params.set("with_draft", "1");
  if (onlyFavorites.value) params.set("favorites", "1");
  if (onlyUnreviewed.value) params.set("unreviewed", "1");
  if (archived.value) params.set("archived", "1");
  if (mode.value !== PRODUCTION_MODE_ALL) params.set("mode", mode.value);
  if (sort.value !== "updated") params.set("sort", sort.value);
  if (page.value > 1) params.set("page", String(page.value));
  const search = params.toString();
  return search ? `/recipes?${search}` : "/recipes";
});
watch(
  () => [visible.value.map((entry) => entry.ref).join("\n"), trailFrom.value, trailLabel.value] as const,
  ([refs, from, label]) => rememberTrail(refs ? refs.split("\n") : [], { from, label }),
  { immediate: true },
);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <RecipeHeader
      v-model:query="query"
      title="Inventário"
      searchable
      search-label="Buscar receita por nome, ref ou SKU"
      :pending="pending"
      :primary="canEdit ? { label: 'Nova receita', icon: 'i-lucide-plus', to: '/recipes/new' } : undefined"
      :active-filters="activeFilters"
      :clear-filters="clearFilters"
      @refresh="refresh()"
    >
      <template #actions>
        <NuxtButton
          to="/recipes/sheets"
          color="neutral"
          variant="outline"
          icon="i-lucide-clipboard-list"
          label="Fichas de execução"
        />
      </template>
      <template #filters-primary>
        <OperatorQuickFilters
          v-model="quickSelection"
          :items="quickItems"
          multiple
          label="Recortes das receitas"
          data-recipe-quick-filters
        />
      </template>
      <template #filter-panel>
        <OperatorFilterPanel
          v-model="panelFilters"
          :dimensions="panelDimensions"
          :chips="false"
          data-recipe-filter-panel
        />
      </template>
      <template #filters>
        <NuxtButton
          to="/recipes/review"
          color="neutral"
          variant="outline"
          icon="i-lucide-badge-check"
          label="Conferência"
        />
        <NuxtSelect
          v-model="sort"
          :items="sortItems"
          value-key="value"
          label-key="label"
          class="w-56"
          aria-label="Ordenar receitas"
        />
      </template>
      <template #filters-end>
        <p v-if="total" class="text-xs text-muted-foreground tabular-nums">
          {{ total === 1 ? "1 receita" : `${total} receitas` }}
        </p>
      </template>
    </RecipeHeader>

    <!-- Sem a permissão de leitura: explica com calma, sem beco. -->
    <section v-if="forbidden" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-md border border-dashed p-10">
        <Icon name="lucide:lock" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Área da produção</p>
        <p class="text-sm text-muted-foreground">
          O inventário de receitas pede uma permissão que este operador não tem. Peça a liberação a quem administra
          a loja.
        </p>
        <NuxtLink to="/" class="mt-1 text-sm text-primary underline-offset-2 hover:underline"
          >Voltar para a produção</NuxtLink
        >
      </div>
    </section>

    <section v-else class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
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

      <OperatorScreenState v-if="pending && !entries.length" state="loading" what="as receitas" />

      <OperatorScreenState
        v-else-if="error && !entries.length"
        state="error"
        what="as receitas"
        @retry="refresh()"
      />

      <OperatorScreenState
        v-else-if="!entries.length && !hasFilters"
        state="empty"
        title="Nenhuma receita cadastrada."
        description="Cadastre a primeira receita para guardar fórmulas, versões e fichas de execução."
        icon="i-lucide-book-open"
      >
        <template v-if="canEdit" #actions>
          <NuxtButton to="/recipes/new" icon="i-lucide-plus" label="Nova receita" />
        </template>
      </OperatorScreenState>

      <OperatorScreenState
        v-else-if="!visible.length"
        state="empty"
        title="Nenhuma receita corresponde aos filtros."
        description="Retire um recorte ou faça outra busca."
        icon="i-lucide-search"
      >
        <template #actions>
          <NuxtButton color="neutral" variant="outline" label="Limpar filtros" @click="clearFilters" />
        </template>
      </OperatorScreenState>

      <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        <!-- As ações ficam FORA do link principal: nenhum controle interativo aninhado em <a>. -->
        <div
          v-for="entry in visible"
          :key="entry.ref"
          class="relative grid h-full grid-rows-[1fr_auto] overflow-hidden rounded-xl border border-border bg-card transition hover:border-primary/40 focus-within:border-primary/40"
          :class="!entry.is_active ? 'opacity-70' : ''"
          data-recipe-card
        >
          <NuxtLink
            :to="`/recipes/${entry.ref}`"
            class="grid min-w-0 grid-cols-1 content-start gap-2 p-3 transition hover:bg-accent/30"
          >
            <div class="flex items-start justify-between gap-2 pr-10">
              <div class="min-w-0">
                <p class="truncate font-bold">{{ entry.name }}</p>
                <p class="truncate font-mono text-xs text-muted-foreground">{{ entry.ref }}</p>
              </div>
              <NuxtBadge color="neutral" class="shrink-0" :label="entry.kind_label" />
            </div>

            <p class="flex items-center gap-1.5 text-sm">
              <Icon name="lucide:tag" class="size-3.5 shrink-0 text-muted-foreground" />
              <template v-if="entry.output_sku">
                <span class="truncate">{{ entry.output_name || entry.output_sku }}</span>
                <span v-if="entry.output_name" class="hidden truncate font-mono text-xs text-muted-foreground sm:inline">{{
                  entry.output_sku
                }}</span>
              </template>
              <span v-else class="text-warning">Sem SKU</span>
            </p>

            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span v-if="entry.current_version_number" class="tabular-nums">
                Versão atual <b class="text-foreground">{{ entry.current_version_number }}</b>
                <span v-if="entry.version_count > 1"> de {{ entry.version_count }}</span>
              </span>
              <span v-else>Sem versão publicada</span>
              <span v-if="entry.hydration_display" class="tabular-nums">
                Hidratação <b class="text-foreground">{{ entry.hydration_display }}</b>
              </span>
              <span
                v-if="entry.rating_display"
                class="tabular-nums"
                :title="entry.rating_count === 1 ? '1 avaliação da versão atual' : `${entry.rating_count} avaliações da versão atual`"
              >
                Nota <b class="text-foreground">{{ entry.rating_display }}</b> de 5
              </span>
              <NuxtBadge
                v-if="entry.draft_count > 0"
                color="warning"
                :label="entry.draft_count === 1 ? 'Rascunho' : `${entry.draft_count} rascunhos`"
              />
              <NuxtBadge
                v-if="entry.production_mode === PRODUCTION_MODE_MADE_TO_ORDER"
                color="primary"
                icon="i-lucide-coffee"
                :label="entry.production_mode_label"
              />
              <NuxtBadge v-if="!entry.is_active" color="neutral" label="Arquivada" />
              <NuxtBadge v-if="!entry.has_ficha && entry.output_sku" color="neutral" label="Sem ficha" />
              <NuxtBadge
                v-if="needsReview(entry.review_status)"
                :color="entry.review_status === 'changed' ? 'warning' : 'neutral'"
                :label="entry.review_label"
                :title="entry.provenance_label"
              />
            </div>

            <p v-if="entry.updated_at_display" class="text-xs text-muted-foreground">
              Atualizada {{ entry.updated_at_display }}
            </p>
          </NuxtLink>
          <div v-if="canEdit && entry.is_active" class="flex justify-end border-t border-border px-2 py-1.5">
            <NuxtButton
              :to="`/recipes/${entry.ref}/edit`"
              color="neutral"
              variant="ghost"
              icon="i-lucide-pencil-line"
              label="Editar receita"
              data-recipe-edit
            />
          </div>
          <NuxtButton
            color="neutral"
            variant="ghost"
            square
            :active="entry.is_favorite"
            active-color="primary"
            active-variant="ghost"
            class="absolute right-1 top-1 pointer-coarse:size-control pointer-coarse:justify-center"
            :aria-pressed="entry.is_favorite"
            :aria-label="favoriteToggleLabel(entry.name)"
            :title="favoriteActionHint(entry.is_favorite)"
            :disabled="isFavoriteBusy(entry.ref)"
            @click="toggleFavorite(entry.ref, !entry.is_favorite)"
          >
            <Icon name="lucide:star" class="size-5" :class="entry.is_favorite ? 'fill-current' : ''" />
          </NuxtButton>
        </div>
      </div>

      <div v-if="total > pageSize" class="mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <p class="text-xs text-muted-foreground tabular-nums">
          {{ total }} receitas · página {{ page }}
        </p>
        <NuxtPagination
          v-model:page="page"
          :total="total"
          :items-per-page="pageSize"
          :sibling-count="1"
          aria-label="Páginas de receitas"
        />
      </div>
    </section>
  </main>
</template>
