<script setup lang="ts">
// An expedition (dispatch) board card. A moldura é a comum dos cards do KDS
// (KdsCardIdentity + KdsCardButton + `cardScale`): margem em volta, código herói
// sob uma linha de chamada, um elemento à direita, o ato escrito num botão
// DENTRO da moldura. Superfície neutra (cor só onde tem significado; aqui não há
// SLA, e despacho/balcão é distinguido pelo ÍCONE, não por cor), e a ação
// principal em neutro INVERTIDO (despachar/entregar).
import type { KDSExpeditionCardProjection } from "~/types/kds";
import {
  cardScale,
  lucideIcon,
  shortDateLabel,
  splitRef,
  type KDSDensity,
} from "~/presentation/board";
import KdsCardButton from "~/components/KdsCardButton.vue";
import KdsCardIdentity from "~/components/KdsCardIdentity.vue";
import KdsTestOrderBanner from "~/components/KdsTestOrderBanner.vue";

const props = withDefaults(
  defineProps<{
    card: KDSExpeditionCardProjection;
    density?: KDSDensity;
    /** Data de serviço do quadro (ISO) — a prévia precisa DIZER a data. */
    serviceDate?: string;
  }>(),
  { density: "cozy", serviceDate: "" },
);
defineEmits<{ action: [action: "dispatch" | "complete"] }>();

const ref_ = computed(() => splitRef(props.card.order_ref));
const scheduledDate = computed(() =>
  props.serviceDate ? shortDateLabel(props.serviceDate) : "",
);
// Bloqueio do servidor (payment_gate), já resolvido na projection: quando há
// rótulo, a ação de saída NÃO é oferecida.
const blocked = computed(() => Boolean(props.card.advance_block_label));
// Conferência de itens na Saída: colapsado por padrão (board scannable),
// expande pra conferir o que entregar/despachar.
const showItems = ref(false);
const d = computed(() => cardScale(props.density));
</script>

<template>
  <article
    class="flex w-full flex-col overflow-hidden rounded-md border bg-card shadow-sm"
    :class="[d.inset, d.padT, d.padB, d.gap]"
  >
    <!-- Pedido de teste da homologação do iFood: a Saída é o card do PEDIDO,
         não do ticket, então ele chega aqui mesmo sem passar pela cozinha — e é
         aqui que alguém entregaria a sacola. O aviso vem antes do código. -->
    <KdsTestOrderBanner
      v-if="card.test_order_label"
      :label="card.test_order_label"
      forbids="não entregar"
    />

    <!-- identidade: código herói + badge neutro de despacho/balcão -->
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
          class="inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm font-semibold"
        >
          <Icon
            :name="`lucide:${lucideIcon(card.fulfillment_icon)}`"
            class="size-4 shrink-0"
          />
          {{ card.is_delivery ? "Entrega" : "Retirada" }}
        </span>
      </template>
    </KdsCardIdentity>

    <!-- meta: VOLUMES em destaque (o que conferir/entregar) + linhas · total -->
    <div class="flex items-end justify-between gap-3">
      <div class="flex items-baseline gap-1.5">
        <span class="text-3xl font-extrabold tabular-nums leading-none">{{
          card.units_count
        }}</span>
        <span class="text-sm font-medium text-muted-foreground">{{
          card.units_count === "1" ? "volume" : "volumes"
        }}</span>
      </div>
      <div class="text-right text-sm leading-tight">
        <div class="text-muted-foreground">
          {{ card.line_count }} {{ card.line_count === 1 ? "linha" : "linhas" }}
        </div>
        <div class="font-bold tabular-nums">{{ card.total_display }}</div>
      </div>
    </div>

    <!-- conferência de itens (qty × nome): toggle pra manter o board enxuto -->
    <div v-if="card.items.length" class="border-t pt-2">
      <button
        type="button"
        class="flex w-full items-center justify-between gap-2 rounded-md px-1 py-1 text-sm font-medium text-muted-foreground transition hover:text-foreground"
        :aria-expanded="showItems"
        @click="showItems = !showItems"
      >
        <span class="inline-flex items-center gap-1.5">
          <Icon name="lucide:list" class="size-4 shrink-0" />
          {{ showItems ? "Ocultar itens" : `Ver itens (${card.line_count})` }}
        </span>
        <Icon
          :name="showItems ? 'lucide:chevron-up' : 'lucide:chevron-down'"
          class="size-4 shrink-0"
        />
      </button>
      <ul v-if="showItems" class="mt-1 space-y-1">
        <li
          v-for="(item, idx) in card.items"
          :key="idx"
          class="flex items-baseline gap-2.5 text-sm"
        >
          <span class="min-w-[2.5ch] shrink-0 text-right font-bold tabular-nums"
            >{{ item.qty }}×</span
          >
          <span class="min-w-0 flex-1 truncate font-medium">{{
            item.name
          }}</span>
        </li>
      </ul>
    </div>

    <!-- bloqueio: a gêmea na tela do gate do servidor (payment_gate). O motivo
         aparece ANTES do toque — recusa seca com o cliente esperando é o pior dos
         dois mundos —, no MESMO rótulo e na MESMA frase que o Gestor mostra.
         Neutro de propósito: âmbar/vermelho aqui são o semáforo de SLA, e um
         segundo significado na mesma cor apaga os dois. Dinheiro na entrega NÃO
         cai aqui: é venda legítima que se paga na porta. -->
    <div v-if="card.is_scheduled" class="mt-auto" data-testid="expedition-scheduled">
      <KdsCardButton
        tone="inert"
        icon="lucide:calendar-clock"
        :label="`Prévia${scheduledDate ? ` · começa em ${scheduledDate}` : ''}`"
        :size-class="d.action"
      />
    </div>
    <div v-else-if="blocked" class="mt-auto" data-testid="expedition-blocked">
      <KdsCardButton
        tone="inert"
        icon="lucide:clock"
        :label="card.advance_block_label"
        :size-class="d.action"
      />
      <p class="mt-1.5 text-xs leading-snug text-muted-foreground">
        {{ card.advance_block_reason }}
      </p>
    </div>

    <!-- ação principal: neutro invertido -->
    <KdsCardButton
      v-else
      class="mt-auto"
      tone="confirm"
      :icon="`lucide:${lucideIcon(card.fulfillment_icon)}`"
      :label="card.is_delivery ? 'Despachar pedido' : 'Entregar pedido'"
      :size-class="d.action"
      @click="$emit('action', card.is_delivery ? 'dispatch' : 'complete')"
    />
  </article>
</template>
