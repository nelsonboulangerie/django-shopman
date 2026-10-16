<script setup lang="ts">
import type { POSCartItem, POSSeatingSpotOption, POSTabProjection } from "~/types/pos";
import {
  allowsExistingTab,
  allowsNewTab,
  buildMovePayload,
  filterTargets,
  freeSpotOptions,
  freezesPriceOnMove,
  linesToMove,
  type MovePayload,
  moveLineId,
  movesEverything,
  moveTargetOptions,
  movingSummary,
  resolveDestination,
  tabLabel,
  transferCta,
} from "~/presentation/moveLines";

// TRANSFERIR, A AÇÃO ÚNICA (dono, N=1, 13/10/2026): um campo só, "Para qual comanda?",
// que recebe o leitor, a digitação ou a escolha na lista das comandas em uso. Ao abrir,
// a ação padrão já está pronta: a comanda nova pré-nomeada ("13-2"), e o Enter confirma.
const props = defineProps<{
  open: boolean;
  tabDisplay: string;
  /** A sessão da comanda de origem (fica fora da lista de destinos). */
  sourceSessionKey?: string;
  /** A mesa da comanda de origem ("" sem mesa): não é destino nem mesa livre. */
  sourceSpotRef?: string;
  /** As mesas do Salão de hoje (dono, M=1): a ocupada leva à comanda dela; a livre abre a
   *  comanda nova já nela. */
  seatingSpots?: POSSeatingSpotOption[];
  items: POSCartItem[];
  /** O nome que a comanda nova recebe se ninguém mudar ("13-2", ou o próximo livre). */
  suggestedNewTabRef: string;
  otherTabs: POSTabProjection[];
  /** `tab_manipulation`: o que o canal deixa (comanda nova, comanda em uso) e o preço. */
  capability: unknown;
  busy: boolean;
  /** Fase de preparo (persist + reload da comanda): o diálogo já abriu. */
  preparing?: boolean;
  /** As linhas marcadas na comanda. Vazio: vai a comanda inteira. */
  preselected?: string[];
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  submit: [MovePayload];
}>();

const destinationInput = ref("");
const field = ref<{ inputRef?: HTMLInputElement; $el?: HTMLElement } | null>(null);

const sourceTitle = computed(() => tabLabel(props.tabDisplay));
const lines = computed(() => linesToMove(props.items, props.preselected));
const lineIds = computed(() => lines.value.map(moveLineId));
const all = computed(() => movesEverything(props.items, lineIds.value));
const summary = computed(() => movingSummary(lines.value));
const spots = computed(() => props.seatingSpots || []);
const options = computed(() => moveTargetOptions(props.otherTabs, props.sourceSessionKey, spots.value));
const freeSpots = computed(() => freeSpotOptions(spots.value, props.otherTabs, props.sourceSpotRef));
const sourceSpotKeys = computed(() => {
  const spot = spots.value.find((entry) => entry.ref === props.sourceSpotRef);
  return spot ? [spot.label, spot.short_label].filter(Boolean) : [];
});
const shown = computed(() => filterTargets(options.value, destinationInput.value, props.suggestedNewTabRef));
const shownSpots = computed(() => filterTargets(freeSpots.value, destinationInput.value, props.suggestedNewTabRef));
const destination = computed(() =>
  resolveDestination({
    input: destinationInput.value,
    options: options.value,
    spots: freeSpots.value,
    sourceSpotKeys: sourceSpotKeys.value,
    sourceDisplay: props.tabDisplay,
    suggested: props.suggestedNewTabRef,
    allowsNew: allowsNewTab(props.capability),
    allowsExisting: allowsExistingTab(props.capability),
  }),
);
const cta = computed(() => transferCta({ units: summary.value.units, all: all.value, destination: destination.value, sourceTitle: sourceTitle.value }));
const canSubmit = computed(() => !props.busy && !props.preparing && destination.value.kind !== "invalid" && lineIds.value.length > 0);
// A origem, sempre à vista, e a garantia do preço.
const description = computed(() => {
  const origin = props.tabDisplay ? `Da comanda ${sourceTitle.value}.` : "";
  const price = freezesPriceOnMove(props.capability) ? "O preço de cada item fica como foi cobrado." : "";
  return [origin, price].filter(Boolean).join(" ") || undefined;
});

watch(() => props.open, (isOpen) => {
  if (!isOpen) return;
  destinationInput.value = props.suggestedNewTabRef;
  // O campo nasce com o nome sugerido SELECIONADO: o leitor ou a digitação substituem;
  // o Enter aceita.
  void nextTick(() => {
    const input = field.value?.inputRef || field.value?.$el?.querySelector?.("input");
    input?.focus();
    input?.select();
  });
});

function pick(title: string) {
  destinationInput.value = title;
}

function submit() {
  if (!canSubmit.value) return;
  const payload = buildMovePayload({ items: props.items, lineIds: lineIds.value, destination: destination.value });
  if (payload) emit("submit", payload);
}
</script>

<template>
  <NuxtModal
    :open="open"
    title="Transferir"
    :description="description"
    :ui="{ content: 'sm:max-w-lg' }"
    data-pos-move-dialog
    @update:open="$emit('update:open', Boolean($event))"
  >
    <template #body>
      <div class="grid gap-3">
        <!-- O que vai, numa frase: as marcadas, ou a comanda inteira. -->
        <p class="op-body [overflow-wrap:anywhere]" data-pos-move-summary>
          <span class="font-semibold">{{ all ? "Vai tudo" : "Vão" }}</span>
          {{ summary.text }}
        </p>

        <p v-if="preparing" class="flex items-center gap-2 op-micro text-muted-foreground">
          <Icon name="line-md:loading-loop" class="size-4 shrink-0" />
          Preparando a comanda…
        </p>

        <div class="grid gap-1.5">
          <label for="pos-move-destination" class="op-label font-medium">Para qual comanda?</label>
          <NuxtInput
            id="pos-move-destination"
            ref="field"
            v-model="destinationInput"
            class="w-full"
            autocomplete="off"
            :placeholder="`Bipe, digite o número ou um nome (ex.: ${suggestedNewTabRef || '13-2'})`"
            :color="destination.kind === 'invalid' ? 'error' : undefined"
            :aria-invalid="destination.kind === 'invalid' || undefined"
            aria-describedby="pos-move-destination-state"
            data-pos-move-destination
            @keydown.enter.prevent="submit"
          />
          <!-- O estado do campo em palavra: comanda nova, comanda em uso, ou o motivo. -->
          <p
            id="pos-move-destination-state"
            class="flex items-center gap-1.5 op-micro"
            :class="destination.kind === 'invalid' ? 'text-error' : 'text-muted-foreground'"
            data-pos-move-destination-state
            :data-destination-kind="destination.kind"
          >
            <template v-if="destination.kind === 'new' && destination.spotTitle">
              <Icon name="lucide:armchair" class="size-3.5 shrink-0" aria-hidden="true" />Comanda nova {{ destination.title }}, já na {{ destination.spotTitle }}.
            </template>
            <template v-else-if="destination.kind === 'new'">
              <Icon name="lucide:plus" class="size-3.5 shrink-0" aria-hidden="true" />Comanda nova {{ destination.title }}. Para outra, bipe ou escolha abaixo.
            </template>
            <template v-else-if="destination.kind === 'existing'">
              <Icon name="lucide:receipt-text" class="size-3.5 shrink-0" aria-hidden="true" />Comanda em uso {{ destination.title }}.
            </template>
            <template v-else>{{ destination.reason }}</template>
          </p>
        </div>

        <!-- As comandas EM USO, para escolher com um toque (a que casa com o campo). -->
        <div v-if="shown.length" class="grid gap-1.5">
          <span class="op-micro text-muted-foreground">Comandas em uso</span>
          <div class="flex flex-wrap gap-2" data-pos-move-targets>
            <NuxtButton
              v-for="option in shown"
              :key="option.sessionKey"
              color="neutral"
              :variant="destination.kind === 'existing' && destination.sessionKey === option.sessionKey ? 'solid' : 'outline'"
              :label="option.label"
              :aria-pressed="destination.kind === 'existing' && destination.sessionKey === option.sessionKey"
              :data-pos-move-target="option.sessionKey"
              @click="pick(option.title)"
            />
          </div>
        </div>

        <!-- As MESAS LIVRES do Salão (dono, M=1): a comanda nova nasce na escolhida. -->
        <div v-if="shownSpots.length" class="grid gap-1.5">
          <span class="op-micro text-muted-foreground">Mesas livres</span>
          <div class="flex flex-wrap gap-2" data-pos-move-spots>
            <NuxtButton
              v-for="spot in shownSpots"
              :key="spot.spotRef"
              color="neutral"
              :variant="destination.kind === 'new' && destination.spotRef === spot.spotRef ? 'solid' : 'outline'"
              icon="i-lucide-armchair"
              :label="spot.title"
              :aria-pressed="destination.kind === 'new' && destination.spotRef === spot.spotRef"
              :data-pos-move-spot="spot.spotRef"
              @click="pick(spot.title)"
            />
          </div>
        </div>
      </div>
    </template>
    <template #footer>
      <div class="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <NuxtButton color="neutral" variant="outline" label="Cancelar" :disabled="busy" @click="$emit('update:open', false)" />
        <!-- O botão diz o RESULTADO, em palavras (dono, N=1). -->
        <!-- Frase inteira, que quebra linha no celular em vez de cortar. -->
        <NuxtButton
          color="primary"
          :disabled="!canSubmit"
          :loading="busy"
          class="justify-center"
          data-pos-move-submit
          @click="submit"
        >
          <span class="whitespace-normal text-center [overflow-wrap:anywhere]">{{ cta }}</span>
        </NuxtButton>
      </div>
    </template>
  </NuxtModal>
</template>
