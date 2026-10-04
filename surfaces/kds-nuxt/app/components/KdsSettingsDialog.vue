<script setup lang="ts">
// Ajustes da Cozinha (item do pé do rail e da barra do polegar, prévia v4). Mora aqui
// o que é da BANCADA e não do toque de quem passa (nota 1: "densidade e som saem do
// botão: vêm da estação provisionada"): o tamanho do ticket e o som da estação. Os dois
// ficam gravados no cadastro da estação e valem para todas as telas dela. A data de
// consulta saiu da Cozinha (nota 2): a prévia de outra data é da Produção/Encomendas.
import { KDS_DENSITIES } from "~/composables/useKdsDensity";

const open = useKdsSettingsOpen();
const board = useKdsBoardState();
const { busy, save } = useKdsStationSettings();

const onStation = computed(() => board.value.onBoard && Boolean(board.value.stationRef));
const stationLabel = computed(() => {
  const name = board.value.stationName || board.value.stationRef;
  return /^esta[çc][aã]o\b/i.test(name) ? name : `Estação ${name}`;
});
</script>

<template>
  <UiDialog :open="open" @update:open="open = Boolean($event)">
    <UiDialogContent class="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-md" data-kds-settings data-suite="v3">
      <UiDialogTitle class="border-b px-5 py-4 op-title">Ajustes da Cozinha</UiDialogTitle>
      <UiDialogDescription class="sr-only">
        Tamanho do ticket e som da estação, gravados para todas as telas dela.
      </UiDialogDescription>
      <div class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-5">
        <p v-if="!onStation" class="op-body text-muted-foreground" data-kds-settings-no-station>
          Abra uma estação para ajustar o tamanho do ticket e o som dela.
        </p>

        <template v-else>
          <p class="op-label text-muted-foreground" data-kds-settings-station>
            {{ stationLabel }} · vale para todas as telas desta estação.
          </p>

          <section class="flex flex-col gap-2">
            <h3 class="op-eyebrow text-muted-foreground">Tamanho do ticket</h3>
            <div class="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Tamanho do ticket nesta estação">
              <button
                v-for="option in KDS_DENSITIES"
                :key="option.key"
                type="button"
                role="radio"
                :aria-checked="board.density === option.key"
                :disabled="busy"
                class="flex min-h-14 flex-col items-center justify-center gap-1 rounded-lg border px-2 py-2 op-label transition disabled:opacity-60"
                :class="board.density === option.key ? 'border-primary bg-primary/10 font-semibold' : 'bg-card hover:bg-accent'"
                :data-density="option.key"
                @click="save({ density: option.key })"
              >
                <Icon :name="option.icon" class="size-5" aria-hidden="true" />
                {{ option.label }}
              </button>
            </div>
          </section>

          <section class="flex flex-col gap-2">
            <h3 class="op-eyebrow text-muted-foreground">Som da estação</h3>
            <div class="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Som do pedido novo nesta estação">
              <button
                type="button"
                role="radio"
                :aria-checked="board.soundEnabled"
                :disabled="busy"
                class="flex min-h-14 items-center justify-center gap-2 rounded-lg border px-2 op-label transition disabled:opacity-60"
                :class="board.soundEnabled ? 'border-primary bg-primary/10 font-semibold' : 'bg-card hover:bg-accent'"
                data-kds-sound-on
                @click="save({ sound_enabled: true })"
              >
                <Icon name="lucide:volume-2" class="size-5" aria-hidden="true" />
                Ligado
              </button>
              <button
                type="button"
                role="radio"
                :aria-checked="!board.soundEnabled"
                :disabled="busy"
                class="flex min-h-14 items-center justify-center gap-2 rounded-lg border px-2 op-label transition disabled:opacity-60"
                :class="!board.soundEnabled ? 'border-primary bg-primary/10 font-semibold' : 'bg-card hover:bg-accent'"
                data-kds-sound-off
                @click="save({ sound_enabled: false })"
              >
                <Icon name="lucide:volume-x" class="size-5" aria-hidden="true" />
                Desligado
              </button>
            </div>
            <p class="op-micro text-muted-foreground">
              Ligado: o pedido novo toca até alguém da estação dar Visto.
            </p>
          </section>
        </template>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
