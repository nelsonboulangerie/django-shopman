<script setup lang="ts">
// PRÉVIA hiperfoco (31/10/2026, rodada 3): o Gestor aberto pelo POSTO.
// Três pessoas olham o Gestor no pico (dono, 31/10): o caixa no computador, de relance;
// o passe no tablet, em pé, entregando sacolas; o gerente no celular, andando. Mesmos
// dados, mesmas ações e mesmos diálogos do quadro (useOrdersBoard). Um pedido tem UMA
// anatomia em todo posto (relógio · quem · o essencial · o gesto); o posto muda a
// densidade e o que ganha destaque. `?modo=caixa|passe|gerente`.
// Corrige a revisão adversarial (REVISAO-ADVERSARIAL.md, achados 1 a 18).
import type { CancellationReason, OrderCardProjection } from "~/types/orders";
import {
  channelLabel,
  splitRef,
  confirmationRemainingLabel,
  oneTapDispatch,
  realtimeIndicator,
  type DispatchStep,
} from "~/presentation/board";
import { queueItems, workingOrders, waitsForCustomer, type QueueItem } from "~/presentation/queue";
import { COURIER_CALL_HASH } from "~/presentation/courier";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

const route = useRoute();
const modo = computed(() => String(route.query.modo || "caixa"));
const MODOS = [
  { value: "caixa", label: "Caixa · computador" },
  { value: "passe", label: "Passe · tablet" },
  { value: "gerente", label: "Gerente · celular" },
];
const TITLES: Record<string, string> = { caixa: "Pedidos", passe: "Saída", gerente: "Agora na loja" };

const {
  readMetadata, queue, zones, realtime, pending, error, refresh,
  isBusy, actionError, clearActionError,
  confirm, advance, reject, fetchCancellationReasons, courierBack, markStationReady,
  soundOn, soundBlocked, attentionPending, activateAttentionSound, acknowledgeAttention,
} = useOrdersBoard();
const intentions = useOrderIntention();
const nowMs = useNowTick(() => queue.value?.intake[0]?.server_now_iso ?? "");

// ── leitura: nunca dizer "nada pede você" sem ter lido, nem sobre dado velho
const loaded = computed(() => Boolean(queue.value));
const stale = computed(() => Boolean(error.value) && loaded.value);
const readClock = computed(() => {
  const at = readMetadata.value?.generated_at;
  return at ? new Date(at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "";
});
const realtimeView = computed(() => realtimeIndicator(realtime.value));
const liveTone = computed(() =>
  error.value ? "off" : realtime.value === "live" ? "live" : realtime.value === "connecting" ? "late" : "calm",
);

const cards = computed<OrderCardProjection[]>(() => {
  const seen = new Set<string>();
  return zones.value.flatMap((z) => z.cards).filter((c) => (seen.has(c.ref) ? false : (seen.add(c.ref), true)));
});
const allItems = computed(() => queueItems(cards.value, nowMs.value, { scope: "attention" }));

// ── LOCALIZAR: código, nome ou a Via Pedido no leitor (VP-<ref>-k-n-XXXX)
const query = ref("");
function matches(card: OrderCardProjection, q: string) {
  const term = q.trim().toUpperCase();
  if (!term) return true;
  const scanned = term.match(/^VP-(.+)-\d{1,2}-\d{1,2}-[A-Z2-7]{8}$/);
  if (scanned) return card.ref.toUpperCase() === scanned[1];
  return (
    card.ref.toUpperCase().includes(term) ||
    (card.customer_name || "").toUpperCase().includes(term) ||
    (card.channel_display_id || "").toUpperCase().includes(term)
  );
}
const items = computed(() => allItems.value.filter((i) => matches(i.card, query.value)));
const working = computed(() => workingOrders(cards.value, nowMs.value));
const waitingPay = computed(() => cards.value.filter(waitsForCustomer).length);
const code = (ref: string) => splitRef(ref).code;

// ── a anatomia única: o relógio lê numa frase só (rótulo em cima, número embaixo)
type Tone = "loss" | "late" | "calm";
function clock(item: QueueItem): { label: string; value: string; sub: string; tone: Tone } {
  if (item.cancelsIn !== null) {
    const m = Math.floor(item.cancelsIn / 60);
    const s = String(item.cancelsIn % 60).padStart(2, "0");
    return {
      label: item.kind === "negotiation" ? "o iFood decide sozinho em" : "cancela sozinho em",
      value: `${m}:${s}`,
      sub: "",
      tone: "loss",
    };
  }
  const left = item.card.confirmation_deadline_iso
    ? confirmationRemainingLabel(item.card.confirmation_deadline_iso, nowMs.value)
    : "";
  if (item.kind === "confirm" && left) return { label: "aceita sozinho em", value: left, sub: "", tone: "calm" };
  const late: Tone = item.tone === "late" ? "late" : "calm";
  if (item.kind === "handoff") return { label: "pronto há", value: item.timeLabel, sub: "", tone: late };
  if (item.kind === "courier_back") return { label: "na rua há", value: item.timeLabel, sub: "", tone: "calm" };
  const goal = item.card.goal_minutes ? `meta ${item.card.goal_minutes} min` : "";
  return { label: "há", value: item.timeLabel, sub: goal, tone: late };
}
const toneText: Record<Tone, string> = { loss: "text-destructive", late: "text-warning", calm: "text-muted-foreground" };

// ── os gestos de verdade (nenhum rótulo promete o que não faz)
type Gesture = { label: string; icon: string; run?: () => void; to?: string } | null;
const passeKinds = new Set(["dispatch", "courier_back"]);
function courierCalled(card: OrderCardProjection) {
  return Boolean(card.courier_status) || Boolean(card.courier_status_label);
}
/** A saída que precisa de maquininha e não tem nenhuma livre: dito ANTES do toque (L3). */
function noFreeMachine(card: OrderCardProjection) {
  return Boolean(card.dispatch_needs_machine) && !(card.equipment_options ?? []).some((o) => o.enabled);
}
/** A estação sem tela (papel): o Pronto dela se marca daqui. */
function paperStation(card: OrderCardProjection) {
  return card.kitchen?.stations.find((s) => s.can_mark_ready) ?? null;
}
function canCallCourier(card: OrderCardProjection) {
  return (card.actions ?? []).some((a) => a.ref === "courier-dispatch" && a.enabled);
}
function gesture(item: QueueItem, posto: string): Gesture {
  const card = item.card;
  if (posto === "caixa" && passeKinds.has(item.kind)) return null; // fato do passe
  switch (item.kind) {
    case "confirm":
      return { label: "Aceitar", icon: "i-lucide-check", run: () => void confirm(card.ref) };
    case "negotiation":
      return { label: "Responder no pedido", icon: "i-lucide-message-square-reply", to: `/${card.ref}#ifood-negotiations` };
    case "handoff":
      return payUnknown(card) ? null : { label: `Entregar ${code(card.ref)}`, icon: "i-lucide-hand-platter", run: () => void advance(card.ref) };
    case "dispatch":
      if (canCallCourier(card) && !courierCalled(card))
        return { label: "Chamar entregador", icon: "i-lucide-send", to: `/${card.ref}${COURIER_CALL_HASH}` };
      if (courierCalled(card)) return null; // a TaOn despacha sozinha quando coleta
      if (noFreeMachine(card)) return null;
      return { label: `Saiu ${code(card.ref)}`, icon: "i-lucide-bike", run: () => dispatch(card) };
    case "courier_back":
      return { label: "Entregador voltou", icon: "i-lucide-undo-2", run: () => (courierBackRef.value = card.ref) };
    case "station": {
      const st = paperStation(card);
      return st && card.kitchen
        ? {
            label: `Pronto de ${st.station_name}`,
            icon: "i-lucide-check",
            run: () => void markStationReady(card.ref, card.kitchen!.order_pk, st.station_ref),
          }
        : null;
    }
    case "start":
      return { label: "Iniciar preparo", icon: "i-lucide-arrow-right", run: () => void advance(card.ref) };
    default:
      return null;
  }
}
/** O que fica escrito quando não há gesto: o porquê, nunca um botão travado. */
function noGestureLine(item: QueueItem, posto: string): string {
  const card = item.card;
  if (posto === "caixa" && passeKinds.has(item.kind)) return "Resolve-se no passe.";
  if (item.kind === "handoff" && payUnknown(card) && posto === "caixa") return "Pagamento não registrado: confira antes de entregar.";
  if (item.kind === "dispatch" && courierCalled(card))
    return `${card.courier_status_label || "Entregador chamado"}. Sai sozinho quando o entregador coletar.`;
  if (item.kind === "dispatch" && noFreeMachine(card) && !courierCalled(card))
    return "Nenhuma maquininha livre: a saída espera uma voltar.";
  if (item.kind === "station" && paperStation(card))
    return `${paperStation(card)!.station_name} trabalha no papel: marque o Pronto quando o item chegar.`;
  if (item.kind === "blocked") return card.advance_block_reason || card.advance_block_label;
  return "";
}

// ── saída (o mesmo caminho do quadro: um toque quando não há o que perguntar)
const dispatchRef = ref<string | null>(null);
const dispatchCard = computed(() => cards.value.find((c) => c.ref === dispatchRef.value) ?? null);
async function runDispatch(steps: DispatchStep[]) {
  for (const step of steps) if (!(await advance(step.ref, step.changeOut, step.equipment, step.tripRef))) return false;
  return true;
}
function dispatch(card: OrderCardProjection) {
  const steps = oneTapDispatch(card, cards.value);
  if (steps) void runDispatch(steps);
  else dispatchRef.value = card.ref;
}
async function onDispatch(steps: DispatchStep[]) {
  if (await runDispatch(steps)) dispatchRef.value = null;
}
const courierBackRef = ref<string | null>(null);
const courierBackCard = computed(() => cards.value.find((c) => c.ref === courierBackRef.value) ?? null);
async function confirmCourierBack() {
  if (courierBackRef.value && (await courierBack(courierBackRef.value))) courierBackRef.value = null;
}
function courierBackDifferent() {
  const r = courierBackRef.value;
  courierBackRef.value = null;
  if (r) void navigateTo(`/${r}`);
}

// ── recusar: o mesmo diálogo de motivo do Gestor
const rejectRef = ref<string | null>(null);
const rejectReasons = ref<CancellationReason[]>([]);
const rejectLoading = ref(false);
const rejectError = ref("");
async function openReject(ref_: string) {
  rejectRef.value = ref_;
  rejectReasons.value = [];
  rejectError.value = "";
  rejectLoading.value = true;
  try {
    rejectReasons.value = await fetchCancellationReasons(ref_);
  } catch {
    rejectError.value = "Não foi possível consultar os motivos. Nenhuma ação foi aplicada.";
  } finally {
    rejectLoading.value = false;
  }
}
async function onReject(payload: { reason: string; cancellationCode: string }) {
  if (rejectRef.value && (await reject(rejectRef.value, payload.reason, payload.cancellationCode)))
    rejectRef.value = null;
}
const rejectMarketplace = computed(
  () => cards.value.find((c) => c.ref === rejectRef.value)?.channel_ref === "ifood",
);
function closeReject(value: boolean) {
  if (!value) rejectRef.value = null;
}

// ── a pergunta da retirada (dono, 31/10): sem pagamento registrado, a tela pergunta,
//    e a resposta fica no pedido (comentário com quem respondeu e quando).
function payUnknown(card: OrderCardProjection) {
  return card.fulfillment_type === "pickup" && !card.payment_pending && ["", "unknown"].includes(card.payment_status || "");
}
const notPaidRef = ref<string | null>(null);
const paidError = ref<Record<string, string>>({});
async function paidAndHandoff(card: OrderCardProjection) {
  paidError.value = { ...paidError.value, [card.ref]: "" };
  try {
    await intentions.execute(
      card.ref,
      "comment",
      (card.actions ?? []).find((a) => a.ref === "comment"),
      { note: "Retirada: o cliente disse que já pagou. O pagamento não estava registrado." },
    );
  } catch {
    // sem rastro, não entrega
    paidError.value = {
      ...paidError.value,
      [card.ref]: `${code(card.ref)} continua pronto: o Já pagou não chegou. Tente de novo.`,
    };
    return;
  }
  await advance(card.ref);
}
function bags(card: OrderCardProjection) {
  return card.volumes
    ? `${card.volumes} ${card.volumes === 1 ? "sacola" : "sacolas"}`
    : `${card.items_count} ${card.items_count === 1 ? "item" : "itens"} · sacolas não declaradas`;
}

// ── caixa: só o que pede você; A aceita o pedido novo mais urgente
const CAIXA_FOCUS = 6;
const caixaShown = computed(() => items.value.slice(0, CAIXA_FOCUS));
const firstLoss = computed(() => items.value.find((i) => i.cancelsIn !== null) ?? null);
const acceptRef = computed(() => items.value.find((i) => i.kind === "confirm")?.card.ref ?? "");
function onKey(event: KeyboardEvent) {
  if (modo.value !== "caixa" || event.key.toLowerCase() !== "a" || event.metaKey || event.ctrlKey) return;
  if ((event.target as HTMLElement)?.closest("input,textarea,[contenteditable]")) return;
  if (acceptRef.value) void confirm(acceptRef.value);
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

// ── passe: o pedido em destaque é o escolhido (toque na lista, busca ou leitor);
//    sem escolha, o primeiro da Saída.
const saida = computed(() => items.value.filter((i) => i.kind === "handoff" || i.kind === "dispatch"));
const chosen = ref<string | null>(null);
watch(query, () => {
  if (saida.value.length === 1) chosen.value = saida.value[0]!.card.ref;
});
const destaque = computed(() => saida.value.find((i) => i.card.ref === chosen.value) ?? saida.value[0] ?? null);
const depois = computed(() => saida.value.filter((i) => i !== destaque.value));
const voltas = computed(() => allItems.value.filter((i) => i.kind === "courier_back"));
const naRua = computed(() => {
  const back = new Set(voltas.value.map((i) => i.card.ref));
  return working.value.road.filter((o) => !back.has(o.card.ref));
});
const perdas = computed(() => allItems.value.filter((i) => i.cancelsIn !== null));

// ── gerente: o estado da loja numa frase; o que pode ser perdido; os atrasados; canais
const atrasados = computed(() => allItems.value.filter((i) => i.tone === "late" && i.cancelsIn === null));
const canais = computed(() => queue.value?.awareness?.menu_channels ?? []);
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const estado = computed(() =>
  [
    perdas.value.length ? plural(perdas.value.length, "pode ser perdido", "podem ser perdidos") : "",
    atrasados.value.length ? plural(atrasados.value.length, "atrasado", "atrasados") : "",
    `${working.value.kitchen.length} em preparo`,
    `${working.value.road.length} na rua`,
  ]
    .filter(Boolean)
    .join(" · "),
);
const switchRef = ref<string | null>(null);
const switchTarget = computed(() => canais.value.find((row) => row.ref === switchRef.value)?.switch ?? null);
const { switchChannel, isSwitching } = useChannelSwitch(
  (ref_) => canais.value.find((row) => row.ref === ref_)?.switch,
  () => refresh(),
);
const submitSwitch = (request: Parameters<typeof switchChannel>[1], approval?: Record<string, string>) =>
  switchChannel(switchRef.value!, request, approval);
function closeSwitch(value: boolean) {
  if (!value) switchRef.value = null;
}

const restLine = computed(() => {
  const hidden = items.value.length - caixaShown.value.length;
  const going = [
    working.value.kitchen.length ? `${working.value.kitchen.length} em preparo` : "",
    working.value.road.length ? `${working.value.road.length} na rua` : "",
    waitingPay.value ? `${waitingPay.value} esperando o cliente pagar` : "",
  ].filter(Boolean);
  return [
    hidden > 0 ? `Mais ${hidden} ${hidden === 1 ? "pede" : "pedem"} você` : "",
    going.length ? `Seguem sozinhos: ${going.join(", ")}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
});
useHead({ title: () => TITLES[modo.value] ?? "Pedidos" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-hf-posto>
    <OperatorPageHeader :title="TITLES[modo] ?? 'Pedidos'">
      <template #status>
        <OperatorLiveStatus
          :tone="liveTone"
          :time="readClock"
          :label="error ? 'Atualização falhou' : realtimeView.label"
          :short-label="realtimeView.shortLabel"
          :detail="realtimeView.title"
        />
      </template>
      <template #search>
        <OperatorSuiteSearch
          :model-value="query"
          screen-label="filtrando os pedidos"
          :placeholder="modo === 'passe' ? 'Código, cliente ou Via Pedido' : 'Código ou cliente'"
          aria-label="Buscar por código, cliente ou Via Pedido (atalho: /)"
          @update:model-value="(v: string) => (query = v)"
        />
      </template>
      <template #actions>
        <NuxtButton
          v-if="attentionPending"
          icon="i-lucide-check"
          label="Visto"
          color="neutral"
          variant="outline"
          @click="acknowledgeAttention()"
        />
      </template>
    </OperatorPageHeader>

    <div class="min-h-0 flex-1 overflow-auto">
      <!-- só para a prévia: no produto, o posto vem do dispositivo (Ajustes › Postos) -->
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

      <div
        class="mx-auto flex w-full flex-col gap-4 p-4"
        :class="modo === 'gerente' ? 'max-w-md' : modo === 'caixa' ? 'max-w-4xl sm:p-8' : ''"
      >
        <!-- leitura velha ou som bloqueado: antes de tudo, em todo posto -->
        <NuxtAlert
          v-if="stale"
          color="error"
          variant="subtle"
          icon="i-lucide-wifi-off"
          :title="readClock ? `Sem conexão. O que está na tela é de ${readClock}.` : 'Sem conexão. O que está na tela pode estar velho.'"
          :actions="alertActions('error', [{ label: 'Tentar de novo', onClick: () => refresh() }])"
          data-hf-stale
        />
        <NuxtAlert
          v-if="soundOn && soundBlocked"
          color="warning"
          variant="subtle"
          icon="i-lucide-volume-x"
          title="O som de pedido novo está bloqueado neste dispositivo."
          :actions="alertActions('warning', [{ label: 'Ligar o som', onClick: () => activateAttentionSound() }])"
          data-hf-sound
        />
        <p v-if="!loaded && !error" class="op-title text-muted-foreground" data-hf-loading>Lendo os pedidos…</p>
        <NuxtAlert
          v-else-if="!loaded && error"
          color="error"
          variant="subtle"
          icon="i-lucide-wifi-off"
          title="Sem conexão. Ainda não foi possível ler os pedidos."
          :actions="alertActions('error', [{ label: 'Tentar de novo', onClick: () => refresh() }])"
        />

        <template v-if="loaded">
          <!-- ═══ CAIXA: de relance, entre uma venda e outra ═══ -->
          <template v-if="modo === 'caixa'">
            <p
              class="op-figure leading-tight"
              :class="firstLoss ? 'text-destructive' : stale ? 'text-muted-foreground' : ''"
              data-hf-headline
            >
              <template v-if="stale && !items.length">Sem leitura nova: não dá para saber se algo pede você.</template>
              <template v-else-if="!items.length">{{ query ? "Nenhum pedido com esse código ou cliente." : "Nada pede você agora." }}</template>
              <template v-else-if="firstLoss">
                {{ code(firstLoss.card.ref) }} {{ clock(firstLoss).label }} {{ clock(firstLoss).value }}
              </template>
              <template v-else>{{ plural(items.length, "pedido pede", "pedidos pedem") }} você</template>
            </p>

            <ol v-if="items.length" class="flex flex-col divide-y divide-border rounded-lg border border-border bg-card">
              <li v-for="item in caixaShown" :key="item.card.ref" class="px-4 py-3" :data-hf-caixa="item.kind">
                <div class="grid grid-cols-[112px_minmax(0,1fr)_auto] items-center gap-4">
                  <div data-hf-clock>
                    <p class="op-micro leading-tight" :class="toneText[clock(item).tone]">{{ clock(item).label }}</p>
                    <p class="op-title tnum font-bold leading-none" :class="toneText[clock(item).tone]">{{ clock(item).value }}</p>
                    <p v-if="clock(item).sub" class="op-micro text-muted-foreground">{{ clock(item).sub }}</p>
                  </div>
                  <div class="min-w-0">
                    <p class="op-body">
                      <NuxtLink :to="`/${item.card.ref}`" class="font-semibold hover:underline">{{ code(item.card.ref) }}</NuxtLink>
                      <span class="font-semibold"> · {{ item.card.customer_name || "Sem cliente" }}</span>
                      <span class="text-muted-foreground"> · {{ item.card.fulfillment_label }} · {{ channelLabel(item.card.channel_ref) }}</span>
                    </p>
                    <p class="op-micro text-muted-foreground">{{ item.card.items_summary }} · {{ item.card.total_display }}</p>
                    <p v-if="noGestureLine(item, 'caixa')" class="op-micro text-muted-foreground">{{ noGestureLine(item, "caixa") }}</p>
                  </div>
                  <div class="flex items-center gap-2">
                    <NuxtButton
                      v-if="item.kind === 'confirm'"
                      color="neutral"
                      variant="outline"
                      label="Recusar"
                      :disabled="isBusy(item.card.ref)"
                      @click="openReject(item.card.ref)"
                    />
                    <NuxtButton
                      v-if="gesture(item, 'caixa')"
                      size="lg"
                      color="primary"
                      :icon="gesture(item, 'caixa')!.icon"
                      :to="gesture(item, 'caixa')!.to"
                      :loading="isBusy(item.card.ref)"
                      @click="gesture(item, 'caixa')!.run?.()"
                    >
                      {{ gesture(item, "caixa")!.label }}
                      <template v-if="item.card.ref === acceptRef" #trailing>
                        <NuxtKbd value="A" />
                      </template>
                    </NuxtButton>
                  </div>
                </div>
                <NuxtAlert
                  v-if="actionError(item.card.ref)"
                  class="mt-2"
                  color="error"
                  variant="subtle"
                  icon="i-lucide-triangle-alert"
                  :title="actionError(item.card.ref)"
                  close
                  @update:open="clearActionError(item.card.ref)"
                />
              </li>
            </ol>
            <p v-if="restLine" class="op-body text-muted-foreground">
              {{ restLine }} · <NuxtLink to="/?columns=all" class="underline">Quadro completo</NuxtLink>
            </p>
          </template>

          <!-- ═══ PASSE: em pé, a sacola na mão ═══ -->
          <template v-else-if="modo === 'passe'">
            <!-- só o que pode ser perdido interrompe o passe -->
            <NuxtAlert
              v-for="item in perdas"
              :key="`perda-${item.card.ref}`"
              color="error"
              variant="subtle"
              icon="i-lucide-alarm-clock"
              :title="`${code(item.card.ref)} · ${item.card.customer_name || 'Sem cliente'} ${clock(item).label} ${clock(item).value}`"
              :actions="
                alertActions('error', [
                  gesture(item, 'passe') && {
                    label: gesture(item, 'passe')!.label,
                    to: gesture(item, 'passe')!.to,
                    onClick: () => gesture(item, 'passe')!.run?.(),
                  },
                ])
              "
              data-hf-passe-perda
            />

            <div class="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <NuxtCard v-if="destaque" data-hf-destaque>
                <div class="flex items-start justify-between gap-4">
                  <p class="op-eyebrow text-muted-foreground">
                    {{ destaque.card.fulfillment_label }}<template v-if="destaque.card.channel_display_id"> · {{ destaque.card.channel_display_id }}</template>
                  </p>
                  <div class="text-end" data-hf-clock>
                    <p class="op-micro" :class="toneText[clock(destaque).tone]">{{ clock(destaque).label }}</p>
                    <p class="op-title tnum font-bold leading-none" :class="toneText[clock(destaque).tone]">{{ clock(destaque).value }}</p>
                    <p v-if="clock(destaque).sub" class="op-micro text-muted-foreground">{{ clock(destaque).sub }}</p>
                  </div>
                </div>
                <div class="mt-1 flex flex-wrap items-baseline gap-x-4">
                  <NuxtLink :to="`/${destaque.card.ref}`" class="op-display tnum hover:underline">{{ code(destaque.card.ref) }}</NuxtLink>
                  <p class="op-title">{{ destaque.card.customer_name || "Sem cliente" }}</p>
                </div>
                <p class="mt-3 op-title">{{ bags(destaque.card) }}</p>
                <p class="op-body text-muted-foreground">{{ destaque.card.items_summary }}</p>
                <p v-if="destaque.card.delivery_address" class="mt-1 op-body">{{ destaque.card.delivery_address }}</p>
                <p v-if="destaque.card.change_label" class="mt-3 rounded-md bg-muted px-3 py-2 op-title">{{ destaque.card.change_label }}</p>
                <p v-if="noGestureLine(destaque, 'passe')" class="mt-3 op-body">{{ noGestureLine(destaque, "passe") }}</p>

                <!-- a pergunta da retirada sem pagamento registrado (dono, 31/10) -->
                <div v-if="destaque.kind === 'handoff' && payUnknown(destaque.card)" class="mt-5" data-hf-pergunta>
                  <p class="op-title">Já pagou? <span class="text-muted-foreground">{{ destaque.card.total_display }}</span></p>
                  <div class="mt-2 grid grid-cols-2 gap-3">
                    <NuxtButton size="xl" color="neutral" variant="outline" block @click="notPaidRef = destaque.card.ref">Ainda não pagou</NuxtButton>
                    <NuxtButton size="xl" color="primary" block icon="i-lucide-check" :loading="isBusy(destaque.card.ref)" @click="paidAndHandoff(destaque.card)">Já pagou, entregar</NuxtButton>
                  </div>
                  <NuxtAlert
                    v-if="notPaidRef === destaque.card.ref"
                    class="mt-3"
                    color="warning"
                    variant="subtle"
                    icon="i-lucide-hand-coins"
                    :title="`Receba ${destaque.card.total_display} no PDV, em Encomendas, e entregue por lá.`"
                    description="O Gestor não tem caixa: o dinheiro entra pela gaveta do PDV."
                  />
                  <NuxtAlert
                    v-if="paidError[destaque.card.ref]"
                    class="mt-3"
                    color="error"
                    variant="subtle"
                    icon="i-lucide-triangle-alert"
                    :title="paidError[destaque.card.ref]"
                  />
                </div>
                <NuxtButton
                  v-else-if="gesture(destaque, 'passe')"
                  class="mt-5"
                  size="xl"
                  color="primary"
                  block
                  :icon="gesture(destaque, 'passe')!.icon"
                  :to="gesture(destaque, 'passe')!.to"
                  :loading="isBusy(destaque.card.ref)"
                  @click="gesture(destaque, 'passe')!.run?.()"
                >
                  {{ gesture(destaque, "passe")!.label }}
                </NuxtButton>
                <NuxtAlert
                  v-if="actionError(destaque.card.ref)"
                  class="mt-3"
                  color="error"
                  variant="subtle"
                  icon="i-lucide-triangle-alert"
                  :title="actionError(destaque.card.ref)"
                  close
                  @update:open="clearActionError(destaque.card.ref)"
                />
              </NuxtCard>
              <NuxtCard v-else>
                <p class="op-title text-muted-foreground">
                  {{ query ? "Nenhum pedido pronto com esse código ou cliente." : stale ? "Sem leitura nova: não dá para saber o que está pronto." : "Nada pronto para sair." }}
                </p>
              </NuxtCard>

              <div class="flex flex-col gap-4">
                <NuxtCard>
                  <p class="op-eyebrow text-muted-foreground">Também prontos</p>
                  <p v-if="!depois.length" class="op-body text-muted-foreground">Nenhum outro pronto.</p>
                  <!-- tocar traz para o destaque: quem chega ao balcão não segue a ordem da fila -->
                  <button
                    v-for="item in depois"
                    :key="item.card.ref"
                    type="button"
                    class="flex min-h-12 w-full items-center gap-3 border-b border-border py-2 text-start last:border-0"
                    :aria-label="`Atender ${code(item.card.ref)}, ${item.card.customer_name || 'sem cliente'}`"
                    @click="chosen = item.card.ref"
                  >
                    <span class="op-title tnum font-bold">{{ code(item.card.ref) }}</span>
                    <span class="min-w-0 flex-1 op-body">{{ item.card.customer_name || "Sem cliente" }} · {{ item.card.fulfillment_label }}</span>
                    <span class="op-micro" :class="toneText[clock(item).tone]">{{ clock(item).label }} {{ clock(item).value }}</span>
                  </button>
                </NuxtCard>
                <NuxtCard data-hf-entregadores>
                  <p class="op-eyebrow text-muted-foreground">Entregadores</p>
                  <p v-if="!voltas.length && !naRua.length" class="op-body text-muted-foreground">Nenhum na rua.</p>
                  <div v-for="item in voltas" :key="item.card.ref" class="border-b border-border py-2 last:border-0">
                    <p class="op-body">
                      <span class="op-title tnum font-bold">{{ code(item.card.ref) }}</span> · {{ item.card.customer_name }} · {{ item.card.courier_status_label || item.card.status_label }}
                    </p>
                    <div class="mt-2 rounded-md bg-muted px-3 py-2">
                      <template v-if="item.card.courier_return_lines?.length">
                        <p class="op-micro text-muted-foreground">Deve voltar com o entregador</p>
                        <p v-for="line in item.card.courier_return_lines" :key="line" class="op-body font-semibold">{{ line }}</p>
                      </template>
                      <NuxtButton class="mt-2" block color="primary" icon="i-lucide-undo-2" :loading="isBusy(item.card.ref)" @click="courierBackRef = item.card.ref">Entregador voltou</NuxtButton>
                    </div>
                  </div>
                  <div v-for="o in naRua" :key="o.card.ref" class="flex items-baseline gap-3 border-b border-border py-2 last:border-0">
                    <span class="op-title tnum font-bold">{{ code(o.card.ref) }}</span>
                    <span class="min-w-0 flex-1 op-body">{{ o.card.customer_name }} · {{ o.card.courier_status_label || o.card.status_label }}</span>
                  </div>
                </NuxtCard>
              </div>
            </div>
          </template>

          <!-- ═══ GERENTE: andando, o celular na mão ═══ -->
          <template v-else>
            <p class="op-title" data-hf-estado>{{ estado }}</p>

            <section class="flex flex-col gap-3">
              <p class="op-eyebrow text-destructive">Pode ser perdido</p>
              <p v-if="!perdas.length" class="op-body text-muted-foreground">Nenhum pedido para ser perdido agora.</p>
              <NuxtCard v-for="item in perdas" :key="item.card.ref">
                <div class="grid grid-cols-[124px_minmax(0,1fr)] gap-3">
                  <div data-hf-clock>
                    <p class="op-micro leading-tight text-destructive">{{ clock(item).label }}</p>
                    <p class="op-title tnum font-bold leading-none text-destructive">{{ clock(item).value }}</p>
                  </div>
                  <div class="min-w-0">
                    <p class="op-body">
                      <NuxtLink :to="`/${item.card.ref}`" class="font-semibold">{{ code(item.card.ref) }} · {{ item.card.customer_name }}</NuxtLink>
                      · {{ channelLabel(item.card.channel_ref) }}
                    </p>
                    <p class="op-micro text-muted-foreground">{{ item.card.items_summary }} · {{ item.card.total_display }}</p>
                  </div>
                </div>
                <div class="mt-3 grid gap-2" :class="item.kind === 'confirm' ? 'grid-cols-[1fr_2fr]' : 'grid-cols-1'">
                  <NuxtButton v-if="item.kind === 'confirm'" block color="neutral" variant="outline" size="lg" label="Recusar" @click="openReject(item.card.ref)" />
                  <NuxtButton
                    v-if="gesture(item, 'gerente')"
                    block
                    size="lg"
                    color="primary"
                    :icon="gesture(item, 'gerente')!.icon"
                    :to="gesture(item, 'gerente')!.to"
                    :loading="isBusy(item.card.ref)"
                    @click="gesture(item, 'gerente')!.run?.()"
                  >{{ gesture(item, "gerente")!.label }}</NuxtButton>
                </div>
                <NuxtAlert
                  v-if="actionError(item.card.ref)"
                  class="mt-2"
                  color="error"
                  variant="subtle"
                  icon="i-lucide-triangle-alert"
                  :title="actionError(item.card.ref)"
                  close
                  @update:open="clearActionError(item.card.ref)"
                />
              </NuxtCard>
            </section>

            <section v-if="atrasados.length" class="flex flex-col gap-1">
              <p class="op-eyebrow text-warning">Atrasados</p>
              <NuxtLink
                v-for="item in atrasados"
                :key="item.card.ref"
                :to="`/${item.card.ref}`"
                class="grid grid-cols-[124px_minmax(0,1fr)] items-center gap-3 rounded-md bg-card px-3 py-3"
              >
                <div>
                  <p class="op-micro leading-tight text-warning">{{ clock(item).label }}</p>
                  <p class="op-title tnum font-bold leading-none text-warning">{{ clock(item).value }}</p>
                  <p v-if="clock(item).sub" class="op-micro text-muted-foreground">{{ clock(item).sub }}</p>
                </div>
                <p class="min-w-0 op-body">
                  <span class="font-semibold">{{ code(item.card.ref) }}</span> · {{ item.card.customer_name }} · {{ item.card.status_label }}
                </p>
              </NuxtLink>
            </section>

            <section class="flex flex-col gap-1">
              <p class="op-eyebrow text-muted-foreground">Canais</p>
              <div v-for="c in canais" :key="c.ref" class="flex min-h-12 items-center justify-between gap-3 rounded-md bg-card px-3 py-2">
                <span class="op-body">{{ c.name }} {{ c.active ? "ligado" : "desligado" }}</span>
                <NuxtSwitch
                  v-if="c.switch"
                  color="success"
                  :model-value="c.active"
                  :disabled="isSwitching(c.ref) || !c.switch.enabled"
                  :aria-label="c.active ? `${c.name}: ligado. Desligar…` : `${c.name}: desligado. Ligar…`"
                  @update:model-value="switchRef = c.ref"
                />
              </div>
            </section>
          </template>
        </template>
      </div>
    </div>

    <DispatchDialog
      :card="dispatchCard"
      :cards="cards"
      :busy="dispatchRef != null && isBusy(dispatchRef)"
      @dispatch="onDispatch"
      @courier-back="(ref_: string) => (courierBackRef = ref_)"
      @close="dispatchRef = null"
    />
    <CourierBackDialog
      :card="courierBackCard"
      :busy="courierBackRef != null && isBusy(courierBackRef)"
      @confirm="confirmCourierBack"
      @different="courierBackDifferent"
      @close="courierBackRef = null"
    />
    <OrderReasonDialog
      :open="rejectRef != null"
      mode="reject"
      :loading="rejectLoading"
      :reasons="rejectReasons"
      :presets="[]"
      :cancel-reasons="[]"
      :busy="rejectRef != null && isBusy(rejectRef)"
      :marketplace="rejectMarketplace"
      :error="rejectError"
      @update:open="closeReject"
      @retry="rejectRef && openReject(rejectRef)"
      @confirm="onReject"
    />
    <ChannelSwitchDialog
      :open="Boolean(switchTarget)"
      :sw="switchTarget"
      :managers="queue?.awareness?.managers ?? []"
      :viewer-name="queue?.awareness?.viewer_name ?? ''"
      :busy="Boolean(switchRef && isSwitching(switchRef))"
      :submit="submitSwitch"
      @update:open="closeSwitch"
    />
  </main>
</template>
