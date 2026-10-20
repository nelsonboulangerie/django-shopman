<script setup lang="ts">
import { alertActions } from "../../../../operator-kit/app/utils/alertActions";
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
  mode.value = PRODUCTION_MODE_ALL;
  page.value = 1;
}
const ALL_KINDS = "__all__";
const kindItems = computed(() => [{ value: ALL_KINDS, label: "Todas" }, ...kinds.value]);
const kindChoice = computed({
  get: () => kind.value || ALL_KINDS,
  set: (value: string) => {
    kind.value = value === ALL_KINDS ? "" : value;
  },
});
const sortItems = [
  { value: "updated", label: "Atualizadas recentemente" },
  { value: "name", label: "Nome" },
  { value: "kind", label: "Tipo e nome" },
];
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
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <!-- O tipo é escolha de uma lista que cresce com o cadastro: `NuxtSelect`. -->
        <NuxtSelect
          v-if="kinds.length"
          v-model="kindChoice"
          :items="kindItems"
          value-key="value"
          class="w-48"
          aria-label="Tipo de receita"
        />
        <NuxtSelect
          v-model="mode"
          :items="modeItems"
          value-key="value"
          label-key="label"
          class="w-44"
          aria-label="Modo de produção"
        />
        <NuxtSelect
          v-model="sort"
          :items="sortItems"
          value-key="value"
          label-key="label"
          class="w-56"
          aria-label="Ordenar receitas"
        />

        <NuxtButton
          to="/recipes/review"
          color="primary"
          variant="ghost"
          icon="i-lucide-badge-check"
          label="Conferência"
        />

        <div class="ml-auto flex flex-wrap items-center gap-3">
          <NuxtCheckbox v-model="onlyFavorites" label="Favoritas" />
          <NuxtCheckbox v-model="onlyUnreviewed" label="Não conferidas" />
          <NuxtCheckbox v-model="onlyWithoutSku" label="Sem SKU" />
          <NuxtCheckbox v-model="onlyWithDraft" label="Com rascunho" />
          <NuxtCheckbox v-model="archived" label="Arquivadas" />
        </div>
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

      <p v-if="pending && !entries.length" class="text-sm text-muted-foreground">Carregando…</p>

      <div
        v-else-if="error && !entries.length"
        class="grid place-items-center gap-2 rounded-md border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
        <p class="text-base font-medium text-foreground">Não foi possível carregar as receitas.</p>
        <NuxtButton
          class="mt-1"
          color="neutral"
          variant="outline"
          icon="i-lucide-refresh-cw"
          label="Tentar de novo"
          @click="refresh()"
        />
      </div>

      <div
        v-else-if="!entries.length && !hasFilters"
        class="grid place-items-center gap-2 rounded-md border border-dashed py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:book-open" class="size-8" />
        <p class="text-base font-medium">Nenhuma receita ainda.</p>
        <p class="text-sm">As fichas que já existem entram sozinhas; as novas nascem de uma anotação, uma foto ou à mão.</p>
        <NuxtLink v-if="canEdit" to="/recipes/new" class="mt-1 text-sm text-primary underline-offset-2 hover:underline"
          >Nova receita</NuxtLink
        >
      </div>

      <div
        v-else-if="!visible.length"
        class="grid place-items-center gap-2 rounded-md border border-dashed py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:search" class="size-8" />
        <p class="text-base font-medium">Nenhuma receita com esses filtros.</p>
        <NuxtButton color="primary" variant="ghost" label="Limpar filtros" @click="clearFilters" />
      </div>

      <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        <!-- A estrela fica FORA do link (botão dentro de <a> não é HTML válido) e por cima do canto do cartão. -->
        <div v-for="entry in visible" :key="entry.ref" class="relative">
          <NuxtLink
            :to="`/recipes/${entry.ref}`"
            class="grid h-full min-w-0 grid-cols-1 gap-2 rounded-xl border border-border bg-card p-3 transition hover:border-primary/40 hover:bg-accent/30"
            :class="!entry.is_active ? 'opacity-70' : ''"
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
