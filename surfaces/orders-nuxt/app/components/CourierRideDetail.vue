<script setup lang="ts">
// PRÉVIA (14/11) — o detalhe da corrida: painel lateral que abre ao tocar no cartão.
// O cartão diz o momento e o gesto; o detalhe responde "onde está, quando chega, como
// falo com ele, quanto custou" e guarda os gestos raros (tirar parada, cancelar).
import { rideColor } from "~/presentation/ridePalette";

const props = defineProps<{ number: number }>();
const tone = computed(() => rideColor(props.number - 1));

const stops = [
  { code: "D07", customer: "Lúcia Ferreira", address: "R. Ernani Lacerda de Athayde, 1100 · Bela Suíça", state: "done", at: "12:27", x: 40, y: 66 },
  { code: "D10", customer: "Tiago Martins", address: "Av. Madre Leônia Milito, 450 · Bela Suíça", state: "now", at: "12:41", x: 62, y: 84 },
  { code: "D11", customer: "Sofia Ramos", address: "R. Bento Munhoz da Rocha Neto, 230 · Bela Suíça", state: "next", at: "12:49", x: 82, y: 64 },
];
const store = { x: 30, y: 22 };
const courierAt = { x: 51, y: 75 };
const timeline = [
  { at: "12:02", what: "Corrida chamada", who: "por Ana" },
  { at: "12:04", what: "Léo aceitou", who: "" },
  { at: "12:12", what: "Léo chegou na loja", who: "" },
  { at: "12:15", what: "Saiu com 3 sacolas", who: "entregue por Ana" },
  { at: "12:27", what: "D07 entregue", who: "Lúcia Ferreira" },
];
const path = computed(() => [store, ...stops].map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" "));
</script>

<template>
  <aside class="flex h-full w-[30rem] flex-col overflow-hidden bg-default shadow-2xl ring-1 ring-default" data-ride-detail>
    <header class="flex items-start gap-3 border-b border-default px-5 py-4" :style="{ borderTop: `6px solid ${tone.bg}` }">
      <span class="grid size-9 shrink-0 place-items-center rounded-lg text-lg font-bold" :style="{ background: tone.bg, color: tone.fg }">{{ number }}</span>
      <div class="min-w-0 flex-1">
        <p class="op-title font-semibold text-highlighted">Corrida {{ number }} · Em rota</p>
        <p class="op-body text-muted">D10 previsto às 12:41 · 1 de 3 entregues</p>
      </div>
      <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" aria-label="Fechar" />
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <!-- onde está agora -->
      <div class="relative mx-5 mt-4 h-48 overflow-hidden rounded-xl bg-[#f3ede3] ring-1 ring-default">
        <svg class="absolute inset-0 size-full" aria-hidden="true">
          <defs><pattern id="det-streets" width="40" height="40" patternUnits="userSpaceOnUse" patternTransform="rotate(-12)"><path d="M40 0H0V40" fill="none" stroke="#fff" stroke-width="5" /><path d="M40 0H0V40" fill="none" stroke="#e4dccd" stroke-width="1" /></pattern></defs>
          <rect width="100%" height="100%" fill="url(#det-streets)" />
        </svg>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="absolute inset-0 size-full" aria-hidden="true">
          <path :d="path" fill="none" :stroke="tone.bg" vector-effect="non-scaling-stroke" style="stroke-width: 3px" stroke-linejoin="round" stroke-linecap="round" />
        </svg>
        <span class="absolute grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-inverted text-inverted ring-4 ring-white" :style="{ left: `${store.x}%`, top: `${store.y}%` }"><NuxtIcon name="i-lucide-store" class="size-4" /></span>
        <span
          v-for="(s, i) in stops"
          :key="s.code"
          class="absolute grid size-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full op-micro font-semibold shadow"
          :class="s.state === 'done' ? 'bg-success text-white' : ''"
          :style="{ left: `${s.x}%`, top: `${s.y}%`, ...(s.state === 'done' ? {} : { background: tone.bg, color: tone.fg }) }"
        ><NuxtIcon v-if="s.state === 'done'" name="i-lucide-check" class="size-3.5" /><template v-else>{{ i + 1 }}</template></span>
        <span class="absolute grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-white text-highlighted shadow-lg ring-2" :style="{ left: `${courierAt.x}%`, top: `${courierAt.y}%`, '--tw-ring-color': tone.bg }" title="Léo agora"><NuxtIcon name="i-lucide-bike" class="size-4" /></span>
        <p class="absolute top-2 left-2 rounded-md bg-white/90 px-2 py-1 op-micro text-toned shadow-sm">Posição de 1 min atrás · pela TaOn</p>
      </div>

      <!-- quem leva, e como falar com ele -->
      <div class="mx-5 mt-4 flex items-center gap-3 rounded-xl bg-elevated/60 p-3">
        <NuxtAvatar text="L" size="lg" />
        <div class="min-w-0 flex-1">
          <p class="op-label font-semibold text-highlighted">Léo</p>
          <p class="op-micro text-muted">Moto azul · JKL7M89</p>
        </div>
        <NuxtButton icon="i-lucide-phone" color="neutral" variant="outline" label="Ligar" />
        <NuxtButton icon="i-lucide-message-circle" color="neutral" variant="outline" square aria-label="WhatsApp do Léo" />
      </div>

      <!-- as paradas -->
      <section class="mx-5 mt-5">
        <p class="op-micro font-semibold text-muted">Paradas</p>
        <ol class="mt-2 flex flex-col">
          <li v-for="(s, i) in stops" :key="s.code" class="relative flex gap-3 pb-4 last:pb-0">
            <span v-if="i < stops.length - 1" class="absolute top-7 bottom-0 left-3.5 w-px" :class="s.state === 'done' ? 'bg-success/60' : 'bg-default'" aria-hidden="true" />
            <span class="relative z-10 grid size-7 shrink-0 place-items-center rounded-full op-micro font-semibold" :class="s.state === 'done' ? 'bg-success text-white' : s.state === 'now' ? 'ring-4' : ''" :style="s.state === 'done' ? {} : { background: tone.bg, color: tone.fg, '--tw-ring-color': `${tone.bg}40` }">
              <NuxtIcon v-if="s.state === 'done'" name="i-lucide-check" class="size-3.5" /><template v-else>{{ i + 1 }}</template>
            </span>
            <div class="min-w-0 flex-1">
              <p class="flex items-baseline gap-2">
                <span class="op-body font-medium text-highlighted">{{ s.code }} · {{ s.customer }}</span>
                <span class="ml-auto op-micro tabular-nums" :class="s.state === 'done' ? 'text-success' : 'text-muted'">{{ s.state === "done" ? `entregue ${s.at}` : `previsto ${s.at}` }}</span>
              </p>
              <p class="truncate op-micro text-muted">{{ s.address }}</p>
              <NuxtButton class="-ml-2" size="xs" color="neutral" variant="link" label="Abrir o pedido" trailing-icon="i-lucide-arrow-up-right" />
            </div>
          </li>
        </ol>
      </section>

      <!-- o que aconteceu -->
      <section class="mx-5 mt-5">
        <p class="op-micro font-semibold text-muted">O que aconteceu</p>
        <ul class="mt-2 flex flex-col gap-1.5">
          <li v-for="t in timeline" :key="t.at + t.what" class="flex gap-3 op-body">
            <span class="w-11 shrink-0 tabular-nums text-muted">{{ t.at }}</span>
            <span class="text-highlighted">{{ t.what }}<span v-if="t.who" class="text-muted"> · {{ t.who }}</span></span>
          </li>
        </ul>
      </section>

      <!-- quanto custou -->
      <section class="mx-5 mt-5 mb-5 grid grid-cols-2 gap-2">
        <div class="rounded-xl bg-elevated/60 p-3">
          <p class="op-micro text-muted">A corrida (casa paga)</p>
          <p class="op-title font-semibold tabular-nums text-highlighted">R$ 18,40</p>
        </div>
        <div class="rounded-xl bg-elevated/60 p-3">
          <p class="op-micro text-muted">Frete dos clientes</p>
          <p class="op-title font-semibold tabular-nums text-highlighted">R$ 24,00</p>
        </div>
      </section>
    </div>

    <footer class="flex gap-2 border-t border-default px-5 py-3">
      <NuxtButton color="neutral" variant="outline" icon="i-lucide-split" label="Tirar parada" />
      <NuxtButton color="neutral" variant="ghost" icon="i-lucide-external-link" label="Na TaOn" />
      <NuxtButton class="ml-auto" color="error" variant="ghost" icon="i-lucide-circle-x" label="Cancelar corrida" />
    </footer>
  </aside>
</template>
