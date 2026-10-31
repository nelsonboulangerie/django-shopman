<script setup lang="ts">
// PRÉVIA hiperfoco (31/10/2026): o Gestor aberto pelo POSTO, não pelo app.
// Três pessoas olham o Gestor no pico (dono, 31/10): o caixa no computador, de relance,
// entre uma venda e outra; o passe no tablet, em pé, entregando sacolas; o gerente no
// celular, andando. Cada uma abre no que o momento dela pede, com os mesmos dados e
// as mesmas ações do quadro (useOrdersBoard). `?modo=caixa|passe|gerente`.
import type { OrderCardProjection } from "~/types/orders";
import { channelLabel, splitRef, confirmationRemainingLabel } from "~/presentation/board";
import { queueItems, workingOrders, waitsForCustomer, type QueueItem } from "~/presentation/queue";

const route = useRoute();
const modo = computed(() => String(route.query.modo || "caixa"));
const MODOS = [
  { value: "caixa", label: "Caixa · computador" },
  { value: "passe", label: "Passe · tablet" },
  { value: "gerente", label: "Gerente · celular" },
];

const { queue, zones, isBusy, confirm, advance, courierBack } = useOrdersBoard();
const nowMs = useNowTick(() => queue.value?.intake[0]?.server_now_iso ?? "");
const cards = computed<OrderCardProjection[]>(() => {
  const seen = new Set<string>();
  return zones.value
    .flatMap((z) => z.cards)
    .filter((c) => (seen.has(c.ref) ? false : (seen.add(c.ref), true)));
});
const items = computed(() => queueItems(cards.value, nowMs.value, { scope: "attention" }));
const working = computed(() => workingOrders(cards.value, nowMs.value));
const waitingPay = computed(() => cards.value.filter(waitsForCustomer).length);
const code = (ref: string) => splitRef(ref).code;

// O relógio do momento: perder vence tudo; depois, o tempo contra a meta.
function clock(item: QueueItem) {
  if (item.cancelsIn !== null) {
    const m = Math.floor(item.cancelsIn / 60);
    const s = String(item.cancelsIn % 60).padStart(2, "0");
    return {
      value: `${m}:${s}`,
      caption: item.kind === "negotiation" ? "para o iFood decidir" : "para cancelar sozinho",
      tone: "loss" as const,
    };
  }
  const left = item.card.confirmation_deadline_iso
    ? confirmationRemainingLabel(item.card.confirmation_deadline_iso, nowMs.value)
    : "";
  if (item.kind === "confirm" && left)
    return { value: left, caption: "para aceitar sozinho", tone: "calm" as const };
  return {
    value: item.timeLabel,
    caption: item.goalLabel.replace(/^meta (\d+)$/, "meta $1 min"),
    tone: item.tone === "late" ? ("late" as const) : ("calm" as const),
  };
}
const toneText = { loss: "text-destructive", late: "text-warning", calm: "text-muted-foreground" };

/** O que o operador faz, numa palavra, e se a tela resolve ali mesmo. */
function gesture(item: QueueItem): { label: string; key?: string; run?: () => void; to?: string } | null {
  const ref = item.card.ref;
  switch (item.kind) {
    case "confirm":
      return { label: "Aceitar", key: "A", run: () => void confirm(ref) };
    case "negotiation":
      return { label: "Responder", to: `/${ref}#ifood-negotiations` };
    case "handoff":
      return { label: "Entregar", run: () => void advance(ref) };
    case "dispatch":
      return { label: "Saiu", to: "/?columns=expedition" };
    case "courier_back":
      return { label: "Entregador voltou", run: () => void courierBack(ref) };
    case "start":
      return { label: "Iniciar preparo", run: () => void advance(ref) };
    default:
      return { label: "Abrir", to: `/${ref}` };
  }
}
/** A pergunta da retirada (dono, 31/10): sem pagamento registrado, a tela pergunta. */
function payUnknown(card: OrderCardProjection) {
  return (
    card.fulfillment_type === "pickup" &&
    !card.payment_pending &&
    ["", "unknown"].includes(card.payment_status || "")
  );
}
function bags(card: OrderCardProjection) {
  return card.volumes ? `${card.volumes} ${card.volumes === 1 ? "sacola" : "sacolas"}` : `${card.items_count} ${card.items_count === 1 ? "item" : "itens"}`;
}

// ── Caixa: só o que pede você, de relance; tecla A aceita o primeiro novo.
const caixaShown = computed(() => items.value.slice(0, 5));
const firstLoss = computed(() => items.value.find((i) => i.cancelsIn !== null) ?? null);
function onKey(event: KeyboardEvent) {
  if (modo.value !== "caixa" || event.key.toLowerCase() !== "a") return;
  if ((event.target as HTMLElement)?.closest("input,textarea")) return;
  const novo = items.value.find((i) => i.kind === "confirm");
  if (novo) void confirm(novo.card.ref);
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

// ── Passe: o próximo a sair em destaque; depois, os seguintes e os entregadores.
const saida = computed(() =>
  items.value.filter((i) => i.kind === "handoff" || i.kind === "dispatch"),
);
const proximo = computed(() => saida.value[0] ?? null);
const depois = computed(() => saida.value.slice(1));
const entregadores = computed(() => {
  const back = items.value.filter((i) => i.kind === "courier_back").map((i) => ({ card: i.card, back: true }));
  const refs = new Set(back.map((e) => e.card.ref));
  return [...back, ...working.value.road.filter((o) => !refs.has(o.card.ref)).map((o) => ({ card: o.card, back: false }))];
});
const perdas = computed(() => items.value.filter((i) => i.cancelsIn !== null));

// ── Gerente: o estado da casa numa frase; o que pode ser perdido; o atrasado.
const atrasados = computed(() => items.value.filter((i) => i.tone === "late" && i.cancelsIn === null));
const canais = computed(() => queue.value?.awareness?.menu_channels ?? []);
const estado = computed(() => {
  const parts = [];
  if (perdas.value.length) parts.push(`${perdas.value.length} pode${perdas.value.length === 1 ? "" : "m"} ser perdido${perdas.value.length === 1 ? "" : "s"}`);
  if (atrasados.value.length) parts.push(`${atrasados.value.length} atrasado${atrasados.value.length === 1 ? "" : "s"}`);
  parts.push(`${working.value.kitchen.length} na cozinha`, `${working.value.road.length} na rua`);
  return parts.join(" · ");
});
useHead({ title: "Posto" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col overflow-auto bg-background" data-hf-posto>
    <!-- só para a prévia: escolher o posto -->
    <div class="flex flex-wrap items-center gap-2 border-b border-dashed border-border px-4 py-2 op-micro text-muted-foreground">
      Prévia, posto:
      <NuxtButton
        v-for="m in MODOS"
        :key="m.value"
        size="xs"
        :variant="modo === m.value ? 'solid' : 'outline'"
        color="neutral"
        :to="{ query: { modo: m.value } }"
        :label="m.label"
      />
    </div>

    <!-- ═══ CAIXA: de relance, entre uma venda e outra ═══ -->
    <section v-if="modo === 'caixa'" class="mx-auto flex w-full max-w-4xl flex-col gap-4 p-4 sm:p-8">
      <header>
        <p class="op-figure leading-tight" :class="firstLoss ? 'text-destructive' : ''">
          <template v-if="!items.length">Nada pede você agora.</template>
          <template v-else-if="firstLoss">
            {{ code(firstLoss.card.ref) }} {{ firstLoss.kind === 'negotiation' ? 'o iFood decide' : 'cancela' }} em {{ clock(firstLoss).value }}
          </template>
          <template v-else>{{ items.length }} {{ items.length === 1 ? "pede" : "pedem" }} você</template>
        </p>
        <p v-if="items.length" class="op-body text-muted-foreground">
          {{ items.length }} {{ items.length === 1 ? "pedido pede" : "pedidos pedem" }} você · o que pode ser perdido vem primeiro
        </p>
      </header>

      <ol class="flex flex-col divide-y divide-border rounded-lg border border-border bg-card">
        <li
          v-for="item in caixaShown"
          :key="item.card.ref"
          class="grid grid-cols-[88px_minmax(0,1fr)_auto] items-center gap-4 px-4 py-3"
          :data-hf-caixa="item.kind"
        >
          <div>
            <p class="op-title tnum leading-none font-bold" :class="toneText[clock(item).tone]">{{ clock(item).value }}</p>
            <p class="op-micro leading-tight" :class="toneText[clock(item).tone]">{{ clock(item).caption }}</p>
          </div>
          <div class="min-w-0">
            <p class="op-body truncate">
              <span class="font-semibold">{{ code(item.card.ref) }} · {{ item.card.customer_name || "Sem cliente" }}</span>
              <span class="text-muted-foreground"> · {{ item.card.fulfillment_label }} · {{ channelLabel(item.card.channel_ref) }}</span>
            </p>
            <p class="op-micro truncate text-muted-foreground">{{ item.card.items_summary }} · {{ item.card.total_display }}</p>
          </div>
          <NuxtButton
            v-if="gesture(item)"
            size="lg"
            color="primary"
            :to="gesture(item)!.to"
            :disabled="isBusy(item.card.ref)"
            @click="gesture(item)!.run?.()"
          >
            {{ gesture(item)!.label }}
            <template v-if="gesture(item)!.key" #trailing><NuxtKbd :value="gesture(item)!.key" /></template>
          </NuxtButton>
        </li>
      </ol>
      <p class="op-body text-muted-foreground">
        <template v-if="items.length > caixaShown.length">Mais {{ items.length - caixaShown.length }} pedem você · </template>
        Seguem sozinhos: {{ working.kitchen.length }} na cozinha, {{ working.road.length }} na rua<template v-if="waitingPay">, {{ waitingPay }} esperando o cliente pagar</template>
        · <NuxtLink to="/?columns=all" class="underline">Quadro completo</NuxtLink>
      </p>
    </section>

    <!-- ═══ PASSE: em pé, a sacola na mão ═══ -->
    <section v-else-if="modo === 'passe'" class="flex flex-col gap-4 p-4">
      <!-- só o que pode ser perdido interrompe o passe -->
      <div
        v-for="item in perdas"
        :key="`perda-${item.card.ref}`"
        class="flex items-center gap-3 rounded-lg bg-destructive px-4 py-2 text-inverted"
        data-hf-passe-perda
      >
        <span class="op-title tnum font-bold">{{ clock(item).value }}</span>
        <span class="min-w-0 flex-1 op-body">{{ code(item.card.ref) }} · {{ item.card.customer_name }} · {{ clock(item).caption }}</span>
        <NuxtButton color="neutral" variant="solid" :to="gesture(item)!.to" @click="gesture(item)!.run?.()">{{ gesture(item)!.label }}</NuxtButton>
      </div>

      <div class="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <!-- o próximo a sair -->
        <NuxtCard v-if="proximo" data-hf-proximo>
          <p class="op-eyebrow text-muted-foreground">Próximo a sair · {{ proximo.card.fulfillment_label }}</p>
          <div class="mt-2 flex items-baseline gap-4">
            <p class="text-6xl font-bold leading-none tnum">{{ code(proximo.card.ref) }}</p>
            <p class="op-title">{{ proximo.card.customer_name || "Sem cliente" }}</p>
          </div>
          <p class="mt-3 op-title">{{ bags(proximo.card) }}</p>
          <p class="op-body text-muted-foreground">{{ proximo.card.items_summary }}</p>
          <p v-if="proximo.card.delivery_address" class="mt-1 op-body">{{ proximo.card.delivery_address }}</p>
          <p v-if="proximo.card.change_label" class="mt-3 rounded-md bg-muted px-3 py-2 op-title">{{ proximo.card.change_label }}</p>
          <p v-if="proximo.card.courier_status_label" class="mt-2 op-body">{{ proximo.card.courier_status_label }}</p>

          <!-- a pergunta da retirada sem pagamento registrado -->
          <div v-if="proximo.kind === 'handoff' && payUnknown(proximo.card)" class="mt-5" data-hf-pergunta>
            <p class="op-title">Já pagou? <span class="text-muted-foreground">{{ proximo.card.total_display }}</span></p>
            <div class="mt-2 grid grid-cols-2 gap-3">
              <NuxtButton size="xl" color="neutral" variant="outline" block icon="i-lucide-hand-coins" :to="`/${proximo.card.ref}`">Receber {{ proximo.card.total_display }}</NuxtButton>
              <NuxtButton size="xl" color="primary" block icon="i-lucide-check" :disabled="isBusy(proximo.card.ref)" @click="advance(proximo.card.ref)">Já pagou, entregar</NuxtButton>
            </div>
          </div>
          <NuxtButton
            v-else-if="gesture(proximo)"
            class="mt-5"
            size="xl"
            color="primary"
            block
            :to="gesture(proximo)!.to"
            :disabled="isBusy(proximo.card.ref)"
            @click="gesture(proximo)!.run?.()"
          >
            {{ gesture(proximo)!.label }} {{ code(proximo.card.ref) }}
          </NuxtButton>
        </NuxtCard>
        <NuxtCard v-else><p class="op-title text-muted-foreground">Nada pronto para sair.</p></NuxtCard>

        <div class="flex flex-col gap-4">
          <NuxtCard>
            <p class="op-eyebrow text-muted-foreground">Depois</p>
            <p v-if="!depois.length" class="op-body text-muted-foreground">Ninguém mais pronto.</p>
            <div v-for="item in depois" :key="item.card.ref" class="flex items-center gap-3 border-b border-border py-2 last:border-0">
              <span class="op-title tnum font-bold">{{ code(item.card.ref) }}</span>
              <span class="min-w-0 flex-1 truncate op-body">{{ item.card.customer_name }} · {{ item.card.fulfillment_label }}</span>
              <span class="op-micro text-muted-foreground">{{ item.timeLabel }}</span>
            </div>
          </NuxtCard>
          <NuxtCard data-hf-entregadores>
            <p class="op-eyebrow text-muted-foreground">Entregadores</p>
            <p v-if="!entregadores.length" class="op-body text-muted-foreground">Nenhum na rua.</p>
            <div v-for="e in entregadores" :key="e.card.ref" class="border-b border-border py-2 last:border-0">
              <div class="flex items-center gap-3">
                <span class="op-title tnum font-bold">{{ code(e.card.ref) }}</span>
                <span class="min-w-0 flex-1 truncate op-body">{{ e.card.customer_name }} · {{ e.card.courier_status_label || e.card.status_label }}</span>
              </div>
              <div v-if="e.back" class="mt-2 rounded-md bg-muted px-3 py-2">
                <p v-if="e.card.courier_return_lines?.length" class="op-micro text-muted-foreground">Deve voltar com o entregador</p>
                <p v-for="line in e.card.courier_return_lines" :key="line" class="op-body font-semibold">{{ line }}</p>
                <NuxtButton class="mt-2" block color="primary" :disabled="isBusy(e.card.ref)" @click="courierBack(e.card.ref)">Entregador voltou</NuxtButton>
              </div>
            </div>
          </NuxtCard>
        </div>
      </div>
    </section>

    <!-- ═══ GERENTE: andando, o celular na mão ═══ -->
    <section v-else class="mx-auto flex w-full max-w-md flex-col gap-4 p-4">
      <header>
        <p class="op-eyebrow text-muted-foreground">Agora na loja</p>
        <p class="op-title">{{ estado }}</p>
      </header>

      <div v-if="perdas.length" class="flex flex-col gap-3">
        <p class="op-eyebrow text-destructive">Pode ser perdido</p>
        <NuxtCard v-for="item in perdas" :key="item.card.ref" :ui="{ body: 'p-4' }">
          <div class="flex items-baseline gap-3">
            <span class="op-figure tnum font-bold text-destructive">{{ clock(item).value }}</span>
            <span class="op-micro text-destructive">{{ clock(item).caption }}</span>
          </div>
          <p class="op-body"><span class="font-semibold">{{ code(item.card.ref) }} · {{ item.card.customer_name }}</span> · {{ channelLabel(item.card.channel_ref) }}</p>
          <p class="op-micro text-muted-foreground">{{ item.card.items_summary }} · {{ item.card.total_display }}</p>
          <div class="mt-3 grid grid-cols-[1fr_2fr] gap-2">
            <NuxtButton v-if="item.kind === 'confirm'" block color="neutral" variant="outline" size="lg" :to="`/${item.card.ref}`">Recusar</NuxtButton>
            <NuxtButton block size="lg" color="primary" :class="item.kind === 'confirm' ? '' : 'col-span-2'" :to="gesture(item)!.to" @click="gesture(item)!.run?.()">{{ gesture(item)!.label }}</NuxtButton>
          </div>
        </NuxtCard>
      </div>
      <NuxtCard v-else><p class="op-body text-muted-foreground">Nada para ser perdido agora.</p></NuxtCard>

      <div v-if="atrasados.length" class="flex flex-col gap-1">
        <p class="op-eyebrow text-warning">Atrasados</p>
        <NuxtLink v-for="item in atrasados" :key="item.card.ref" :to="`/${item.card.ref}`" class="flex items-center gap-3 rounded-md bg-card px-3 py-3">
          <span class="op-title tnum font-bold">{{ code(item.card.ref) }}</span>
          <span class="min-w-0 flex-1 truncate op-body">{{ item.card.customer_name }} · {{ item.card.status_label }}</span>
          <span class="op-body tnum text-warning">{{ item.timeLabel }}</span>
        </NuxtLink>
      </div>

      <div class="flex flex-col gap-1">
        <p class="op-eyebrow text-muted-foreground">Canais</p>
        <NuxtLink v-for="c in canais" :key="c.ref" to="/feeds" class="flex items-center justify-between rounded-md bg-card px-3 py-3 op-body">
          <span>{{ c.name }}</span>
          <NuxtBadge :color="c.active ? 'success' : 'error'" :label="c.active ? 'recebendo' : 'desligado'" />
        </NuxtLink>
      </div>
      <NuxtLink to="/?columns=all" class="op-body underline text-muted-foreground">Quadro completo</NuxtLink>
    </section>
  </main>
</template>
