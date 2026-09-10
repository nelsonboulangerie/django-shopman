<script setup lang="ts">
import type { MarketingHistoryFilterName } from "~/composables/useCampaignHistory";
import {
  historyActorLabel,
  historyHref,
  historyLinkLabel,
  historyOccurredAt,
  historySubject,
} from "~/presentation/marketingHistory";
import {
  deliveryCountItems,
  deliveryStatePresentation,
  marketingLoadError,
  platformResultLabel,
} from "~/presentation/marketingResult";
import { scheduleSummary } from "~/utils/marketingSchedule";

const {
  announcements,
  actions,
  filters,
  hasActiveFilters,
  hasMore,
  shopTimezone,
  loading,
  loadingMore,
  error,
  loadMoreError,
  loadMore,
  refresh,
  setFilter,
  clearFilters,
} = useCampaignHistory();

const loadFailure = computed(() =>
  marketingLoadError(error.value || loadMoreError.value),
);

const FILTERS = [
  {
    name: "outcome",
    label: "Situação",
    options: [
      ["", "Todas"],
      ["not_started", "Ainda não iniciada"],
      ["fanout_pending", "Preparando destinos"],
      ["delivering", "Em andamento"],
      ["succeeded", "Concluída"],
      ["completed_with_failures", "Concluída com falhas"],
      ["unknown", "Resultado incerto"],
      ["cancelled", "Cancelada"],
      ["expired", "Expirada"],
      ["legacy_untracked", "Registro antigo"],
    ],
  },
  {
    name: "platform",
    label: "Plataforma",
    options: [
      ["", "Todas"],
      ["instagram", "Instagram"],
      ["facebook", "Facebook"],
      ["google_business", "Google"],
      ["whatsapp", "WhatsApp"],
    ],
  },
  {
    name: "period",
    label: "Criado em",
    options: [
      ["all", "Qualquer período"],
      ["today", "Hoje"],
      ["7d", "Últimos 7 dias"],
      ["30d", "Últimos 30 dias"],
    ],
  },
  {
    name: "actor",
    label: "Origem da decisão",
    options: [
      ["", "Todas"],
      ["operator", "Pessoa"],
      ["automation", "Automação ou sem autoria"],
    ],
  },
] as const;

const TONE_CLASS = {
  ok: "border-emerald-500/40 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400",
  attention:
    "border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-400",
  danger: "border-destructive/40 bg-destructive/5 text-destructive",
  quiet: "border-border bg-muted/40 text-muted-foreground",
} as const;
const TONE_TEXT = {
  ok: "text-emerald-700 dark:text-emerald-400",
  attention: "text-amber-700 dark:text-amber-400",
  danger: "text-destructive",
  quiet: "text-muted-foreground",
} as const;

function changeFilter(name: MarketingHistoryFilterName, event: Event) {
  const target = event.target;
  if (target instanceof HTMLSelectElement) void setFilter(name, target.value);
}

useHead({ title: "Histórico · Marketing" });
</script>

<template>
  <main class="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
    <div class="mb-5 flex items-center gap-3">
      <div>
        <h1 class="text-xl font-bold">Histórico</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Resultado rastreado por plataforma, sem confundir aceite com entrega.
        </p>
      </div>
      <button
        type="button"
        class="ml-auto inline-flex min-h-11 items-center gap-1.5 rounded-md border border-border px-3 text-sm text-muted-foreground transition hover:bg-muted"
        :disabled="loading"
        @click="refresh()"
      >
        <Icon
          name="lucide:refresh-cw"
          class="size-3.5"
          :class="loading ? 'animate-spin' : ''"
        />
        Atualizar
      </button>
    </div>

    <section
      class="mb-5 rounded-xl border border-border bg-card p-4"
      aria-labelledby="history-filters-title"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 id="history-filters-title" class="text-sm font-semibold">
          Encontrar um resultado
        </h2>
        <button
          v-if="hasActiveFilters"
          type="button"
          class="min-h-11 text-sm font-semibold underline underline-offset-2"
          @click="clearFilters()"
        >
          Limpar filtros
        </button>
      </div>
      <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label
          v-for="filter in FILTERS"
          :key="filter.name"
          class="grid gap-1.5 text-sm font-medium"
        >
          {{ filter.label }}
          <select
            class="min-h-11 w-full rounded-md border-border bg-background text-sm"
            :value="filters[filter.name] || ''"
            @change="changeFilter(filter.name, $event)"
          >
            <option
              v-for="option in filter.options"
              :key="option[0]"
              :value="option[0]"
            >
              {{ option[1] }}
            </option>
          </select>
        </label>
      </div>
    </section>

    <div
      v-if="error && announcements.length === 0"
      class="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
      role="alert"
    >
      <p class="font-semibold text-destructive">{{ loadFailure.title }}</p>
      <p class="mt-1 text-muted-foreground">{{ loadFailure.detail }}</p>
      <button
        v-if="loadFailure.canRetry"
        type="button"
        class="mt-2 min-h-11 font-semibold underline underline-offset-2"
        @click="refresh()"
      >
        Tentar de novo
      </button>
    </div>

    <div
      v-else-if="loading && announcements.length === 0"
      class="space-y-3"
      aria-busy="true"
      aria-label="Carregando histórico"
    >
      <div
        v-for="n in 3"
        :key="n"
        class="h-36 animate-pulse rounded-xl bg-muted"
      ></div>
    </div>

    <div
      v-else-if="announcements.length === 0"
      class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon
        name="lucide:megaphone-off"
        class="mx-auto size-8 text-muted-foreground"
      />
      <p class="mt-2 font-semibold">
        {{
          hasActiveFilters
            ? "Nenhum resultado combina com os filtros"
            : "Nenhum resultado registrado ainda"
        }}
      </p>
      <p class="mt-1 text-sm text-muted-foreground">
        {{
          hasActiveFilters
            ? "Limpe ou ajuste os filtros para ampliar a busca."
            : "Quando uma decisão ou entrega começar, ela aparecerá aqui."
        }}
      </p>
      <button
        v-if="hasActiveFilters"
        type="button"
        class="mt-3 min-h-11 font-semibold underline underline-offset-2"
        @click="clearFilters()"
      >
        Limpar filtros
      </button>
    </div>

    <template v-else>
      <p class="mb-3 text-sm text-muted-foreground" role="status">
        {{ announcements.length }}
        {{
          announcements.length === 1
            ? "resultado carregado"
            : "resultados carregados"
        }}
      </p>

      <div
        v-if="error"
        class="mb-3 rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-sm"
        role="alert"
      >
        <p class="font-semibold">
          Os resultados já carregados continuam visíveis.
        </p>
        <p class="mt-1 text-muted-foreground">
          Não foi possível atualizar agora. Você pode tentar novamente sem
          perder os filtros.
        </p>
      </div>

      <ul class="space-y-3">
        <li
          v-for="announcement in announcements"
          :key="announcement.ref"
          class="rounded-xl border border-border bg-card p-4"
        >
          <div class="flex flex-wrap items-start gap-3">
            <div
              class="mt-0.5 rounded-full border p-2"
              :class="
                TONE_CLASS[
                  deliveryStatePresentation(
                    announcement.delivery.state,
                    announcement.state,
                  ).tone
                ]
              "
            >
              <Icon
                :name="
                  deliveryStatePresentation(
                    announcement.delivery.state,
                    announcement.state,
                  ).icon
                "
                class="size-4"
              />
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <h2 class="font-semibold">
                  {{ historySubject(announcement) }}
                </h2>
                <span class="text-xs text-muted-foreground">
                  {{
                    scheduleSummary(
                      historyOccurredAt(announcement),
                      shopTimezone,
                    )
                  }}
                </span>
              </div>
              <p
                class="mt-1 text-sm font-semibold"
                :class="
                  TONE_TEXT[
                    deliveryStatePresentation(
                      announcement.delivery.state,
                      announcement.state,
                    ).tone
                  ]
                "
              >
                {{
                  deliveryStatePresentation(
                    announcement.delivery.state,
                    announcement.state,
                  ).label
                }}
              </p>
              <p class="mt-1 text-sm text-muted-foreground">
                {{ historyActorLabel(announcement.decision_actor_policy) }}
              </p>

              <ul
                v-if="announcement.delivery.platforms.length"
                class="mt-3 grid gap-2 sm:grid-cols-2"
                aria-label="Resultado por plataforma"
              >
                <li
                  v-for="platform in announcement.delivery.platforms"
                  :key="platform.platform_ref"
                  class="rounded-lg border border-border bg-background/60 px-3 py-2"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-sm font-semibold">
                      {{ platformResultLabel(platform.platform_ref) }}
                    </span>
                    <span class="text-xs text-muted-foreground">
                      {{ deliveryStatePresentation(platform.state).label }}
                    </span>
                  </div>
                  <p
                    v-for="count in deliveryCountItems(platform.counts)"
                    :key="count.key"
                    class="mt-1 text-xs text-muted-foreground"
                  >
                    {{ count.count }} {{ count.label }}
                  </p>
                </li>
              </ul>
              <p v-else class="mt-3 text-xs text-muted-foreground">
                Não há contagem rastreável por plataforma neste registro.
              </p>

              <NuxtLink
                :to="historyHref(announcement.ref)"
                class="mt-3 inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold underline underline-offset-2"
              >
                {{ historyLinkLabel(actions, announcement.ref) }}
                <Icon name="lucide:arrow-right" class="size-4" />
              </NuxtLink>
            </div>
          </div>
        </li>
      </ul>

      <div class="mt-5 flex flex-col items-center gap-2">
        <button
          v-if="hasMore"
          type="button"
          class="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-4 text-sm font-semibold hover:bg-muted disabled:opacity-50"
          :disabled="loadingMore"
          @click="loadMore()"
        >
          <Icon
            name="lucide:chevron-down"
            class="size-4"
            :class="loadingMore ? 'animate-pulse' : ''"
          />
          {{ loadingMore ? "Carregando…" : "Carregar mais resultados" }}
        </button>
        <div
          v-if="loadMoreError"
          class="w-full rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
          role="alert"
        >
          <p class="font-semibold text-destructive">
            Não foi possível carregar a próxima página.
          </p>
          <p class="mt-1 text-muted-foreground">
            Os {{ announcements.length }} resultados acima e seus filtros foram
            preservados.
          </p>
          <button
            type="button"
            class="mt-2 min-h-11 font-semibold underline underline-offset-2"
            @click="loadMore()"
          >
            Tentar de novo
          </button>
        </div>
      </div>
    </template>
  </main>
</template>
