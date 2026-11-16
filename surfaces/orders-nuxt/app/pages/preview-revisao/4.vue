<script setup lang="ts">
// Prévia 4 (#2468): o Painel do Gestor unificado com as Entregas. Dados fictícios,
// sem backend. O cartão Pronto ganha "Chamar entregador"; a faixa "Aguardando
// entregador" e os espelhos das corridas vivas moram no Painel.
// A: a faixa abre a parte A coletar da coluna Saída.
// B: só os espelhos na coluna; a faixa vai para o topo do quadro.
import { rideColor } from "~/presentation/ridePalette";
import type { SaidaItem } from "~/components/PreviewSaidaCard.vue";

type Variant = "A" | "B";

interface Card {
  code: string;
  who: string;
  items: string;
  detail: string;
  clock: string;
  total: string;
  delivery: boolean;
  ride?: number;
  rideNote?: string;
  highlight?: boolean;
}

interface Mirror {
  number: number;
  icon: string;
  title: string;
  stops: { code: string; done?: boolean; bags?: number }[];
  hint: string;
  handoff?: string;
  pulse?: boolean;
  /** Já coletada: mora em "Saiu para entrega"; senão, em "A coletar". */
  onRoad?: boolean;
}

interface SheetOrder {
  code: string;
  who: string;
  place: string;
  note: string;
  checked: boolean;
  locked?: boolean;
  preparing?: boolean;
}

interface SheetRide {
  number: number;
  title: string;
  saving: string;
  order: string;
  custody: string;
  orders: SheetOrder[];
}

interface Sheet {
  heading: string;
  intro: string;
  rides: SheetRide[];
  primary: string;
  secondary: string;
}

interface State {
  key: string;
  caption: string;
  waiting: number;
  waitingNote: string;
  suggested: number;
  cards: Card[];
  mirrors: Mirror[];
  sheet?: Sheet;
  tapped?: string;
}

const variants: { key: Variant; title: string; change: string }[] = [
  {
    key: "A",
    title: "A · Faixa dentro da Saída, em A coletar",
    change: "A parte A coletar abre com a faixa; embaixo, as corridas chamadas e os prontos. Saiu para entrega continua igual.",
  },
  {
    key: "B",
    title: "B · Faixa no topo do quadro",
    change: "A faixa atravessa o quadro inteiro, acima das colunas; a Saída fica só com A coletar e Saiu para entrega.",
  },
];

const readyCards: Card[] = [
  {
    code: "A47",
    who: "Mariana · Loja online · Entrega",
    items: "2 Baguete tradicional, 1 Pain au chocolat",
    detail: "Gleba Palhano · Troco para R$ 100,00",
    clock: "Pronto há 6 min",
    total: "R$ 58,00",
    delivery: true,
  },
  {
    code: "C03",
    who: "Rafael · WhatsApp · Entrega",
    items: "1 Campagne, 6 Croissant",
    detail: "Bela Suíça · Pago no Pix",
    clock: "Pronto há 4 min",
    total: "R$ 74,50",
    delivery: true,
  },
  {
    code: "D12",
    who: "Juliana · iFood · Entrega",
    items: "1 Quiche lorraine, 2 Café coado",
    detail: "Centro · Leva a maquininha",
    clock: "Pronto há 2 min",
    total: "R$ 46,00",
    delivery: true,
  },
  {
    code: "E21",
    who: "Paulo · Loja online · Entrega",
    items: "1 Brioche, 1 Geleia de morango",
    detail: "Jardim Higienópolis · Pago no cartão",
    clock: "Pronto agora",
    total: "R$ 39,00",
    delivery: true,
  },
  {
    code: "A51",
    who: "Beatriz · Loja online · Entrega",
    items: "1 Tradi, 4 Pão de queijo",
    detail: "Gleba Palhano",
    clock: "Pronto há 9 min",
    total: "R$ 31,00",
    delivery: true,
    ride: 1,
    rideNote: "Vai na corrida A · Diego chega uns 14:32",
  },
  {
    code: "C07",
    who: "Tiago · Loja online · Entrega",
    items: "2 Baguete, 1 Manteiga",
    detail: "Bela Suíça",
    clock: "Pronto há 8 min",
    total: "R$ 27,00",
    delivery: true,
    ride: 1,
    rideNote: "Vai na corrida A · Diego chega uns 14:32",
  },
  {
    code: "B08",
    who: "Carla · Balcão · Retirada",
    items: "1 Bolo de laranja",
    detail: "Retira na loja",
    clock: "Pronto há 3 min",
    total: "R$ 42,00",
    delivery: false,
  },
];

const mirrorsBase: Mirror[] = [
  {
    number: 1,
    icon: "i-lucide-bike",
    title: "Diego vem buscar · chega uns 14:32",
    stops: [{ code: "A51", bags: 2 }, { code: "C07", bags: 1 }],
    hint: "Moto prata · ABC1D23",
  },
  {
    number: 2,
    icon: "i-lucide-navigation",
    title: "Léo na rua · 1 de 3 entregues",
    stops: [{ code: "D04", done: true }, { code: "A44" }, { code: "E18" }],
    hint: "Próxima: A44, Gleba Palhano",
    onRoad: true,
  },
];

// Saiu para entrega sem corrida da TaOn (o iFood leva com o entregador dele).
const roadCards: Card[] = [
  {
    code: "H58",
    who: "Marcos · iFood · Entrega",
    items: "1 Focaccia, 2 Suco de laranja",
    detail: "Centro · Entregador do iFood",
    clock: "Saiu há 9 min",
    total: "R$ 52,00",
    delivery: true,
  },
];

const mirrorsAtStore: Mirror[] = [
  {
    number: 1,
    icon: "i-lucide-store",
    title: "Diego espera na loja há 3 min",
    stops: [{ code: "A51", bags: 2 }, { code: "C07", bags: 1 }],
    hint: "Confira a placa: ABC1D23",
    handoff: "Entregue as 3 sacolas para Diego",
  },
  mirrorsBase[1]!,
];

const mirrorsSearching: Mirror[] = [
  {
    number: 3,
    icon: "i-lucide-search",
    title: "A TaOn procura entregador · há 1 min",
    stops: [{ code: "A47" }, { code: "C03" }],
    hint: "Chamada às 14:26",
    pulse: true,
  },
  ...mirrorsBase,
];

const sheetOne: Sheet = {
  heading: "Chamar entregador para A47",
  intro: "Sugestão da casa:\nJuntas: R$ 11,00 · 18 min · 7,4 km ✔\nSeparadas sairiam R$ 17,00\nC03 chega uns 6 min depois.",
  rides: [
    {
      number: 3,
      title: `Corrida ${rideLetter(3)}`,
      saving: "Juntas: R$ 11,00 · 18 min · 7,4 km ✔\nSeparadas sairiam R$ 17,00",
      order: "O entregador sai da loja e segue esta ordem: A47, depois C03.",
      custody: "Leva R$ 42,00 de troco para A47 · sem maquininha",
      orders: [
        { code: "A47", who: "Mariana", place: "Gleba Palhano", note: "Troco para R$ 100,00", checked: true, locked: true },
        { code: "C03", who: "Rafael", place: "Bela Suíça", note: "Pago no Pix · +1,9 km", checked: true },
        { code: "F09", who: "Ana", place: "Gleba Palhano", note: "Em preparo · fica pronto 14:40", checked: false, preparing: true },
      ],
    },
  ],
  primary: "Chamar corrida com A47 e C03",
  secondary: "Chamar só A47",
};

const sheetAll: Sheet = {
  heading: "Montar corridas",
  intro: "A casa juntou os prontos que ficam perto. Desmarque o que deve sair sozinho.",
  rides: [
    {
      number: 3,
      title: `Corrida ${rideLetter(3)}`,
      saving: "Juntas: R$ 11,00 · 18 min · 7,4 km ✔\nSeparadas sairiam R$ 17,00",
      order: "A47, depois C03.",
      custody: "Leva R$ 42,00 de troco · sem maquininha",
      orders: [
        { code: "A47", who: "Mariana", place: "Gleba Palhano", note: "Troco para R$ 100,00", checked: true },
        { code: "C03", who: "Rafael", place: "Bela Suíça", note: "Pago no Pix", checked: true },
      ],
    },
    {
      number: 4,
      title: `Corrida ${rideLetter(4)}`,
      saving: "Juntas: R$ 12,50 · 16 min · 6,3 km ✔\nSeparadas sairiam R$ 18,00",
      order: "D12, depois E21.",
      custody: "Leva a maquininha 2 (D12 paga no cartão na porta)",
      orders: [
        { code: "D12", who: "Juliana", place: "Centro", note: "Leva a maquininha", checked: true },
        { code: "E21", who: "Paulo", place: "Jardim Higienópolis", note: "Pago no cartão", checked: true },
      ],
    },
  ],
  primary: "Chamar as 2 corridas sugeridas",
  secondary: "Escolher na página Entregas",
};

const states: State[] = [
  {
    key: "normal",
    caption: "1 · Hora do almoço: 5 entregas esperando entregador e 2 corridas na rua.",
    waiting: 5,
    waitingNote: "4 prontos · 1 em preparo",
    suggested: 2,
    cards: readyCards,
    mirrors: mirrorsBase,
  },
  {
    key: "atStore",
    caption: "2 · Diego chegou: o espelho da corrida A diz o que entregar a ele.",
    waiting: 5,
    waitingNote: "4 prontos · 1 em preparo",
    suggested: 2,
    cards: readyCards.map((card) =>
      card.ride === 1 ? { ...card, rideNote: "Corrida A · entregue para Diego", highlight: true } : card,
    ),
    mirrors: mirrorsAtStore,
  },
  {
    key: "tapCard",
    caption: "3 · Toque em \"Chamar entregador\" no A47: o mesmo gesto já oferece levar C03 junto.",
    waiting: 5,
    waitingNote: "4 prontos · 1 em preparo",
    suggested: 2,
    cards: readyCards,
    mirrors: mirrorsBase,
    sheet: sheetOne,
    tapped: "A47",
  },
  {
    key: "tapBand",
    caption: "4 · Toque em \"Montar corridas\": as 2 sugestões num toque só.",
    waiting: 5,
    waitingNote: "4 prontos · 1 em preparo",
    suggested: 2,
    cards: readyCards,
    mirrors: mirrorsBase,
    sheet: sheetAll,
    tapped: "band",
  },
  {
    key: "called",
    caption: "5 · Depois de chamar a corrida C: A47 e C03 saem da faixa e viram um espelho novo.",
    waiting: 3,
    waitingNote: "2 prontos · 1 em preparo",
    suggested: 0,
    cards: readyCards
      .filter((card) => card.code !== "A47" && card.code !== "C03"),
    mirrors: mirrorsSearching,
  },
];

const strips = [
  { label: "Entrada", count: 3 },
  { label: "Preparo", count: 4 },
];

// Corrida aparece por letra (1 = A, 2 = B…); a cor segue pelo número.
// A Saída no cartão E (dono, 16/11): o espelho e o pronto viram o mesmo cartão.
const placeOf: Record<string, string> = {
  A51: "Gleba Palhano", C07: "Bela Suíça", A47: "Gleba Palhano", C03: "Bela Suíça",
  D04: "Centro", A44: "Gleba Palhano", E18: "Jardim Higienópolis",
};
function mirrorItem(m: Mirror): SaidaItem {
  const [moment, ...rest] = m.title.split(" · ");
  return {
    key: `r${m.number}`, ride: m.number, icon: m.icon, moment: moment ?? m.title,
    momentTone: m.handoff ? "warning" : m.onRoad || m.icon === "i-lucide-bike" ? "info" : "neutral",
    hint: ((h) => h.charAt(0).toUpperCase() + h.slice(1))([rest.join(" · "), m.hint].filter(Boolean).join(" · ")),
    stops: m.stops.map((x) => ({ code: x.code, place: placeOf[x.code] ?? "", bags: x.bags, done: x.done })),
    action: m.handoff ? { label: m.handoff, icon: "i-lucide-package-check" } : undefined,
    pulse: m.pulse,
  };
}
function cardItem(c: Card, road = false): SaidaItem {
  return {
    key: c.code, icon: road ? "i-lucide-navigation" : "i-lucide-circle-check", moment: c.clock,
    momentTone: road ? "neutral" : "success", hint: c.who,
    stops: [{ code: c.code, place: c.detail }],
    action: road ? undefined : c.delivery ? { label: "Chamar entregador", icon: "i-lucide-bike" } : { label: "Entregue ao cliente", icon: "i-lucide-hand-helping" },
  };
}
function collectItems(state: State): SaidaItem[] {
  return [...state.mirrors.filter((m) => !m.onRoad).map(mirrorItem), ...state.cards.filter((c) => !c.ride).map((c) => cardItem(c))];
}
function roadItems(state: State): SaidaItem[] {
  return [...state.mirrors.filter((m) => m.onRoad).map(mirrorItem), ...roadCards.map((c) => cardItem(c, true))];
}

function rideLetter(n: number) {
  return String.fromCharCode(64 + n);
}

function tone(n: number) {
  return rideColor(n - 1);
}

function bandText(state: State) {
  return state.waiting === 1 ? "Aguardando entregador: 1" : `Aguardando entregador: ${state.waiting}`;
}

function bandAction(state: State) {
  if (!state.suggested) return "Montar corridas";
  return state.suggested === 1 ? "Montar corridas (1 sugerida)" : `Montar corridas (${state.suggested} sugeridas)`;
}

function bagsLabel(stop: { bags?: number }) {
  return stop.bags ? ` (${stop.bags})` : "";
}

// Mapa simples da corrida sugerida: loja no centro, pinos por bairro.
const places: Record<string, { x: number; y: number }> = {
  "Gleba Palhano": { x: 70, y: 120 },
  "Bela Suíça": { x: 150, y: 140 },
  Centro: { x: 200, y: 50 },
  "Jardim Higienópolis": { x: 250, y: 100 },
};
const store = { x: 150, y: 80 };

function route(ride: SheetRide) {
  const pts = ride.orders.filter((o) => o.checked).map((o) => places[o.place] ?? store);
  return [store, ...pts].map((p) => `${p.x},${p.y}`).join(" ");
}
</script>

<template>
  <!-- Prévia de olhar: cobre a casca do Gestor (barra lateral e rolagem interna)
       para a página ter os 1440 px inteiros e rolar com o documento. -->
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default" data-preview-overlay>
        <main class="mx-auto flex w-full max-w-[1440px] flex-col gap-6 bg-default px-6 py-6 text-default" data-preview="4-painel">
          <header class="flex flex-col gap-1">
            <PreviewNav :current="4" />
            <h1 class="op-title text-highlighted">Prévia 4 · Painel unificado com as Entregas</h1>
            <p class="op-body text-muted">
              Você decide onde mora a faixa "Aguardando entregador": junto das corridas na coluna Saída (A) ou no topo do quadro inteiro (B). O "Chamar entregador" no cartão Pronto vale para os dois.
            </p>
          </header>

          <div class="grid grid-cols-2 gap-6">
            <div v-for="variant in variants" :key="variant.key" class="flex flex-col gap-1 rounded-xl border border-default bg-elevated/40 px-4 py-3">
              <div class="flex items-center gap-2">
                <span class="grid size-8 place-items-center rounded-lg bg-inverted op-label font-bold text-inverted">{{ variant.key }}</span>
                <h2 class="op-label font-semibold text-highlighted">{{ variant.title }}</h2>
              </div>
              <p class="op-body text-muted">{{ variant.change }}</p>
            </div>
          </div>

          <section v-for="state in states" :key="state.key" class="flex flex-col gap-3">
            <NuxtSeparator />
            <h3 class="op-label font-semibold text-highlighted">{{ state.caption }}</h3>

            <div class="grid grid-cols-2 gap-6">
              <div v-for="variant in variants" :key="variant.key" class="flex min-w-0 flex-col gap-3">
                <span class="op-micro font-semibold text-muted">{{ variant.key }}</span>

                <!-- o quadro -->
                <div class="flex flex-col gap-2 rounded-2xl border border-default bg-default p-2">
                  <!-- B: a faixa no topo do quadro -->
                  <div
                    v-if="variant.key === 'B' && state.waiting"
                    class="flex items-center gap-3 rounded-xl border border-default bg-elevated px-3 py-2"
                    :class="state.tapped === 'band' ? 'ring-2 ring-primary' : ''"
                  >
                    <NuxtIcon name="i-lucide-bike" class="size-5 shrink-0 text-toned" />
                    <span class="op-body font-semibold text-highlighted">{{ bandText(state) }}</span>
                    <span class="op-micro text-muted">{{ state.waitingNote }}</span>
                    <NuxtButton class="ms-auto" icon="i-lucide-route" :label="bandAction(state)" :color="state.suggested ? 'primary' : 'neutral'" :variant="state.suggested ? 'solid' : 'outline'" />
                  </div>

                  <div class="flex min-h-0 gap-2">
                    <!-- Entrada e Preparo recolhidas, como faixas -->
                    <div v-for="strip in strips" :key="strip.label" class="flex w-10 shrink-0 flex-col items-center gap-2 rounded-xl bg-elevated/60 py-3">
                      <OperatorCountChip :count="strip.count" />
                      <span class="op-micro font-semibold text-toned [writing-mode:vertical-rl]">{{ strip.label }}</span>
                    </div>

                    <!-- a coluna Saída -->
                    <section class="flex min-w-0 flex-1 flex-col gap-2 rounded-xl bg-elevated/60 p-2">
                      <header class="flex h-9 items-center gap-2 px-1">
                        <span class="op-label font-semibold text-highlighted">Saída</span>
                        <OperatorCountChip :count="state.cards.length + roadCards.length + state.mirrors.filter((m) => m.onRoad).reduce((n, m) => n + m.stops.filter((x) => !x.done).length, 0)" />
                      </header>

                      <!-- A coletar: no balcão, esperando o cliente ou o entregador -->
                      <p class="px-1 pt-1 op-micro font-semibold text-muted">A coletar</p>

                      <!-- A: a faixa abre a parte A coletar -->
                      <template v-if="variant.key === 'A'">
                        <div
                          v-if="state.waiting"
                          class="flex flex-wrap items-center gap-2 rounded-lg border border-default bg-default px-2.5 py-2"
                          :class="state.tapped === 'band' ? 'ring-2 ring-primary' : ''"
                        >
                          <NuxtIcon name="i-lucide-bike" class="size-4 shrink-0 text-toned" />
                          <span class="min-w-0 flex-1 op-body font-semibold text-highlighted">{{ bandText(state) }}</span>
                          <NuxtButton icon="i-lucide-route" :label="bandAction(state)" :color="state.suggested ? 'primary' : 'neutral'" :variant="state.suggested ? 'solid' : 'outline'" />
                        </div>
                        <p v-else class="px-1 op-micro text-muted">Nenhuma entrega esperando entregador.</p>
                      </template>

                      <!-- o cartão da Saída (forma E): corridas chamadas e prontos soltos -->
                      <div class="grid grid-cols-2 items-start gap-2">
                        <PreviewSaidaCard v-for="it in collectItems(state)" :key="it.key" :item="it" />
                      </div>

                      <!-- Saiu para entrega: o que ainda está na rua -->
                      <p class="px-1 pt-2 op-micro font-semibold text-muted">Saiu para entrega</p>
                      <div class="grid grid-cols-2 items-start gap-2">
                        <PreviewSaidaCard v-for="it in roadItems(state)" :key="it.key" :item="it" />
                      </div>
                    </section>
                  </div>
                </div>

                <!-- o sheet que abre com o toque, desenhado aberto -->
                <div v-if="state.sheet" class="flex flex-col gap-3 rounded-2xl border border-default bg-default p-4 shadow-lg">
                  <div class="flex items-start gap-2">
                    <div class="min-w-0 flex-1">
                      <p class="op-label font-semibold text-highlighted">{{ state.sheet.heading }}</p>
                      <PreviewQuote :text="state.sheet.intro" />
                    </div>
                    <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square aria-label="Fechar" />
                  </div>

                  <div v-for="ride in state.sheet.rides" :key="ride.number" class="flex gap-3 rounded-xl border p-3" :style="{ borderColor: tone(ride.number).bg }">
                    <svg viewBox="0 0 300 180" class="h-40 w-64 shrink-0 rounded-lg" role="img" :aria-label="`Mapa da ${ride.title}`">
                      <defs>
                        <pattern :id="`grid-${state.key}-${variant.key}-${ride.number}`" width="20" height="20" patternUnits="userSpaceOnUse">
                          <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#e7e2d8" stroke-width="1" />
                        </pattern>
                      </defs>
                      <rect width="300" height="180" fill="#f7f4ee" />
                      <rect width="300" height="180" :fill="`url(#grid-${state.key}-${variant.key}-${ride.number})`" />
                      <polyline :points="route(ride)" fill="none" :stroke="tone(ride.number).bg" stroke-width="4" stroke-linejoin="round" stroke-dasharray="2 6" stroke-linecap="round" />
                      <rect :x="store.x - 9" :y="store.y - 9" width="18" height="18" rx="3" fill="#111111" />
                      <g v-for="(o, k) in ride.orders" :key="o.code">
                        <circle
                          :cx="(places[o.place] ?? store).x + (o.preparing ? -30 : 0)"
                          :cy="(places[o.place] ?? store).y + (o.preparing ? 26 : 0)"
                          r="11"
                          :fill="o.checked ? tone(ride.number).bg : '#ffffff'"
                          :stroke="o.checked ? '#ffffff' : '#b9a888'"
                          stroke-width="2.5"
                        />
                        <text
                          :x="(places[o.place] ?? store).x + (o.preparing ? -30 : 0)"
                          :y="(places[o.place] ?? store).y + (o.preparing ? 30 : 4)"
                          text-anchor="middle"
                          font-size="11"
                          font-weight="700"
                          :fill="o.checked ? tone(ride.number).fg : '#6b6253'"
                        >{{ o.checked ? k + 1 : "+" }}</text>
                      </g>
                    </svg>
                    <div class="flex min-w-0 flex-1 flex-col gap-1.5">
                      <div class="flex items-center gap-2">
                        <span class="grid h-6 min-w-6 place-items-center rounded-md px-1.5 op-micro font-bold" :style="{ background: tone(ride.number).bg, color: tone(ride.number).fg }">{{ rideLetter(ride.number) }}</span>
                        <span class="op-label font-semibold text-highlighted">{{ ride.title }}</span>
                        <PreviewQuote class="ms-auto text-right" size="micro" :text="ride.saving" />
                      </div>
                      <label v-for="o in ride.orders" :key="o.code" class="flex items-center gap-2">
                        <NuxtCheckbox :model-value="o.checked" :disabled="o.locked" />
                        <span class="min-w-0 flex-1 truncate op-body">
                          <span class="font-medium text-highlighted">{{ o.code }} · {{ o.who }}</span>
                          <span class="text-muted"> · {{ o.place }}</span>
                        </span>
                        <NuxtBadge v-if="o.preparing" color="warning" icon="i-lucide-chef-hat" label="Em preparo" />
                        <span v-else class="op-micro text-muted">{{ o.note }}</span>
                      </label>
                      <p class="op-micro text-muted">{{ ride.order }}</p>
                      <p class="flex items-center gap-1 op-micro text-toned"><NuxtIcon name="i-lucide-wallet" class="size-3.5" />{{ ride.custody }}</p>
                    </div>
                  </div>

                  <div class="flex items-center justify-end gap-2">
                    <NuxtButton color="neutral" variant="outline" :label="state.sheet.secondary" />
                    <NuxtButton icon="i-lucide-bike" :label="state.sheet.primary" />
                  </div>
                </div>
              </div>
            </div>
          </section>
        </main>
      </div>
    </Teleport>
  </div>
</template>
