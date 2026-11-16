<script setup lang="ts">
// PRÉVIA (16/11, DEV-2026-030): a página do entregador da casa em HIPERFOCO, depois da
// revisão adversarial. Cada momento tem uma tela só, com o que importa ali e nada mais.
// Cores: a cor da corrida é IDENTIDADE (a letra e a rota), nunca botão. Botão principal é
// preto e único; escolha entre iguais é contorno. A maquininha vai pelo nome, sem bolinha
// (a cor dela colidia com a da corrida). Não vai ao ar.
import { rideColor } from "~/presentation/ridePalette";

export type FocusMoment =
  | "call"
  | "pickup"
  | "pickup-wait"
  | "drive"
  | "door"
  | "door-card"
  | "which-door"
  | "undo"
  | "other-pay"
  | "failed"
  | "failed-wait"
  | "cancelled"
  | "back"
  | "closed";

const props = defineProps<{ moment: FocusMoment; landscape?: boolean }>();
const tone = rideColor(0);
const primary = "min-h-16 w-full rounded-2xl bg-black text-[20px] font-extrabold text-white";
const choice = "min-h-16 w-full rounded-2xl border-2 border-black px-4 text-left text-[20px] font-bold";
const isDoor = computed(() => props.moment === "door" || props.moment === "door-card" || props.moment === "undo");
const card = computed(() => props.moment === "door-card");
</script>

<template>
  <div class="relative flex size-full flex-col overflow-hidden bg-white text-black" style="font-size: 16px">
    <!-- ══ 0 · A chamada chega ══ -->
    <div v-if="moment === 'call'" class="flex size-full flex-col bg-[#1d1d1f] p-4 text-white">
      <p class="mt-10 text-center text-[64px] font-light leading-none tabular-nums">12h31</p>
      <p class="text-center text-[15px] text-white/70">Segunda-feira, 16 de novembro</p>
      <div class="mt-8 flex flex-col gap-1 rounded-2xl bg-white/15 p-3">
        <p class="flex items-center gap-2 text-[13px] text-white/70">
          <span class="grid size-5 place-items-center rounded bg-white text-[10px] font-black text-black">N</span>Nelson · agora
        </p>
        <p class="text-[16px] font-bold">Corrida A para você</p>
        <p class="text-[15px] leading-snug">2 entregas na Gleba Palhano. Você recebe R$ 15,00. Fica pronta às 12h40.</p>
      </div>
    </div>

    <!-- ══ 1 · Na loja (tudo pronto, ou esperando um pedido) ══ -->
    <template v-else-if="moment === 'pickup' || moment === 'pickup-wait'">
      <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5">
        <div class="flex items-center gap-3">
          <span class="grid size-14 place-items-center rounded-2xl text-[32px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
          <span class="text-[24px] font-extrabold">Leve da loja</span>
        </div>
        <ul class="flex flex-col divide-y divide-black/10 border-y border-black/10 text-[19px]">
          <li class="flex items-baseline justify-between gap-2 py-3"><span><b>A47</b> · 2 sacolas</span><span class="text-[16px] text-black/60">Pronta</span></li>
          <li class="flex items-baseline justify-between gap-2 py-3">
            <span><b>C03</b> · 1 sacola</span>
            <span class="text-[16px]" :class="moment === 'pickup-wait' ? 'font-bold' : 'text-black/60'">{{ moment === "pickup-wait" ? "Fica pronta às 12h48" : "Pronta" }}</span>
          </li>
          <li class="flex items-baseline justify-between gap-2 py-3"><span>Troco de <b>A47</b></span><span class="tabular-nums font-bold">R$ 42,00</span></li>
          <li class="flex items-baseline justify-between gap-2 py-3"><span>Maquininha Azul</span><span class="text-[16px] text-black/60">para C03</span></li>
        </ul>
        <p class="text-[16px] leading-snug text-black/70">Dica: C03 no fundo, A47 por cima. A47 é a primeira entrega.</p>
      </div>
      <div class="shrink-0 border-t border-black/10 p-4" style="padding-bottom: max(1rem, env(safe-area-inset-bottom))">
        <button v-if="moment === 'pickup'" type="button" :class="primary">Saí da loja</button>
        <p v-else class="grid min-h-16 place-items-center rounded-2xl bg-black/5 text-center text-[19px] font-bold">Espere C03 ficar pronta</p>
      </div>
    </template>

    <!-- ══ 2 · Dirigindo: só o caminho ══ -->
    <div v-else-if="moment === 'drive'" class="flex size-full" :class="landscape ? 'flex-row' : 'flex-col'">
      <div class="relative min-h-0 min-w-0 flex-1 bg-[#ebe7dd]">
        <svg viewBox="40 20 330 260" preserveAspectRatio="xMidYMid meet" class="absolute inset-0 size-full" aria-hidden="true">
          <rect x="-600" y="-600" width="1600" height="1600" fill="#ebe7dd" />
          <path d="M-600 230 L 0 200 Q 150 170 400 210 L 1000 240" stroke="#fff" stroke-width="16" fill="none" />
          <path d="M140 -600 L 150 0 Q 170 160 140 320 L 130 1000" stroke="#fff" stroke-width="12" fill="none" />
          <path d="M-600 110 L 1000 40" stroke="#fff" stroke-width="9" fill="none" />
          <path d="M270 -600 L 330 1000" stroke="#fff" stroke-width="9" fill="none" />
          <polyline points="150,215 160,150 250,120" fill="none" stroke="#111" stroke-width="11" stroke-linejoin="round" stroke-linecap="round" />
          <polyline points="150,215 160,150 250,120" fill="none" :stroke="tone.bg" stroke-width="6" stroke-linejoin="round" stroke-linecap="round" />
          <circle cx="250" cy="120" r="20" fill="#fff" stroke="#111" stroke-width="4" />
          <text x="250" y="125" font-size="13" font-weight="900" text-anchor="middle">A47</text>
          <circle cx="150" cy="215" r="10" fill="#111" stroke="#fff" stroke-width="4" />
        </svg>
        <div class="absolute inset-x-3 top-3 flex items-center gap-3 rounded-2xl bg-black px-4 py-3 text-white shadow-lg">
          <NuxtIcon name="i-lucide-corner-up-right" class="size-9 shrink-0" />
          <div class="flex min-w-0 flex-col">
            <span class="text-[26px] font-extrabold leading-none tabular-nums">200 m</span>
            <span class="truncate text-[17px]">Rua Caracas</span>
          </div>
        </div>
        <button type="button" class="absolute end-3 bottom-3 rounded-full bg-white px-4 py-3 text-[15px] font-bold shadow-lg">Abrir no Waze</button>
      </div>
      <div class="flex shrink-0 flex-col justify-center gap-0.5 bg-white px-5 py-4" :class="landscape ? 'w-[38%] border-s border-black/10' : 'border-t border-black/10'">
        <p class="text-[15px] text-black/60">Faltam 2 · chega 12h46</p>
        <p class="text-[30px] font-extrabold leading-tight">A47 · Marina</p>
        <p class="text-[18px] leading-snug">Rua Caracas, 420</p>
      </div>
    </div>

    <!-- ══ 3 · Na porta (dinheiro ou cartão), e o "Desfazer" logo depois do toque ══ -->
    <template v-else-if="isDoor">
      <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-5" :class="moment === 'undo' ? 'opacity-40' : ''">
        <p class="flex items-center gap-2 text-[15px] text-black/60">
          <span class="grid size-6 place-items-center rounded-md text-[13px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
          {{ card ? "Falta 1" : "Faltam 2" }}
        </p>
        <div>
          <p class="text-[40px] font-black leading-none">{{ card ? "Paulo" : "Marina" }}</p>
          <p class="mt-1 text-[20px] font-semibold leading-snug">{{ card ? "Casa de portão verde" : "Torre 2 · Apto 41" }}</p>
          <p class="text-[16px] text-black/60">{{ card ? "Rua Bélgica, 155" : "Rua Caracas, 420" }}</p>
          <p class="mt-2 rounded-xl bg-black/5 px-3 py-2 text-[16px] leading-snug">
            {{ card ? "“Toque a campainha.”" : "“O interfone não funciona, me ligue que eu desço.”" }}
          </p>
        </div>
        <div class="flex flex-col divide-y divide-black/10 border-y border-black/10 text-[19px]">
          <p class="flex items-baseline justify-between gap-2 py-3"><span class="text-black/60">Entregar</span><span class="font-bold">{{ card ? "1 sacola de C03" : "2 sacolas de A47" }}</span></p>
          <p class="flex items-baseline justify-between gap-2 py-3">
            <span class="text-black/60">Receber</span>
            <span class="text-[26px] font-black tabular-nums">{{ card ? "R$ 42,00 no cartão" : "R$ 58,00" }}</span>
          </p>
          <p class="py-3 text-[18px] leading-snug">
            <template v-if="card">Na maquininha Azul.</template>
            <template v-else>Marina paga com R$ 100,00. <b>Devolva R$ 42,00.</b></template>
          </p>
        </div>
      </div>
      <div v-if="moment !== 'undo'" class="flex shrink-0 flex-col gap-1 border-t border-black/10 px-4 pt-3" style="padding-bottom: max(0.5rem, env(safe-area-inset-bottom))">
        <button type="button" :class="primary">Entreguei {{ card ? "C03" : "A47" }}</button>
        <div class="flex justify-between text-[16px] font-semibold">
          <button type="button" class="min-h-12 px-1 underline">Ligar</button>
          <button type="button" class="min-h-12 px-1 underline">Pagou de outro jeito</button>
          <button type="button" class="min-h-12 px-1 text-black/60 underline">Não consegui</button>
        </div>
      </div>
      <div v-else class="absolute inset-x-3 bottom-3 flex items-center gap-3 overflow-hidden rounded-2xl bg-black px-4 py-4 text-white shadow-xl" style="margin-bottom: env(safe-area-inset-bottom)">
        <span class="flex-1 text-[20px] font-bold">A47 entregue.</span>
        <button type="button" class="min-h-12 rounded-xl bg-white px-4 text-[18px] font-extrabold text-black">Desfazer</button>
        <span class="absolute inset-x-0 bottom-0 h-1 w-2/3 bg-white/70" aria-hidden="true" />
      </div>
    </template>

    <!-- ══ 3c · Duas paradas perto: qual porta ══ -->
    <div v-else-if="moment === 'which-door'" class="flex size-full flex-col gap-3 p-5">
      <p class="text-[28px] font-black leading-tight">Em qual porta você está?</p>
      <p class="text-[16px] text-black/60">A47 e C03 ficam a menos de 150 m uma da outra.</p>
      <button type="button" :class="choice">Marina · A47<br /><span class="text-[16px] font-normal">Torre 2 · Apto 41</span></button>
      <button type="button" :class="choice">Paulo · C03<br /><span class="text-[16px] font-normal">Casa de portão verde</span></button>
    </div>

    <!-- ══ 3d · Pagou de outro jeito ══ -->
    <div v-else-if="moment === 'other-pay'" class="flex size-full flex-col gap-3 p-5">
      <p class="text-[15px] text-black/60">A47 · R$ 58,00</p>
      <p class="text-[28px] font-black leading-tight">Como Marina pagou?</p>
      <button type="button" :class="choice">No cartão, na maquininha Azul</button>
      <button type="button" :class="choice">Pix, na maquininha Azul</button>
      <p class="mt-auto text-[16px] leading-snug text-black/70">Pix só pela maquininha: assim o pagamento aparece na loja na hora.</p>
      <button type="button" class="min-h-12 text-[17px] font-semibold underline">Pagou em dinheiro</button>
    </div>

    <!-- ══ 3b · Não consegui: o motivo, e a espera curta ══ -->
    <div v-else-if="moment === 'failed'" class="flex size-full flex-col gap-3 p-5">
      <p class="text-[15px] text-black/60">A47 · Marina</p>
      <p class="text-[28px] font-black leading-tight">O que aconteceu?</p>
      <button v-for="r in ['Ninguém atendeu', 'Não achei o endereço', 'Recusou o pedido', 'Pedido com problema']" :key="r" type="button" :class="choice">{{ r }}</button>
      <p class="mt-auto text-[16px] leading-snug text-black/70">Escolha o motivo. A loja liga para a Marina.</p>
      <button type="button" class="min-h-12 text-[17px] font-semibold underline">Vou tentar de novo</button>
    </div>
    <div v-else-if="moment === 'failed-wait'" class="flex size-full flex-col items-center justify-center gap-3 p-6 text-center">
      <p class="text-[64px] font-black leading-none tabular-nums">2 min</p>
      <p class="text-[22px] font-bold leading-snug">Espere aqui. A loja está ligando para a Marina.</p>
      <p class="text-[16px] text-black/60">Se ela não atender, a tela leva você para C03. A sacola de A47 volta com você.</p>
      <button type="button" class="mt-4 min-h-12 text-[17px] font-semibold underline">Marina atendeu, vou entregar</button>
    </div>

    <!-- ══ 7 · A loja cancelou um pedido com ele na rua ══ -->
    <div v-else-if="moment === 'cancelled'" class="flex size-full flex-col justify-center gap-3 bg-black p-6 text-white">
      <p class="text-[40px] font-black leading-none">C03 foi cancelado.</p>
      <p class="text-[22px] font-bold leading-snug">Não entregue. Traga a sacola de volta.</p>
      <p class="text-[16px] text-white/70">Paulo já foi avisado pela loja.</p>
      <button type="button" class="mt-6 min-h-16 w-full rounded-2xl bg-white text-[20px] font-extrabold text-black">Entendi</button>
    </div>

    <!-- ══ 5 · Voltando: só o acerto ══ -->
    <div v-else-if="moment === 'back'" class="flex size-full flex-col justify-center gap-4 p-5">
      <p class="text-[24px] font-extrabold">Entregue no caixa</p>
      <ul class="flex flex-col divide-y divide-black/10 border-y border-black/10 text-[22px]">
        <li class="flex items-baseline justify-between py-3"><span>Dinheiro</span><span class="font-black tabular-nums">R$ 100,00</span></li>
        <li class="py-3">Maquininha Azul</li>
      </ul>
      <p class="text-[16px] text-black/60">O balcão confere e fecha a corrida.</p>
    </div>

    <!-- ══ 6 · Fechada ══ -->
    <div v-else class="flex size-full flex-col">
      <div class="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
        <span class="grid size-16 place-items-center rounded-2xl text-[36px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
        <p class="text-[26px] font-black leading-tight">Corrida A fechada.</p>
        <p class="text-[18px]">R$ 15,00 para você.</p>
        <p class="text-[16px] text-black/60">A receber hoje: R$ 27,00 (2 corridas).</p>
      </div>
      <div class="m-3 flex flex-col gap-2 rounded-2xl bg-black/5 p-4">
        <p class="text-[17px] font-bold leading-snug">Receba a próxima corrida como aviso no celular.</p>
        <button type="button" class="min-h-12 rounded-xl border-2 border-black text-[17px] font-bold">Pôr na tela de início</button>
      </div>
    </div>
  </div>
</template>
