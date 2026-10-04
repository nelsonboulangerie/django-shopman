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
// Só o fato humano é botão. A Supervisão (o quadro de três colunas) segue a um toque
// (alternador e tecla T); o detalhe abre pelo código. Nada aqui decide estado: o fato,
// a meta e o "o sistema fez" vêm do servidor (`order_attention`).
import type { OrderCardProjection, QueueAwarenessProjection } from "~/types/orders";
import type { AffordanceRef } from "~/presentation/board";
import { channelLabel, confirmationRemainingLabel, splitRef, undoLine } from "~/presentation/board";
import { inProgress, queueGesture, queueItems, queueWho, restLine, type QueueTone } from "~/presentation/queue";

const props = defineProps<{
  cards: OrderCardProjection[];
  awareness: QueueAwarenessProjection | null | undefined;
  nowMs: number;
  focusRef: string;
  isBusy: (ref: string) => boolean;
  actionError: (ref: string) => string;
  canOpen: boolean;
}>();
const emit = defineEmits<{
  (e: "action", ref: string, action: AffordanceRef): void;
  (e: "station-ready", card: OrderCardProjection, stationRef: string): void;
  (e: "focus" | "dismiss-error", ref: string): void;
  (e: "show-all"): void;
}>();

const items = computed(() => queueItems(props.cards, props.nowMs));
const progress = computed(() => inProgress(props.cards, props.nowMs));
const rest = computed(() => restLine(progress.value));
const progressCount = computed(() => progress.value.reduce((n, line) => n + line.count, 0));
const systemActions = computed(() => props.awareness?.system_actions ?? []);
const outages = computed(() => props.awareness?.menu_outages ?? []);
const menuChannels = computed(() => props.awareness?.menu_channels ?? []);

function toneClass(tone: QueueTone): string {
  if (tone === "late") return "text-destructive";
  if (tone === "warning") return "text-warning";
  return "text-foreground";
}
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
</script>

<template>
  <div class="grid min-h-0 gap-5 lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_400px]" data-queue-view>
    <!-- a Fila: só o que pede um fato humano, por urgência -->
    <section class="flex min-w-0 flex-col gap-2.5" aria-labelledby="queue-title">
      <div class="flex items-baseline gap-2 border-b border-border pb-2">
        <h2 id="queue-title" class="op-eyebrow">Precisa de você</h2>
        <span class="op-label tnum text-muted-foreground" data-queue-count>{{ items.length }}</span>
        <span class="ml-auto hidden op-micro text-muted-foreground sm:inline">Mais urgente primeiro (tempo contra a meta)</span>
      </div>

      <p v-if="!items.length" class="rounded-lg border border-dashed border-border p-6 text-center op-body text-muted-foreground" data-queue-empty>
        Nada pede você agora.
      </p>

      <article
        v-for="item in items"
        :key="item.card.ref"
        class="queue-item grid items-center gap-x-[18px] gap-y-2 rounded-[10px] border bg-card px-4 py-3.5"
        :class="item.card.ref === focusRef ? 'border-primary shadow-[0_0_0_1px_var(--primary)]' : 'border-border'"
        :data-queue-item="item.kind"
        :data-queue-ref="item.card.ref"
        :aria-current="item.card.ref === focusRef || undefined"
        @pointerdown="emit('focus', item.card.ref)"
      >
        <!-- código, tempo na etapa e a meta -->
        <div class="min-w-0">
          <NuxtLink v-if="canOpen" :to="`/${item.card.ref}`" class="block op-figure leading-none hover:underline" :aria-label="`Abrir pedido ${item.card.ref}`">{{ splitRef(item.card.ref).code }}</NuxtLink>
          <p v-else class="op-figure leading-none">{{ splitRef(item.card.ref).code }}</p>
          <p class="mt-1.5 op-title tnum" :class="toneClass(item.tone)" data-queue-time>{{ item.timeLabel }}</p>
          <p class="op-micro text-muted-foreground" data-queue-goal>{{ item.goalLabel }}</p>
        </div>

        <!-- quem, o quê e o estado escrito -->
        <div class="flex min-w-0 flex-col gap-1.5">
          <p class="truncate op-body">
            <span class="font-semibold">{{ queueWho(item.card, channelLabel(item.card.channel_ref)).name }}</span>
            <span class="text-muted-foreground"> · {{ queueWho(item.card, channelLabel(item.card.channel_ref)).rest }}</span>
          </p>
          <p class="truncate op-body text-foreground/85" :title="item.card.items_summary">{{ item.card.items_summary }}</p>
          <div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <template v-if="undoLine(item.card, nowMs)?.kind === 'auto_ready'">
              <span class="inline-flex h-6 items-center gap-1.5 rounded-full bg-muted px-2 text-xs font-semibold whitespace-nowrap text-muted-foreground" data-queue-auto>
                <Icon name="lucide:sparkles" class="size-3.5" />{{ undoLine(item.card, nowMs)!.label }}<template v-if="undoLine(item.card, nowMs)!.canUndo"> ·
                  <button type="button" class="font-semibold text-foreground underline underline-offset-[3px] disabled:opacity-60" :disabled="isBusy(item.card.ref)" @click="emit('action', item.card.ref, 'undo_ready')">desfazer</button></template>
              </span>
              <span class="op-micro text-muted-foreground">{{ undoLine(item.card, nowMs)!.canUndo ? undoLine(item.card, nowMs)!.detail : `Cozinha concluiu às ${clock(item.card.ready_at_iso)}` }}</span>
            </template>
            <template v-else-if="item.kind === 'confirm'">
              <span class="pill-primary inline-flex h-6 items-center gap-1.5 rounded-full px-2 op-micro font-semibold"><span class="size-1.5 rounded-full bg-current" aria-hidden="true" />Novo</span>
              <span v-if="item.card.confirmation_deadline_iso && confirmationRemainingLabel(item.card.confirmation_deadline_iso, nowMs)" class="op-micro text-muted-foreground">
                {{ item.card.confirmation_action === "cancel" ? "cancela sozinho em" : "aceita sozinho em" }}
                <span class="font-semibold tnum text-foreground">{{ confirmationRemainingLabel(item.card.confirmation_deadline_iso, nowMs) }}</span>
              </span>
            </template>
            <template v-else-if="item.kind === 'blocked'">
              <span class="pill-destructive inline-flex h-6 items-center gap-1.5 rounded-full px-2 op-micro font-semibold"><Icon name="lucide:lock" class="size-3.5" />{{ item.card.advance_block_label || "Bloqueado" }}</span>
              <span class="min-w-0 truncate op-micro text-muted-foreground" :title="item.card.advance_block_reason">{{ item.card.advance_block_reason }}</span>
            </template>
            <template v-else-if="item.kind === 'station' && readyStation(item.card)">
              <span class="inline-flex h-6 items-center gap-1.5 rounded-full bg-secondary px-2 op-micro font-semibold"><Icon name="lucide:printer" class="size-3.5" />{{ readyStation(item.card)!.station_name }} no papel</span>
              <span class="op-micro text-muted-foreground">{{ item.card.kitchen?.missing_label }}</span>
            </template>
            <span v-if="item.card.volumes || item.card.items_count" class="op-micro text-muted-foreground" data-queue-pack>
              {{ item.card.volumes ? `${item.card.volumes} ${item.card.volumes === 1 ? "volume" : "volumes"}` : `${item.card.items_count} ${item.card.items_count === 1 ? "item" : "itens"}` }}
            </span>
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
            <span class="truncate op-micro text-muted-foreground">{{ item.card.change_label || item.card.payment_method_label }}</span>
            <span class="shrink-0 op-title tnum">{{ item.card.total_display }}</span>
          </div>
          <template v-if="item.kind === 'station' && readyStation(item.card)">
            <button
              type="button"
              class="inline-flex h-action items-center justify-center gap-2 rounded-md bg-primary op-label font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
              :disabled="isBusy(item.card.ref)"
              data-queue-primary
              @click="emit('station-ready', item.card, readyStation(item.card)!.station_ref)"
            >
              <Icon name="lucide:check" class="size-4" />Pronto de {{ readyStation(item.card)!.station_name }}
            </button>
          </template>
          <div v-else-if="queueGesture(item).primary" class="flex gap-1.5">
            <button
              v-if="queueGesture(item).secondary"
              type="button"
              class="inline-flex h-action items-center rounded-md border border-border bg-card px-3 op-label font-semibold text-muted-foreground transition hover:bg-accent disabled:opacity-60"
              :disabled="isBusy(item.card.ref) || queueGesture(item).secondary!.disabled"
              :title="queueGesture(item).secondary!.reason || undefined"
              data-queue-secondary
              @click="emit('action', item.card.ref, queueGesture(item).secondary!.ref)"
            >{{ queueGesture(item).secondary!.label }}</button>
            <button
              type="button"
              class="inline-flex h-action min-w-0 flex-1 items-center justify-center gap-2 rounded-md op-label font-semibold transition"
              :class="queueGesture(item).primary!.disabled
                ? 'cursor-default border-2 border-dashed border-border text-muted-foreground'
                : 'bg-primary text-primary-foreground hover:bg-primary/90 active:scale-[0.98] disabled:opacity-60'"
              :disabled="isBusy(item.card.ref) || queueGesture(item).primary!.disabled"
              :title="queueGesture(item).primary!.reason || (queueGesture(item).primary!.verb !== queueGesture(item).primary!.label ? queueGesture(item).primary!.label : undefined)"
              data-queue-primary
              @click="emit('action', item.card.ref, queueGesture(item).primary!.ref)"
            >
              <Icon :name="queueGesture(item).primary!.disabled ? 'lucide:lock' : item.kind === 'dispatch' ? 'lucide:bike' : item.kind === 'handoff' ? 'lucide:hand-platter' : queueGesture(item).primary!.icon" class="size-4 shrink-0" />
              <span class="truncate">{{ queueGesture(item).primary!.verb }}</span>
              <kbd v-if="!queueGesture(item).primary!.disabled && item.card.ref === focusRef" class="ml-1 hidden font-mono op-micro opacity-70 pointer-fine:inline">{{ queueGesture(item).shortcut }}</kbd>
            </button>
          </div>
        </div>
      </article>

      <!-- o excedente vira número: nunca paginação -->
      <button
        v-if="rest.count"
        type="button"
        class="mt-0.5 flex h-12 items-center gap-3 rounded-lg border border-dashed border-border px-4 text-left op-label transition hover:bg-accent"
        data-queue-rest
        @click="emit('show-all')"
      >
        <span class="op-title tnum">+{{ rest.count }}</span>
        <span class="min-w-0 truncate font-normal text-muted-foreground">{{ rest.text }}</span>
        <span class="ml-auto inline-flex shrink-0 items-center gap-1 font-semibold">Ver todos<Icon name="lucide:chevron-right" class="size-4" /></span>
      </button>
    </section>

    <!-- a coluna de consciência: o agregado, o que o sistema fez e os interruptores -->
    <aside class="flex min-w-0 flex-col gap-4" aria-label="Em andamento e o que o sistema fez">
      <section>
        <div class="mb-2.5 flex items-baseline gap-2 border-b border-border pb-2">
          <h2 class="op-eyebrow">Em andamento</h2><span class="op-label tnum text-muted-foreground">{{ progressCount }}</span>
        </div>
        <div class="rounded-lg border border-border bg-card" data-queue-progress>
          <div v-for="line in progress" :key="line.key" class="queue-row">
            <Icon :name="line.icon" class="size-4 text-info" />
            <span class="flex-1 op-body">{{ line.label }}</span>
            <span class="op-micro text-muted-foreground">{{ line.detail }}</span>
            <span class="w-6 text-right op-title tnum">{{ line.count }}</span>
          </div>
        </div>
      </section>

      <section>
        <div class="mb-2.5 flex items-baseline gap-2 border-b border-border pb-2">
          <Icon name="lucide:sparkles" class="size-3.5 self-center text-muted-foreground" />
          <h2 class="op-eyebrow">O sistema fez</h2>
          <span class="ml-auto op-micro text-muted-foreground">últimos {{ awareness?.system_window_minutes ?? 15 }} min</span>
        </div>
        <div class="rounded-lg border border-border bg-card" data-queue-system>
          <p v-if="!systemActions.length" class="queue-row op-micro text-muted-foreground">Nada automático neste intervalo.</p>
          <div v-for="line in systemActions" :key="`${line.order_ref}-${line.at_iso}`" class="queue-row">
            <span class="w-11 op-label font-semibold tnum">{{ splitRef(line.order_ref).code }}</span>
            <span class="min-w-0 flex-1 truncate op-body">{{ line.verb }} <span class="text-muted-foreground">· {{ line.reason }}</span></span>
            <button
              v-if="systemUndoOpen(line) && cardFor(line.order_ref)"
              type="button"
              class="h-9 rounded-md px-3 op-label font-semibold text-muted-foreground transition hover:bg-accent hover:text-foreground disabled:opacity-60"
              :disabled="isBusy(line.order_ref)"
              data-queue-system-undo
              @click="emit('action', line.order_ref, 'undo_ready')"
            >Desfazer</button>
            <span v-else class="pr-3 op-micro tnum text-muted-foreground">{{ line.at_display }}</span>
          </div>
        </div>
        <p class="mt-2 op-micro leading-snug text-muted-foreground">Aviso ao cliente só sai depois da janela de desfazer. "Marcar pronto" à mão continua no ⋯ do pedido.</p>
      </section>

      <section v-if="outages.length || menuChannels.length">
        <div class="mb-2.5 flex items-baseline gap-2 border-b border-border pb-2">
          <h2 class="op-eyebrow">Agora no cardápio</h2>
          <span v-if="awareness?.menu_outages_more" class="ml-auto op-micro text-muted-foreground">+{{ awareness.menu_outages_more }} fora do ar</span>
        </div>
        <div class="rounded-lg border border-border bg-card" data-queue-menu>
          <div v-for="outage in outages" :key="outage.sku" class="queue-row py-2">
            <span class="min-w-0 flex-1">
              <span class="block op-body">{{ outage.line }}</span>
              <span class="inline-flex items-center gap-1 op-micro text-muted-foreground"><Icon name="lucide:sparkles" class="size-3" />{{ outage.detail }}</span>
            </span>
          </div>
          <template v-for="row in menuChannels" :key="row.ref">
            <NuxtLink v-if="awareness?.can_open_channels" :to="row.focus_path" class="queue-row transition hover:bg-accent" :title="`Abrir ${row.name} em Canais`" data-queue-channel>
              <Icon :name="row.ref === 'ifood' ? 'lucide:bike' : 'lucide:store'" class="size-4 text-muted-foreground" />
              <span class="min-w-0 flex-1 truncate op-body" :title="row.line">{{ row.name }}</span>
              <span class="h-6 rounded-full px-2 op-micro leading-6 font-semibold" :class="row.active ? 'pill-success' : 'bg-muted text-muted-foreground'">{{ row.active ? "ligado" : "desligado" }}</span>
              <Icon name="lucide:chevron-right" class="size-4 text-muted-foreground" />
            </NuxtLink>
            <div v-else class="queue-row" data-queue-channel>
              <Icon :name="row.ref === 'ifood' ? 'lucide:bike' : 'lucide:store'" class="size-4 text-muted-foreground" />
              <span class="min-w-0 flex-1 truncate op-body" :title="row.line">{{ row.name }}</span>
              <span class="h-6 rounded-full px-2 op-micro leading-6 font-semibold" :class="row.active ? 'pill-success' : 'bg-muted text-muted-foreground'">{{ row.active ? "ligado" : "desligado" }}</span>
            </div>
          </template>
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
