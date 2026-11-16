<script setup lang="ts">
// PRÉVIA (16/11, DEV-2026-030): a página do entregador da casa em HIPERFOCO. Cada momento
// da corrida tem uma tela só, com o que importa naquele momento e nada mais.
// Cores: a cor da corrida é IDENTIDADE (a letra e a rota), nunca botão. Botão principal é
// preto; não há botão verde. Não vai ao ar.
import { rideColor } from "~/presentation/ridePalette";

export type FocusMoment = "call" | "pickup" | "drive" | "door" | "door-card" | "failed" | "back" | "closed";

const props = defineProps<{ moment: FocusMoment; landscape?: boolean }>();
const tone = rideColor(0);
const big = "min-h-16 w-full rounded-2xl bg-black text-[20px] font-extrabold text-white";
</script>

<template>
  <div class="relative flex size-full overflow-hidden bg-white text-black" :class="landscape ? 'flex-row' : 'flex-col'" style="font-size: 16px">
    <!-- ══ 0 · A chamada chega (aviso do celular) ══ -->
    <template v-if="moment === 'call'">
      <div class="flex size-full flex-col bg-[#1d1d1f] p-4 text-white">
        <p class="mt-10 text-center text-[64px] font-light leading-none tabular-nums">12h31</p>
        <p class="text-center text-[15px] text-white/70">segunda-feira, 16 de novembro</p>
        <div class="mt-8 flex flex-col gap-1 rounded-2xl bg-white/15 p-3 backdrop-blur">
          <p class="flex items-center gap-2 text-[13px] text-white/70">
            <span class="grid size-5 place-items-center rounded bg-white text-[10px] font-black text-black">N</span>Nelson · agora
          </p>
          <p class="text-[16px] font-bold">Corrida A para você</p>
          <p class="text-[15px] leading-snug">2 entregas, Gleba Palhano. Você recebe R$ 15,00. Fica pronta às 12h40.</p>
        </div>
        <p class="mt-auto text-center text-[13px] text-white/60">Tocar no aviso abre a corrida, já no momento certo.</p>
      </div>
    </template>

    <!-- ══ 1 · Na loja: conferir e sair ══ -->
    <template v-else-if="moment === 'pickup'">
      <div class="flex size-full flex-col gap-4 p-5">
        <div class="flex items-center gap-3">
          <span class="grid size-14 place-items-center rounded-2xl text-[32px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
          <div class="flex flex-col">
            <span class="text-[22px] font-extrabold leading-tight">Leve da loja</span>
            <span class="text-[15px] text-black/60">Você recebe R$ 15,00</span>
          </div>
        </div>
        <ul class="flex flex-col divide-y divide-black/10 border-y border-black/10 text-[20px]">
          <li class="flex items-baseline justify-between py-3"><span class="font-bold">A47</span><span>2 sacolas</span></li>
          <li class="flex items-baseline justify-between py-3"><span class="font-bold">C03</span><span>1 sacola</span></li>
          <li class="flex items-baseline justify-between py-3"><span class="font-bold">Troco</span><span class="tabular-nums">R$ 42,00</span></li>
          <li class="flex items-center justify-between py-3"><span class="font-bold">Maquininha</span><span class="flex items-center gap-2"><span class="size-4 rounded-full bg-[#2563eb]" />Azul</span></li>
        </ul>
        <p class="text-[16px] leading-snug text-black/70">Na bag: C03 no fundo, A47 em cima. A47 é a primeira parada.</p>
        <button type="button" :class="[big, 'mt-auto']">Saí da loja</button>
      </div>
    </template>

    <!-- ══ 2 · Dirigindo: só o caminho ══ -->
    <template v-else-if="moment === 'drive' || moment === 'back'">
      <div class="relative min-h-0 min-w-0 flex-1 bg-[#ebe7dd]">
        <svg viewBox="40 20 330 260" preserveAspectRatio="xMidYMid meet" class="absolute inset-0 size-full" aria-hidden="true">
          <rect x="-600" y="-600" width="1600" height="1600" fill="#ebe7dd" />
          <path d="M-600 230 L 0 200 Q 150 170 400 210 L 1000 240" stroke="#fff" stroke-width="16" fill="none" />
          <path d="M140 -600 L 150 0 Q 170 160 140 320 L 130 1000" stroke="#fff" stroke-width="12" fill="none" />
          <path d="M-600 110 L 1000 40" stroke="#fff" stroke-width="9" fill="none" />
          <path d="M270 -600 L 330 1000" stroke="#fff" stroke-width="9" fill="none" />
          <polyline
            :points="moment === 'drive' ? '150,215 160,150 250,120' : '330,170 300,205 150,200 70,250'"
            fill="none" stroke="#111" stroke-width="11" stroke-linejoin="round" stroke-linecap="round"
          />
          <polyline
            :points="moment === 'drive' ? '150,215 160,150 250,120' : '330,170 300,205 150,200 70,250'"
            fill="none" :stroke="tone.bg" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"
          />
          <template v-if="moment === 'drive'">
            <circle cx="250" cy="120" r="18" fill="#fff" stroke="#111" stroke-width="4" />
            <text x="250" y="126" font-size="17" font-weight="900" text-anchor="middle">1</text>
            <circle cx="150" cy="215" r="10" fill="#111" stroke="#fff" stroke-width="4" />
          </template>
          <template v-else>
            <rect x="56" y="236" width="28" height="28" rx="6" fill="#111" />
            <text x="70" y="254" font-size="9" font-weight="700" fill="#fff" text-anchor="middle">Loja</text>
            <circle cx="330" cy="170" r="10" fill="#111" stroke="#fff" stroke-width="4" />
          </template>
        </svg>
        <!-- a próxima manobra: o único texto em cima do mapa -->
        <div class="absolute inset-x-3 top-3 flex items-center gap-3 rounded-2xl bg-black px-4 py-3 text-white shadow-lg">
          <NuxtIcon :name="moment === 'drive' ? 'i-lucide-corner-up-right' : 'i-lucide-corner-up-left'" class="size-9 shrink-0" />
          <div class="flex min-w-0 flex-col">
            <span class="text-[26px] font-extrabold leading-none tabular-nums">200 m</span>
            <span class="truncate text-[17px]">{{ moment === "drive" ? "Rua Caracas" : "Av. Higienópolis" }}</span>
          </div>
        </div>
      </div>
      <div
        class="flex shrink-0 flex-col justify-center gap-0.5 bg-white px-5 py-4"
        :class="landscape ? 'w-[38%] border-s border-black/10' : 'border-t border-black/10'"
      >
        <template v-if="moment === 'drive'">
          <p class="text-[15px] text-black/60">1 de 2 · chega 12h46</p>
          <p class="text-[30px] font-extrabold leading-tight">A47 · Marina</p>
          <p class="text-[18px] leading-snug">Rua Caracas, 420</p>
        </template>
        <template v-else>
          <p class="text-[15px] text-black/60">Volta à loja · chega 13h05</p>
          <p class="text-[30px] font-extrabold leading-tight">R$ 100,00</p>
          <p class="text-[18px] leading-snug">em dinheiro e a maquininha azul</p>
        </template>
      </div>
    </template>

    <!-- ══ 3 · Na porta: entregar certo ══ -->
    <template v-else-if="moment === 'door' || moment === 'door-card'">
      <div class="flex size-full flex-col gap-4 p-5" :class="landscape ? 'flex-row' : ''">
        <div class="flex flex-col gap-1" :class="landscape ? 'w-1/2' : ''">
          <p class="flex items-center gap-2 text-[15px] text-black/60">
            <span class="grid size-6 place-items-center rounded-md text-[13px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
            {{ moment === "door" ? "1 de 2" : "2 de 2" }} · combinado até {{ moment === "door" ? "12h50" : "13h00" }}
          </p>
          <p class="text-[40px] font-black leading-none">{{ moment === "door" ? "Marina" : "Paulo" }}</p>
          <p class="text-[20px] font-semibold leading-snug">{{ moment === "door" ? "Apto 41 · Interfone 41" : "Casa de portão verde" }}</p>
          <p class="text-[16px] text-black/60">{{ moment === "door" ? "Rua Caracas, 420" : "Rua Bélgica, 155 · toque a campainha" }}</p>
        </div>
        <div class="flex flex-col gap-3" :class="landscape ? 'w-1/2' : 'flex-1'">
          <div class="flex flex-col divide-y divide-black/10 border-y border-black/10">
            <p class="flex items-baseline justify-between py-3 text-[20px]">
              <span class="text-black/60">Entregue</span><span class="font-bold">{{ moment === "door" ? "2 sacolas · A47" : "1 sacola · C03" }}</span>
            </p>
            <template v-if="moment === 'door'">
              <p class="flex items-baseline justify-between py-3 text-[20px]">
                <span class="text-black/60">Receba</span><span class="text-[28px] font-black tabular-nums">R$ 58,00</span>
              </p>
              <p class="py-3 text-[18px] leading-snug">Ela paga com R$ 100,00. <strong>Devolva R$ 42,00.</strong></p>
            </template>
            <template v-else>
              <p class="flex items-baseline justify-between py-3 text-[20px]">
                <span class="text-black/60">Cartão</span><span class="text-[28px] font-black tabular-nums">R$ 42,00</span>
              </p>
              <p class="flex items-center gap-2 py-3 text-[18px]"><span class="size-4 rounded-full bg-[#2563eb]" />Na maquininha azul</p>
            </template>
          </div>
          <div class="mt-auto flex flex-col gap-2">
            <button type="button" :class="big">Entreguei</button>
            <div class="flex justify-between text-[17px] font-semibold">
              <button type="button" class="min-h-12 px-1 underline">Ligar para {{ moment === "door" ? "Marina" : "Paulo" }}</button>
              <button type="button" class="min-h-12 px-1 text-black/60 underline">Não consegui</button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ══ 3b · Não consegui ══ -->
    <template v-else-if="moment === 'failed'">
      <div class="flex size-full flex-col gap-3 p-5">
        <p class="text-[15px] text-black/60">A47 · Marina</p>
        <p class="text-[28px] font-black leading-tight">O que aconteceu?</p>
        <button v-for="r in ['Ninguém atendeu', 'Não achei o endereço', 'Recusou o pedido']" :key="r" type="button" class="min-h-16 rounded-2xl border-2 border-black px-4 text-left text-[20px] font-bold">{{ r }}</button>
        <p class="mt-auto text-[16px] leading-snug text-black/70">A loja fica sabendo na hora e liga para a Marina. Leve a sacola de A47 com você e siga para C03.</p>
        <button type="button" class="min-h-12 text-[17px] font-semibold underline">Voltar, vou tentar de novo</button>
      </div>
    </template>

    <!-- ══ 5 · Fechada ══ -->
    <template v-else>
      <div class="flex size-full flex-col items-center justify-center gap-2 p-6 text-center">
        <span class="grid size-16 place-items-center rounded-2xl text-[36px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
        <p class="text-[26px] font-black leading-tight">Corrida A fechada</p>
        <p class="text-[18px]">R$ 15,00 para você.</p>
        <p class="text-[16px] text-black/60">Hoje: 2 corridas, R$ 27,00.</p>
        <p class="mt-6 text-[14px] text-black/50">Os endereços somem daqui às 15h08.</p>
      </div>
    </template>
  </div>
</template>
