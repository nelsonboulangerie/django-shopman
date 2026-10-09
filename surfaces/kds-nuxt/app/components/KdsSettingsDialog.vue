<script setup lang="ts">
// Ajustes da Cozinha (item do pé da barra lateral e do "Mais", prévia v4). Mora aqui o
// que é da BANCADA e não do toque de quem passa (nota 1: "densidade e som saem do
// botão: vêm da estação provisionada"): o tamanho do ticket e o som da estação. Os dois
// ficam gravados no cadastro da estação e valem para todas as telas dela. A data de
// consulta saiu da Cozinha (nota 2): a prévia de outra data é da Produção/Encomendas.
import type { KDSDensity } from "~/presentation/board";
import { KDS_DENSITIES } from "~/composables/useKdsDensity";

const open = useKdsSettingsOpen();
const board = useKdsBoardState();
const { busy, save } = useKdsStationSettings();

const onStation = computed(() => board.value.onBoard && Boolean(board.value.stationRef));
const stationLabel = computed(() => {
  const name = board.value.stationName || board.value.stationRef;
  return /^esta[çc][aã]o\b/i.test(name) ? name : `Estação ${name}`;
});

const densityItems = KDS_DENSITIES.map((option) => ({
  value: option.key,
  label: option.label,
  "data-density": option.key,
}));
const density = computed({
  get: () => board.value.density,
  set: (value: KDSDensity) => {
    if (value !== board.value.density) void save({ density: value });
  },
});
const soundItems = [
  { value: "on", label: "Ligado", "data-kds-sound-on": "" },
  { value: "off", label: "Desligado", "data-kds-sound-off": "" },
];
const sound = computed({
  get: () => (board.value.soundEnabled ? "on" : "off"),
  set: (value: string) => {
    const enabled = value === "on";
    if (enabled !== board.value.soundEnabled) void save({ sound_enabled: enabled });
  },
});
</script>

<template>
  <NuxtModal
    v-model:open="open"
    title="Ajustes da Cozinha"
    description="Tamanho do ticket e som da estação, gravados para todas as telas dela."
    data-kds-settings
  >
    <template #body>
      <div class="flex flex-col gap-5">
        <p v-if="!onStation" class="op-body text-muted-foreground" data-kds-settings-no-station>
          Abra uma estação para ajustar o tamanho do ticket e o som dela.
        </p>

        <template v-else>
          <p class="op-label text-muted-foreground" data-kds-settings-station>
            {{ stationLabel }} · vale para todas as telas desta estação.
          </p>

          <NuxtRadioGroup
            v-model="density"
            legend="Tamanho do ticket"
            :items="densityItems"
            orientation="horizontal"
            variant="card"
            :disabled="busy"
          />

          <div class="flex flex-col gap-2">
            <NuxtRadioGroup
              v-model="sound"
              legend="Som da estação"
              :items="soundItems"
              orientation="horizontal"
              variant="card"
              :disabled="busy"
            />
            <p class="op-micro text-muted-foreground">
              Ligado: o pedido novo toca até alguém da estação dar Visto.
            </p>
          </div>
        </template>
      </div>
    </template>
  </NuxtModal>
</template>
