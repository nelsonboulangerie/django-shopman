<script setup lang="ts">
// O painel da mesa escolhida (prévia `salao-mesas4.html`, coluna da direita): lugares,
// forma, área, nome e "conta na capacidade oficial", tudo num lugar só, com a regra de
// tempo escrita no lugar ("Existe desde": mudar lugares ou a capacidade vale a partir
// de hoje). No pé, tirar do salão a partir de hoje. No celular a mesma peça abre numa
// folha de baixo (`PosSeatingList`).
import { type DraftSpot, SHAPES, areaOf, changeList, shortLabelOf, timeRule } from "~/presentation/seating";

const props = defineProps<{
  spot: DraftSpot;
  original: DraftSpot | undefined;
  areas: readonly string[];
  todayLabel: string;
  maxSeats: number;
  /** Comandas em uso agora (a nota de que mover mesa não mexe em comanda). */
  openTabs: number;
  /** A comanda aberta NESTA mesa (vínculo opcional comanda × mesa); "" = nenhuma. */
  spotTab?: string;
}>();

const emit = defineEmits<{
  update: [patch: Partial<DraftSpot>];
  rotate: [];
  duplicate: [];
  remove: [];
}>();

const rule = computed(() => timeRule(props.original, props.spot, props.todayLabel));
const status = computed(() => {
  const change = changeList(props.original ? [props.original] : [], [props.spot], [])[0];
  const words = change ? change.text.slice(shortLabelOf(props.spot).length + 1) : "";
  return [areaOf(props.spot), words].filter(Boolean).join(" · ");
});
const isStool = computed(() => props.spot.shape === "stool");

const NEW_AREA = "__nova__";
// O `NuxtSelect` (Reka) não aceita valor vazio num item: "Sem área" tem o seu.
const NO_AREA_VALUE = "__sem_area__";
const newAreaOpen = ref(false);
const newAreaName = ref("");
const areaChoices = computed(() => {
  const names = [...props.areas];
  if (props.spot.area && !names.includes(props.spot.area)) names.unshift(props.spot.area);
  return names;
});
const areaItems = computed(() => [
  ...areaChoices.value.map((name) => ({ label: name, value: name })),
  { label: "Sem área", value: NO_AREA_VALUE },
  { label: "Nova área…", value: NEW_AREA },
]);
const areaValue = computed(() => props.spot.area || NO_AREA_VALUE);
function onArea(value: unknown) {
  if (value === NEW_AREA) {
    newAreaOpen.value = true;
    newAreaName.value = "";
    return;
  }
  emit("update", { area: value === NO_AREA_VALUE ? "" : String(value ?? "") });
}
function confirmNewArea() {
  const name = newAreaName.value.trim();
  if (name) emit("update", { area: name });
  newAreaOpen.value = false;
}

function seats(delta: number) {
  const next = Math.min(props.maxSeats, Math.max(1, props.spot.seats + delta));
  if (next !== props.spot.seats) emit("update", { seats: next });
}

const label = ref(props.spot.label);
const shortLabel = ref(props.spot.short_label);
watch(() => [props.spot.key, props.spot.label, props.spot.short_label], () => {
  label.value = props.spot.label;
  shortLabel.value = props.spot.short_label;
});
function commitNames() {
  const patch: Partial<DraftSpot> = {};
  if (label.value.trim() && label.value.trim() !== props.spot.label) patch.label = label.value.trim();
  if (shortLabel.value.trim() !== props.spot.short_label) patch.short_label = shortLabel.value.trim();
  if (Object.keys(patch).length) emit("update", patch);
  else label.value = props.spot.label;
}

// O ⋯ da mesa (o mesmo de toda a suíte).
const menuItems = computed(() => [
  { label: "Duplicar", icon: "i-lucide-copy", onSelect: () => emit("duplicate") },
  { label: "Girar 90°", icon: "i-lucide-rotate-cw", onSelect: () => emit("rotate") },
  { label: "Tirar do salão", icon: "i-lucide-trash-2", color: "error" as const, onSelect: () => emit("remove") },
]);
// "Mesa 4 tem comanda aberta agora. Mover mesas não mexe em comanda." (v4 pino 6):
// com o vínculo, a nota fala DESTA mesa; sem ele, do salão.
const tabsNote = computed(() => {
  if (props.spotTab) return `${props.spot.label} tem comanda aberta agora (${props.spotTab}). Mover mesas não mexe em comanda.`;
  const lead = props.openTabs === 1 ? "1 comanda aberta agora." : props.openTabs > 1 ? `${props.openTabs} comandas abertas agora.` : "";
  return `${lead} Mover mesas não mexe em comanda.`.trim();
});
</script>

<template>
  <section class="flex min-h-0 flex-1 flex-col" :aria-label="`Mesa ${spot.label}`" data-seating-panel>
    <div class="flex items-center gap-3 border-b border-border px-4 pt-4 pb-3">
      <span
        class="grid size-10 shrink-0 place-items-center border-2 border-primary bg-primary/12 op-label font-semibold"
        :class="spot.shape === 'round' || spot.shape === 'stool' ? 'rounded-full' : 'rounded-md'"
        aria-hidden="true"
      >{{ shortLabelOf(spot) }}</span>
      <div class="min-w-0 flex-1">
        <h2 class="truncate op-title">{{ spot.label }}</h2>
        <p class="truncate op-micro text-muted-foreground">{{ status }}</p>
      </div>
      <OperatorMoreMenu :items="menuItems" :label="`Mais ações de ${spot.label}`" class="shrink-0" data-seating-spot-menu />
    </div>

    <div class="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-3">
      <div class="flex flex-col gap-1.5">
        <span id="seating-seats-label" class="op-label text-muted-foreground">Lugares</span>
        <div class="flex items-center gap-2">
          <NuxtFieldGroup size="xl" role="group" aria-labelledby="seating-seats-label">
            <NuxtButton
              icon="i-lucide-minus"
              color="neutral"
              variant="outline"
              square
              :disabled="isStool || spot.seats <= 1"
              aria-label="Um lugar a menos"
              data-seating-seats-minus
              @click="seats(-1)"
            />
            <span
              class="inline-flex w-14 items-center justify-center border-y border-default op-figure tabular-nums"
              aria-live="polite"
              data-seating-seats
            >{{ spot.seats }}</span>
            <NuxtButton
              icon="i-lucide-plus"
              color="neutral"
              variant="outline"
              square
              :disabled="isStool || spot.seats >= maxSeats"
              aria-label="Um lugar a mais"
              data-seating-seats-plus
              @click="seats(1)"
            />
          </NuxtFieldGroup>
          <span class="op-micro leading-4 text-muted-foreground">
            <template v-if="isStool">banqueta é um<br>lugar só</template>
            <template v-else>cadeiras aparecem<br>em volta da mesa</template>
          </span>
        </div>
      </div>

      <div class="flex flex-col gap-1.5">
        <span id="seating-shape-label" class="op-label text-muted-foreground">Forma</span>
        <NuxtFieldGroup class="grid w-full grid-cols-4" role="radiogroup" aria-labelledby="seating-shape-label">
          <NuxtButton
            v-for="shape in SHAPES"
            :key="shape.value"
            role="radio"
            color="neutral"
            variant="outline"
            active-color="primary"
            active-variant="solid"
            :active="spot.shape === shape.value"
            :aria-checked="spot.shape === shape.value"
            class="justify-center px-1"
            :label="shape.label"
            :data-seating-shape="shape.value"
            @click="emit('update', { shape: shape.value })"
          />
        </NuxtFieldGroup>
      </div>

      <div class="flex flex-col gap-1.5">
        <label for="seating-area" class="op-label text-muted-foreground">Área</label>
        <form v-if="newAreaOpen" class="flex items-center gap-2" @submit.prevent="confirmNewArea">
          <NuxtInput
            v-model="newAreaName"
            class="min-w-0 flex-1"
            :maxlength="40"
            placeholder="Nome da área nova"
            aria-label="Nome da área nova"
            autofocus
          />
          <NuxtButton type="submit" label="Usar" />
        </form>
        <NuxtSelect
          v-else
          id="seating-area"
          :model-value="areaValue"
          :items="areaItems"
          class="w-full"
          data-seating-area-select
          @update:model-value="onArea"
        />
      </div>

      <div class="flex flex-col gap-1.5 rounded-lg border border-border p-3">
        <label class="flex items-center gap-3">
          <span class="flex-1 op-label font-semibold">Conta na capacidade oficial</span>
          <UiSwitch
            :model-value="spot.counts_in_capacity"
            tone="success"
            data-seating-capacity
            @update:model-value="emit('update', { counts_in_capacity: Boolean($event) })"
          />
        </label>
        <p class="op-micro leading-4 text-muted-foreground">
          O B.I. mede a lotação com estes lugares. Desligue para a mesa que só sai em dia cheio (vira extra).
        </p>
      </div>

      <div class="flex items-start gap-3">
        <Icon name="lucide:calendar" class="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div>
          <p class="op-label">{{ rule.title }}</p>
          <p class="op-micro leading-4 text-muted-foreground" data-seating-time-rule>{{ rule.note }}</p>
        </div>
      </div>

      <div class="flex items-start gap-2 rounded-lg bg-info/10 p-2.5">
        <Icon name="lucide:info" class="mt-0.5 size-4 shrink-0 text-info" aria-hidden="true" />
        <p class="op-micro leading-4">{{ tabsNote }}</p>
      </div>
      <div class="grid grid-cols-[1fr_5.5rem] gap-2">
        <label class="flex flex-col gap-1.5">
          <span class="op-label text-muted-foreground">Nome</span>
          <NuxtInput
            v-model="label"
            class="w-full min-w-0"
            :maxlength="80"
            data-seating-label
            @change="commitNames"
            @keydown.enter="($event.target as HTMLInputElement).blur()"
          />
        </label>
        <label class="flex flex-col gap-1.5">
          <span class="op-label text-muted-foreground">Sigla</span>
          <NuxtInput
            v-model="shortLabel"
            class="w-full min-w-0"
            :ui="{ base: 'uppercase' }"
            :maxlength="8"
            :placeholder="shortLabelOf({ short_label: '', label: spot.label })"
            data-seating-short-label
            @change="commitNames"
            @keydown.enter="($event.target as HTMLInputElement).blur()"
          />
        </label>
      </div>

    </div>

    <div class="border-t border-border px-4 py-3">
      <NuxtButton
        icon="i-lucide-trash-2"
        color="error"
        variant="ghost"
        :label="original ? 'Tirar do salão a partir de hoje' : 'Tirar esta mesa nova'"
        data-seating-remove
        @click="emit('remove')"
      />
    </div>
  </section>
</template>
