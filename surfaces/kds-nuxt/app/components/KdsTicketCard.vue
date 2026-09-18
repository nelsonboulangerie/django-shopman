<script setup lang="ts">
// Card de preparo. Duas zonas, cada uma com um só papel:
//
// - CABEÇALHO = o pedido e o GESTO. Código, minutagem, quem/como, notas do pedido e
//   a faixa de estado. O cabeçalho inteiro é o alvo do toque (sem botão de ação):
//   pendente → toque inicia o preparo; em preparo → toque finaliza (com "Desfazer").
// - CORPO = só os itens. Nada é truncado nem escondido: nome e observação quebram
//   linha, e o card cresce o quanto precisar (a grade alinha a altura por linha).
//
// O preparo é estado do TICKET, guardado no servidor — todos os tablets veem quem já
// pegou o pedido. Cor só onde tem significado: a barra de SLA (urgência) e o
// vermelho do item cancelado que trava o finalizar.
import type { KDSTicketProjection } from "~/types/kds";
import {
  elapsedLabel,
  KDS_ARM_DELAY_MS,
  slaPercent,
  splitRef,
  ticketTapAction,
  ticketTone,
  toneBar,
  toneNextSurface,
  toneTimer,
} from "~/presentation/board";

export type KDSDensity = "compact" | "cozy" | "roomy";

const props = withDefaults(
  defineProps<{
    ticket: KDSTicketProjection;
    density?: KDSDensity;
    next?: boolean;
    /** Há item cancelado deste pedido sem "Ciente" — finalizar espera. */
    blocked?: boolean;
    /** Ticket adicional de um pedido que já passou por esta estação. */
    addition?: boolean;
  }>(),
  { density: "cozy", next: false, blocked: false, addition: false },
);
const emit = defineEmits<{ start: []; finish: []; blocked: []; open: [] }>();

const tone = computed(() => ticketTone(props.ticket.timer_class));
const code = computed(() => splitRef(props.ticket.order_ref).code);
const fill = computed(() =>
  slaPercent(props.ticket.elapsed_seconds, props.ticket.target_seconds),
);
const isDelivery = computed(() => props.ticket.fulfillment_icon === "local_shipping");
// Sem cliente nomeado, o nome cai para a própria comanda — que já aparece riscada.
const customerLabel = computed(() =>
  props.ticket.customer_name === props.ticket.previous_tab_ref ? "" : props.ticket.customer_name,
);

// Armar o finalizar: o toque que INICIOU não pode, quicando, finalizar também.
// Card que já chega em preparo (outro tablet, recarga) nasce armado.
const armed = ref(props.ticket.status !== "pending");
let armTimer: ReturnType<typeof setTimeout> | null = null;
watch(
  () => props.ticket.status,
  (status, previous) => {
    if (status === "in_progress" && previous === "pending") {
      armed.value = false;
      if (armTimer) clearTimeout(armTimer);
      armTimer = setTimeout(() => (armed.value = true), KDS_ARM_DELAY_MS);
    } else if (status !== "in_progress") {
      armed.value = status !== "pending";
    }
  },
);
onBeforeUnmount(() => {
  if (armTimer) clearTimeout(armTimer);
});

const tap = computed(() =>
  ticketTapAction(props.ticket, { armed: armed.value, blocked: props.blocked }),
);
const interactive = computed(() => !props.ticket.is_scheduled);

function onTap() {
  if (tap.value === "start") emit("start");
  else if (tap.value === "finish") emit("finish");
  else if (tap.value === "blocked") emit("blocked");
}

// Faixa de estado: diz o que o card É e o que o próximo toque FAZ.
const strip = computed(() => {
  const t = props.ticket;
  if (t.is_scheduled)
    return { icon: "lucide:calendar-clock", text: "Prévia · libera na data", tone: "muted" };
  if (t.status === "pending")
    return { icon: "lucide:pointer", text: "Toque para iniciar", tone: "muted" };
  if (props.blocked)
    return { icon: "lucide:ban", text: "Item cancelado · dê Ciente", tone: "alert" };
  if (!armed.value)
    return { icon: "lucide:chef-hat", text: "Em preparo", tone: "active" };
  return { icon: "lucide:check-check", text: "Em preparo · toque para finalizar", tone: "active" };
});
const stripClass = computed(
  () =>
    ({
      muted: "bg-muted/60 text-muted-foreground",
      active: "bg-foreground text-background",
      alert: "bg-destructive/15 text-destructive dark:text-red-300",
    })[strip.value.tone],
);
const actionLabel = computed(() => {
  if (tap.value === "start") return `Iniciar preparo do pedido ${code.value}`;
  if (tap.value === "finish") return `Finalizar pedido ${code.value}`;
  if (tap.value === "blocked") return `Pedido ${code.value}: item cancelado, confirme antes de finalizar`;
  return `Pedido ${code.value} em preparo`;
});

const timerChip = computed(() => toneTimer(tone.value));
const barFill = computed(() => toneBar(tone.value));
const nextSurface = computed(() => toneNextSurface(tone.value));

// Escala de densidade num único mapa — padroniza tamanhos, ritmo e altura mínima.
const d = computed(
  () =>
    ({
      compact: {
        code: "text-xl",
        timer: "text-base",
        ctrlH: "h-8",
        item: "text-sm",
        note: "text-xs",
        inset: "px-3",
        padT: "pt-2.5",
        strip: "h-8 text-xs",
        gapY: "py-1.5",
        card: "min-h-[180px]",
      },
      cozy: {
        code: "text-3xl",
        timer: "text-lg",
        ctrlH: "h-9",
        item: "text-base",
        note: "text-sm",
        inset: "px-4",
        padT: "pt-3",
        strip: "h-9 text-sm",
        gapY: "py-2",
        card: "min-h-[220px]",
      },
      roomy: {
        code: "text-4xl",
        timer: "text-xl",
        ctrlH: "h-11",
        item: "text-lg",
        note: "text-base",
        inset: "px-5",
        padT: "pt-4",
        strip: "h-11 text-base",
        gapY: "py-2.5",
        card: "min-h-[270px]",
      },
    })[props.density],
);
</script>

<template>
  <article
    class="relative flex w-full flex-col overflow-hidden rounded-md border transition"
    :class="[d.card, next ? `shadow-lg ring-1 ${nextSurface}` : 'bg-card shadow-sm']"
    :data-status="ticket.status"
  >
    <!-- CABEÇALHO: o pedido + o gesto. O botão cobre o cabeçalho inteiro por baixo do
         conteúdo (que não intercepta o toque); só o `i` fica por cima. -->
    <header class="relative">
      <button
        v-if="interactive"
        type="button"
        class="absolute inset-0 z-0 transition hover:bg-accent/30 active:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        :aria-label="actionLabel"
        data-kds-tap
        @click="onTap"
      />

      <div class="pointer-events-none relative z-10 flex flex-col gap-1.5" :class="[d.inset, d.padT]">
        <!-- linha 1: CÓDIGO (herói) · minutagem · detalhes -->
        <div class="flex items-center gap-2">
          <p
            class="min-w-0 flex-1 whitespace-nowrap font-extrabold leading-none tracking-tight tabular-nums"
            :class="d.code"
          >
            {{ code }}
          </p>
          <div
            class="inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 font-bold tabular-nums"
            :class="[ticket.is_scheduled ? 'bg-muted text-muted-foreground' : timerChip, d.ctrlH, d.timer]"
          >
            <Icon
              :name="ticket.is_scheduled ? 'lucide:calendar-clock' : 'lucide:timer'"
              class="size-4 shrink-0 opacity-70"
            />
            {{ ticket.is_scheduled ? "Agendado" : elapsedLabel(ticket.elapsed_seconds) }}
          </div>
          <button
            type="button"
            class="pointer-events-auto relative z-20 grid aspect-square shrink-0 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground"
            :class="d.ctrlH"
            :aria-label="`Detalhes do pedido ${code}`"
            data-kds-open
            @click.stop="emit('open')"
          >
            <Icon name="lucide:info" class="size-4" />
          </button>
        </div>

        <!-- linha 2: contexto curto (nome pode encurtar; o resto não) -->
        <div
          v-if="customerLabel || isDelivery || addition || ticket.previous_tab_ref"
          class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm font-medium text-muted-foreground"
        >
          <span
            v-if="addition"
            class="inline-flex items-center gap-1 rounded border border-foreground/30 px-1.5 text-xs font-bold uppercase tracking-wide text-foreground"
          >
            <Icon name="lucide:plus" class="size-3" />Adicional
          </span>
          <span
            v-if="isDelivery"
            class="inline-flex items-center gap-1 rounded border px-1.5 text-xs font-bold uppercase tracking-wide text-foreground"
          >
            <Icon name="lucide:bike" class="size-3" />Entrega
          </span>
          <span
            v-if="ticket.previous_tab_ref"
            class="line-through"
            :title="`Comanda ${ticket.previous_tab_ref} já liberada`"
            >Comanda {{ ticket.previous_tab_ref }}</span
          >
          <span v-if="customerLabel" class="min-w-0 max-w-full truncate">{{ customerLabel }}</span>
        </div>

        <!-- notas do pedido: completas (podem ser alergia) -->
        <p
          v-if="ticket.kitchen_note"
          class="flex items-start gap-1.5 rounded-md border border-foreground/20 bg-muted/60 px-2 py-1 font-medium leading-snug"
          :class="d.note"
        >
          <Icon name="lucide:chef-hat" class="mt-0.5 size-3.5 shrink-0 opacity-70" />
          <span class="min-w-0 whitespace-pre-wrap break-words">{{ ticket.kitchen_note }}</span>
        </p>
        <p
          v-if="ticket.customer_note"
          class="flex items-start gap-1.5 rounded-md border px-2 py-1 leading-snug text-muted-foreground"
          :class="d.note"
        >
          <Icon name="lucide:user" class="mt-0.5 size-3.5 shrink-0" />
          <span class="min-w-0 whitespace-pre-wrap break-words">{{ ticket.customer_note }}</span>
        </p>
      </div>

      <!-- faixa de estado: o que o card é e o que o próximo toque faz -->
      <div
        class="pointer-events-none relative z-10 mt-2.5 flex items-center justify-center gap-1.5 px-2 font-semibold"
        :class="[d.strip, stripClass]"
        data-kds-strip
      >
        <Icon :name="strip.icon" class="size-4 shrink-0" />
        <span class="truncate">{{ strip.text }}</span>
      </div>

      <!-- time-to-SLA: a borda de baixo do cabeçalho -->
      <div v-if="!ticket.is_scheduled" class="relative z-10 h-1.5 w-full bg-white/5" aria-hidden="true">
        <div
          class="h-full rounded-r-full transition-[width] duration-500"
          :class="barFill"
          :style="{ width: `${fill}%` }"
        />
      </div>
    </header>

    <!-- CORPO: só os itens, inteiros. -->
    <ul class="flex flex-1 flex-col divide-y divide-border/50" :class="[d.inset, d.gapY]">
      <li
        v-for="(item, idx) in ticket.items"
        :key="idx"
        class="flex items-start gap-2.5 py-1.5"
      >
        <span
          class="min-w-[2.5ch] shrink-0 text-right font-bold leading-snug tabular-nums"
          :class="d.item"
          >{{ item.qty }}×</span
        >
        <div class="min-w-0 flex-1">
          <p class="break-words font-semibold leading-snug" :class="d.item">
            {{ item.name }}
          </p>
          <p
            v-if="item.notes"
            class="mt-0.5 flex items-start gap-1 font-semibold leading-snug text-foreground/85"
            :class="d.note"
          >
            <Icon name="lucide:corner-down-right" class="mt-0.5 size-3.5 shrink-0 opacity-60" />
            <span class="min-w-0 whitespace-pre-wrap break-words">{{ item.notes }}</span>
          </p>
          <p
            v-if="item.stock_warning"
            class="mt-0.5 flex items-start gap-1 font-semibold leading-snug"
            :class="d.note"
          >
            <Icon name="lucide:triangle-alert" class="mt-0.5 size-3.5 shrink-0" />
            <span class="min-w-0 break-words">{{ item.stock_warning }}</span>
          </p>
        </div>
      </li>
    </ul>
  </article>
</template>
