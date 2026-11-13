<script setup lang="ts">
// Um cartão de pedido no quadro, no desenho da prévia v4 (UX-KIT-V2,
// `docs/plans/suite-ux-v2/fontes/v4/gestor-colunas4.html` e `gestor-fila4.html`):
//
//   código grande + nome                         selo do estado · tempo
//   etiquetas cheias (Retirada · 3 itens …)
//   itens
//   andamento numa frase, sem barra ("Produção de Croissant: não começou")
//   "Pronto pela Cozinha · desfazer" (a última estação fechou o pedido)
//   bloqueio escrito no cartão
//   pagamento ······························ total
//   [ botão largo com o verbo e o nome: "Entregar a Ana" ]  [⋯]
//
// O que a v4 não mostra no cartão fica a um toque: atribuir ("Atender") e a seleção em
// lote moram no ⋯ do cartão (e no toque longo); o detalhe abre pelo código. Nenhuma
// ação saiu: só mudou de lugar. O cor do estado é funcional; o resto é neutro.
import type { ButtonProps } from "#ui/types";
import type { OrderCardProjection } from "~/types/orders";
import {
  cardAffordances,
  cardAuthorizationNotice,
  cardClock,
  cardSeal,
  channelLabel,
  ifoodAcceptNotice,
  onRoadLine,
  packLabel,
  primaryVerb,
  splitRef,
  kitchenWaiting,
  productionLines,
  undoLine,
  type AffordanceRef,
  type Tone,
} from "~/presentation/board";
import { computed, onBeforeUnmount } from "vue";
import { danfeLine } from "~/presentation/danfe";
import { COURIER_CALL_HASH, courierReminderLine } from "~/presentation/courier";
import { kitchenChips } from "~/presentation/kitchen";
import { cardCheckBadge } from "~/presentation/volumeCheck";
import OrderCardActions from "./OrderCardActions.vue";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

// ``canOpen``: falso para quem só expede; o detalhe do pedido e o "Atender" são de quem
// gerencia. ``selecting``: o modo de seleção em lote está ligado e o cartão mostra a
// caixa. ``next``: o primeiro da Saída a sair (selo "Próximo" e moldura).
const props = withDefaults(
  defineProps<{
    card: OrderCardProjection;
    busy?: boolean;
    error?: string;
    selected?: boolean;
    selecting?: boolean;
    next?: boolean;
    danfePrinting?: boolean;
    canOpen?: boolean;
    /** Celular (G17): o Recusar mora no deslize do cartão; a ação principal fica larga. */
    swipeReject?: boolean;
    /** O Quadro da mesa (D, dono 13/11/2026, prévia `gestor-d`): o cartão enxuto, em
     *  quatro linhas (código, selo e valor; quem; itens; o gesto e o ⋮). O que é
     *  exceção (avisos, erro, desfazer, DANFE) só aparece quando existe. */
    compact?: boolean;
  }>(),
  { canOpen: true },
);
const emit = defineEmits<{
  (e: "action", ref: AffordanceRef): void;
  (
    e:
      | "dismiss-error"
      | "toggle-select"
      | "toggle-assign"
      | "print-danfe"
      | "select-mode",
  ): void;
  (e: "station-ready", stationRef: string): void;
  (e: "station-recall" | "volumes", value: number): void;
}>();

const code = computed(() => splitRef(props.card.ref));
const pack = computed(() => packLabel(props.card));
// A conferência das sacolas (P1-13), só depois da primeira bipada.
const checkBadge = computed(() => cardCheckBadge(props.card));
const nowMs = useNowTick(() => props.card.server_now_iso);
const clock = computed(() => cardClock(props.card, nowMs.value));
const seal = computed(() => cardSeal(props.card, { next: props.next }));

// A Cozinha neste pedido: quem ainda falta, o "Pronto" da estação sem tela e o
// "Voltar para…" no menu do pedido.
const kitchenMissing = computed(() => kitchenWaiting(props.card.kitchen));
const attentionStations = computed(() =>
  kitchenChips(props.card.kitchen).filter(
    (chip) => chip.canMarkReady || chip.tone === "alert" || chip.cancelledNote,
  ),
);

const onRoad = computed(() => onRoadLine(props.card));
const affordances = computed(() => cardAffordances(props.card));
const primary = computed(
  () =>
    affordances.value.find((a) => a.priority === "primary" || a.disabled) ??
    null,
);
const secondary = computed(() =>
  affordances.value.filter(
    (a) => a !== primary.value && !(props.swipeReject && a.ref === "reject"),
  ),
);
const primaryLabel = computed(() =>
  primary.value ? primaryVerb(props.card, primary.value) : "",
);
// A estação ainda trabalha e o "Marcar pronto" mora no menu: o lugar do botão diz o que
// se espera ("Aguardando Café"), sem ser botão.
const waitingFor = computed(() => (primary.value ? "" : kitchenMissing.value));
// O andamento do pedido: uma frase por coisa que ele espera, nunca barra (dono,
// 02/11/2026: barras de cores e tamanhos diferentes não diziam a que se referiam).
// A Cozinha só entra aqui quando o botão do pedido não diz o "Aguardando".
const progressLines = computed(() => [
  ...productionLines(props.card).map((line) => ({
    key: line.ref,
    icon: "lucide:factory",
    text: line.text,
  })),
  ...(primary.value && kitchenMissing.value
    ? [{ key: "kitchen", icon: "lucide:chef-hat", text: `Aguardando ${kitchenMissing.value}` }]
    : []),
]);

// Pagamento: o tom vem da projeção. Dinheiro não é "pago" nem "devendo".
const paymentColor = computed<"warning" | "error" | "success" | "neutral">(
  () => {
    const tone = props.card.payment_tone as Tone;
    if (tone === "warning") return "warning";
    if (tone === "danger") return "error";
    if (tone === "success") return "success";
    return "neutral";
  },
);
const paymentIcon = computed(() => {
  if (!props.card.payment_method) return "lucide:circle-help";
  return (
    {
      warning: "lucide:hourglass",
      danger: "lucide:alert-triangle",
      success: "lucide:check",
      neutral: "lucide:banknote",
    }[props.card.payment_tone] || "lucide:banknote"
  );
});

const danfe = computed(() => danfeLine(props.card));
// "O sistema fez · desfazer": o pronto que veio da Cozinha, ou a saída tocada ainda na
// janela. O fato fica à vista; o gesto só enquanto o prazo corre.
const undo = computed(() => undoLine(props.card, nowMs.value));
const handoff = computed(() =>
  undo.value?.kind === "handoff" ? undo.value : null,
);
// Toque longo liga a seleção em lote (como no celular de qualquer lista).
let pressTimer: ReturnType<typeof setTimeout> | null = null;
function pressStart(event: PointerEvent) {
  if (props.selecting || event.button > 0) return;
  if ((event.target as HTMLElement).closest("button, a, input, textarea"))
    return;
  // Toque longo liga a seleção em lote em qualquer coluna.
  pressTimer = setTimeout(() => {
    pressTimer = null;
    emit("select-mode");
  }, 550);
}
function pressEnd() {
  if (pressTimer) clearTimeout(pressTimer);
  pressTimer = null;
}
onBeforeUnmount(pressEnd);

/** Um aviso do pedido, compacto: a pílula no cartão e o Alert inteiro no Popover. */
interface CardNotice {
  key: string;
  color: "error" | "warning" | "info";
  icon: string;
  /** Rótulo curto da pílula. */
  label: string;
  title: string;
  description?: string;
  actions?: ButtonProps[];
  /** Ganchos de teste no Alert do Popover. */
  attrs?: Record<string, string>;
}

// Os avisos longos (DANFE, NFC-e, iFood, bloqueio, papel da cozinha) deixam o cartão
// alto demais (dono, 07/10/2026): no cartão fica a pílula com a cor e o nome; o texto
// e a ação abrem no Popover, a um toque.
const notices = computed<CardNotice[]>(() => {
  const out: CardNotice[] = [];
  const card = props.card;
  if (card.test_order_notice)
    out.push({
      key: "test-order",
      color: "warning",
      icon: "i-lucide-flask-conical",
      label: "Pedido de teste",
      title: card.test_order_label || "Pedido de teste",
      description: card.test_order_notice,
      attrs: { "data-test-order-notice": "" },
    });
  if (handoff.value) return out;
  // O aceite saiu daqui e não chegou ao iFood: a cozinha trabalha e o iFood cancela
  // no prazo dele (o mesmo do canto do cartão). Vermelho, com o reenvio no aviso.
  const ifoodAccept = ifoodAcceptNotice(card, nowMs.value);
  if (ifoodAccept)
    out.push({
      key: "ifood-accept",
      color: "error",
      icon: "i-lucide-send",
      label: ifoodAccept.label,
      title: ifoodAccept.title,
      description: ifoodAccept.description,
      actions: ifoodAccept.action
        ? [
            action(
              {
                icon: "i-lucide-refresh-cw",
                label: ifoodAccept.action.label,
                disabled: props.busy || !ifoodAccept.action.enabled,
                onClick: () => emit("action", "ifood_accept_retry"),
              },
              {
                "aria-label": `${ifoodAccept.action.label}: enviar o aceite do pedido ${code.value.code} ao iFood`,
                ...(ifoodAccept.action.reason
                  ? { title: ifoodAccept.action.reason }
                  : {}),
                "data-ifood-accept-retry": "",
              },
            ),
          ]
        : [],
      attrs: { "data-ifood-accept": "" },
    });
  // Cartão autorizado esperando aceite: a reserva vence no Stripe. O aviso traz o
  // prazo e os dois gestos que o resolvem, na cor do aviso (D8).
  const cardAuth = cardAuthorizationNotice(
    card.card_authorization_expires_iso,
    nowMs.value,
  );
  if (cardAuth) {
    const accept = affordances.value.find((a) => a.ref === "confirm");
    const reject = affordances.value.find((a) => a.ref === "reject");
    out.push({
      key: "card-authorization",
      color: cardAuth.tone,
      icon: "i-lucide-credit-card",
      label: cardAuth.label,
      title: cardAuth.title,
      description: cardAuth.description,
      actions: cardAuth.expired
        ? undefined
        : [
            accept &&
              action(
                {
                  label: "Aceitar",
                  icon: "i-lucide-check",
                  disabled: props.busy || accept.disabled,
                  onClick: () => emit("action", "confirm"),
                },
                { "data-card-authorization-accept": "" },
              ),
            reject &&
              action(
                {
                  label: "Recusar",
                  icon: "i-lucide-x",
                  disabled: props.busy || reject.disabled,
                  onClick: () => emit("action", "reject"),
                },
                { "data-card-authorization-reject": "" },
              ),
          ].filter((a): a is ButtonProps => Boolean(a)),
      attrs: { "data-card-authorization": "" },
    });
  }
  // Lembrete temporário (até a chamada antecipada aprender): entrega da casa em
  // preparo há X min sem entregador chamado. O "Chamar entregador" abre o pedido
  // com a confirmação armada (a corrida é paga: a pergunta vem antes).
  const reminder = courierReminderLine(card.courier_reminder, nowMs.value);
  if (reminder)
    out.push({
      key: "courier-reminder",
      color: "warning",
      icon: "i-lucide-bike",
      label: "Chamar entregador?",
      title: reminder,
      actions: [
        action(
          {
            label: "Chamar entregador",
            icon: "i-lucide-send",
            to: `/${card.ref}${COURIER_CALL_HASH}`,
          },
          { "data-courier-reminder-call": "" },
        ),
        action(
          {
            label: "Dispensar",
            disabled: props.busy,
            onClick: () => emit("action", "dismiss_courier_reminder"),
          },
          {
            "aria-label": `Dispensar o lembrete do pedido ${code.value.code}`,
            "data-courier-reminder-dismiss": "",
          },
        ),
      ],
      attrs: { "data-courier-reminder": "" },
    });
  if (card.advance_block_reason)
    out.push({
      key: "block",
      color: seal.value.tone === "error" ? "error" : "info",
      icon: "i-lucide-lock",
      label: "Por que espera",
      // O nome do bloqueio primeiro ("Pix expirado"), o porquê embaixo: só os
      // horários ("gerado às 05:51 · expirou às 05:57") não diziam o que trava.
      // O mesmo par do aviso de bloqueio do detalhe.
      title: card.advance_block_label?.replace(/…$/, "") || "Bloqueado",
      description: card.advance_block_reason,
      // Pix ou link vencido nunca destrava sozinho: o próximo passo vem pronto.
      // O detalhe abre o cancelar com "Pagamento não confirmado" já marcado.
      actions: card.payment_lapsed
        ? [
            action(
              {
                label: "Cancelar pedido",
                icon: "i-lucide-ban",
                to: `/${card.ref}#cancel-unpaid`,
              },
              { "data-cancel-unpaid": "" },
            ),
          ]
        : undefined,
      attrs: { "data-advance-block": "" },
    });
  for (const chip of attentionStations.value)
    out.push({
      key: `station-${chip.ref}`,
      color: chip.tone === "alert" ? "error" : "info",
      icon: nuxtIcon(chip.icon),
      label: chip.station,
      title: chip.station,
      description: `${chip.detail}${chip.cancelledNote ? ` · ${chip.cancelledNote}` : ""}`,
      actions: chip.canMarkReady
        ? [
            action(
              {
                icon: "i-lucide-check",
                label: `Pronto de ${chip.station}`,
                disabled: props.busy,
                onClick: () => emit("station-ready", chip.ref),
              },
              {
                "aria-label": `Pronto de ${chip.station} no pedido ${code.value.code}`,
                "data-kitchen-ready": "",
              },
            ),
          ]
        : undefined,
      attrs: { "data-kitchen-attention": "" },
    });
  if (danfe.value?.attention)
    out.push({
      key: "danfe",
      color: "warning",
      icon: "i-lucide-receipt",
      label: "DANFE não impressa",
      title: danfe.value.status,
      description: danfe.value.problem || undefined,
      actions: [
        action(
          {
            label:
              props.danfePrinting || danfe.value.sending
                ? "Imprimindo…"
                : danfe.value.action,
            icon: "i-lucide-printer",
            disabled: props.danfePrinting || danfe.value.sending,
            onClick: () => emit("print-danfe"),
          },
          { "data-danfe-print": "" },
        ),
      ],
      attrs: { "data-danfe": "", "data-danfe-attention": "" },
    });
  if (card.fiscal_status === "failed")
    out.push({
      key: "fiscal",
      color: "warning",
      icon: "i-lucide-file-x",
      label: "NFC-e não autorizada",
      title: "NFC-e não autorizada",
      description: "O pedido tem o Reprocessar NFC-e.",
      actions: [
        action(
          {
            label: "Abrir e reprocessar",
            to: `/${card.ref}`,
          },
          { "data-fiscal-failed-open": "" },
        ),
      ],
      attrs: { "data-fiscal-failed": "" },
    });
  if (card.ifood_negotiations?.length)
    out.push({
      key: "negotiation",
      color: "warning",
      icon: "i-lucide-message-square-warning",
      label: "Negociação iFood",
      title: "Negociação iFood",
      description: "O iFood espera resposta dentro do prazo.",
      actions: [
        action(
          {
            label: "Abrir solicitação",
            to: `/${card.ref}#ifood-negotiations`,
          },
          { "data-ifood-negotiation-link": "" },
        ),
      ],
      attrs: { "data-ifood-negotiation": "" },
    });
  if (card.ifood_cancellation_notice)
    out.push({
      key: "ifood-cancellation",
      color: "warning",
      icon: "i-lucide-circle-x",
      label: "Cancelamento no iFood",
      title: card.ifood_cancellation_notice,
      attrs: { "data-ifood-cancellation": "" },
    });
  if (card.ifood_remote_ahead_label)
    out.push({
      key: "ifood-ahead",
      color: "info",
      icon: "i-lucide-info",
      label: "iFood à frente",
      title: card.ifood_remote_ahead_label,
      attrs: { "data-ifood-remote-ahead": "" },
    });
  return out;
});

/** Ação de Alert com ganchos de teste ou nome acessível: o tipo `ButtonProps` não
 *  declara `data-*` nem `aria-label`, mas o Nuxt UI os repassa ao botão. */
function action(
  props: ButtonProps,
  attrs: Record<string, string>,
): ButtonProps {
  return { ...props, ...attrs };
}
// O selo único do cartão enxuto: o que muda o que o operador faz primeiro (a saída
// tocada, o prazo que decide sozinho, o bloqueio), senão a situação e o tempo.
const compactPill = computed<{ label: string; color: "error" | "warning" | "success" | "neutral" | "info" | "primary" }>(() => {
  if (handoff.value) return { label: handoff.value.label, color: "success" };
  const timeColor =
    clock.value.tone === "late"
      ? "error"
      : clock.value.tone === "warning"
        ? "warning"
        : clock.value.tone === "ready"
          ? "success"
          : "neutral";
  if (clock.value.countdown) return { label: clock.value.text, color: timeColor };
  if (seal.value.tone === "error" || seal.value.tone === "warning")
    return { label: seal.value.label, color: seal.value.tone };
  const status =
    seal.value.label !== props.card.status_label &&
    !props.card.ready_at_iso &&
    !props.card.dispatched_at_iso
      ? `${props.card.status_label} · `
      : "";
  return { label: `${status}${clock.value.text}`, color: timeColor };
});
// A terceira linha: o que saiu com o entregador (maquininha, troco) ou o andamento;
// sem nada disso, os itens.
const compactDetail = computed(() =>
  [onRoad.value, props.card.change_label, progressLines.value[0]?.text]
    .filter(Boolean)
    .join(" · "),
);

function nuxtIcon(icon: string): string {
  return icon.startsWith("lucide:")
    ? `i-lucide-${icon.slice("lucide:".length)}`
    : icon;
}
</script>

<template>
  <!-- O cartão enxuto do Quadro (prévia `gestor-d`): o pedido que espera você ganha a
       moldura na cor principal (`data-highlight="true"` do tema); o "Próximo" da
       saída, o halo (`ready`). -->
  <NuxtCard
    v-if="compact"
    as="article"
    :variant="selected ? 'subtle' : 'outline'"
    :data-card-state="handoff ? 'handoff' : seal.tone"
    :data-highlight="next ? 'ready' : card.attention && !handoff ? 'true' : undefined"
    :aria-selected="selecting ? selected : undefined"
    data-card-compact
    @pointerdown="pressStart"
    @pointerup="pressEnd"
    @pointerleave="pressEnd"
    @pointercancel="pressEnd"
  >
    <div class="flex flex-col gap-1">
    <div class="flex items-baseline gap-2" :class="handoff ? 'opacity-55' : ''">
      <NuxtButton
        v-if="selecting"
        :icon="selected ? 'i-lucide-check-square-2' : 'i-lucide-square'"
        color="neutral"
        variant="ghost"
        square
        class="self-center"
        :aria-label="selected ? 'Desmarcar pedido' : 'Selecionar pedido'"
        :aria-pressed="selected"
        data-card-select
        @click="emit('toggle-select')"
      />
      <NuxtLink
        v-if="canOpen"
        :to="`/${card.ref}`"
        class="shrink-0 text-2xl font-bold leading-none text-highlighted hover:underline"
        :class="handoff ? 'line-through decoration-success/60' : ''"
        :aria-label="`Abrir pedido ${card.ref}`"
        >{{ code.code }}</NuxtLink
      >
      <span
        v-else
        class="shrink-0 text-2xl font-bold leading-none text-highlighted"
        data-card-code
        >{{ code.code }}</span
      >
      <NuxtBadge
        class="min-w-0 self-center"
        :color="compactPill.color"
        :label="compactPill.label"
        :role="clock.countdown ? 'timer' : undefined"
        data-card-clock
      />
      <span class="ms-auto shrink-0 tnum text-muted">{{ card.total_display }}</span>
    </div>
    <p
      class="truncate"
      :title="`${card.customer_name || 'Sem cliente'} · ${channelLabel(card.channel_ref)} · ${card.fulfillment_label}`"
      data-card-who
    >
      {{ card.customer_name || "Sem cliente" }} · {{ channelLabel(card.channel_ref) }} ·
      {{ card.fulfillment_label }}
    </p>
    <p
      v-if="card.items_summary"
      class="truncate op-micro text-muted"
      :title="card.items_summary"
    >
      {{ card.items_summary }}
    </p>
    <p
      v-if="compactDetail && !handoff"
      class="truncate op-micro text-muted"
      :title="compactDetail"
      data-card-detail
    >
      {{ compactDetail }}
    </p>
    <!-- as exceções, só quando existem -->
    <div v-if="notices.length" class="flex flex-wrap gap-1.5" data-card-notices>
      <NuxtPopover
        v-for="notice in notices"
        :key="notice.key"
        :content="{ side: 'bottom', align: 'start' }"
      >
        <NuxtButton
          :color="notice.color"
          variant="soft"
          :icon="notice.icon"
          :label="notice.label"
          :data-card-notice="notice.key"
        />
        <template #content>
          <NuxtAlert
            class="max-w-80"
            :color="notice.color"
            variant="subtle"
            :icon="notice.icon"
            :title="notice.title"
            :description="notice.description"
            :actions="alertActions(notice.color, notice.actions ?? [])"
            v-bind="notice.attrs"
          />
        </template>
      </NuxtPopover>
    </div>
    <!-- O "pronto sozinho" com Desfazer mora na faixa "O sistema fez", abaixo do
         cabeçalho do Quadro; aqui não se repete. -->
    <div
      v-if="danfe && !danfe.attention && !handoff"
      class="flex items-center gap-1.5 op-micro text-muted"
      data-danfe
    >
      <span class="min-w-0 flex-1 truncate" data-danfe-status>{{ danfe.status }}</span>
      <NuxtButton
        icon="i-lucide-printer"
        :label="danfePrinting || danfe.sending ? 'Imprimindo…' : danfe.action"
        color="neutral"
        variant="ghost"
        class="shrink-0"
        :disabled="danfePrinting || danfe.sending"
        data-danfe-print
        @click="emit('print-danfe')"
      />
    </div>
    <NuxtAlert
      v-if="error"
      color="error"
      variant="subtle"
      icon="i-lucide-triangle-alert"
      :title="error"
      :close="action({}, { 'aria-label': 'Dispensar aviso' })"
      data-card-error
      @update:open="emit('dismiss-error')"
    />
    <div class="mt-1.5">
      <OrderCardActions
        :card="card"
        :busy="busy"
        :handoff="handoff"
        :primary="primary"
        :secondary="secondary"
        :primary-label="primaryLabel"
        :waiting-for="waitingFor"
        :can-open="canOpen"
        :selecting="selecting"
        :selected="selected"
        @action="(ref_) => emit('action', ref_)"
        @toggle-assign="emit('toggle-assign')"
        @toggle-select="emit('toggle-select')"
        @select-mode="emit('select-mode')"
        @volumes="(count) => emit('volumes', count)"
        @station-recall="(pk) => emit('station-recall', pk)"
      />
    </div>
    </div>
  </NuxtCard>
  <NuxtCard
    v-else
    as="article"
    class="grid grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr_auto]"
    :variant="selected ? 'subtle' : 'outline'"
    :data-card-state="handoff ? 'handoff' : seal.tone"
    :data-highlight="next ? 'ready' : undefined"
    :aria-selected="selecting ? selected : undefined"
    @pointerdown="pressStart"
    @pointerup="pressEnd"
    @pointerleave="pressEnd"
    @pointercancel="pressEnd"
  >
    <template #header>
      <!-- Duas linhas (dono, 07/10/2026: cartão mais compacto): o código e os selos na
           primeira; quem e o canal na segunda, numa linha só. -->
      <div class="flex flex-col gap-1" :class="handoff ? 'opacity-55' : ''">
        <div class="flex items-center gap-2">
          <NuxtButton
            v-if="selecting"
            :icon="selected ? 'i-lucide-check-square-2' : 'i-lucide-square'"
            color="neutral"
            variant="ghost"
            square
            :aria-label="selected ? 'Desmarcar pedido' : 'Selecionar pedido'"
            :aria-pressed="selected"
            data-card-select
            @click="emit('toggle-select')"
          />
          <NuxtLink
            v-if="canOpen"
            :to="`/${card.ref}`"
            class="group shrink-0"
            :aria-label="`Abrir pedido ${card.ref}`"
          >
            <span
              class="block op-code group-hover:underline"
              :class="handoff ? 'line-through decoration-success/60' : ''"
              >{{ code.code }}</span
            >
          </NuxtLink>
          <span
            v-else
            class="block shrink-0 op-code"
            :class="handoff ? 'line-through decoration-success/60' : ''"
            data-card-code
            >{{ code.code }}</span
          >
          <span
            v-if="card.channel_display_id"
            class="shrink-0 text-xs font-medium tnum text-muted-foreground"
            data-channel-display-id
            >iFood #{{ card.channel_display_id }}</span
          >
          <div
            v-if="!handoff"
            class="ms-auto flex min-w-0 flex-wrap justify-end gap-1"
          >
            <NuxtBadge
              :color="
                seal.tone === 'error'
                  ? 'error'
                  : seal.tone === 'success'
                    ? 'success'
                    : seal.tone === 'warning'
                      ? 'warning'
                      : seal.tone === 'info'
                        ? 'info'
                        : seal.tone === 'primary'
                          ? 'primary'
                          : 'neutral'
              "
              :label="seal.label"
              data-card-seal
            />
            <NuxtBadge
              v-if="clock.countdown"
              :color="
                clock.tone === 'late'
                  ? 'error'
                  : clock.tone === 'warning'
                    ? 'warning'
                    : clock.tone === 'ready'
                      ? 'success'
                      : 'neutral'
              "
              :title="
                card.confirmation_action === 'cancel'
                  ? 'Cancelado automaticamente se vencer'
                  : 'Confirmado automaticamente se vencer'
              "
              :label="clock.text"
              role="timer"
              aria-live="off"
            />
            <NuxtBadge
              v-else
              :color="
                clock.tone === 'late'
                  ? 'error'
                  : clock.tone === 'warning'
                    ? 'warning'
                    : clock.tone === 'ready'
                      ? 'success'
                      : 'neutral'
              "
              :label="`${seal.label !== card.status_label && !card.ready_at_iso && !card.dispatched_at_iso ? `${card.status_label} · ` : ''}${clock.text}`"
              data-card-clock
            />
          </div>
          <span v-else class="ms-auto shrink-0 op-micro text-muted-foreground"
            >{{ card.fulfillment_label
            }}<template v-if="pack"> · {{ pack }}</template></span
          >
        </div>
        <p
          class="truncate op-title"
          :title="`${card.customer_name || 'Sem cliente'} · ${channelLabel(card.channel_ref)}`"
          data-card-who
        >
          <span>{{ card.customer_name || "Sem cliente" }}</span>
          {{ " "
          }}<span class="font-normal text-muted-foreground"
            >· {{ channelLabel(card.channel_ref) }}</span
          >
        </p>
      </div>
    </template>

    <div class="flex h-full flex-col gap-3">
      <!-- Entregue, na janela do desfazer: o cartão fica no lugar; o tempo mora no
           próprio Desfazer do rodapé (o fundo esvazia até a janela fechar). -->
      <template v-if="handoff">
        <NuxtBadge
          class="self-start"
          color="success"
          icon="i-lucide-check"
          :label="handoff.label"
          :data-undo="handoff.kind"
        />
        <p class="op-micro leading-snug text-muted-foreground" data-undo-detail>
          {{ handoff.detail
          }}<span v-if="handoff.alreadyOut" data-undo-already-out>
            · {{ handoff.alreadyOut }}</span
          >
        </p>
      </template>

      <template v-else>
        <!-- etiquetas cheias: os fatos do pedido, com ícone (um estilo só) -->
        <div class="flex flex-wrap gap-2" data-card-tags>
          <NuxtBadge
            color="neutral"
            :icon="
              card.fulfillment_type === 'delivery'
                ? 'i-lucide-bike'
                : 'i-lucide-store'
            "
            :label="card.fulfillment_label"
          />
          <!-- Volume é fato do pedido e, portanto, Badge. A edição permanece na ação
             "Volumes" do menu oficial do cartão; não se disfarça Button de etiqueta. -->
          <NuxtBadge
            v-if="pack"
            color="neutral"
            icon="i-lucide-package"
            :label="pack"
            :data-card-pack="card.volumes ? 'volumes' : 'items'"
          />
          <NuxtBadge
            v-if="checkBadge"
            :color="checkBadge.complete ? 'primary' : 'neutral'"
            :icon="checkBadge.complete ? 'i-lucide-package-check' : 'i-lucide-scan-barcode'"
            :label="checkBadge.label"
            :data-card-volume-check="checkBadge.complete ? 'complete' : 'partial'"
          />
          <NuxtBadge
            v-if="card.is_preorder"
            color="neutral"
            icon="i-lucide-calendar-clock"
            :label="`Encomenda${card.commitment_date_display ? ` · ${card.commitment_date_display}` : ''}`"
            data-preorder-badge
          />
          <!-- fila de espera: o pedido não está parado, está esperando o lote -->
          <NuxtBadge
            v-if="card.waitlist_label"
            :color="
              card.waitlist_state === 'confirming' ? 'primary' : 'neutral'
            "
            icon="i-lucide-hourglass"
            :label="card.waitlist_label"
            data-waitlist-badge
          />
          <NuxtBadge
            v-if="card.is_gift"
            color="neutral"
            icon="i-lucide-gift"
            role="img"
            :aria-label="
              card.gift_has_recipient
                ? 'Presente com destinatário'
                : 'Embalar para presente'
            "
            data-gift-badge
          />
          <NuxtBadge
            v-if="card.has_customer_note"
            color="neutral"
            icon="i-lucide-message-square"
            role="img"
            aria-label="Tem observação do cliente"
            data-customer-note-badge
          />
          <NuxtBadge
            v-if="card.assigned_operator"
            color="primary"
            icon="i-lucide-user-check"
            :label="card.assigned_operator"
            data-card-assigned
          />
        </div>

        <p class="op-body text-foreground/85" :title="card.items_summary">
          {{ card.items_summary }}
        </p>

        <p
          v-if="card.courier_status_label"
          class="flex items-center gap-1.5 truncate op-micro text-muted-foreground"
        >
          <Icon name="lucide:bike" class="size-3.5 shrink-0" />
          {{ card.courier_status_label }}
        </p>
        <!-- para onde vai -->
        <p
          v-if="card.delivery_address"
          class="flex items-center gap-1.5 op-micro text-muted-foreground"
          :title="card.delivery_address"
          data-card-address
        >
          <Icon name="lucide:map-pin" class="size-3.5 shrink-0" />
          <span class="truncate">{{ card.delivery_address }}</span>
        </p>
        <!-- troco da entrega: o que o cliente disse, o que saiu da gaveta, o que voltou -->
        <p
          v-if="card.change_label"
          class="flex items-center gap-1.5 op-micro text-muted-foreground"
          :class="{ 'font-medium text-foreground': card.change_back_pending }"
          data-change-label
        >
          <Icon name="lucide:coins" class="size-3.5 shrink-0" />
          <span class="truncate">{{ card.change_label }}</span>
        </p>
        <!-- a maquininha na rua: o único sinal dela no quadro é esta linha -->
        <p
          v-if="onRoad"
          class="flex items-center gap-1.5 op-micro font-medium"
          data-equipment-label
        >
          <Icon
            :name="
              card.equipment_label ? 'lucide:smartphone-nfc' : 'lucide:bike'
            "
            class="size-3.5 shrink-0"
          />
          <span class="truncate">{{ onRoad }}</span>
        </p>

        <!-- andamento: uma frase por coisa que o pedido espera (a estação que pede
             alguém vira pílula de aviso, em notices) -->
        <ul
          v-if="progressLines.length && !handoff"
          class="flex flex-col gap-1"
          data-card-progress
        >
          <li
            v-for="line in progressLines"
            :key="line.key"
            class="flex items-center gap-1.5 op-label text-muted-foreground"
          >
            <Icon :name="line.icon" class="size-3.5 shrink-0" />
            <span class="min-w-0">{{ line.text }}</span>
          </li>
        </ul>

        <!-- a última estação fechou o pedido: "Pronto pela Cozinha · desfazer" -->
        <div
          v-if="undo && undo.kind === 'auto_ready'"
          class="flex flex-wrap items-center gap-2"
          :data-undo="undo.kind"
        >
          <NuxtBadge
            color="neutral"
            icon="i-lucide-sparkles"
            :label="undo.label"
          />
          <NuxtButton
            v-if="undo.canUndo"
            label="Desfazer"
            color="neutral"
            variant="ghost"
            :disabled="busy"
            data-undo-button
            @click="emit('action', undo.action)"
          />
          <span class="op-micro text-muted-foreground" data-undo-detail>{{
            undo.detail
          }}</span>
          <span
            v-if="undo.alreadyOut"
            class="op-micro text-muted-foreground"
            data-undo-already-out
            >· {{ undo.alreadyOut }}</span
          >
        </div>

        <!-- DANFE que saiu ou vai sair sozinha é fato, com a reimpressão compacta ao lado;
             a que não saiu é aviso (notices). -->
        <div
          v-if="danfe && !danfe.attention"
          class="flex items-center gap-1.5 op-micro text-muted-foreground"
          data-danfe
        >
          <Icon
            :name="
              card.danfe_printed ? 'lucide:receipt-text' : 'lucide:receipt'
            "
            class="size-3.5 shrink-0"
          />
          <span class="min-w-0 flex-1 truncate" data-danfe-status>{{
            danfe.status
          }}</span>
          <NuxtButton
            icon="i-lucide-printer"
            :label="
              danfePrinting || danfe.sending ? 'Imprimindo…' : danfe.action
            "
            color="neutral"
            variant="outline"
            class="shrink-0"
            :disabled="danfePrinting || danfe.sending"
            data-danfe-print
            @click="emit('print-danfe')"
          />
        </div>
      </template>

      <!-- avisos: a pílula com cor e nome; o texto e o gesto no Popover -->
      <div
        v-if="notices.length"
        class="flex flex-wrap gap-1.5"
        data-card-notices
      >
        <NuxtPopover
          v-for="notice in notices"
          :key="notice.key"
          :content="{ side: 'bottom', align: 'start' }"
        >
          <NuxtButton
            :color="notice.color"
            variant="soft"
            :icon="notice.icon"
            :label="notice.label"
            :data-card-notice="notice.key"
          />
          <template #content>
            <NuxtAlert
              class="max-w-80"
              :color="notice.color"
              variant="subtle"
              :icon="notice.icon"
              :title="notice.title"
              :description="notice.description"
              :actions="alertActions(notice.color, notice.actions ?? [])"
              v-bind="notice.attrs"
            />
          </template>
        </NuxtPopover>
      </div>
      <p
        v-if="card.ifood_schedule_label"
        class="op-micro text-muted-foreground"
        data-ifood-schedule
      >
        {{ card.ifood_schedule_label }}
      </p>
      <NuxtBadge
        v-if="card.ifood_pickup_code"
        class="self-start"
        color="neutral"
        icon="i-lucide-key-round"
        :label="`Código de retirada · ${card.ifood_pickup_code}`"
        data-ifood-pickup-code
      />

      <!-- erro da ação: a razão do servidor, à vista até dispensar -->
      <NuxtAlert
        v-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        :title="error"
        :close="action({}, { 'aria-label': 'Dispensar aviso' })"
        data-card-error
        @update:open="emit('dismiss-error')"
      />

      <div class="flex-1" />

      <!-- pagamento e total, logo acima do gesto -->
      <div v-if="!handoff" class="flex items-baseline justify-between gap-2">
        <NuxtBadge
          v-if="card.payment_method_label"
          :color="paymentColor"
          :icon="paymentIcon.replace('lucide:', 'i-lucide-')"
          :label="card.payment_method_label"
          data-card-payment
        />
        <span class="shrink-0 op-title tnum">{{ card.total_display }}</span>
      </div>
    </div>

    <!-- O próximo gesto ocupa o footer oficial do Card, como na receita do
         Kitchen Sink. A divisão e o padding passam a pertencer ao NuxtCard. -->
    <template #footer>
      <!-- @container: o rodapé decide pela própria largura (card largo, coluna estreita,
           grade da Saída), não pelo breakpoint da página. -->
      <OrderCardActions
        :card="card"
        :busy="busy"
        :handoff="handoff"
        :primary="primary"
        :secondary="secondary"
        :primary-label="primaryLabel"
        :waiting-for="waitingFor"
        :can-open="canOpen"
        :selecting="selecting"
        :selected="selected"
        @action="(ref_) => emit('action', ref_)"
        @toggle-assign="emit('toggle-assign')"
        @toggle-select="emit('toggle-select')"
        @select-mode="emit('select-mode')"
        @volumes="(count) => emit('volumes', count)"
        @station-recall="(pk) => emit('station-recall', pk)"
      />
    </template>
  </NuxtCard>
</template>
