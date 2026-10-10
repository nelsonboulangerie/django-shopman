<script setup lang="ts">
// A Fila "Precisa de você" (V4-G4, prévia v4 `gestor-fila4.html`):
//
//   PRECISA DE VOCÊ 4                         Mais urgente primeiro (tempo contra a meta)
//   [R7K  27 min meta 30 | João Oliveira · Entrega · … | Dinheiro …  R$ 74,00 [Saiu]]
//   …
//   Mais 3 pedem você · Seguem sozinhos: 5 na cozinha, 2 na rua            Ver todos ›
//
//   EM ANDAMENTO 7 · O SISTEMA FEZ (últimos 15 min) · AGORA NO CARDÁPIO
//
// Só o fato humano é botão. A Lista (a tabela densa, seleção em lote) segue a um
// toque (alternador e tecla L); as três colunas, no ⋯ e na tecla V; o detalhe abre pelo
// código. Recortes (v4): "Precisa de você" com 4 em foco e o resto num "+N", "Todos" e
// "Atrasados". O tempo é âmbar com intensidade: vermelho é só o bloqueio com motivo.
// Nada aqui decide estado: o fato, a meta, a previsão da Cozinha e o "o sistema fez"
// vêm do servidor (`order_attention`).
import type {
  OrderCardProjection,
  QueueAwarenessProjection,
} from "~/types/orders";
import type { AffordanceRef } from "~/presentation/board";
import {
  channelLabel,
  confirmationRemainingLabel,
  splitRef,
  undoLine,
} from "~/presentation/board";
import {
  inProgress,
  QUEUE_FOCUS,
  QUEUE_SORT_OPTIONS,
  queueGesture,
  queueItems,
  queueWho,
  restLine,
  workingOrders,
  type QueueItem,
  type QueueScope,
  type QueueSort,
} from "~/presentation/queue";
import OrderCardMenu from "./OrderCardMenu.vue";

const props = withDefaults(
  defineProps<{
    cards: OrderCardProjection[];
    awareness: QueueAwarenessProjection | null | undefined;
    nowMs: number;
    focusRef: string;
    /** O pedido novo que a tecla A aceita (o em foco, ou o mais urgente). */
    acceptRef?: string;
    scope?: QueueScope;
    sort?: QueueSort;
    isBusy: (ref: string) => boolean;
    actionError: (ref: string) => string;
    canOpen: boolean;
    /** O interruptor do canal está indo ao servidor. */
    switching?: (ref: string) => boolean;
  }>(),
  {
    acceptRef: "",
    scope: "attention",
    sort: "urgency",
    switching: () => false,
  },
);
const emit = defineEmits<{
  (e: "action", ref: string, action: AffordanceRef): void;
  (e: "station-ready", card: OrderCardProjection, stationRef: string): void;
  (e: "focus" | "dismiss-error" | "switch" | "select-mode", ref: string): void;
  (e: "scope", scope: QueueScope): void;
  (e: "toggle-assign", card: OrderCardProjection): void;
  (e: "volumes" | "station-recall", ref: string, value: number): void;
}>();

const items = computed(() =>
  queueItems(props.cards, props.nowMs, {
    scope: props.scope,
    sort: props.sort,
  }),
);
// Densidade pela atenção (SPEC4 §4): em "Precisa de você", 4 em foco; o resto vira "+N".
const shown = computed(() =>
  props.scope === "attention" ? items.value.slice(0, QUEUE_FOCUS) : items.value,
);
const hidden = computed(() => items.value.length - shown.value.length);
const progress = computed(() => inProgress(props.cards, props.nowMs));
const rest = computed(() =>
  props.scope === "attention"
    ? restLine(progress.value, hidden.value)
    : { hidden: 0, moving: 0, text: "" },
);
const working = computed(() => workingOrders(props.cards, props.nowMs));
const workingCount = computed(
  () => working.value.kitchen.length + working.value.road.length,
);
function accordionItems(orders: ReturnType<typeof workingOrders>["kitchen"]) {
  return orders.map((order) => ({
    value: order.card.ref,
    label: `${splitRef(order.card.ref).code} ${order.card.customer_name}`,
    code: splitRef(order.card.ref).code,
    who: order.card.customer_name || "Sem cliente",
    summary: order.summary,
    age: order.ageLabel,
    items: order.card.items_summary,
    stations: order.stations,
  }));
}
const workingGroups = computed(() => {
  const detail = (key: "kitchen" | "road") =>
    progress.value.find((line) => line.key === key)?.detail ?? "";
  return [
    {
      key: "kitchen",
      label: "Na Cozinha",
      icon: "lucide:chef-hat",
      orders: working.value.kitchen,
      items: accordionItems(working.value.kitchen),
      detail: detail("kitchen"),
      emptyText: "Nada na cozinha agora.",
    },
    {
      key: "road",
      label: "Na rua",
      icon: "lucide:bike",
      orders: working.value.road,
      items: accordionItems(working.value.road),
      detail: detail("road"),
      emptyText: "Nenhuma entrega na rua.",
    },
  ];
});
const systemActions = computed(() => props.awareness?.system_actions ?? []);
const outages = computed(() => props.awareness?.menu_outages ?? []);
const menuChannels = computed(() => props.awareness?.menu_channels ?? []);
const title = computed(
  () =>
    ({ attention: "Precisa de você", all: "Todos", late: "Atrasados" })[
      props.scope
    ],
);
const sortHint = computed(
  () =>
    QUEUE_SORT_OPTIONS.find((option) => option.key === props.sort)?.hint ?? "",
);
const emptyText = computed(
  () =>
    ({
      attention: "Nada pede você agora.",
      all: "Nenhum pedido em andamento.",
      late: "Nenhum pedido passou da meta.",
    })[props.scope],
);

function clock(iso: string): string {
  const at = iso ? new Date(iso) : null;
  return at && !Number.isNaN(at.getTime())
    ? at.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
    : "";
}
function readyStation(card: OrderCardProjection) {
  return (
    card.kitchen?.stations.find((station) => station.can_mark_ready) ?? null
  );
}
function systemUndoOpen(line: {
  undo_action: string;
  undo_until_iso: string;
}): boolean {
  return (
    Boolean(line.undo_action) && Date.parse(line.undo_until_iso) > props.nowMs
  );
}
function cardFor(ref: string): OrderCardProjection | undefined {
  return props.cards.find((card) => card.ref === ref);
}
/** A pílula do bloqueio é um estado, não uma espera em curso: sem reticências. */
function blockLabel(card: OrderCardProjection): string {
  return (card.advance_block_label || "Bloqueado").replace(/…$/, "");
}
function toneColor(tone: QueueItem["tone"]): "success" | "warning" | "error" {
  if (tone === "late") return "error";
  if (tone === "warning") return "warning";
  return "success";
}
/** A tecla impressa no botão (desktop, `pointer: fine`): Enter no item em foco; A no
 *  pedido novo que a tecla aceita. A que não vale ali não se imprime (o R é "atualizar"). */
function printedKey(item: QueueItem): string {
  const gesture = queueGesture(item);
  if (!gesture.primary || gesture.primary.disabled) return "";
  if (gesture.shortcut === "A")
    return item.card.ref === props.acceptRef ? "A" : "";
  if (item.card.ref !== props.focusRef) return "";
  return gesture.shortcut === "Enter" ? "enter" : gesture.shortcut;
}
/** "desligar pede gerente" / "ligar pede gerente": a consequência antes do gesto. */
function switchHint(row: {
  active: boolean;
  switch?: { requires_manager_approval: boolean } | null;
}): string {
  if (!row.switch?.requires_manager_approval) return "";
  return row.active ? "desligar pede gerente" : "ligar pede gerente";
}
</script>

<template>
  <div
    class="grid shrink-0 gap-5 lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_400px]"
    data-queue-view
  >
    <!-- a Fila: só o que pede um fato humano, por urgência -->
    <section
      class="flex min-w-0 flex-col gap-2.5"
      aria-labelledby="queue-title"
    >
      <div class="flex items-baseline gap-2 border-b border-border pb-2">
        <h2 id="queue-title" class="op-eyebrow">{{ title }}</h2>
        <span class="op-label tnum text-muted-foreground" data-queue-count>{{
          items.length
        }}</span>
        <span
          class="ms-auto hidden op-micro text-muted-foreground sm:inline"
          data-queue-sort-hint
          >{{ sortHint }}</span
        >
      </div>

      <NuxtEmpty
        v-if="!items.length"
        icon="i-lucide-inbox"
        :description="emptyText"
        data-queue-empty
      />

      <!-- O item da vez (o mais urgente, ou o que o operador escolheu) recebe o destaque
           semântico do Kitchen Sink: PageCard com highlight na cor primária. -->
      <NuxtPageCard
        v-for="item in shown"
        :key="item.card.ref"
        as="article"
        variant="outline"
        :highlight="item.card.ref === focusRef"
        highlight-color="primary"
        :data-queue-item="item.kind || 'moving'"
        :data-queue-ref="item.card.ref"
        :aria-current="item.card.ref === focusRef || undefined"
        @pointerdown="emit('focus', item.card.ref)"
      >
        <div
          class="grid gap-3 sm:grid-cols-[80px_minmax(0,1fr)] sm:items-start xl:grid-cols-[92px_minmax(0,1fr)_240px] xl:items-center xl:gap-4"
        >
          <!-- código, tempo na etapa e a meta -->
          <div
            class="flex min-w-0 flex-col items-start gap-1 sm:row-span-2 xl:row-span-1"
          >
            <NuxtLink
              v-if="canOpen"
              :to="`/${item.card.ref}`"
              class="block op-figure leading-none hover:underline"
              :aria-label="`Abrir pedido ${item.card.ref}`"
              >{{ splitRef(item.card.ref).code }}</NuxtLink
            >
            <p v-else class="op-figure leading-none">
              {{ splitRef(item.card.ref).code }}
            </p>
            <NuxtBadge
              :color="toneColor(item.tone)"
              :label="item.timeLabel"
              :data-queue-tone="item.tone"
              data-queue-time
            />
            <p class="op-micro text-muted-foreground" data-queue-goal>
              {{ item.goalLabel }}
            </p>
          </div>

          <!-- quem, o quê e o estado escrito (a cópia não se corta: quebra a linha) -->
          <div
            class="flex min-w-0 flex-col gap-1.5 sm:col-start-2 xl:col-start-auto"
          >
            <p class="op-body">
              <span class="font-semibold">{{
                queueWho(item.card, channelLabel(item.card.channel_ref)).name
              }}</span>
              <span class="text-muted-foreground">
                ·
                {{
                  queueWho(item.card, channelLabel(item.card.channel_ref)).rest
                }}</span
              >
            </p>
            <p class="op-body text-foreground/85">
              {{ item.card.items_summary }}
            </p>
            <!-- pagamento é fato do pedido: mora com os itens, não espreme o gesto. No
                 bloqueado, o selo do bloqueio já diz o pagamento ("Pix pendente"). -->
            <p
              v-if="
                item.card.change_label ||
                (item.card.payment_method_label && item.kind !== 'blocked')
              "
              class="flex items-start gap-1.5 op-micro text-muted-foreground"
              data-queue-payment
            >
              <Icon
                :name="
                  item.card.change_label ? 'lucide:coins' : 'lucide:wallet'
                "
                class="mt-px size-3.5 shrink-0"
              />
              <span>{{
                item.card.change_label || item.card.payment_method_label
              }}</span>
            </p>
            <div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <template
                v-if="undoLine(item.card, nowMs)?.kind === 'auto_ready'"
              >
                <NuxtBadge
                  color="neutral"
                  icon="i-lucide-sparkles"
                  :label="undoLine(item.card, nowMs)!.label"
                  data-queue-auto
                />
                <NuxtButton
                  v-if="undoLine(item.card, nowMs)!.canUndo"
                  label="Desfazer"
                  color="neutral"
                  variant="ghost"
                  :disabled="isBusy(item.card.ref)"
                  @click="emit('action', item.card.ref, 'undo_ready')"
                />
                <span class="op-micro text-muted-foreground">{{
                  undoLine(item.card, nowMs)!.canUndo
                    ? undoLine(item.card, nowMs)!.detail
                    : `Cozinha concluiu às ${clock(item.card.ready_at_iso)}`
                }}</span>
              </template>
              <template v-else-if="item.kind === 'negotiation'">
                <NuxtBadge
                  color="error"
                  icon="i-lucide-message-square-warning"
                  label="Negociação iFood"
                  data-queue-negotiation
                />
                <span class="op-micro text-muted-foreground"
                  >no prazo, o iFood decide sem a loja</span
                >
              </template>
              <template v-else-if="item.kind === 'confirm'">
                <NuxtBadge color="primary" label="Novo" />
                <span
                  v-if="
                    item.card.confirmation_deadline_iso &&
                    confirmationRemainingLabel(
                      item.card.confirmation_deadline_iso,
                      nowMs,
                    )
                  "
                  class="op-micro text-muted-foreground"
                  data-queue-deadline
                >
                  {{
                    item.card.confirmation_action === "cancel"
                      ? "cancela sozinho em"
                      : "aceita sozinho em"
                  }}
                  <span class="font-semibold tnum text-foreground">{{
                    confirmationRemainingLabel(
                      item.card.confirmation_deadline_iso,
                      nowMs,
                    )
                  }}</span>
                </span>
              </template>
              <template v-else-if="item.kind === 'blocked'">
                <NuxtBadge
                  color="error"
                  icon="i-lucide-lock"
                  :label="blockLabel(item.card)"
                  data-queue-block
                />
                <span
                  class="min-w-0 op-micro text-muted-foreground"
                  data-queue-block-reason
                  >{{ item.card.advance_block_reason }}</span
                >
              </template>
              <template
                v-else-if="item.kind === 'station' && readyStation(item.card)"
              >
                <NuxtBadge
                  color="neutral"
                  icon="i-lucide-printer"
                  :label="`${readyStation(item.card)!.station_name} no papel`"
                />
                <span class="op-micro text-muted-foreground">{{
                  item.card.kitchen?.missing_label
                }}</span>
              </template>
              <template v-else-if="!item.kind">
                <NuxtBadge
                  color="neutral"
                  :label="item.card.status_label"
                  data-queue-moving
                />
                <span class="op-micro text-muted-foreground"
                  >nada pede você agora</span
                >
              </template>
            </div>
            <NuxtAlert
              v-if="actionError(item.card.ref)"
              color="error"
              variant="subtle"
              icon="i-lucide-triangle-alert"
              :title="actionError(item.card.ref)"
              close
              @update:open="emit('dismiss-error', item.card.ref)"
            />
          </div>

          <!-- pagamento, total e o gesto -->
          <!-- total e gesto: numa linha sob o conteúdo; na coluna própria a partir do xl -->
          <div
            class="flex min-w-0 items-center gap-3 sm:col-start-2 xl:col-start-auto xl:flex-col xl:items-stretch xl:gap-1.5"
          >
            <span class="shrink-0 op-title tnum xl:self-end">{{
              item.card.total_display
            }}</span>
            <!-- o gesto da linha e o ⋯ do pedido (as mesmas opções do cartão do quadro) -->
            <div class="flex min-w-0 flex-1 items-center gap-1.5">
              <NuxtButton
                v-if="item.kind === 'negotiation'"
                :to="`/${item.card.ref}#ifood-negotiations`"
                icon="i-lucide-message-square-reply"
                label="Responder"
                color="primary"
                block
                class="min-w-0 flex-1"
                data-queue-primary
              />
              <template
                v-else-if="item.kind === 'station' && readyStation(item.card)"
              >
                <NuxtButton
                  icon="i-lucide-check"
                  color="primary"
                  block
                  class="min-w-0 flex-1"
                  :disabled="isBusy(item.card.ref)"
                  data-queue-primary
                  @click="
                    emit(
                      'station-ready',
                      item.card,
                      readyStation(item.card)!.station_ref,
                    )
                  "
                >
                  <span class="min-w-0 text-center leading-tight">{{
                    `Pronto de ${readyStation(item.card)!.station_name}`
                  }}</span>
                  <template v-if="item.card.ref === focusRef" #trailing>
                    <NuxtKbd
                      value="enter"
                      size="sm"
                      variant="soft"
                      data-queue-key
                    />
                  </template>
                </NuxtButton>
              </template>
              <div
                v-else-if="queueGesture(item).primary"
                class="grid min-w-0 flex-1 gap-1.5"
                :class="
                  queueGesture(item).secondary
                    ? 'grid-cols-[minmax(0,1fr)_minmax(0,2fr)]'
                    : 'grid-cols-1'
                "
              >
                <NuxtButton
                  v-if="queueGesture(item).secondary"
                  block
                  class="min-w-0"
                  color="neutral"
                  variant="outline"
                  :disabled="
                    isBusy(item.card.ref) ||
                    queueGesture(item).secondary!.disabled
                  "
                  :title="queueGesture(item).secondary!.reason || undefined"
                  data-queue-secondary
                  @click="
                    emit(
                      'action',
                      item.card.ref,
                      queueGesture(item).secondary!.ref,
                    )
                  "
                >
                  <span class="min-w-0 text-center leading-tight">{{
                    queueGesture(item).secondary!.label
                  }}</span>
                </NuxtButton>
                <NuxtButton
                  :icon="
                    queueGesture(item).primary!.disabled
                      ? 'i-lucide-lock'
                      : item.kind === 'dispatch'
                        ? 'i-lucide-bike'
                        : item.kind === 'handoff'
                          ? 'i-lucide-hand-platter'
                          : queueGesture(item).primary!.icon.replace(
                              'lucide:',
                              'i-lucide-',
                            )
                  "
                  :color="
                    queueGesture(item).primary!.disabled ? 'neutral' : 'primary'
                  "
                  :variant="
                    queueGesture(item).primary!.disabled ? 'outline' : 'solid'
                  "
                  block
                  class="min-w-0"
                  :disabled="
                    isBusy(item.card.ref) ||
                    queueGesture(item).primary!.disabled
                  "
                  :title="
                    queueGesture(item).primary!.reason ||
                    (queueGesture(item).primary!.verb !==
                    queueGesture(item).primary!.label
                      ? queueGesture(item).primary!.label
                      : undefined)
                  "
                  data-queue-primary
                  @click="
                    emit(
                      'action',
                      item.card.ref,
                      queueGesture(item).primary!.ref,
                    )
                  "
                >
                  <span class="min-w-0 text-center leading-tight">{{
                    queueGesture(item).primary!.verb
                  }}</span>
                  <template v-if="printedKey(item)" #trailing>
                    <NuxtKbd
                      :value="printedKey(item)"
                      size="sm"
                      variant="soft"
                      data-queue-key
                    />
                  </template>
                </NuxtButton>
              </div>
              <div v-else class="flex-1" />
              <OrderCardMenu
                class="shrink-0"
                :card="item.card"
                :busy="isBusy(item.card.ref)"
                :can-open="canOpen"
                @toggle-assign="emit('toggle-assign', item.card)"
                @select-mode="emit('select-mode', item.card.ref)"
                @volumes="(count) => emit('volumes', item.card.ref, count)"
                @station-recall="
                  (pk) => emit('station-recall', item.card.ref, pk)
                "
              />
            </div>
          </div>
        </div>
      </NuxtPageCard>

      <!-- o excedente vira contagem com nome, nunca paginação nem soma de grandezas
           diferentes (P1-7). "Ver todos" abre o recorte Todos. -->
      <NuxtButton
        v-if="rest.text"
        color="neutral"
        variant="outline"
        trailing-icon="i-lucide-chevron-right"
        :label="`${rest.text} · Ver todos`"
        data-queue-rest
        @click="emit('scope', 'all')"
      />
    </section>

    <!-- a coluna de consciência: o agregado, o que o sistema fez e os interruptores -->
    <aside
      class="flex min-w-0 flex-col gap-4"
      aria-label="Em andamento e o que o sistema fez"
    >
      <!-- Em andamento (dono, 07/10/2026): o que está de fato na cozinha, pedido a
           pedido; aberto, cada estação com o estado e os itens que foram para ela. -->
      <NuxtCard data-queue-progress>
        <div class="flex flex-col gap-3">
          <div class="flex items-center justify-between gap-3">
            <h2 class="op-title">Em andamento</h2>
            <NuxtBadge
              color="neutral"
              :label="`${workingCount} ${workingCount === 1 ? 'pedido' : 'pedidos'}`"
            />
          </div>
          <div class="flex flex-col gap-3">
            <section
              v-for="group in workingGroups"
              :key="group.key"
              class="flex flex-col gap-1"
              :data-queue-working="group.key"
            >
              <p class="flex items-center gap-2 op-label">
                <Icon :name="group.icon" class="size-4 text-info" />
                <span class="flex-1">{{ group.label }}</span>
                <span class="op-title tnum">{{ group.orders.length }}</span>
              </p>
              <p
                v-if="group.detail"
                class="op-micro leading-snug text-muted-foreground"
                :data-queue-progress-detail="group.key"
              >
                {{ group.detail }}
              </p>
              <!-- Lista emoldurada (dono, 07/10/2026): um card sem cabeçalho nem rodapé
                   por grupo, uma coluna só, como uma tabela sem cabeçalho. O kit tira o
                   padding vertical do corpo quando o Accordion é o conteúdo inteiro. -->
              <NuxtCard
                v-if="group.orders.length"
                :data-queue-working-list="group.key"
              >
                <NuxtAccordion type="multiple" :items="group.items">
                  <!-- Duas linhas (dono, 08/10/2026): "B03 · Maria Santos" em cima; a
                       situação embaixo, truncada se precisar, com o tempo e a seta na
                       mesma linha dela. Numa linha só o nome era espremido a 340 px. -->
                  <template #default="{ item }">
                    <span class="flex min-w-0 flex-1 flex-col" data-queue-working-row>
                      <span class="break-words">
                        <span class="font-semibold tnum">{{ item.code }}</span>
                        <span class="text-muted-foreground"> · {{ item.who }}</span>
                      </span>
                      <span
                        class="truncate op-micro text-muted-foreground"
                        :title="item.summary"
                        >{{ item.summary }}</span
                      >
                    </span>
                  </template>
                  <template #trailing="{ item }">
                    <span class="ms-auto flex shrink-0 items-center gap-2 self-end">
                      <NuxtBadge
                        color="neutral"
                        :label="item.age"
                      />
                      <Icon
                        name="lucide:chevron-down"
                        class="size-4 text-dimmed transition-transform group-data-[state=open]:rotate-180"
                      />
                    </span>
                  </template>
                  <template #body="{ item }">
                    <div class="flex flex-col gap-2" data-queue-working-detail>
                      <div
                        v-for="station in item.stations"
                        :key="station.ref"
                        class="flex flex-col gap-1"
                      >
                        <p class="flex items-center gap-2 op-label">
                          <span class="flex-1 font-medium">{{
                            station.name
                          }}</span>
                          <NuxtBadge
                            :color="station.tone"
                            :label="station.label"
                          />
                        </p>
                        <p
                          v-if="station.items.length"
                          class="op-micro text-muted-foreground"
                        >
                          {{ station.items.join(" · ") }}
                        </p>
                      </div>
                      <p
                        v-if="!item.stations.length"
                        class="op-micro text-muted-foreground"
                      >
                        {{ item.items }}
                      </p>
                      <NuxtButton
                        v-if="canOpen"
                        :to="`/${item.value}`"
                        class="self-start"
                        label="Abrir o pedido"
                        icon="i-lucide-file-text"
                        color="neutral"
                        variant="ghost"
                      />
                    </div>
                  </template>
                </NuxtAccordion>
              </NuxtCard>
              <p v-else class="op-micro text-muted-foreground">
                {{ group.emptyText }}
              </p>
            </section>
          </div>
        </div>
      </NuxtCard>

      <NuxtCard data-queue-system>
        <div class="flex items-center justify-between gap-3 pb-1">
          <h2 class="op-title">O sistema fez</h2>
          <NuxtBadge
            color="neutral"
            :label="`${awareness?.system_window_minutes ?? 15} min`"
          />
        </div>
        <NuxtEmpty
          v-if="!systemActions.length"
          icon="i-lucide-sparkles"
          description="Nada automático neste intervalo."
        />
        <template
          v-for="(line, index) in systemActions"
          :key="`${line.order_ref}-${line.at_iso}`"
        >
          <div class="flex items-center gap-2 py-2">
            <span class="w-11 op-label font-semibold tnum">{{
              splitRef(line.order_ref).code
            }}</span>
            <span class="min-w-0 flex-1 op-body"
              >{{ line.verb }}
              <span class="text-muted-foreground"
                >· {{ line.reason }}</span
              ></span
            >
            <NuxtButton
              v-if="systemUndoOpen(line) && cardFor(line.order_ref)"
              label="Desfazer"
              color="neutral"
              variant="ghost"
              :disabled="isBusy(line.order_ref)"
              data-queue-system-undo
              @click="emit('action', line.order_ref, 'undo_ready')"
            />
            <span v-else class="op-micro tnum text-muted-foreground">{{
              line.at_display
            }}</span>
          </div>
          <NuxtSeparator v-if="index < systemActions.length - 1" />
        </template>
        <p class="pt-2 op-micro leading-snug text-muted-foreground">
          Aviso ao cliente só sai depois da janela de desfazer. “Marcar
          pronto” à mão continua no menu do pedido.
        </p>
      </NuxtCard>

      <NuxtCard v-if="outages.length || menuChannels.length" data-queue-menu>
        <div class="flex items-center justify-between gap-3 pb-1">
          <h2 class="op-title">Agora no cardápio</h2>
          <NuxtBadge
            v-if="awareness?.menu_outages_more"
            color="warning"
            :label="`+${awareness.menu_outages_more} fora do ar`"
          />
        </div>
        <div
          v-for="outage in outages"
          :key="outage.sku"
          class="flex items-center gap-2 py-2"
        >
          <span class="min-w-0 flex-1">
            <span class="block op-body">{{ outage.line }}</span>
            <span
              class="inline-flex items-center gap-1 op-micro text-muted-foreground"
              ><Icon name="lucide:sparkles" class="size-3" />{{
                outage.detail
              }}</span
            >
          </span>
        </div>
        <!-- o canal: "iFood ligado · desligar pede gerente · [interruptor]" (v4). O
               interruptor abre o MESMO diálogo de Canais (período, motivo, gerente). -->
        <div
          v-for="row in menuChannels"
          :key="row.ref"
          class="flex items-center gap-2 py-2"
          data-queue-channel
        >
          <Icon
            :name="row.ref === 'ifood' ? 'lucide:bike' : 'lucide:store'"
            class="size-4 shrink-0 text-muted-foreground"
          />
          <NuxtLink
            v-if="awareness?.can_open_channels"
            :to="row.focus_path"
            class="min-w-0 flex-1 op-body hover:underline"
            :title="`Abrir ${row.name} em Canais`"
          >
            {{ row.name }} {{ row.active ? "ligado" : "desligado" }}
          </NuxtLink>
          <span v-else class="min-w-0 flex-1 op-body"
            >{{ row.name }} {{ row.active ? "ligado" : "desligado" }}</span
          >
          <span
            v-if="switchHint(row)"
            class="hidden shrink-0 op-micro text-muted-foreground sm:inline"
            data-queue-channel-hint
            >{{ switchHint(row) }}</span
          >
          <NuxtSwitch
            v-if="row.switch"
            color="success"
            :model-value="row.active"
            :disabled="switching(row.ref) || !row.switch.enabled"
            :aria-label="
              row.active
                ? `${row.name}: ligado. Desligar…`
                : `${row.name}: desligado. Ligar…`
            "
            :title="row.switch.enabled ? undefined : row.switch.disabled_reason"
            data-queue-channel-switch
            @update:model-value="emit('switch', row.ref)"
          />
        </div>
      </NuxtCard>
    </aside>
  </div>
</template>
