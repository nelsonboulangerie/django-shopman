<script setup lang="ts">
// Agendados: o que já foi aprovado e espera a hora marcada, o mais próximo primeiro. Cada
// linha abre o anúncio, onde cancelar o que não começou já mora hoje.
//
// Desenho: o cartão da fila de decisões (`marketing-decisoes4.html`), sem destaque: aqui
// nada pede você, tudo já foi decidido.
import {
  decisionTitle,
  departureLabel,
  destinationsLine,
  scheduledHeadline,
} from "~/presentation/decisions";

const { queue, scheduled, shopTimezone, nowMs, loading, error, refresh } =
  useMarketingDecisions();

const live = useMarketingLiveStatus({
  generatedAt: computed(() => queue.value?.generated_at),
  failed: computed(() => Boolean(error.value)),
  timeZone: shopTimezone,
});

useHead({ title: "Agendados" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-marketing-scheduled>
    <MarketingPageHeader title="Agendados">
      <template #status>
        <OperatorLiveStatus
          :tone="live.tone"
          :time="live.time"
          :label="live.label"
          :detail="live.detail"
        />
      </template>
    </MarketingPageHeader>

    <div class="mx-auto flex w-full max-w-3xl flex-col gap-2.5 px-4 pt-3 pb-5 sm:px-6">
      <div class="flex min-h-11 items-center gap-2">
        <p class="min-w-0 flex-1 text-[14px] text-muted-foreground" role="status">
          {{ scheduledHeadline(scheduled.length) }}
        </p>
        <UiIconButton
          icon="lucide:refresh-cw"
          label="Atualizar agendados"
          :spinning="loading"
          :disabled="loading"
          @click="refresh()"
        />
      </div>

      <div
        v-if="error && !queue"
        class="rounded-[14px] border border-destructive/30 bg-destructive/5 p-4"
        role="alert"
      >
        <p class="font-semibold">Os agendados não carregaram</p>
        <p class="mt-1 text-sm text-muted-foreground">
          Isso não quer dizer que nada está agendado. Atualize antes de concluir.
        </p>
      </div>

      <ol v-else-if="scheduled.length" class="flex flex-col gap-2.5">
        <li
          v-for="item in scheduled"
          :key="item.ref"
          :data-scheduled="item.ref"
          class="flex items-center gap-3 rounded-[14px] border border-border bg-card p-3"
        >
          <span
            class="grid size-[60px] shrink-0 place-items-center rounded-lg bg-[color-mix(in_oklab,var(--app-color,var(--primary))_14%,transparent)] text-[var(--app-color,var(--primary))]"
            aria-hidden="true"
          >
            <Icon name="lucide:calendar-clock" class="size-7" />
          </span>
          <div class="min-w-0 flex-1">
            <h2 class="break-words text-[16px] font-semibold leading-snug">
              {{ decisionTitle(item) }}
            </h2>
            <p class="mt-0.5 text-[14px] font-medium tnum">
              {{
                departureLabel(
                  item.scheduled_for,
                  item.platform_refs,
                  shopTimezone,
                  nowMs,
                )
              }}
            </p>
            <p class="mt-0.5 break-words text-[13px] leading-snug text-muted-foreground">
              {{ destinationsLine(item.platform_refs, item.reach) }}
            </p>
          </div>
          <UiButton
            :to="item.href"
            variant="outline"
            class="h-12 shrink-0 rounded-xl px-5 text-[15px] font-semibold"
            :aria-label="`Abrir: ${decisionTitle(item)}`"
          >
            Abrir
          </UiButton>
        </li>
      </ol>

      <div
        v-else-if="queue"
        class="rounded-[14px] border border-dashed border-border bg-card/50 px-6 py-10 text-center"
      >
        <Icon
          name="lucide:calendar"
          class="mx-auto size-8 text-muted-foreground"
          aria-hidden="true"
        />
        <p class="mt-2 font-semibold">Nenhum anúncio agendado</p>
        <p class="mt-1 text-sm text-muted-foreground">
          Ao aprovar com hora marcada, o anúncio espera aqui até a hora chegar.
        </p>
      </div>
    </div>
  </main>
</template>
