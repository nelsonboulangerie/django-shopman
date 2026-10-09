<script setup lang="ts">
// O botão de uma ação que só vale até um prazo, com o tempo DENTRO dele: o fundo
// esvazia até a janela fechar (dono, 09/10/2026, proposta #1575: "é exatamente assim:
// fundo esvazia! ótimo! poderia canonizar isso para outros casos de uso"). Desfazer o
// Pronto na Cozinha, desfazer a saída no Gestor, qualquer gesto que o sistema segura
// por alguns segundos antes de valer.
//
// Regras da peça:
//   - É o `NuxtButton` do conjunto mínimo (md/xl × solid/outline × primary/neutral/
//     error), com uma camada atrás do rótulo. Não é botão novo.
//   - A MENOR interferência possível (dono, 09/10/2026): o botão com prazo é o MESMO
//     botão que ele substitui (mesma cor, mesma variante, mesmo tamanho, mesmo lugar).
//     Quem chama passa a aparência do botão de origem; só o TEXTO muda ("Pronto 0131"
//     vira "Desfazer 0131") e o fundo esvazia atrás dele. Nada de trocar para
//     contornado/neutro, nada de mudar altura ou largura.
//   - O fundo que esvazia é a PRÓPRIA cor do botão, translúcida: no sólido, a cor um
//     tom mais funda (a superfície invertida a 30% por cima), que sempre AUMENTA o
//     contraste do rótulo; no contornado, a cor do rótulo a 10%. Ao fim da janela o
//     botão está idêntico ao de origem. AA nos dois temas: `tests/timedButtonContrast.test.ts`.
//   - O prazo é ABSOLUTO (`until`, epoch ms ou ISO). Montar de novo, mudar de lugar ou
//     a aba dormir em segundo plano não reinicia a janela: o fim é o mesmo instante.
//     O prazo do servidor vem com `server-now` (o relógio dele), e o desvio do
//     dispositivo sai da conta. `since` ou `duration` dizem o tamanho da janela, para
//     o fundo começar cheio na proporção certa.
//   - A animação é UMA só, em CSS, do tamanho da janela, começando onde a janela já
//     está (atraso negativo): o botão não redesenha a cada quadro.
//   - Movimento reduzido (`prefers-reduced-motion: reduce`): nada anima; o botão
//     mostra o número de segundos ("4 s"), que muda uma vez por segundo.
//   - Acessível: o nome do botão é o rótulo, fixo (ou o `aria-label` de quem chama).
//     O tempo vai numa descrição fixa, "Disponível até 10:42:15", que não muda a cada
//     segundo; uma região educada fala duas vezes, ao abrir e ao fechar a janela. O
//     número visível é `aria-hidden`.
//   - Ao fim, `expire` sai uma vez, e o botão some (`when-expired="hide"`, o padrão)
//     ou fica desabilitado (`"disable"`).
//
// `class`, `data-*` e `aria-*` chegam ao botão.
// Imports explícitos (nenhum auto-import do Nuxt): a peça é SFC puro, e os harnesses
// sem runtime Nuxt dos apps a montam de verdade.
import { usePreferredReducedMotion } from "@vueuse/core";
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from "vue";
import {
  clockOffsetMs,
  remainingSeconds,
  timedAnnouncement,
  timedDescription,
  timedWindow,
  type Instant,
} from "../presentation/timedAction";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    label: string;
    /** Fim da janela (epoch em ms ou ISO). */
    until: Instant;
    /** Começo da janela (epoch em ms ou ISO). */
    since?: Instant;
    /** Tamanho da janela em ms, quando não há `since`. */
    duration?: number;
    /** O "agora" do servidor (ISO) que deu `until`/`since`: corrige o relógio do dispositivo. */
    serverNow?: string;
    whenExpired?: "hide" | "disable";
    size?: "md" | "xl";
    variant?: "solid" | "outline";
    /** `primary`/`neutral`/`error` do conjunto; as cores de aviso só como ação de um
     *  `NuxtAlert` daquela cor (a exceção declarada do conjunto mínimo). */
    color?: "primary" | "neutral" | "error" | "info" | "success" | "warning";
    /** Ícone no formato `i-lucide-nome`. */
    icon?: string;
    block?: boolean;
    disabled?: boolean;
    loading?: boolean;
    /** Força a leitura sem movimento (o catálogo mostra os dois modos lado a lado). */
    reducedMotion?: boolean;
  }>(),
  {
    since: undefined,
    duration: undefined,
    serverNow: undefined,
    whenExpired: "hide",
    size: "md",
    variant: "solid",
    color: "primary",
    icon: undefined,
    block: false,
    disabled: false,
    loading: false,
    reducedMotion: false,
  },
);
const emit = defineEmits<{ click: [event: MouseEvent]; expire: [] }>();

const motion = usePreferredReducedMotion();
const reduced = computed(() => props.reducedMotion || motion.value === "reduce");

// Tudo que depende do relógio só começa no cliente: o servidor não sabe o "agora"
// de quem vai tocar, e a hidratação não pode divergir.
const ready = ref(false);
const now = ref(0);
const offset = ref(0);
const firstSeen = ref(0);
const expired = ref(false);
const announcement = ref("");
// Muda a cada janela nova: reinicia a animação do fundo.
const armKey = ref(0);
const fillStyle = ref<Record<string, string>>({});

const win = computed(() =>
  timedWindow(
    {
      until: props.until,
      since: props.since,
      duration: props.duration,
      offsetMs: offset.value,
      firstSeenMs: firstSeen.value,
    },
    now.value,
  ),
);
const seconds = computed(() => remainingSeconds(win.value.remainingMs));
const description = computed(() => timedDescription(win.value.untilMs, expired.value));
const descriptionId = useId();
const hidden = computed(() => expired.value && props.whenExpired === "hide");
const showFill = computed(() => ready.value && !reduced.value && !expired.value);
const showCount = computed(() => ready.value && reduced.value && !expired.value);

let expiryTimer: ReturnType<typeof setTimeout> | undefined;
let secondTimer: ReturnType<typeof setInterval> | undefined;
let announceTimer: ReturnType<typeof setTimeout> | undefined;

function clearTimers() {
  if (expiryTimer) clearTimeout(expiryTimer);
  if (secondTimer) clearInterval(secondTimer);
  expiryTimer = undefined;
  secondTimer = undefined;
}

function announce(text: string) {
  // A região já existe na página; o texto entra um instante depois, para o leitor
  // de tela perceber a mudança.
  if (announceTimer) clearTimeout(announceTimer);
  announceTimer = setTimeout(() => (announcement.value = text), 50);
}

function close() {
  clearTimers();
  if (expired.value) return;
  expired.value = true;
  announce(timedAnnouncement(props.label, win.value.untilMs, true));
  emit("expire");
}

function check() {
  now.value = Date.now();
  if (win.value.expired) close();
}

function arm() {
  clearTimers();
  now.value = Date.now();
  offset.value = clockOffsetMs(props.serverNow, now.value);
  firstSeen.value = now.value;
  const current = win.value;
  if (current.expired) {
    close();
    return;
  }
  const reopened = expired.value || !ready.value;
  expired.value = false;
  armKey.value += 1;
  fillStyle.value = {
    animationDuration: `${current.totalMs}ms`,
    animationDelay: `-${current.elapsedMs}ms`,
  };
  ready.value = true;
  if (reopened) announce(timedAnnouncement(props.label, current.untilMs, false));
  expiryTimer = setTimeout(check, current.remainingMs + 20);
  if (reduced.value) secondTimer = setInterval(check, 1000);
}

function onVisibility() {
  if (document.visibilityState === "visible" && ready.value && !expired.value) check();
}

function onClick(event: MouseEvent) {
  if (expired.value) return;
  check();
  if (expired.value) return;
  emit("click", event);
}

onMounted(() => {
  arm();
  document.addEventListener("visibilitychange", onVisibility);
});
onBeforeUnmount(() => {
  clearTimers();
  if (announceTimer) clearTimeout(announceTimer);
  document.removeEventListener("visibilitychange", onVisibility);
});
watch(
  () => [toKey(props.until), toKey(props.since), props.duration, props.serverNow],
  () => {
    if (ready.value || expired.value) arm();
  },
);
watch(reduced, () => {
  if (ready.value && !expired.value) arm();
});

function toKey(value: Instant | undefined): string {
  return value === undefined ? "" : String(value);
}

// A camada que esvazia: a própria cor do botão, translúcida. Sólido: um tom mais fundo
// da cor (a superfície invertida a 30% por cima: escurece o latão sob o rótulo branco
// no claro, clareia o dourado sob o rótulo escuro no escuro), e o contraste só sobe.
// O neutro sólido JÁ é a superfície invertida, então o tom vem do fundo da página.
// Contornado: a cor do rótulo (`currentColor`) a 10%.
const fillClass = computed(() => {
  if (props.variant === "outline") return "bg-current/10";
  return props.color === "neutral" ? "bg-(--ui-bg)/30" : "bg-(--ui-bg-inverted)/30";
});
</script>

<template>
  <span
    :class="block ? 'flex w-full min-w-0' : 'inline-flex'"
    data-timed-button
    :data-timed-expired="expired || undefined"
  >
    <NuxtButton
      v-if="!hidden"
      v-bind="$attrs"
      :color="color"
      :variant="variant"
      :size="size"
      :icon="icon"
      :block="block"
      :loading="loading"
      :disabled="disabled || expired"
      :aria-describedby="descriptionId"
      class="relative isolate overflow-hidden tabular-nums"
      :data-timed-reduced="reduced || undefined"
      @click="onClick"
    >
      <span
        v-if="showFill"
        :key="armKey"
        aria-hidden="true"
        class="timed-fill pointer-events-none absolute inset-0 -z-10 origin-left"
        :class="fillClass"
        :style="fillStyle"
        data-timed-fill
      />
      <span>{{ label }}</span>
      <span v-if="showCount" aria-hidden="true" class="opacity-75" data-timed-count>{{ seconds }} s</span>
    </NuxtButton>
    <span :id="descriptionId" class="sr-only" data-timed-description>{{ description }}</span>
    <span class="sr-only" aria-live="polite" data-timed-announcement>{{ announcement }}</span>
  </span>
</template>

<style scoped>
.timed-fill {
  animation-name: timed-fill-drain;
  animation-timing-function: linear;
  animation-fill-mode: both;
}
@keyframes timed-fill-drain {
  from {
    transform: scaleX(1);
  }
  to {
    transform: scaleX(0);
  }
}
@media (prefers-reduced-motion: reduce) {
  .timed-fill {
    animation: none;
  }
}
</style>
