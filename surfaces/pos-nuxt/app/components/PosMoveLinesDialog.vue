<script setup lang="ts">
import type { POSCartItem, POSTabProjection } from "~/types/pos";
import {
  availableMoveModes,
  buildMovePayload,
  canSubmitMove,
  defaultMoveTarget,
  freezesPriceOnMove,
  initialMoveMode,
  type MoveMode,
  type MovePayload,
  moveLineId,
  moveLineView,
  modeNeedsSelection,
  moveSubmitLabel,
  moveTargetOptions,
  selectedLineIds,
} from "~/presentation/moveLines";
import { tabTitleView } from "~/presentation/tabTitle";

const props = defineProps<{
  open: boolean;
  tabDisplay: string;
  items: POSCartItem[];
  suggestedSplitRef: string;
  otherTabs: POSTabProjection[];
  /** `tab_manipulation` capability — drives the offered modes + price note. */
  capability: unknown;
  busy: boolean;
  /** Fase de preparo (persist + reload da comanda): o diálogo já abriu. */
  preparing?: boolean;
  /**
   * Linhas que já vêm marcadas: o Transferir do modo seleção da comanda (v4), onde o
   * operador escolheu antes o que sai. Pelo F10 a lista vem vazia, como sempre.
   */
  preselected?: string[];
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  submit: [MovePayload];
}>();

const modes = computed(() => availableMoveModes(props.capability));
const showPriceNote = computed(() => freezesPriceOnMove(props.capability));
const targetOptions = computed(() => moveTargetOptions(props.otherTabs));
const lineViews = computed(() => props.items.map(moveLineView));
// DE ONDE os itens saem, sempre à vista (o título é o verbo; a origem é a primeira
// coisa que o operador confere antes de escolher o destino).
const originLine = computed(() => {
  const origin = props.tabDisplay ? `Da comanda ${tabTitleView(props.tabDisplay, "").title}.` : "";
  const price = showPriceNote.value ? "O preço de cada item fica como foi cobrado nesta comanda." : "";
  return [origin, price].filter(Boolean).join(" ") || undefined;
});
// O exemplo do campo é o formato que o servidor aceita (hífen; barra é recusada).
const splitPlaceholder = computed(() => `Ex.: ${props.suggestedSplitRef || "1007-2"}`);

const mode = ref<MoveMode>("transfer");
const selected = ref<Set<string>>(new Set());
const splitRef = ref("");
const targetSessionKey = ref("");

watch(() => props.open, (isOpen) => {
  if (!isOpen) return;
  mode.value = initialMoveMode(modes.value, targetOptions.value.length > 0);
  // Seleção começa VAZIA: dividir a conta é escolher O QUE SAI — nascer com
  // tudo marcado invertia o gesto (desmarcar o que fica) e um Enter apressado
  // movia a comanda inteira.
  // A exceção é o Transferir do modo seleção: lá a escolha já foi feita, linha a linha.
  const known = new Set(props.items.map(moveLineId));
  selected.value = new Set((props.preselected ?? []).filter((id) => known.has(id)));
  splitRef.value = props.suggestedSplitRef;
  targetSessionKey.value = defaultMoveTarget(props.otherTabs);
});

function toggle(id: string) {
  const next = new Set(selected.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selected.value = next;
}

const selectedIds = computed(() => selectedLineIds(props.items, selected.value));
const needsSelection = computed(() => modeNeedsSelection(mode.value));
const canSubmit = computed(() => canSubmitMove({
  mode: mode.value,
  selectedIds: selectedIds.value,
  splitRef: splitRef.value,
  targetSessionKey: targetSessionKey.value,
  itemCount: props.items.length,
  busy: props.busy,
}));

// O rodapé diz o verbo: Transferir (para outra comanda ou para uma nova) ou Juntar.
const submitLabel = computed(() => moveSubmitLabel(mode.value));

function submit() {
  const payload = buildMovePayload({
    mode: mode.value,
    items: props.items,
    selectedIds: selectedIds.value,
    splitRef: splitRef.value,
    targetSessionKey: targetSessionKey.value,
  });
  if (payload) emit("submit", payload);
}
</script>

<template>
  <!-- O título é o VERBO (dono, 10/10): os botões de cima são o destino (outra
       comanda, comanda nova, juntar), não três verbos concorrentes. -->
  <NuxtModal
    :open="open"
    title="Transferir itens"
    :description="originLine"
    :ui="{ content: 'sm:max-w-xl' }"
    data-pos-move-dialog
    @update:open="$emit('update:open', Boolean($event))"
  >
    <template #body>
      <div class="grid gap-3">
        <!-- O DESTINO, em colunas iguais que descem JUNTAS (dono, 13/10): completo, o
             curto escrito à mão, ícone. Nunca "Juntar comand…" cortado. -->
        <OperatorFitGroup
          :actions="modes"
          equal
          class="grid gap-2"
          :style="{ gridTemplateColumns: `repeat(${modes.length}, minmax(0, 1fr))` }"
          data-pos-move-modes
        >
          <OperatorButton
            v-for="option in modes"
            :key="option.ref"
            :label="option.label"
            :short-label="option.shortLabel"
            :icon="option.icon"
            block
            class="justify-center"
            :color="mode === option.ref ? 'primary' : 'neutral'"
            :variant="mode === option.ref ? 'solid' : 'outline'"
            :aria-pressed="mode === option.ref"
            @click="mode = option.ref"
          />
        </OperatorFitGroup>

        <p v-if="mode === 'merge'" class="rounded-md border bg-muted/40 p-2 text-xs text-muted-foreground">
          Leva todos os itens desta comanda para a escolhida e libera esta.
        </p>

        <!-- Preparo em curso: o diálogo abre na hora e a comanda é persistida por
             baixo; sem isto o botão do rodapé parecia morto. -->
        <p v-if="preparing" class="flex items-center gap-2 rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          <Icon name="line-md:loading-loop" class="size-4 shrink-0" />
          Preparando a comanda…
        </p>
        <!-- A lista cabe na largura: a coluna é `minmax(0, 1fr)` (sem ela a grade cresce
             até o nome mais comprido e rola de lado) e o nome quebra linha. -->
        <div v-else-if="needsSelection" class="grid max-h-56 grid-cols-[minmax(0,1fr)] gap-1 overflow-y-auto overflow-x-hidden">
          <div
            v-for="line in lineViews"
            :key="line.id"
            class="flex min-w-0 cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5"
            :class="selected.has(line.id) ? 'border-primary bg-primary/5' : ''"
          >
            <UiCheckbox
              :model-value="selected.has(line.id)"
              :aria-label="`Selecionar ${line.label}`"
              @update:model-value="toggle(line.id)"
            />
            <span class="min-w-0 flex-1 text-sm [overflow-wrap:anywhere]">{{ line.label }}</span>
            <span class="text-xs tabular-nums text-muted-foreground">{{ line.amountDisplay }}</span>
          </div>
        </div>

        <label v-if="mode === 'split'" class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">Nova comanda</span>
          <UiInput v-model="splitRef" :placeholder="splitPlaceholder" data-pos-move-split-ref />
        </label>

        <div v-else class="grid gap-1 text-sm">
          <span id="pos-move-target-label" class="font-medium text-muted-foreground">Comanda de destino</span>
          <NuxtSelect
            class="w-full"
            :model-value="targetSessionKey || undefined"
            :items="targetOptions.map((option) => ({ label: option.label, value: option.sessionKey }))"
            :placeholder="targetOptions.length ? 'Escolha a comanda' : 'Nenhuma outra comanda aberta'"
            :disabled="!targetOptions.length"
            aria-labelledby="pos-move-target-label"
            data-pos-move-target
            @update:model-value="(value) => { targetSessionKey = String(value ?? ''); }"
          />
        </div>
      </div>
    </template>
    <template #footer>
      <div class="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <NuxtButton color="neutral" variant="outline" label="Cancelar" :disabled="busy" @click="$emit('update:open', false)" />
        <!-- O botão diz o verbo do ato: Transferir, ou Juntar quando a comanda inteira vai. -->
        <NuxtButton color="primary" :label="submitLabel" :disabled="!canSubmit" :loading="busy" @click="submit" />
      </div>
    </template>
  </NuxtModal>
</template>
