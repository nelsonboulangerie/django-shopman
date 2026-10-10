<script setup lang="ts">
import type { POSCartItem, POSTabProjection } from "~/types/pos";
import {
  availableMoveModes,
  buildMovePayload,
  canSubmitMove,
  defaultMoveTarget,
  freezesPriceOnMove,
  type MoveMode,
  type MovePayload,
  moveLineId,
  moveLineView,
  modeNeedsSelection,
  moveTargetOptions,
  selectedLineIds,
} from "~/presentation/moveLines";

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

const mode = ref<MoveMode>("split");
const selected = ref<Set<string>>(new Set());
const splitRef = ref("");
const targetSessionKey = ref("");

watch(() => props.open, (isOpen) => {
  if (!isOpen) return;
  mode.value = modes.value[0]?.ref ?? "split";
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

// O rodapé diz o verbo do modo selecionado — o dicionário da comanda é
// dividir · transferir · juntar, e nada além disso.
const submitLabel = computed(() => modes.value.find((option) => option.ref === mode.value)?.label || "Mover itens");

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
  <!-- ⚠️ O título NÃO pode ser um dos três modos: "Transferir" era ao mesmo tempo o
       nome da caixa e o nome de um dos botões dentro dela, e quem escolhia "Dividir"
       lia "Transferir" no topo. A comanda é o assunto; os verbos são dela (dividir,
       transferir, juntar) e moram nos botões. -->
  <NuxtModal
    :open="open"
    :title="`Comanda #${tabDisplay || 'atual'}`"
    :description="showPriceNote ? 'O preço de cada item é mantido como foi cobrado nesta comanda.' : undefined"
    :ui="{ content: 'sm:max-w-md' }"
    data-pos-move-dialog
    @update:open="$emit('update:open', Boolean($event))"
  >
    <template #body>
      <div class="grid gap-3">
        <div class="grid gap-2" :style="{ gridTemplateColumns: `repeat(${modes.length}, minmax(0, 1fr))` }">
          <NuxtButton
            v-for="option in modes"
            :key="option.ref"
            block
            :color="mode === option.ref ? 'primary' : 'neutral'"
            :variant="mode === option.ref ? 'solid' : 'outline'"
            :label="option.label"
            :aria-pressed="mode === option.ref"
            @click="mode = option.ref"
          />
        </div>

        <p v-if="mode === 'merge'" class="rounded-md border bg-muted/40 p-2 text-xs text-muted-foreground">
          Junta todos os itens desta comanda na comanda escolhida e libera esta.
        </p>

        <!-- Preparo em curso: o diálogo abre na hora e a comanda é persistida por
             baixo; sem isto o botão do rodapé parecia morto. -->
        <p v-if="preparing" class="flex items-center gap-2 rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          <Icon name="line-md:loading-loop" class="size-4 shrink-0" />
          Preparando a comanda…
        </p>
        <div v-else-if="needsSelection" class="grid max-h-56 gap-1 overflow-y-auto">
          <div
            v-for="line in lineViews"
            :key="line.id"
            class="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5"
            :class="selected.has(line.id) ? 'border-primary bg-primary/5' : ''"
          >
            <UiCheckbox
              :model-value="selected.has(line.id)"
              :aria-label="`Selecionar ${line.label}`"
              @update:model-value="toggle(line.id)"
            />
            <span class="min-w-0 flex-1 truncate text-sm">{{ line.label }}</span>
            <span class="text-xs tabular-nums text-muted-foreground">{{ line.amountDisplay }}</span>
          </div>
        </div>

        <label v-if="mode === 'split'" class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">Nova comanda</span>
          <UiInput v-model="splitRef" placeholder="Ex: 1007/2" />
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
        <!-- O botão repete o modo escolhido. Dizia "Mover": um quarto verbo para um
             gesto que já tinha três nomes na mesma caixa. -->
        <NuxtButton color="primary" :label="submitLabel" :disabled="!canSubmit" :loading="busy" @click="submit" />
      </div>
    </template>
  </NuxtModal>
</template>
