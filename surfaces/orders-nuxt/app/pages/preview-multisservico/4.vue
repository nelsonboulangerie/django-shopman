<script setup lang="ts">
// Prévia M2b (DEV-2026-030): a página do entregador da casa com o mapa da corrida, no
// celular em pé e deitado (no suporte da moto). Os dois celulares de mentira mostram a
// MESMA corrida: tocar num muda o outro. Dados fictícios.
import { reactive } from "vue";
import type { CourierRide } from "~/components/MsCourierScreen.vue";

const ride = reactive<CourierRide>({
  phase: "before",
  stops: [
    { code: "A47", name: "Marina", street: "Rua Caracas, 420, apto 41", extra: "Gleba Palhano · Interfone 41", charge: "Cobrar R$ 58,00 em dinheiro · Troco para R$ 100,00", pay: "cash", bags: 2, x: 250, y: 120, state: "open" },
    { code: "C03", name: "Paulo", street: "Rua Bélgica, 155", extra: "Gleba Palhano · Casa de portão verde", charge: "Cobrar R$ 42,00 no cartão (maquininha azul)", pay: "card", bags: 1, x: 340, y: 160, state: "open" },
  ],
});
function mark(code: string, state: "done" | "failed") {
  const s = ride.stops.find((x) => x.code === code);
  if (s) s.state = state;
  if (!ride.stops.some((x) => x.state === "open")) ride.phase = "back";
}
function reset() {
  ride.phase = "before";
  ride.stops.forEach((s) => (s.state = "open"));
}
const rules = [
  "O mapa ocupa a tela; embaixo (em pé) ou à direita (deitado) fica só a próxima parada.",
  "Deitado, os botões ficam do lado do polegar direito e nada precisa rolar para entregar.",
  "Texto de 16 px para cima, botão principal com 56 px de altura, alto contraste para ler no sol.",
  "Tela acesa durante a corrida (Screen Wake Lock) e respeito às bordas do celular (notch, barra de gestos).",
  "Instalável na tela de início (PWA): abre pelo ícone, em tela cheia, e recebe aviso de corrida nova.",
  "Sem rede, os toques ficam guardados e vão quando a rede volta; a tela diz \"Enviando quando houver sinal\".",
  "O mapa segue a moto até o entregador mexer nele; \"Centralizar em mim\" volta a seguir.",
  "Pesada só na primeira vez: depois abre do cache, e o mapa carrega só a área da rota.",
];
</script>

<template>
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default pb-32" data-preview-overlay>
        <main class="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-8 py-8">
          <header class="flex flex-col gap-1">
            <MsPreviewNav :current="4" />
            <h1 class="op-title font-semibold text-highlighted">Prévia M2b · O mapa do entregador, em pé e deitado</h1>
            <p class="op-body text-toned">
              Para a posição ao vivo funcionar, a nossa página é o mapa da corrida. Ela precisa ser boa no celular nos dois jeitos: em pé na mão
              e deitado no suporte da moto. Os dois celulares abaixo mostram a mesma corrida; toque em um e veja o outro acompanhar.
            </p>
          </header>

          <div class="flex flex-wrap items-start gap-10">
            <div class="flex flex-col gap-2">
              <p class="op-micro font-semibold text-muted">Em pé · 375 × 812 (iPhone)</p>
              <div class="h-[812px] w-[375px] overflow-hidden rounded-[2.5rem] border-[10px] border-black/85 shadow-xl">
                <MsCourierScreen :ride="ride" @depart="ride.phase = 'route'" @mark="mark" @back="reset" />
              </div>
            </div>
            <div class="flex flex-col gap-2">
              <p class="op-micro font-semibold text-muted">Deitado · 812 × 375 (no suporte)</p>
              <div class="h-[375px] w-[812px] overflow-hidden rounded-[2.5rem] border-[10px] border-black/85 shadow-xl">
                <MsCourierScreen :ride="ride" landscape @depart="ride.phase = 'route'" @mark="mark" @back="reset" />
              </div>
              <p class="op-micro font-semibold text-muted">Deitado · 740 × 360 (Android menor)</p>
              <div class="h-[360px] w-[740px] overflow-hidden rounded-[2rem] border-[10px] border-black/85 shadow-xl">
                <MsCourierScreen :ride="ride" landscape @depart="ride.phase = 'route'" @mark="mark" @back="reset" />
              </div>
              <NuxtButton class="self-start" size="xs" color="neutral" variant="outline" icon="i-lucide-rotate-ccw" label="Recomeçar a corrida" @click="reset" />
            </div>
          </div>

          <section class="flex flex-col gap-1 rounded-xl border border-dashed border-accented p-4 op-body text-toned">
            <p class="font-semibold text-highlighted">O que entra na frente M2b para ela ser boa no celular</p>
            <p v-for="r in rules" :key="r">· {{ r }}</p>
          </section>
        </main>
      </div>
    </Teleport>
  </div>
</template>
