<script setup lang="ts">
// PRÉVIA (16/11, DEV-2026-030): a página do entregador da casa em HIPERFOCO.
//
// Paleta própria e neutra (dono, 16/11: nada do tema do backstage): branco, preto e só dois
// cinzas, um claro (#e5e5e5, neutral-200 do Tailwind) e um escuro (#404040, neutral-700).
//   claro:  fundo branco · bloco cinza claro · apoio cinza escuro · forte preto
//   escuro: fundo preto · bloco cinza escuro · apoio cinza claro · forte branco
//   badge do código: o cinza OPOSTO ao do bloco, para ter contraste no fundo e no bloco.
// Texto: 3 tamanhos (grande 28, normal 18, pequeno 15). Sem borda nem fio.
// Hiperfoco é sagrado: nenhuma configuração nem navegação dentro das telas da corrida; tema
// e instalação moram na tela inicial (sem corrida). Não vai ao ar.
import { rideColor } from "~/presentation/ridePalette";

export type FocusMoment =
  | "home"
  | "call"
  | "pickup"
  | "pickup-wait"
  | "drive"
  | "door"
  | "door-card"
  | "which-door"
  | "undo"
  | "problem"
  | "other-pay"
  | "failed-wait"
  | "cancelled"
  | "back"
  | "closed";

const props = defineProps<{ moment: FocusMoment; landscape?: boolean; dark?: boolean }>();
const tone = rideColor(0);

const T = {
  big: "text-[28px] font-extrabold leading-tight text-[var(--c-fg)]",
  base: "text-[18px] font-medium leading-snug text-[var(--c-fg)]",
  small: "text-[15px] font-medium leading-snug text-[var(--c-muted)]",
};
const badge = "inline-flex w-fit items-center rounded-lg bg-[var(--c-badge)] px-2 py-0.5 text-[15px] font-bold tabular-nums text-[var(--c-badge-fg)]";
const S = {
  screen: "flex min-h-0 flex-1 flex-col gap-7 overflow-y-auto p-5",
  block: "blk flex flex-col gap-1.5 rounded-2xl bg-[var(--c-block)] p-4",
  choice: "blk flex min-h-16 w-full flex-col items-start justify-center gap-1 rounded-2xl bg-[var(--c-block)] px-4 py-3 text-left",
  primary: "min-h-16 w-full rounded-2xl bg-[var(--c-strong)] text-[18px] font-extrabold text-[var(--c-strong-fg)]",
  secondary: "blk min-h-14 flex-1 rounded-2xl bg-[var(--c-block)] text-[18px] font-bold text-[var(--c-fg)]",
  footer: "flex shrink-0 flex-col gap-2 bg-[var(--c-bg)] px-5 pt-3",
};
const isDoor = computed(() => ["door", "door-card", "undo", "problem", "other-pay"].includes(props.moment));
const card = computed(() => props.moment === "door-card");
</script>

<template>
  <div class="ms-courier relative flex size-full flex-col overflow-hidden bg-[var(--c-bg)]" :class="dark ? 'is-dark' : ''" style="font-size: 16px">
    <!-- ══ Tela inicial (sem corrida): o único lugar de configuração ══ -->
    <div v-if="moment === 'home'" :class="S.screen">
      <div class="flex flex-col gap-1">
        <p :class="T.small">Nelson Boulangerie</p>
        <p :class="T.big">Olá, Diego</p>
        <p :class="T.base">Nenhuma corrida agora. Quando chegar uma, ela abre aqui.</p>
      </div>
      <div :class="S.block">
        <p :class="T.small">Hoje</p>
        <p :class="T.big">R$ 27,00</p>
        <p :class="T.base">2 corridas a receber</p>
      </div>
      <div class="flex flex-col gap-3">
        <p :class="T.small">Tema</p>
        <div class="flex gap-2">
          <button v-for="t in ['Claro', 'Escuro', 'Do celular']" :key="t" type="button"
            class="min-h-12 flex-1 rounded-xl text-[15px] font-bold"
            :class="(dark ? t === 'Escuro' : t === 'Claro') ? 'bg-[var(--c-strong)] text-[var(--c-strong-fg)]' : 'blk bg-[var(--c-block)] text-[var(--c-fg)]'">{{ t }}</button>
        </div>
      </div>
      <button type="button" :class="[S.secondary, 'flex-none']">Adicionar à tela inicial</button>
    </div>

    <!-- ══ 0 · A chamada chega (aviso do sistema do celular) ══ -->
    <div v-else-if="moment === 'call'" class="flex size-full flex-col gap-3 bg-[#1d1d1f] p-4 text-white">
      <p class="mt-10 text-center text-[64px] font-light leading-none tabular-nums">12h31</p>
      <p class="mb-6 text-center text-[15px] text-white/80">Segunda-feira, 16 de novembro</p>
      <div v-for="n in [
        { title: 'Corrida para você: Rota A', body: '2 entregas na Gleba Palhano. Você recebe R$ 15,00. Fica pronta às 12h40.', when: 'agora' },
        { title: 'Corrida para você: Pedido B12', body: '1 entrega no Centro. Você recebe R$ 8,00. Fica pronto às 13h10.', when: '12h05' },
      ]" :key="n.title" class="flex flex-col gap-1 rounded-2xl bg-white/15 p-3">
        <p class="flex items-center gap-2 text-[13px] text-white/80">
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
        <p v-else class="blk grid min-h-16 place-items-center rounded-2xl bg-[var(--c-block)] text-center text-[18px] font-medium text-[var(--c-fg)]">Espere C03 ficar pronto</p>
      </div>
    </template>

    <!-- ══ 2 · Dirigindo: o endereço em destaque ══ -->
    <div v-else-if="moment === 'drive'" class="flex size-full" :class="landscape ? 'flex-row' : 'flex-col'">
      <div class="relative min-h-0 min-w-0 flex-1" :class="dark ? 'bg-[#262626]' : 'bg-[#ebebeb]'">
        <svg viewBox="40 20 330 260" preserveAspectRatio="xMidYMid meet" class="absolute inset-0 size-full" aria-hidden="true">
          <rect x="-600" y="-600" width="1600" height="1600" :fill="dark ? '#262626' : '#ebebeb'" />
          <g :stroke="dark ? '#404040' : '#ffffff'" fill="none">
            <path d="M-600 230 L 0 200 Q 150 170 400 210 L 1000 240" stroke-width="16" />
            <path d="M140 -600 L 150 0 Q 170 160 140 320 L 130 1000" stroke-width="12" />
            <path d="M-600 110 L 1000 40" stroke-width="9" />
            <path d="M270 -600 L 330 1000" stroke-width="9" />
          </g>
          <polyline points="150,215 160,150 250,120" fill="none" :stroke="dark ? '#fff' : '#000'" stroke-width="11" stroke-linejoin="round" stroke-linecap="round" />
          <polyline points="150,215 160,150 250,120" fill="none" :stroke="tone.bg" stroke-width="6" stroke-linejoin="round" stroke-linecap="round" />
          <circle cx="250" cy="120" r="20" :fill="dark ? '#000' : '#fff'" :stroke="dark ? '#fff' : '#000'" stroke-width="4" />
          <text x="250" y="125" font-size="13" font-weight="900" text-anchor="middle" :fill="dark ? '#fff' : '#000'">A47</text>
          <circle cx="150" cy="215" r="10" :fill="dark ? '#fff' : '#000'" :stroke="dark ? '#000' : '#fff'" stroke-width="4" />
        </svg>
        <div class="absolute inset-x-3 top-3 flex items-center gap-3 rounded-2xl bg-[var(--c-strong)] px-4 py-3 text-[var(--c-strong-fg)] shadow-lg">
          <NuxtIcon name="i-lucide-corner-up-right" class="size-9 shrink-0" />
          <div class="flex min-w-0 flex-col">
            <span class="text-[28px] font-extrabold leading-none tabular-nums">200 m</span>
            <span class="truncate text-[18px] font-medium">Rua Caracas</span>
          </div>
        </div>
        <button type="button" class="absolute end-3 bottom-3 rounded-full bg-[var(--c-bg)] px-4 py-3 text-[15px] font-bold text-[var(--c-fg)] shadow-lg">Abrir no Waze</button>
      </div>
      <div class="flex shrink-0 flex-col justify-center gap-1.5 bg-[var(--c-bg)] p-5" :class="landscape ? 'w-[38%]' : ''">
        <p :class="T.small">Faltam 2 · chega 12h46</p>
        <p :class="T.big">Rua Caracas, 420</p>
        <p class="flex items-center gap-2"><span :class="badge">A47</span><span :class="T.base">Marina</span></p>
      </div>
    </div>

    <!-- ══ 3 · Na entrega (e, por cima dela, o Desfazer e a folha de Problema) ══ -->
    <template v-else-if="isDoor">
      <div :class="[S.screen, moment === 'door' || moment === 'door-card' ? '' : 'opacity-30']">
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
      <div v-if="moment === 'door' || moment === 'door-card'" :class="S.footer" style="padding-bottom: max(1rem, env(safe-area-inset-bottom))">
        <button type="button" :class="S.primary">Entreguei {{ card ? "C03" : "A47" }}</button>
        <div class="flex gap-2">
          <button type="button" :class="S.secondary">Ligar</button>
          <button type="button" :class="S.secondary">Problema</button>
        </div>
      </div>

      <!-- Desfazer -->
      <div v-if="moment === 'undo'" class="absolute inset-x-3 bottom-3 flex items-center gap-3 overflow-hidden rounded-2xl bg-[var(--c-strong)] px-4 py-4 text-[var(--c-strong-fg)] shadow-xl" style="margin-bottom: env(safe-area-inset-bottom)">
        <span class="flex-1 text-[18px] font-extrabold">A47 entregue</span>
        <button type="button" class="min-h-12 rounded-xl bg-[var(--c-bg)] px-4 text-[18px] font-extrabold text-[var(--c-fg)]">Desfazer</button>
        <span class="absolute inset-x-0 bottom-0 h-1 w-2/3 bg-[var(--c-bg)]" aria-hidden="true" />
      </div>

      <!-- Folha "Problema" e a segunda folha "Como pagou" -->
      <div v-if="moment === 'problem' || moment === 'other-pay'" class="absolute inset-x-0 bottom-0 flex max-h-[85%] flex-col gap-3 overflow-y-auto rounded-t-3xl bg-[var(--c-bg)] p-5 shadow-[0_-12px_32px_rgba(0,0,0,0.35)]" style="padding-bottom: max(1.25rem, env(safe-area-inset-bottom))">
        <span class="mx-auto mb-1 h-1.5 w-12 rounded-full bg-[var(--c-block)]" aria-hidden="true" />
        <template v-if="moment === 'problem'">
          <div class="flex flex-col gap-2"><span :class="badge">A47</span><p :class="T.big">Qual o problema?</p></div>
          <button v-for="r in ['Pagou de outro jeito', 'Ninguém atendeu', 'Não achei o endereço', 'Recusou o pedido', 'Pedido com problema']" :key="r" type="button" :class="S.choice">
            <span :class="T.base">{{ r }}</span>
          </button>
          <p :class="T.small">A loja fica sabendo na hora e liga para a Marina.</p>
        </template>
        <template v-else>
          <div class="flex flex-col gap-2"><span :class="badge">A47</span><p :class="T.big">Como pagou?</p></div>
          <button v-for="o in ['No cartão, na maquininha Azul', 'No Pix, na maquininha Azul', 'Em dinheiro']" :key="o" type="button" :class="S.choice">
            <span :class="T.base">{{ o }}</span>
          </button>
          <p :class="T.small">Pix só pela maquininha: assim o pagamento aparece na loja na hora.</p>
        </template>
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

    <!-- ══ 3b' · A espera curta ══ -->
    <div v-else-if="moment === 'failed-wait'" :class="[S.screen, 'justify-center']">
      <div class="flex flex-col gap-2">
        <span :class="badge">A47</span>
        <p :class="T.big">Espere 2 minutos</p>
      </div>
      <p :class="T.base">A loja está ligando para a Marina.</p>
      <p :class="T.small">Sem resposta, a tela leva você para C03. A sacola de A47 volta com você.</p>
      <button type="button" :class="[S.secondary, 'w-full flex-none']">Marina atendeu</button>
    </div>

    <!-- ══ 7 · A loja cancelou com ele na rua: o tom forte, oposto ao tema ══ -->
    <div v-else-if="moment === 'cancelled'" class="flex size-full flex-col justify-center gap-4 bg-[var(--c-strong)] p-6 text-[var(--c-strong-fg)]">
      <span class="inline-flex w-fit items-center rounded-lg bg-[var(--c-bg)] px-2 py-0.5 text-[15px] font-bold tabular-nums text-[var(--c-fg)]">C03</span>
      <p class="text-[28px] font-extrabold leading-tight">Foi cancelado.</p>
      <p class="text-[18px] font-medium leading-snug">Não entregue. Traga a sacola de volta.</p>
      <p class="text-[15px] font-medium">Paulo já foi avisado pela loja.</p>
      <button type="button" class="mt-6 min-h-16 w-full rounded-2xl bg-[var(--c-bg)] text-[18px] font-extrabold text-[var(--c-fg)]">Entendi</button>
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
    <div v-else :class="[S.screen, 'justify-center']">
      <span class="grid size-16 place-items-center rounded-2xl text-[36px] font-black" :style="{ background: tone.bg, color: tone.fg }">A</span>
      <p :class="T.big">Rota A fechada</p>
      <p :class="T.base">R$ 15,00 para você.</p>
      <p :class="T.small">A receber hoje: R$ 27,00 (2 corridas)</p>
    </div>
  </div>
</template>

<style scoped>
/* Dois cinzas claros (dono, 16/11): neutral-100 (#f5f5f5) no bloco e neutral-300 (#d4d4d4)
   no badge; no escuro, o espelho: neutral-800 (#262626) e neutral-600 (#525252). O texto é
   sempre preto ou branco; a hierarquia é só o tamanho. */
.ms-courier {
  --c-bg: #ffffff;
  --c-fg: #000000;
  --c-muted: #000000;
  --c-block: #f5f5f5;
  --c-block-fg: #000000;
  --c-badge: #d4d4d4;
  --c-badge-fg: #000000;
  --c-strong: #000000;
  --c-strong-fg: #ffffff;
}
.ms-courier.is-dark {
  --c-bg: #000000;
  --c-fg: #ffffff;
  --c-muted: #ffffff;
  --c-block: #262626;
  --c-block-fg: #ffffff;
  --c-badge: #525252;
  --c-badge-fg: #ffffff;
  --c-strong: #ffffff;
  --c-strong-fg: #000000;
}
/* Dentro de um bloco, o texto é o do bloco. */
.ms-courier :deep(.blk) {
  --c-fg: var(--c-block-fg);
  --c-muted: var(--c-block-fg);
}
</style>
