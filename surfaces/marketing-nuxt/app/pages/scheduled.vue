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

// O ⋯ do cabeçalho: os links de hoje e "Atualizar" (tecla R).
const headerActions = [
  { label: "Enviados", icon: "i-lucide-history", to: "/history" },
  { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => void refresh() },
];
onKeyStroke(["r", "R"], (event) => {
  const target = event.target as HTMLElement | null;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
  void refresh();
});

useHead({ title: "Agendados" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-marketing-scheduled>
    <OperatorPageHeader
      title="Agendados"
      :actions="headerActions"
      actions-label="Mais ações de Agendados"
    >
      <template #status>
        <!-- No celular o kit desce o estado para a segunda linha da barra (README "Barra
             do topo no celular"): ele não disputa a largura com o título. -->
        <span class="flex min-w-0" data-marketing-live>
          <OperatorLiveStatus
            :tone="live.tone"
            :time="live.time"
            :label="live.label"
            :detail="live.detail"
          />
        </span>
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto flex w-full max-w-3xl flex-col gap-3">
        <p
          v-if="queue"
          class="flex min-h-8 items-center text-sm text-muted-foreground"
          role="status"
          :aria-busy="loading"
          data-scheduled-headline
        >
          {{ scheduledHeadline(scheduled.length) }}
        </p>

        <OperatorScreenState
          v-if="error && !queue"
          state="error"
          what="os agendados"
          description="Isso não quer dizer que nada está agendado. Atualize antes de concluir."
          @retry="refresh()"
        />

        <OperatorScreenState
          v-else-if="loading && !queue"
          state="loading"
          what="os agendados"
        />

        <ol v-else-if="scheduled.length" class="flex flex-col gap-3">
          <li
            v-for="item in scheduled"
            :key="item.ref"
            :data-scheduled="item.ref"
          >
            <NuxtCard class="*:data-[slot=body]:p-3">
              <div class="flex flex-wrap items-center gap-3">
                <img
                  v-if="item.image_url && !brokenImages.has(item.ref)"
                  :src="item.image_url"
                  alt=""
                  class="size-15 shrink-0 rounded-lg object-cover"
                  loading="lazy"
                  @error="brokenImages = new Set([...brokenImages, item.ref])"
                >
                <span
                  v-else
                  class="grid size-15 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"
                  aria-hidden="true"
                >
                  <Icon :name="decisionIcon(item.trigger)" class="size-7" />
                </span>
                <div class="min-w-0 flex-1">
                  <h2 class="break-words text-base font-semibold leading-snug">
                    <NuxtLink :to="item.href" class="hover:underline">{{ decisionTitle(item) }}</NuxtLink>
                  </h2>
                  <p class="mt-0.5 text-sm font-medium tnum">
                    {{
                      departureLabel(
                        item.scheduled_for,
                        item.platform_refs,
                        shopTimezone,
                        nowMs,
                      )
                    }}
                  </p>
                  <p class="mt-0.5 break-words text-sm leading-snug text-muted-foreground">
                    {{ destinationsLine(item.platform_refs, item.reach) }}
                  </p>
                </div>
                <div class="flex w-full gap-2 sm:w-auto">
                  <NuxtButton
                    :to="{ path: item.href, query: { action: 'reschedule_announcement' }, hash: '#result' }"
                    label="Reagendar"
                    icon="i-lucide-calendar-clock"
                    color="neutral"
                    variant="outline"
                    class="flex-1 justify-center sm:flex-none"
                    :aria-label="`Reagendar: ${decisionTitle(item)}`"
                    data-scheduled-reschedule
                  />
                  <NuxtButton
                    :to="{ path: item.href, query: { action: 'cancel_announcement' }, hash: '#result' }"
                    label="Cancelar"
                    icon="i-lucide-x"
                    color="neutral"
                    variant="outline"
                    class="flex-1 justify-center sm:flex-none"
                    :aria-label="`Cancelar antes de começar: ${decisionTitle(item)}`"
                    data-scheduled-cancel
                  />
                </div>
              </div>
            </NuxtCard>
          </li>
        </ol>

        <OperatorScreenState
          v-else-if="queue"
          state="empty"
          icon="i-lucide-calendar"
          title="Nenhum anúncio agendado agora."
          description="Ao aprovar com hora marcada, o anúncio espera aqui até a hora chegar."
          data-scheduled-empty
        />
      </div>
    </section>
  </main>
</template>
