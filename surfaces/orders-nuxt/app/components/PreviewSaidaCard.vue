<script setup lang="ts">
// PRÉVIA (16/11): o cartão da Saída, forma E (dono). Pedido solto, corrida de um
// pedido e corrida de vários compartilham a mesma estrutura (identidade · momento ·
// destino · gesto). A corrida ganha o trilho da cor e a letra no canto superior
// direito, com a quantidade de pedidos à esquerda dela; a de vários ganha o
// empilhamento. Os códigos só recolhem ("A51 ∙ C07 +1") quando falta espaço.
// Não vai ao ar.
import { rideColor } from "~/presentation/ridePalette";

export interface SaidaStop { code: string; place: string; bags?: number; done?: boolean; note?: string }
export interface SaidaItem {
  key: string;
  /** A corrida: 1 vira A, 2 vira B… (a cor segue o mesmo índice). */
  ride?: number;
  icon: string;
  moment: string;
  momentTone?: "success" | "info" | "warning" | "error" | "neutral";
  hint?: string;
  stops: SaidaStop[];
  action?: { label: string; icon: string };
  /** Segundo gesto, opcional: aparece ao lado do primeiro, em contorno. */
  secondaryAction?: { label: string; icon: string };
  pulse?: boolean;
}

const props = defineProps<{ item: SaidaItem }>();
const SEP = "∙";
const tone = computed(() => (props.item.ride ? rideColor(props.item.ride - 1) : null));
const letter = computed(() => (props.item.ride ? String.fromCharCode(64 + props.item.ride) : ""));
const many = computed(() => props.item.stops.length > 1);
const layers = computed(() => Math.min(props.item.stops.length - 1, 2));
const toneText: Record<string, string> = { success: "text-success", info: "text-info", warning: "text-warning", error: "text-error", neutral: "text-toned" };
const bags = (s: SaidaStop) => (s.bags ? ` · ${s.bags} ${s.bags === 1 ? "sacola" : "sacolas"}` : "");

// Quantos códigos cabem na linha: mede numa cópia invisível e recolhe o resto em "+N".
const box = ref<HTMLElement | null>(null);
const probe = ref<HTMLElement | null>(null);
const fit = ref(props.item.stops.length);
function measure() {
  if (!box.value || !probe.value) return;
  const avail = box.value.clientWidth;
  const parts = Array.from(probe.value.querySelectorAll<HTMLElement>("[data-code]"));
  const sep = probe.value.querySelector<HTMLElement>("[data-sep]")?.offsetWidth ?? 0;
  const plus = probe.value.querySelector<HTMLElement>("[data-plus]")?.offsetWidth ?? 0;
  let used = 0;
  let n = 0;
  for (let i = 0; i < parts.length; i++) {
    const w = parts[i]!.offsetWidth + (i ? sep : 0);
    const rest = parts.length - (i + 1);
    if (used + w + (rest ? plus + sep : 0) > avail) break;
    used += w;
    n++;
  }
  fit.value = Math.max(1, n);
}
let ro: ResizeObserver | null = null;
onMounted(() => {
  measure();
  ro = new ResizeObserver(measure);
  if (box.value) ro.observe(box.value);
});
onBeforeUnmount(() => ro?.disconnect());
const shown = computed(() => props.item.stops.slice(0, fit.value));
const hidden = computed(() => props.item.stops.length - fit.value);
</script>

<template>
  <div class="relative isolate" :style="{ paddingBottom: `${layers * 6}px` }">
    <!-- o empilhamento: uma camada por pedido a mais, até duas -->
    <div
      v-for="l in layers"
      :key="l"
      aria-hidden="true"
      class="absolute inset-x-0 top-0 rounded-xl border border-accented bg-default shadow-xs"
      :style="{ bottom: `${layers * 6}px`, transform: `translateY(${l * 6}px) scaleX(${1 - l * 0.04})`, zIndex: 3 - l }"
    />

    <article class="relative z-10 flex flex-col overflow-hidden rounded-xl border border-default bg-default shadow-xs">
      <span v-if="tone" class="h-1.5 shrink-0" :style="{ background: tone.bg }" aria-hidden="true" />

      <div class="flex min-w-0 flex-1 flex-col gap-1 p-3">
        <!-- identidade: os códigos à esquerda; a quantidade e a letra no canto -->
        <div class="flex min-w-0 items-center gap-2">
          <div ref="box" class="relative min-w-0 flex-1 overflow-hidden">
            <span class="flex items-baseline gap-x-1 whitespace-nowrap text-xl leading-tight font-bold tabular-nums text-highlighted">
              <template v-for="(s, i) in shown" :key="s.code">
                <span v-if="i" class="font-normal text-dimmed">{{ SEP }}</span>
                <span :class="s.done ? 'text-dimmed line-through decoration-2' : ''">{{ s.code }}</span>
              </template>
              <span v-if="hidden > 0" class="ms-1 self-center rounded-md bg-elevated px-1.5 op-micro font-semibold text-toned">+{{ hidden }}</span>
            </span>
            <!-- cópia invisível só para medir -->
            <span ref="probe" aria-hidden="true" class="pointer-events-none invisible absolute top-0 left-0 flex items-baseline gap-x-1 whitespace-nowrap text-xl leading-tight font-bold tabular-nums">
              <template v-for="(s, i) in item.stops" :key="s.code">
                <span v-if="i" data-sep class="font-normal">{{ SEP }}</span>
                <span data-code>{{ s.code }}</span>
              </template>
              <span data-plus class="ms-1 rounded-md px-1.5 op-micro font-semibold">+9</span>
            </span>
          </div>
          <template v-if="tone">
            <span class="shrink-0 op-micro whitespace-nowrap text-muted">{{ many ? `${item.stops.length} pedidos` : "1 pedido" }}</span>
            <span
              class="grid size-7 shrink-0 place-items-center rounded-md op-label font-bold"
              :style="{ background: tone.bg, color: tone.fg }"
              :aria-label="`Corrida ${letter}`"
            >{{ letter }}</span>
          </template>
        </div>

        <!-- momento -->
        <p class="mt-1 flex items-center gap-1.5 op-body font-semibold" :class="toneText[item.momentTone ?? 'neutral']">
          <NuxtIcon :name="item.icon" class="size-4 shrink-0" :class="item.pulse ? 'motion-safe:animate-pulse' : ''" />
          <span class="min-w-0">{{ item.moment }}</span>
        </p>
        <p v-if="item.hint" class="op-micro text-muted">{{ item.hint }}</p>

        <!-- destino: uma linha no único, uma por parada no de vários -->
        <ul class="flex flex-col gap-0.5">
          <li v-for="s in item.stops" :key="s.code" class="flex min-w-0 items-baseline gap-1.5 op-micro">
            <span v-if="many" class="w-8 shrink-0 font-semibold tabular-nums" :class="s.done ? 'text-dimmed line-through' : 'text-toned'">{{ s.code }}</span>
            <span class="min-w-0 text-muted">{{ s.place }}{{ bags(s) }}<template v-if="s.note"> · {{ s.note }}</template></span>
          </li>
        </ul>

        <!-- gesto -->
        <div v-if="item.action" class="flex flex-wrap gap-2 pt-1.5">
          <NuxtButton :icon="item.action.icon" :label="item.action.label" />
          <NuxtButton
            v-if="item.secondaryAction"
            color="neutral"
            variant="outline"
            :icon="item.secondaryAction.icon"
            :label="item.secondaryAction.label"
          />
        </div>
      </div>
    </article>
  </div>
</template>
