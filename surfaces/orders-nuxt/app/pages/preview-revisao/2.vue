<script setup lang="ts">
// Prévia 2 da revisão das Entregas: sugestões de juntar corridas no topo de Aguardando.
// Dados fictícios, sem backend: nada aqui chama a API. O mapa é desenhado em SVG
// (o Google Maps não carrega offline), só para ler a geografia.
import { rideColor } from "~/presentation/ridePalette";

// A corrida aparece por letra (1 vira A, 2 vira B); a cor segue pelo número.
const rideLetter = (n: number) => String.fromCharCode(64 + n);

definePageMeta({ key: (route) => route.path });

type Variant = "A" | "B";
type Stage = "chegou" | "montando" | "sem-cotacao";

interface Stop {
  code: string;
  customer: string;
  place: string;
  x: number;
  y: number;
  preparing?: boolean;
  note?: string;
}

interface Suggestion {
  n: number;
  codes: string[];
  together_q: number;
  apart_q: number;
  quoted: boolean;
  minutes: number;
  km: number;
  late: string;
  order: string;
}

interface BuildingRide {
  number: number;
  codes: string[];
}

interface View {
  status: string;
  waitingCount: number;
  ghosts: Suggestion[];
  hulls: Suggestion[];
  building: BuildingRide[];
  waiting: Stop[];
  suggestions: Suggestion[];
}

const W = 680;
const H = 260;
const STORE = { x: 300, y: 140 };

const STOPS: Stop[] = [
  { code: "A47", customer: "Marina", place: "Gleba Palhano", x: 168, y: 186, note: "Dinheiro: troco de R$ 20,00 (para R$ 50,00)" },
  { code: "C03", customer: "Rafael", place: "Gleba Palhano", x: 112, y: 214 },
  { code: "B12", customer: "Helena", place: "Centro", x: 392, y: 118 },
  { code: "D14", customer: "Otávio", place: "Centro", x: 446, y: 94, note: "Cartão: leva a maquininha" },
  { code: "E02", customer: "Beatriz", place: "Jardim Higienópolis", x: 512, y: 132 },
  { code: "D12", customer: "Paulo", place: "Bela Suíça", x: 560, y: 204 },
  { code: "F09", customer: "Lúcia", place: "Bela Suíça", x: 612, y: 176, preparing: true },
];
const byCode = new Map(STOPS.map((s) => [s.code, s]));

const S1: Suggestion = {
  n: 1,
  codes: ["A47", "C03"],
  together_q: 1100,
  apart_q: 1700,
  quoted: true,
  minutes: 18,
  km: 7.4,
  late: "C03 chega uns 6 min depois.",
  order: "Ordem: A47, depois C03.",
};
const S2: Suggestion = {
  n: 2,
  codes: ["B12", "D14", "E02"],
  together_q: 2030,
  apart_q: 2710,
  quoted: true,
  minutes: 26,
  km: 9.8,
  late: "E02 chega uns 9 min depois.",
  order: "Ordem: B12, D14, depois E02.",
};
const S2_UNQUOTED: Suggestion = { ...S2, quoted: false };

function brl(q: number): string {
  return `R$ ${(q / 100).toFixed(2).replace(".", ",")}`;
}

function km(n: number): string {
  return `${n.toFixed(1).replace(".", ",")} km`;
}

/** Juntas × separadas, sempre em duas linhas; o ✔ marca a opção mais barata. */
function quoteLines(together_q: number, apart_q: number, minutes: number, dist: number): string[] {
  const together = `Juntas: ${brl(together_q)} · ${minutes} min · ${km(dist)}`;
  return together_q <= apart_q
    ? [`${together} ✔`, `Separadas sairiam ${brl(apart_q)}`]
    : [together, `Separadas sai mais barato: ${brl(apart_q)} ✔`];
}

/** O total de várias corridas: preço e distância somam; o tempo é o da corrida mais longa (saem juntas). */
function totalQuoteLines(sugg: Suggestion[]): string[] {
  return quoteLines(
    sugg.reduce((n, s) => n + s.together_q, 0),
    sugg.reduce((n, s) => n + s.apart_q, 0),
    Math.max(...sugg.map((s) => s.minutes)),
    sugg.reduce((n, s) => n + s.km, 0),
  );
}

function stop(code: string): Stop {
  return byCode.get(code)!;
}

function pct(p: { x: number; y: number }) {
  return { left: `${(p.x / W) * 100}%`, top: `${(p.y / H) * 100}%` };
}

function pathOf(codes: string[]): string {
  return [STORE, ...codes.map(stop)].map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" ");
}

function hullOf(codes: string[]) {
  const pts = codes.map(stop);
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return { cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, rx: (maxX - minX) / 2 + 36, ry: (maxY - minY) / 2 + 30 };
}

function tagAt(codes: string[]) {
  const h = hullOf(codes);
  return pct({ x: h.cx, y: Math.max(h.cy - h.ry - 4, 14) });
}

function places(codes: string[]): string {
  return [...new Set(codes.map((c) => stop(c).place))].join(", ");
}

function view(variant: Variant, stage: Stage): View {
  const sugg = stage === "sem-cotacao" ? [S1, S2_UNQUOTED] : [S1, S2];
  if (variant === "A") {
    if (stage === "montando") {
      return {
        status: "2 aguardando · 5 editando · 0 corridas",
        waitingCount: 2,
        ghosts: [],
        hulls: [],
        building: [
          { number: 1, codes: S1.codes },
          { number: 2, codes: S2.codes },
        ],
        waiting: [stop("D12"), stop("F09")],
        suggestions: [],
      };
    }
    return {
      status: "7 aguardando · 0 editando · 0 corridas",
      waitingCount: 7,
      ghosts: sugg,
      hulls: [],
      building: [],
      waiting: STOPS.filter((s) => !sugg.some((g) => g.codes.includes(s.code))),
      suggestions: sugg,
    };
  }
  // B: só o realce no mapa; o operador monta à mão.
  if (stage === "montando") {
    return {
      status: "5 aguardando · 2 editando · 0 corridas",
      waitingCount: 5,
      ghosts: [],
      hulls: [S2],
      building: [{ number: 1, codes: S1.codes }],
      waiting: STOPS.filter((s) => !S1.codes.includes(s.code)),
      suggestions: [S2],
    };
  }
  // Sem cotação, o realce não aparece: dinheiro da casa falha fechado.
  const lit = sugg.filter((s) => s.quoted);
  return {
    status: "7 aguardando · 0 editando · 0 corridas",
    waitingCount: 7,
    ghosts: [],
    hulls: lit,
    building: [],
    waiting: STOPS,
    suggestions: lit,
  };
}

function suggestionOf(v: View, code: string): Suggestion | undefined {
  return v.suggestions.find((s) => s.codes.includes(code));
}

function headline(sugg: Suggestion[]): string {
  const orders = sugg.reduce((n, s) => n + s.codes.length, 0);
  if (sugg.every((s) => s.quoted)) {
    return [`${sugg.length} corridas sugeridas: ${orders} pedidos.`, ...totalQuoteLines(sugg)].join("\n");
  }
  const quoted = sugg.filter((s) => s.quoted).map((s) => s.n);
  return `${sugg.length} corridas sugeridas: ${orders} pedidos. Só a ${quoted.join(" e a ")} tem cotação agora.`;
}

const COLUMNS: { variant: Variant; title: string; change: string }[] = [
  { variant: "A", title: "A · Cartão com botão", change: "A sugestão vem cotada e vira corrida em dois toques: Chamar e confirmar." },
  { variant: "B", title: "B · Só realce no mapa", change: "O mapa marca os grupos; o operador toca pedido por pedido e monta cada corrida." },
];

const ROWS: { stage: Stage; caption: string; cells: Record<Variant, string> }[] = [
  {
    stage: "chegou",
    caption: "1. Chegaram as sugestões: 7 aguardando, 5 cabem em 2 corridas.",
    cells: {
      A: "Cartão no topo de Aguardando, rota tracejada no mapa. D12 fica de fora (sem par perto) e F09 está em preparo.",
      B: "Nada de cartão: o mapa envolve os grupos e a lista marca quem é de qual sugestão.",
    },
  },
  {
    stage: "montando",
    caption: "2. O operador age sobre as sugestões.",
    cells: {
      A: "Tocou em \"Chamar as 2 corridas\": confere tudo no mesmo painel e confirma.",
      B: "Tocou em A47 e C03: a corrida A nasce em Editando. A sugestão 2 continua marcada.",
    },
  },
  {
    stage: "sem-cotacao",
    caption: "3. A TaOn não cotou a sugestão 2.",
    cells: {
      A: "Sem preço, não há \"Chamar juntas\" nem o botão das 2: só montar à mão.",
      B: "Sem preço, o grupo 2 nem é realçado. Fica só a sugestão 1.",
    },
  },
];
</script>

<template>
  <!-- Prévia de olhar: cobre a casca do Gestor (barra lateral e rolagem interna)
       para a página ter os 1440 px inteiros e rolar com o documento. -->
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default" data-preview-overlay>
        <main class="mx-auto flex w-full max-w-[1440px] flex-col gap-6 bg-default p-6" data-preview="revisao-2">
          <header class="flex flex-col gap-1">
            <PreviewNav :current="2" />
            <h1 class="op-title text-highlighted">Prévia 2 · Sugestões no topo de Aguardando</h1>
            <p class="op-body text-toned">
              Você decide: a sugestão de juntar corridas vem num cartão com botão para chamar (A), ou só aparece no mapa e o operador monta a corrida à mão (B).
            </p>
          </header>

          <div class="grid grid-cols-2 gap-6">
            <div v-for="col in COLUMNS" :key="col.variant" class="rounded-lg bg-elevated px-4 py-3">
              <p class="op-label font-semibold text-highlighted">
                <span class="mr-1 inline-grid size-6 place-items-center rounded-md bg-inverted text-inverted">{{ col.variant }}</span>
                {{ col.title }}
              </p>
              <p class="mt-1 op-body text-muted">{{ col.change }}</p>
            </div>
          </div>

          <section v-for="row in ROWS" :key="row.stage" class="flex flex-col gap-3">
            <h2 class="op-label font-semibold text-highlighted">{{ row.caption }}</h2>
            <div class="grid grid-cols-2 items-start gap-6">
              <div v-for="col in COLUMNS" :key="col.variant" class="flex flex-col gap-2">
                <p class="op-micro text-muted"><span class="font-bold text-toned">{{ col.variant }}.</span> {{ row.cells[col.variant] }}</p>

                <template v-for="v in [view(col.variant, row.stage)]" :key="`${col.variant}-${row.stage}`">
                  <div class="overflow-hidden rounded-xl border border-default bg-default shadow-sm">
                    <!-- cabeçalho da página, como o OperatorPageHeader -->
                    <div class="flex items-center justify-between gap-3 border-b border-default px-4 py-2.5">
                      <span class="op-label font-semibold text-highlighted">Entregas</span>
                      <span class="op-micro text-muted">{{ v.status }}</span>
                    </div>

                    <!-- mapa simples -->
                    <div class="relative border-b border-default" style="aspect-ratio: 680 / 260">
                      <svg class="absolute inset-0 size-full" :viewBox="`0 0 ${W} ${H}`" aria-hidden="true">
                        <defs>
                          <pattern :id="`grid-${col.variant}-${row.stage}`" width="34" height="34" patternUnits="userSpaceOnUse">
                            <path d="M34 0H0V34" fill="none" stroke="#e4ddcf" stroke-width="1" />
                          </pattern>
                        </defs>
                        <rect :width="W" :height="H" fill="#f6f2ea" />
                        <rect :width="W" :height="H" :fill="`url(#grid-${col.variant}-${row.stage})`" />
                        <path d="M0 150 C 140 140, 260 150, 680 120" stroke="#ffffff" stroke-width="9" fill="none" />
                        <path d="M300 0 C 310 90, 290 180, 320 260" stroke="#ffffff" stroke-width="7" fill="none" />
                        <path d="M60 260 C 160 200, 220 170, 300 140" stroke="#ffffff" stroke-width="6" fill="none" />
                        <path d="M300 140 C 420 160, 520 190, 680 230" stroke="#ffffff" stroke-width="6" fill="none" />
                        <ellipse cx="96" cy="120" rx="48" ry="22" fill="#d6e6ef" />
                        <text x="70" y="248" font-size="11" fill="#9a9183">Gleba Palhano</text>
                        <text x="352" y="200" font-size="11" fill="#9a9183">Centro</text>
                        <text x="548" y="92" font-size="11" fill="#9a9183">Jardim Higienópolis</text>
                        <text x="586" y="244" font-size="11" fill="#9a9183">Bela Suíça</text>

                        <!-- A: rota-fantasma da sugestão (tracejado longo, cinza) -->
                        <path
                          v-for="g in v.ghosts"
                          :key="`g${g.n}`"
                          :d="pathOf(g.codes)"
                          fill="none"
                          stroke="#5f6670"
                          :stroke-opacity="g.quoted ? 0.6 : 0.3"
                          stroke-width="4"
                          stroke-dasharray="11 8"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
                        <!-- B: realce do grupo, sem rota -->
                        <ellipse
                          v-for="h in v.hulls"
                          :key="`h${h.n}`"
                          v-bind="hullOf(h.codes)"
                          fill="#5f6670"
                          fill-opacity="0.08"
                          stroke="#5f6670"
                          stroke-opacity="0.6"
                          stroke-width="2"
                          stroke-dasharray="6 5"
                        />
                        <!-- editando: pontilhado na cor da corrida -->
                        <path
                          v-for="r in v.building"
                          :key="`b${r.number}`"
                          :d="pathOf(r.codes)"
                          fill="none"
                          :stroke="rideColor(r.number - 1).bg"
                          stroke-width="4"
                          stroke-dasharray="0.1 9"
                          stroke-linecap="round"
                        />
                      </svg>

                      <!-- rótulo da sugestão no mapa -->
                      <span
                        v-for="g in [...v.ghosts, ...v.hulls]"
                        :key="`t${g.n}`"
                        class="absolute z-20 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-full border border-dashed border-[#5f6670] bg-white/95 px-2 py-0.5 op-micro font-semibold text-toned shadow-sm"
                        :style="tagAt(g.codes)"
                      >
                        Sugestão {{ g.n }}<template v-if="v.ghosts.length && g.quoted"> · {{ brl(g.together_q) }}</template><template v-else-if="v.ghosts.length"> · sem cotação</template>
                      </span>

                      <!-- a loja -->
                      <span class="absolute z-10 grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-inverted text-inverted shadow-lg ring-4 ring-white" :style="pct(STORE)" title="A loja">
                        <NuxtIcon name="i-lucide-store" class="size-4" />
                      </span>

                      <!-- editando: parada redonda pontilhada, número na ordem -->
                      <template v-for="r in v.building" :key="`bs${r.number}`">
                        <span v-for="(code, k) in r.codes" :key="code" class="absolute z-10 -translate-x-1/2 -translate-y-1/2" :style="pct(stop(code))">
                          <span class="grid size-8 place-items-center rounded-full border-4 border-dotted bg-white op-label font-bold tabular-nums text-highlighted shadow-sm" :style="{ borderColor: rideColor(r.number - 1).bg }">{{ k + 1 }}</span>
                        </span>
                      </template>

                      <!-- aguardando: quadrado branco com o código -->
                      <span v-for="o in [...v.waiting, ...v.ghosts.flatMap((g) => g.codes.map(stop))]" :key="o.code" class="absolute z-10 -translate-x-1/2 -translate-y-1/2" :style="pct(o)">
                        <span class="relative grid h-8 min-w-8 place-items-center rounded-lg border-2 border-[#b9a888] bg-white px-1.5 op-micro font-semibold tabular-nums text-toned shadow-md">
                          {{ o.code }}
                          <span v-if="o.preparing" class="absolute -right-1 -bottom-1 grid size-4 place-items-center rounded-full bg-white text-toned ring-1 ring-default" title="Em preparo"><NuxtIcon name="i-lucide-chef-hat" class="size-2.5" /></span>
                        </span>
                      </span>

                      <!-- legenda pela forma -->
                      <div class="absolute inset-x-3 top-2 z-30 mx-auto flex w-fit items-center gap-3 rounded-md bg-white/90 px-2.5 py-1 op-micro text-toned shadow-sm">
                        <span class="flex items-center gap-1"><span class="h-3.5 w-4 rounded-[3px] border-2 bg-white" style="border-color: #b9a888" />Aguardando</span>
                        <span v-if="col.variant === 'A'" class="flex items-center gap-1"><svg width="22" height="6" aria-hidden="true"><path d="M1 3H21" stroke="#5f6670" stroke-opacity="0.6" stroke-width="3" stroke-dasharray="6 4" /></svg>Rota sugerida</span>
                        <span v-else class="flex items-center gap-1"><span class="h-3.5 w-5 rounded-full border-2 border-dashed border-[#5f6670] bg-[#5f6670]/10" />Sugestão</span>
                        <span class="flex items-center gap-1"><span class="size-3.5 rounded-full border-[3px] border-dotted bg-white" style="border-color: #5f6670" />Editando</span>
                      </div>
                    </div>

                    <!-- lista -->
                    <div class="px-4 py-4">
                      <!-- A, painel de confirmação aberto -->
                      <template v-if="col.variant === 'A' && row.stage === 'montando'">
                        <p class="op-micro text-muted">Aguardando: D12 e F09 ficam.</p>
                        <div class="mt-2 rounded-xl border border-default bg-default p-4 shadow-lg ring-1 ring-default">
                          <p class="op-label font-semibold text-highlighted">Chamar 2 corridas</p>
                          <p class="mt-0.5 op-body text-muted">5 pedidos.</p>
                          <PreviewQuote :text="totalQuoteLines([S1, S2])" />
                          <div class="mt-3 flex flex-col gap-2">
                            <div v-for="s in [S1, S2]" :key="s.n" class="rounded-lg border border-default px-3 py-2.5">
                              <div class="flex items-center gap-2">
                                <span class="grid h-6 min-w-6 place-items-center rounded-md px-1.5 op-micro font-bold" :style="{ background: rideColor(s.n - 1).bg, color: rideColor(s.n - 1).fg }">{{ rideLetter(s.n) }}</span>
                                <span class="op-label font-semibold text-highlighted">Corrida {{ rideLetter(s.n) }}</span>
                                <span class="min-w-0 flex-1 truncate op-body text-toned">{{ s.codes.join(" → ") }}</span>
                                <span class="op-body font-semibold tabular-nums text-highlighted">{{ brl(s.together_q) }}</span>
                              </div>
                              <p class="mt-1 op-micro text-muted">{{ s.order }} {{ s.late }}</p>
                              <p v-for="code in s.codes.filter((c) => stop(c).note)" :key="code" class="op-micro text-toned">{{ code }}: {{ stop(code).note }}</p>
                              <div v-if="s.codes.includes('D14')" class="mt-2 flex items-center gap-2">
                                <span class="op-body text-toned">Maquininha:</span>
                                <NuxtButton color="neutral" variant="outline" trailing-icon="i-lucide-chevron-down" label="Maquininha 2" />
                              </div>
                            </div>
                          </div>
                          <div class="mt-3 flex items-center justify-end gap-2">
                            <NuxtButton color="neutral" variant="ghost" label="Voltar" />
                            <NuxtButton icon="i-lucide-bike" label="Chamar as 2 corridas" />
                          </div>
                        </div>
                      </template>

                      <template v-else>
                        <!-- editando (B, montou à mão) -->
                        <section v-if="v.building.length" class="mb-5">
                          <h3 class="flex items-center gap-2 op-label font-semibold text-highlighted">
                            <NuxtIcon name="i-lucide-route" class="size-4 text-muted" />
                            Editando
                            <OperatorCountChip :count="v.building.length" />
                          </h3>
                          <div v-for="r in v.building" :key="r.number" class="mt-2 rounded-xl border bg-default" :style="{ borderColor: rideColor(r.number - 1).bg, boxShadow: `0 0 0 3px ${rideColor(r.number - 1).bg}2e` }">
                            <div class="flex items-center gap-2 px-3 py-2.5">
                              <span class="grid h-6 min-w-6 place-items-center rounded-md px-1.5 op-micro font-bold" :style="{ background: rideColor(r.number - 1).bg, color: rideColor(r.number - 1).fg }">{{ rideLetter(r.number) }}</span>
                              <span class="op-label font-semibold text-highlighted">Corrida {{ rideLetter(r.number) }}</span>
                              <span class="op-micro tabular-nums text-muted">{{ r.codes.length }} de 4</span>
                            </div>
                            <ol class="flex flex-col gap-1 px-3 pb-3">
                              <li v-for="(code, k) in r.codes" :key="code" class="flex items-center gap-2.5 rounded-lg bg-elevated/60 px-2 py-1.5">
                                <span class="grid size-6 shrink-0 place-items-center rounded-full border-[3px] border-dotted bg-white op-micro font-bold text-highlighted" :style="{ borderColor: rideColor(r.number - 1).bg }">{{ k + 1 }}</span>
                                <span class="min-w-0 flex-1">
                                  <span class="block truncate op-body font-medium text-highlighted">{{ code }} · {{ stop(code).customer }}</span>
                                  <span class="block truncate op-micro text-muted">{{ [stop(code).place, stop(code).note].filter(Boolean).join(" · ") }}</span>
                                </span>
                                <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square :aria-label="`Tirar ${code}`" />
                              </li>
                              <li class="px-1 pt-1 op-micro text-muted">A TaOn leva na ordem do percurso, a partir da loja.</li>
                            </ol>
                          </div>
                        </section>

                        <!-- aguardando -->
                        <section>
                          <h3 class="flex items-center gap-2 op-label font-semibold text-highlighted">
                            <span class="size-3 rounded-full border-2 bg-white" style="border-color: #b9a888" />
                            Aguardando
                            <OperatorCountChip :count="v.waitingCount" />
                          </h3>

                          <!-- A: o cartão das sugestões -->
                          <div v-if="col.variant === 'A' && v.suggestions.length" class="mt-2 rounded-xl border border-default bg-elevated/50 p-3">
                            <p class="flex items-start gap-2 op-body font-medium text-highlighted">
                              <NuxtIcon name="i-lucide-sparkles" class="mt-0.5 size-4 shrink-0 text-muted" />
                              <span class="flex flex-col"><span>{{ headline(v.suggestions).split("\n")[0] }}</span><PreviewQuote :text="headline(v.suggestions).split('\n').slice(1)" class="font-normal" /></span>
                            </p>
                            <ul class="mt-2 flex flex-col divide-y divide-default">
                              <li v-for="s in v.suggestions" :key="s.n" class="flex items-center gap-3 py-2">
                                <span class="grid h-6 min-w-6 shrink-0 place-items-center rounded-md border border-dashed border-[#5f6670] bg-white op-micro font-bold text-toned">{{ s.n }}</span>
                                <span class="min-w-0 flex-1">
                                  <span class="block truncate op-body"><span class="font-medium text-highlighted">{{ s.codes.join(" + ") }}</span> <span class="text-muted">· {{ places(s.codes) }}</span></span>
                                  <template v-if="s.quoted">
                                    <PreviewQuote size="micro" :text="quoteLines(s.together_q, s.apart_q, s.minutes, s.km)" />
                                    <span class="block op-micro text-muted">{{ s.late }}</span>
                                  </template>
                                  <span v-else class="block op-micro text-warning">A TaOn não cotou agora. Monte a corrida se quiser levar junto.</span>
                                </span>
                                <NuxtButton v-if="s.quoted" color="neutral" variant="outline" icon="i-lucide-bike" label="Chamar juntas" />
                                <NuxtButton v-else color="neutral" variant="outline" icon="i-lucide-route" label="Montar a corrida" />
                                <NuxtButton color="neutral" variant="ghost" label="Agora não" />
                              </li>
                            </ul>
                            <NuxtButton v-if="v.suggestions.every((s) => s.quoted)" block class="mt-2" icon="i-lucide-bike" :label="`Chamar as ${v.suggestions.length} corridas`" />
                          </div>

                          <!-- B: só uma linha de leitura -->
                          <p v-if="col.variant === 'B' && v.suggestions.length" class="mt-2 flex items-start gap-2 op-micro text-muted">
                            <NuxtIcon name="i-lucide-map" class="mt-0.5 size-3.5 shrink-0" />
                            O mapa marca {{ v.suggestions.length === 1 ? "1 grupo que cabe" : `${v.suggestions.length} grupos que cabem` }} numa corrida só. Toque nos pedidos para montar.
                          </p>

                          <ul class="mt-2 flex flex-col">
                            <li v-for="o in v.waiting" :key="o.code">
                              <NuxtButton color="neutral" variant="ghost" block class="justify-start gap-2.5 text-left">
                                <span class="grid size-6 shrink-0 place-items-center rounded-full border-2 bg-white text-toned" style="border-color: #b9a888"><NuxtIcon name="i-lucide-plus" class="size-3.5" /></span>
                                <span class="min-w-0 flex-1">
                                  <span class="block truncate op-body"><span class="font-medium text-highlighted">{{ o.code }} · {{ o.customer }}</span> <span class="text-muted">· {{ o.place }}</span></span>
                                  <span v-if="o.note" class="block truncate op-micro text-muted">{{ o.note }}</span>
                                </span>
                                <NuxtBadge v-if="col.variant === 'B' && suggestionOf(v, o.code)" :label="`Sugestão ${suggestionOf(v, o.code)!.n}`" color="neutral" />
                                <NuxtBadge v-if="o.preparing" label="Em preparo" color="warning" icon="i-lucide-chef-hat" />
                              </NuxtButton>
                            </li>
                          </ul>
                        </section>
                      </template>
                    </div>

                    <!-- base: chamar o que está em Editando (B, montou à mão) -->
                    <div v-if="col.variant === 'B' && v.building.length" class="flex items-center gap-3 border-t border-default bg-default p-4">
                      <p class="min-w-0 flex-1 op-body text-muted">2 pedidos em 1 corrida · 5 ficam</p>
                      <NuxtButton icon="i-lucide-bike" label="Chamar a corrida A" />
                    </div>
                  </div>
                </template>
              </div>
            </div>
          </section>
        </main>
      </div>
    </Teleport>
  </div>
</template>
