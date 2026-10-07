<script setup lang="ts">
// Um cartão de pedido no quadro, no desenho da prévia v4 (UX-KIT-V2,
// `docs/plans/suite-ux-v2/fontes/v4/gestor-colunas4.html` e `gestor-fila4.html`):
//
//   código grande + nome                         selo do estado · tempo
//   etiquetas cheias (Retirada · 3 itens …)
//   itens
//   barra de progresso por estação + a frase dela ("2 de 3 prontos · falta Café")
//   "Pronto · automático · desfazer" (o sistema fez)
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
  cardClock,
  cardSeal,
  channelLabel,
  onRoadLine,
  packLabel,
  primaryVerb,
  splitRef,
  stationProgress,
  undoLine,
  type AffordanceRef,
  type Tone,
} from "~/presentation/board";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { danfeLine } from "~/presentation/danfe";
import { kitchenChips } from "~/presentation/kitchen";
import OrderCardMenu from "./OrderCardMenu.vue";

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
const nowMs = useNowTick(() => props.card.server_now_iso);
const clock = computed(() => cardClock(props.card, nowMs.value));
const seal = computed(() => cardSeal(props.card, { next: props.next }));

// A Cozinha neste pedido: a barra por estação, o "Pronto" da estação sem tela e o
// "Voltar para…" no menu do pedido.
const progress = computed(() => stationProgress(props.card.kitchen));
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
const waitingFor = computed(() =>
  !primary.value && progress.value && !progress.value.done
    ? progress.value.missingNames
    : "",
);

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
// A janela de desfazer usa o progresso oficial do Nuxt UI.
const handoffWindow = ref(0);
watch(
  () => handoff.value?.secondsLeft ?? 0,
  (left) => {
    if (left > handoffWindow.value) handoffWindow.value = left;
    if (!left) handoffWindow.value = 0;
  },
  { immediate: true },
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

function segmentColor(state: string): "success" | "error" | "info" | "neutral" {
  if (state === "done") return "success";
  if (state === "alert") return "error";
  if (state === "working") return "info";
  return "neutral";
}
function segmentValue(state: string): number {
  if (state === "done") return 100;
  if (state === "working" || state === "alert") return 50;
  return 0;
}
/** Um aviso do pedido, compacto: a pílula no cartão e o Alert inteiro no Popover. */
interface CardNotice {
  key: string;
  color: "error" | "warning" | "info" | "neutral";
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
  if (card.advance_block_reason)
    out.push({
      key: "block",
      color: seal.value.tone === "error" ? "error" : "neutral",
      icon: "i-lucide-lock",
      label: "Por que espera",
      title: card.advance_block_reason,
      attrs: { "data-advance-block": "" },
    });
  for (const chip of attentionStations.value)
    out.push({
      key: `station-${chip.ref}`,
      color: chip.tone === "alert" ? "error" : "neutral",
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
                color: chip.tone === "alert" ? "error" : "neutral",
                variant: "outline",
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
            color: "warning",
            variant: "outline",
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
            color: "warning",
            variant: "outline",
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
            color: "warning",
            variant: "outline",
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
function nuxtIcon(icon: string): string {
  return icon.startsWith("lucide:")
    ? `i-lucide-${icon.slice("lucide:".length)}`
    : icon;
}
</script>

<template>
  <NuxtCard
    as="article"
    class="grid h-full grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr_auto]"
    :variant="selected ? 'subtle' : 'outline'"
    :data-card-state="handoff ? 'handoff' : seal.tone"
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
              variant="subtle"
              :label="seal.label"
              data-card-seal
            />
            <NuxtBadge
              v-if="clock.countdown"
              :color="
                clock.tone === 'late'
                  ? 'warning'
                  : clock.tone === 'warning'
                    ? 'warning'
                    : 'neutral'
              "
              variant="subtle"
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
                  ? 'warning'
                  : clock.tone === 'warning'
                    ? 'warning'
                    : 'neutral'
              "
              variant="subtle"
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
      <!-- Entregue, na janela do desfazer: o cartão fica no lugar, com o anel do tempo. -->
      <template v-if="handoff">
        <NuxtBadge
          class="self-start"
          color="success"
          variant="subtle"
          icon="i-lucide-check"
          :label="handoff.label"
          :data-undo="handoff.kind"
        />
        <NuxtProgress
          :model-value="handoff.secondsLeft"
          :max="handoffWindow || 1"
          color="success"
          size="sm"
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
            variant="soft"
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
            variant="soft"
            icon="i-lucide-package"
            :label="pack"
            :data-card-pack="card.volumes ? 'volumes' : 'items'"
          />
          <NuxtBadge
            v-if="card.is_preorder"
            color="neutral"
            variant="soft"
            icon="i-lucide-calendar-clock"
            :label="`Agendado${card.commitment_date_display ? ` · ${card.commitment_date_display}` : ''}`"
            data-preorder-badge
          />
          <!-- fila de espera: o pedido não está parado, está esperando o lote -->
          <NuxtBadge
            v-if="card.waitlist_label"
            :color="
              card.waitlist_state === 'confirming' ? 'primary' : 'neutral'
            "
            variant="subtle"
            icon="i-lucide-hourglass"
            :label="card.waitlist_label"
            data-waitlist-badge
          />
          <NuxtBadge
            v-if="card.is_gift"
            color="neutral"
            variant="soft"
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
            variant="soft"
            icon="i-lucide-message-square"
            role="img"
            aria-label="Tem observação do cliente"
            data-customer-note-badge
          />
          <NuxtBadge
            v-if="card.assigned_operator"
            color="primary"
            variant="soft"
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

        <!-- a Cozinha neste pedido: um traço por estação e a frase -->
        <div
          v-if="progress"
          class="flex flex-col gap-1"
          data-kitchen-progress
          :data-kitchen="progress.done ? undefined : ''"
        >
          <div
            class="grid gap-2"
            role="list"
            aria-label="Estações deste pedido"
          >
            <NuxtProgress
              v-for="seg in progress.segments"
              :key="seg.ref"
              :model-value="segmentValue(seg.state)"
              :color="segmentColor(seg.state)"
              size="sm"
              role="listitem"
              :title="seg.title"
              :aria-label="seg.title"
              data-kitchen-station
            />
          </div>
          <p v-if="progress.done" class="op-micro text-muted-foreground">
            {{ progress.summary }}
          </p>
          <p v-else class="op-label">
            <span class="text-muted-foreground">{{ progress.summary }} · </span
            ><b class="font-semibold text-info" data-kitchen-missing>{{
              progress.missing
            }}</b>
          </p>
          <!-- a estação que pede alguém vira pílula de aviso (notices) -->
        </div>

        <!-- o sistema fez: "Pronto · automático · desfazer" -->
        <div
          v-if="undo && undo.kind === 'auto_ready'"
          class="flex flex-wrap items-center gap-2"
          :data-undo="undo.kind"
        >
          <NuxtBadge
            color="neutral"
            variant="soft"
            icon="i-lucide-sparkles"
            :label="undo.label"
          />
          <NuxtButton
            v-if="undo.canUndo"
            label="Desfazer"
            color="neutral"
            variant="link"
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
            size="xs"
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
            size="xs"
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
              :actions="notice.actions"
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
        variant="subtle"
        icon="i-lucide-key-round"
        :label="`Código de retirada · ${card.ifood_pickup_code}`"
        data-ifood-pickup-code
      />

      <!-- aguardando produção -->
      <div
        v-if="card.awaiting_work_orders.length && !handoff"
        class="flex flex-col gap-1.5"
      >
        <div
          v-for="wo in card.awaiting_work_orders"
          :key="wo.ref"
          class="flex flex-col gap-1"
          data-work-order-progress
        >
          <p class="flex items-center gap-1.5 op-micro text-muted-foreground">
            <Icon name="lucide:factory" class="size-3 shrink-0" />
            <span class="min-w-0 flex-1 truncate"
              >{{ wo.output_sku }} · {{ wo.status_label }}</span
            >
            <span class="shrink-0 tnum">{{ wo.progress_pct }}%</span>
          </p>
          <NuxtProgress
            :model-value="wo.progress_pct"
            :max="100"
            color="primary"
            size="sm"
            :get-value-label="
              () => `${wo.output_sku}, ${wo.status_label}, ${wo.progress_pct}%`
            "
          />
        </div>
      </div>

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
          variant="subtle"
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
      <div class="@container flex items-end gap-2">
        <NuxtButton
          v-if="handoff && handoff.canUndo"
          block
          class="min-w-0 flex-1"
          color="success"
          variant="outline"
          icon="i-lucide-undo-2"
          :label="`Desfazer ${handoff.countdown}`"
          :disabled="busy"
          :loading="busy"
          data-undo-button
          @click="emit('action', handoff.action)"
        />
        <div
          v-else-if="!handoff"
          class="grid min-w-0 flex-1 gap-2"
          :class="
            primary && secondary.length === 1
              ? '@[22rem]:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]'
              : secondary.length > 1
                ? 'grid-cols-2'
                : 'grid-cols-1'
          "
        >
          <NuxtButton
            v-for="aff in secondary"
            :key="aff.ref"
            block
            class="h-full min-w-0"
            :disabled="busy"
            :loading="busy"
            :color="aff.priority === 'danger' ? 'error' : 'neutral'"
            variant="outline"
            :icon="nuxtIcon(aff.icon)"
            :title="aff.reason || undefined"
            @click="emit('action', aff.ref)"
          >
            <span class="min-w-0 text-center leading-tight">{{
              aff.label
            }}</span>
          </NuxtButton>
          <NuxtButton
            v-if="primary"
            block
            class="min-w-0"
            :class="secondary.length > 1 ? 'col-span-2' : undefined"
            :disabled="busy || primary.disabled"
            :loading="busy"
            :title="
              primary.reason ||
              (primaryLabel !== primary.label ? primary.label : undefined)
            "
            :color="primary.disabled ? 'neutral' : 'primary'"
            :variant="primary.disabled ? 'outline' : 'solid'"
            :icon="primary.disabled ? 'i-lucide-lock' : nuxtIcon(primary.icon)"
            data-card-primary
            @click="!primary.disabled && emit('action', primary.ref)"
          >
            <span class="min-w-0 text-center leading-tight">{{
              primaryLabel
            }}</span>
          </NuxtButton>
          <NuxtAlert
            v-else-if="waitingFor"
            class="min-w-0"
            color="neutral"
            variant="soft"
            icon="i-lucide-chef-hat"
            :title="`Aguardando ${waitingFor}`"
            data-card-waiting
          />
        </div>
        <div v-else class="flex-1" />

        <!-- ⋯ do cartão: atender, seleção em lote, voltar à estação, abrir. -->
        <OrderCardMenu
          class="shrink-0"
          :card="card"
          :busy="busy"
          :can-open="canOpen"
          :selecting="selecting"
          :selected="selected"
          @toggle-assign="emit('toggle-assign')"
          @toggle-select="emit('toggle-select')"
          @select-mode="emit('select-mode')"
          @volumes="(count) => emit('volumes', count)"
          @station-recall="(pk) => emit('station-recall', pk)"
        />
      </div>
    </template>
  </NuxtCard>
</template>
