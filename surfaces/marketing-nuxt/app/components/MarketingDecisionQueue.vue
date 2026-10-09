<script setup lang="ts">
// A casa do Marketing: o que espera o seu sim, do prazo mais curto ao mais longo.
//
// Decisão do dono (03/10/2026): antes eram cinco portas (Hoje cortado em quatro,
// sino, push, a volta do disparo, a linha do histórico) e nenhuma tela. Agora a
// fila é uma só, sem corte, e o sino abre esta mesma lista. Cada cartão tem UM
// gesto, "Revisar", que leva ao lugar exato onde a decisão já é tomada (a revisão
// do anúncio, ou o resultado da entrega dele). A fila não decide nada sozinha.
//
// Desenho: `marketing-decisoes4.html` (v4), no conjunto mínimo da suíte (fase 2): o
// cartão é um `NuxtCard` de bloco único com 12 px de respiro; a miniatura de 60 px (a
// ocasião, ou a plataforma que falhou); o motivo da falha num `NuxtAlert` de erro; o
// prazo como hora + tom; "Revisar" cheio só no mais urgente.
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

// O cabeçalho da suíte (fase 2): "Preparar disparo" é a ação primária (o botão cheio na
// mesa; no celular, a vaga de ícone). O resto, com "Atualizar" (tecla R), é o ⋯.
const headerActions = [
  { label: "Modelos de texto", icon: "i-lucide-file-text", to: "/settings/templates" },
  { label: "Enviados", icon: "i-lucide-history", to: "/history" },
  { label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => void refresh() },
];
const phoneHeaderActions = [
  { label: "Preparar disparo", icon: "i-lucide-send", to: "/settings/campaigns", priority: 1 },
  ...headerActions,
];
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
    <OperatorPageHeader
      title="Decisões"
      :actions="headerActions"
      :phone-actions="phoneHeaderActions"
      actions-label="Mais ações de Decisões"
    >
      <template #status>
        <!-- No celular o kit desce o estado para a segunda linha da barra (README "Barra
             do topo no celular"), e o rótulo por extenso aparece inteiro. -->
        <span class="flex min-w-0" data-marketing-live>
          <OperatorLiveStatus
            :tone="live.tone"
            :time="live.time"
            :label="live.label"
            :detail="live.detail"
          />
        </span>
      </template>
      <template #actions>
        <NuxtButton
          to="/settings/campaigns"
          icon="i-lucide-send"
          label="Preparar disparo"
          data-decisions-primary
        />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto flex w-full max-w-3xl flex-col gap-3">
        <!-- Uma linha limpa (v4): quantas e em que ordem. -->
        <p
          v-if="queue"
          class="flex min-h-8 items-center text-sm text-muted-foreground"
          role="status"
          aria-live="polite"
          :aria-busy="loading"
          data-decisions-headline
        >
          <span><strong class="font-semibold text-foreground">{{ headline.strong }}</strong><template v-if="headline.rest"> · {{ headline.rest }}</template></span>
        </p>

        <OperatorScreenState
          v-if="error && !queue"
          state="error"
          what="as decisões"
          description="Isso não quer dizer que nada pede você. Atualize antes de concluir."
          @retry="refresh()"
        />

        <OperatorScreenState
          v-else-if="loading && !queue"
          state="loading"
          what="as decisões"
        />

        <ol v-else-if="items.length" class="flex flex-col gap-3">
          <li
            v-for="(item, index) in items"
            :key="item.ref"
            :data-decision="item.ref"
            :data-decision-kind="item.kind"
            :data-decision-focus="index === 0 || undefined"
          >
            <!-- Um bloco só, 12 px de respiro, sem cabeçalho nem rodapé destacados. O
                 mais urgente leva o anel na cor da ação. -->
            <NuxtCard
              class="*:data-[slot=body]:p-3"
              :class="index === 0 ? 'ring-2 ring-primary' : ''"
              data-decision-card
            >
              <div class="flex flex-col gap-3">
                <div class="flex gap-3">
                  <img
                    v-if="photo(item)"
                    :src="photo(item)"
                    alt=""
                    class="size-15 shrink-0 rounded-lg object-cover"
                    loading="lazy"
                    data-decision-photo
                    @error="brokenImages = new Set([...brokenImages, item.ref])"
                  >
                  <span
                    v-else
                    class="grid size-15 shrink-0 place-items-center rounded-lg"
                    :class="
                      item.kind === 'review'
                        ? 'bg-primary/10 text-primary'
                        : 'bg-error/10 text-error'
                    "
                    aria-hidden="true"
                  >
                    <Icon :name="icon(item)" class="size-7" />
                  </span>
                  <div class="min-w-0 flex-1">
                    <h2 class="break-words text-base font-semibold leading-snug">
                      {{ title(item) }}
                    </h2>
                    <p class="mt-0.5 break-words text-sm leading-snug text-muted-foreground">
                      {{ subtitle(item) }}
                    </p>
                  </div>
                </div>

                <ul
                  v-if="item.failures.length"
                  class="flex flex-col gap-2"
                  :aria-label="`Motivo de ${title(item)}`"
                >
                  <li v-for="failure in item.failures" :key="failure.platform_ref">
                    <NuxtAlert
                      color="error"
                      variant="subtle"
                      icon="i-lucide-triangle-alert"
                      :title="failureReason(failure, item.kind)"
                    />
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
                    <span class="block text-sm">{{ splitClock(deadline(item).label)[0] }}<b v-if="splitClock(deadline(item).label)[1]" class="tnum font-semibold">{{ splitClock(deadline(item).label)[1] }}</b></span>
                    <span
                      v-if="deadline(item).detail"
                      class="block text-xs tnum"
                      :class="toneClasses[deadline(item).tone]"
                      >{{ deadline(item).detail }}</span
                    >
                  </p>
                  <!-- Cheio só no mais urgente (v4): o estado ativo do botão, nunca a
                       troca de variante. -->
                  <NuxtButton
                    :to="item.href"
                    label="Revisar"
                    variant="outline"
                    :active="index === 0"
                    active-variant="solid"
                    class="shrink-0"
                    :aria-label="`Revisar: ${title(item)}`"
                    data-decision-review
                  />
                </div>
              </div>
            </NuxtCard>
          </li>
        </ol>

        <OperatorScreenState
          v-else-if="queue"
          state="empty"
          icon="i-lucide-inbox"
          title="Nenhuma decisão espera você agora."
          description="Quando um anúncio pedir revisão, ele aparece aqui, com o prazo."
          data-decisions-empty
        />

        <ul
          v-if="automaticChecks.length"
          class="flex flex-col gap-1"
          aria-label="Conferências automáticas"
        >
          <li v-for="check in automaticChecks" :key="check.ref">
            <NuxtLink
              :to="check.href"
              :data-automatic-check="check.state"
              class="flex min-h-11 items-start gap-2.5 rounded-lg px-1 py-1.5 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
              <span class="min-w-0 flex-1 text-sm leading-snug text-muted-foreground"><strong class="font-semibold text-foreground">{{ automaticCheckLine(check, shopTimezone, nowMs).title }}</strong> {{ automaticCheckLine(check, shopTimezone, nowMs).detail }}</span>
            </NuxtLink>
          </li>
        </ul>

        <NuxtLink
          v-if="queue && scheduledLine"
          to="/scheduled"
          class="flex min-h-12 items-center gap-2 rounded-lg border border-dashed border-border px-3.5 text-sm hover:bg-muted"
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
    </section>
  </main>
</template>
