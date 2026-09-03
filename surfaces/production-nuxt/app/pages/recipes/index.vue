<script setup lang="ts">
// Inventário de receitas (/recipes) — a lista do conhecimento da casa. Busca,
// chips por tipo, os dois toggles que importam ("sem SKU" = receita ainda só
// conhecimento; "com rascunho" = alguém começou e não publicou) e as arquivadas
// fora da vista por padrão. O cartão diz o que o gestor procura de relance: tipo,
// SKU/produto, versão atual, hidratação. "Nova receita" só com `can_edit`.
import { isStale } from "~/presentation/production";
import { filterEntries } from "~/presentation/recipeBook";

useHead({ title: "Receitas · Produção" });

const route = useRoute();
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
const kind = ref(typeof route.query.kind === "string" ? route.query.kind : "");
const archived = ref(false);
const onlyWithoutSku = ref(false);
const onlyWithDraft = ref(false);

const { entries, kinds, canEdit, forbidden, pending, error, refresh } = useRecipeBook(query, kind, archived);

const visible = computed(() =>
  filterEntries(entries.value, query.value, kind.value, onlyWithoutSku.value, onlyWithDraft.value),
);
const hasFilters = computed(() => !!query.value.trim() || !!kind.value || onlyWithoutSku.value || onlyWithDraft.value);
const stale = computed(() => isStale({ error: !!error.value, hasData: entries.value.length > 0 }));

function clearFilters() {
  query.value = "";
  kind.value = "";
  onlyWithoutSku.value = false;
  onlyWithDraft.value = false;
}
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <RecipeHeader
      v-model:query="query"
      title="Inventário"
      searchable
      search-label="Buscar receita por nome, ref ou SKU"
      :pending="pending"
      @refresh="refresh()"
    >
      <template #actions>
        <NuxtLink
          v-if="canEdit"
          to="/recipes/new"
          class="inline-flex h-9 items-center gap-1.5 rounded-md border border-transparent bg-primary px-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
        >
          <Icon name="lucide:plus" class="size-4" />
          <span class="hidden sm:inline">Nova receita</span>
        </NuxtLink>
      </template>
    </RecipeHeader>

    <!-- Sem a permissão de leitura: explica com calma, sem beco. -->
    <section v-if="forbidden" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-lg border border-dashed p-10">
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
        <div
          v-if="kinds.length"
          class="flex flex-wrap items-center gap-1 rounded-lg border bg-background p-0.5"
          role="group"
          aria-label="Tipo de receita"
        >
          <button
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="
              kind === '' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            "
            :aria-pressed="kind === ''"
            @click="kind = ''"
          >
            Todas
          </button>
          <button
            v-for="option in kinds"
            :key="option.value"
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="
              kind === option.value
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            "
            :aria-pressed="kind === option.value"
            @click="kind = option.value"
          >
            {{ option.label }}
          </button>
        </div>

        <div class="ml-auto flex flex-wrap items-center gap-3">
          <label class="inline-flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
            <input v-model="onlyWithoutSku" type="checkbox" class="size-4 rounded border" />
            Sem SKU
          </label>
          <label class="inline-flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
            <input v-model="onlyWithDraft" type="checkbox" class="size-4 rounded border" />
            Com rascunho
          </label>
          <label class="inline-flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
            <input v-model="archived" type="checkbox" class="size-4 rounded border" />
            Arquivadas
          </label>
        </div>
      </div>

      <div
        v-if="stale"
        role="status"
        aria-live="polite"
        class="mb-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm font-medium text-amber-700 dark:text-amber-300"
      >
        <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
        <span>Sem atualizar. Mostrando a última lista carregada.</span>
      </div>

      <p v-if="pending && !entries.length" class="text-sm text-muted-foreground">Carregando…</p>

      <div
        v-else-if="error && !entries.length"
        class="grid place-items-center gap-2 rounded-lg border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
        <p class="text-base font-medium text-foreground">Não foi possível carregar as receitas.</p>
        <button
          type="button"
          class="mt-1 inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
          @click="refresh()"
        >
          <Icon name="lucide:refresh-cw" class="size-4" /> Tentar de novo
        </button>
      </div>

      <div
        v-else-if="!entries.length && !hasFilters"
        class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground"
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
        class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:search" class="size-8" />
        <p class="text-base font-medium">Nenhuma receita com esses filtros.</p>
        <button type="button" class="text-sm text-primary underline-offset-2 hover:underline" @click="clearFilters">
          Limpar filtros
        </button>
      </div>

      <div v-else class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        <NuxtLink
          v-for="entry in visible"
          :key="entry.ref"
          :to="`/recipes/${entry.ref}`"
          class="grid gap-2 rounded-lg border bg-card p-3 transition hover:border-primary/40 hover:bg-accent/30"
          :class="entry.is_archived ? 'opacity-70' : ''"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="truncate font-bold">{{ entry.name }}</p>
              <p class="truncate font-mono text-xs text-muted-foreground">{{ entry.ref }}</p>
            </div>
            <UiBadge variant="outline" class="shrink-0 px-1.5 py-0 text-xs">{{ entry.kind_label }}</UiBadge>
          </div>

          <p class="flex items-center gap-1.5 text-sm">
            <Icon name="lucide:tag" class="size-3.5 shrink-0 text-muted-foreground" />
            <template v-if="entry.output_sku">
              <span class="truncate">{{ entry.output_name || entry.output_sku }}</span>
              <span v-if="entry.output_name" class="hidden truncate font-mono text-xs text-muted-foreground sm:inline">{{
                entry.output_sku
              }}</span>
            </template>
            <span v-else class="text-amber-700 dark:text-amber-300">Sem SKU</span>
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
            <UiBadge v-if="entry.draft_count > 0" variant="warning" class="px-1.5 py-0 text-xs">
              {{ entry.draft_count === 1 ? "Rascunho" : `${entry.draft_count} rascunhos` }}
            </UiBadge>
            <UiBadge v-if="entry.is_archived" variant="outline" class="px-1.5 py-0 text-xs">Arquivada</UiBadge>
            <UiBadge v-if="!entry.has_ficha && entry.output_sku" variant="outline" class="px-1.5 py-0 text-xs"
              >Sem ficha</UiBadge
            >
          </div>

          <p v-if="entry.updated_at_display" class="text-xs text-muted-foreground">
            Atualizada {{ entry.updated_at_display }}
          </p>
        </NuxtLink>
      </div>
    </section>
  </main>
</template>
