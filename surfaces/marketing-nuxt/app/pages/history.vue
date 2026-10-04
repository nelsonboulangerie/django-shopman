<script setup lang="ts">
import type { MarketingHistoryFilterName } from "~/composables/useCampaignHistory";
import { choiceLabels, formatCount } from "~/presentation/campaign";
import {
  historyActorLabel,
  historyHref,
  historyLinkLabel,
  historyOccurredAt,
  historySubject,
  historyWhen,
} from "~/presentation/marketingHistory";
import {
  deliveryCountItems,
  deliveryStatePresentation,
  marketingLoadError,
  platformDeliveryLabel,
  platformResultLabel,
  platformSwitchedOff,
} from "~/presentation/marketingResult";
import type { AnnouncementProjectionV2 } from "~/types/campaign";

type PlatformDelivery = AnnouncementProjectionV2["delivery"]["platforms"][number];

function platformStateLabel(
  announcement: AnnouncementProjectionV2,
  platform: PlatformDelivery,
): string {
  return platformDeliveryLabel(
    platform,
    platformSwitchedOff(announcement, platform.platform_ref),
  );
}

function platformCountItems(
  announcement: AnnouncementProjectionV2,
  platform: PlatformDelivery,
) {
  return deliveryCountItems(platform.counts, {
    platformSwitchedOff: platformSwitchedOff(announcement, platform.platform_ref),
  });
}

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
// O assunto diz o NOME do produto, não o SKU: o rótulo mora em `options.products`.
const { products } = useCampaigns();
const productLabels = computed(() => choiceLabels(products.value));

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
      ["automation", "Automação"],
    ],
  },
] as const;

const TONE_CLASS = {
  ok: "border-emerald-500/40 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400",
  attention:
    "border-warning/40 bg-warning/5 text-warning",
  danger: "border-destructive/40 bg-destructive/5 text-destructive",
  quiet: "border-border bg-muted/40 text-muted-foreground",
} as const;
const TONE_TEXT = {
  ok: "text-emerald-700 dark:text-emerald-400",
  attention: "text-warning",
  danger: "text-destructive",
  quiet: "text-muted-foreground",
} as const;

function changeFilter(name: MarketingHistoryFilterName, event: Event) {
  const target = event.target;
  if (target instanceof HTMLSelectElement) void setFilter(name, target.value);
}

// O ponto e a hora da última leitura (v4: lista calma, ao vivo).
const lastRead = ref<string | null>(null);
watch(
  loading,
  (now, before) => {
    if (before && !now && !error.value) lastRead.value = new Date().toISOString();
  },
);
onMounted(() => {
  if (!loading.value && !error.value) lastRead.value = new Date().toISOString();
});
const live = useMarketingLiveStatus({
  generatedAt: lastRead,
  failed: computed(() => Boolean(error.value)),
  timeZone: shopTimezone,
});

/** "Situação: Todas" (o recorte em chip, v4: "lista calma com recortes em chips"). */
function chipValue(filter: (typeof FILTERS)[number]): string {
  const current = filters.value[filter.name] || filter.options[0][0];
  return filter.options.find((option) => option[0] === current)?.[1] ?? filter.options[0][1];
}
function chipActive(filter: (typeof FILTERS)[number]): boolean {
  const current = filters.value[filter.name] || "";
  return Boolean(current) && current !== filter.options[0][0];
}

onKeyStroke(["r", "R"], (event) => {
  const target = event.target as HTMLElement | null;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
  void refresh();
});
const MENU = [{ key: "refresh", label: "Atualizar", icon: "lucide:refresh-cw", shortcut: "R" }];

useHead({ title: "Enviados" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <MarketingPageHeader title="Enviados" phone-hides-actions>
      <template #phone-actions>
        <UiIconButton
          icon="lucide:refresh-cw"
          label="Atualizar"
          :spinning="loading"
          :disabled="loading"
          @click="refresh()"
        />
      </template>
      <template #status>
        <span class="flex min-w-0 shrink-[1000] overflow-hidden" data-marketing-live>
          <OperatorLiveStatus :tone="live.tone" :time="live.time" :label="live.label" :detail="live.detail" />
        </span>
      </template>
      <template #actions>
        <MarketingPageMenu heading="Enviados" :items="MENU" @select="refresh()" />
      </template>
      <template #filters>
        <label
          v-for="filter in FILTERS"
          :key="filter.name"
          class="relative inline-flex min-h-control items-center gap-2 rounded-full border px-3 op-label transition focus-within:ring-2 focus-within:ring-ring/40"
          :class="chipActive(filter) ? 'border-primary bg-primary/10 font-semibold' : 'border-border bg-card'"
          :data-history-chip="filter.name"
        >
          <span class="font-normal text-muted-foreground">{{ filter.label }}:</span> {{ chipValue(filter) }}
          <Icon name="lucide:chevron-down" class="size-4 text-muted-foreground" aria-hidden="true" />
          <select
            :value="filters[filter.name] || ''"
            class="absolute inset-0 cursor-pointer opacity-0"
            :aria-label="filter.label"
            @change="changeFilter(filter.name, $event)"
          >
            <option v-for="option in filter.options" :key="option[0]" :value="option[0]">{{ option[1] }}</option>
          </select>
        </label>
        <button
          v-if="hasActiveFilters"
          type="button"
          class="inline-flex min-h-control items-center gap-1 px-2 op-label font-semibold text-primary"
          @click="clearFilters()"
        >
          <Icon name="lucide:x" class="size-4" aria-hidden="true" />Limpar filtros
        </button>
      </template>
    </MarketingPageHeader>
    <div class="mx-auto w-full max-w-5xl px-4 py-5">

    <div
      v-if="error && announcements.length === 0"
      class="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
      role="alert"
    >
      <p class="font-semibold text-destructive">{{ loadFailure.title }}</p>
      <p class="mt-1 text-muted-foreground">{{ loadFailure.detail }}</p>
      <UiButton
        v-if="loadFailure.canRetry"
        type="button"
        variant="link"
        class="mt-2"
        @click="refresh()"
      >
        Tentar de novo
      </UiButton>
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
        class="h-36 animate-pulse rounded-md bg-muted"
      ></div>
    </div>

    <div
      v-else-if="announcements.length === 0"
      class="rounded-md border border-dashed border-border bg-card/50 px-6 py-10 text-center"
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
      <UiButton
        v-if="hasActiveFilters"
        type="button"
        variant="link"
        class="mt-3"
        @click="clearFilters()"
      >
        Limpar filtros
      </UiButton>
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
        class="mb-3 rounded-lg border border-warning/40 bg-warning/5 px-4 py-3 text-sm"
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
          class="rounded-md border border-border bg-card p-4"
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
                  {{ historySubject(announcement, productLabels) }}
                </h2>
                <span class="text-xs text-muted-foreground">
                  {{ historyWhen(historyOccurredAt(announcement), shopTimezone) }}
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
                      {{ platformStateLabel(announcement, platform) }}
                    </span>
                  </div>
                  <p
                    v-for="count in platformCountItems(announcement, platform)"
                    :key="count.key"
                    class="mt-1 text-xs text-muted-foreground"
                  >
                    {{ formatCount(count.count) }} {{ count.label }}
                  </p>
                </li>
              </ul>
              <p v-else class="mt-3 text-xs text-muted-foreground">
                Este registro é antigo e não guarda contagem por plataforma.
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
        <UiButton
          v-if="hasMore"
          type="button"
          variant="outline"
          :disabled="loadingMore"
          @click="loadMore()"
        >
          <Icon
            name="lucide:chevron-down"
            class="size-4"
            :class="loadingMore ? 'animate-pulse' : ''"
          />
          {{ loadingMore ? "Carregando…" : "Carregar mais resultados" }}
        </UiButton>
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
          <UiButton
            type="button"
            variant="link"
            class="mt-2"
            @click="loadMore()"
          >
            Tentar de novo
          </UiButton>
        </div>
      </div>
    </template>
    </div>
  </main>
</template>
