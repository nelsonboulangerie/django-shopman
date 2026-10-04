<script setup lang="ts">
// PDV › Ajustes › Salão (V5-SALAO, prévia v4 `salao-mesas4.html`): o salão desenhado
// uma vez e mudado quando muda o mobiliário. Decisão do dono (04/10/2026): quem opera
// o PDV pode editar, e toda mudança fica registrada (quem, quando, o quê).
//
// Do tablet para cima, a planta: paleta (formas e áreas) à esquerda, a planta com as
// áreas no meio, o painel da mesa escolhida à direita e, no pé, o total que o B.I. usa
// ("N lugares na capacidade oficial · M extras de dia cheio") com o que mudou e UM
// Salvar, com a consequência no rótulo. No tablet a paleta deita numa faixa acima da
// planta. No celular a planta vira lista editável (`PosSeatingList`), com o mesmo
// painel numa folha de baixo.
//
// Teclado: Ctrl S salva, Ctrl Z desfaz, Ctrl Shift Z refaz, setas movem a mesa
// escolhida (Shift move de 1 em 1), Del tira do salão, Esc solta a escolha.
import { useEventListener } from "@vueuse/core";
import { toast } from "vue-sonner";

import {
  GRID,
  NO_AREA,
  ZOOM_STEPS,
  areaSummaries,
  snap,
  totals,
} from "~/presentation/seating";
import type { SpotShape } from "~/types/seating";

useHead({ title: "Salão" });

const { pos, tabs, pending: posPending, refresh: refreshPos } = await usePosTerminal();
const { operator: activeOperator, lock } = useOperatorLock("cashman.operate_pos");
const seating = usePosSeating();
const confirm = useConfirm();

const customerDisplayWindow = useCustomerDisplayWindow();
function openCustomerDisplay() {
  if (!customerDisplayWindow.open()) toast.error("O navegador bloqueou a Tela do Cliente.", {
    description: "Permita pop-ups para este site e tente novamente.",
  });
}

// Celular x tablet x computador: só no navegador. Até montar, o servidor desenha a
// planta (tablet e computador); o celular troca para a lista ao montar.
const mounted = ref(false);
onMounted(() => {
  mounted.value = true;
});
const phoneQuery = useMediaQuery("(max-width: 767.98px)");
const wideQuery = useMediaQuery("(min-width: 1280px)");
const largeQuery = useMediaQuery("(min-width: 1024px)");
const isPhone = computed(() => mounted.value && phoneQuery.value);
const isWide = computed(() => !mounted.value || wideQuery.value);
/** Tablet em pé: o painel da mesa desce para baixo da planta, e só aparece com mesa escolhida. */
const isLarge = computed(() => !mounted.value || largeQuery.value);

const plan = ref<{ toPlan: (x: number, y: number) => { x: number; y: number } | null; visibleCenter: () => { x: number; y: number }; fitZoom: () => number } | null>(null);
const zoom = ref(1);
const snapEnabled = ref(true);
const historyOpen = ref(false);
const menuOpen = ref(false);
const sheetOpen = ref(false);

const summaries = computed(() => areaSummaries(seating.spots.value, seating.areas.value));
const areaNames = computed(() => summaries.value.map((area) => area.name).filter((name) => name !== NO_AREA));
const activeArea = ref("");
watch(summaries, (list) => {
  if (!list.some((area) => area.name === activeArea.value)) activeArea.value = list[0]?.name ?? "";
}, { immediate: true });
watch(() => seating.selected.value?.area, (area) => {
  if (area) activeArea.value = area;
});

const sums = computed(() => totals(seating.spots.value));
const openTabs = computed(() => tabs.value.filter((tab) => tab.state === "in_use").length);
const changedKeys = computed(() => new Set(seating.changes.value.map((change) => change.key)));
const zoomLabel = computed(() => `${Math.round(zoom.value * 100)}%`);

// Pinça no tablet (v4: "No tablet: pinça para zoom"): o zoom acompanha os dedos
// entre o menor e o maior passo dos botões.
let pinchBase = 1;
function onPinch(ratio: number, phase: "start" | "move") {
  if (phase === "start") {
    pinchBase = zoom.value;
    return;
  }
  const min = ZOOM_STEPS[0] ?? 0.5;
  const max = ZOOM_STEPS[ZOOM_STEPS.length - 1] ?? 1.5;
  zoom.value = Math.round(Math.min(max, Math.max(min, pinchBase * ratio)) * 100) / 100;
}
// A comanda aberta em cada mesa (vínculo opcional comanda × mesa).
const occupiedSpots = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  for (const [ref, tab] of Object.entries(seating.data.value?.open_tabs || {})) map[ref] = tab.tab_display || tab.tab_ref;
  return map;
});
function onAddFixture(kind: "showcase" | "entrance") {
  const label = seating.data.value?.fixture_kinds?.find((item) => item.value === kind)?.label || (kind === "showcase" ? "Vitrine e caixa" : "Entrada");
  seating.addFixture(kind, label, plan.value?.visibleCenter() ?? { x: 200, y: 200 });
}

function stepZoom(direction: 1 | -1) {
  const index = ZOOM_STEPS.findIndex((step) => step >= zoom.value - 0.001);
  const next = ZOOM_STEPS[Math.min(ZOOM_STEPS.length - 1, Math.max(0, (index < 0 ? ZOOM_STEPS.length - 1 : index) + direction))];
  if (next) zoom.value = next;
}

// Zoom inicial: a planta inteira cabe na tela do tablet (nunca acima de 100%).
let fitted = false;
watch([() => seating.spots.value.length, plan], async () => {
  if (fitted || !seating.spots.value.length || !plan.value || isPhone.value) return;
  await nextTick();
  const fit = plan.value.fitZoom();
  fitted = true;
  if (fit < 1) zoom.value = [...ZOOM_STEPS].reverse().find((step) => step <= fit) ?? ZOOM_STEPS[0]!;
});

function areaForNew() {
  return activeArea.value && activeArea.value !== NO_AREA ? activeArea.value : "";
}

// ── pôr mesa nova: arrastar da paleta ou tocar ───────────────────────────
const ghost = ref<{ shape: SpotShape; x: number; y: number } | null>(null);
function onGrab(shape: SpotShape, event: PointerEvent) {
  if (event.button !== 0) return;
  event.preventDefault();
  const startX = event.clientX;
  const startY = event.clientY;
  let moved = false;
  const stopMove = useEventListener(window, "pointermove", (move: PointerEvent) => {
    if (!moved && Math.hypot(move.clientX - startX, move.clientY - startY) < 6) return;
    moved = true;
    ghost.value = { shape, x: move.clientX, y: move.clientY };
  });
  const finish = (up: PointerEvent) => {
    stopMove();
    stopUp();
    stopCancel();
    ghost.value = null;
    if (!plan.value) return;
    if (!moved) {
      seating.add(shape, undefined, areaForNew());
      return;
    }
    const point = plan.value.toPlan(up.clientX, up.clientY);
    if (point) seating.add(shape, point, areaForNew());
  };
  const stopUp = useEventListener(window, "pointerup", finish);
  const stopCancel = useEventListener(window, "pointercancel", () => {
    stopMove();
    stopUp();
    stopCancel();
    ghost.value = null;
  });
}

function addFromList(shape: SpotShape, area: string) {
  seating.add(shape, undefined, area);
  sheetOpen.value = true;
}
function selectFromList(key: string) {
  seating.selectedKey.value = key;
  sheetOpen.value = true;
}

function onAddArea(name: string) {
  if (seating.addArea(name)) activeArea.value = name;
}

function onMove(key: string, x: number, y: number) {
  seating.update(key, { x, y }, { checkpoint: false });
}

async function removeSelected() {
  const key = seating.selectedKey.value;
  if (!key) return;
  const spot = seating.selected.value;
  const tab = spot?.ref ? occupiedSpots.value[spot.ref] : "";
  // Mesa com comanda aberta: o aviso vem antes (v4 "Mesa 4 tem comanda aberta agora").
  if (spot && tab) {
    const agreed = await confirm({
      tone: "danger",
      title: `${spot.label} tem comanda aberta agora`,
      description: `A comanda ${tab} continua aberta e só perde a mesa. Tirar ${spot.label} do salão a partir de hoje?`,
      confirmLabel: "Tirar do salão",
    });
    if (!agreed) return;
  }
  seating.remove(key);
  sheetOpen.value = false;
}

async function discard() {
  if (!seating.dirty.value) return;
  const agreed = await confirm({
    tone: "danger",
    title: "Descartar as mudanças do salão?",
    description: seating.summary.value,
    confirmLabel: "Descartar",
    cancelLabel: "Continuar editando",
  });
  if (agreed) seating.discard();
}

onBeforeRouteLeave(async () => {
  if (!seating.dirty.value) return true;
  return await confirm({
    tone: "danger",
    title: "Sair sem salvar o salão?",
    description: `${seating.summary.value}. Fora daqui elas se perdem.`,
    confirmLabel: "Sair sem salvar",
    cancelLabel: "Continuar editando",
  });
});

function isTyping(target: EventTarget | null) {
  const element = target as HTMLElement | null;
  if (!element) return false;
  return element.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName);
}

useEventListener(window, "keydown", (event: KeyboardEvent) => {
  const mod = event.ctrlKey || event.metaKey;
  const key = event.key.toLowerCase();
  if (mod && key === "s") {
    event.preventDefault();
    void seating.save();
    return;
  }
  if (isTyping(event.target)) return;
  if (mod && key === "z") {
    event.preventDefault();
    if (event.shiftKey) seating.redo();
    else seating.undo();
    return;
  }
  if (mod && key === "y") {
    event.preventDefault();
    seating.redo();
    return;
  }
  const spot = seating.selected.value;
  if (!spot) return;
  if (event.key === "Escape") {
    seating.selectedKey.value = null;
    return;
  }
  if (event.key === "Delete") {
    event.preventDefault();
    removeSelected();
    return;
  }
  const step = event.shiftKey || !snapEnabled.value ? 1 : GRID;
  const moves: Record<string, [number, number]> = {
    ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step],
  };
  const delta = moves[event.key];
  if (!delta) return;
  event.preventDefault();
  const snapped = !event.shiftKey && snapEnabled.value;
  seating.update(spot.key, { x: snap(spot.x + delta[0], snapped), y: snap(spot.y + delta[1], snapped) });
});

const saveHint = "vale a partir de hoje; o passado não muda";
</script>

<template>
  <main class="flex min-h-dvh flex-col bg-background text-foreground md:h-[100dvh] md:min-h-0 md:flex-row md:overflow-hidden">
    <PosFunctionRail
      v-if="pos"
      :pos="pos"
      :has-open-cash-session="pos.has_open_cash_session"
      :operator-name="activeOperator?.name || ''"
      :pending="posPending"
      view="settings"
      @board="navigateTo('/')"
      @cash="navigateTo('/session')"
      @display="openCustomerDisplay"
      @lock="lock()"
      @refresh="refreshPos()"
    />

    <div class="flex min-w-0 flex-1 flex-col md:min-h-0 md:overflow-hidden">
      <OperatorPageHeader title="Salão">
        <template v-if="!isPhone" #lead>
          <span class="hidden items-center gap-1 op-label text-muted-foreground md:inline-flex" data-seating-crumb>
            Ajustes<Icon name="lucide:chevron-right" class="size-4" aria-hidden="true" />
          </span>
        </template>
        <template #status>
          <span class="hidden op-micro text-muted-foreground lg:inline">mesas e lugares da casa</span>
        </template>
        <template #actions>
          <div class="flex h-control items-center rounded-md border border-border" role="group" aria-label="Desfazer e refazer">
            <button
              type="button"
              class="grid size-control place-items-center border-r border-border disabled:text-muted-foreground/50"
              :disabled="!seating.canUndo.value"
              aria-label="Desfazer (Ctrl Z)"
              title="Desfazer (Ctrl Z)"
              data-seating-undo
              @click="seating.undo()"
            >
              <Icon name="lucide:undo-2" class="size-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              class="grid size-control place-items-center disabled:text-muted-foreground/50"
              :disabled="!seating.canRedo.value"
              aria-label="Refazer (Ctrl Shift Z)"
              title="Refazer (Ctrl Shift Z)"
              data-seating-redo
              @click="seating.redo()"
            >
              <Icon name="lucide:redo-2" class="size-4" aria-hidden="true" />
            </button>
          </div>
          <template v-if="!isPhone">
            <div class="flex h-control items-center rounded-md border border-border" role="group" aria-label="Zoom da planta">
              <button type="button" class="grid size-control place-items-center border-r border-border" aria-label="Menos zoom" @click="stepZoom(-1)">
                <Icon name="lucide:minus" class="size-4" aria-hidden="true" />
              </button>
              <span class="px-3 op-label tabular-nums" aria-live="polite" data-seating-zoom>{{ zoomLabel }}</span>
              <button type="button" class="grid size-control place-items-center border-l border-border" aria-label="Mais zoom" @click="stepZoom(1)">
                <Icon name="lucide:plus" class="size-4" aria-hidden="true" />
              </button>
            </div>
            <button
              type="button"
              class="inline-flex h-control items-center gap-2 rounded-md border px-3 op-label font-semibold transition"
              :class="snapEnabled ? 'border-primary bg-primary/10' : 'border-border text-muted-foreground'"
              :aria-pressed="snapEnabled"
              data-seating-snap
              @click="snapEnabled = !snapEnabled"
            >
              <Icon name="lucide:grid-3x3" class="size-4" aria-hidden="true" />Encaixar na grade
            </button>
          </template>
          <UiPopover v-model:open="menuOpen">
            <UiPopoverTrigger as-child>
              <button
                type="button"
                class="grid size-control place-items-center rounded-md border border-border transition hover:bg-accent"
                aria-label="Mais: histórico do salão, recarregar"
                title="Mais: histórico do salão, recarregar"
                data-seating-menu
              >
                <Icon name="lucide:ellipsis" class="size-5" aria-hidden="true" />
              </button>
            </UiPopoverTrigger>
            <UiPopoverContent align="end" class="w-60 p-1.5">
              <button
                type="button"
                class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body hover:bg-accent"
                data-seating-history-open
                @click="menuOpen = false; historyOpen = true"
              >
                <Icon name="lucide:history" class="size-4 text-muted-foreground" aria-hidden="true" />Histórico do salão
              </button>
              <button
                type="button"
                class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body hover:bg-accent"
                @click="menuOpen = false; seating.refresh()"
              >
                <Icon name="lucide:refresh-cw" class="size-4 text-muted-foreground" aria-hidden="true" />Recarregar o salão
              </button>
            </UiPopoverContent>
          </UiPopover>
        </template>
        <template #below>
          <PosSettingsTabs />
        </template>
      </OperatorPageHeader>

      <div v-if="seating.error.value && !seating.data.value" class="grid flex-1 place-items-center p-6 text-center">
        <div class="flex max-w-sm flex-col items-center gap-3">
          <p class="op-title">Não deu para ler o salão.</p>
          <p class="op-body text-muted-foreground">{{ httpErrorMessage(seating.error.value, "Confira a conexão e tente de novo.") }}</p>
          <UiButton @click="seating.refresh()">Tentar de novo</UiButton>
        </div>
      </div>
      <div v-else-if="!seating.data.value" class="grid flex-1 place-items-center p-6">
        <p class="op-body text-muted-foreground">Lendo o salão…</p>
      </div>

      <template v-else>
        <!-- celular: lista editável -->
        <div v-if="isPhone" class="flex-1">
          <PosSeatingList
            :spots="seating.spots.value"
            :areas="summaries"
            :changed-keys="changedKeys"
            @select="selectFromList"
            @add="addFromList"
          />
          <UiSheet :open="sheetOpen && Boolean(seating.selected.value)" @update:open="(value) => (sheetOpen = value)">
            <UiSheetContent side="bottom" class="max-h-[88dvh] gap-0 rounded-t-xl p-0" :title="undefined">
              <template #header>
                <UiSheetTitle class="sr-only">Mesa</UiSheetTitle>
                <UiSheetDescription class="sr-only">Lugares, forma, área e capacidade da mesa.</UiSheetDescription>
              </template>
              <template #content>
                <PosSeatingSpotPanel
                  v-if="seating.selected.value"
                  :spot="seating.selected.value"
                  :original="seating.selectedOriginal.value"
                  :areas="areaNames"
                  :today-label="seating.data.value.today_label"
                  :max-seats="seating.data.value.max_seats"
                  :open-tabs="openTabs"
                  :spot-tab="seating.selected.value?.ref ? occupiedSpots[seating.selected.value.ref] : ''"
                  @update="(patch) => seating.update(seating.selected.value!.key, patch)"
                  @rotate="seating.rotate(seating.selected.value!.key)"
                  @duplicate="seating.duplicate(seating.selected.value!.key)"
                  @remove="removeSelected"
                />
              </template>
            </UiSheetContent>
          </UiSheet>
        </div>

        <!-- tablet e computador: a planta -->
        <div v-else class="flex min-h-0 flex-1 flex-col lg:flex-row">
          <PosSeatingPalette
            v-if="isWide"
            :areas="summaries"
            :active-area="activeArea"
            @grab="onGrab"
            @select-area="(name) => (activeArea = name)"
            @add-area="onAddArea"
          />
          <div class="flex min-h-0 min-w-0 flex-1 flex-col">
            <PosSeatingPalette
              v-if="!isWide"
              layout="strip"
              :areas="summaries"
              :active-area="activeArea"
              @grab="onGrab"
              @select-area="(name) => (activeArea = name)"
              @add-area="onAddArea"
              @add-fixture="onAddFixture"
            />
            <PosSeatingPlan
              ref="plan"
              :spots="seating.spots.value"
              :selected-key="seating.selectedKey.value"
              :zoom="zoom"
              :snap-enabled="snapEnabled"
              :fixtures="seating.fixtures.value"
              :occupied="occupiedSpots"
              @select="(key) => (seating.selectedKey.value = key)"
              @move-start="seating.checkpoint()"
              @move="onMove"
              @rotate="seating.rotate"
              @fixture-move-start="seating.checkpoint()"
              @move-fixture="seating.moveFixture"
              @rotate-fixture="seating.rotateFixture"
              @remove-fixture="seating.removeFixture"
              @pinch="onPinch"
            />
          </div>
          <aside
            v-if="isLarge || seating.selected.value"
            class="flex max-h-[50%] min-h-0 shrink-0 flex-col border-t border-border bg-card lg:max-h-none lg:w-[300px] lg:border-t-0 lg:border-l xl:w-[340px]"
            aria-label="Mesa escolhida"
          >
            <PosSeatingSpotPanel
              v-if="seating.selected.value"
              :key="seating.selected.value.key"
              :spot="seating.selected.value"
              :original="seating.selectedOriginal.value"
              :areas="areaNames"
              :today-label="seating.data.value.today_label"
              :max-seats="seating.data.value.max_seats"
              :open-tabs="openTabs"
              :spot-tab="seating.selected.value?.ref ? occupiedSpots[seating.selected.value.ref] : ''"
              @update="(patch) => seating.update(seating.selected.value!.key, patch)"
              @rotate="seating.rotate(seating.selected.value!.key)"
              @duplicate="seating.duplicate(seating.selected.value!.key)"
              @remove="removeSelected"
            />
            <div v-else class="flex flex-1 flex-col gap-2 p-4" data-seating-panel-empty>
              <p class="op-title">Escolha uma mesa</p>
              <p class="op-body text-muted-foreground">
                Toque numa mesa da planta para mudar lugares, forma, área ou a conta na capacidade oficial. Para pôr uma nova, arraste uma forma da paleta.
              </p>
            </div>
          </aside>
        </div>

        <!-- rodapé: o total que o B.I. usa, o que mudou e um Salvar só -->
        <footer
          class="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-t border-border bg-card px-4 py-3 max-md:sticky max-md:bottom-16 max-md:z-20 lg:h-[68px] lg:flex-nowrap lg:py-0"
          data-seating-footer
        >
          <div class="flex shrink-0 flex-wrap items-baseline gap-x-2 md:flex-nowrap md:whitespace-nowrap">
            <span class="op-figure tabular-nums" data-seating-capacity-total>{{ sums.capacitySeats }}</span>
            <span class="op-label">lugares na capacidade oficial</span>
            <span class="op-label text-muted-foreground">· <b class="text-foreground tabular-nums">{{ sums.extraSeats }}</b> extras de dia cheio</span>
          </div>
          <span
            v-if="seating.summary.value"
            class="inline-flex h-6 max-w-full min-w-0 shrink items-center gap-1.5 overflow-hidden rounded-full bg-primary/12 px-2 op-micro font-semibold text-primary"
            :title="seating.summary.value"
            data-seating-changes
          >
            <span class="size-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" />
            <span class="min-w-0 truncate">{{ seating.summary.value }}</span>
          </span>
          <div class="hidden flex-1 lg:block" />
          <div class="flex w-full items-center gap-2 lg:w-auto lg:shrink-0">
            <button
              type="button"
              class="h-action rounded-md px-4 op-label text-muted-foreground disabled:opacity-50"
              :disabled="!seating.dirty.value || seating.saving.value"
              data-seating-discard
              @click="discard"
            >Descartar</button>
            <button
              type="button"
              class="inline-flex h-action min-w-0 flex-1 items-center justify-center gap-2 rounded-md bg-primary px-5 op-label font-semibold text-primary-foreground disabled:opacity-50 lg:flex-none"
              :disabled="!seating.dirty.value || seating.saving.value"
              data-seating-save
              @click="seating.save()"
            >
              <Icon :name="seating.saving.value ? 'lucide:loader-circle' : 'lucide:check'" class="size-4 shrink-0" :class="seating.saving.value ? 'animate-spin' : ''" aria-hidden="true" />
              Salvar salão
              <span class="hidden font-normal whitespace-nowrap opacity-85 xl:inline">({{ saveHint }})</span>
              <span class="hidden font-normal whitespace-nowrap opacity-85 md:inline xl:hidden">(de hoje em diante)</span>
              <kbd class="ml-1 hidden rounded bg-primary-foreground/20 px-1.5 op-micro xl:inline">Ctrl S</kbd>
            </button>
          </div>
          <p v-if="seating.dirty.value" class="w-full op-micro text-muted-foreground md:hidden">Salvar {{ saveHint }}.</p>
        </footer>
      </template>

      <PosFunctionRail place="bar" :operator-name="activeOperator?.name || ''" @board="navigateTo('/')" @cash="navigateTo('/session')" @display="openCustomerDisplay" @lock="lock()" />
    </div>

    <PosSeatingHistory v-model:open="historyOpen" :entries="seating.data.value?.history ?? []" />

    <!-- a forma que vai sendo arrastada da paleta -->
    <div
      v-if="ghost"
      class="pointer-events-none fixed z-50 -translate-x-1/2 -translate-y-1/2 border-2 border-primary bg-primary/15 shadow-lg"
      :class="{
        'size-14 rounded-full': ghost.shape === 'round',
        'size-[70px] rounded-md': ghost.shape === 'square',
        'h-[60px] w-[120px] rounded-md': ghost.shape === 'long',
        'size-10 rounded-full': ghost.shape === 'stool',
      }"
      :style="{ left: `${ghost.x}px`, top: `${ghost.y}px` }"
      aria-hidden="true"
    />
  </main>
</template>
