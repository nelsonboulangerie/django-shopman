<script setup lang="ts">
// Enviados: o que já saiu (ou tentou sair), do mais novo ao mais antigo, com o resultado
// por plataforma. Os quatro recortes de hoje (Situação, Plataforma, Criado em, Origem da
// decisão) são `NuxtSelect` rotulados no `#filters` do cabeçalho: na mesa ficam na linha,
// no celular vão para o painel "Filtros" (WP-FASE2, "Período nas listas mora no painel").
// Os valores e a URL são os de `useCampaignHistory`.
import { choiceLabels, formatCount } from "~/presentation/campaign";
import {
  HISTORY_FILTERS,
  historyActiveFilters,
  historyActorLabel,
  historyFilterQueryValue,
  historyFilterValue,
  historyHref,
  historyLinkLabel,
  historyOccurredAt,
  historySubject,
  historyWhen,
  type HistoryFilterName,
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
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

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

const loadFailure = computed(() => marketingLoadError(error.value));

// O tom do resultado vira a cor do selo (conjunto mínimo: as 6 cores do Badge).
const TONE_COLOR = {
  ok: "success",
  attention: "warning",
  danger: "error",
  quiet: "neutral",
} as const;

function state(announcement: AnnouncementProjectionV2) {
  return deliveryStatePresentation(announcement.delivery.state, announcement.state);
}

function changeFilter(name: HistoryFilterName, value: unknown) {
  void setFilter(name, historyFilterQueryValue(String(value ?? "")));
}

// Um chip removível por recorte fora do padrão ("Criado em: Últimos 7 dias").
const activeFilters = computed(() =>
  historyActiveFilters(filters.value).map((chip) => ({
    key: chip.name,
    label: chip.label,
    remove: () => void setFilter(chip.name, ""),
  })),
);

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

// Erro com lista na tela: as linhas que já estavam ficam, e o aviso diz isso.
const alerts = computed(() =>
  error.value && announcements.value.length
    ? [
        {
          id: "history-refresh-failed",
          color: "warning" as const,
          title: "Não foi possível atualizar agora.",
          description:
            "Os resultados já carregados continuam na tela, com os seus filtros.",
          action: { label: "Tentar de novo", onSelect: () => void refresh() },
        },
      ]
    : [],
);

const loadedLabel = computed(() =>
  announcements.value.length === 1
    ? "1 resultado carregado"
    : `${announcements.value.length} resultados carregados`,
);

const headerActions = [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => void refresh() },
];
onKeyStroke(["r", "R"], (event) => {
  const target = event.target as HTMLElement | null;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
  void refresh();
});

useHead({ title: "Enviados" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-marketing-history>
    <OperatorPageHeader
      title="Enviados"
      :actions="headerActions"
      actions-label="Mais ações de Enviados"
      :active-filters="activeFilters"
      :clear-filters="() => void clearFilters()"
      :alerts="alerts"
    >
      <template #status>
        <!-- No celular o kit desce o estado para a segunda linha da barra. -->
        <span class="flex min-w-0" data-marketing-live>
          <OperatorLiveStatus :tone="live.tone" :time="live.time" :label="live.label" :detail="live.detail" />
        </span>
      </template>
      <template #filters>
        <NuxtFormField
          v-for="filter in HISTORY_FILTERS"
          :key="filter.name"
          :label="filter.label"
          orientation="horizontal"
          class="gap-2"
          :data-history-chip="filter.name"
        >
          <NuxtSelect
            :model-value="historyFilterValue(filters[filter.name])"
            :items="filter.options"
            class="min-w-40"
            :data-history-filter="filter.name"
            @update:model-value="changeFilter(filter.name, $event)"
          />
        </NuxtFormField>
      </template>
      <template v-if="announcements.length" #filters-end>
        <span
          class="text-xs text-muted-foreground tabular-nums"
          role="status"
          data-history-total
          >{{ loadedLabel }}</span
        >
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto w-full max-w-5xl">
        <template v-if="error && announcements.length === 0">
          <OperatorScreenState
            v-if="loadFailure.canRetry"
            state="error"
            what="os enviados"
            :description="loadFailure.detail"
            @retry="refresh()"
          />
          <NuxtAlert
            v-else
            color="error"
            variant="subtle"
            icon="i-lucide-circle-alert"
            :title="loadFailure.title"
            :description="loadFailure.detail"
            role="alert"
          />
        </template>

        <OperatorScreenState
          v-else-if="loading && announcements.length === 0"
          state="loading"
          what="os enviados"
        />

        <OperatorScreenState
          v-else-if="announcements.length === 0"
          state="empty"
          icon="i-lucide-megaphone-off"
          :title="
            hasActiveFilters
              ? 'Nenhum resultado combina com os filtros.'
              : 'Nenhum resultado registrado ainda.'
          "
          :description="
            hasActiveFilters
              ? 'Limpe ou ajuste os filtros para ampliar a busca.'
              : 'Quando uma decisão ou entrega começar, ela aparecerá aqui.'
          "
          data-history-empty
        >
          <template v-if="hasActiveFilters" #actions>
            <NuxtButton
              label="Limpar filtros"
              icon="i-lucide-x"
              color="neutral"
              variant="outline"
              @click="clearFilters()"
            />
          </template>
        </OperatorScreenState>

        <template v-else>
          <ul class="flex flex-col gap-3" data-history-list>
            <li
              v-for="announcement in announcements"
              :key="announcement.ref"
              :data-history-row="announcement.ref"
            >
              <NuxtCard>
                <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <h2 class="text-base font-semibold">
                    {{ historySubject(announcement, productLabels) }}
                  </h2>
                  <span class="text-xs text-muted-foreground">
                    {{ historyWhen(historyOccurredAt(announcement), shopTimezone) }}
                  </span>
                </div>
                <div class="mt-2 flex flex-wrap items-center gap-2">
                  <NuxtBadge
                    :color="TONE_COLOR[state(announcement).tone]"
                    :icon="state(announcement).icon"
                    :label="state(announcement).label"
                  />
                  <span class="text-sm text-muted-foreground">
                    {{ historyActorLabel(announcement.decision_actor_policy) }}
                  </span>
                </div>

                <ul
                  v-if="announcement.delivery.platforms.length"
                  class="mt-3 grid gap-2 sm:grid-cols-2"
                  aria-label="Resultado por plataforma"
                >
                  <li
                    v-for="platform in announcement.delivery.platforms"
                    :key="platform.platform_ref"
                  >
                    <NuxtCard variant="soft" class="h-full *:data-[slot=body]:p-3">
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
                    </NuxtCard>
                  </li>
                </ul>
                <p v-else class="mt-3 text-xs text-muted-foreground">
                  Este registro é antigo e não guarda contagem por plataforma.
                </p>

                <NuxtLink
                  :to="historyHref(announcement.ref)"
                  class="mt-3 inline-flex min-h-8 items-center gap-1.5 text-sm font-semibold underline underline-offset-2"
                >
                  {{ historyLinkLabel(actions, announcement.ref) }}
                  <Icon name="lucide:arrow-right" class="size-4" aria-hidden="true" />
                </NuxtLink>
              </NuxtCard>
            </li>
          </ul>

          <div class="mt-5 flex flex-col items-center gap-3">
            <NuxtButton
              v-if="hasMore"
              label="Carregar mais resultados"
              icon="i-lucide-chevron-down"
              color="neutral"
              variant="outline"
              :loading="loadingMore"
              data-history-load-more
              @click="loadMore()"
            />
            <!-- O erro da próxima página fica junto do controle que o causou. -->
            <NuxtAlert
              v-if="loadMoreError"
              class="w-full"
              color="error"
              variant="subtle"
              icon="i-lucide-circle-alert"
              title="Não foi possível carregar a próxima página."
              :description="`Os ${announcements.length} resultados acima e os seus filtros continuam na tela.`"
              :actions="alertActions('error', [
                {
                  label: 'Tentar de novo',
                  size: 'md',
                  onClick: () => void loadMore(),
                },
              ])"
              role="alert"
            />
          </div>
        </template>
      </div>
    </section>
  </main>
</template>
