<script setup lang="ts">
// Prévia 5 da revisão das Entregas: a corrida em apuros. Dados fictícios, sem
// backend. O mapa é um desenho simples (grade, loja preta, pinos), não o Google Maps.
import { rideColor } from "~/presentation/ridePalette";
import type { SaidaItem } from "~/components/PreviewSaidaCard.vue";

type AlertColor = "warning" | "info" | "neutral" | "primary" | "error";
type Footer = "recallOrBoost" | "reopen" | "atStore" | "silent" | "grouped" | "cancelFailed";

interface Stop {
  code: string;
  customer: string;
  place: string;
  bags: number;
  done?: boolean;
  next?: boolean;
  x: number;
  y: number;
}
interface Ride {
  number: number;
  status: string;
  icon: string;
  title: string;
  hint: string;
  titleTone?: "error" | "warning";
  alert: { color: AlertColor; icon: string; title: string; description?: string };
  driver: { name: string; phone: string; vehicle: string; plate: string } | null;
  stops: Stop[];
  courier: { x: number; y: number; stale?: string } | null;
  timeline: { at: string; text: string; strong?: boolean }[];
  cost: string;
}
interface Pane {
  tag: string;
  change?: string;
  show: "mirror" | "detail" | "both";
  ride: Ride;
  footer: Footer;
}
interface Block {
  key: string;
  title: string;
  caption: string;
  panes: Pane[];
}

const STORE = { x: 30, y: 62 };

const noneAccepted: Ride = {
  number: 2,
  status: "Procurando entregador",
  icon: "i-lucide-hourglass",
  title: "Ninguém aceitou em 12 min",
  hint: "Chamada às 14:08",
  titleTone: "warning",
  alert: {
    color: "warning",
    icon: "i-lucide-hourglass",
    title: "Ninguém aceitou em 12 min.",
    description: "A TaOn segue procurando. As sacolas ficam no balcão de saída.",
  },
  driver: null,
  stops: [
    { code: "A47", customer: "Marina Souza", place: "Gleba Palhano", bags: 2, x: 55, y: 62 },
    { code: "C03", customer: "Rafael Lima", place: "Gleba Palhano", bags: 1, x: 78, y: 40 },
  ],
  courier: null,
  timeline: [
    { at: "14:08", text: "Corrida chamada, R$ 9,00" },
    { at: "14:20", text: "Ninguém aceitou ainda", strong: true },
  ],
  cost: "R$ 9,00",
};

const reopened: Ride = {
  number: 1,
  status: "Procurando outro entregador",
  icon: "i-lucide-user-x",
  title: "Diego desistiu às 14:32",
  hint: "A TaOn já procura outro",
  alert: {
    color: "info",
    icon: "i-lucide-user-x",
    title: "Diego desistiu às 14:32. A TaOn já procura outro.",
    description: "A corrida continua chamada, com as mesmas paradas. Chamar de novo faria uma segunda corrida paga.",
  },
  driver: null,
  stops: [{ code: "D12", customer: "Helena Prado", place: "Bela Suíça", bags: 1, x: 76, y: 34 }],
  courier: null,
  timeline: [
    { at: "14:10", text: "Corrida chamada" },
    { at: "14:14", text: "Diego aceitou" },
    { at: "14:32", text: "Diego desistiu", strong: true },
    { at: "14:32", text: "A TaOn procura outro entregador" },
  ],
  cost: "R$ 8,50",
};

const atStore: Ride = {
  number: 4,
  status: "Entregador na loja",
  icon: "i-lucide-store",
  title: "Diego espera na loja há 7 min",
  hint: "Entregue as 2 sacolas de A47",
  titleTone: "warning",
  alert: {
    color: "primary",
    icon: "i-lucide-package-check",
    title: "Diego espera na loja há 7 min. Entregue as 2 sacolas de A47.",
  },
  driver: { name: "Diego", phone: "(43) 99876-1203", vehicle: "Moto prata", plate: "ABC1D23" },
  stops: [{ code: "A47", customer: "Marina Souza", place: "Gleba Palhano", bags: 2, x: 60, y: 74 }],
  courier: { x: 30, y: 62 },
  timeline: [
    { at: "14:21", text: "Corrida chamada" },
    { at: "14:23", text: "Diego aceitou" },
    { at: "14:31", text: "Chegou na loja", strong: true },
  ],
  cost: "R$ 8,50",
};

const silent: Ride = {
  number: 5,
  status: "Em rota",
  icon: "i-lucide-wifi-off",
  title: "A TaOn não dá notícias desde 14:05",
  hint: "Léo em rota",
  titleTone: "warning",
  alert: {
    color: "warning",
    icon: "i-lucide-wifi-off",
    title: "A TaOn não dá notícias desta corrida desde 14:05.",
    description: "A última posição de Léo é das 14:05. Ligue para ele e confirme onde está.",
  },
  driver: { name: "Léo", phone: "(43) 99124-5580", vehicle: "Moto preta", plate: "BRA2E19" },
  stops: [
    { code: "B21", customer: "Paulo Mendes", place: "Centro", bags: 1, done: true, x: 44, y: 30 },
    { code: "D12", customer: "Helena Prado", place: "Jardim Higienópolis", bags: 2, next: true, x: 76, y: 24 },
  ],
  courier: { x: 52, y: 27, stale: "14:05" },
  timeline: [
    { at: "13:41", text: "Corrida chamada" },
    { at: "13:50", text: "Saiu com as sacolas" },
    { at: "14:02", text: "B21 entregue" },
    { at: "14:05", text: "Última notícia da TaOn", strong: true },
  ],
  cost: "R$ 13,00",
};

const grouped: Ride = {
  number: 6,
  status: "A TaOn juntou com outra corrida",
  icon: "i-lucide-link",
  title: "A TaOn juntou com outra corrida",
  hint: "Ela já tem entregador",
  alert: {
    color: "neutral",
    icon: "i-lucide-link",
    title: "A TaOn juntou com outra corrida.",
    description: "E09 foi para uma corrida que já tem entregador. Não precisa chamar de novo.",
  },
  driver: null,
  stops: [{ code: "E09", customer: "Carla Nogueira", place: "Bela Suíça", bags: 1, x: 80, y: 40 }],
  courier: null,
  timeline: [
    { at: "14:12", text: "Corrida chamada" },
    { at: "14:15", text: "A TaOn juntou com outra corrida", strong: true },
  ],
  cost: "R$ 7,50",
};

const cancelFailed: Ride = {
  number: 3,
  status: "Procurando entregador",
  icon: "i-lucide-circle-alert",
  title: "A TaOn não cancelou a corrida C",
  hint: "Cancele pela central da TaOn",
  titleTone: "error",
  alert: {
    color: "error",
    icon: "i-lucide-circle-alert",
    title: "A TaOn não cancelou a corrida C. Cancele pela central da TaOn.",
    description: "A corrida segue procurando entregador. Até cancelar lá, alguém pode aceitar e vir à loja.",
  },
  driver: null,
  stops: [{ code: "F02", customer: "Jorge Tanaka", place: "Centro", bags: 1, x: 40, y: 26 }],
  courier: null,
  timeline: [
    { at: "14:02", text: "Corrida chamada" },
    { at: "14:25", text: "Cancelamento pedido à TaOn" },
    { at: "14:25", text: "A TaOn recusou o cancelamento", strong: true },
  ],
  cost: "R$ 7,00",
};

const blocks: Block[] = [
  {
    key: "nenhum",
    title: "1 · Ninguém aceitou",
    caption: "Decidido: as duas saídas juntas. \"Chamar de novo\" vem primeiro porque não custa nada a mais; \"Aumentar a oferta\" vem logo depois, para quando o preço é o que trava.",
    panes: [
      { tag: "Na coluna Corridas", show: "mirror", ride: noneAccepted, footer: "recallOrBoost" },
      { tag: "Detalhe da corrida", show: "detail", ride: noneAccepted, footer: "recallOrBoost" },
    ],
  },
  {
    key: "desistiu",
    title: "2 · O entregador desistiu",
    caption: "A TaOn reabre a corrida sozinha. Não há botão de chamar de novo.",
    panes: [
      { tag: "Na coluna Corridas", show: "mirror", ride: reopened, footer: "reopen" },
      { tag: "Detalhe da corrida", show: "detail", ride: reopened, footer: "reopen" },
    ],
  },
  {
    key: "espera",
    title: "3 · Entregador esperando no balcão",
    caption: "O relógio conta desde a chegada. A placa ajuda a conferir quem leva.",
    panes: [
      { tag: "Na coluna Corridas", show: "mirror", ride: atStore, footer: "atStore" },
      { tag: "Detalhe da corrida", show: "detail", ride: atStore, footer: "atStore" },
    ],
  },
  {
    key: "silencio",
    title: "4 · A TaOn parou de dar notícias",
    caption: "Dado parado vira aviso com hora, e o gesto é ligar para o entregador.",
    panes: [
      { tag: "Na coluna Corridas", show: "mirror", ride: silent, footer: "silent" },
      { tag: "Detalhe da corrida", show: "detail", ride: silent, footer: "silent" },
    ],
  },
  {
    key: "junto",
    title: "5 · A TaOn juntou com outra corrida",
    caption: "A própria TaOn juntou a corrida a outra. Nunca vira \"Ninguém aceitou\".",
    panes: [
      { tag: "Na coluna Corridas", show: "mirror", ride: grouped, footer: "grouped" },
      { tag: "Detalhe da corrida", show: "detail", ride: grouped, footer: "grouped" },
    ],
  },
  {
    key: "cancelamento",
    title: "6 · O cancelamento falhou",
    caption: "A recusa da TaOn aparece, em vez de sumir calada.",
    panes: [
      { tag: "Na coluna Corridas", show: "mirror", ride: cancelFailed, footer: "cancelFailed" },
      { tag: "Detalhe da corrida", show: "detail", ride: cancelFailed, footer: "cancelFailed" },
    ],
  },
];

const BOOSTS = [3, 5, 8];
const boost = ref(5);
const money = (value: number) => `R$ ${value.toFixed(2).replace(".", ",")}`;
const boostTotal = computed(() => money(9 + boost.value));
const tone = (ride: Ride) => rideColor(ride.number - 1);
const rideLetter = (n: number) => String.fromCharCode(64 + n);
const bagsLabel = (n: number) => `${n} ${n === 1 ? "sacola" : "sacolas"}`;
// O espelho na coluna Corridas é o cartão da Saída, forma E (dono, 16/11).
const ACTIONS: Partial<Record<Footer, (ride: Ride) => SaidaItem["action"]>> = {
  recallOrBoost: () => ({ label: "Chamar de novo", icon: "i-lucide-bike" }),
  silent: (ride) => ({ label: `Ligar para ${ride.driver?.name}`, icon: "i-lucide-phone" }),
};
const saidaItem = (pane: Pane): SaidaItem => ({
  key: `${pane.tag}-${pane.ride.number}`,
  ride: pane.ride.number,
  icon: pane.ride.icon,
  moment: pane.ride.title,
  momentTone: pane.ride.titleTone ?? "neutral",
  hint: pane.ride.hint,
  stops: pane.ride.stops.map((s) => ({ code: s.code, place: s.place, bags: s.bags, done: s.done })),
  action: ACTIONS[pane.footer]?.(pane.ride),
  secondaryAction: pane.footer === "recallOrBoost" ? { label: "Aumentar a oferta", icon: "i-lucide-trending-up" } : undefined,
  pulse: pane.ride.status.startsWith("Procurando") && pane.ride.titleTone !== "error",
});
const route = (ride: Ride) =>
  [STORE, ...ride.stops].map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" ");
</script>

<template>
  <!-- Prévia de olhar: cobre a casca do Gestor (barra lateral e rolagem interna)
       para a página ter os 1440 px inteiros e rolar com o documento. -->
  <div>
    <Teleport to="body">
      <div class="absolute inset-x-0 top-0 z-40 min-h-dvh bg-default" data-preview-overlay>
        <main class="min-h-dvh overflow-x-auto bg-elevated/40 py-6 pb-32 sm:py-8 sm:pb-32" data-preview="5-apuros">
          <div class="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-4 sm:gap-8 sm:px-8">
            <header class="flex flex-col gap-1">
              <PreviewNav :current="5" />
              <h1 class="op-title font-bold text-highlighted">Prévia 5 · Corrida em apuros</h1>
              <p class="op-body text-toned">
                O dono decide se o tom de cada aviso está certo. O caso de ninguém aceitar já está decidido.
              </p>
            </header>

            <section v-for="block in blocks" :key="block.key" class="flex flex-col gap-3 rounded-2xl border border-default bg-default p-4 sm:p-6">
              <div>
                <h2 class="op-title font-semibold text-highlighted">{{ block.title }}</h2>
                <p class="op-body text-muted text-pretty">{{ block.caption }}</p>
              </div>

              <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
                <div v-for="pane in block.panes" :key="pane.tag" class="flex min-w-0 flex-col gap-3">
                  <div class="flex items-baseline gap-2">
                    <span
                      class="grid h-7 min-w-7 shrink-0 place-items-center rounded-md px-2 op-label font-bold"
                      :class="pane.change ? 'bg-inverted text-inverted' : 'bg-elevated text-toned'"
                    >{{ pane.tag }}</span>
                    <p v-if="pane.change" class="op-body text-toned">{{ pane.change }}</p>
                  </div>

                  <!-- espelho: o cartão da corrida na coluna Corridas (forma E) -->
                  <PreviewSaidaCard v-if="pane.show !== 'detail'" :item="saidaItem(pane)" />
                  <p v-if="pane.show === 'mirror'" class="op-micro text-muted">Tocar na linha abre o detalhe, ao lado.</p>

                  <!-- detalhe: o painel lateral da corrida -->
                  <aside
                    v-if="pane.show !== 'mirror'"
                    class="flex w-full max-w-lg flex-col overflow-hidden rounded-xl border border-default bg-default shadow-sm"
                  >
                    <header class="flex items-start gap-3 border-b border-default px-5 py-4" :style="{ borderTop: `6px solid ${tone(pane.ride).bg}` }">
                      <span class="grid size-9 shrink-0 place-items-center rounded-lg text-lg font-bold" :style="{ background: tone(pane.ride).bg, color: tone(pane.ride).fg }">{{ rideLetter(pane.ride.number) }}</span>
                      <div class="min-w-0 flex-1">
                        <p class="op-title font-semibold text-highlighted">Corrida {{ rideLetter(pane.ride.number) }} · {{ pane.ride.status }}</p>
                        <p class="op-body text-muted">{{ pane.ride.stops.map((stop) => stop.code).join(", ") }} · {{ pane.ride.cost }}</p>
                      </div>
                      <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" aria-label="Fechar" />
                    </header>

                    <div class="flex flex-col">
                      <NuxtAlert
                        class="mx-5 mt-4 w-auto"
                        :color="pane.ride.alert.color"
                        variant="subtle"
                        :icon="pane.ride.alert.icon"
                        :title="pane.ride.alert.title"
                        :description="pane.ride.alert.description"
                      />

                      <!-- mapa desenhado: grade, loja preta, pinos na cor da corrida -->
                      <div class="relative mx-5 mt-4 h-44 overflow-hidden rounded-xl bg-[#f4f1ea] ring-1 ring-default">
                        <svg class="absolute inset-0 size-full" aria-hidden="true">
                          <defs>
                            <pattern :id="`grid-${block.key}-${pane.tag.replace(/[^A-Za-z0-9]+/g, '-')}`" width="24" height="24" patternUnits="userSpaceOnUse">
                              <path d="M24 0H0V24" fill="none" stroke="#000" stroke-opacity="0.07" stroke-width="1" />
                            </pattern>
                          </defs>
                          <rect width="100%" height="100%" :fill="`url(#grid-${block.key}-${pane.tag.replace(/[^A-Za-z0-9]+/g, '-')})`" />
                        </svg>
                        <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="absolute inset-0 size-full" aria-hidden="true">
                          <path
                            :d="route(pane.ride)"
                            fill="none"
                            :stroke="tone(pane.ride).bg"
                            stroke-opacity="0.5"
                            vector-effect="non-scaling-stroke"
                            style="stroke-width: 3px"
                            :stroke-dasharray="pane.ride.driver ? undefined : '6 5'"
                          />
                        </svg>
                        <span
                          class="absolute grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-[#111] text-white shadow-md ring-4 ring-white"
                          :style="{ left: `${STORE.x}%`, top: `${STORE.y}%` }"
                          title="A loja"
                        ><NuxtIcon name="i-lucide-store" class="size-4" /></span>
                        <template v-for="(stop, i) in pane.ride.stops" :key="stop.code">
                          <span
                            class="absolute grid size-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-[3px] bg-white op-micro font-bold text-black shadow-sm"
                            :style="{ left: `${stop.x}%`, top: `${stop.y}%`, borderColor: tone(pane.ride).bg, opacity: stop.done ? 0.5 : 1 }"
                          ><NuxtIcon v-if="stop.done" name="i-lucide-check" class="size-3.5" /><template v-else>{{ i + 1 }}</template></span>
                          <span
                            class="pointer-events-none absolute -translate-x-1/2 translate-y-4 whitespace-nowrap rounded bg-white/85 px-1 op-micro font-medium text-black/65"
                            :style="{ left: `${stop.x}%`, top: `${stop.y}%` }"
                          >{{ stop.code }} · {{ stop.place }}</span>
                        </template>
                        <span
                          v-if="pane.ride.courier"
                          class="absolute grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full shadow-md ring-2 ring-white"
                          :style="{ left: `${pane.ride.courier.x + (pane.ride.courier.x === STORE.x ? 6 : 0)}%`, top: `${pane.ride.courier.y - (pane.ride.courier.y === STORE.y ? 10 : 0)}%`, background: tone(pane.ride).bg, color: tone(pane.ride).fg, opacity: pane.ride.courier.stale ? 0.45 : 1 }"
                        ><NuxtIcon name="i-lucide-bike" class="size-4" /></span>
                        <p class="absolute right-2 bottom-2 rounded-md bg-white/90 px-2 py-1 op-micro text-black/65 shadow-sm">
                          {{ pane.ride.courier?.stale ? `Última posição às ${pane.ride.courier.stale}` : pane.ride.courier ? "Posição agora" : "Sem entregador no mapa" }}
                        </p>
                      </div>

                      <div v-if="pane.ride.driver" class="mx-5 mt-4 flex flex-wrap items-center gap-3 rounded-xl bg-elevated/60 p-3">
                        <NuxtAvatar :text="pane.ride.driver.name.slice(0, 1)" size="lg" />
                        <div class="min-w-36 flex-1">
                          <p class="op-label font-semibold text-highlighted">{{ pane.ride.driver.name }}</p>
                          <p class="flex flex-wrap items-center gap-x-1.5 gap-y-1 op-body text-toned">
                            <span class="whitespace-nowrap">{{ pane.ride.driver.vehicle }} ·</span>
                            <span class="rounded border border-[#111]/40 bg-white px-1.5 font-mono text-sm font-semibold tracking-wider text-black">{{ pane.ride.driver.plate }}</span>
                          </p>
                        </div>
                        <div class="ml-auto flex shrink-0 gap-2">
                          <NuxtButton icon="i-lucide-phone" color="neutral" variant="outline" label="Ligar" />
                          <NuxtButton icon="i-lucide-message-circle" color="neutral" variant="outline" square :aria-label="`WhatsApp de ${pane.ride.driver.name}`" />
                        </div>
                      </div>

                      <section class="mx-5 mt-5">
                        <p class="op-micro font-semibold text-muted">Paradas, na ordem do percurso</p>
                        <ol class="mt-2 flex flex-col">
                          <li v-for="(stop, i) in pane.ride.stops" :key="stop.code" class="relative flex gap-3 pb-3 last:pb-0">
                            <span v-if="i < pane.ride.stops.length - 1" class="absolute top-7 bottom-0 left-3.5 w-px bg-default" aria-hidden="true" />
                            <span class="relative z-10 grid size-7 shrink-0 place-items-center rounded-full border-[3px] bg-white op-micro font-bold text-black" :style="{ borderColor: tone(pane.ride).bg }">
                              <NuxtIcon v-if="stop.done" name="i-lucide-check" class="size-3.5" /><template v-else>{{ i + 1 }}</template>
                            </span>
                            <div class="min-w-0 flex-1">
                              <p class="flex items-baseline gap-2">
                                <span class="op-body font-medium" :class="stop.done ? 'text-muted' : 'text-highlighted'">{{ stop.code }} · {{ stop.customer }}</span>
                                <span class="ml-auto shrink-0 op-micro" :class="stop.done ? 'text-success' : stop.next ? 'font-semibold text-highlighted' : 'text-muted'">
                                  {{ stop.done ? "Entregue" : stop.next ? "Indo para cá" : bagsLabel(stop.bags) }}
                                </span>
                              </p>
                              <p class="op-micro text-muted">{{ stop.place }}, Londrina</p>
                            </div>
                          </li>
                        </ol>
                      </section>

                      <section class="mx-5 mt-5 mb-5">
                        <p class="op-micro font-semibold text-muted">O que aconteceu</p>
                        <ul class="mt-2 flex flex-col gap-1.5 op-body">
                          <li v-for="(event, i) in pane.ride.timeline" :key="i" class="flex gap-3">
                            <span class="w-11 shrink-0 tabular-nums text-muted">{{ event.at }}</span>
                            <span :class="event.strong ? 'font-semibold text-highlighted' : 'text-toned'">{{ event.text }}</span>
                          </li>
                        </ul>
                      </section>
                    </div>

                    <footer class="flex flex-col gap-3 border-t border-default px-5 py-4">
                      <!-- ninguém aceitou: chamar de novo (primeiro, sem custo) ou aumentar a oferta -->
                      <template v-if="pane.footer === 'recallOrBoost'">
                        <div class="flex flex-col gap-1">
                          <NuxtButton class="justify-center" color="primary" icon="i-lucide-bike" label="Chamar de novo" />
                          <p class="op-micro text-muted">Pelo mesmo preço, R$ 9,00.</p>
                        </div>

                        <div class="flex flex-col gap-3 rounded-xl bg-elevated/70 p-3">
                          <p class="op-body font-medium text-highlighted text-pretty">Ou aumente a oferta, para a TaOn achar um entregador mais rápido:</p>
                          <div class="flex gap-2">
                            <NuxtButton
                              v-for="value in BOOSTS"
                              :key="value"
                              :color="boost === value ? 'primary' : 'neutral'"
                              variant="outline"
                              :label="`+R$ ${value}`"
                              :icon="boost === value ? 'i-lucide-check' : undefined"
                              :aria-pressed="boost === value"
                              class="flex-1 justify-center"
                              :class="boost === value ? 'font-semibold ring-2' : ''"
                              @click="boost = value"
                            />
                          </div>
                          <div>
                            <p class="op-body font-semibold text-highlighted">A corrida passa de R$ 9,00 para {{ boostTotal }}.</p>
                            <p class="op-micro text-muted">A casa paga a diferença. Dá para aumentar uma vez por corrida.</p>
                          </div>
                          <NuxtButton class="justify-center" color="neutral" variant="outline" icon="i-lucide-trending-up" :label="`Aumentar para ${boostTotal}`" />
                        </div>

                        <div class="flex justify-end">
                          <NuxtButton color="error" variant="ghost" icon="i-lucide-circle-x" label="Cancelar corrida" />
                        </div>
                      </template>

                      <template v-else-if="pane.footer === 'reopen'">
                        <div class="flex items-center gap-2">
                          <p class="min-w-0 flex-1 op-micro text-muted">Nada a fazer agora. Quando outro entregador aceitar, o nome dele aparece aqui.</p>
                          <NuxtButton color="error" variant="ghost" icon="i-lucide-circle-x" label="Cancelar corrida" />
                        </div>
                      </template>

                      <template v-else-if="pane.footer === 'atStore'">
                        <div class="flex items-center gap-2">
                          <p class="min-w-0 flex-1 op-micro text-muted">Antes de ele sair com as sacolas, dá para cancelar.</p>
                          <NuxtButton color="error" variant="ghost" icon="i-lucide-circle-x" label="Cancelar corrida" />
                        </div>
                      </template>

                      <template v-else-if="pane.footer === 'silent'">
                        <NuxtButton class="justify-center" color="primary" icon="i-lucide-phone" :label="`Ligar para ${pane.ride.driver?.name}`" />
                        <p class="op-micro text-muted">Ele já saiu com as sacolas: cancelar agora só pela central da TaOn.</p>
                      </template>

                      <template v-else-if="pane.footer === 'grouped'">
                        <p class="op-micro text-muted">A TaOn cuida desta entrega junto com a outra corrida. Quando ela disser quem leva, o nome aparece aqui.</p>
                      </template>

                      <template v-else-if="pane.footer === 'cancelFailed'">
                        <NuxtButton class="justify-center" color="neutral" variant="outline" icon="i-lucide-external-link" label="Abrir a central da TaOn" />
                        <p class="op-micro text-muted">Depois de cancelar lá, a corrida some daqui sozinha.</p>
                      </template>
                    </footer>
                  </aside>
                </div>
              </div>
            </section>
          </div>
        </main>
      </div>
    </Teleport>
  </div>
</template>
