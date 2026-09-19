<script setup lang="ts">
// Card de preparo. TRÊS zonas, na ordem em que a cozinha pergunta — QUE PEDIDO ·
// QUANTO TEMPO · QUE TAREFA — e um só ato por vez:
//
// - IDENTIDADE (topo) = o código grande, o relógio ao lado, e uma linha fina de
//   contexto (cliente, entrega, comanda antiga). A barra de SLA fecha o bloco.
// - TAREFA (meio) = só os itens. Nada é truncado nem escondido: nome e observação
//   quebram linha, e o card cresce o quanto precisar (a grade alinha a altura).
// - AÇÃO (rodapé) = UM botão, com o ato escrito: "Iniciar preparo" → "Finalizar
//   preparo". O botão fica na base do card, então numa linha da grade todos os
//   botões caem na mesma altura, ao alcance do polegar.
//
// A área grande (identidade + itens) faz o que é SEGURO: abre o detalhe. O ato que
// sai da cozinha exige o botão rotulado. Antes era o contrário — o cabeçalho
// inteiro era um botão invisível, e a tela precisava de uma faixa só para avisar
// que aquilo era um alvo de toque.
//
// Finalizar não some com o card: por 5 s ele fica no lugar, apagado, com
// "Desfazer" exatamente onde o dedo acabou de tocar.
//
// O preparo é estado do TICKET, guardado no servidor — todos os tablets veem quem
// já pegou o pedido. Cor só onde tem significado: a barra de SLA (urgência) e o
// vermelho do item cancelado que trava o finalizar.
import type { KDSTicketProjection } from "~/types/kds";
import {
  elapsedLabel,
  KDS_ARM_DELAY_MS,
  KDS_UNDO_WINDOW_MS,
  shortDateLabel,
  slaPercent,
  splitRef,
  ticketAction,
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
    /** Há item cancelado deste pedido sem confirmação — finalizar espera. */
    blocked?: boolean;
    /** Ticket adicional de um pedido que já passou por esta estação. */
    addition?: boolean;
    /** Finalizado com a janela de "Desfazer" ainda aberta. */
    finishing?: boolean;
    /** Data de serviço do quadro (ISO) — o card agendado precisa DIZER a data. */
    serviceDate?: string;
  }>(),
  {
    density: "cozy",
    next: false,
    blocked: false,
    addition: false,
    finishing: false,
    serviceDate: "",
  },
);
const emit = defineEmits<{ start: []; finish: []; blocked: []; undo: []; open: [] }>();

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
const scheduledDate = computed(() =>
  props.serviceDate ? shortDateLabel(props.serviceDate) : "",
);

// Armar o finalizar: o botão fica no MESMO lugar nos dois estados, então o toque
// que INICIOU não pode, quicando, finalizar também. O rótulo já é "Finalizar
// preparo" durante o intervalo — o que muda é só ele não aceitar o toque, e assim
// nada pisca na cara de ninguém. Card que já chega em preparo (outro tablet,
// recarga) nasce armado.
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

const action = computed(() =>
  ticketAction(props.ticket, {
    armed: armed.value,
    blocked: props.blocked,
    finishing: props.finishing,
  }),
);

function onAction() {
  if (!action.value.enabled) return;
  const kind = action.value.kind;
  if (kind === "start") emit("start");
  else if (kind === "finish") emit("finish");
  else if (kind === "blocked") emit("blocked");
  else if (kind === "undo") emit("undo");
}

// Nome acessível do botão: o rótulo já diz o ato; o leitor de tela precisa saber
// de QUE pedido é o ato, porque na grade há muitos botões com o mesmo texto.
const actionAria = computed(() => {
  const kind = action.value.kind;
  if (kind === "start") return `Iniciar o preparo do pedido ${code.value}`;
  if (kind === "finish") return `Finalizar o preparo do pedido ${code.value}`;
  if (kind === "undo") return `Desfazer a finalização do pedido ${code.value}`;
  if (kind === "blocked")
    return `Pedido ${code.value}: confirme o cancelamento no cartão vermelho para poder finalizar`;
  return "";
});

// Cor do botão por ato. Iniciar é o convite (primary); finalizar é a confirmação
// (foreground sólido — o mesmo contraste que a antiga faixa de "em preparo" tinha);
// bloqueado é contornado em vermelho, porque não se convida ninguém a apertá-lo.
const actionClass = computed(() => {
  const kind = action.value.kind;
  if (kind === "start")
    return "bg-primary text-primary-foreground hover:bg-primary/90 active:bg-primary/80";
  if (kind === "finish")
    return "bg-foreground text-background hover:bg-foreground/90 active:bg-foreground/80";
  if (kind === "blocked")
    return "border-t border-destructive/50 bg-destructive/10 text-destructive dark:text-red-300";
  return "border-t bg-card";
});

const timerChip = computed(() => toneTimer(tone.value));
const barFill = computed(() => toneBar(tone.value));
const nextSurface = computed(() => toneNextSurface(tone.value));
const undoWindowSeconds = Math.round(KDS_UNDO_WINDOW_MS / 1000);

// Escala de densidade num único mapa — padroniza tamanhos, ritmo e altura mínima.
// `ctrlH` e `action` seguem a escada de altura do canon do kit (operator-base.css,
// "ALTURAS DE CONTROLE"): h-9 = chip, h-11 = controle padrão, h-14 = CTA. O compact
// usava h-8, abaixo do alvo de toque; o botão de ação nunca desce de h-11, porque
// ele é a razão de o card existir.
const d = computed(
  () =>
    ({
      compact: {
        code: "text-xl",
        timer: "text-base",
        ctrlH: "h-9",
        action: "h-11 text-sm",
        item: "text-sm",
        note: "text-xs",
        inset: "px-3",
        padT: "pt-2.5",
        gapY: "py-1.5",
        card: "min-h-[180px]",
      },
      cozy: {
        code: "text-3xl",
        timer: "text-lg",
        ctrlH: "h-9",
        action: "h-11 text-base",
        item: "text-base",
        note: "text-sm",
        inset: "px-4",
        padT: "pt-3",
        gapY: "py-2",
        card: "min-h-[220px]",
      },
      roomy: {
        code: "text-4xl",
        timer: "text-xl",
        ctrlH: "h-11",
        action: "h-14 text-lg",
        item: "text-lg",
        note: "text-base",
        inset: "px-5",
        padT: "pt-4",
        gapY: "py-2.5",
        card: "min-h-[270px]",
      },
    })[props.density],
);
</script>

<template>
  <article
    class="relative flex w-full flex-col overflow-hidden rounded-md border transition"
    :class="[
      d.card,
      finishing
        ? 'border-dashed bg-muted/40'
        : next
          ? `shadow-lg ${nextSurface}`
          : 'bg-card shadow-sm',
    ]"
    :data-status="ticket.status"
  >
    <!-- Pedido de teste da homologação do iFood: a trava do servidor não cria
         ticket para ele, então este card só existe para o que já estava no
         painel. A faixa vem ANTES do código, em largura inteira: quem lê o
         card tem de saber que aquilo não se forna antes de ler o que é. -->
    <p
      v-if="ticket.test_order_label"
      class="relative z-20 flex items-center gap-1.5 border-b border-warning/40 bg-warning/20 px-3 py-1.5 text-sm font-bold uppercase tracking-wide"
      data-kds-test-order
    >
      <Icon name="lucide:flask-conical" class="size-4 shrink-0" />
      {{ ticket.test_order_label }} · não produzir
    </p>

    <!-- ÁREA DE LEITURA: identidade + itens. Um toque aqui abre o detalhe — o gesto
         seguro fica com a área grande, o gesto que sai da cozinha fica no botão. -->
    <div class="relative flex flex-1 flex-col">
      <button
        v-if="!finishing"
        type="button"
        class="absolute inset-0 z-0 transition hover:bg-accent/20 active:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        :aria-label="`Ver o detalhe do pedido ${code}`"
        data-kds-open
        @click="emit('open')"
      />

      <div
        class="pointer-events-none relative z-10 flex flex-1 flex-col"
        :class="finishing ? 'opacity-45' : ''"
      >
        <!-- IDENTIDADE -->
        <header class="flex flex-col gap-1.5" :class="[d.inset, d.padT]">
          <!-- linha 1: CÓDIGO (herói) · relógio · marca do detalhe -->
          <div class="flex items-center gap-2">
            <p
              class="min-w-0 flex-1 whitespace-nowrap font-extrabold leading-none tracking-tight tabular-nums"
              :class="d.code"
            >
              {{ code }}
            </p>
            <div
              class="inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 font-bold tabular-nums"
              :class="[
                ticket.is_scheduled ? 'bg-muted text-muted-foreground' : timerChip,
                d.ctrlH,
                d.timer,
              ]"
            >
              <Icon
                :name="ticket.is_scheduled ? 'lucide:calendar-clock' : 'lucide:timer'"
                class="size-4 shrink-0 opacity-70"
              />
              {{
                ticket.is_scheduled
                  ? scheduledDate || "Agendado"
                  : elapsedLabel(ticket.elapsed_seconds)
              }}
            </div>
            <!-- Marca do detalhe: a área inteira já é o alvo, então isto é um
                 sinal, não um segundo botão para errar. -->
            <span
              class="grid aspect-square shrink-0 place-items-center rounded-md border text-muted-foreground"
              :class="d.ctrlH"
              aria-hidden="true"
            >
              <Icon name="lucide:info" class="size-4" />
            </span>
          </div>

          <!-- linha 2: contexto fino. O cliente vem primeiro (é por ele que o
               pedido é chamado); "Adicional" é a única marca com selo, porque é a
               única que muda o que se FAZ — o resto acompanha o nome, sem caixa. -->
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
            <span v-if="customerLabel" class="min-w-0 max-w-full truncate text-foreground/80">{{
              customerLabel
            }}</span>
            <span v-if="isDelivery" class="inline-flex shrink-0 items-center gap-1">
              <Icon name="lucide:bike" class="size-3.5" />Entrega
            </span>
            <span
              v-if="ticket.previous_tab_ref"
              class="line-through"
              :title="`Comanda ${ticket.previous_tab_ref} já liberada`"
              >Comanda {{ ticket.previous_tab_ref }}</span
            >
          </div>

          <!-- Notas do pedido: completas (podem ser alergia), num bloco só. Duas
               molduras para duas linhas de texto era o dobro de caixa pela mesma
               informação. -->
          <div
            v-if="ticket.kitchen_note || ticket.customer_note"
            class="flex flex-col gap-1 rounded-md border border-foreground/20 bg-muted/60 px-2 py-1.5 leading-snug"
            :class="d.note"
          >
            <p v-if="ticket.kitchen_note" class="flex items-start gap-1.5 font-medium">
              <Icon name="lucide:chef-hat" class="mt-0.5 size-3.5 shrink-0 opacity-70" />
              <span class="min-w-0 whitespace-pre-wrap break-words">{{ ticket.kitchen_note }}</span>
            </p>
            <p v-if="ticket.customer_note" class="flex items-start gap-1.5 text-muted-foreground">
              <Icon name="lucide:user" class="mt-0.5 size-3.5 shrink-0" />
              <span class="min-w-0 whitespace-pre-wrap break-words">{{ ticket.customer_note }}</span>
            </p>
          </div>
        </header>

        <!-- time-to-SLA: fecha o bloco de identidade -->
        <div
          v-if="!ticket.is_scheduled"
          class="mt-2.5 h-1.5 w-full bg-white/5"
          aria-hidden="true"
        >
          <div
            class="h-full rounded-r-full transition-[width] duration-500"
            :class="barFill"
            :style="{ width: `${fill}%` }"
          />
        </div>

        <!-- TAREFA: só os itens, inteiros. -->
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
      </div>
    </div>

    <!-- AÇÃO: um botão, o ato escrito nele, na base do card. -->
    <div v-if="finishing" class="flex flex-col" data-kds-undo>
      <p
        class="flex items-center justify-center gap-1.5 px-2 pb-1.5 text-sm font-semibold text-muted-foreground"
      >
        <Icon name="lucide:check-check" class="size-4 shrink-0" />
        Finalizado — sai em {{ undoWindowSeconds }}s
      </p>
      <div class="h-1 w-full bg-muted" aria-hidden="true">
        <div class="kds-undo-drain h-full bg-foreground/50" />
      </div>
      <button
        type="button"
        class="flex w-full items-center justify-center gap-2 border-t bg-card font-bold transition hover:bg-accent active:bg-accent/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        :class="d.action"
        :aria-label="actionAria"
        data-kds-action
        @click="onAction"
      >
        <Icon :name="action.icon" class="size-5 shrink-0" />
        {{ action.label }}
      </button>
    </div>
    <p
      v-else-if="ticket.is_scheduled"
      class="flex items-center justify-center gap-1.5 border-t bg-muted/60 px-2 font-semibold text-muted-foreground"
      :class="d.action"
      data-kds-action
    >
      <Icon name="lucide:calendar-clock" class="size-4 shrink-0" />
      <span class="truncate"
        >Prévia{{ scheduledDate ? ` · começa em ${scheduledDate}` : "" }}</span
      >
    </p>
    <button
      v-else
      type="button"
      class="flex w-full items-center justify-center gap-2 font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
      :class="[d.action, actionClass]"
      :disabled="!action.enabled"
      :aria-label="actionAria"
      data-kds-action
      @click="onAction"
    >
      <Icon :name="action.icon" class="size-5 shrink-0" />
      <span class="truncate">{{ action.label }}</span>
    </button>
  </article>
</template>

<style scoped>
/* A barra escoa no mesmo tempo da janela de "Desfazer": a pressa fica visível sem
   um número piscando na cozinha. */
.kds-undo-drain {
  animation: kds-undo-drain 5s linear forwards;
}
@keyframes kds-undo-drain {
  from {
    width: 100%;
  }
  to {
    width: 0%;
  }
}
@media (prefers-reduced-motion: reduce) {
  .kds-undo-drain {
    animation: none;
    width: 100%;
  }
}
</style>
