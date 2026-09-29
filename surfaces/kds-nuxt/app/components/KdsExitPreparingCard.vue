<script setup lang="ts">
// O card da coluna "Em preparo" da Saída: um pedido que ainda espera alguma
// estação. A moldura é a comum dos cards do KDS (KdsCardIdentity + `cardScale`);
// no lugar dos itens, uma linha por ESTAÇÃO do pedido.
//
// A estação de tela dá baixa sozinha — a linha só diz em que pé ela está. A
// estação SEM tela recebeu o pedido em papel (Via Cozinha), e quem dá a baixa
// dela é a Saída: a linha diz quando o papel saiu e traz o botão "Pronto"
// (decisão do dono, 26/09/2026). Quando a última estação conclui, o pedido sai
// desta coluna e entra em "Prontos para sair" sozinho, com o som do KDS.
import type { KDSExitPreparingCardProjection } from "~/types/kds";
import {
  cardScale,
  elapsedLabel,
  exitChipTone,
  exitChipView,
  lucideIcon,
  splitRef,
  type KDSDensity,
} from "~/presentation/board";
import KdsCardIdentity from "~/components/KdsCardIdentity.vue";
import KdsTestOrderBanner from "~/components/KdsTestOrderBanner.vue";

const props = withDefaults(
  defineProps<{
    card: KDSExitPreparingCardProjection;
    density?: KDSDensity;
    /** Estações com o "Pronto" já enviado e ainda sem resposta do servidor. */
    busyStations?: ReadonlySet<string>;
  }>(),
  { density: "cozy", busyStations: () => new Set<string>() },
);
defineEmits<{ ready: [stationRef: string] }>();

const ref_ = computed(() => splitRef(props.card.order_ref));
const d = computed(() => cardScale(props.density));
const chips = computed(() =>
  props.card.stations.map((chip) => ({ ref: chip.station_ref, view: exitChipView(chip) })),
);
</script>

<template>
  <article
    class="flex w-full flex-col overflow-hidden rounded-md border bg-card shadow-sm"
    :class="[d.inset, d.padT, d.padB, d.gap]"
    data-testid="exit-preparing-card"
  >
    <KdsTestOrderBanner
      v-if="card.test_order_label"
      :label="card.test_order_label"
      forbids="não entregar"
    />

    <KdsCardIdentity
      :code="ref_.code"
      :code-class="d.code"
      :channel-icon="card.channel_icon"
      :overline="card.fulfillment_label"
    >
      <p
        v-if="card.customer_name"
        class="mt-1.5 truncate text-sm font-medium text-foreground/80"
      >
        {{ card.customer_name }}
      </p>
      <template #aside>
        <span
          class="inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm font-semibold tabular-nums"
          :title="`Na cozinha desde ${card.fired_at_display}`"
        >
          <Icon
            :name="`lucide:${lucideIcon(card.fulfillment_icon)}`"
            class="size-4 shrink-0"
          />
          {{ elapsedLabel(card.elapsed_seconds) }}
        </span>
      </template>
    </KdsCardIdentity>

    <ul class="flex flex-col gap-2 border-t pt-2.5" aria-label="Estações deste pedido">
      <li
        v-for="chip in chips"
        :key="chip.ref"
        class="flex items-center gap-2.5 rounded-md border px-3 py-2"
        :class="exitChipTone(chip.view.tone)"
        data-testid="exit-station-chip"
      >
        <Icon :name="chip.view.icon" class="size-4 shrink-0" />
        <div class="min-w-0 flex-1 leading-tight">
          <p class="truncate text-base font-bold text-foreground">{{ chip.view.station }}</p>
          <p class="truncate text-sm font-medium">{{ chip.view.detail }}</p>
          <p v-if="chip.view.cancelledNote" class="truncate text-xs font-semibold text-destructive dark:text-red-300">
            {{ chip.view.cancelledNote }}
          </p>
        </div>
        <button
          v-if="chip.view.canMarkReady"
          type="button"
          class="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-md bg-foreground px-4 text-base font-semibold text-background transition hover:bg-foreground/90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="busyStations.has(chip.ref)"
          :aria-label="`${chip.view.station} pronto no pedido ${ref_.code}`"
          @click="$emit('ready', chip.ref)"
        >
          <Icon name="lucide:check" class="size-5 shrink-0" />
          Pronto
        </button>
      </li>
    </ul>
  </article>
</template>
