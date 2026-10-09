<script setup lang="ts">
// PROPOSTA (dono, 09/10/2026: "supérfluo, mas anote"; quer ver antes): o "Desfazer"
// com o tempo correndo DENTRO do próprio botão. Extensão do NuxtButton, não um botão
// novo: mesma anatomia, tamanhos e variantes do conjunto mínimo (md/xl, outline).
//
// Duas leituras do tempo:
//  - `fill`  o fundo do botão esvazia da direita para a esquerda até a janela fechar;
//  - `ring`  um anel ao lado do rótulo esvazia, com os segundos no meio.
//
// Movimento reduzido (`prefers-reduced-motion: reduce`): nada anima; o botão mostra só
// o número de segundos, que muda uma vez por segundo.
//
// Acessibilidade: o rótulo do botão é sempre "Desfazer"; o tempo vai numa descrição
// fixa ("Disponível até 10:42:15"), que não muda a cada segundo. Uma região educada
// avisa duas vezes: quando a janela abre e quando fecha. O número visível é
// `aria-hidden`.
//
// Ao fim: `expire` é emitido, e o botão some (`whenExpired="hide"`, o padrão) ou fica
// desabilitado (`"disable"`).
import { usePreferredReducedMotion } from "@vueuse/core";

const props = withDefaults(
  defineProps<{
    /** Duração da janela de desfazer, em segundos. */
    seconds?: number;
    variant?: "fill" | "ring";
    size?: "md" | "xl";
    label?: string;
    whenExpired?: "hide" | "disable";
    /** Força a leitura sem movimento (para a prévia mostrar os dois modos lado a lado). */
    forceReducedMotion?: boolean;
  }>(),
  {
    seconds: 5,
    variant: "fill",
    size: "md",
    label: "Desfazer",
    whenExpired: "hide",
    forceReducedMotion: false,
  },
);
const emit = defineEmits<{ undo: []; expire: [] }>();

const motion = usePreferredReducedMotion();
const reduced = computed(() => props.forceReducedMotion || motion.value === "reduce");

const deadline = ref(0);
const now = ref(0);
const expired = ref(false);
const announcement = ref("");
let timer: ReturnType<typeof setInterval> | undefined;

const remainingMs = computed(() => Math.max(0, deadline.value - now.value));
const remainingSeconds = computed(() => Math.ceil(remainingMs.value / 1000));
const deadlineText = computed(() =>
  deadline.value
    ? new Date(deadline.value).toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "",
);
const descriptionId = useId();

function stop() {
  if (timer) clearInterval(timer);
  timer = undefined;
}

function start() {
  stop();
  expired.value = false;
  now.value = Date.now();
  deadline.value = now.value + props.seconds * 1000;
  announcement.value = `Dá para desfazer por ${props.seconds} segundos.`;
  timer = setInterval(() => {
    now.value = Date.now();
    if (remainingMs.value <= 0) {
      stop();
      expired.value = true;
      announcement.value = "Não dá mais para desfazer.";
      emit("expire");
    }
  }, 200);
}

function onClick() {
  if (expired.value) return;
  stop();
  emit("undo");
}

onMounted(start);
onBeforeUnmount(stop);
defineExpose({ restart: start });

// A animação é CSS (uma só, do tamanho da janela), para não redesenhar o botão a cada
// quadro. O `key` reinicia a animação quando a janela recomeça.
const animationStyle = computed(() => ({ animationDuration: `${props.seconds}s` }));
const ringSize = computed(() => (props.size === "xl" ? 28 : 20));
const ringRadius = computed(() => ringSize.value / 2 - 2);
const ringLength = computed(() => 2 * Math.PI * ringRadius.value);
const showRing = computed(() => props.variant === "ring" && !reduced.value);
</script>

<template>
  <div v-if="!(expired && whenExpired === 'hide')" class="inline-flex">
    <NuxtButton
      color="neutral"
      variant="outline"
      :size="size"
      icon="lucide:undo-2"
      :disabled="expired"
      :aria-describedby="descriptionId"
      class="relative isolate overflow-hidden tabular-nums"
      :data-undo-variant="variant"
      :data-undo-reduced="reduced || undefined"
      @click="onClick"
    >
      <span
        v-if="variant === 'fill' && !reduced && !expired"
        :key="deadline"
        aria-hidden="true"
        class="undo-fill pointer-events-none absolute inset-0 -z-10 origin-left bg-primary/20"
        :style="animationStyle"
      />
      <span>{{ label }}</span>
      <span
        v-if="!expired && (reduced || variant === 'ring')"
        aria-hidden="true"
        class="relative inline-grid place-items-center"
        :style="showRing ? { width: `${ringSize}px`, height: `${ringSize}px` } : undefined"
        data-undo-count
      >
        <svg
          v-if="showRing"
          :key="deadline"
          :width="ringSize"
          :height="ringSize"
          class="absolute inset-0 -rotate-90"
        >
          <circle
            :cx="ringSize / 2"
            :cy="ringSize / 2"
            :r="ringRadius"
            fill="none"
            stroke-width="2"
            class="stroke-(--ui-border)"
          />
          <circle
            :cx="ringSize / 2"
            :cy="ringSize / 2"
            :r="ringRadius"
            fill="none"
            stroke-width="2"
            stroke-linecap="round"
            class="undo-ring stroke-(--ui-primary)"
            :stroke-dasharray="ringLength"
            :style="{ ...animationStyle, '--undo-ring-length': `${ringLength}` }"
          />
        </svg>
        <span :class="showRing ? 'text-[11px] font-semibold leading-none' : 'text-muted'">
          {{ showRing ? remainingSeconds : `${remainingSeconds} s` }}
        </span>
      </span>
    </NuxtButton>
    <span :id="descriptionId" class="sr-only">
      {{ expired ? "O tempo para desfazer acabou." : `Disponível até ${deadlineText}.` }}
    </span>
    <span class="sr-only" aria-live="polite">{{ announcement }}</span>
  </div>
</template>

<style scoped>
.undo-fill {
  animation-name: undo-fill;
  animation-timing-function: linear;
  animation-fill-mode: forwards;
}
@keyframes undo-fill {
  from {
    transform: scaleX(1);
  }
  to {
    transform: scaleX(0);
  }
}
.undo-ring {
  stroke-dashoffset: 0;
  animation-name: undo-ring;
  animation-timing-function: linear;
  animation-fill-mode: forwards;
}
@keyframes undo-ring {
  from {
    stroke-dashoffset: 0;
  }
  to {
    stroke-dashoffset: var(--undo-ring-length);
  }
}
@media (prefers-reduced-motion: reduce) {
  .undo-fill,
  .undo-ring {
    animation: none;
  }
}
</style>
