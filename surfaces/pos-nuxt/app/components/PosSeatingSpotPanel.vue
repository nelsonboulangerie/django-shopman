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
const newAreaOpen = ref(false);
const newAreaName = ref("");
const areaChoices = computed(() => {
  const names = [...props.areas];
  if (props.spot.area && !names.includes(props.spot.area)) names.unshift(props.spot.area);
  return names;
});
function onArea(value: unknown) {
  if (value === NEW_AREA) {
    newAreaOpen.value = true;
    newAreaName.value = "";
    return;
  }
  emit("update", { area: String(value ?? "") });
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

const menuOpen = ref(false);
function menu(action: "rotate" | "duplicate" | "remove") {
  menuOpen.value = false;
  if (action === "rotate") emit("rotate");
  else if (action === "duplicate") emit("duplicate");
  else emit("remove");
}
const tabsNote = computed(() => {
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
      <UiPopover v-model:open="menuOpen">
        <UiPopoverTrigger as-child>
          <button
            type="button"
            class="grid size-control shrink-0 place-items-center rounded-md border border-border transition hover:bg-accent"
            aria-label="Mais: duplicar, girar 90°, tirar do salão"
            title="Mais: duplicar, girar 90°, tirar do salão"
          >
            <Icon name="lucide:ellipsis" class="size-5" aria-hidden="true" />
          </button>
        </UiPopoverTrigger>
        <UiPopoverContent align="end" class="w-56 p-1.5">
          <button type="button" class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body hover:bg-accent" @click="menu('duplicate')">
            <Icon name="lucide:copy" class="size-4 text-muted-foreground" aria-hidden="true" />Duplicar
          </button>
          <button type="button" class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body hover:bg-accent" @click="menu('rotate')">
            <Icon name="lucide:rotate-cw" class="size-4 text-muted-foreground" aria-hidden="true" />Girar 90°
          </button>
          <button type="button" class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body text-destructive hover:bg-destructive/10" @click="menu('remove')">
            <Icon name="lucide:trash-2" class="size-4" aria-hidden="true" />Tirar do salão
          </button>
        </UiPopoverContent>
      </UiPopover>
    </div>

    <div class="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-3">
      <div class="flex flex-col gap-1.5">
        <span id="seating-seats-label" class="op-label text-muted-foreground">Lugares</span>
        <div class="flex items-center gap-2">
          <div class="inline-flex h-12 items-center rounded-md border border-input" role="group" aria-labelledby="seating-seats-label">
            <button
              type="button"
              class="grid h-full w-12 place-items-center border-r border-input transition hover:bg-accent disabled:opacity-40"
              :disabled="isStool || spot.seats <= 1"
              aria-label="Um lugar a menos"
              data-seating-seats-minus
              @click="seats(-1)"
            >
              <Icon name="lucide:minus" class="size-4" aria-hidden="true" />
            </button>
            <span class="w-14 text-center op-figure tabular-nums" aria-live="polite" data-seating-seats>{{ spot.seats }}</span>
            <button
              type="button"
              class="grid h-full w-12 place-items-center border-l border-input transition hover:bg-accent disabled:opacity-40"
              :disabled="isStool || spot.seats >= maxSeats"
              aria-label="Um lugar a mais"
              data-seating-seats-plus
              @click="seats(1)"
            >
              <Icon name="lucide:plus" class="size-4" aria-hidden="true" />
            </button>
          </div>
          <span class="op-micro leading-4 text-muted-foreground">
            <template v-if="isStool">banqueta é um<br>lugar só</template>
            <template v-else>cadeiras aparecem<br>em volta da mesa</template>
          </span>
        </div>
      </div>

      <div class="flex flex-col gap-1.5">
        <span id="seating-shape-label" class="op-label text-muted-foreground">Forma</span>
        <div class="grid h-12 grid-cols-4 rounded-lg bg-secondary p-1" role="radiogroup" aria-labelledby="seating-shape-label">
          <button
            v-for="shape in SHAPES"
            :key="shape.value"
            type="button"
            role="radio"
            class="rounded-md px-0.5 op-label"
            :class="spot.shape === shape.value ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground'"
            :aria-checked="spot.shape === shape.value"
            :data-seating-shape="shape.value"
            @click="emit('update', { shape: shape.value })"
          >{{ shape.label }}</button>
        </div>
      </div>

      <div class="flex flex-col gap-1.5">
        <label for="seating-area" class="op-label text-muted-foreground">Área</label>
        <form v-if="newAreaOpen" class="flex items-center gap-2" @submit.prevent="confirmNewArea">
          <input
            v-model="newAreaName"
            class="h-11 min-w-0 flex-1 rounded-md border border-input bg-background px-3 op-body"
            maxlength="40"
            placeholder="Nome da área nova"
            aria-label="Nome da área nova"
            autofocus
          >
          <UiButton type="submit" size="sm">Usar</UiButton>
        </form>
        <UiNativeSelect
          v-else
          id="seating-area"
          :model-value="spot.area"
          class="h-11"
          data-seating-area-select
          @update:model-value="onArea"
        >
          <!-- `selected` em cada opção: o valor do <select> chega antes das opções. -->
          <option v-for="name in areaChoices" :key="name" :value="name" :selected="name === spot.area">{{ name }}</option>
          <option value="" :selected="!spot.area">Sem área</option>
          <option :value="NEW_AREA">Nova área…</option>
        </UiNativeSelect>
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
          <input
            v-model="label"
            class="h-11 w-full min-w-0 rounded-md border border-input bg-background px-3 op-body"
            maxlength="80"
            data-seating-label
            @change="commitNames"
            @keydown.enter="($event.target as HTMLInputElement).blur()"
          >
        </label>
        <label class="flex flex-col gap-1.5">
          <span class="op-label text-muted-foreground">Sigla</span>
          <input
            v-model="shortLabel"
            class="h-11 w-full min-w-0 rounded-md border border-input bg-background px-3 op-body uppercase"
            maxlength="8"
            :placeholder="shortLabelOf({ short_label: '', label: spot.label })"
            data-seating-short-label
            @change="commitNames"
            @keydown.enter="($event.target as HTMLInputElement).blur()"
          >
        </label>
      </div>

    </div>

    <div class="border-t border-border px-4 py-3">
      <button
        type="button"
        class="inline-flex h-10 items-center gap-2 px-2 op-label text-destructive"
        data-seating-remove
        @click="emit('remove')"
      >
        <Icon name="lucide:trash-2" class="size-4" aria-hidden="true" />
        {{ original ? "Tirar do salão a partir de hoje" : "Tirar esta mesa nova" }}
      </button>
    </div>
  </section>
</template>
