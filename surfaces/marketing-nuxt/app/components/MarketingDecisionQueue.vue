<script setup lang="ts">
// A casa do Marketing: o que espera o seu sim, do prazo mais curto ao mais longo.
//
// Decisão do dono (03/10/2026): antes eram cinco portas (Hoje cortado em quatro,
// sino, push, a volta do disparo, a linha do histórico) e nenhuma tela. Agora a
// fila é uma só, sem corte, e o sino abre esta mesma lista. Cada cartão tem UM
// gesto, "Revisar", que leva ao lugar exato onde a decisão já é tomada (a revisão
// do anúncio, ou o resultado da entrega dele). A fila não decide nada sozinha.
import {
  automaticCheckLine,
  deadlinePresentation,
  decisionTitle,
  destinationsLine,
  failureHeadline,
  failureReason,
  queueHeadline,
  scheduledSummary,
  type DeadlineTone,
} from "~/presentation/decisions";
import type { DecisionItem } from "~/types/decisions";

const {
  queue,
  items,
  automaticChecks,
  shopTimezone,
  nowMs,
  loading,
  error,
  refresh,
} = useMarketingDecisions();

const headline = computed(() => queueHeadline(items.value.length));

const TRIGGER_ICONS: Record<string, string> = {
  production_finished: "lucide:croissant",
  low_stock: "lucide:package-minus",
  stock_back: "lucide:package-check",
  product_created: "lucide:sparkles",
  manual: "lucide:megaphone",
  schedule: "lucide:calendar-clock",
};

function icon(item: DecisionItem): string {
  if (item.kind === "retry_failed") return "lucide:triangle-alert";
  if (item.kind === "reconcile_unknown") return "lucide:circle-help";
  return TRIGGER_ICONS[item.trigger] ?? "lucide:megaphone";
}

function title(item: DecisionItem): string {
  return item.kind === "review" ? decisionTitle(item) : failureHeadline(item);
}

function subtitle(item: DecisionItem): string {
  if (item.kind === "review") {
    const where = destinationsLine(item.platform_refs, item.reach);
    const occasion = decisionTitle(item);
    // O nome da campanha só entra quando o título não é ele mesmo.
    return item.campaign_name && occasion !== item.campaign_name
      ? `${item.campaign_name} · ${where}`
      : where;
  }
  return decisionTitle(item);
}

const toneClasses: Record<DeadlineTone, string> = {
  urgent: "text-destructive",
  soon: "text-warning",
  calm: "text-muted-foreground",
  none: "text-muted-foreground",
};

function deadline(item: DecisionItem) {
  return deadlinePresentation(item, shopTimezone.value, nowMs.value);
}
</script>

<template>
  <main
    class="mx-auto w-full max-w-3xl flex-1 px-4 py-5 sm:px-6"
    data-marketing-decisions
  >
    <header class="flex items-start gap-3">
      <div class="min-w-0 flex-1">
        <h1 class="text-2xl font-semibold tracking-tight">Decisões</h1>
        <p class="mt-1 text-sm" role="status" aria-live="polite">
          <strong class="font-semibold">{{ headline.strong }}</strong>
          <span v-if="headline.rest" class="text-muted-foreground">
            · {{ headline.rest }}</span
          >
        </p>
      </div>
      <UiIconButton
        icon="lucide:refresh-cw"
        label="Atualizar decisões"
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
      <p class="font-semibold">A fila de decisões não carregou</p>
      <p class="mt-1 text-sm text-muted-foreground">
        Isso não quer dizer que nada pede você. Atualize antes de concluir.
      </p>
      <UiButton
        type="button"
        variant="outline"
        class="mt-3"
        @click="refresh()"
      >
        Tentar de novo
      </UiButton>
    </div>

    <ol v-else-if="items.length" class="mt-4 flex flex-col gap-3">
      <li
        v-for="(item, index) in items"
        :key="item.ref"
        :data-decision="item.ref"
        :data-decision-kind="item.kind"
        class="rounded-2xl border bg-card p-4"
        :class="
          index === 0
            ? 'border-primary/70 shadow-sm ring-1 ring-primary/30'
            : 'border-border'
        "
      >
        <div class="flex items-start gap-3">
          <span
            class="grid size-12 shrink-0 place-items-center rounded-xl"
            :class="
              item.kind === 'review'
                ? 'bg-primary/10 text-primary'
                : 'bg-destructive/10 text-destructive'
            "
            aria-hidden="true"
          >
            <Icon :name="icon(item)" class="size-6" />
          </span>
          <div class="min-w-0 flex-1">
            <h2 class="break-words text-base font-semibold leading-snug">
              {{ title(item) }}
            </h2>
            <p class="mt-0.5 break-words text-sm text-muted-foreground">
              {{ subtitle(item) }}
            </p>
          </div>
        </div>

        <ul
          v-if="item.failures.length"
          class="mt-3 flex flex-col gap-1.5"
          :aria-label="`Motivo de ${title(item)}`"
        >
          <li
            v-for="failure in item.failures"
            :key="failure.platform_ref"
            class="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            <Icon
              name="lucide:triangle-alert"
              class="mt-0.5 size-4"
              aria-hidden="true"
            />
            <span>{{ failureReason(failure, item.kind) }}</span>
          </li>
        </ul>

        <div class="mt-3 flex items-center gap-3">
          <Icon
            :name="item.scheduled_for ? 'lucide:calendar-clock' : 'lucide:clock'"
            class="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <p class="min-w-0 flex-1 text-sm leading-tight">
            <span class="block font-semibold">{{ deadline(item).label }}</span>
            <span
              v-if="deadline(item).detail"
              class="block"
              :class="toneClasses[deadline(item).tone]"
              >{{ deadline(item).detail }}</span
            >
          </p>
          <UiButton
            :to="item.href"
            :variant="index === 0 ? 'default' : 'outline'"
            class="shrink-0 px-5"
            :aria-label="`Revisar: ${title(item)}`"
            data-decision-review
          >
            Revisar
          </UiButton>
        </div>
      </li>
    </ol>

    <div
      v-else-if="queue"
      class="mt-5 rounded-2xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon
        name="lucide:inbox"
        class="mx-auto size-8 text-muted-foreground"
        aria-hidden="true"
      />
      <p class="mt-2 font-semibold">Nenhuma decisão esperando você</p>
      <p class="mt-1 text-sm text-muted-foreground">
        Quando um anúncio pedir revisão, ele aparece aqui, com o prazo.
      </p>
    </div>

    <ul
      v-if="automaticChecks.length"
      class="mt-4 flex flex-col gap-2"
      aria-label="Conferências automáticas"
    >
      <li v-for="check in automaticChecks" :key="check.ref">
        <NuxtLink
          :to="check.href"
          :data-automatic-check="check.state"
          class="flex min-h-11 items-start gap-3 rounded-xl px-1 py-1.5 text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span
            class="grid size-8 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground"
            aria-hidden="true"
          >
            <Icon name="lucide:scan-search" class="size-4" />
          </span>
          <span class="min-w-0 flex-1">
            <!-- Título e detalhe na MESMA linha: espaço entre tags que atravessa
                 quebra de linha o compilador do Vue descarta, e a linha virava
                 "incerto.O sistema". -->
            <strong class="font-semibold">{{ automaticCheckLine(check, shopTimezone, nowMs).title }}</strong> <span class="text-muted-foreground">{{ automaticCheckLine(check, shopTimezone, nowMs).detail }}</span>
          </span>
        </NuxtLink>
      </li>
    </ul>

    <NuxtLink
      v-if="queue"
      to="/scheduled"
      class="mt-4 flex min-h-12 items-center justify-between gap-3 rounded-xl border border-dashed border-border px-4 text-sm hover:bg-muted"
      data-decisions-scheduled-line
    >
      <span>{{
        scheduledSummary(
          queue.scheduled_today_count,
          queue.active_campaign_count,
        )
      }}</span>
      <Icon
        name="lucide:chevron-right"
        class="size-4 text-muted-foreground"
        aria-hidden="true"
      />
    </NuxtLink>
  </main>
</template>
