<script setup lang="ts">
// PRÉVIA 3 (revisão das Entregas, 16/11/2026): a coluna "Editando" renovada.
// Página de prévia, autocontida: dados fictícios, sem chamada ao servidor. O mapa é um
// desenho simples (fundo com grade, loja preta, pinos), não o Google Maps.
// A = como é hoje (deliveries.vue). B = a proposta: ordem real da rota, cotação por
// corrida, maquininha por corrida, troco editável e parada em preparo marcada.
import { rideColor } from "~/presentation/ridePalette";

type Pay = "cartao" | "dinheiro" | "pix";
interface Stop {
  ref: string;
  code: string;
  customer: string;
  place: string;
  x: number;
  y: number;
  pay: Pay;
  total_q: number;
  /** Troco para quanto (centavos), só no dinheiro. */
  change_for_q?: number;
  /** Em preparo: a hora em que fica pronto. */
  ready_eta?: string;
}
type Quote =
  | { kind: "saving"; together_q: number; minutes: number; km: string; separate_q: number }
  | { kind: "separate"; together_q: number; minutes: number; km: string; separate_q: number }
  | { kind: "single"; together_q: number; minutes: number; km: string }
  | { kind: "failed" };
interface Ride {
  number: number;
  /** A ordem dos toques do operador (o que a tela de hoje numera). */
  tapped: string[];
  /** A ordem real da rota, a que vai para a TaOn. */
  route: string[];
  quote: Quote;
  /** Maquininha pré-atribuída a esta corrida; null quando falta. */
  machine: string | null;
}
interface Scenario {
  key: string;
  title: string;
  caption: string;
  rides: Ride[];
  active: number;
  waiting: string[];
  /** Como o rodapé de hoje resolve a maquininha (uma para todas). */
  todayMachine: string;
  todayNote: string;
  shortage?: string;
  callLabel: string;
  preparingRef?: string;
}

const STORE = { x: 50, y: 46 };
const STOPS: Stop[] = [
  { ref: "A47", code: "A47", customer: "Mariana", place: "Gleba Palhano", x: 24, y: 66, pay: "cartao", total_q: 8790 },
  { ref: "C03", code: "C03", customer: "Rafael", place: "Gleba Palhano", x: 14, y: 80, pay: "dinheiro", total_q: 3890, change_for_q: 5000 },
  { ref: "B12", code: "B12", customer: "Juliana", place: "Bela Suíça", x: 72, y: 72, pay: "cartao", total_q: 6240 },
  { ref: "D14", code: "D14", customer: "Paulo", place: "Bela Suíça", x: 82, y: 86, pay: "dinheiro", total_q: 4570, change_for_q: 10000 },
  { ref: "D12", code: "D12", customer: "Carla", place: "Jardim Higienópolis", x: 74, y: 22, pay: "pix", total_q: 5320, ready_eta: "12:35" },
  { ref: "E02", code: "E02", customer: "Sérgio", place: "Centro", x: 40, y: 30, pay: "pix", total_q: 2980 },
];
const byRef = new Map(STOPS.map((stop) => [stop.ref, stop]));
const stop = (ref: string) => byRef.get(ref)!;

const SCENARIOS: Scenario[] = [
  {
    key: "s1",
    title: "Juntas sai mais barato, duas maquininhas livres",
    caption: "O operador tocou C03 antes de A47. Hoje a tela numera pelo toque; a TaOn recebe A47 primeiro.",
    rides: [
      {
        number: 1,
        tapped: ["C03", "A47"],
        route: ["A47", "C03"],
        quote: { kind: "saving", together_q: 1100, minutes: 18, km: "5,2", separate_q: 1700 },
        machine: "Maquininha 2",
      },
      {
        number: 2,
        tapped: ["D14", "B12"],
        route: ["B12", "D14"],
        quote: { kind: "saving", together_q: 1240, minutes: 21, km: "6,1", separate_q: 1990 },
        machine: "Maquininha 3",
      },
    ],
    active: 2,
    waiting: ["E02", "D12"],
    todayMachine: "Maquininha 2",
    todayNote: "Um seletor só no rodapé: a mesma maquininha vai nas duas corridas.",
    callLabel: "Chamar 2 corridas",
  },
  {
    key: "s2",
    title: "Separadas sai mais barato, falta maquininha",
    caption: "A47 e D14 ficam longe uma da outra. Só 1 maquininha está livre e as 2 corridas levam cartão.",
    rides: [
      {
        number: 1,
        tapped: ["D14", "A47"],
        route: ["A47", "D14"],
        quote: { kind: "separate", together_q: 1680, minutes: 29, km: "9,4", separate_q: 1420 },
        machine: "Maquininha 1",
      },
      {
        number: 2,
        tapped: ["B12"],
        route: ["B12"],
        quote: { kind: "single", together_q: 980, minutes: 14, km: "3,9" },
        machine: null,
      },
    ],
    active: 1,
    waiting: ["C03", "E02", "D12"],
    todayMachine: "Maquininha 1",
    todayNote: "Com 1 maquininha livre ela entra sozinha, e vai nas duas corridas sem aviso.",
    shortage: "Faltam maquininhas: 2 corridas levam cartão e só 1 está livre.",
    callLabel: "Chamar 2 corridas",
  },
  {
    key: "s3",
    title: "A TaOn não cotou, uma parada ainda em preparo",
    caption: "D12 fica pronto às 12:35. Hoje nada na corrida avisa; a proposta marca a parada e o botão diz o que acontece.",
    rides: [
      {
        number: 1,
        tapped: ["D12", "A47", "C03"],
        route: ["A47", "C03", "D12"],
        quote: { kind: "failed" },
        machine: "Maquininha 2",
      },
    ],
    active: 1,
    waiting: ["B12", "D14", "E02"],
    todayMachine: "Maquininha 2",
    todayNote: "O botão chama sem lembrar que D12 ainda não está pronto.",
    callLabel: "Chamar mesmo assim (D12 em preparo)",
    preparingRef: "D12",
  },
];

const money = (q: number) => `R$ ${(q / 100).toFixed(2).replace(".", ",")}`;
const parseMoney = (text: string) => {
  const value = Number(text.replace(/\./g, "").replace(",", ".").replace(/[^\d.]/g, ""));
  return Number.isFinite(value) ? Math.round(value * 100) : 0;
};

// Troco editável na página (B): uma caixa por parada em dinheiro, por prévia.
const changeFor = reactive<Record<string, string>>({});
for (const scenario of SCENARIOS) {
  for (const ride of scenario.rides) {
    for (const ref of ride.route) {
      const item = stop(ref);
      if (item.change_for_q) changeFor[`${scenario.key}:${ref}`] = (item.change_for_q / 100).toFixed(2).replace(".", ",");
    }
  }
}
function changeLine(scenarioKey: string, ref: string) {
  const item = stop(ref);
  const given = parseMoney(changeFor[`${scenarioKey}:${ref}`] ?? "");
  if (!given) return "Sem troco: o cliente paga o valor exato.";
  if (given < item.total_q) return `Menos que o pedido (${money(item.total_q)}). Confira com o cliente.`;
  return `Leva ${money(given - item.total_q)} de troco.`;
}
const todayChangeLabel = (ref: string) => {
  const item = stop(ref);
  return item.change_for_q ? `Troco para ${money(item.change_for_q)}` : "";
};
const payLabel: Record<Pay, string> = { cartao: "Cartão na entrega", dinheiro: "Dinheiro", pix: "Pix pago" };

// O mapa: as corridas na ordem dada (hoje: toques; proposta: rota real).
function ridePath(refs: string[]) {
  const chain = [STORE, ...refs.map((ref) => stop(ref))];
  return chain.map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" ");
}
function pinOf(scenario: Scenario, ref: string, variant: "A" | "B") {
  for (const ride of scenario.rides) {
    const list = variant === "A" ? ride.tapped : ride.route;
    const at = list.indexOf(ref);
    if (at >= 0) return { ride: ride.number, order: at + 1 };
  }
  return null;
}
const ordered = (ride: Ride, variant: "A" | "B") => (variant === "A" ? ride.tapped : ride.route);
// Corrida tem letra na tela (dono, 16/11/2026): 1 vira A, 2 vira B. A cor segue pelo número.
const rideLetter = (n: number) => String.fromCharCode(64 + n);
const rideMachine = (ride: Ride) => ride.route.some((ref) => stop(ref).pay === "cartao");
// Decidido pelo dono (16/11/2026): B. A Proposta vem primeiro e maior; Hoje fica ao lado, apagada.
const columns = [
  { id: "B" as const, title: "Proposta", tag: "Decidido" },
  { id: "A" as const, title: "Hoje", tag: "Referência" },
];

// Diagramação do texto: espaço inseparável dentro de cada grandeza ("R$ 11,00", "18 min",
// "5,2 km ✔"), para a linha só quebrar entre um dado e outro, nunca no meio de um.
const nb = (text: string) => text.replace(/ /g, " ");
function quoteLines(quote: Quote): string[] {
  if (quote.kind === "saving") {
    return [
      `Juntas: ${nb(money(quote.together_q))} · ${nb(`${quote.minutes} min`)} · ${nb(`${quote.km} km ✔`)}`,
      `Separadas sairiam ${nb(money(quote.separate_q))}`,
    ];
  }
  if (quote.kind === "separate") {
    return [
      `Juntas: ${nb(money(quote.together_q))} · ${nb(`${quote.minutes} min`)} · ${nb(`${quote.km} km`)}`,
      `Separadas sai mais barato: ${nb(`${money(quote.separate_q)} ✔`)}`,
    ];
  }
  if (quote.kind === "single") {
    return [`Uma parada: ${nb(money(quote.together_q))} · ${nb(`${quote.minutes} min`)} · ${nb(`${quote.km} km`)}`];
  }
  return [];
}
const stopFacts = (ref: string) => {
  const item = stop(ref);
  return [item.place, payLabel[item.pay], money(item.total_q)];
};
</script>

<template>
  <!-- Prévia de olhar: cobre a casca do Gestor (barra lateral e rolagem interna)
       para a página ter os 1440 px inteiros e rolar com o documento. -->
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default" data-preview-overlay>
        <main class="mx-auto flex w-full max-w-[1440px] flex-col gap-6 bg-default px-4 pt-6 pb-32 sm:px-8 sm:pt-8" data-preview-revisao="3">
          <header class="flex flex-col gap-1">
            <p class="op-micro font-semibold uppercase tracking-wide text-muted">Gestor · Entregas</p>
            <PreviewNav :current="3" />
            <h1 class="op-title font-semibold text-highlighted">Prévia 3 · Coluna Editando renovada</h1>
          </header>

          <div class="flex items-start gap-3 rounded-xl border-2 border-success bg-success/10 px-4 py-3" data-decision="B">
            <span class="grid size-8 shrink-0 place-items-center rounded-lg bg-success op-label font-bold text-inverted">B</span>
            <div class="min-w-0">
              <p class="op-label font-semibold text-highlighted">Decidido: B</p>
              <p class="op-body text-toned text-pretty">
                A corrida que está sendo montada mostra a ordem real da rota, o preço da TaOn, a maquininha de cada corrida e o
                troco, antes do toque em Chamar. A coluna Hoje fica ao lado só como referência.
              </p>
            </div>
          </div>

          <section v-for="(scenario, si) in SCENARIOS" :key="scenario.key" class="flex flex-col gap-3">
            <div>
              <h2 class="op-label font-semibold text-highlighted">{{ si + 1 }}. {{ scenario.title }}</h2>
              <p class="op-body text-muted text-pretty">{{ scenario.caption }}</p>
            </div>

            <div class="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <div
                v-for="col in columns"
                :key="col.id"
                class="flex flex-col overflow-hidden rounded-xl border bg-default"
                :class="col.id === 'B' ? 'border-success shadow-md ring-1 ring-success/40' : 'border-default opacity-55 grayscale-[35%]'"
              >
                <div class="flex items-center gap-2 border-b border-default px-4 py-2">
                  <span class="grid size-6 place-items-center rounded-md op-micro font-bold text-inverted" :class="col.id === 'B' ? 'bg-success' : 'bg-inverted'">{{ col.id }}</span>
                  <span class="op-micro font-semibold" :class="col.id === 'B' ? 'text-highlighted' : 'text-muted'">{{ col.title }}</span>
                  <span class="op-micro" :class="col.id === 'B' ? 'text-success' : 'text-muted'">· {{ col.tag }}</span>
                </div>

                <div class="grid min-h-0 flex-1 grid-cols-1" :class="col.id === 'B' ? 'sm:grid-cols-[250px_minmax(0,1fr)]' : 'sm:grid-cols-[200px_minmax(0,1fr)]'">
                  <!-- mapa simples -->
                  <div class="relative overflow-hidden border-b border-default bg-[#f4f1ea] sm:border-r sm:border-b-0" :class="col.id === 'B' ? 'min-h-[260px] sm:min-h-[420px]' : 'min-h-[220px] sm:min-h-[360px]'">
                    <svg class="absolute inset-0 size-full" preserveAspectRatio="none" aria-hidden="true">
                      <defs>
                        <pattern :id="`blocks-${scenario.key}-${col.id}`" width="24" height="24" patternUnits="userSpaceOnUse">
                          <path d="M24 0H0V24" fill="none" stroke="#000" stroke-opacity="0.07" stroke-width="1" />
                        </pattern>
                      </defs>
                      <rect width="100%" height="100%" :fill="`url(#blocks-${scenario.key}-${col.id})`" />
                    </svg>
                    <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="absolute inset-0 size-full" aria-hidden="true">
                      <path
                        v-for="ride in scenario.rides"
                        :key="ride.number"
                        :d="ridePath(ordered(ride, col.id))"
                        fill="none"
                        :stroke="rideColor(ride.number - 1).bg"
                        stroke-dasharray="4 3"
                        vector-effect="non-scaling-stroke"
                        style="stroke-width: 3px"
                      />
                    </svg>
                    <span
                      class="absolute grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-[#111] text-white shadow-md ring-4 ring-white"
                      :style="{ left: `${STORE.x}%`, top: `${STORE.y}%` }"
                      title="A loja"
                    >
                      <NuxtIcon name="i-lucide-store" class="size-4" />
                    </span>
                    <template v-for="item in STOPS" :key="item.ref">
                      <span
                        v-if="pinOf(scenario, item.ref, col.id)"
                        class="absolute grid size-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-[3px] border-dotted bg-white op-micro font-bold text-black shadow-sm"
                        :class="col.id === 'B' && item.ref === scenario.preparingRef ? 'ring-4 ring-warning/60' : ''"
                        :style="{ left: `${item.x}%`, top: `${item.y}%`, borderColor: rideColor(pinOf(scenario, item.ref, col.id)!.ride - 1).bg }"
                        :title="`${item.code} · ${item.place}`"
                      >{{ pinOf(scenario, item.ref, col.id)!.order }}</span>
                      <span
                        v-else-if="scenario.waiting.includes(item.ref)"
                        class="absolute grid h-6 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-sm border-2 bg-white px-1 op-micro font-semibold text-black/65"
                        :class="item.ready_eta ? 'border-dashed' : ''"
                        style="border-color: #b9a888"
                        :style="{ left: `${item.x}%`, top: `${item.y}%` }"
                        :title="`${item.code} · ${item.place}`"
                      >{{ item.code }}</span>
                    </template>
                    <span class="absolute bottom-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-white/85 px-1.5 op-micro text-black/65">
                      {{ col.id === "A" ? "Linha na ordem dos toques" : "Linha na ordem da rota" }}
                    </span>
                  </div>

                  <!-- coluna Editando + rodapé -->
                  <div class="flex min-w-0 flex-col">
                    <div class="flex-1 px-4 py-3">
                      <h3 class="flex items-center gap-2 op-label font-semibold text-highlighted">
                        <NuxtIcon name="i-lucide-route" class="size-4 text-muted" />
                        Editando
                        <OperatorCountChip :count="scenario.rides.length" />
                      </h3>

                      <!-- A: como é hoje -->
                      <div v-if="col.id === 'A'" class="mt-2 flex flex-col gap-2">
                        <section
                          v-for="ride in scenario.rides"
                          :key="ride.number"
                          class="rounded-xl border"
                          :style="ride.number === scenario.active ? { borderColor: rideColor(ride.number - 1).bg, boxShadow: `0 0 0 3px ${rideColor(ride.number - 1).bg}2e` } : {}"
                          :class="ride.number === scenario.active ? 'bg-default' : 'border-default bg-elevated/50'"
                        >
                          <div class="flex items-center gap-2 px-3 py-2.5">
                            <span class="grid h-6 min-w-6 shrink-0 place-items-center rounded-md px-1.5 op-micro font-bold" :style="{ background: rideColor(ride.number - 1).bg, color: rideColor(ride.number - 1).fg }">{{ rideLetter(ride.number) }}</span>
                            <span class="op-label font-semibold text-highlighted">Corrida {{ rideLetter(ride.number) }}</span>
                            <span class="op-micro tabular-nums text-muted">{{ ride.tapped.length }} de 4</span>
                            <span v-if="ride.number !== scenario.active" class="ml-1 min-w-0 flex-1 truncate op-micro text-muted">{{ ride.tapped.join(" → ") }}</span>
                            <span v-else class="flex-1" />
                            <NuxtButton icon="i-lucide-trash-2" color="neutral" variant="ghost" square :aria-label="`Desfazer a corrida ${rideLetter(ride.number)}`" />
                          </div>
                          <ol v-if="ride.number === scenario.active" class="flex flex-col gap-1 px-3 pb-3">
                            <li v-for="(ref, k) in ride.tapped" :key="ref" class="flex items-center gap-2.5 rounded-lg bg-elevated/60 px-2 py-1.5">
                              <span class="grid size-6 shrink-0 place-items-center rounded-full border-[3px] border-dotted bg-white op-micro font-bold text-highlighted" :style="{ borderColor: rideColor(ride.number - 1).bg }">{{ k + 1 }}</span>
                              <span class="min-w-0 flex-1">
                                <span class="block truncate op-body font-medium text-highlighted">{{ stop(ref).code }} · {{ stop(ref).customer }}</span>
                                <span class="block truncate op-micro text-muted">{{ [stop(ref).place, todayChangeLabel(ref)].filter(Boolean).join(" · ") }}</span>
                              </span>
                              <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square :aria-label="`Tirar ${stop(ref).code}`" />
                            </li>
                            <li v-if="ride.tapped.length > 1" class="px-1 pt-1 op-micro text-muted">A TaOn leva na ordem do percurso, a partir da loja.</li>
                          </ol>
                        </section>
                      </div>

                      <!-- B: proposta -->
                      <div v-else class="mt-2 flex flex-col gap-2">
                        <section
                          v-for="ride in scenario.rides"
                          :key="ride.number"
                          class="rounded-xl border bg-default"
                          :style="{ borderColor: rideColor(ride.number - 1).bg, boxShadow: ride.number === scenario.active ? `0 0 0 3px ${rideColor(ride.number - 1).bg}2e` : 'none' }"
                        >
                          <div class="flex items-center gap-2 px-3 py-2.5">
                            <span class="grid h-6 min-w-6 shrink-0 place-items-center rounded-md px-1.5 op-micro font-bold" :style="{ background: rideColor(ride.number - 1).bg, color: rideColor(ride.number - 1).fg }">{{ rideLetter(ride.number) }}</span>
                            <span class="op-label font-semibold text-highlighted">Corrida {{ rideLetter(ride.number) }}</span>
                            <span class="op-micro tabular-nums text-muted">{{ ride.route.length }} de 4</span>
                            <span class="flex-1" />
                            <NuxtButton icon="i-lucide-trash-2" color="neutral" variant="ghost" square :aria-label="`Desfazer a corrida ${rideLetter(ride.number)}`" />
                          </div>

                          <div class="flex flex-col gap-2 px-3 pb-3">
                            <p v-if="ride.route.length > 1" class="flex items-center gap-2 px-2 op-micro text-muted text-pretty">
                              <NuxtIcon name="i-lucide-store" class="size-3.5 shrink-0" />
                              <span>O entregador sai da loja e segue esta ordem.</span>
                            </p>
                            <ol class="flex flex-col gap-1.5">
                              <li
                                v-for="(ref, k) in ride.route"
                                :key="ref"
                                class="flex flex-col gap-2 rounded-lg px-2.5 py-2"
                                :class="ref === scenario.preparingRef ? 'bg-warning/10 ring-1 ring-warning/40' : 'bg-elevated/60'"
                              >
                                <div class="flex items-start gap-2.5">
                                  <span class="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border-[3px] border-dotted bg-white op-micro font-bold text-black" :style="{ borderColor: rideColor(ride.number - 1).bg }">{{ k + 1 }}</span>
                                  <div class="flex min-w-0 flex-1 flex-col gap-0.5">
                                    <p class="op-body font-medium text-highlighted">
                                      <span class="tabular-nums">{{ stop(ref).code }}</span> · {{ stop(ref).customer }}
                                    </p>
                                    <p class="op-micro text-muted">
                                      <template v-for="(fact, f) in stopFacts(ref)" :key="f">{{ f ? " " : "" }}<span class="whitespace-nowrap" :class="f === 2 ? 'tabular-nums' : ''">{{ fact }}{{ f < 2 ? " ·" : "" }}</span></template>
                                    </p>
                                    <NuxtBadge v-if="stop(ref).ready_eta" class="mt-1 self-start" :label="`Em preparo, fica pronto às ${stop(ref).ready_eta}`" color="warning" variant="subtle" icon="i-lucide-chef-hat" />
                                  </div>
                                  <NuxtButton class="-my-1 -mr-1" icon="i-lucide-x" color="neutral" variant="ghost" size="sm" square :aria-label="`Tirar ${stop(ref).code}`" />
                                </div>
                                <div v-if="stop(ref).pay === 'dinheiro'" class="flex flex-wrap items-center gap-x-2 gap-y-1 pl-[34px]">
                                  <label :for="`troco-${scenario.key}-${ref}`" class="whitespace-nowrap op-micro text-toned">Troco para</label>
                                  <NuxtInput :id="`troco-${scenario.key}-${ref}`" v-model="changeFor[`${scenario.key}:${ref}`]" size="sm" inputmode="decimal" class="w-28" :ui="{ base: 'tabular-nums' }">
                                    <template #leading><span class="op-micro text-muted">R$</span></template>
                                  </NuxtInput>
                                  <span class="op-micro text-muted text-pretty">{{ changeLine(scenario.key, ref) }}</span>
                                </div>
                              </li>
                            </ol>

                            <!-- cotação -->
                            <div class="flex items-start gap-2 rounded-lg px-2.5 py-2" :class="ride.quote.kind === 'failed' ? 'bg-elevated/60' : 'bg-elevated/30'">
                              <NuxtIcon :name="ride.quote.kind === 'failed' ? 'i-lucide-cloud-off' : 'i-lucide-receipt'" class="mt-0.5 size-3.5 shrink-0 text-muted" />
                              <PreviewQuote v-if="ride.quote.kind !== 'failed'" class="min-w-0 flex-1 gap-0.5" size="micro" :text="quoteLines(ride.quote)" />
                              <div v-else class="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1.5">
                                <p class="min-w-48 flex-1 op-micro text-toned text-pretty">A TaOn não cotou agora. O preço aparece na TaOn depois de chamar.</p>
                                <NuxtButton color="neutral" variant="outline" size="xs" icon="i-lucide-refresh-cw" label="Cotar de novo" />
                              </div>
                            </div>

                            <!-- maquininha por corrida -->
                            <div v-if="rideMachine(ride)" class="flex items-center gap-2 px-2.5 op-micro">
                              <NuxtIcon name="i-lucide-credit-card" class="size-3.5 shrink-0 text-muted" />
                              <span v-if="ride.machine" class="whitespace-nowrap font-semibold text-highlighted">{{ ride.machine }}</span>
                              <span v-else class="whitespace-nowrap font-semibold text-error">Nenhuma maquininha livre</span>
                              <span class="flex-1" />
                              <NuxtButton v-if="ride.machine" class="-my-1" color="neutral" variant="ghost" size="xs" label="Trocar" />
                            </div>
                          </div>
                        </section>
                      </div>
                    </div>

                    <!-- rodapé de chamar -->
                    <div class="flex flex-col gap-2 border-t border-default bg-default p-4">
                      <template v-if="col.id === 'A'">
                        <div class="flex items-center gap-2">
                          <p class="op-body text-toned">Maquininha que vai:</p>
                          <span class="inline-flex min-w-40 items-center justify-between gap-2 rounded-md px-2.5 py-1.5 op-body text-highlighted ring ring-accented">
                            {{ scenario.todayMachine }}
                            <NuxtIcon name="i-lucide-chevron-down" class="size-4 text-dimmed" />
                          </span>
                        </div>
                        <p class="op-micro text-muted"><NuxtIcon name="i-lucide-info" class="mr-1 inline size-3.5 align-[-2px]" />{{ scenario.todayNote }}</p>
                        <div class="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
                          <p class="min-w-48 flex-1 op-body text-muted">
                            {{ scenario.rides.reduce((n, r) => n + r.tapped.length, 0) }} pedidos em {{ scenario.rides.length }} {{ scenario.rides.length === 1 ? "corrida" : "corridas" }} · {{ scenario.waiting.length }} ficam
                          </p>
                          <NuxtButton icon="i-lucide-bike" :label="scenario.rides.length === 1 ? 'Chamar a corrida A' : `Chamar ${scenario.rides.length} corridas`" />
                        </div>
                      </template>
                      <template v-else>
                        <NuxtAlert
                          v-if="scenario.shortage"
                          color="error"
                          variant="subtle"
                          icon="i-lucide-credit-card"
                          :title="scenario.shortage"
                          description="Juntando, uma maquininha basta. Ou chame a corrida B quando outra maquininha ficar livre."
                          :actions="alertActions('error', [{ label: 'Juntar numa corrida só', icon: 'i-lucide-merge' }])"
                          orientation="vertical"
                        />
                        <div class="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
                          <p class="min-w-48 flex-1 op-body text-muted">
                            {{ scenario.rides.reduce((n, r) => n + r.route.length, 0) }} pedidos em {{ scenario.rides.length }} {{ scenario.rides.length === 1 ? "corrida" : "corridas" }} · {{ scenario.waiting.length }} ficam
                          </p>
                          <NuxtButton
                            :icon="scenario.preparingRef ? 'i-lucide-chef-hat' : 'i-lucide-bike'"
                            :label="scenario.callLabel"
                            :disabled="Boolean(scenario.shortage)"
                          />
                        </div>
                        <p v-if="scenario.shortage" class="op-micro text-muted">O botão Chamar só libera quando cada corrida com cartão tiver a sua maquininha.</p>
                        <p v-if="scenario.preparingRef" class="op-micro text-muted">O entregador pode chegar antes de {{ scenario.preparingRef }} ficar pronto e esperar no balcão.</p>
                      </template>
                    </div>
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
