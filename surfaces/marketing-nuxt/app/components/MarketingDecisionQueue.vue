<script setup lang="ts">
// A casa do Marketing: o que espera o seu sim, do prazo mais curto ao mais longo.
//
// Decisão do dono (03/10/2026): antes eram cinco portas (Hoje cortado em quatro,
// sino, push, a volta do disparo, a linha do histórico) e nenhuma tela. Agora a
// fila é uma só, sem corte, e o sino abre esta mesma lista. Cada cartão tem UM
// gesto, "Revisar", que leva ao lugar exato onde a decisão já é tomada (a revisão
// do anúncio, ou o resultado da entrega dele). A fila não decide nada sozinha.
//
// Desenho: `marketing-decisoes4.html` (v4). Cartão de 14px de raio e 12px de
// respiro; a miniatura de 60px (a ocasião, ou a plataforma que falhou); título de
// 16px e destino de 13px; o motivo da falha numa faixa vermelha clara; o prazo como
// hora + tom; "Revisar" de 48px, cheio só no mais urgente.
import { platformIcon } from "~/presentation/campaign";
import {
  automaticCheckLine,
  deadlinePresentation,
  decisionIcon,
  decisionTitle,
  failureHeadline,
  failureReason,
  failureSubtitle,
  queueHeadline,
  reviewSubtitle,
  scheduledSummaryParts,
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
const live = useMarketingLiveStatus({
  generatedAt: computed(() => queue.value?.generated_at),
  failed: computed(() => Boolean(error.value)),
  timeZone: shopTimezone,
});

function icon(item: DecisionItem): string {
  // A falha mostra ONDE falhou (v4: a miniatura do cartão de falha é a plataforma).
  const failed = item.failures[0]?.platform_ref;
  if (item.kind !== "review" && failed) return platformIcon(failed);
  if (item.kind === "reconcile_unknown") return "lucide:circle-help";
  if (item.kind === "retry_failed") return "lucide:triangle-alert";
  return decisionIcon(item.trigger);
}

/** Foto na miniatura (v4 pino 2): a do anúncio ou a do produto; quebrou, volta o ícone. */
const brokenImages = ref(new Set<string>());
function photo(item: DecisionItem): string {
  // Na falha a miniatura é a plataforma que falhou (v4): a foto é da revisão.
  if (item.kind !== "review") return "";
  return item.image_url && !brokenImages.value.has(item.ref) ? item.image_url : "";
}

function title(item: DecisionItem): string {
  return item.kind === "review" ? decisionTitle(item) : failureHeadline(item);
}

function subtitle(item: DecisionItem): string {
  return item.kind === "review"
    ? reviewSubtitle(item, shopTimezone.value, nowMs.value)
    : failureSubtitle(item, shopTimezone.value);
}

// Atenção ao tempo é UM número e a intensidade (v4, SPEC4 §cor): o prazo curto fica no
// latão/âmbar, mais forte quanto mais perto. Vermelho é de "bloqueado com motivo" (a
// faixa da falha), nunca de relógio.
const toneClasses: Record<DeadlineTone, string> = {
  urgent: "font-semibold text-warning",
  soon: "font-medium text-warning",
  calm: "text-muted-foreground",
  none: "text-muted-foreground",
};

const iconToneClasses: Record<DeadlineTone, string> = {
  urgent: "text-warning",
  soon: "text-warning",
  calm: "text-muted-foreground",
  none: "text-muted-foreground",
};

// Atualizar mora no ⋯ do cabeçalho, com a tecla R (v3: "Atualizar R").
const DECISIONS_MENU = [
  { key: "templates", label: "Modelos de texto", icon: "lucide:file-text", to: "/settings/templates" },
  { key: "history", label: "Histórico de disparos", icon: "lucide:history", to: "/history" },
  { key: "refresh", label: "Atualizar", icon: "lucide:refresh-cw", shortcut: "R" },
];
function onMenu(key: string) {
  if (key === "refresh") void refresh();
}
onKeyStroke(["r", "R"], (event) => {
  const target = event.target as HTMLElement | null;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
  void refresh();
});

function deadline(item: DecisionItem) {
  return deadlinePresentation(item, shopTimezone.value, nowMs.value);
}

/** "Decide até 10:15" → ["Decide até ", "10:15"]: a hora vai em negrito (v4). */
function splitClock(label: string): [string, string] {
  const match = /^(.*?)((?:amanhã, |\d{2}\/\d{2}, )?\d{2}:\d{2})$/.exec(label);
  return match ? [match[1]!, match[2]!] : [label, ""];
}

const scheduledLine = computed(() =>
  queue.value
    ? scheduledSummaryParts(
        queue.value.scheduled_today_count,
        queue.value.active_campaign_count,
      )
    : null,
);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-marketing-decisions>
    <MarketingPageHeader title="Decisões" phone-hides-actions>
      <!-- Do tablet para cima (v3): o ⋯ com o que não é o gesto da tela e a ação
           primária por último, na mesma linha. No celular o polegar tem o sino e o menu. -->
      <template #actions>
        <MarketingPageMenu heading="Decisões" :items="DECISIONS_MENU" @select="onMenu" />
        <UiButton to="/settings/campaigns" data-decisions-primary>
          <Icon name="lucide:send" class="size-4" aria-hidden="true" />
          Preparar disparo
        </UiButton>
      </template>
      <template #status>
        <!-- No celular o kit desce o estado para a segunda linha da barra (README "Barra
             do topo no celular"): ele não disputa mais a largura com o título, e o rótulo
             por extenso ("Atualiza sozinho a cada 1 min") aparece inteiro. -->
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
      <!-- Uma linha limpa (v4): quantas e em que ordem. Atualizar mora no ⋯ do
           cabeçalho (tecla R), não aqui. -->
      <p class="flex min-h-8 items-center text-[14px] text-muted-foreground" role="status" aria-live="polite" :aria-busy="loading" data-decisions-headline>
        <span><strong class="font-semibold text-foreground">{{ headline.strong }}</strong><template v-if="headline.rest"> · {{ headline.rest }}</template></span>
      </p>

      <div
        v-if="error && !queue"
        class="rounded-[14px] border border-destructive/30 bg-destructive/5 p-4"
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

      <ol v-else-if="items.length" class="flex flex-col gap-2.5">
        <li
          v-for="(item, index) in items"
          :key="item.ref"
          :data-decision="item.ref"
          :data-decision-kind="item.kind"
          class="flex flex-col gap-2.5 rounded-[14px] border bg-card p-3"
          :class="index === 0 ? 'border-primary ring-1 ring-primary' : 'border-border'"
          :data-decision-focus="index === 0 || undefined"
        >
          <div class="flex gap-3">
            <img
              v-if="photo(item)"
              :src="photo(item)"
              alt=""
              class="size-[60px] shrink-0 rounded-lg object-cover"
              loading="lazy"
              data-decision-photo
              @error="brokenImages = new Set([...brokenImages, item.ref])"
            >
            <span
              v-else
              class="grid size-[60px] shrink-0 place-items-center rounded-lg"
              :class="
                item.kind === 'review'
                  ? 'bg-[color-mix(in_oklab,var(--app-color,var(--primary))_14%,transparent)] text-[var(--app-color,var(--primary))]'
                  : 'bg-destructive/10 text-destructive'
              "
              aria-hidden="true"
            >
              <Icon :name="icon(item)" class="size-7" />
            </span>
            <div class="min-w-0 flex-1">
              <h2 class="break-words text-[16px] font-semibold leading-snug">
                {{ title(item) }}
              </h2>
              <p class="mt-0.5 break-words text-[13px] leading-snug text-muted-foreground">
                {{ subtitle(item) }}
              </p>
            </div>
          </div>

          <ul
            v-if="item.failures.length"
            class="flex flex-col gap-1.5"
            :aria-label="`Motivo de ${title(item)}`"
          >
            <li
              v-for="failure in item.failures"
              :key="failure.platform_ref"
              class="flex items-start gap-1.5 rounded-lg bg-destructive/8 px-2.5 py-2 text-[13px] leading-snug font-medium text-destructive"
            >
              <Icon
                name="lucide:triangle-alert"
                class="mt-px size-4"
                aria-hidden="true"
              />
              <span>{{ failureReason(failure, item.kind) }}</span>
            </li>
          </ul>

          <div class="flex items-center gap-3">
            <Icon
              :name="item.scheduled_for ? 'lucide:calendar' : 'lucide:clock'"
              class="size-5"
              :class="iconToneClasses[deadline(item).tone]"
              aria-hidden="true"
            />
            <p class="min-w-0 flex-1 leading-tight">
              <span class="block text-[14px]">{{ splitClock(deadline(item).label)[0] }}<b v-if="splitClock(deadline(item).label)[1]" class="tnum font-semibold">{{ splitClock(deadline(item).label)[1] }}</b></span>
              <span
                v-if="deadline(item).detail"
                class="block text-[13px] tnum"
                :class="toneClasses[deadline(item).tone]"
                >{{ deadline(item).detail }}</span
              >
            </p>
            <UiButton
              :to="item.href"
              :variant="index === 0 ? 'default' : 'outline'"
              class="h-12 shrink-0 rounded-xl px-6 text-[15px] font-semibold"
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
        class="rounded-[14px] border border-dashed border-border bg-card/50 px-6 py-10 text-center"
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
        class="flex flex-col gap-1"
        aria-label="Conferências automáticas"
      >
        <li v-for="check in automaticChecks" :key="check.ref">
          <NuxtLink
            :to="check.href"
            :data-automatic-check="check.state"
            class="flex min-h-11 items-start gap-2.5 rounded-xl px-1 py-1.5 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span
              class="grid size-7 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground"
              aria-hidden="true"
            >
              <Icon name="lucide:sparkles" class="size-4" />
            </span>
            <!-- Título e detalhe na MESMA linha do template: espaço entre tags que
                 atravessa quebra de linha o compilador do Vue descarta, e a frase
                 virava "incerto.O sistema". -->
            <span class="min-w-0 flex-1 text-[13px] leading-snug text-muted-foreground"><strong class="font-semibold text-foreground">{{ automaticCheckLine(check, shopTimezone, nowMs).title }}</strong> {{ automaticCheckLine(check, shopTimezone, nowMs).detail }}</span>
          </NuxtLink>
        </li>
      </ul>

      <NuxtLink
        v-if="queue && scheduledLine"
        to="/scheduled"
        class="flex min-h-12 items-center gap-2 rounded-xl border border-dashed border-border px-3.5 text-[14px] hover:bg-muted"
        data-decisions-scheduled-line
      >
        <span class="min-w-0 flex-1"><b v-if="scheduledLine.lead" class="tnum font-semibold">{{ scheduledLine.lead }}</b> <span class="text-muted-foreground">{{ scheduledLine.rest }}</span></span>
        <Icon
          name="lucide:chevron-right"
          class="size-5 text-muted-foreground"
          aria-hidden="true"
        />
      </NuxtLink>
    </div>
  </main>
</template>
