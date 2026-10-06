<script setup lang="ts">
// A Fila "Precisa de você" (V4-G4, prévia v4 `gestor-fila4.html`):
//
//   PRECISA DE VOCÊ 4                         Mais urgente primeiro (tempo contra a meta)
//   [R7K  27 min meta 30 | João Oliveira · Entrega · … | Dinheiro …  R$ 74,00 [Saiu]]
//   …
//   +7 em andamento, nada pede você: 5 na Cozinha, 2 na rua               Ver todos ›
//
//   EM ANDAMENTO 7 · O SISTEMA FEZ (últimos 15 min) · AGORA NO CARDÁPIO
//
// Só o fato humano é botão. A Supervisão (a tabela densa, seleção em lote) segue a um
// toque (alternador e tecla T); as três colunas, no ⋯ e na tecla V; o detalhe abre pelo
// código. Recortes (v4): "Precisa de você" com 4 em foco e o resto num "+N", "Todos" e
// "Atrasados". O tempo é âmbar com intensidade: vermelho é só o bloqueio com motivo.
// Nada aqui decide estado: o fato, a meta, a previsão da Cozinha e o "o sistema fez"
// vêm do servidor (`order_attention`).
import type { OrderCardProjection, QueueAwarenessProjection } from "~/types/orders";
import type { AffordanceRef } from "~/presentation/board";
import { channelLabel, confirmationRemainingLabel, splitRef, undoLine } from "~/presentation/board";
import {
  inProgress,
  QUEUE_FOCUS,
  QUEUE_SORT_OPTIONS,
  queueGesture,
  queueItems,
  queueToneClass,
  queueWho,
  restLine,
  type QueueItem,
  type QueueScope,
  type QueueSort,
} from "~/presentation/queue";

const props = withDefaults(defineProps<{
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
}>(), { acceptRef: "", scope: "attention", sort: "urgency", switching: () => false });
const emit = defineEmits<{
  (e: "action", ref: string, action: AffordanceRef): void;
  (e: "station-ready", card: OrderCardProjection, stationRef: string): void;
  (e: "focus" | "dismiss-error" | "switch", ref: string): void;
  (e: "scope", scope: QueueScope): void;
}>();

const items = computed(() => queueItems(props.cards, props.nowMs, { scope: props.scope, sort: props.sort }));
// Densidade pela atenção (SPEC4 §4): em "Precisa de você", 4 em foco; o resto vira "+N".
const shown = computed(() => (props.scope === "attention" ? items.value.slice(0, QUEUE_FOCUS) : items.value));
const hidden = computed(() => items.value.length - shown.value.length);
const progress = computed(() => inProgress(props.cards, props.nowMs));
const rest = computed(() => (props.scope === "attention" ? restLine(progress.value, hidden.value) : { count: 0, text: "" }));
const progressCount = computed(() => progress.value.reduce((n, line) => n + line.count, 0));
const systemActions = computed(() => props.awareness?.system_actions ?? []);
const outages = computed(() => props.awareness?.menu_outages ?? []);
const menuChannels = computed(() => props.awareness?.menu_channels ?? []);
const title = computed(() => ({ attention: "Precisa de você", all: "Todos", late: "Atrasados" })[props.scope]);
const sortHint = computed(() => QUEUE_SORT_OPTIONS.find((option) => option.key === props.sort)?.hint ?? "");
const emptyText = computed(() => ({
  attention: "Nada pede você agora.",
  all: "Nenhum pedido em andamento.",
  late: "Nenhum pedido passou da meta.",
})[props.scope]);

function clock(iso: string): string {
  const at = iso ? new Date(iso) : null;
  return at && !Number.isNaN(at.getTime()) ? at.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "";
}
function readyStation(card: OrderCardProjection) {
  return card.kitchen?.stations.find((station) => station.can_mark_ready) ?? null;
}
function systemUndoOpen(line: { undo_action: string; undo_until_iso: string }): boolean {
  return Boolean(line.undo_action) && Date.parse(line.undo_until_iso) > props.nowMs;
}
function cardFor(ref: string): OrderCardProjection | undefined {
  return props.cards.find((card) => card.ref === ref);
}
/** A pílula do bloqueio é um estado, não uma espera em curso: sem reticências. */
function blockLabel(card: OrderCardProjection): string {
  return (card.advance_block_label || "Bloqueado").replace(/…$/, "");
}
/** A tecla impressa no botão (desktop, `pointer: fine`): Enter no item em foco; A no
 *  pedido novo que a tecla aceita. A que não vale ali não se imprime (o R é "atualizar"). */
function printedKey(item: QueueItem): string {
  const gesture = queueGesture(item);
  if (!gesture.primary || gesture.primary.disabled) return "";
  if (gesture.shortcut === "A") return item.card.ref === props.acceptRef ? "A" : "";
  return item.card.ref === props.focusRef ? gesture.shortcut : "";
}
/** "desligar pede gerente" / "ligar pede gerente": a consequência antes do gesto. */
function switchHint(row: { active: boolean; switch?: { requires_manager_approval: boolean } | null }): string {
  if (!row.switch?.requires_manager_approval) return "";
  return row.active ? "desligar pede gerente" : "ligar pede gerente";
}
</script>

<template>
  <div class="grid min-h-0 gap-5 lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_400px]" data-queue-view>
    <!-- a Fila: só o que pede um fato humano, por urgência -->
    <section class="flex min-w-0 flex-col gap-2.5" aria-labelledby="queue-title">
      <div class="flex items-baseline gap-2 border-b border-border pb-2">
        <h2 id="queue-title" class="text-xs uppercase tracking-wider font-semibold">{{ title }}</h2>
        <span class="text-sm font-medium tnum text-muted-foreground" data-queue-count>{{ items.length }}</span>
        <span class="ml-auto hidden text-xs text-muted-foreground sm:inline" data-queue-sort-hint>{{ sortHint }}</span>
      </div>

      <p v-if="!items.length" class="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground" data-queue-empty>
        {{ emptyText }}
      </p>

      <article
        v-for="item in shown"
        :key="item.card.ref"
        class="queue-item grid items-center gap-x-[18px] gap-y-2 rounded-[10px] border bg-card px-4 py-3.5"
        :class="item.card.ref === focusRef ? 'border-primary shadow-[0_0_0_1px_var(--primary)]' : 'border-border'"
        :data-queue-item="item.kind || 'moving'"
        :data-queue-ref="item.card.ref"
        :aria-current="item.card.ref === focusRef || undefined"
        @pointerdown="emit('focus', item.card.ref)"
      >
        <!-- código, tempo na etapa e a meta -->
        <div class="min-w-0">
          <NuxtLink v-if="canOpen" :to="`/${item.card.ref}`" class="block text-2xl tabular-nums font-semibold leading-none hover:underline" :aria-label="`Abrir pedido ${item.card.ref}`">{{ splitRef(item.card.ref).code }}</NuxtLink>
          <p v-else class="text-2xl tabular-nums font-semibold leading-none">{{ splitRef(item.card.ref).code }}</p>
          <p class="mt-1.5 text-base font-semibold tnum" :class="queueToneClass(item.tone)" :data-queue-tone="item.tone" data-queue-time>{{ item.timeLabel }}</p>
          <p class="text-xs text-muted-foreground" data-queue-goal>{{ item.goalLabel }}</p>
        </div>

        <!-- quem, o quê e o estado escrito (a cópia não se corta: quebra a linha) -->
        <div class="flex min-w-0 flex-col gap-1.5">
          <p class="text-sm">
            <span class="font-semibold">{{ queueWho(item.card, channelLabel(item.card.channel_ref)).name }}</span>
            <span class="text-muted-foreground"> · {{ queueWho(item.card, channelLabel(item.card.channel_ref)).rest }}</span>
          </p>
          <p class="text-sm text-foreground/85">{{ item.card.items_summary }}</p>
          <div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <template v-if="undoLine(item.card, nowMs)?.kind === 'auto_ready'">
              <span class="inline-flex h-6 items-center gap-1.5 rounded-full bg-muted px-2 text-xs font-semibold whitespace-nowrap text-muted-foreground" data-queue-auto>
                <Icon name="lucide:sparkles" class="size-3.5" />{{ undoLine(item.card, nowMs)!.label }}<template v-if="undoLine(item.card, nowMs)!.canUndo"> ·
                  <button type="button" class="font-semibold text-foreground underline underline-offset-[3px] disabled:opacity-60" :disabled="isBusy(item.card.ref)" @click="emit('action', item.card.ref, 'undo_ready')">desfazer</button></template>
              </span>
              <span class="text-xs text-muted-foreground">{{ undoLine(item.card, nowMs)!.canUndo ? undoLine(item.card, nowMs)!.detail : `Cozinha concluiu às ${clock(item.card.ready_at_iso)}` }}</span>
            </template>
            <template v-else-if="item.kind === 'confirm'">
              <span class="pill-primary inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-xs font-semibold"><span class="size-1.5 rounded-full bg-current" aria-hidden="true" />Novo</span>
              <span v-if="item.card.confirmation_deadline_iso && confirmationRemainingLabel(item.card.confirmation_deadline_iso, nowMs)" class="text-xs text-muted-foreground" data-queue-deadline>
                {{ item.card.confirmation_action === "cancel" ? "cancela sozinho em" : "aceita sozinho em" }}
                <span class="font-semibold tnum text-foreground">{{ confirmationRemainingLabel(item.card.confirmation_deadline_iso, nowMs) }}</span>
              </span>
            </template>
            <template v-else-if="item.kind === 'blocked'">
              <span class="pill-destructive inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2 text-xs font-semibold whitespace-nowrap" data-queue-block><Icon name="lucide:lock" class="size-3.5" />{{ blockLabel(item.card) }}</span>
              <span class="min-w-0 text-xs text-muted-foreground" data-queue-block-reason>{{ item.card.advance_block_reason }}</span>
            </template>
            <template v-else-if="item.kind === 'station' && readyStation(item.card)">
              <span class="inline-flex h-6 items-center gap-1.5 rounded-full bg-secondary px-2 text-xs font-semibold"><Icon name="lucide:printer" class="size-3.5" />{{ readyStation(item.card)!.station_name }} no papel</span>
              <span class="text-xs text-muted-foreground">{{ item.card.kitchen?.missing_label }}</span>
            </template>
            <template v-else-if="!item.kind">
              <span class="inline-flex h-6 items-center gap-1.5 rounded-full bg-muted px-2 text-xs font-semibold text-muted-foreground" data-queue-moving><span class="size-1.5 rounded-full bg-current" aria-hidden="true" />{{ item.card.status_label }}</span>
              <span class="text-xs text-muted-foreground">nada pede você agora</span>
            </template>
          </div>
          <div v-if="actionError(item.card.ref)" class="flex items-start gap-1.5 rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1.5 text-xs text-destructive" role="alert">
            <span class="min-w-0 flex-1">{{ actionError(item.card.ref) }}</span>
            <button type="button" class="grid size-control shrink-0 place-items-center rounded hover:bg-destructive/20" aria-label="Dispensar aviso" @click="emit('dismiss-error', item.card.ref)">
              <Icon name="lucide:x" class="size-3.5" />
            </button>
          </div>
        </div>

        <!-- pagamento, total e o gesto -->
        <div class="flex min-w-0 flex-col gap-1.5">
          <div class="flex items-baseline justify-between gap-2">
            <span class="min-w-0 text-xs leading-tight text-muted-foreground" data-queue-payment>{{ item.card.change_label || item.card.payment_method_label }}</span>
            <span class="shrink-0 text-base font-semibold tnum">{{ item.card.total_display }}</span>
          </div>
          <template v-if="item.kind === 'station' && readyStation(item.card)">
            <button
              type="button"
              class="inline-flex h-action items-center justify-center gap-2 rounded-md bg-primary text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
              :disabled="isBusy(item.card.ref)"
              data-queue-primary
              @click="emit('station-ready', item.card, readyStation(item.card)!.station_ref)"
            >
              <Icon name="lucide:check" class="size-4" />Pronto de {{ readyStation(item.card)!.station_name }}
              <kbd v-if="item.card.ref === focusRef" class="ml-1 hidden font-mono text-xs opacity-70 pointer-fine:inline" data-queue-key>Enter</kbd>
            </button>
          </template>
          <div v-else-if="queueGesture(item).primary" class="flex gap-1.5">
            <button
              v-if="queueGesture(item).secondary"
              type="button"
              class="inline-flex h-action items-center rounded-md border border-border bg-card px-3 text-sm font-semibold text-muted-foreground transition hover:bg-accent disabled:opacity-60"
              :disabled="isBusy(item.card.ref) || queueGesture(item).secondary!.disabled"
              :title="queueGesture(item).secondary!.reason || undefined"
              data-queue-secondary
              @click="emit('action', item.card.ref, queueGesture(item).secondary!.ref)"
            >{{ queueGesture(item).secondary!.label }}</button>
            <button
              type="button"
              class="inline-flex h-action min-w-0 flex-1 items-center justify-center gap-2 rounded-md text-sm font-semibold transition"
              :class="queueGesture(item).primary!.disabled
                ? 'cursor-default border-2 border-dashed border-border text-muted-foreground'
                : 'bg-primary text-primary-foreground hover:bg-primary/90 active:scale-[0.98] disabled:opacity-60'"
              :disabled="isBusy(item.card.ref) || queueGesture(item).primary!.disabled"
              :title="queueGesture(item).primary!.reason || (queueGesture(item).primary!.verb !== queueGesture(item).primary!.label ? queueGesture(item).primary!.label : undefined)"
              data-queue-primary
              @click="emit('action', item.card.ref, queueGesture(item).primary!.ref)"
            >
              <Icon :name="queueGesture(item).primary!.disabled ? 'lucide:lock' : item.kind === 'dispatch' ? 'lucide:bike' : item.kind === 'handoff' ? 'lucide:hand-platter' : queueGesture(item).primary!.icon" class="size-4 shrink-0" />
              <span>{{ queueGesture(item).primary!.verb }}</span>
              <kbd v-if="printedKey(item)" class="ml-1 hidden font-mono text-xs opacity-70 pointer-fine:inline" data-queue-key>{{ printedKey(item) }}</kbd>
            </button>
          </div>
        </div>
      </article>

      <!-- o excedente vira número: nunca paginação. "Ver todos" abre o recorte Todos. -->
      <button
        v-if="rest.count"
        type="button"
        class="mt-0.5 flex min-h-12 items-center gap-3 rounded-lg border border-dashed border-border px-4 py-2 text-left text-sm font-medium transition hover:bg-accent"
        data-queue-rest
        @click="emit('scope', 'all')"
      >
        <span class="text-base font-semibold tnum">+{{ rest.count }}</span>
        <span class="min-w-0 font-normal text-muted-foreground">{{ rest.text }}</span>
        <span class="ml-auto inline-flex shrink-0 items-center gap-1 font-semibold">Ver todos<Icon name="lucide:chevron-right" class="size-4" /></span>
      </button>
    </section>

    <!-- a coluna de consciência: o agregado, o que o sistema fez e os interruptores -->
    <aside class="flex min-w-0 flex-col gap-4" aria-label="Em andamento e o que o sistema fez">
      <section>
        <div class="mb-2.5 flex items-baseline gap-2 border-b border-border pb-2">
          <h2 class="text-xs uppercase tracking-wider font-semibold">Em andamento</h2><span class="text-sm font-medium tnum text-muted-foreground">{{ progressCount }}</span>
        </div>
        <div class="rounded-lg border border-border bg-card" data-queue-progress>
          <div v-for="line in progress" :key="line.key" class="queue-row">
            <Icon :name="line.icon" class="size-4 text-info" />
            <span class="flex-1 text-sm">{{ line.label }}</span>
            <span
              class="text-xs text-muted-foreground"
              :title="line.key === 'kitchen' && awareness?.kitchen_eta_basis ? `Previsão ${awareness.kitchen_eta_basis}` : undefined"
              :data-queue-progress-detail="line.key"
            >{{ line.detail }}</span>
            <span class="w-6 text-right text-base font-semibold tnum">{{ line.count }}</span>
          </div>
        </div>
      </section>

      <section>
        <div class="mb-2.5 flex items-baseline gap-2 border-b border-border pb-2">
          <Icon name="lucide:sparkles" class="size-3.5 self-center text-muted-foreground" />
          <h2 class="text-xs uppercase tracking-wider font-semibold">O sistema fez</h2>
          <span class="ml-auto text-xs text-muted-foreground">últimos {{ awareness?.system_window_minutes ?? 15 }} min</span>
        </div>
        <div class="rounded-lg border border-border bg-card" data-queue-system>
          <p v-if="!systemActions.length" class="queue-row text-xs text-muted-foreground">Nada automático neste intervalo.</p>
          <div v-for="line in systemActions" :key="`${line.order_ref}-${line.at_iso}`" class="queue-row">
            <span class="w-11 text-sm font-semibold tnum">{{ splitRef(line.order_ref).code }}</span>
            <span class="min-w-0 flex-1 text-sm">{{ line.verb }} <span class="text-muted-foreground">· {{ line.reason }}</span></span>
            <button
              v-if="systemUndoOpen(line) && cardFor(line.order_ref)"
              type="button"
              class="h-9 rounded-md px-3 text-sm font-semibold text-muted-foreground transition hover:bg-accent hover:text-foreground disabled:opacity-60"
              :disabled="isBusy(line.order_ref)"
              data-queue-system-undo
              @click="emit('action', line.order_ref, 'undo_ready')"
            >Desfazer</button>
            <span v-else class="pr-3 text-xs tnum text-muted-foreground">{{ line.at_display }}</span>
          </div>
        </div>
        <p class="mt-2 text-xs leading-snug text-muted-foreground">Aviso ao cliente só sai depois da janela de desfazer. "Marcar pronto" à mão continua no ⋯ do pedido.</p>
      </section>

      <section v-if="outages.length || menuChannels.length">
        <div class="mb-2.5 flex items-baseline gap-2 border-b border-border pb-2">
          <h2 class="text-xs uppercase tracking-wider font-semibold">Agora no cardápio</h2>
          <span v-if="awareness?.menu_outages_more" class="ml-auto text-xs text-muted-foreground">+{{ awareness.menu_outages_more }} fora do ar</span>
        </div>
        <div class="rounded-lg border border-border bg-card" data-queue-menu>
          <div v-for="outage in outages" :key="outage.sku" class="queue-row py-2">
            <span class="min-w-0 flex-1">
              <span class="block text-sm">{{ outage.line }}</span>
              <span class="inline-flex items-center gap-1 text-xs text-muted-foreground"><Icon name="lucide:sparkles" class="size-3" />{{ outage.detail }}</span>
            </span>
          </div>
          <!-- o canal: "iFood ligado · desligar pede gerente · [interruptor]" (v4). O
               interruptor abre o MESMO diálogo de Canais (período, motivo, gerente). -->
          <div v-for="row in menuChannels" :key="row.ref" class="queue-row" data-queue-channel>
            <Icon :name="row.ref === 'ifood' ? 'lucide:bike' : 'lucide:store'" class="size-4 shrink-0 text-muted-foreground" />
            <NuxtLink v-if="awareness?.can_open_channels" :to="row.focus_path" class="min-w-0 flex-1 text-sm hover:underline" :title="`Abrir ${row.name} em Canais`">
              {{ row.name }} {{ row.active ? "ligado" : "desligado" }}
            </NuxtLink>
            <span v-else class="min-w-0 flex-1 text-sm">{{ row.name }} {{ row.active ? "ligado" : "desligado" }}</span>
            <span v-if="switchHint(row)" class="hidden shrink-0 text-xs text-muted-foreground sm:inline" data-queue-channel-hint>{{ switchHint(row) }}</span>
            <UiSwitch
              v-if="row.switch"
              tone="success"
              :model-value="row.active"
              :disabled="switching(row.ref) || !row.switch.enabled"
              :aria-label="row.active ? `${row.name}: ligado. Desligar…` : `${row.name}: desligado. Ligar…`"
              :title="row.switch.enabled ? undefined : row.switch.disabled_reason"
              data-queue-channel-switch
              @update:model-value="emit('switch', row.ref)"
            />
          </div>
        </div>
      </section>
    </aside>
  </div>
</template>

<style scoped>
/* Medidas da prévia (`.qi`, `.srow`, `.tg` de gestor-fila4.html). */
.queue-item {
  grid-template-columns: 92px minmax(0, 1fr) 212px;
}
@media (max-width: 1279.98px) {
  .queue-item {
    grid-template-columns: 80px minmax(0, 1fr) 184px;
  }
}
.queue-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 48px;
  padding: 0 14px;
}
.queue-row + .queue-row {
  border-top: 1px solid var(--border);
}
</style>
