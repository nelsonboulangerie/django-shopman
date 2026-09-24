<script setup lang="ts">
// Card de preparo. TRÊS zonas, na ordem em que a cozinha pergunta — QUE PEDIDO ·
// QUANTO TEMPO · QUE TAREFA — e um só ato por vez:
//
// - IDENTIDADE (topo) = a mesma da expedição (KdsCardIdentity): linha de chamada
//   com o canal e "Entrega"/"Retirada", o código grande na sua própria linha, o
//   cliente embaixo dele, e à direita só o relógio. A barra de SLA fecha o bloco.
// - TAREFA (meio) = só os itens. Nada é truncado nem escondido: nome e observação
//   quebram linha, e o card cresce o quanto precisar (a grade alinha a altura).
// - AÇÃO (rodapé) = UM botão, com o ato escrito: "Iniciar preparo" → "Finalizar
//   preparo". O botão fica na base do card, então numa linha da grade todos os
//   botões caem na mesma altura, ao alcance do polegar.
//
// A moldura é a comum dos cards do KDS (`cardScale`): margem em volta de tudo,
// ritmo vertical único, e o botão DENTRO da moldura, arredondado — não uma laje
// colada na borda. Era a diferença que fazia a expedição parecer mais limpa.
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
  cardScale,
  elapsedLabel,
  fulfillmentLabel,
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
  type KDSDensity,
} from "~/presentation/board";
import KdsCardButton, { type KdsCardButtonTone } from "~/components/KdsCardButton.vue";
import KdsCardIdentity from "~/components/KdsCardIdentity.vue";
import KdsTestOrderBanner from "~/components/KdsTestOrderBanner.vue";

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
const overline = computed(() => fulfillmentLabel(props.ticket.fulfillment_icon));
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

// Tom do botão por ato. Iniciar e finalizar têm a MESMA cor (o neutro invertido —
// o mesmo do "Despachar" da expedição): iniciar é contornado, finalizar é o único
// sólido. Bloqueado é contornado em vermelho, porque não se convida ninguém a
// apertá-lo.
const actionTone = computed<KdsCardButtonTone>(() => {
  const kind = action.value.kind;
  if (kind === "start") return "invite";
  if (kind === "finish") return "confirm";
  if (kind === "blocked") return "blocked";
  return "outline";
});

const timerChip = computed(() => toneTimer(tone.value));
const barFill = computed(() => toneBar(tone.value));
const nextSurface = computed(() => toneNextSurface(tone.value));
const undoWindowSeconds = Math.round(KDS_UNDO_WINDOW_MS / 1000);

// Moldura comum (margem, ritmo, código, botão) + o que só o preparo tem: o
// relógio, o corpo dos itens e das notas. `timerH` segue a escada do canon do
// kit (operator-base.css, "ALTURAS DE CONTROLE"): h-9 = chip, h-11 = controle.
const d = computed(() => ({
  ...cardScale(props.density),
  ...{
    compact: { timer: "text-base", timerH: "h-9", item: "text-sm", note: "text-xs" },
    cozy: { timer: "text-lg", timerH: "h-9", item: "text-base", note: "text-sm" },
    roomy: { timer: "text-xl", timerH: "h-11", item: "text-lg", note: "text-base" },
  }[props.density],
}));
</script>

<template>
  <article
    class="relative flex w-full flex-col overflow-hidden rounded-md border transition"
    :class="[
      d.gap,
      d.padB,
      finishing
        ? 'border-dashed bg-muted/40'
        : next
          ? `shadow-lg ${nextSurface}`
          : 'bg-card shadow-sm',
    ]"
    :data-status="ticket.status"
  >
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
        :class="[d.inset, d.padT, d.gap, finishing ? 'opacity-45' : '']"
      >
        <!-- Pedido de teste da homologação do iFood: a trava do servidor não cria
             ticket para ele, então este card só existe para o que já estava no
             painel. O aviso vem ANTES do código: quem lê o card tem de saber que
             aquilo não se forna antes de ler o que é. -->
        <KdsTestOrderBanner
          v-if="ticket.test_order_label"
          :label="ticket.test_order_label"
          forbids="não produzir"
        />

        <!-- IDENTIDADE: chamada (canal + entrega/retirada) · CÓDIGO · contexto.
             "Adicional" é a única marca com selo, porque é a única que muda o que
             se FAZ — o resto acompanha o nome, sem caixa. -->
        <KdsCardIdentity
          :code="code"
          :code-class="d.code"
          :channel-icon="ticket.channel_icon"
          :overline="overline"
        >
          <div
            v-if="customerLabel || addition || ticket.previous_tab_ref"
            class="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm font-medium text-muted-foreground"
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
            <span
              v-if="ticket.previous_tab_ref"
              class="line-through"
              :title="`Comanda ${ticket.previous_tab_ref} já liberada`"
              >Comanda {{ ticket.previous_tab_ref }}</span
            >
          </div>

          <!-- À direita, o relógio — o único chip. A marca do detalhe é um sinal
               (a área inteira já é o alvo), não um segundo botão para errar, e
               por isso não ganha moldura. -->
          <template #aside>
            <div class="flex shrink-0 items-center gap-1">
              <div
                class="inline-flex items-center gap-1.5 rounded-md border px-2.5 font-bold tabular-nums"
                :class="[
                  ticket.is_scheduled ? 'bg-muted text-muted-foreground' : timerChip,
                  d.timerH,
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
              <Icon
                name="lucide:info"
                class="size-4 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />
            </div>
          </template>
        </KdsCardIdentity>

        <!-- Notas do pedido: completas (podem ser alergia), num bloco só. -->
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

        <!-- time-to-SLA: fecha o bloco de identidade. Trilha dentro da margem, no
             lugar do fio que separa identidade e itens na expedição. -->
        <div
          v-if="!ticket.is_scheduled"
          class="h-1.5 w-full overflow-hidden rounded-full bg-foreground/10"
          aria-hidden="true"
        >
          <div
            class="h-full rounded-full transition-[width] duration-500"
            :class="barFill"
            :style="{ width: `${fill}%` }"
          />
        </div>

        <!-- TAREFA: só os itens, inteiros. -->
        <ul class="-my-1.5 flex flex-col divide-y divide-border/50">
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

    <!-- AÇÃO: um botão, o ato escrito nele, na base do card, dentro da moldura. -->
    <div v-if="finishing" class="flex flex-col gap-2" :class="d.inset" data-kds-undo>
      <p
        class="flex items-center justify-center gap-1.5 text-sm font-semibold text-muted-foreground"
      >
        <Icon name="lucide:check-check" class="size-4 shrink-0" />
        Finalizado — sai em {{ undoWindowSeconds }}s
      </p>
      <div class="h-1 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
        <div class="kds-undo-drain h-full bg-foreground/50" />
      </div>
      <KdsCardButton
        tone="outline"
        :icon="action.icon"
        :label="action.label"
        :size-class="d.action"
        :aria-label="actionAria"
        data-kds-action
        @click="onAction"
      />
    </div>
    <div v-else-if="ticket.is_scheduled" :class="d.inset">
      <KdsCardButton
        tone="inert"
        icon="lucide:calendar-clock"
        :label="`Prévia${scheduledDate ? ` · começa em ${scheduledDate}` : ''}`"
        :size-class="d.action"
        data-kds-action
      />
    </div>
    <div v-else :class="d.inset">
      <KdsCardButton
        :tone="actionTone"
        :icon="action.icon"
        :label="action.label"
        :size-class="d.action"
        :disabled="!action.enabled"
        :aria-label="actionAria"
        data-kds-action
        @click="onAction"
      />
    </div>
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
