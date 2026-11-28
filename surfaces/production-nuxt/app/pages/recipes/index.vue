<script setup lang="ts">
import { alertActions } from "../../../../operator-kit/app/utils/alertActions";
import type { QuickFilterItem } from "../../../../operator-kit/app/presentation/quickFilters";
import type { ActiveFilters, FilterDimension } from "../../../../operator-kit/app/types/filters";
// Receitas (/recipes) — as fichas técnicas que guardam o conhecimento da casa. Busca,
// chips por tipo, os dois toggles que importam ("sem SKU" = receita ainda só
// conhecimento; "com rascunho" = alguém começou e não publicou) e as arquivadas
// fora da vista por padrão. O cartão diz o que o gestor procura de relance: tipo,
// SKU/produto, versão atual, hidratação. "Nova receita" só com `can_edit`. A estrela
// é de cada operador (pede só a leitura), e "Favoritas" filtra as dele.
import { isStale } from "~/presentation/production";
import {
  PRODUCTION_MODE_ALL,
  PRODUCTION_MODE_FILTER_OPTIONS,
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
// KISS (28/11): a barra tem no máximo 5 controles. Ficam à vista os dois recortes de
// toda hora; "Sem SKU" e "Com rascunho" moram no painel de Filtros. "Não conferidas"
// e "Receitas a conferir" eram o MESMO conjunto em dois controles: o recorte fica, e a
// passada uma a uma (/recipes/review) aparece só com ele ligado.
const quickItems = [
  { key: "favorites", label: "Favoritas", icon: "i-lucide-star" },
  { key: "unreviewed", label: "Não conferidas", icon: "i-lucide-badge-alert" },
] satisfies QuickFilterItem[];
const quickSelection = computed<string[]>({
  get: () => [
    ...(onlyFavorites.value ? ["favorites"] : []),
    ...(onlyUnreviewed.value ? ["unreviewed"] : []),
  ],
  set: (next) => {
    onlyFavorites.value = next.includes("favorites");
    onlyUnreviewed.value = next.includes("unreviewed");
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
  { id: "without_sku", label: "Sem SKU", type: "boolean", options: [] },
  { id: "with_draft", label: "Com rascunho", type: "boolean", options: [] },
  { id: "archived", label: "Arquivadas", type: "boolean", options: [] },
]);
const panelFilters = computed<ActiveFilters>({
  get: () => ({
    ...(kind.value ? { kind: [kind.value] } : {}),
    ...(mode.value !== PRODUCTION_MODE_ALL ? { mode: [mode.value] } : {}),
    ...(onlyWithoutSku.value ? { without_sku: ["true"] } : {}),
    ...(onlyWithDraft.value ? { with_draft: ["true"] } : {}),
    ...(archived.value ? { archived: ["true"] } : {}),
  }),
  set: (next) => {
    kind.value = next.kind?.[0] ?? "";
    mode.value = next.mode?.[0] ?? PRODUCTION_MODE_ALL;
    onlyWithoutSku.value = next.without_sku?.[0] === "true";
    onlyWithDraft.value = next.with_draft?.[0] === "true";
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
  if (onlyWithoutSku.value) filters.push({
    key: "without_sku",
    label: "Sem SKU",
    remove: () => { onlyWithoutSku.value = false; },
  });
  if (onlyWithDraft.value) filters.push({
    key: "with_draft",
    label: "Com rascunho",
    remove: () => { onlyWithDraft.value = false; },
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
      title="Receitas"
      searchable
      search-label="Buscar receita por nome, ref ou SKU"
      :pending="pending"
      :primary="canEdit ? { label: 'Nova receita', icon: 'i-lucide-plus', to: '/recipes/new' } : undefined"
      :active-filters="activeFilters"
      :clear-filters="clearFilters"
      @refresh="refresh()"
    >
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
          v-if="onlyUnreviewed"
          to="/recipes/review"
          color="neutral"
          variant="outline"
          icon="i-lucide-badge-check"
          label="Conferir uma a uma"
          data-recipe-review-pass
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
          As receitas pedem uma permissão que este operador não tem. Peça a liberação a quem administra
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
        description="Cadastre a primeira ficha técnica com ingredientes, rendimento e modo de preparo."
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
          class="relative h-full overflow-hidden rounded-xl border border-border bg-card transition hover:border-primary/40 focus-within:border-primary/40"
          :class="!entry.is_active ? 'opacity-70' : ''"
          data-recipe-card
        >
          <!-- A estrela e o Editar moram AO LADO do link, numa coluna à direita: nenhuma
               parte do link fica sob eles, e o Editar divide a linha das etiquetas em vez
               de ganhar um rodapé (KISS, 28/11: o dobro de receitas na tela). -->
          <div class="flex h-full min-w-0 items-stretch">
            <NuxtLink
              :to="`/recipes/${entry.ref}`"
              class="grid min-w-0 flex-1 grid-cols-1 content-start gap-2 self-stretch p-3 transition hover:bg-accent/30"
            >
              <div class="flex items-start justify-between gap-2">
                <p class="min-w-0 truncate font-bold">{{ entry.name }}</p>
                <NuxtBadge color="neutral" class="shrink-0" :label="entry.kind_label" />
              </div>

              <!-- KISS (dono, 28/11): o cartão é o nome, o tipo e o que pede atenção. O
                   produto só aparece quando não é o mesmo nome da receita (ou falta);
                   o código interno, a versão e a data moram na receita. -->
              <p
                v-if="!entry.output_sku || (entry.output_name && entry.output_name !== entry.name)"
                class="flex items-center gap-1.5 text-sm"
                data-recipe-output
              >
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
                <span v-if="!entry.current_version_number">Sem versão publicada</span>
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
                <NuxtBadge v-if="!entry.is_active" color="neutral" label="Arquivada" />
                <!-- O selo é curto (sai em sentença); quem tomou o SKU vai na frase ao lado. -->
                <NuxtBadge v-if="entry.ficha_status_label" color="neutral" :label="entry.ficha_status_label" />
                <span v-if="entry.ficha_status_detail" data-recipe-ficha-detail>{{ entry.ficha_status_detail }}</span>
                <NuxtBadge
                  v-if="needsReview(entry.review_status)"
                  :color="entry.review_status === 'changed' ? 'warning' : 'neutral'"
                  :label="entry.review_label"
                  :title="entry.provenance_label"
                />
              </div>
            </NuxtLink>
            <div class="flex shrink-0 flex-col items-end justify-between gap-1 p-1">
            <NuxtButton
              color="neutral"
              variant="ghost"
              square
              :active="entry.is_favorite"
              active-color="primary"
              active-variant="ghost"
              class="shrink-0 pointer-coarse:size-control pointer-coarse:justify-center"
              :aria-pressed="entry.is_favorite"
              :aria-label="favoriteToggleLabel(entry.name)"
              :title="favoriteActionHint(entry.is_favorite)"
              :disabled="isFavoriteBusy(entry.ref)"
              @click="toggleFavorite(entry.ref, !entry.is_favorite)"
            >
              <Icon name="lucide:star" class="size-5" :class="entry.is_favorite ? 'fill-current' : ''" />
            </NuxtButton>
            <NuxtButton
              v-if="canEdit && entry.is_active"
              :to="`/recipes/${entry.ref}/edit`"
              color="neutral"
              variant="ghost"
              icon="i-lucide-pencil-line"
              label="Editar"
              :aria-label="`Editar ${entry.name}`"
              data-recipe-edit
            />
            </div>
          </div>
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
