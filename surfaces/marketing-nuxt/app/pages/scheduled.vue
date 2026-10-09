<script setup lang="ts">
// Agendados: o que já foi aprovado e espera a hora marcada, o mais próximo primeiro. Cada
// item leva os dois gestos da v4 (pino 5): reagendar e cancelar o que não começou. Os
// dois abrem, direto, o mesmo gesto da tela do anúncio (`?action=`), que confere a
// consequência e pede a confirmação; aqui ninguém cancela no escuro.
//
// Desenho: o cartão da fila de decisões (`marketing-decisoes4.html`), sem destaque: aqui
// nada pede você, tudo já foi decidido.
import {
  decisionIcon,
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

const brokenImages = ref(new Set<string>());

onKeyStroke(["r", "R"], (event) => {
  const target = event.target as HTMLElement | null;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
  void refresh();
});
const MENU = [
  { key: "history", label: "Histórico de disparos", icon: "lucide:history", to: "/history" },
  { key: "refresh", label: "Atualizar", icon: "lucide:refresh-cw", shortcut: "R" },
];
function onMenu(key: string) {
  if (key === "refresh") void refresh();
}

useHead({ title: "Agendados" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-marketing-scheduled>
    <MarketingPageHeader title="Agendados" phone-hides-actions>
      <template #actions>
        <MarketingPageMenu heading="Agendados" :items="MENU" @select="onMenu" />
      </template>
      <template #status>
        <!-- No celular o kit desce o estado para a segunda linha da barra (README "Barra
             do topo no celular"): ele não disputa mais a largura com o título. -->
        <span class="flex min-w-0" data-marketing-live>
          <OperatorLiveStatus
            :tone="live.tone"
            :time="live.time"
            :label="live.label"
            :detail="live.detail"
          />
        </span>
      </template>
    </MarketingPageHeader>

    <div class="mx-auto flex w-full max-w-3xl flex-col gap-2.5 px-4 pt-3 pb-5 sm:px-6">
      <p class="flex min-h-8 items-center text-[14px] text-muted-foreground" role="status" :aria-busy="loading">
        {{ scheduledHeadline(scheduled.length) }}
      </p>

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
          class="flex flex-wrap items-center gap-3 rounded-[14px] border border-border bg-card p-3"
        >
          <img
            v-if="item.image_url && !brokenImages.has(item.ref)"
            :src="item.image_url"
            alt=""
            class="size-[60px] shrink-0 rounded-lg object-cover"
            loading="lazy"
            @error="brokenImages = new Set([...brokenImages, item.ref])"
          >
          <span
            v-else
            class="grid size-[60px] shrink-0 place-items-center rounded-lg bg-[color-mix(in_oklab,var(--app-color,var(--primary))_14%,transparent)] text-[var(--app-color,var(--primary))]"
            aria-hidden="true"
          >
            <Icon :name="decisionIcon(item.trigger)" class="size-7" />
          </span>
          <div class="min-w-0 flex-1">
            <h2 class="break-words text-[16px] font-semibold leading-snug">
              <NuxtLink :to="item.href" class="hover:underline">{{ decisionTitle(item) }}</NuxtLink>
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
          <div class="flex w-full gap-2 sm:w-auto">
            <UiButton
              :to="{ path: item.href, query: { action: 'reschedule_announcement' }, hash: '#result' }"
              variant="outline"
              class="h-12 flex-1 rounded-xl px-4 text-[15px] font-semibold sm:flex-none"
              :aria-label="`Reagendar: ${decisionTitle(item)}`"
              data-scheduled-reschedule
            >
              Reagendar
            </UiButton>
            <UiButton
              :to="{ path: item.href, query: { action: 'cancel_announcement' }, hash: '#result' }"
              variant="outline"
              class="h-12 flex-1 rounded-xl px-4 text-[15px] font-semibold sm:flex-none"
              :aria-label="`Cancelar antes de começar: ${decisionTitle(item)}`"
              data-scheduled-cancel
            >
              Cancelar
            </UiButton>
          </div>
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
