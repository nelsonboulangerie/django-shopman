<script setup lang="ts">
// Ticket de preparo, no desenho da prévia v4 (`cozinha-estacao4.html`, `.tk`). TRÊS
// zonas, na ordem em que a cozinha pergunta (QUE PEDIDO · QUANTO TEMPO · QUE TAREFA)
// e um só ato por vez:
//
// - IDENTIDADE (topo): o código grande e, embaixo, "Retirada"/"Entrega" (prévia v4,
//   nota 6: sem canal, telefone nem cliente; só a encomenda diz o cliente, com quem a
//   hora foi combinada); "iniciado por Rafael às 21:56 · retira às 22:30" logo abaixo
//   quando houver (nota 7); à direita o relógio (o tempo contra a meta num número só, a cor diz se
//   está no prazo) e a pílula do estado ("Próximo · atrasado", "Novo", "Em preparo",
//   "Bloqueado").
// - TAREFA (meio): os itens, inteiros. Nome e observação quebram linha, e o card
//   cresce o quanto precisar; ticket longo ocupa duas alturas na grade em vez de
//   cortar a lista (quem decide é a página, por `isTallTicket`).
// - AÇÃO (base): UM botão, com o ato escrito: "Iniciar preparo" → "Pronto W07"
//   (o mesmo nome no polegar do celular, `thumbActionLabel`). Quando o servidor
//   recusaria o Pronto (pagamento não confirmado), o
//   card diz ANTES do toque, numa caixa com cadeado, e o botão fica tracejado.
//
// A área grande (identidade + itens) faz o que é SEGURO: abre o detalhe. O ato que
// sai da cozinha exige o botão rotulado.
//
// Pronto não some com o card: por 5 s ele fica no lugar, apagado, com
// "Desfazer" exatamente onde o dedo acabou de tocar. O tempo mora no próprio botão
// (`OperatorTimedButton` do kit: o fundo esvazia até a janela fechar).
//
// O preparo é estado do TICKET, guardado no servidor: todos os tablets veem quem
// já pegou o pedido.
import type { KDSTicketProjection } from "~/types/kds";
import {
  cardScale,
  elapsedLabel,
  KDS_ARM_DELAY_MS,
  KDS_UNDO_WINDOW_MS,
  pillClass,
  splitRef,
  cardActionLabel,
  thumbActionLabel,
  ticketAction,
  ticketOverline,
  ticketPill,
  ticketStartLine,
  ticketTone,
  toneNextSurface,
  toneTimerChip,
  type KDSDensity,
} from "~/presentation/board";
import KdsCardButton, { type KdsCardButtonTone } from "~/components/KdsCardButton.vue";
import KdsTestOrderBanner from "~/components/KdsTestOrderBanner.vue";

const props = withDefaults(
  defineProps<{
    ticket: KDSTicketProjection;
    density?: KDSDensity;
    next?: boolean;
    /** Há item cancelado deste pedido sem confirmação: o Pronto espera. */
    blocked?: boolean;
    /** Ticket adicional de um pedido que já passou por esta estação. */
    addition?: boolean;
    /** Marcado Pronto com a janela de "Desfazer" ainda aberta. */
    finishing?: boolean;
    /** Fim da janela do "Desfazer" (epoch ms), guardado pelo quadro: o card pode
     *  montar de novo sem reiniciar a janela. Sem ele, conta do momento em que abriu. */
    finishUntil?: number;
    /** Rótulo fino acima do código (celular: "Agora"). */
    eyebrow?: string;
    /** Seletor para onde o botão vai (celular: a barra do polegar). Vazio = no card. */
    actionTarget?: string;
  }>(),
  {
    density: "cozy",
    next: false,
    blocked: false,
    addition: false,
    finishing: false,
    finishUntil: undefined,
    eyebrow: "",
    actionTarget: "",
  },
);
const emit = defineEmits<{ start: []; finish: []; blocked: []; locked: []; undo: []; open: []; hold: [] }>();

const tone = computed(() => ticketTone(props.ticket.timer_class));
const code = computed(() => splitRef(props.ticket.order_ref).code);
const overline = computed(() => ticketOverline(props.ticket));
const startLine = computed(() => ticketStartLine(props.ticket));
const finishLocked = computed(() => Boolean(props.ticket.finish_block_label) && !props.finishing);
// Toque longo (celular, prévia v4 nota 7): desfazer, reabrir e ver o pedido, sem botões
// a mais na tela. A página decide se escuta (`@hold`).
const longPress = useLongPress(() => emit("hold"));

// Armar o Pronto: o botão fica no MESMO lugar nos dois estados, então o toque
// que INICIOU não pode, quicando, marcar Pronto também. O rótulo já é "Pronto"
// durante o intervalo — o que muda é só ele não aceitar o toque. Card que
// já chega em preparo (outro tablet, recarga) nasce armado.
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
  else if (kind === "locked") emit("locked");
  else if (kind === "undo") emit("undo");
}

// Nome acessível do botão: o rótulo já diz o ato; o leitor de tela precisa saber
// de QUE pedido é o ato, porque na grade há muitos botões com o mesmo texto.
const actionAria = computed(() => {
  const kind = action.value.kind;
  if (kind === "start") return `Iniciar o preparo do pedido ${code.value}`;
  if (kind === "finish") return `Marcar o pedido ${code.value} como pronto`;
  if (kind === "undo") return `Desfazer o Pronto do pedido ${code.value}`;
  if (kind === "blocked")
    return `Pedido ${code.value}: toque em Recebi o cancelamento, no cartão vermelho, para poder marcar Pronto`;
  if (kind === "locked")
    return `Pedido ${code.value}: ${props.ticket.finish_block_label}. ${props.ticket.finish_block_reason}`;
  return "";
});

// Tom do botão por ato (v4): o convite do PRÓXIMO é o único sólido de iniciar; os
// outros convites são contornados; Pronto é verde sólido; travado é tracejado.
const actionTone = computed<KdsCardButtonTone>(() => {
  const kind = action.value.kind;
  if (kind === "start") return props.next ? "lead" : "invite";
  if (kind === "finish") return "confirm";
  if (kind === "blocked") return "blocked";
  if (kind === "locked") return "locked";
  return "outline";
});

const pill = computed(() =>
  props.finishing
    ? null
    : ticketPill(props.ticket, { next: props.next, blocked: props.blocked || finishLocked.value }),
);
const surface = computed(() => {
  if (props.finishing) return "border border-dashed border-border bg-muted/40";
  if (props.next) return toneNextSurface(tone.value);
  if (props.blocked || finishLocked.value) return "border border-destructive/50 bg-card";
  if (props.ticket.status === "in_progress") return "border border-primary/50 bg-card";
  return "border border-border bg-card";
});
const timerChip = computed(() => toneTimerChip(tone.value));
// O Pronto leva o código em todo tamanho ("Pronto W07"); no polegar do celular os
// outros atos também levam, porque o card em foco fica longe do dedo.
const actionLabel = computed(() =>
  props.actionTarget ? thumbActionLabel(action.value, code.value) : cardActionLabel(action.value, code.value),
);
// O prazo do Desfazer: o do quadro, ou, sem ele, o instante em que o card o viu abrir.
const undoUntil = ref(0);
watch(
  () => [props.finishing, props.finishUntil] as const,
  ([finishing, until]) => {
    undoUntil.value = finishing ? (until ?? (undoUntil.value || Date.now() + KDS_UNDO_WINDOW_MS)) : 0;
  },
  { immediate: true },
);
// Observação curta mora na linha do item ("Pão de Hambúrguer · sem gergelim"); a longa
// ganha a caixa "Obs.:" embaixo dele, inteira. As duas em âmbar (v4).
function isShortNote(notes: string): boolean {
  return Boolean(notes) && notes.length <= 24 && !notes.includes("\n");
}

// Moldura comum (margem, ritmo, código, botão) + o que só o preparo tem: o relógio e
// o corpo dos itens e das notas. `timerH` segue a escada do canon do kit
// (operator-base.css, "ALTURAS DE CONTROLE"): h-9 = chip, h-11 = controle.
const d = computed(() => ({
  ...cardScale(props.density),
  ...{
    compact: { timer: "text-base", timerH: "h-9", item: "text-base leading-snug", note: "text-xs" },
    cozy: { timer: "text-lg", timerH: "h-9", item: "text-lg leading-[1.375rem]", note: "text-sm" },
    roomy: { timer: "text-xl", timerH: "h-11", item: "text-xl leading-snug", note: "text-base" },
  }[props.density],
}));
</script>

<template>
  <article
    class="relative flex w-full flex-col overflow-hidden rounded-xl transition"
    :class="[d.gap, d.padB, surface]"
    :data-status="ticket.status"
    :data-next="next || undefined"
  >
    <!-- ÁREA DE LEITURA: identidade + itens. Um toque aqui abre o detalhe — o gesto
         seguro fica com a área grande, o gesto que sai da cozinha fica no botão. -->
    <div class="relative flex flex-1 flex-col" v-bind="longPress" data-kds-hold>
      <button
        v-if="!finishing"
        type="button"
        class="absolute inset-0 z-0 rounded-t-xl transition hover:bg-accent/20 active:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        :aria-label="`Ver o detalhe do pedido ${code}`"
        data-kds-open
        @click="emit('open')"
      />

      <div
        class="pointer-events-none relative z-10 flex flex-1 flex-col"
        :class="[d.inset, d.padT, d.gap, finishing ? 'opacity-45' : '']"
      >
        <!-- Pedido de teste da homologação do iFood: o aviso vem ANTES do código. -->
        <KdsTestOrderBanner
          v-if="ticket.test_order_label"
          :label="ticket.test_order_label"
          forbids="não produzir"
        />

        <!-- IDENTIDADE: código · Retirada/Entrega e cliente | relógio + pílula. -->
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0 flex-1">
            <span v-if="eyebrow" class="block op-micro text-muted-foreground">{{ eyebrow }}</span>
            <p
              class="whitespace-nowrap font-bold leading-none tracking-tight tabular-nums"
              :class="d.code"
            >
              {{ code }}
            </p>
            <div class="mt-1 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 op-label text-muted-foreground">
              <span
                v-if="addition"
                class="inline-flex h-6 items-center gap-1 rounded-full px-2 text-xs font-semibold pill-info"
              >
                <Icon name="lucide:plus" class="size-3" />Adicional
              </span>
              <span class="min-w-0 break-words" data-kds-overline>{{ overline }}</span>
              <span
                v-if="ticket.previous_tab_ref"
                class="line-through"
                :title="`Comanda ${ticket.previous_tab_ref} já liberada`"
                >Comanda {{ ticket.previous_tab_ref }}</span
              >
            </div>
          </div>

          <!-- À direita, o relógio (o único chip com moldura) e a pílula do estado. -->
          <div class="flex shrink-0 flex-col items-end gap-1">
            <span
              class="inline-flex items-center gap-1.5 rounded-lg px-2.5 font-bold tabular-nums"
              :class="[timerChip, d.timerH, d.timer]"
            >
              <Icon
                name="lucide:timer"
                class="size-5 shrink-0"
                :class="tone === 'ok' ? 'text-muted-foreground' : ''"
              />
              {{ elapsedLabel(ticket.elapsed_seconds) }}
            </span>
            <span
              v-if="pill"
              class="inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-xs font-semibold whitespace-nowrap"
              :class="pillClass(pill.tone)"
              data-kds-pill
            >
              <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />{{ pill.label }}
            </span>
          </div>
        </div>

        <!-- Quem iniciou e a hora combinada (v4: "iniciado por Rafael às 21:56 · retira às 22:30"). -->
        <p
          v-if="startLine"
          class="flex min-w-0 items-start gap-1.5 op-micro text-muted-foreground"
          data-kds-started
        >
          <Icon name="lucide:user-round" class="mt-px size-3.5 shrink-0" aria-hidden="true" />
          <span class="min-w-0 break-words">{{ startLine }}</span>
        </p>

        <!-- TAREFA: só os itens, inteiros. -->
        <ul class="flex flex-col divide-y divide-border border-t border-border">
          <li
            v-for="(item, idx) in ticket.items"
            :key="idx"
            class="flex items-start gap-2.5 py-1.5"
          >
            <span
              class="w-[2.5ch] shrink-0 font-semibold tabular-nums"
              :class="d.item"
              >{{ item.qty }}×</span
            >
            <div class="min-w-0 flex-1">
              <p class="break-words font-semibold" :class="d.item">
                {{ item.name
                }}<span v-if="isShortNote(item.notes)" class="text-sm text-warning"> · {{ item.notes }}</span>
              </p>
              <p
                v-if="item.notes && !isShortNote(item.notes)"
                class="mt-1 flex w-fit max-w-full items-start gap-1.5 rounded-md bg-warning/15 px-2.5 py-1 font-semibold leading-snug text-warning"
                :class="d.note"
              >
                <Icon name="lucide:message-square-warning" class="mt-0.5 size-4 shrink-0" />
                <span class="min-w-0 whitespace-pre-wrap break-words">Obs.: {{ item.notes }}</span>
              </p>
              <p
                v-if="item.stock_warning"
                class="mt-1 flex items-start gap-1.5 font-semibold leading-snug text-warning"
                :class="d.note"
              >
                <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
                <span class="min-w-0 break-words">{{ item.stock_warning }}</span>
              </p>
            </div>
          </li>
        </ul>

        <!-- Notas do pedido: completas (podem ser alergia), destacadas, depois dos itens (v4). -->
        <div
          v-if="ticket.kitchen_note || ticket.customer_note"
          class="flex flex-col gap-1 rounded-md bg-warning/15 px-2.5 py-1.5 font-semibold leading-snug text-warning"
          :class="d.note"
          data-kds-order-notes
        >
          <p v-if="ticket.kitchen_note" class="flex items-start gap-1.5">
            <Icon name="lucide:chef-hat" class="mt-0.5 size-4 shrink-0" />
            <span class="min-w-0 whitespace-pre-wrap break-words">{{ ticket.kitchen_note }}</span>
          </p>
          <p v-if="ticket.customer_note" class="flex items-start gap-1.5">
            <Icon name="lucide:message-square-warning" class="mt-0.5 size-4 shrink-0" />
            <span class="min-w-0 whitespace-pre-wrap break-words">{{ ticket.customer_note }}</span>
          </p>
        </div>

        <!-- O motivo do bloqueio ANTES do toque (era um toast 5 s depois, K11). -->
        <div
          v-if="finishLocked"
          class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/12 px-2.5 py-1.5"
          data-kds-finish-block
        >
          <Icon name="lucide:lock" class="mt-0.5 size-4 shrink-0 text-destructive" />
          <p class="op-label leading-snug">
            <b class="text-destructive">{{ ticket.finish_block_label }}.</b>
            {{ ticket.finish_block_reason }}
          </p>
        </div>
      </div>
    </div>

    <!-- AÇÃO: um botão, o ato escrito nele, na base do card, dentro da moldura (no
         celular, o card em foco leva o botão para a barra do polegar). -->
    <Teleport defer :to="actionTarget || 'body'" :disabled="!actionTarget">
      <div v-if="finishing" :class="actionTarget ? '' : d.inset" data-kds-undo>
        <OperatorTimedButton
          :until="undoUntil"
          :duration="KDS_UNDO_WINDOW_MS"
          :label="actionLabel"
          icon="i-lucide-undo-2"
          size="xl"
          variant="outline"
          color="neutral"
          block
          class="justify-center"
          :class="d.action"
          :aria-label="actionAria"
          data-kds-action
          @click="onAction"
        />
      </div>
      <div v-else :class="actionTarget ? '' : d.inset">
        <KdsCardButton
          :tone="actionTone"
          :icon="action.icon"
          :label="actionLabel"
          :size-class="d.action"
          :disabled="!action.enabled"
          :aria-label="actionAria"
          :title="action.kind === 'locked' ? ticket.finish_block_reason : undefined"
          data-kds-action
          @click="onAction"
        />
      </div>
    </Teleport>
  </article>
</template>
