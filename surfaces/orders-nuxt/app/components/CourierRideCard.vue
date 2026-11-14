<script setup lang="ts">
// PRÉVIA (14/11) — a corrida como UM cartão no Saída, do chamado à volta.
// Os pedidos dela não aparecem soltos: são as paradas deste cartão. Cada momento
// diz ao operador a única coisa que importa agora, e o gesto dele está pronto.
export interface RideStop {
  code: string;
  customer: string;
  place: string;
  /** done: entregue · now: o entregador vai para esta · next: depois · prep: ainda em preparo */
  state: "done" | "now" | "next" | "prep" | "ready";
  eta?: string;
}
const props = defineProps<{
  number: number;
  color: string;
  state: "searching" | "late" | "coming" | "atStore" | "route" | "back" | "failed";
  stops: RideStop[];
  courier?: { name: string; vehicle: string };
  since?: string;
  eta?: string;
  handoff?: string[];
  cost?: string;
}>();

const head = computed(() => ({
  searching: { icon: "i-lucide-radar", tone: "neutral", title: "Procurando entregador", hint: props.since ? `Chamada há ${props.since}` : "" },
  late: { icon: "i-lucide-hourglass", tone: "warning", title: "Ninguém aceitou ainda", hint: `Chamada há ${props.since}` },
  coming: { icon: "i-lucide-bike", tone: "info", title: `${props.courier?.name} chega em ${props.eta}`, hint: props.courier?.vehicle ?? "" },
  atStore: { icon: "i-lucide-store", tone: "primary", title: `${props.courier?.name} está na loja`, hint: props.courier?.vehicle ?? "" },
  route: { icon: "i-lucide-navigation", tone: "info", title: "Em rota", hint: `${props.stops.filter((s) => s.state === "done").length} de ${props.stops.length} entregues` },
  back: { icon: "i-lucide-undo-2", tone: "success", title: "Tudo entregue", hint: `${props.courier?.name} está voltando` },
  failed: { icon: "i-lucide-circle-x", tone: "error", title: "A TaOn não achou entregador", hint: `Depois de ${props.since}` },
}[props.state]));
const toneClass: Record<string, string> = {
  neutral: "text-toned", warning: "text-warning", info: "text-info", primary: "text-primary", success: "text-success", error: "text-error",
};
</script>

<template>
  <article class="overflow-hidden rounded-xl border border-default bg-default shadow-xs" :style="{ borderLeft: `5px solid ${color}` }" data-ride-card>
    <header class="flex items-start gap-3 px-4 pt-3.5">
      <span class="grid size-9 shrink-0 place-items-center rounded-full bg-elevated" :class="toneClass[head.tone]">
        <NuxtIcon :name="head.icon" class="size-5" :class="state === 'searching' ? 'animate-pulse' : ''" />
      </span>
      <div class="min-w-0 flex-1">
        <p class="flex items-center gap-2">
          <span class="op-micro font-semibold tabular-nums" :style="{ color }">Corrida {{ number }}</span>
          <span class="op-micro text-muted">· {{ stops.length }} {{ stops.length === 1 ? "pedido" : "pedidos" }}<template v-if="cost"> · {{ cost }}</template></span>
        </p>
        <p class="op-label font-semibold text-highlighted">{{ head.title }}</p>
        <p v-if="head.hint" class="op-micro text-muted">{{ head.hint }}</p>
      </div>
      <NuxtButton icon="i-lucide-ellipsis-vertical" color="neutral" variant="ghost" size="sm" square aria-label="Mais ações da corrida" />
    </header>

    <!-- as paradas, como trajeto -->
    <ol class="mt-3 flex flex-col px-4">
      <li v-for="(stop, i) in stops" :key="stop.code" class="relative flex items-center gap-3 pb-2.5 last:pb-0">
        <span v-if="i < stops.length - 1" class="absolute top-6 bottom-0 left-3 w-px" :class="stop.state === 'done' ? 'bg-success/60' : 'bg-default'" aria-hidden="true" />
        <span
          class="relative z-10 grid size-6 shrink-0 place-items-center rounded-full op-micro font-semibold"
          :class="stop.state === 'done' ? 'bg-success text-white' : stop.state === 'now' ? 'text-white ring-4' : 'border-2 bg-default text-toned'"
          :style="stop.state === 'now' ? { background: color, '--tw-ring-color': `${color}33` } : stop.state === 'done' ? {} : { borderColor: `${color}88` }"
        >
          <NuxtIcon v-if="stop.state === 'done'" name="i-lucide-check" class="size-3.5" />
          <template v-else>{{ i + 1 }}</template>
        </span>
        <span class="min-w-0 flex-1">
          <span class="block truncate op-body" :class="stop.state === 'done' ? 'text-muted line-through decoration-1' : 'font-medium text-highlighted'">{{ stop.code }} · {{ stop.customer }}</span>
          <span class="block truncate op-micro text-muted">{{ stop.place }}</span>
        </span>
        <NuxtBadge v-if="stop.state === 'prep'" label="Em preparo" color="warning" variant="soft" size="sm" icon="i-lucide-chef-hat" />
        <span v-else-if="stop.eta" class="op-micro tabular-nums text-muted">{{ stop.eta }}</span>
      </li>
    </ol>

    <!-- o que entregar na mão do entregador -->
    <div v-if="handoff?.length" class="mx-4 mt-3 rounded-lg bg-elevated/70 px-3 py-2">
      <p class="op-micro font-semibold text-toned">{{ state === "back" ? "Ele volta com" : "Entregue ao entregador" }}</p>
      <ul class="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
        <li v-for="item in handoff" :key="item" class="flex items-center gap-1 op-body text-highlighted"><NuxtIcon name="i-lucide-dot" class="size-4 text-muted" />{{ item }}</li>
      </ul>
    </div>

    <footer class="mt-3 flex gap-2 border-t border-default px-4 py-3">
      <template v-if="state === 'searching'">
        <p class="flex-1 self-center op-micro text-muted">A TaOn avisa quando alguém aceitar.</p>
      </template>
      <template v-else-if="state === 'late'">
        <NuxtButton block color="warning" icon="i-lucide-refresh-cw" label="Chamar de novo" />
        <NuxtButton block color="neutral" variant="outline" icon="i-lucide-split" label="Separar" />
      </template>
      <template v-else-if="state === 'coming'">
        <p class="flex-1 self-center op-micro text-muted">Deixe as sacolas no balcão de saída.</p>
      </template>
      <template v-else-if="state === 'atStore'">
        <NuxtButton block size="lg" icon="i-lucide-package-check" :label="`Entreguei as ${stops.length} sacolas`" />
      </template>
      <template v-else-if="state === 'route'">
        <p class="flex-1 self-center op-micro text-muted">Os clientes acompanham pelo link.</p>
      </template>
      <template v-else-if="state === 'back'">
        <NuxtButton block size="lg" color="success" icon="i-lucide-undo-2" label="Entregador voltou" />
      </template>
      <template v-else-if="state === 'failed'">
        <NuxtButton block icon="i-lucide-refresh-cw" label="Chamar de novo" />
        <NuxtButton block color="neutral" variant="outline" icon="i-lucide-map" label="Remontar no mapa" />
      </template>
    </footer>
  </article>
</template>
