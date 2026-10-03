<script setup lang="ts">
// Agendados: o que já foi aprovado e espera a hora marcada, o mais próximo primeiro. Cada
// linha abre o anúncio, onde cancelar o que não começou já mora hoje.
import {
  decisionTitle,
  departureLabel,
  destinationsLine,
  scheduledHeadline,
} from "~/presentation/decisions";

const { queue, scheduled, shopTimezone, nowMs, loading, error, refresh } =
  useMarketingDecisions();

useHead({ title: "Agendados" });
</script>

<template>
  <main
    class="mx-auto w-full max-w-3xl flex-1 px-4 py-5 sm:px-6"
    data-marketing-scheduled
  >
    <header class="flex items-start gap-3">
      <div class="min-w-0 flex-1">
        <h1 class="text-2xl font-semibold tracking-tight">Agendados</h1>
        <p class="mt-1 text-sm text-muted-foreground" role="status">
          {{ scheduledHeadline(scheduled.length) }}
        </p>
      </div>
      <UiIconButton
        icon="lucide:refresh-cw"
        label="Atualizar agendados"
        :spinning="loading"
        :disabled="loading"
        @click="refresh()"
      />
    </header>

    <div
      v-if="error && !queue"
      class="mt-5 rounded-xl border border-destructive/30 bg-destructive/5 p-4"
      role="alert"
    >
      <p class="font-semibold">Os agendados não carregaram</p>
      <p class="mt-1 text-sm text-muted-foreground">
        Isso não quer dizer que nada está agendado. Atualize antes de concluir.
      </p>
    </div>

    <ol v-else-if="scheduled.length" class="mt-4 flex flex-col gap-3">
      <li
        v-for="item in scheduled"
        :key="item.ref"
        :data-scheduled="item.ref"
        class="flex items-center gap-3 rounded-2xl border border-border bg-card p-4"
      >
        <span
          class="grid size-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"
          aria-hidden="true"
        >
          <Icon name="lucide:calendar-clock" class="size-5" />
        </span>
        <div class="min-w-0 flex-1">
          <h2 class="break-words text-base font-semibold leading-snug">
            {{ decisionTitle(item) }}
          </h2>
          <p class="mt-0.5 text-sm font-medium">
            {{
              departureLabel(
                item.scheduled_for,
                item.platform_refs,
                shopTimezone,
                nowMs,
              )
            }}
          </p>
          <p class="mt-0.5 break-words text-sm text-muted-foreground">
            {{ destinationsLine(item.platform_refs, item.reach) }}
          </p>
        </div>
        <UiButton
          :to="item.href"
          variant="outline"
          class="shrink-0"
          :aria-label="`Abrir: ${decisionTitle(item)}`"
        >
          Abrir
        </UiButton>
      </li>
    </ol>

    <div
      v-else-if="queue"
      class="mt-5 rounded-2xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
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
  </main>
</template>
