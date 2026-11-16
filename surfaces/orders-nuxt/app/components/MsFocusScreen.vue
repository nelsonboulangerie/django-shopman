<script setup lang="ts">
// PRÉVIA (16/11, DEV-2026-030): a página do entregador da casa em HIPERFOCO, na linguagem do
// Painel do Gestor, simplificada a pedido do dono ("diferenciações tipográficas demais, KISS").
//
// A linguagem inteira:
//   Texto: 3 tamanhos, e só eles
//     grande   28 / 800   o título da tela e o dinheiro (o que se lê de longe)
//     normal   18 / 500   o fato
//     pequeno  15 / 500   o apoio, em tom mais fraco
//   Código do pedido: sempre o mesmo badge neutro (A47), em qualquer tela.
//   Fundo: 2 tons (tela e bloco), sem borda nem fio; o tom forte é só o botão principal e o
//   aviso que passa na frente. O forte é o OPOSTO do tema: escuro no claro, claro no escuro.
//   Espaço: 20 px na borda, 16 px dentro do bloco, 12 px entre blocos, 28 px entre grupos.
//   Cor da rota: só o quadrado da letra e a linha do mapa.
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
  big: "text-[28px] font-extrabold leading-tight text-highlighted",
  base: "text-[18px] font-medium leading-snug text-highlighted",
  small: "text-[15px] font-medium leading-snug text-muted",
};
const badge = "inline-flex w-fit items-center rounded-lg bg-accented px-2 py-0.5 text-[15px] font-bold tabular-nums text-highlighted";
const S = {
  screen: "flex min-h-0 flex-1 flex-col gap-7 overflow-y-auto p-5",
  block: "flex flex-col gap-1.5 rounded-2xl bg-elevated p-4",
  choice: "flex min-h-16 w-full flex-col items-start justify-center gap-1 rounded-2xl bg-elevated px-4 py-3 text-left",
  primary: "min-h-16 w-full rounded-2xl bg-inverted text-[18px] font-extrabold text-inverted",
  link: "min-h-12 px-1 text-[15px] font-semibold text-toned underline underline-offset-4",
  footer: "flex shrink-0 flex-col gap-1 bg-default px-5 pt-3",
};
const isDoor = computed(() => props.moment === "door" || props.moment === "door-card" || props.moment === "undo");
const card = computed(() => props.moment === "door-card");
</script>

<template>
  <div class="relative flex size-full flex-col overflow-hidden bg-default" style="font-size: 16px">
    <!-- ══ 0 · A chamada chega (aviso do sistema do celular) ══ -->
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

    <!-- ══ 1 · No balcão ══ -->
    <template v-else-if="moment === 'pickup' || moment === 'pickup-wait'">
      <div :class="S.screen">
        <div class="flex items-center gap-3">
          <span class="grid size-12 shrink-0 place-items-center rounded-xl text-[26px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
          <div class="min-w-0 flex-1">
            <p :class="T.small">Rota A</p>
            <p :class="T.big">Pegue no balcão</p>
          </div>
          <button type="button" class="grid size-12 shrink-0 place-items-center rounded-xl text-toned" aria-label="Tema claro ou escuro">
            <NuxtIcon name="i-lucide-sun-moon" class="size-6" />
          </button>
        </div>
        <div class="flex flex-col gap-3">
          <div :class="S.block">
            <div class="flex items-center justify-between gap-3"><span :class="badge">A47</span><span :class="T.small">Pronto</span></div>
            <p :class="T.base">2 sacolas</p>
            <p :class="T.base">Troco R$ 42,00</p>
          </div>
          <div :class="S.block">
            <div class="flex items-center justify-between gap-3">
              <span :class="badge">C03</span>
              <span :class="moment === 'pickup-wait' ? T.base : T.small">{{ moment === "pickup-wait" ? "Fica pronto às 12h48" : "Pronto" }}</span>
            </div>
            <p :class="T.base">1 sacola</p>
            <p :class="T.base">Maquininha Azul</p>
          </div>
        </div>
        <p :class="T.small">Dica: C03 no fundo, A47 por cima. A47 é a primeira entrega.</p>
      </div>
      <div :class="S.footer" style="padding-bottom: max(1rem, env(safe-area-inset-bottom))">
        <button v-if="moment === 'pickup'" type="button" :class="S.primary">Saí da loja</button>
        <p v-else class="grid min-h-16 place-items-center rounded-2xl bg-elevated text-center text-[18px] font-medium text-toned">Espere C03 ficar pronto</p>
      </div>
    </template>

    <!-- ══ 2 · Dirigindo: o endereço em destaque ══ -->
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
            <span class="text-[28px] font-extrabold leading-none tabular-nums">200 m</span>
            <span class="truncate text-[18px] font-medium">Rua Caracas</span>
          </div>
        </div>
        <button type="button" class="absolute end-3 bottom-3 rounded-full bg-default px-4 py-3 text-[15px] font-semibold text-highlighted shadow-lg">Abrir no Waze</button>
      </div>
      <div class="flex shrink-0 flex-col justify-center gap-1.5 bg-default p-5" :class="landscape ? 'w-[38%]' : ''">
        <p :class="T.small">Faltam 2 · chega 12h46</p>
        <p :class="T.big">Rua Caracas, 420</p>
        <p class="flex items-center gap-2"><span :class="badge">A47</span><span :class="T.base">Marina</span></p>
      </div>
    </div>

    <!-- ══ 3 · Na entrega: quem, o que entregar, o que receber ══ -->
    <template v-else-if="isDoor">
      <div :class="[S.screen, moment === 'undo' ? 'opacity-40' : '']">
        <div class="flex flex-col gap-1">
          <p class="flex items-center gap-2" :class="T.small">
            <span class="grid size-6 place-items-center rounded-md text-[13px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
            {{ card ? "Falta 1" : "Faltam 2" }}
          </p>
          <p :class="T.big">{{ card ? "Paulo" : "Marina" }}</p>
          <p :class="T.base">{{ card ? "Casa de portão verde" : "Torre 2 · Apto 41" }}</p>
          <p :class="T.small">{{ card ? "Rua Bélgica, 155" : "Rua Caracas, 420" }}</p>
        </div>
        <div class="flex flex-col gap-3">
          <p :class="[S.block, T.base]">{{ card ? "“Toque a campainha.”" : "“O interfone não funciona, me ligue que eu desço.”" }}</p>
          <div :class="[S.block, 'flex-row items-center justify-between gap-3']">
            <span :class="badge">{{ card ? "C03" : "A47" }}</span>
            <span :class="T.base">{{ card ? "1 sacola" : "2 sacolas" }}</span>
          </div>
          <div :class="S.block">
            <p :class="T.small">{{ card ? "Receber no cartão" : "Receber em dinheiro" }}</p>
            <p :class="T.big">{{ card ? "R$ 42,00" : "R$ 58,00" }}</p>
            <p :class="T.base">{{ card ? "Na maquininha Azul." : "Marina paga com R$ 100,00. Devolva R$ 42,00." }}</p>
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
        <span class="flex-1 text-[18px] font-extrabold">A47 entregue</span>
        <button type="button" class="min-h-12 rounded-xl bg-default px-4 text-[18px] font-extrabold text-highlighted">Desfazer</button>
        <span class="absolute inset-x-0 bottom-0 h-1 w-2/3 bg-default/70" aria-hidden="true" />
      </div>
    </template>

    <!-- ══ 3c · Duas entregas perto ══ -->
    <div v-else-if="moment === 'which-door'" :class="S.screen">
      <div class="flex flex-col gap-1">
        <p :class="T.big">Qual entrega é esta?</p>
        <p :class="T.small">A47 e C03 ficam a menos de 150 m uma da outra.</p>
      </div>
      <div class="flex flex-col gap-3">
        <button v-for="d in [{ r: 'A47', n: 'Marina · Torre 2 · Apto 41' }, { r: 'C03', n: 'Paulo · Casa de portão verde' }]" :key="d.r" type="button" :class="S.choice">
          <span :class="badge">{{ d.r }}</span>
          <span :class="T.base">{{ d.n }}</span>
        </button>
      </div>
    </div>

    <!-- ══ 3d · Pagou de outro jeito ══ -->
    <div v-else-if="moment === 'other-pay'" :class="S.screen">
      <div class="flex flex-col gap-2">
        <span :class="badge">A47</span>
        <p :class="T.big">Como Marina pagou os R$ 58,00?</p>
      </div>
      <div class="flex flex-col gap-3">
        <button v-for="o in ['No cartão, na maquininha Azul', 'No Pix, na maquininha Azul', 'Em dinheiro']" :key="o" type="button" :class="S.choice">
          <span :class="T.base">{{ o }}</span>
        </button>
      </div>
      <p :class="T.small">Pix só pela maquininha: assim o pagamento aparece na loja na hora.</p>
    </div>

    <!-- ══ 3b · Não consegui, e a espera curta ══ -->
    <div v-else-if="moment === 'failed'" :class="S.screen">
      <div class="flex flex-col gap-2">
        <span :class="badge">A47</span>
        <p :class="T.big">O que aconteceu?</p>
      </div>
      <div class="flex flex-col gap-3">
        <button v-for="r in ['Ninguém atendeu', 'Não achei o endereço', 'Recusou o pedido', 'Pedido com problema']" :key="r" type="button" :class="S.choice">
          <span :class="T.base">{{ r }}</span>
        </button>
      </div>
      <div class="mt-auto flex flex-col items-center gap-1">
        <p :class="T.small">A loja liga para a Marina.</p>
        <button type="button" :class="S.link">Vou tentar de novo</button>
      </div>
    </div>
    <div v-else-if="moment === 'failed-wait'" class="flex size-full flex-col items-center justify-center gap-3 p-6 text-center">
      <span :class="badge">A47</span>
      <p :class="T.big">Espere 2 minutos</p>
      <p :class="T.base">A loja está ligando para a Marina.</p>
      <p :class="T.small">Sem resposta, a tela leva você para C03. A sacola de A47 volta com você.</p>
      <button type="button" :class="[S.link, 'mt-4']">Marina atendeu</button>
    </div>

    <!-- ══ 7 · A loja cancelou com ele na rua: o tom forte, oposto ao tema ══ -->
    <div v-else-if="moment === 'cancelled'" class="flex size-full flex-col justify-center gap-4 bg-inverted p-6 text-inverted">
      <span class="inline-flex w-fit items-center rounded-lg bg-default/20 px-2 py-0.5 text-[15px] font-bold tabular-nums">C03</span>
      <p class="text-[28px] font-extrabold leading-tight">Foi cancelado.</p>
      <p class="text-[18px] font-medium leading-snug">Não entregue. Traga a sacola de volta.</p>
      <p class="text-[15px] font-medium opacity-70">Paulo já foi avisado pela loja.</p>
      <button type="button" class="mt-6 min-h-16 w-full rounded-2xl bg-default text-[18px] font-extrabold text-highlighted">Entendi</button>
    </div>

    <!-- ══ 5 · Voltando: só o acerto ══ -->
    <div v-else-if="moment === 'back'" :class="[S.screen, 'justify-center']">
      <p :class="T.big">Entregue no caixa</p>
      <div class="flex flex-col gap-3">
        <div :class="S.block"><p :class="T.small">Dinheiro</p><p :class="T.big">R$ 100,00</p></div>
        <div :class="S.block"><p :class="T.base">Maquininha Azul</p></div>
      </div>
      <p :class="T.small">O balcão confere e fecha a rota.</p>
    </div>

    <!-- ══ 6 · Fechada ══ -->
    <div v-else class="flex size-full flex-col">
      <div class="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
        <span class="grid size-16 place-items-center rounded-2xl text-[36px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
        <p :class="T.big">Rota A fechada</p>
        <p :class="T.base">R$ 15,00 para você.</p>
        <p :class="T.small">A receber hoje: R$ 27,00 (2 corridas)</p>
      </div>
      <div class="m-4 flex flex-col gap-3 rounded-2xl bg-elevated p-4">
        <p :class="T.base">Receba a próxima corrida como aviso no celular.</p>
        <button type="button" class="min-h-12 rounded-xl bg-default text-[15px] font-semibold text-highlighted">Pôr na tela de início</button>
      </div>
    </div>
  </div>
</template>
