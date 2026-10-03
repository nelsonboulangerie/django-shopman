<script setup lang="ts">
// One order card in the board. Glanceable: ref + timer up top, customer + items in
// the middle, payment/total, then the pre-resolved affordances as buttons. Status
// color is functional; chrome neutral. Tapping the ref opens the detail page.
import type { OrderCardProjection } from "~/types/orders";
import {
  cardAffordances,
  channelLabel,
  confirmationRemainingLabel,
  deadlineTone,
  lucideIcon,
  onRoadLine,
  splitRef,
  statusTone,
  timerChip,
  timerTone,
  toneBadge,
  elapsedLabel,
  undoLine,
  type AffordanceRef,
  type Tone,
} from "~/presentation/board";
import { computed, ref } from "vue";
import { danfeLine } from "~/presentation/danfe";
import { kitchenChips, kitchenChipTone, kitchenRecallOptions } from "~/presentation/kitchen";

// ``touch``: o posto de saída (Gestor na "Visão: Saída", tablet do passe): todo
// alvo do cartão sobe para 48 px. ``canOpen``: falso para quem só expede; o
// detalhe do pedido e o "Atender" são de quem gerencia: o código deixa de ser
// link e o "Atender" some.
const props = withDefaults(
  defineProps<{ card: OrderCardProjection; busy?: boolean; error?: string; selected?: boolean; negotiationOnly?: boolean; danfePrinting?: boolean; touch?: boolean; canOpen?: boolean }>(),
  { canOpen: true },
);
const emit = defineEmits<{
  (e: "action", ref: AffordanceRef): void;
  (e: "dismiss-error" | "toggle-select" | "toggle-assign" | "print-danfe"): void;
  (e: "station-ready", stationRef: string): void;
  (e: "station-recall", ticketPk: number): void;
}>();

// A Cozinha neste pedido: quem falta e o "Pronto" da estação sem tela (Preparo);
// o "Voltar para…" no menu do pedido (o que já está pronto).
const kitchenLine = computed(() => props.negotiationOnly ? "" : props.card.kitchen?.missing_label || "");
const chips = computed(() => props.negotiationOnly ? [] : kitchenChips(props.card.kitchen));
const recallOptions = computed(() => props.negotiationOnly ? [] : kitchenRecallOptions(props.card.kitchen));
const menuOpen = ref(false);
function recall(ticketPk: number) {
  menuOpen.value = false;
  emit("station-recall", ticketPk);
}
// Alvo de toque: 44 px no escritório, 48 px no posto de saída.
const target = computed(() => props.touch ? "min-h-action min-w-action" : "min-h-control min-w-control");

const code = computed(() => splitRef(props.card.ref));
const onRoad = computed(() => onRoadLine(props.card));
const affordances = computed(() => props.negotiationOnly ? [] : cardAffordances(props.card));
// Tom do pagamento vem da projeção, não de dedução na tela: dinheiro não é
// "pago" nem "devendo" — é cobrança fora do site, e verde ali diria que entrou
// dinheiro que não entrou. O fundo esmaecido reusa `toneBadge`, o mesmo do pill
// de status: dois pills lado a lado com gramáticas visuais diferentes fazem o
// olho tratá-los como coisas de naturezas distintas.
const paymentPillClass = computed(() => toneBadge(props.card.payment_tone as Tone));
// Ícones de 12px pedem silhueta, não detalhe: um check dentro de um círculo vira
// um borrão nesse tamanho. Traço simples, forma reconhecível de longe.
const paymentPillIcon = computed(() => {
  // Sem meio de pagamento = sem info nenhuma: interrogação, não a ampulheta de
  // "aguardando" (ambos usam o tom warning, o meio vazio é que os separa).
  if (!props.card.payment_method) return "lucide:circle-help";
  // Esperando pagamento é ampulheta, não alarme: quem não paga a tempo é
  // cancelado e sai do board (ver _payment_tone no backend).
  return ({
    warning: "lucide:hourglass",
    danger: "lucide:alert-triangle",
    success: "lucide:check",
    neutral: "lucide:banknote"
  }[props.card.payment_tone] || "lucide:banknote");
});
const tTone = computed(() => timerTone(props.card.timer_class));
// A DANFE da nota autorizada: vai na sacola da entrega (sai sozinha pelo
// servidor) e fica à mão na retirada, para o cliente que pede no balcão.
const danfe = computed(() => props.negotiationOnly ? null : danfeLine(props.card));

// Countdown do prazo da confirmação otimista (só em cards com timer agendado).
// Usa o relógio compartilhado (um só interval no board, não um por card).
const nowMs = useNowTick(() => props.card.server_now_iso);
const confirmationLeft = computed(() =>
  confirmationRemainingLabel(props.card.confirmation_deadline_iso, nowMs.value),
);
const deadlineTone_ = computed(() => deadlineTone(props.card.confirmation_deadline_iso, nowMs.value));
// "O sistema fez · desfazer": o pronto que veio da Cozinha, ou a saída tocada
// ainda na janela. O fato fica à vista; o gesto só enquanto o prazo corre.
const undo = computed(() => props.negotiationOnly ? null : undoLine(props.card, nowMs.value));

// Visual da suíte (UX-KIT-V1, `_ocard.html` das prévias): pílula de estado com ponto,
// sem borda; relógio sem caixa quando não há urgência (só o atraso ganha cor).
const PILL = "inline-flex h-6 items-center gap-1.5 rounded-full border border-transparent px-2 text-xs font-semibold";
function timerClass(tone: string): string {
  return tone === "late" || tone === "warning" ? `rounded-full ${timerChip(tone as never)}` : "border-transparent text-muted-foreground";
}

function buttonClass(priority: string): string {
  if (priority === "primary")
    return "bg-primary text-primary-foreground hover:bg-primary/90 border-transparent";
  if (priority === "danger")
    return "border-destructive/40 text-destructive hover:bg-destructive/10 dark:text-orange-300";
  return "border-border hover:bg-accent";
}
</script>

<template>
  <!-- foco: pedidos NOVOS (aguardando aceitar/recusar) ganham um filete âmbar à
       esquerda — a decisão pendente do operador salta à vista sem poluir o resto. -->
  <article
    class="flex flex-col gap-2.5 rounded-lg border bg-card p-3.5 transition hover:border-primary/40"
    :class="[
      selected ? 'border-primary ring-1 ring-primary' : '',
      card.can_confirm && !selected ? 'border-l-2 border-l-warning' : '',
    ]"
  >
    <!-- Homologação do iFood: o pedido de teste é operável como qualquer outro,
         e é essa semelhança que engana em horário de movimento. O aviso vem
         ANTES do código, com a frase inteira: o que fazer (avançar) e o que não
         fazer (produzir, entregar). Até aqui a única pista era o item vir com
         "NÃO ENTREGAR" no nome. -->
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

    <!-- ref + timer. Prévia v3 (`_ocard.html`): a linha fina do canal com o relógio
         à direita, o código grande embaixo. O código nunca encolhe: o relógio mora na
         linha fina para sobrar largura até no cartão estreito (posto Saída, celular). -->
    <div class="flex items-start gap-2">
      <button
        v-if="!negotiationOnly"
        type="button"
        class="-mt-1 -ml-2 grid shrink-0 place-items-center rounded transition hover:bg-accent"
        :class="touch ? 'size-action' : 'size-control'"
        :aria-label="selected ? 'Desmarcar pedido' : 'Selecionar pedido'"
        :aria-pressed="selected"
        @click="emit('toggle-select')"
      >
        <span class="grid size-5 place-items-center rounded border" :class="selected ? 'border-primary bg-primary text-primary-foreground' : 'border-input bg-card hover:border-primary'">
          <Icon v-if="selected" name="lucide:check" class="size-3.5" />
        </span>
      </button>
      <div class="min-w-0 flex-1">
        <p class="flex min-h-6 items-center gap-1.5 text-xs text-muted-foreground">
          <Icon :name="`lucide:${lucideIcon(card.channel_icon)}`" class="size-3.5 shrink-0" />
          <span class="min-w-0 truncate tracking-[0.02em]">{{ channelLabel(card.channel_ref) }} · {{ code.prefix }}</span>
          <!-- Um relógio só. Havendo prazo, ele é o relógio: quanto FALTA decide se o
               operador pega este pedido agora, e quanto PASSOU não decide nada. Sem
               prazo (a maioria dos estados), volta a contar o decorrido. -->
          <span
            v-if="confirmationLeft"
            class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 op-label font-semibold tabular-nums"
            :class="timerChip(deadlineTone_)"
            :title="card.confirmation_action === 'cancel' ? 'Cancelado automaticamente se vencer' : 'Confirmado automaticamente se vencer'"
            role="timer"
            aria-live="off"
          >
            <Icon name="lucide:hourglass" class="size-3" />
            <span class="sr-only">Restam </span>{{ confirmationLeft }}
          </span>
          <span
            v-else
            class="ml-auto inline-flex shrink-0 items-center gap-1 border px-2 py-0.5 op-label tabular-nums"
            :class="timerClass(tTone)"
          >
            <Icon name="lucide:clock" class="size-3.5" />
            {{ elapsedLabel(card.elapsed_seconds) }}
          </span>
        </p>
        <NuxtLink v-if="canOpen" :to="`/${card.ref}`" class="group inline-flex min-w-control flex-col justify-start pt-1" :class="touch ? 'min-h-action' : 'min-h-control'" :aria-label="`Abrir pedido ${card.ref}`">
          <span class="block op-figure leading-none tracking-[-0.01em] break-all group-hover:underline">{{ code.code }}</span>
          <!-- Só quando o ref NÃO carrega o número do canal (colisão no dia, ou pedido
               anterior a essa mudança). No caso normal o código acima já é ele, e
               repetir aqui daria dois números para o operador conferir. -->
          <span
            v-if="card.channel_display_id"
            class="block break-all text-xs font-medium tabular-nums text-muted-foreground"
            data-channel-display-id
          >iFood #{{ card.channel_display_id }}</span>
        </NuxtLink>
        <!-- quem só expede não abre o detalhe (é de quem gerencia): o código é só texto -->
        <div v-else class="flex flex-col justify-start pt-1" :class="touch ? 'min-h-action' : 'min-h-control'" data-card-code>
          <span class="block op-figure leading-none tracking-[-0.01em] break-all">{{ code.code }}</span>
          <span
            v-if="card.channel_display_id"
            class="block break-all text-xs font-medium tabular-nums text-muted-foreground"
            data-channel-display-id
          >iFood #{{ card.channel_display_id }}</span>
        </div>
      </div>
      <button
        v-if="!negotiationOnly && canOpen"
        type="button"
        class="inline-flex shrink-0 items-center justify-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium transition"
        :class="[target, card.assigned_operator ? 'border-primary/40 bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent']"
        :aria-label="card.assigned_operator ? `Atendido por ${card.assigned_operator}. Toque para liberar` : 'Atender este pedido'"
        :title="card.assigned_operator ? `${card.assigned_operator}: toque para liberar` : 'Atender'"
        @click="emit('toggle-assign')"
      >
        <Icon :name="card.assigned_operator ? 'lucide:user-check' : 'lucide:user-plus'" class="size-4" />
        <span v-if="card.assigned_operator" class="max-w-20 truncate">{{ card.assigned_operator }}</span>
      </button>
    </div>

    <!-- customer + fulfillment -->
    <div class="min-w-0">
      <p class="truncate op-body">
        <span class="font-medium">{{ card.customer_name || "Sem cliente" }}</span>
        <span class="text-muted-foreground"> · {{ card.fulfillment_label }}</span>
      </p>
      <p v-if="card.courier_status_label" class="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
        <!-- corrida externa (Machine): estado do entregador direto no card -->
        <Icon name="lucide:bike" class="size-3.5 shrink-0" /> {{ card.courier_status_label }}
      </p>
      <!-- para onde vai: sem isto o cartão de uma entrega não dizia o destino,
           e quem despacha precisava abrir o pedido (onde também não estava). -->
      <p
        v-if="card.delivery_address"
        class="mt-0.5 flex items-start gap-1.5 text-xs text-muted-foreground"
        data-card-address
      >
        <Icon name="lucide:map-pin" class="mt-0.5 size-3.5 shrink-0" />
        <span class="line-clamp-2">{{ card.delivery_address }}</span>
      </p>
    </div>

    <!-- items -->
    <p class="line-clamp-2 op-body text-foreground/85">{{ card.items_summary }}</p>

    <!-- troco da entrega: o que o cliente disse, o que saiu da gaveta, o que voltou -->
    <p
      v-if="card.change_label"
      class="flex items-center gap-1.5 text-xs text-muted-foreground"
      :class="{ 'font-medium': card.change_back_pending }"
      data-change-label
    >
      <Icon name="lucide:coins" class="size-3.5 shrink-0" />
      <span class="truncate">{{ card.change_label }}</span>
    </p>
    <!-- a maquininha na rua: o único sinal dela no quadro é esta linha, no
         pedido que a levou ("Saiu com a maquininha Azul · junto com 0418") -->
    <p
      v-if="onRoad"
      class="flex items-center gap-1.5 text-xs font-medium"
      data-equipment-label
    >
      <Icon :name="card.equipment_label ? 'lucide:smartphone-nfc' : 'lucide:bike'" class="size-3.5 shrink-0" />
      <span class="truncate">{{ onRoad }}</span>
    </p>

    <!-- status + payment + total -->
    <div class="flex flex-wrap items-center gap-1.5 text-xs">
      <span :class="[PILL, toneBadge(statusTone(card.status)), 'border-transparent']">
        <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
        {{ card.status_label }}
      </span>
      <!-- agendado: pedido combinado para data futura -->
      <span
        v-if="card.is_preorder"
        class="inline-flex h-6 items-center gap-1 rounded-full border px-2 font-medium text-muted-foreground"
        data-preorder-badge
      >
        <Icon name="lucide:calendar-clock" class="size-3" />
        Agendado{{ card.commitment_date_display ? ` · ${card.commitment_date_display}` : "" }}
      </span>
      <!-- fila de espera: o pedido não está parado, está esperando a fornada.
           Sem o selo ele se parece com pedido travado, e alguém cutuca o que
           não deve. Em "confirming" o relógio corre do lado do CLIENTE. -->
      <span
        v-if="card.waitlist_label"
        class="inline-flex h-6 items-center gap-1 rounded-full border px-2 font-medium"
        :class="card.waitlist_state === 'confirming' ? 'border-primary/40 text-primary' : 'text-muted-foreground'"
        data-waitlist-badge
      >
        <Icon name="lucide:hourglass" class="size-3" />
        {{ card.waitlist_label }}
      </span>
      <!-- indicações mínimas (o conteúdo mora no detalhe): presente e
           observação do CLIENTE. Ícone só, aria diz o que é — o card fica
           escaneável sem carregar texto que não cabe aqui. -->
      <span
        v-if="card.is_gift"
        class="inline-flex h-6 items-center rounded-full border px-2 text-muted-foreground"
        role="img"
        :aria-label="card.gift_has_recipient ? 'Presente com destinatário' : 'Embalar para presente'"
        data-gift-badge
      >
        <Icon name="lucide:gift" class="size-3" />
      </span>
      <span
        v-if="card.has_customer_note"
        class="inline-flex h-6 items-center rounded-full border px-2 text-muted-foreground"
        role="img"
        aria-label="Tem observação do cliente"
        data-customer-note-badge
      >
        <Icon name="lucide:message-square" class="size-3" />
      </span>
      <span
        v-if="card.payment_method_label"
        :class="[PILL, paymentPillClass, 'border-transparent']"
      >
        <Icon :name="paymentPillIcon" class="size-3" />
        {{ card.payment_method_label }}
      </span>
      <span class="ml-auto text-base font-semibold tabular-nums">{{ card.total_display }}</span>
    </div>

    <div
      v-if="undo"
      class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"
      :data-undo="undo.kind"
    >
      <span
        class="inline-flex h-6 items-center gap-1 rounded-full border px-2 font-medium"
        :class="undo.kind === 'handoff' ? 'border-primary/40 bg-primary/10 text-primary' : 'text-muted-foreground'"
      >
        <Icon :name="undo.kind === 'handoff' ? 'lucide:check' : 'lucide:sparkles'" class="size-3" />
        {{ undo.label }}
      </span>
      <span class="text-muted-foreground" data-undo-detail>{{ undo.detail }}</span>
      <span v-if="undo.alreadyOut" class="text-muted-foreground" data-undo-already-out>· {{ undo.alreadyOut }}</span>
      <button
        v-if="undo.canUndo"
        type="button"
        class="ml-auto inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm font-semibold transition hover:bg-accent disabled:opacity-60"
        :class="[target, undo.kind === 'handoff' ? 'min-h-action border-primary text-primary' : '']"
        :disabled="busy"
        data-undo-button
        @click="emit('action', undo.action)"
      >
        <Icon name="lucide:undo-2" class="size-3.5" />
        <span class="tabular-nums">{{ undo.kind === "handoff" ? `Desfazer ${undo.countdown}` : "Desfazer" }}</span>
      </button>
    </div>

    <div v-if="danfe" class="space-y-0.5 text-xs" data-danfe :data-danfe-attention="danfe.attention || undefined">
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

    <!-- A nota que não autorizou: o gesto (Reprocessar NFC-e) mora no detalhe,
         a um toque daqui. Antes o card recebia o estado fiscal e não mostrava. -->
    <NuxtLink
      v-if="!negotiationOnly && card.fiscal_status === 'failed'"
      :to="`/${card.ref}`"
      class="min-h-control flex items-center gap-1.5 rounded-md border border-warning/40 bg-warning/10 p-2 text-sm font-medium text-warning"
      data-fiscal-failed
    >
      <Icon name="lucide:triangle-alert" class="size-4 shrink-0" />
      NFC-e não autorizada · abrir e reprocessar
    </NuxtLink>

    <NuxtLink v-if="card.ifood_negotiations?.length" :to="`/${card.ref}#ifood-negotiations`" class="min-h-control block rounded-md border border-warning/40 bg-warning/10 p-2 text-sm" data-ifood-negotiation-link>
      Negociação iFood · abrir solicitação e conferir prazo
    </NuxtLink>
    <!-- O aviso de cancelamento continua: é estado do pedido, não evidência. A
         evidência completa (bandeira, CEP, responsável pela entrega, janela em
         três linhas) mora no detalhe — aqui ela fazia o card do iFood ter o dobro
         da altura do card do PDV, na mesma coluna. -->
    <p
      v-if="card.ifood_cancellation_notice"
      class="rounded-md border border-warning/40 bg-warning/10 p-2 text-xs"
      role="status"
      data-ifood-cancellation
    >{{ card.ifood_cancellation_notice }}</p>

    <!-- O iFood já passou deste ponto: dito como instrução, logo acima do resto,
         para não parecer um segundo status disputando com o pill. -->
    <p
      v-if="card.ifood_remote_ahead_label"
      class="rounded-md border border-primary/30 bg-primary/10 px-2.5 py-1.5 text-xs font-medium"
      role="status"
      data-ifood-remote-ahead
    >{{ card.ifood_remote_ahead_label }}</p>

    <p v-if="card.ifood_schedule_label" class="text-xs text-muted-foreground" data-ifood-schedule>
      {{ card.ifood_schedule_label }}
    </p>

    <!-- Rótulo à vista: sem ele, este quatro dígitos disputava com o número do
         pedido — e era o único dos dois que aparecia. -->
    <p
      v-if="card.ifood_pickup_code"
      class="flex items-baseline gap-2 rounded-md bg-muted px-2.5 py-1.5"
      data-ifood-pickup-code
    >
      <span class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Código de retirada</span>
      <span class="ml-auto text-base font-bold tabular-nums">{{ card.ifood_pickup_code }}</span>
    </p>

    <!-- a Cozinha neste pedido (SUITE-UX §15): quem falta, e o "Pronto" da estação
         que só recebe papel. Era a coluna "Em preparo" da Saída da Cozinha. -->
    <div v-if="kitchenLine" class="flex flex-col gap-1.5" data-kitchen>
      <p class="flex items-center gap-1.5 text-xs font-semibold" data-kitchen-missing>
        <Icon name="lucide:chef-hat" class="size-3.5 shrink-0" />
        {{ kitchenLine }}
      </p>
      <ul class="flex flex-col gap-1" aria-label="Estações deste pedido">
        <li
          v-for="chip in chips"
          :key="chip.ref"
          class="flex items-center gap-2 rounded-md border px-2 py-1"
          :class="kitchenChipTone(chip.tone)"
          data-kitchen-station
        >
          <Icon :name="chip.icon" class="size-3.5 shrink-0" />
          <span class="min-w-0 flex-1 leading-tight">
            <span class="block truncate text-xs font-bold text-foreground">{{ chip.station }}</span>
            <span class="block truncate text-xs">{{ chip.detail }}</span>
            <span v-if="chip.cancelledNote" class="block truncate text-xs font-semibold text-destructive dark:text-red-300">{{ chip.cancelledNote }}</span>
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
        </li>
      </ul>
    </div>

    <!-- awaiting production -->
    <div v-if="card.awaiting_work_orders.length" class="flex flex-col gap-1">
      <div
        v-for="wo in card.awaiting_work_orders"
        :key="wo.ref"
        class="flex items-center gap-1.5 rounded-md bg-muted/60 px-2 py-1 text-xs text-muted-foreground"
      >
        <Icon name="lucide:factory" class="size-3 shrink-0" />
        <span class="truncate">{{ wo.output_sku }} · {{ wo.status_label }}</span>
        <span class="ml-auto tabular-nums">{{ wo.progress_pct }}%</span>
      </div>
    </div>

    <!-- action error: the backend's specific reason, inline and persistent -->
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

    <!-- actions -->
    <div v-if="affordances.length || recallOptions.length" class="flex flex-wrap gap-2 pt-0.5">
      <button
        v-for="aff in affordances"
        :key="aff.ref"
        type="button"
        :disabled="busy || aff.disabled"
        :title="aff.reason || undefined"
        class="inline-flex items-center justify-center gap-2 rounded-md border px-3 py-1.5 text-sm font-semibold transition disabled:opacity-60"
        :class="[
          aff.priority === 'primary' || touch ? 'min-h-action min-w-action' : 'min-h-control min-w-control',
          aff.priority === 'primary' || aff.disabled ? 'flex-1' : '',
          aff.disabled ? 'cursor-default border-dashed text-muted-foreground' : 'active:scale-[0.98] ' + buttonClass(aff.priority),
        ]"
        @click="!aff.disabled && emit('action', aff.ref)"
      >
        <Icon :name="aff.icon" class="size-4" />
        {{ aff.label }}
      </button>
      <!-- menu do pedido: devolver à cozinha o que uma estação já tinha dado por
           pronto (o recall que a Cozinha fazia na tela dela). -->
      <div v-if="recallOptions.length" class="relative ml-auto">
        <button
          type="button"
          class="grid place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground"
          :class="touch ? 'size-action' : 'size-control'"
          aria-haspopup="menu"
          :aria-expanded="menuOpen"
          :aria-label="`Mais ações do pedido ${code.code}`"
          data-card-menu
          @click="menuOpen = !menuOpen"
        >
          <Icon name="lucide:ellipsis" class="size-4" />
        </button>
        <div v-if="menuOpen" class="fixed inset-0 z-40" @click="menuOpen = false" />
        <div v-if="menuOpen" class="absolute bottom-full right-0 z-50 mb-1 w-56 overflow-hidden rounded-md border bg-card py-1 shadow-lg" role="menu">
          <button
            v-for="option in recallOptions"
            :key="option.ticketPk"
            type="button"
            role="menuitem"
            class="flex w-full items-center gap-2 px-3 text-left text-sm transition hover:bg-accent disabled:opacity-60"
            :class="target"
            :disabled="busy"
            data-card-recall
            @click="recall(option.ticketPk)"
          >
            <Icon name="lucide:rotate-ccw" class="size-4 shrink-0" />
            {{ option.label }}
          </button>
        </div>
      </div>
    </div>
    <!-- Por que o botão está travado, à vista: antes só no tooltip, que o
         tablet não tem. A frase inteira, e não o rótulo curto, que dizia
         "Encomenda do dia…" e deixava o operador completar o sentido. -->
    <p v-if="!negotiationOnly && card.advance_block_reason" class="text-xs text-muted-foreground" data-advance-block>
      {{ card.advance_block_reason }}
    </p>
  </article>
</template>
