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
import type { OrderCardProjection } from "~/types/orders";
import {
  cardAffordances,
  cardClock,
  cardSeal,
  channelLabel,
  onRoadLine,
  packLabel,
  primaryVerb,
  sealClass,
  splitRef,
  stationProgress,
  timerChip,
  toneBadge,
  undoLine,
  type AffordanceRef,
  type Tone,
} from "~/presentation/board";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { danfeLine } from "~/presentation/danfe";
import { kitchenChips, kitchenRecallOptions } from "~/presentation/kitchen";

// ``touch``: o posto de saída (Gestor na "Visão: Saída", tablet do passe): todo alvo do
// cartão sobe para 48 px. ``canOpen``: falso para quem só expede; o detalhe do pedido e
// o "Atender" são de quem gerencia. ``selecting``: o modo de seleção em lote está
// ligado e o cartão mostra a caixa. ``next``: o primeiro da Saída a sair (selo
// "Próximo" e moldura). ``fill``: o cartão ocupa a célula inteira da grade da Saída.
const props = withDefaults(
  defineProps<{
    card: OrderCardProjection;
    busy?: boolean;
    error?: string;
    selected?: boolean;
    selecting?: boolean;
    next?: boolean;
    fill?: boolean;
    negotiationOnly?: boolean;
    danfePrinting?: boolean;
    touch?: boolean;
    canOpen?: boolean;
  }>(),
  { canOpen: true },
);
const emit = defineEmits<{
  (e: "action", ref: AffordanceRef): void;
  (e: "dismiss-error" | "toggle-select" | "toggle-assign" | "print-danfe" | "select-mode"): void;
  (e: "station-ready", stationRef: string): void;
  (e: "station-recall" | "volumes", value: number): void;
}>();

const code = computed(() => splitRef(props.card.ref));
const pack = computed(() => packLabel(props.card));
// "Volumes" no ⋯: quem embalou diz quantas sacolas ou caixas saem (0 apaga). Só aparece
// quando o servidor oferece o gesto (ação "volumes"), com a mesma régua das outras.
const volumesAction = computed(() => props.card.actions.find((action) => action.ref === "volumes") ?? null);
const volumesEditing = ref(false);
const volumesDraft = ref(0);
function openVolumes() {
  volumesDraft.value = props.card.volumes || Math.max(1, Math.min(props.card.items_count || 1, 99));
  volumesEditing.value = true;
}
function stepVolumes(delta: number) {
  volumesDraft.value = Math.max(0, Math.min(99, volumesDraft.value + delta));
}
function saveVolumes() {
  menuOpen.value = false;
  volumesEditing.value = false;
  emit("volumes", volumesDraft.value);
}
const nowMs = useNowTick(() => props.card.server_now_iso);
const clock = computed(() => cardClock(props.card, nowMs.value));
const seal = computed(() => cardSeal(props.card, { next: props.next }));
const target = computed(() => props.touch ? "min-h-action min-w-action" : "min-h-control min-w-control");

// A Cozinha neste pedido: a barra por estação, o "Pronto" da estação sem tela e o
// "Voltar para…" no menu do pedido.
const progress = computed(() => props.negotiationOnly ? null : stationProgress(props.card.kitchen));
const attentionStations = computed(() => props.negotiationOnly
  ? []
  : kitchenChips(props.card.kitchen).filter((chip) => chip.canMarkReady || chip.tone === "alert" || chip.cancelledNote));
const recallOptions = computed(() => props.negotiationOnly ? [] : kitchenRecallOptions(props.card.kitchen));

const onRoad = computed(() => onRoadLine(props.card));
const affordances = computed(() => props.negotiationOnly ? [] : cardAffordances(props.card));
const primary = computed(() => affordances.value.find((a) => a.priority === "primary" || a.disabled) ?? null);
const secondary = computed(() => affordances.value.filter((a) => a !== primary.value));
const primaryLabel = computed(() => primary.value ? primaryVerb(props.card, primary.value) : "");
// A estação ainda trabalha e o "Marcar pronto" mora no menu: o lugar do botão diz o que
// se espera ("Aguardando Café"), sem ser botão.
const waitingFor = computed(() => !primary.value && progress.value && !progress.value.done ? progress.value.missingNames : "");

// Pagamento: o tom vem da projeção. Dinheiro não é "pago" nem "devendo".
const paymentAttention = computed(() => Boolean(props.card.payment_method_label) && (props.card.payment_tone === "warning" || props.card.payment_tone === "danger"));
const paymentClass = computed(() => {
  const tone = props.card.payment_tone as Tone;
  return tone === "warning" || tone === "danger" ? toneBadge(tone).split(" ").filter((c) => c.startsWith("text-")).join(" ") : "text-muted-foreground";
});
const paymentIcon = computed(() => {
  if (!props.card.payment_method) return "lucide:circle-help";
  return ({ warning: "lucide:hourglass", danger: "lucide:alert-triangle", success: "lucide:check", neutral: "lucide:banknote" }[props.card.payment_tone] || "lucide:banknote");
});

const danfe = computed(() => props.negotiationOnly ? null : danfeLine(props.card));
// "O sistema fez · desfazer": o pronto que veio da Cozinha, ou a saída tocada ainda na
// janela. O fato fica à vista; o gesto só enquanto o prazo corre.
const undo = computed(() => props.negotiationOnly ? null : undoLine(props.card, nowMs.value));
const handoff = computed(() => undo.value?.kind === "handoff" ? undo.value : null);
// O anel do desfazer: a fração que falta da janela (a maior contagem vista é o todo).
const handoffWindow = ref(0);
watch(() => handoff.value?.secondsLeft ?? 0, (left) => {
  if (left > handoffWindow.value) handoffWindow.value = left;
  if (!left) handoffWindow.value = 0;
}, { immediate: true });
const ringStyle = computed(() => {
  const total = handoffWindow.value || 1;
  const pct = Math.round(((handoff.value?.secondsLeft ?? 0) / total) * 100);
  return { background: `conic-gradient(var(--success) 0 ${pct}%, color-mix(in oklab, var(--success) 18%, transparent) ${pct}% 100%)` };
});

// ⋯ do cartão: atender, seleção em lote, voltar para a estação, abrir o pedido.
const menuOpen = ref(false);
watch(menuOpen, (open) => { if (!open) volumesEditing.value = false; });
function pick(fn: () => void) {
  menuOpen.value = false;
  fn();
}

// Toque longo liga a seleção em lote (como no celular de qualquer lista).
let pressTimer: ReturnType<typeof setTimeout> | null = null;
function pressStart(event: PointerEvent) {
  if (props.negotiationOnly || props.selecting || event.button > 0) return;
  if ((event.target as HTMLElement).closest("button, a, input, textarea")) return;
  pressTimer = setTimeout(() => { pressTimer = null; emit("select-mode"); }, 550);
}
function pressEnd() {
  if (pressTimer) clearTimeout(pressTimer);
  pressTimer = null;
}
onBeforeUnmount(pressEnd);

const CHIP = "inline-flex items-center gap-1.5 rounded-lg bg-secondary px-2.5 font-semibold text-secondary-foreground";
const chipSize = computed(() => props.touch ? "h-9 op-body" : "h-8 text-sm");
function segClass(state: string): string {
  if (state === "done") return "bg-success";
  if (state === "alert") return "bg-destructive";
  if (state === "working") return "seg-wip";
  return "bg-foreground/15";
}
function secondaryClass(priority: string): string {
  if (priority === "danger") return "border-border text-muted-foreground hover:bg-destructive/10 hover:text-destructive";
  return "border-border hover:bg-accent";
}
</script>

<template>
  <article
    class="relative flex flex-col gap-2 rounded-xl border bg-card p-3.5 transition"
    :class="[
      fill ? 'h-full' : '',
      handoff ? 'border-success/50 bg-success/8' : '',
      !handoff && seal.tone === 'destructive' ? 'border-destructive/50' : '',
      !handoff && next && !selected ? 'border-2 border-primary shadow-[0_0_0_4px_color-mix(in_oklab,var(--primary)_14%,transparent)]' : '',
      !handoff && card.can_confirm && !next && !selected ? 'border-primary/70' : '',
      selected ? 'border-primary ring-1 ring-primary' : '',
      !handoff && seal.tone !== 'destructive' && !next && !card.can_confirm && !selected ? 'border-border hover:border-primary/40' : '',
    ]"
    :data-card-state="handoff ? 'handoff' : seal.tone"
    @pointerdown="pressStart"
    @pointerup="pressEnd"
    @pointerleave="pressEnd"
    @pointercancel="pressEnd"
  >
    <!-- Homologação do iFood: o aviso vem ANTES do código, com a frase inteira. -->
    <p
      v-if="card.test_order_notice"
      class="rounded-md border border-warning/50 bg-warning/15 p-2 text-xs font-medium"
      role="status"
      data-test-order-notice
    >
      <span class="mb-0.5 flex items-center gap-1.5 font-bold uppercase tracking-wide">
        <Icon name="lucide:flask-conical" class="size-3.5 shrink-0" />
        {{ card.test_order_label }}
      </span>
      {{ card.test_order_notice }}
    </p>

    <!-- código grande + nome à esquerda; selo do estado e o tempo no canto -->
    <div class="flex items-start gap-2" :class="handoff ? 'opacity-55' : ''">
      <button
        v-if="selecting && !negotiationOnly"
        type="button"
        class="-mt-1 -ml-2 grid shrink-0 place-items-center rounded transition hover:bg-accent"
        :class="touch ? 'size-action' : 'size-control'"
        :aria-label="selected ? 'Desmarcar pedido' : 'Selecionar pedido'"
        :aria-pressed="selected"
        data-card-select
        @click="emit('toggle-select')"
      >
        <span class="grid size-5 place-items-center rounded border" :class="selected ? 'border-primary bg-primary text-primary-foreground' : 'border-input bg-card hover:border-primary'">
          <Icon v-if="selected" name="lucide:check" class="size-3.5" />
        </span>
      </button>
      <div class="min-w-0 flex-1">
        <NuxtLink
          v-if="canOpen && !negotiationOnly"
          :to="`/${card.ref}`"
          class="group inline-flex min-w-control flex-col justify-start"
          :class="touch ? 'min-h-action' : 'min-h-control'"
          :aria-label="`Abrir pedido ${card.ref}`"
        >
          <span
            class="block op-code break-all group-hover:underline"
            :class="handoff ? 'line-through decoration-success/60' : ''"
          >{{ code.code }}</span>
        </NuxtLink>
        <div v-else class="flex flex-col justify-start" :class="touch ? 'min-h-action' : 'min-h-control'" data-card-code>
          <span class="block op-code break-all" :class="handoff ? 'line-through decoration-success/60' : ''">{{ code.code }}</span>
        </div>
        <span
          v-if="card.channel_display_id"
          class="block break-all text-xs font-medium tnum text-muted-foreground"
          data-channel-display-id
        >iFood #{{ card.channel_display_id }}</span>
        <p class="truncate op-title" :title="card.customer_name || 'Sem cliente'">
          <span>{{ card.customer_name || "Sem cliente" }}</span><span class="font-normal text-muted-foreground"> · {{ channelLabel(card.channel_ref) }}</span>
        </p>
      </div>
      <div v-if="!handoff" class="flex shrink-0 flex-col items-end gap-1 pt-1">
        <span :class="[sealClass(seal.tone), 'inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-xs font-semibold whitespace-nowrap']" data-card-seal>
          <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
          {{ seal.label }}
        </span>
        <span
          v-if="clock.countdown"
          class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 op-micro font-semibold tnum"
          :class="timerChip(clock.tone)"
          :title="card.confirmation_action === 'cancel' ? 'Cancelado automaticamente se vencer' : 'Confirmado automaticamente se vencer'"
          role="timer"
          aria-live="off"
        >{{ clock.text }}</span>
        <span
          v-else
          class="op-micro tnum"
          :class="clock.tone === 'late' ? 'font-semibold text-destructive' : clock.tone === 'warning' ? 'font-semibold text-warning' : 'text-muted-foreground'"
          data-card-clock
        ><template v-if="seal.label !== card.status_label && !card.ready_at_iso && !card.dispatched_at_iso">{{ card.status_label }} · </template>{{ clock.text }}</span>
      </div>
      <span v-else class="shrink-0 pt-1 op-micro text-muted-foreground">{{ card.fulfillment_label }}<template v-if="pack"> · {{ pack }}</template></span>
    </div>

    <!-- Entregue, na janela do desfazer: o cartão fica no lugar, com o anel do tempo. -->
    <template v-if="handoff">
      <div class="mt-1 flex items-center gap-3" :data-undo="handoff.kind">
        <span class="grid size-12 shrink-0 place-items-center rounded-full" :style="ringStyle" aria-hidden="true">
          <span class="grid size-9 place-items-center rounded-full bg-card text-success"><Icon name="lucide:check" class="size-5" /></span>
        </span>
        <p class="op-action">{{ handoff.label }}</p>
      </div>
      <p class="op-micro leading-snug text-muted-foreground" data-undo-detail>{{ handoff.detail }}<span v-if="handoff.alreadyOut" data-undo-already-out> · {{ handoff.alreadyOut }}</span></p>
    </template>

    <template v-else>
      <!-- etiquetas cheias: os fatos do pedido, com ícone (um estilo só) -->
      <div class="flex flex-wrap gap-2" data-card-tags>
        <span :class="[CHIP, chipSize]">
          <Icon :name="card.fulfillment_type === 'delivery' ? 'lucide:bike' : 'lucide:store'" class="size-4" />{{ card.fulfillment_label }}
        </span>
        <span v-if="pack" :class="[CHIP, chipSize, 'tnum']" :data-card-pack="card.volumes ? 'volumes' : 'items'">
          <Icon name="lucide:package" class="size-4" />{{ pack }}
        </span>
        <span v-if="card.is_preorder" :class="[CHIP, chipSize]" data-preorder-badge>
          <Icon name="lucide:calendar-clock" class="size-4" />Agendado{{ card.commitment_date_display ? ` · ${card.commitment_date_display}` : "" }}
        </span>
        <!-- fila de espera: o pedido não está parado, está esperando o lote -->
        <span
          v-if="card.waitlist_label"
          :class="[CHIP, chipSize, card.waitlist_state === 'confirming' ? 'bg-primary/12 text-primary' : '']"
          data-waitlist-badge
        >
          <Icon name="lucide:hourglass" class="size-4" />{{ card.waitlist_label }}
        </span>
        <span
          v-if="card.is_gift"
          :class="[CHIP, chipSize]"
          role="img"
          :aria-label="card.gift_has_recipient ? 'Presente com destinatário' : 'Embalar para presente'"
          data-gift-badge
        >
          <Icon name="lucide:gift" class="size-4" />
        </span>
        <span
          v-if="card.has_customer_note"
          :class="[CHIP, chipSize]"
          role="img"
          aria-label="Tem observação do cliente"
          data-customer-note-badge
        >
          <Icon name="lucide:message-square" class="size-4" />
        </span>
        <!-- Saída larga (v4): o pagamento só vira etiqueta quando pede atenção -->
        <span v-if="fill && paymentAttention" :class="[CHIP, chipSize, 'bg-warning/12 text-warning']" data-card-payment-tag>
          <Icon :name="paymentIcon" class="size-4" />{{ card.payment_method_label }}
        </span>
        <span v-if="card.assigned_operator" :class="[CHIP, chipSize, 'bg-primary/12 text-primary']" data-card-assigned>
          <Icon name="lucide:user-check" class="size-4" /><span class="max-w-24 truncate">{{ card.assigned_operator }}</span>
        </span>
      </div>

      <p class="op-body text-foreground/85" :class="fill ? 'line-clamp-1' : 'line-clamp-2'" :title="card.items_summary">{{ card.items_summary }}</p>

      <p v-if="card.courier_status_label" class="flex items-center gap-1.5 truncate op-micro text-muted-foreground">
        <Icon name="lucide:bike" class="size-3.5 shrink-0" /> {{ card.courier_status_label }}
      </p>
      <!-- para onde vai -->
      <p v-if="card.delivery_address" class="flex items-start gap-1.5 op-micro text-muted-foreground" data-card-address>
        <Icon name="lucide:map-pin" class="mt-0.5 size-3.5 shrink-0" />
        <span class="line-clamp-2">{{ card.delivery_address }}</span>
      </p>
      <!-- troco da entrega: o que o cliente disse, o que saiu da gaveta, o que voltou -->
      <p v-if="card.change_label" class="flex items-center gap-1.5 op-micro text-muted-foreground" :class="{ 'font-medium text-foreground': card.change_back_pending }" data-change-label>
        <Icon name="lucide:coins" class="size-3.5 shrink-0" />
        <span class="truncate">{{ card.change_label }}</span>
      </p>
      <!-- a maquininha na rua: o único sinal dela no quadro é esta linha -->
      <p v-if="onRoad" class="flex items-center gap-1.5 op-micro font-medium" data-equipment-label>
        <Icon :name="card.equipment_label ? 'lucide:smartphone-nfc' : 'lucide:bike'" class="size-3.5 shrink-0" />
        <span class="truncate">{{ onRoad }}</span>
      </p>

      <!-- a Cozinha neste pedido: um traço por estação e a frase -->
      <div v-if="progress" class="flex flex-col gap-1" data-kitchen-progress :data-kitchen="progress.done ? undefined : ''">
        <div class="flex gap-[3px]" role="list" aria-label="Estações deste pedido">
          <span
            v-for="seg in progress.segments"
            :key="seg.ref"
            role="listitem"
            class="h-1.5 flex-1 rounded-full"
            :class="segClass(seg.state)"
            :title="seg.title"
            :aria-label="seg.title"
            data-kitchen-station
          />
        </div>
        <p v-if="progress.done" class="op-micro text-muted-foreground">{{ progress.summary }}</p>
        <p v-else class="op-label">
          <span class="text-muted-foreground">{{ progress.summary }} · </span><b class="font-semibold text-info" data-kitchen-missing>{{ progress.missing }}</b>
        </p>
        <!-- só a estação que pede alguém: papel perdido, item cancelado, o Pronto da estação sem tela -->
        <div
          v-for="chip in attentionStations"
          :key="chip.ref"
          class="flex items-center gap-2 rounded-md px-2 py-1"
          :class="chip.tone === 'alert' ? 'bg-destructive/10 text-destructive dark:text-red-300' : 'bg-secondary'"
          data-kitchen-attention
        >
          <Icon :name="chip.icon" class="size-3.5 shrink-0" />
          <span class="min-w-0 flex-1 truncate op-micro">
            <b class="font-semibold text-foreground">{{ chip.station }}</b> · {{ chip.detail }}<span v-if="chip.cancelledNote" class="font-semibold text-destructive dark:text-red-300"> · {{ chip.cancelledNote }}</span>
          </span>
          <button
            v-if="chip.canMarkReady"
            type="button"
            class="inline-flex shrink-0 items-center gap-1 rounded-md border border-transparent bg-foreground px-2.5 text-sm font-semibold text-background transition hover:bg-foreground/90 active:scale-[0.98] disabled:opacity-60"
            :class="target"
            :disabled="busy"
            :aria-label="`Pronto de ${chip.station} no pedido ${code.code}`"
            data-kitchen-ready
            @click="emit('station-ready', chip.ref)"
          >
            <Icon name="lucide:check" class="size-3.5" />
            Pronto de {{ chip.station }}
          </button>
        </div>
      </div>

      <!-- o sistema fez: "Pronto · automático · desfazer" -->
      <div v-if="undo && undo.kind === 'auto_ready'" class="flex flex-wrap items-center gap-x-2 gap-y-1" :data-undo="undo.kind">
        <span class="inline-flex h-6 items-center gap-1.5 rounded-full bg-muted px-2 text-xs font-semibold whitespace-nowrap text-muted-foreground">
          <Icon name="lucide:sparkles" class="size-3.5" />
          {{ undo.label }}<template v-if="undo.canUndo"> ·
            <button
              type="button"
              class="font-semibold text-foreground underline underline-offset-[3px] disabled:opacity-60"
              :disabled="busy"
              data-undo-button
              @click="emit('action', undo.action)"
            >desfazer</button></template>
        </span>
        <span class="op-micro text-muted-foreground" data-undo-detail>{{ undo.detail }}</span>
        <span v-if="undo.alreadyOut" class="op-micro text-muted-foreground" data-undo-already-out>· {{ undo.alreadyOut }}</span>
      </div>

      <div v-if="danfe" class="space-y-0.5 op-micro" data-danfe :data-danfe-attention="danfe.attention || undefined">
        <div class="flex items-center gap-1.5" :class="danfe.attention ? 'font-medium text-warning' : 'text-muted-foreground'">
          <Icon :name="danfe.attention ? 'lucide:triangle-alert' : card.danfe_printed ? 'lucide:receipt-text' : 'lucide:receipt'" class="size-3.5 shrink-0" />
          <span class="truncate" data-danfe-status>{{ danfe.status }}</span>
          <button
            type="button"
            class="ml-auto inline-flex min-h-control shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 font-medium text-foreground transition hover:bg-accent disabled:opacity-60"
            :disabled="danfePrinting || danfe.sending"
            data-danfe-print
            @click="emit('print-danfe')"
          >
            <Icon name="lucide:printer" class="size-3.5" />
            {{ danfePrinting || danfe.sending ? "Imprimindo…" : danfe.action }}
          </button>
        </div>
        <p v-if="danfe.problem" class="text-warning" data-danfe-problem>{{ danfe.problem }}</p>
      </div>

      <NuxtLink
        v-if="!negotiationOnly && card.fiscal_status === 'failed'"
        :to="`/${card.ref}`"
        class="min-h-control flex items-center gap-1.5 rounded-md border border-warning/40 bg-warning/10 p-2 text-sm font-medium text-warning"
        data-fiscal-failed
      >
        <Icon name="lucide:triangle-alert" class="size-4 shrink-0" />
        NFC-e não autorizada · abrir e reprocessar
      </NuxtLink>
    </template>

    <NuxtLink v-if="card.ifood_negotiations?.length" :to="`/${card.ref}#ifood-negotiations`" class="min-h-control block rounded-md border border-warning/40 bg-warning/10 p-2 text-sm" data-ifood-negotiation-link>
      Negociação iFood · abrir solicitação e conferir prazo
    </NuxtLink>
    <p v-if="card.ifood_cancellation_notice" class="rounded-md border border-warning/40 bg-warning/10 p-2 text-xs" role="status" data-ifood-cancellation>{{ card.ifood_cancellation_notice }}</p>
    <p v-if="card.ifood_remote_ahead_label" class="rounded-md border border-primary/30 bg-primary/10 px-2.5 py-1.5 text-xs font-medium" role="status" data-ifood-remote-ahead>{{ card.ifood_remote_ahead_label }}</p>
    <p v-if="card.ifood_schedule_label" class="op-micro text-muted-foreground" data-ifood-schedule>{{ card.ifood_schedule_label }}</p>
    <p v-if="card.ifood_pickup_code" class="flex items-baseline gap-2 rounded-md bg-muted px-2.5 py-1.5" data-ifood-pickup-code>
      <span class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Código de retirada</span>
      <span class="ml-auto text-base font-bold tnum">{{ card.ifood_pickup_code }}</span>
    </p>

    <!-- aguardando produção -->
    <div v-if="card.awaiting_work_orders.length && !handoff" class="flex flex-col gap-1">
      <div v-for="wo in card.awaiting_work_orders" :key="wo.ref" class="flex items-center gap-1.5 rounded-md bg-muted/60 px-2 py-1 op-micro text-muted-foreground">
        <Icon name="lucide:factory" class="size-3 shrink-0" />
        <span class="truncate">{{ wo.output_sku }} · {{ wo.status_label }}</span>
        <span class="ml-auto tnum">{{ wo.progress_pct }}%</span>
      </div>
    </div>

    <!-- bloqueio antes do gesto (v4): o motivo escrito no cartão, com o cadeado. Quando
         a frase não trava o gesto do momento (ex.: o pedido novo ainda sem próxima
         etapa), ela fica à vista em texto calmo, como antes. -->
    <div
      v-if="!negotiationOnly && card.advance_block_reason && !handoff && seal.tone === 'destructive'"
      class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/12 px-2.5 py-1.5"
    >
      <Icon name="lucide:lock" class="mt-0.5 size-4 shrink-0 text-destructive" />
      <p class="op-label leading-snug" data-advance-block>{{ card.advance_block_reason }}</p>
    </div>
    <p v-else-if="!negotiationOnly && card.advance_block_reason && !handoff" class="op-micro text-muted-foreground" data-advance-block>
      {{ card.advance_block_reason }}
    </p>

    <!-- erro da ação: a razão do servidor, à vista até dispensar -->
    <div
      v-if="error"
      class="flex items-start gap-1.5 rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1.5 text-xs text-destructive dark:text-orange-300"
      role="alert"
    >
      <Icon name="lucide:alert-triangle" class="mt-px size-3.5 shrink-0" />
      <span class="min-w-0 flex-1">{{ error }}</span>
      <button type="button" class="grid size-control shrink-0 place-items-center rounded transition hover:bg-destructive/20" aria-label="Dispensar aviso" @click="emit('dismiss-error')">
        <Icon name="lucide:x" class="size-3.5" />
      </button>
    </div>

    <div v-if="!negotiationOnly" class="flex-1" />

    <!-- pagamento e total, logo acima do gesto -->
    <div v-if="!negotiationOnly && !handoff && !fill" class="flex items-baseline justify-between gap-2">
      <span class="inline-flex min-w-0 items-center gap-1.5 op-micro" :class="paymentClass" data-card-payment>
        <Icon v-if="card.payment_method_label" :name="paymentIcon" class="size-3.5 shrink-0" />
        <span class="truncate">{{ card.payment_method_label }}</span>
      </span>
      <span class="shrink-0 op-title tnum">{{ card.total_display }}</span>
    </div>

    <!-- o gesto: um botão largo com o verbo e o nome; o resto no ⋯ -->
    <div v-if="!negotiationOnly" class="flex items-stretch gap-2">
      <button
        v-if="handoff && handoff.canUndo"
        type="button"
        class="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-success/50 bg-card op-action transition hover:bg-accent disabled:opacity-60"
        :class="touch ? 'h-14' : 'h-12'"
        :disabled="busy"
        data-undo-button
        @click="emit('action', handoff.action)"
      >
        <Icon name="lucide:undo-2" class="size-5" />
        Desfazer <span class="tnum text-muted-foreground">{{ handoff.countdown }}</span>
      </button>
      <template v-else-if="!handoff">
        <button
          v-for="aff in secondary"
          :key="aff.ref"
          type="button"
          :disabled="busy"
          class="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg border bg-card px-3 op-label font-semibold transition active:scale-[0.98] disabled:opacity-60"
          :class="[touch ? 'h-14' : 'h-12', secondaryClass(aff.priority)]"
          :title="aff.reason || undefined"
          @click="emit('action', aff.ref)"
        >
          <Icon :name="aff.icon" class="size-4" />
          {{ aff.label }}
        </button>
        <button
          v-if="primary"
          type="button"
          :disabled="busy || primary.disabled"
          :title="primary.reason || (primaryLabel !== primary.label ? primary.label : undefined)"
          class="inline-flex min-w-0 flex-1 items-center justify-center gap-2 rounded-lg px-3 font-semibold transition"
          :class="[
            touch ? 'h-14 op-action' : 'h-12 op-body font-semibold',
            primary.disabled
              ? 'cursor-default border-2 border-dashed border-border text-muted-foreground card-stripes'
              : 'bg-primary text-primary-foreground hover:bg-primary/90 active:scale-[0.98] disabled:opacity-60',
          ]"
          data-card-primary
          @click="!primary.disabled && emit('action', primary.ref)"
        >
          <Icon :name="primary.disabled ? 'lucide:lock' : primary.icon" class="size-5 shrink-0" />
          <span class="truncate">{{ primaryLabel }}</span>
        </button>
        <div
          v-else-if="waitingFor"
          class="inline-flex min-w-0 flex-1 items-center justify-center gap-2 rounded-lg bg-muted px-3 font-medium text-muted-foreground"
          :class="touch ? 'h-14 op-title font-medium' : 'h-12 op-body'"
          data-card-waiting
        >
          <Icon name="lucide:chef-hat" class="size-5 shrink-0" />
          <span class="text-center leading-tight">Aguardando {{ waitingFor }}</span>
        </div>
        <div v-else class="flex-1" />
      </template>
      <div v-else class="flex-1" />

      <!-- ⋯ do cartão: atender, seleção em lote, voltar à estação, abrir -->
      <div class="relative shrink-0">
        <button
          type="button"
          class="grid h-full place-items-center rounded-lg border border-border bg-card text-muted-foreground transition hover:bg-accent hover:text-foreground"
          :class="touch ? 'min-h-14 w-14' : 'min-h-12 w-12'"
          aria-haspopup="menu"
          :aria-expanded="menuOpen"
          :aria-label="`Mais ações do pedido ${code.code}`"
          data-card-menu
          @click="menuOpen = !menuOpen"
        >
          <Icon name="lucide:ellipsis" class="size-5" />
        </button>
        <div v-if="menuOpen" class="fixed inset-0 z-40" @click="menuOpen = false" />
        <div v-if="menuOpen" class="absolute right-0 bottom-full z-50 mb-1 w-60 overflow-hidden rounded-md border bg-popover py-1 text-popover-foreground shadow-lg" role="menu">
          <button
            v-if="canOpen"
            type="button"
            role="menuitem"
            class="flex w-full items-center gap-2.5 px-3 text-left op-body transition hover:bg-accent"
            :class="target"
            :aria-label="card.assigned_operator ? `Atendido por ${card.assigned_operator}. Toque para liberar` : 'Atender este pedido'"
            data-card-assign
            @click="pick(() => emit('toggle-assign'))"
          >
            <Icon :name="card.assigned_operator ? 'lucide:user-check' : 'lucide:user-plus'" class="size-4 shrink-0 text-muted-foreground" />
            {{ card.assigned_operator ? `Liberar (${card.assigned_operator} atende)` : "Atender este pedido" }}
          </button>
          <button
            type="button"
            role="menuitem"
            class="flex w-full items-center gap-2.5 px-3 text-left op-body transition hover:bg-accent"
            :class="target"
            data-card-select-mode
            @click="pick(() => (selecting ? emit('toggle-select') : emit('select-mode')))"
          >
            <Icon name="lucide:list-checks" class="size-4 shrink-0 text-muted-foreground" />
            {{ selecting ? (selected ? "Desmarcar este pedido" : "Marcar este pedido") : "Selecionar vários" }}
          </button>
          <div v-if="volumesEditing" class="flex flex-col gap-2 px-3 py-2" data-card-volumes-editor>
            <p class="op-label font-semibold">Quantos volumes saem?</p>
            <div class="flex items-center gap-2">
              <button type="button" class="grid place-items-center rounded-md border border-border transition hover:bg-accent" :class="target" aria-label="Um volume a menos" @click="stepVolumes(-1)">
                <Icon name="lucide:minus" class="size-4" />
              </button>
              <span class="min-w-10 text-center op-title tnum" aria-live="polite" data-card-volumes-draft>{{ volumesDraft }}</span>
              <button type="button" class="grid place-items-center rounded-md border border-border transition hover:bg-accent" :class="target" aria-label="Um volume a mais" @click="stepVolumes(1)">
                <Icon name="lucide:plus" class="size-4" />
              </button>
              <button
                type="button"
                class="ml-auto inline-flex items-center rounded-md bg-primary px-3 op-label font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
                :class="target"
                :disabled="busy"
                data-card-volumes-save
                @click="saveVolumes"
              >Gravar</button>
            </div>
            <p class="op-micro text-muted-foreground">{{ volumesDraft === 0 ? "Zero apaga: o cartão volta a contar itens." : "Sacolas ou caixas, contadas por quem embalou." }}</p>
          </div>
          <button
            v-else-if="volumesAction"
            type="button"
            role="menuitem"
            class="flex w-full items-center gap-2.5 px-3 text-left op-body transition hover:bg-accent disabled:opacity-60"
            :class="target"
            :disabled="busy || !volumesAction.enabled"
            :title="volumesAction.reason || undefined"
            data-card-volumes
            @click="openVolumes"
          >
            <Icon name="lucide:package" class="size-4 shrink-0 text-muted-foreground" />
            {{ card.volumes ? `Volumes: ${card.volumes} (mudar)` : "Declarar volumes" }}
          </button>
          <button
            v-for="option in recallOptions"
            :key="option.ticketPk"
            type="button"
            role="menuitem"
            class="flex w-full items-center gap-2.5 px-3 text-left op-body transition hover:bg-accent disabled:opacity-60"
            :class="target"
            :disabled="busy"
            data-card-recall
            @click="pick(() => emit('station-recall', option.ticketPk))"
          >
            <Icon name="lucide:rotate-ccw" class="size-4 shrink-0 text-muted-foreground" />
            {{ option.label }}
          </button>
          <NuxtLink
            v-if="canOpen"
            :to="`/${card.ref}`"
            role="menuitem"
            class="flex w-full items-center gap-2.5 px-3 op-body transition hover:bg-accent"
            :class="target"
            data-card-open
          >
            <Icon name="lucide:file-text" class="size-4 shrink-0 text-muted-foreground" />
            Abrir o pedido
          </NuxtLink>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
/* A estação ainda trabalhando: o traço tracejado da v4 (`.seg span.wip`). */
.seg-wip {
  background: repeating-linear-gradient(90deg, var(--info) 0 6px, color-mix(in oklab, var(--info) 35%, transparent) 6px 10px);
}
/* Botão bloqueado: tracejado com listras finas no tom do bloqueio (`.stripes` da v4). */
.card-stripes {
  background: repeating-linear-gradient(135deg, transparent 0 7px, color-mix(in oklab, var(--destructive) 9%, transparent) 7px 14px);
}
</style>
