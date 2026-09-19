<script setup lang="ts">
// Card de timer da bancada — a linguagem do KDS aplicada ao fournil.
//
// Duas zonas, um gesto:
// · CORPO = o nome e o relógio, e ele É o alvo do toque quando há uma coisa
//   óbvia a fazer: tocando → ``Visto`` silencia o que grita; já visto → o
//   toque encerra. Correndo, o corpo não é botão: um esbarrão não pode mexer
//   no tempo de ninguém.
// · RODAPÉ = os dois botões explícitos que sobram, ``+5 min`` e ``Encerrar``.
//   Sem grade de quatro: o caso comum está no corpo, e +1 morreu com o numpad
//   da criação, que já resolve precisão.
//
// O que o toque faz nunca fica escondido: a dica escreve o gesto do estado
// atual, e o rótulo ARIA do corpo diz a mesma frase para quem não vê a tela.
import type { FloorTimerEntry } from "~/composables/useFloorTimers";
import {
  FLOOR_TIMER_ARM_MS,
  floorTimerModeLabel,
  floorTimerTap,
  floorTimerTapHint,
  minutesLabel,
} from "~/presentation/timers";

const props = defineProps<{
  entry: FloorTimerEntry;
  /** O relógio vivo, já formatado pelo composable (ex.: "12:34"). */
  remaining: string;
}>();
const emit = defineEmits<{ seen: []; clear: []; extend: [number] }>();

// Armar: o toque que marcou ``Visto`` transforma o card em "visto", onde o
// toque encerra. Sem a janela, um toque que quicasse faria as duas coisas.
const armed = ref(props.entry.mode === "seen");
let armTimer: ReturnType<typeof setTimeout> | null = null;
watch(
  () => props.entry.mode,
  (mode, previous) => {
    if (mode === "seen" && previous === "ringing") {
      armed.value = false;
      if (armTimer) clearTimeout(armTimer);
      armTimer = setTimeout(() => (armed.value = true), FLOOR_TIMER_ARM_MS);
      return;
    }
    armed.value = mode === "seen";
  },
);
onBeforeUnmount(() => {
  if (armTimer) clearTimeout(armTimer);
});

const tap = computed(() => floorTimerTap(props.entry.mode, { armed: armed.value }));
const hint = computed(() => floorTimerTapHint(props.entry.mode));
const stateLabel = computed(() => floorTimerModeLabel(props.entry.mode));
/** O que o relógio mostra: o estado quando há palavra, senão a contagem. */
const clock = computed(() => stateLabel.value || props.remaining);

function onTap() {
  if (tap.value === "seen") emit("seen");
  else if (tap.value === "clear") emit("clear");
}
</script>

<template>
  <li
    class="flex flex-col overflow-hidden rounded-lg border bg-card"
    :class="entry.mode === 'ringing' ? 'floor-timer-ringing border-destructive/60' : ''"
  >
    <component
      :is="tap === 'none' ? 'div' : 'button'"
      :type="tap === 'none' ? undefined : 'button'"
      class="flex min-h-32 flex-1 flex-col items-start gap-1 p-4 text-left"
      :class="
        tap === 'none'
          ? ''
          : 'transition hover:bg-accent active:translate-y-px'
      "
      :aria-label="hint ? `${entry.title}: ${hint}` : undefined"
      @click="onTap()"
    >
      <p class="w-full truncate text-lg font-semibold leading-tight">
        {{ entry.title }}
      </p>
      <p class="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
        <span v-if="entry.kind === 'oven'">Forno</span>
        <span v-if="entry.sku" class="truncate">{{ entry.sku }}</span>
        <span>{{ minutesLabel(entry.minutes) }}</span>
      </p>
      <p
        class="mt-auto w-full text-4xl font-bold tabular-nums leading-none"
        :class="
          entry.mode === 'ringing'
            ? 'animate-pulse text-destructive motion-reduce:animate-none'
            : entry.mode === 'seen'
              ? 'text-muted-foreground'
              : 'text-foreground'
        "
        role="timer"
        :aria-label="`${entry.title}: ${clock}`"
      >
        {{ clock }}
      </p>
      <p v-if="hint" class="text-xs font-medium text-muted-foreground">
        {{ hint }}
      </p>
    </component>

    <div class="grid grid-cols-2 gap-px border-t bg-border">
      <button
        type="button"
        class="min-h-14 bg-card text-base font-semibold tabular-nums transition hover:bg-accent active:translate-y-px"
        :aria-label="`Somar 5 minutos a ${entry.title}`"
        @click="emit('extend', 5)"
      >
        +5 min
      </button>
      <button
        type="button"
        class="min-h-14 bg-card text-base font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground active:translate-y-px"
        :aria-label="`Encerrar ${entry.title}`"
        @click="emit('clear')"
      >
        Encerrar
      </button>
    </div>
  </li>
</template>

<style scoped>
/* O card inteiro oscila em danger quando o alarme toca: reconhecível do outro
   lado do fournil, sem depender de ler o texto. Mesma linguagem que a lista
   antiga usava — o que mudou foi o tamanho do alvo, não o aviso. */
@keyframes floor-timer-ring {
  0%,
  100% {
    background-color: var(--card);
  }
  50% {
    background-color: color-mix(in oklab, var(--destructive) 16%, var(--card));
  }
}
.floor-timer-ringing {
  animation: floor-timer-ring 1.1s ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  .floor-timer-ringing {
    animation: none;
    box-shadow: inset 0 0 0 3px
      color-mix(in oklab, var(--destructive) 55%, transparent);
  }
}
</style>
