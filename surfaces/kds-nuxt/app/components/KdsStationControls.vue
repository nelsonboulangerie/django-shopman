<script setup lang="ts">
// Os controles da estação na barra (dono, 13/10/2026): o TAMANHO DO TICKET e o SOM,
// dois botões explícitos que também são o INDICADOR do estado. Antes os dois moravam no
// ⋯ "Ajustes da estação (som ligado/desligado)", e o tamanho do ticket ficava escondido
// atrás de um rótulo que só falava do som.
//
// Os dois continuam sendo da ESTAÇÃO (nota 1 da prévia v4): gravam no cadastro dela e
// valem para todas as telas da estação (`useKdsStationSettings`).
//
// - Tamanho do ticket: o mesmo segmentado da grade do PDV (`PosProductGrid`), um padrão
//   por gesto na suíte. Compacta · Padrão · Ampla, o ativo cheio e com o nome.
// - Som: um botão que liga e desliga. Ligado é discreto (contorno); DESLIGADO é cheio e
//   vermelho, para se ver de longe que o pedido novo vai entrar calado.
// - Rótulo: completo do `xl` para cima (a barra lateral come o resto); abaixo, só o ícone (o nome fica no aria e na
//   dica), como o segmentado do PDV. A barra do tablet em pé não tem lugar para os dois. Ligado mas
//   bloqueado pelo navegador diz "Ativar o som" e o toque ativa (o mesmo gesto do aviso
//   âmbar da tela, que continua lá).
import { KDS_DENSITIES } from "~/composables/useKdsDensity";
import type { KDSDensity } from "~/presentation/board";

const props = withDefaults(defineProps<{ soundBlocked?: boolean }>(), { soundBlocked: false });
const emit = defineEmits<{ activateSound: [] }>();

const board = useKdsBoardState();
const { busy, save } = useKdsStationSettings();

const density = computed(() => board.value.density);
function setDensity(value: KDSDensity) {
  if (value !== board.value.density) void save({ density: value });
}

const soundOn = computed(() => board.value.soundEnabled);
const soundState = computed<"on" | "off" | "blocked">(() =>
  !soundOn.value ? "off" : props.soundBlocked ? "blocked" : "on",
);
const sound = computed(() => {
  switch (soundState.value) {
    case "off":
      return {
        label: "Som desligado",
        icon: "i-lucide-volume-x",
        color: "error" as const,
        variant: "solid" as const,
        title: "Som da estação desligado: pedido novo entra sem tocar. Toque para ligar.",
      };
    case "blocked":
      return {
        label: "Ativar o som",
        icon: "i-lucide-volume-x",
        color: "neutral" as const,
        variant: "outline" as const,
        title: "O navegador bloqueou o som desta estação. Toque para ativar.",
      };
    default:
      return {
        label: "Som ligado",
        icon: "i-lucide-volume-2",
        color: "neutral" as const,
        variant: "outline" as const,
        title: "Som da estação ligado: pedido novo toca até alguém dar Visto. Toque para desligar.",
      };
  }
});
function toggleSound() {
  if (soundState.value === "blocked") {
    emit("activateSound");
    return;
  }
  void save({ sound_enabled: !soundOn.value });
}
</script>

<template>
  <div class="flex items-center gap-2" data-kds-station-controls>
    <NuxtFieldGroup role="group" aria-label="Tamanho do ticket" data-kds-density-control>
      <NuxtButton
        v-for="option in KDS_DENSITIES"
        :key="option.key"
        color="neutral"
        variant="outline"
        active-color="primary"
        active-variant="solid"
        :active="density === option.key"
        :square="density !== option.key"
        :disabled="busy"
        :aria-label="`Tamanho do ticket: ${option.label}`"
        :aria-pressed="density === option.key"
        :title="`Tamanho do ticket: ${option.label}`"
        :data-kds-density="option.key"
        @click="setDensity(option.key)"
      >
        <Icon :name="option.icon" class="size-4 shrink-0" aria-hidden="true" />
        <span v-if="density === option.key" class="max-xl:hidden" aria-hidden="true">{{ option.label }}</span>
      </NuxtButton>
    </NuxtFieldGroup>

    <NuxtButton
      :icon="sound.icon"
      :color="sound.color"
      :variant="sound.variant"
      :square="false"
      :disabled="busy"
      :aria-label="sound.label"
      :aria-pressed="soundOn"
      :title="sound.title"
      :data-kds-sound="soundState"
      @click="toggleSound"
    >
      <span class="max-xl:hidden" aria-hidden="true">{{ sound.label }}</span>
    </NuxtButton>
  </div>
</template>
