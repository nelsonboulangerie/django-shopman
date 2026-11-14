<script setup lang="ts">
// PRÉVIA (14/11) — o detalhe da corrida: painel lateral que abre ao tocar na corrida
// (espelho no Painel, linha "Na rua", moto ou parada no mapa da página Entregas).
// O espelho diz o momento e o gesto; o detalhe responde "onde está, quando termina,
// como falo com ele, quanto custou" e guarda os gestos raros.
//
// Só promete o que a API da TaOn entrega (estudo de 14/11):
//  · posição da moto: webhook "posicao" a cada 10 s (ou GET /posicaoCondutor),
//    só depois do aceite;
//  · entregador: nome, telefone, placa e modelo (GET /v1/request/{id});
//  · paradas: situação de cada uma ("parada finalizada" chega com a hora);
//  · previsão: chegada à loja no aceite e a duração da viagem. A TaOn NÃO dá a hora
//    de cada parada: a tela mostra a hora de término da rota, não uma por parada;
//  · link de acompanhamento (GET /obterLinkRastreio/{id});
//  · custo: cotação antes, valor final quando a corrida fecha;
//  · cancelar: só antes de ele sair com as sacolas. Depois, só a central.
//  · trocar ou tirar parada: a API não tem. Antes do aceite, dá para refazer a
//    corrida (cancela e chama outra); depois, não.
import { rideColor } from "~/presentation/ridePalette";

const props = defineProps<{ number: number }>();
defineEmits<{ close: [] }>();
const tone = computed(() => rideColor(props.number - 1));
const GREY = "#c9ccd1";
const GREY_STOP = "#aeb3ba";

const stops = [
  { code: "D01", customer: "Lúcia Ferreira", address: "R. Ernani Lacerda de Athayde, 1100 · Bela Suíça", state: "done", at: "12:27", x: 40, y: 66 },
  { code: "D02", customer: "Tiago Martins", address: "Av. Madre Leônia Milito, 450 · Bela Suíça", state: "now", x: 62, y: 84 },
  { code: "D03", customer: "Sofia Ramos", address: "R. Bento Munhoz da Rocha Neto, 230 · Bela Suíça", state: "next", x: 82, y: 64 },
];
const store = { x: 30, y: 22 };
const courierAt = { x: 51, y: 75 };
const timeline = [
  { at: "12:02", what: "Corrida chamada", who: "por Ana" },
  { at: "12:04", what: "Léo aceitou", who: "chegada prevista 12:12" },
  { at: "12:11", what: "Léo chegou na loja", who: "" },
  { at: "12:15", what: "Saiu com 3 sacolas", who: "entregue por Ana" },
  { at: "12:27", what: "D01 entregue", who: "Lúcia Ferreira" },
];
const path = computed(() => [store, ...stops].map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" "));
</script>

<template>
  <aside class="flex h-full w-full flex-col overflow-hidden bg-default shadow-2xl ring-1 ring-default sm:w-[30rem]" data-ride-detail>
    <header class="flex items-start gap-3 border-b border-default px-5 py-4" :style="{ borderTop: `6px solid ${tone.bg}` }">
      <span class="grid size-9 shrink-0 place-items-center rounded-lg text-lg font-bold" :style="{ background: tone.bg, color: tone.fg }">{{ number }}</span>
      <div class="min-w-0 flex-1">
        <p class="op-title font-semibold text-highlighted">Corrida {{ number }} · Em rota</p>
        <p class="op-body text-muted">1 de 3 entregues · termina por volta de 12:49</p>
      </div>
      <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" aria-label="Fechar" @click="$emit('close')" />
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <!-- onde está agora: a rota já chamada em cinza, a moto na cor da corrida -->
      <div class="relative mx-5 mt-4 h-48 overflow-hidden rounded-xl bg-[#f3ede3] ring-1 ring-default">
        <svg class="absolute inset-0 size-full" aria-hidden="true">
          <defs><pattern id="det-streets" width="40" height="40" patternUnits="userSpaceOnUse" patternTransform="rotate(-12)"><path d="M40 0H0V40" fill="none" stroke="#fff" stroke-width="5" /><path d="M40 0H0V40" fill="none" stroke="#e4dccd" stroke-width="1" /></pattern></defs>
          <rect width="100%" height="100%" fill="url(#det-streets)" />
        </svg>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="absolute inset-0 size-full" aria-hidden="true">
          <path :d="path" fill="none" :stroke="GREY" vector-effect="non-scaling-stroke" style="stroke-width: 4px" stroke-linejoin="round" stroke-linecap="round" />
        </svg>
        <span class="absolute grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-inverted text-inverted ring-4 ring-white" :style="{ left: `${store.x}%`, top: `${store.y}%` }"><NuxtIcon name="i-lucide-store" class="size-4" /></span>
        <span
          v-for="(s, i) in stops"
          :key="s.code"
          class="absolute grid size-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full op-micro font-semibold text-white shadow"
          :style="{ left: `${s.x}%`, top: `${s.y}%`, background: GREY_STOP }"
        ><NuxtIcon v-if="s.state === 'done'" name="i-lucide-check" class="size-3.5" /><template v-else>{{ i + 1 }}</template></span>
        <span class="absolute flex -translate-x-1/2 -translate-y-1/2 items-center gap-1 rounded-full py-1 pr-2 pl-1 shadow-lg ring-2 ring-white" :style="{ left: `${courierAt.x}%`, top: `${courierAt.y}%`, background: tone.bg, color: tone.fg }" title="Léo agora">
          <span class="grid size-6 place-items-center rounded-full bg-white/20"><NuxtIcon name="i-lucide-bike" class="size-4" /></span>
          <span class="op-label font-bold">{{ number }}</span>
        </span>
        <p class="absolute top-2 left-2 rounded-md bg-white/90 px-2 py-1 op-micro text-toned shadow-sm">Posição de 10 s atrás, pela TaOn</p>
      </div>

      <!-- quem leva, e como falar com ele -->
      <div class="mx-5 mt-4 flex items-center gap-3 rounded-xl bg-elevated/60 p-3">
        <NuxtAvatar text="L" size="lg" />
        <div class="min-w-0 flex-1">
          <p class="op-label font-semibold text-highlighted">Léo</p>
          <p class="op-micro text-muted">Honda CG · JKL7M89</p>
        </div>
        <NuxtButton icon="i-lucide-phone" color="neutral" variant="outline" label="Ligar" />
        <NuxtButton icon="i-lucide-message-circle" color="neutral" variant="outline" square aria-label="WhatsApp do Léo" />
      </div>

      <!-- as paradas -->
      <section class="mx-5 mt-5">
        <p class="op-micro font-semibold text-muted">Paradas, na ordem do percurso</p>
        <ol class="mt-2 flex flex-col">
          <li v-for="(s, i) in stops" :key="s.code" class="relative flex gap-3 pb-4 last:pb-0">
            <span v-if="i < stops.length - 1" class="absolute top-7 bottom-0 left-3.5 w-px bg-default" aria-hidden="true" />
            <span class="relative z-10 grid size-7 shrink-0 place-items-center rounded-full op-micro font-semibold text-white" :style="{ background: GREY_STOP }">
              <NuxtIcon v-if="s.state === 'done'" name="i-lucide-check" class="size-3.5" /><template v-else>{{ i + 1 }}</template>
            </span>
            <div class="min-w-0 flex-1">
              <p class="flex items-baseline gap-2">
                <span class="op-body font-medium" :class="s.state === 'done' ? 'text-muted' : 'text-highlighted'">{{ s.code }} · {{ s.customer }}</span>
                <span class="ml-auto shrink-0 op-micro" :class="s.state === 'done' ? 'text-success' : s.state === 'now' ? 'font-semibold text-highlighted' : 'text-muted'">{{ s.state === "done" ? `entregue às ${s.at}` : s.state === "now" ? "indo para cá" : "depois" }}</span>
              </p>
              <p class="truncate op-micro text-muted">{{ s.address }}</p>
              <NuxtButton class="-ml-2" size="xs" color="neutral" variant="link" label="Abrir o pedido" trailing-icon="i-lucide-arrow-up-right" />
            </div>
          </li>
        </ol>
      </section>

      <!-- o cliente acompanha -->
      <section class="mx-5 mt-5 flex items-center gap-3 rounded-xl border border-default p-3">
        <NuxtIcon name="i-lucide-map-pinned" class="size-5 text-muted" />
        <p class="min-w-0 flex-1 op-body text-toned">Os clientes receberam o link de acompanhamento quando ele saiu.</p>
        <NuxtButton size="sm" color="neutral" variant="outline" icon="i-lucide-copy" label="Copiar link" />
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
          <p class="op-micro text-muted">A corrida (cotação; o valor final vem no fim)</p>
          <p class="op-title font-semibold tabular-nums text-highlighted">R$ 18,40</p>
        </div>
        <div class="rounded-xl bg-elevated/60 p-3">
          <p class="op-micro text-muted">Frete pago pelos clientes</p>
          <p class="op-title font-semibold tabular-nums text-highlighted">R$ 24,00</p>
        </div>
      </section>
    </div>

    <footer class="flex flex-wrap items-center gap-2 border-t border-default px-5 py-3">
      <p class="min-w-0 flex-1 op-micro text-muted">Ele já saiu com as sacolas: cancelar agora só pela central da TaOn.</p>
      <NuxtButton color="neutral" variant="outline" icon="i-lucide-external-link" label="Abrir na TaOn" />
    </footer>
  </aside>
</template>
