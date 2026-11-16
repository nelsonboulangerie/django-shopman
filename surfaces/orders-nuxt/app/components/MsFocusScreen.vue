<script setup lang="ts">
// PRÉVIA (16/11, DEV-2026-030): a página do entregador da casa em HIPERFOCO, na linguagem do
// Painel do Gestor (pedido do dono, 16/11): diferença por TOM de fundo, sem borda nem fio;
// fio só grosso e só para destaque; hierarquia por TAMANHO e PESO; espaço generoso.
//
// A linguagem, com rigor (nada fora destas peças):
//   Texto (5 estilos, e só eles)
//     display  40 / 900   a única coisa da tela (o nome na porta, o valor a receber, a espera)
//     title    24 / 800   o nome da tela ("Leve da loja", "O que aconteceu?")
//     ref      20 / 800   código de pedido: SEMPRE à esquerda do bloco, sempre igual
//     body     18 / 500   o fato
//     meta     15 / 500   o apoio, em tom mais fraco
//   Superfície (3 tons, e só eles)
//     tela     bg-default      o fundo
//     bloco    bg-elevated     um pedido, uma escolha, um recado
//     forte    bg-inverted     o botão principal (um por tela) e o aviso que passa na frente
//   Fio: só o grosso (6 px, à esquerda), só no bloco do dinheiro da porta.
//   Espaço: tela 20 px; bloco 16 px por dentro; 12 px entre blocos; 28 px entre grupos.
//   Cor da corrida: só identidade (o quadrado da letra e a rota no mapa).
// Não vai ao ar.
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

const T = {
  display: "text-[40px] font-black leading-[1.05] tracking-tight text-highlighted",
  title: "text-[24px] font-extrabold leading-tight text-highlighted",
  ref: "text-[20px] font-extrabold tabular-nums text-highlighted",
  body: "text-[18px] font-medium leading-snug text-highlighted",
  meta: "text-[15px] font-medium leading-snug text-muted",
};
const S = {
  screen: "flex min-h-0 flex-1 flex-col gap-7 overflow-y-auto p-5",
  block: "flex flex-col gap-1.5 rounded-2xl bg-elevated p-4",
  choice: "flex min-h-16 w-full flex-col items-start justify-center gap-0.5 rounded-2xl bg-elevated px-4 py-3 text-left",
  primary: "min-h-16 w-full rounded-2xl bg-inverted text-[20px] font-extrabold text-inverted",
  link: "min-h-12 px-1 text-[16px] font-semibold text-toned underline underline-offset-4",
  footer: "flex shrink-0 flex-col gap-1 bg-default px-5 pt-3",
};
const isDoor = computed(() => props.moment === "door" || props.moment === "door-card" || props.moment === "undo");
const card = computed(() => props.moment === "door-card");
</script>

<template>
  <div class="relative flex size-full flex-col overflow-hidden bg-default" style="font-size: 16px">
    <!-- ══ 0 · A chamada chega: duas formas, rota (vários pedidos) e pedido (um só) ══ -->
    <div v-if="moment === 'call'" class="flex size-full flex-col gap-3 bg-[#1d1d1f] p-4 text-white">
      <p class="mt-10 text-center text-[64px] font-light leading-none tabular-nums">12h31</p>
      <p class="mb-6 text-center text-[15px] text-white/70">Segunda-feira, 16 de novembro</p>
      <div v-for="n in [
        { title: 'Corrida para você: Rota A', body: '2 entregas na Gleba Palhano. Você recebe R$ 15,00. Fica pronta às 12h40.', when: 'agora' },
        { title: 'Corrida para você: Pedido B12', body: '1 entrega no Centro. Você recebe R$ 8,00. Fica pronto às 13h10.', when: '12h05' },
      ]" :key="n.title" class="flex flex-col gap-1 rounded-2xl bg-white/15 p-3">
        <p class="flex items-center gap-2 text-[13px] text-white/70">
          <span class="grid size-5 place-items-center rounded bg-white text-[10px] font-black text-black">N</span>Nelson · {{ n.when }}
        </p>
        <p class="text-[16px] font-bold">{{ n.title }}</p>
        <p class="text-[15px] leading-snug">{{ n.body }}</p>
      </div>
    </div>

    <!-- ══ 1 · Na loja: um bloco por pedido, o código sempre à esquerda ══ -->
    <template v-else-if="moment === 'pickup' || moment === 'pickup-wait'">
      <div :class="S.screen">
        <div class="flex items-center gap-3">
          <span class="grid size-12 shrink-0 place-items-center rounded-xl text-[26px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
          <div>
            <p :class="T.meta">Rota A</p>
            <p :class="T.title">Leve da loja</p>
          </div>
        </div>
        <div class="flex flex-col gap-3">
          <div :class="S.block">
            <div class="flex items-baseline justify-between gap-3"><span :class="T.ref">A47</span><span :class="T.meta">Pronto</span></div>
            <p :class="T.body">2 sacolas</p>
            <p :class="T.body">Troco R$ 42,00</p>
          </div>
          <div :class="S.block">
            <div class="flex items-baseline justify-between gap-3">
              <span :class="T.ref">C03</span>
              <span :class="moment === 'pickup-wait' ? 'text-[15px] font-extrabold text-highlighted' : T.meta">{{ moment === "pickup-wait" ? "Fica pronto às 12h48" : "Pronto" }}</span>
            </div>
            <p :class="T.body">1 sacola</p>
            <p :class="T.body">Maquininha Azul</p>
          </div>
        </div>
        <p :class="T.meta">Dica: C03 no fundo, A47 por cima. A47 é a primeira entrega.</p>
      </div>
      <div :class="S.footer" style="padding-bottom: max(1rem, env(safe-area-inset-bottom))">
        <button v-if="moment === 'pickup'" type="button" :class="S.primary">Saí da loja</button>
        <p v-else class="grid min-h-16 place-items-center rounded-2xl bg-elevated text-center text-[18px] font-bold text-toned">Espere C03 ficar pronto</p>
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
        <div class="absolute inset-x-3 top-3 flex items-center gap-3 rounded-2xl bg-inverted px-4 py-3 text-inverted shadow-lg">
          <NuxtIcon name="i-lucide-corner-up-right" class="size-9 shrink-0" />
          <div class="flex min-w-0 flex-col">
            <span class="text-[26px] font-black leading-none tabular-nums">200 m</span>
            <span class="truncate text-[18px] font-medium">Rua Caracas</span>
          </div>
        </div>
        <button type="button" class="absolute end-3 bottom-3 rounded-full bg-default px-4 py-3 text-[15px] font-bold text-highlighted shadow-lg">Abrir no Waze</button>
      </div>
      <div class="flex shrink-0 flex-col justify-center gap-1 bg-default p-5" :class="landscape ? 'w-[38%]' : ''">
        <p :class="T.meta">Faltam 2 · chega 12h46</p>
        <p :class="T.ref">A47</p>
        <p :class="T.display">Marina</p>
        <p :class="T.body">Rua Caracas, 420</p>
      </div>
    </div>

    <!-- ══ 3 · Na porta: quem, o que entregar, o que receber ══ -->
    <template v-else-if="isDoor">
      <div :class="[S.screen, moment === 'undo' ? 'opacity-40' : '']">
        <div class="flex flex-col gap-1">
          <p class="flex items-center gap-2" :class="T.meta">
            <span class="grid size-6 place-items-center rounded-md text-[13px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
            {{ card ? "Falta 1" : "Faltam 2" }}
          </p>
          <p :class="T.display">{{ card ? "Paulo" : "Marina" }}</p>
          <p :class="T.body">{{ card ? "Casa de portão verde" : "Torre 2 · Apto 41" }}</p>
          <p :class="T.meta">{{ card ? "Rua Bélgica, 155" : "Rua Caracas, 420" }}</p>
        </div>
        <div class="flex flex-col gap-3">
          <p :class="[S.block, T.body]">{{ card ? "“Toque a campainha.”" : "“O interfone não funciona, me ligue que eu desço.”" }}</p>
          <div :class="[S.block, 'flex-row items-baseline justify-between gap-3']">
            <span :class="T.ref">{{ card ? "C03" : "A47" }}</span>
            <span :class="T.body">{{ card ? "1 sacola" : "2 sacolas" }}</span>
          </div>
          <div class="flex flex-col gap-1 rounded-2xl border-s-[6px] border-inverted bg-elevated p-4">
            <p :class="T.meta">{{ card ? "Receber no cartão" : "Receber em dinheiro" }}</p>
            <p :class="T.display">{{ card ? "R$ 42,00" : "R$ 58,00" }}</p>
            <p v-if="card" :class="T.body">Na maquininha Azul</p>
            <template v-else>
              <p :class="T.body">Marina paga com R$ 100,00</p>
              <p class="text-[18px] font-extrabold text-highlighted">Devolva R$ 42,00</p>
            </template>
          </div>
        </div>
      </div>
      <div v-if="moment !== 'undo'" :class="S.footer" style="padding-bottom: max(0.5rem, env(safe-area-inset-bottom))">
        <button type="button" :class="S.primary">Entreguei {{ card ? "C03" : "A47" }}</button>
        <div class="flex justify-between">
          <button type="button" :class="S.link">Ligar</button>
          <button type="button" :class="S.link">Pagou de outro jeito</button>
          <button type="button" :class="S.link">Não consegui</button>
        </div>
      </div>
      <div v-else class="absolute inset-x-3 bottom-3 flex items-center gap-3 overflow-hidden rounded-2xl bg-inverted px-4 py-4 text-inverted shadow-xl" style="margin-bottom: env(safe-area-inset-bottom)">
        <span class="flex-1 text-[20px] font-extrabold">A47 entregue</span>
        <button type="button" class="min-h-12 rounded-xl bg-default px-4 text-[18px] font-extrabold text-highlighted">Desfazer</button>
        <span class="absolute inset-x-0 bottom-0 h-1 w-2/3 bg-default/70" aria-hidden="true" />
      </div>
    </template>

    <!-- ══ 3c · Duas paradas perto ══ -->
    <div v-else-if="moment === 'which-door'" :class="S.screen">
      <div class="flex flex-col gap-1">
        <p :class="T.title">Em qual porta você está?</p>
        <p :class="T.meta">A47 e C03 ficam a menos de 150 m uma da outra.</p>
      </div>
      <div class="flex flex-col gap-3">
        <button v-for="d in [{ r: 'A47', n: 'Marina', w: 'Torre 2 · Apto 41' }, { r: 'C03', n: 'Paulo', w: 'Casa de portão verde' }]" :key="d.r" type="button" :class="S.choice">
          <span :class="T.ref">{{ d.r }}</span>
          <span :class="T.body">{{ d.n }} · {{ d.w }}</span>
        </button>
      </div>
    </div>

    <!-- ══ 3d · Pagou de outro jeito ══ -->
    <div v-else-if="moment === 'other-pay'" :class="S.screen">
      <div class="flex flex-col gap-1">
        <p :class="T.ref">A47</p>
        <p :class="T.title">Como Marina pagou os R$ 58,00?</p>
      </div>
      <div class="flex flex-col gap-3">
        <button type="button" :class="S.choice"><span :class="T.body">No cartão, na maquininha Azul</span></button>
        <button type="button" :class="S.choice"><span :class="T.body">No Pix, na maquininha Azul</span></button>
        <button type="button" :class="S.choice"><span :class="T.body">Em dinheiro</span></button>
      </div>
      <p :class="T.meta">Pix só pela maquininha: assim o pagamento aparece na loja na hora.</p>
    </div>

    <!-- ══ 3b · Não consegui, e a espera curta ══ -->
    <div v-else-if="moment === 'failed'" :class="S.screen">
      <div class="flex flex-col gap-1">
        <p :class="T.ref">A47</p>
        <p :class="T.title">O que aconteceu?</p>
      </div>
      <div class="flex flex-col gap-3">
        <button v-for="r in ['Ninguém atendeu', 'Não achei o endereço', 'Recusou o pedido', 'Pedido com problema']" :key="r" type="button" :class="S.choice">
          <span :class="T.body">{{ r }}</span>
        </button>
      </div>
      <div class="mt-auto flex flex-col items-center gap-1">
        <p :class="T.meta">A loja liga para a Marina.</p>
        <button type="button" :class="S.link">Vou tentar de novo</button>
      </div>
    </div>
    <div v-else-if="moment === 'failed-wait'" class="flex size-full flex-col items-center justify-center gap-3 p-6 text-center">
      <p :class="T.ref">A47</p>
      <p class="text-[64px] font-black leading-none tabular-nums text-highlighted">2 min</p>
      <p :class="T.body">Espere aqui. A loja está ligando para a Marina.</p>
      <p :class="T.meta">Sem resposta, a tela leva você para C03. A sacola de A47 volta com você.</p>
      <button type="button" :class="[S.link, 'mt-4']">Marina atendeu</button>
    </div>

    <!-- ══ 7 · A loja cancelou com ele na rua: o único aviso que passa na frente ══ -->
    <div v-else-if="moment === 'cancelled'" class="flex size-full flex-col justify-center gap-4 bg-inverted p-6 text-inverted">
      <p class="text-[20px] font-extrabold tabular-nums">C03</p>
      <p class="text-[40px] font-black leading-[1.05]">Foi cancelado.</p>
      <p class="text-[18px] font-medium leading-snug">Não entregue. Traga a sacola de volta.</p>
      <p class="text-[15px] font-medium opacity-70">Paulo já foi avisado pela loja.</p>
      <button type="button" class="mt-6 min-h-16 w-full rounded-2xl bg-default text-[20px] font-extrabold text-highlighted">Entendi</button>
    </div>

    <!-- ══ 5 · Voltando: só o acerto ══ -->
    <div v-else-if="moment === 'back'" :class="[S.screen, 'justify-center']">
      <p :class="T.title">Entregue no caixa</p>
      <div class="flex flex-col gap-3">
        <div :class="S.block"><p :class="T.meta">Dinheiro</p><p :class="T.display">R$ 100,00</p></div>
        <div :class="S.block"><p :class="T.body">Maquininha Azul</p></div>
      </div>
      <p :class="T.meta">O balcão confere e fecha a rota.</p>
    </div>

    <!-- ══ 6 · Fechada ══ -->
    <div v-else class="flex size-full flex-col">
      <div class="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
        <span class="grid size-16 place-items-center rounded-2xl text-[36px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
        <p :class="T.title">Rota A fechada</p>
        <p :class="T.display">R$ 15,00</p>
        <p :class="T.meta">A receber hoje: R$ 27,00 (2 corridas)</p>
      </div>
      <div class="m-4 flex flex-col gap-3 rounded-2xl bg-elevated p-4">
        <p :class="T.body">Receba a próxima corrida como aviso no celular.</p>
        <button type="button" class="min-h-12 rounded-xl bg-default text-[17px] font-bold text-highlighted">Pôr na tela de início</button>
      </div>
    </div>
  </div>
</template>
