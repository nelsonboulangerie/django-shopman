<script setup lang="ts">
// PRÉVIA (16/11, DEV-2026-030, M2b): a página do entregador da casa com o mapa da corrida,
// em retrato e em paisagem (pedido do dono: "SUPER otimizado para mobile, inclusive em modo
// horizontal"). O mapa aqui é desenho; na frente M2b é o Google Maps do Gestor. Não vai ao ar.
import { rideColor } from "~/presentation/ridePalette";

export interface CourierStop {
  code: string;
  name: string;
  street: string;
  extra: string;
  charge: string;
  pay: "cash" | "card" | "paid";
  bags: number;
  x: number;
  y: number;
  state: "open" | "done" | "failed";
}
export interface CourierRide {
  phase: "before" | "route" | "back";
  stops: CourierStop[];
}

const props = defineProps<{ ride: CourierRide; landscape?: boolean }>();
const emit = defineEmits<{ depart: []; mark: [code: string, state: "done" | "failed"]; back: [] }>();
const tone = rideColor(0);
const STORE = { x: 70, y: 250 };

const next = computed(() => props.ride.stops.find((s) => s.state === "open") ?? null);
const nextIndex = computed(() => (next.value ? props.ride.stops.indexOf(next.value) + 1 : 0));
const doneCount = computed(() => props.ride.stops.filter((s) => s.state !== "open").length);
const courier = computed(() => {
  if (props.ride.phase === "before") return STORE;
  if (props.ride.phase === "back") return { x: 120, y: 230 };
  const prev = props.ride.stops[nextIndex.value - 2] ?? STORE;
  const n = next.value ?? STORE;
  return { x: prev.x + (n.x - prev.x) * 0.55, y: prev.y + (n.y - prev.y) * 0.55 };
});
const route = computed(() => [STORE, ...props.ride.stops, STORE].map((p) => `${p.x},${p.y}`).join(" "));
const payTone = (s: CourierStop) => (s.pay === "paid" ? "text-[#0a7a35]" : "text-[#9a4a00]");
</script>

<template>
  <div
    class="relative flex size-full overflow-hidden bg-[#f4f1ea] text-black"
    :class="landscape ? 'flex-row' : 'flex-col'"
    style="font-size: 16px"
  >
    <!-- o mapa: ocupa o que sobra; em paisagem, a esquerda inteira -->
    <div class="relative min-h-0 min-w-0 flex-1">
      <svg viewBox="40 80 330 200" preserveAspectRatio="xMidYMid meet" class="absolute inset-0 size-full" role="img" aria-label="Mapa da corrida">
        <rect x="-600" y="-600" width="1600" height="1600" fill="#ebe7dd" />
        <path d="M-600 230 L 0 200 Q 150 170 400 210 L 1000 240" stroke="#fff" stroke-width="14" fill="none" />
        <path d="M140 -600 L 150 0 Q 170 160 140 320 L 130 1000" stroke="#fff" stroke-width="11" fill="none" />
        <path d="M-600 110 L 1000 40" stroke="#fff" stroke-width="8" fill="none" />
        <path d="M270 -600 L 330 1000" stroke="#fff" stroke-width="8" fill="none" />
        <path d="M-600 420 L 1000 380" stroke="#fff" stroke-width="8" fill="none" />
        <path d="M-60 -600 L 0 1000" stroke="#fff" stroke-width="8" fill="none" />
        <rect x="200" y="230" width="70" height="50" rx="8" fill="#d7e8cf" />
        <polyline :points="route" fill="none" stroke="#111" stroke-width="9" stroke-linejoin="round" stroke-linecap="round" opacity="0.85" />
        <polyline :points="route" fill="none" :stroke="tone.bg" stroke-width="5" stroke-linejoin="round" stroke-linecap="round" />
        <rect :x="STORE.x - 13" :y="STORE.y - 13" width="26" height="26" rx="6" fill="#111" />
        <text :x="STORE.x" :y="STORE.y + 4" font-size="9" font-weight="700" fill="#fff" text-anchor="middle">Loja</text>
        <g v-for="(s, i) in ride.stops" :key="s.code">
          <circle :cx="s.x" :cy="s.y" :r="next && next.code === s.code ? 17 : 14" :fill="s.state === 'open' ? '#fff' : '#bdbdbd'" stroke="#111" stroke-width="3" />
          <text :x="s.x" :y="s.y + 5" font-size="14" font-weight="800" text-anchor="middle" fill="#111">{{ s.state === "done" ? "✓" : i + 1 }}</text>
        </g>
        <circle v-if="ride.phase !== 'before'" :cx="courier.x" :cy="courier.y" r="22" fill="#0047ff" opacity="0.15" />
        <circle v-if="ride.phase !== 'before'" :cx="courier.x" :cy="courier.y" r="8" fill="#0047ff" stroke="#fff" stroke-width="3" />
      </svg>

      <!-- topo do mapa: a corrida e o sinal de que a posição está indo -->
      <div class="absolute inset-x-2 top-2 flex items-center gap-2" style="padding-top: env(safe-area-inset-top)">
        <span class="grid size-11 shrink-0 place-items-center rounded-xl text-2xl font-black shadow" :style="{ background: tone.bg, color: tone.fg }">A</span>
        <div class="flex min-w-0 flex-col rounded-xl bg-white/95 px-3 py-1.5 shadow">
          <span class="truncate text-[15px] font-bold leading-tight">Corrida A · Diego</span>
          <span class="truncate text-[13px] leading-tight text-black/70">{{ doneCount }} de {{ ride.stops.length }} entregues · R$ 15,00</span>
        </div>
        <span v-if="ride.phase !== 'before'" class="ms-auto flex items-center gap-1 rounded-full bg-white/95 px-2.5 py-1.5 text-[13px] font-semibold shadow">
          <span class="size-2 rounded-full bg-[#00a03c]" />Posição enviada
        </span>
      </div>
      <button type="button" class="absolute end-2 bottom-2 grid size-12 place-items-center rounded-full bg-white text-black shadow-lg" aria-label="Centralizar em mim">
        <NuxtIcon name="i-lucide-locate-fixed" class="size-6" />
      </button>
    </div>

    <!-- o painel: embaixo no retrato, à direita na paisagem; só o que importa agora -->
    <section
      class="flex shrink-0 flex-col overflow-y-auto bg-white shadow-[0_-6px_18px_rgba(0,0,0,0.12)]"
      :class="landscape ? 'w-[46%] gap-1 border-s border-black/10 px-3 py-2' : 'max-h-[52%] gap-2 rounded-t-2xl p-3'"
      style="padding-bottom: max(0.75rem, env(safe-area-inset-bottom))"
    >
      <template v-if="ride.phase === 'before'">
        <p class="text-[13px] font-semibold uppercase tracking-wide text-black/60">Antes de sair</p>
        <p class="text-[17px] font-bold">Leve da loja</p>
        <ul class="flex flex-col gap-1 text-[16px]">
          <li>3 sacolas: 2 de A47 e 1 de C03</li>
          <li>Troco: R$ 70,00</li>
          <li class="flex items-center gap-1.5">Maquininha <span class="size-3 rounded-full bg-[#2563eb]" /> azul</li>
        </ul>
        <button type="button" class="mt-1 min-h-14 rounded-xl bg-black text-[19px] font-extrabold text-white" @click="emit('depart')">Saí da loja</button>
      </template>

      <template v-else-if="ride.phase === 'route' && next">
        <div class="flex items-baseline gap-2">
          <span class="grid size-8 shrink-0 place-items-center rounded-full bg-black text-[15px] font-black text-white">{{ nextIndex }}</span>
          <span class="text-[21px] font-extrabold leading-tight">{{ next.code }} · {{ next.name }}</span>
          <span class="ms-auto whitespace-nowrap text-[13px] font-semibold text-black/60">1,2 km · 4 min</span>
        </div>
        <p class="text-[17px] font-semibold leading-snug">{{ next.street }}</p>
        <p class="text-[15px] leading-snug text-black/70">{{ next.extra }}</p>
        <p class="text-[16px] font-bold" :class="payTone(next)">{{ next.charge }}</p>
        <div class="grid grid-cols-2 gap-2">
          <a href="#" class="flex min-h-12 items-center justify-center gap-1.5 rounded-xl bg-black/5 text-[16px] font-bold"><NuxtIcon name="i-lucide-phone" class="size-5" />Ligar</a>
          <a href="#" class="flex min-h-12 items-center justify-center gap-1.5 rounded-xl bg-black/5 text-[16px] font-bold"><NuxtIcon name="i-lucide-navigation" class="size-5" />Waze</a>
        </div>
        <button type="button" class="min-h-14 rounded-xl bg-black text-[19px] font-extrabold text-white" @click="emit('mark', next.code, 'done')">Entreguei {{ next.code }}</button>
        <button type="button" class="text-[15px] font-semibold text-black/70 underline" :class="landscape ? 'min-h-10' : 'min-h-11'" @click="emit('mark', next.code, 'failed')">Não consegui entregar</button>
        <p v-if="ride.stops.length > nextIndex && !landscape" class="text-[14px] text-black/60">Depois: {{ ride.stops.slice(nextIndex).map((s) => s.code).join(", ") }}</p>
      </template>

      <template v-else>
        <p class="text-[17px] font-bold">Todas as paradas feitas.</p>
        <p class="text-[16px]">Volte à loja com a maquininha azul e o dinheiro.</p>
        <button type="button" class="min-h-14 rounded-xl bg-black text-[19px] font-extrabold text-white" @click="emit('back')">Voltei à loja</button>
      </template>
    </section>
  </div>
</template>
