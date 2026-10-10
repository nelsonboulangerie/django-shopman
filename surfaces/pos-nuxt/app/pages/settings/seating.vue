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

import {
  GRID,
  NO_AREA,
  ZOOM_STEPS,
  areaSummaries,
  snap,
  totals,
} from "~/presentation/seating";
import type { SpotShape } from "~/types/seating";
import type { OperatorActionBarAction } from "../../../../operator-kit/app/presentation/actionBar";
import type { OperatorHeaderAction } from "../../../../operator-kit/app/presentation/pageHeader";

useHead({ title: "Salão" });

const { tabs } = await usePosTerminal();
const seating = usePosSeating();
const confirm = useConfirm();

// Celular x tablet x computador, pela régua da suíte (`useScreen`): até hidratar ela
// responde "mesa", então o servidor desenha a planta e o celular troca para a lista.
const screen = useScreen();
const isPhone = computed(() => screen.belowMd.value);
const isWide = computed(() => !screen.belowXl.value);
/** Tablet em pé: o painel da mesa desce para baixo da planta, e só aparece com mesa escolhida. */
const isLarge = computed(() => !screen.belowLg.value);

const plan = ref<{ toPlan: (x: number, y: number) => { x: number; y: number } | null; visibleCenter: () => { x: number; y: number }; fitZoom: () => number } | null>(null);
const zoom = ref(1);
const snapEnabled = ref(true);
const historyOpen = ref(false);
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

// O ⋯ do cabeçalho (o mesmo de toda a suíte): o histórico e recarregar.
const headerActions = computed<OperatorHeaderAction[]>(() => [
  { label: "Histórico do salão", icon: "i-lucide-history", onSelect: () => { historyOpen.value = true; } },
  { label: "Recarregar o salão", icon: "i-lucide-refresh-cw", onSelect: () => void seating.refresh() },
]);
// A ação do momento no celular e no tablet (abaixo de `lg`): Salvar, com Descartar ao
// lado. A linha de contexto diz o que muda; sem mudança, a capacidade de hoje.
const saveAction = computed<OperatorActionBarAction>(() => ({
  label: "Salvar salão",
  icon: "i-lucide-check",
  loading: seating.saving.value,
  disabled: !seating.dirty.value || seating.saving.value,
  reason: seating.dirty.value ? "" : "Nada mudou no salão.",
  onSelect: () => void seating.save(),
}));
const discardAction = computed<OperatorActionBarAction>(() => ({
  label: "Descartar",
  disabled: !seating.dirty.value || seating.saving.value,
  onSelect: () => void discard(),
}));
const barContext = computed(() =>
  seating.dirty.value
    ? `${seating.summary.value}. Vale de hoje em diante.`
    : `Capacidade oficial · ${sums.value.extraSeats} extras de dia cheio`,
);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-seating-screen>
    <div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <OperatorPageHeader
        title="Salão"
        :actions="headerActions"
        actions-label="Mais ações do Salão"
      >
        <template v-if="!isPhone" #lead>
          <span class="hidden items-center gap-1 op-label text-muted-foreground md:inline-flex" data-seating-crumb>
            Ajustes<Icon name="lucide:chevron-right" class="size-4" aria-hidden="true" />
          </span>
        </template>
        <template #status>
          <span class="hidden op-micro text-muted-foreground lg:inline">mesas e lugares da casa</span>
        </template>
        <template #actions>
          <NuxtFieldGroup aria-label="Desfazer e refazer">
            <NuxtButton
              icon="i-lucide-undo-2"
              color="neutral"
              variant="outline"
              square
              :disabled="!seating.canUndo.value"
              aria-label="Desfazer (Ctrl Z)"
              title="Desfazer (Ctrl Z)"
              data-seating-undo
              @click="seating.undo()"
            />
            <NuxtButton
              icon="i-lucide-redo-2"
              color="neutral"
              variant="outline"
              square
              :disabled="!seating.canRedo.value"
              aria-label="Refazer (Ctrl Shift Z)"
              title="Refazer (Ctrl Shift Z)"
              data-seating-redo
              @click="seating.redo()"
            />
          </NuxtFieldGroup>
          <NuxtFieldGroup v-if="!isPhone" aria-label="Zoom da planta">
            <NuxtButton icon="i-lucide-minus" color="neutral" variant="outline" square aria-label="Menos zoom" @click="stepZoom(-1)" />
            <span
              class="inline-flex items-center border-y border-default px-3 op-label tabular-nums"
              aria-live="polite"
              data-seating-zoom
            >{{ zoomLabel }}</span>
            <NuxtButton icon="i-lucide-plus" color="neutral" variant="outline" square aria-label="Mais zoom" @click="stepZoom(1)" />
          </NuxtFieldGroup>
          <NuxtButton
            v-if="!isPhone"
            icon="i-lucide-grid-3x3"
            label="Encaixar na grade"
            color="neutral"
            variant="outline"
            active-color="primary"
            active-variant="solid"
            :active="snapEnabled"
            :aria-pressed="snapEnabled"
            data-seating-snap
            @click="snapEnabled = !snapEnabled"
          />
        </template>
        <template #filters-primary>
          <PosSettingsTabs />
        </template>
      </OperatorPageHeader>

      <div v-if="seating.error.value && !seating.data.value" class="p-4 md:p-6">
        <OperatorScreenState state="error" what="o salão" @retry="seating.refresh()" />
      </div>
      <div v-else-if="!seating.data.value" class="p-4 md:p-6">
        <OperatorScreenState state="loading" what="o salão" />
      </div>

      <template v-else>
        <!-- celular: lista editável -->
        <div v-if="isPhone" class="min-h-0 flex-1 overflow-y-auto">
          <PosSeatingList
            :spots="seating.spots.value"
            :areas="summaries"
            :changed-keys="changedKeys"
            @select="selectFromList"
            @add="addFromList"
          />
          <NuxtDrawer
            :open="sheetOpen && Boolean(seating.selected.value)"
            :title="seating.selected.value?.label || 'Mesa'"
            description="Lugares, forma, área e capacidade da mesa."
            :ui="{ header: 'sr-only', body: 'p-0 sm:p-0' }"
            data-seating-sheet
            @update:open="(value) => (sheetOpen = value)"
          >
            <template #body>
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
          </NuxtDrawer>
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

        <!-- Do computador (lg): o total que o B.I. usa, o que mudou e um Salvar só, em
             fluxo no pé da tela. Abaixo de lg, a mesma ação mora no OperatorActionBar. -->
        <footer
          class="flex h-[68px] shrink-0 items-center gap-x-4 border-t border-border bg-card px-4 max-lg:hidden"
          data-seating-footer
        >
          <div class="flex shrink-0 items-baseline gap-x-2 whitespace-nowrap">
            <span class="op-figure tabular-nums" data-seating-capacity-total>{{ sums.capacitySeats }}</span>
            <span class="op-label">lugares na capacidade oficial</span>
            <span class="op-label text-muted-foreground">· <b class="text-foreground tabular-nums">{{ sums.extraSeats }}</b> extras de dia cheio</span>
          </div>
          <NuxtBadge
            v-if="seating.summary.value"
            color="primary"
            class="min-w-0 shrink"
            :title="seating.summary.value"
            data-seating-changes
          >
            <span class="min-w-0 truncate">{{ seating.summary.value }}</span>
          </NuxtBadge>
          <div class="flex-1" />
          <div class="flex shrink-0 items-center gap-2">
            <NuxtButton
              label="Descartar"
              color="neutral"
              variant="ghost"
              :disabled="!seating.dirty.value || seating.saving.value"
              data-seating-discard
              @click="discard"
            />
            <NuxtButton
              icon="i-lucide-check"
              :loading="seating.saving.value"
              :disabled="!seating.dirty.value || seating.saving.value"
              data-seating-save
              @click="seating.save()"
            >
              Salvar salão
              <span class="hidden font-normal whitespace-nowrap opacity-85 xl:inline">({{ saveHint }})</span>
              <span class="font-normal whitespace-nowrap opacity-85 xl:hidden">(de hoje em diante)</span>
              <OperatorKbd class="ml-1 hidden xl:inline-flex">Ctrl S</OperatorKbd>
            </NuxtButton>
          </div>
        </footer>
        <OperatorActionBar
          :action="saveAction"
          :secondary="discardAction"
          :context-label="barContext"
          :context-value="`${sums.capacitySeats} lugares`"
          label="Salvar o salão"
          data-seating-action-bar
        />
      </template>
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
