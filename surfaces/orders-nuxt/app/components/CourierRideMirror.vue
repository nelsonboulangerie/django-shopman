<script setup lang="ts">
// PRÉVIA (14/11) — o ESPELHO da corrida: uma linha que diz o momento dela e, só
// quando o gesto é de quem está no balcão, o botão pronto. Mora em dois lugares:
//  · no Painel, na coluna Prontos, no lugar dos pedidos da corrida;
//  · na página Entregas, na parte "Na rua".
// Tocar na linha (fora do botão) abre a corrida na página Entregas, com o detalhe.
import { rideColor } from "~/presentation/ridePalette";

export interface MirrorStop {
  code: string;
  done?: boolean;
}
const props = defineProps<{
  number: number;
  state: "searching" | "late" | "coming" | "atStore" | "route" | "back" | "failed";
  stops: MirrorStop[];
  courier?: string;
  /** "6 min" (chegada à loja) ou "12:49" (fim previsto da rota). */
  eta?: string;
  since?: string;
}>();
const tone = computed(() => rideColor(props.number - 1));
const done = computed(() => props.stops.filter((s) => s.done).length);
const line = computed(() => ({
  searching: { icon: "i-lucide-radar", title: "Procurando entregador", hint: props.since ? `há ${props.since}` : "" },
  late: { icon: "i-lucide-hourglass", title: "Ninguém aceitou ainda", hint: `há ${props.since}` },
  coming: { icon: "i-lucide-bike", title: `${props.courier} chega em ${props.eta}`, hint: "Deixe as sacolas no balcão de saída" },
  atStore: { icon: "i-lucide-store", title: `${props.courier} está na loja`, hint: "" },
  route: { icon: "i-lucide-navigation", title: `${props.courier} em rota`, hint: `${done.value} de ${props.stops.length} entregues · termina ${props.eta}` },
  back: { icon: "i-lucide-undo-2", title: "Tudo entregue", hint: `${props.courier} está voltando` },
  failed: { icon: "i-lucide-circle-x", title: "A TaOn não achou entregador", hint: "" },
}[props.state]));
// O gesto que é do balcão; os outros moram no detalhe.
const gesture = computed(() => ({
  atStore: { label: `Entreguei as ${props.stops.length} sacolas`, icon: "i-lucide-package-check", color: "primary" as const },
  back: { label: "Entregador voltou", icon: "i-lucide-undo-2", color: "success" as const },
  late: { label: "Chamar de novo", icon: "i-lucide-refresh-cw", color: "warning" as const },
  failed: { label: "Chamar de novo", icon: "i-lucide-refresh-cw", color: "error" as const },
} as Record<string, { label: string; icon: string; color: "primary" | "success" | "warning" | "error" }>)[props.state]);
</script>

<template>
  <NuxtLink
    :to="`/deliveries?ride=${number}`"
    class="group flex items-center gap-3 rounded-xl border border-default bg-default py-2.5 pr-2.5 pl-3 shadow-xs transition hover:border-accented hover:shadow-sm"
    :style="{ borderLeft: `6px solid ${tone.bg}` }"
    data-ride-mirror
  >
    <span class="grid size-8 shrink-0 place-items-center rounded-lg op-label font-bold tabular-nums" :style="{ background: tone.bg, color: tone.fg }">{{ number }}</span>
    <span class="min-w-0 flex-1">
      <span class="flex items-center gap-1.5 op-body font-semibold text-highlighted">
        <NuxtIcon :name="line.icon" class="size-4 shrink-0 text-muted" :class="state === 'searching' ? 'animate-pulse' : ''" />
        <span class="truncate">{{ line.title }}</span>
      </span>
      <span class="flex flex-wrap items-center gap-x-1.5 op-micro text-muted">
        <span v-for="s in stops" :key="s.code" class="tabular-nums" :class="s.done ? 'line-through decoration-1' : 'font-medium text-toned'">{{ s.code }}</span>
        <template v-if="line.hint"><span aria-hidden="true">·</span><span class="truncate">{{ line.hint }}</span></template>
      </span>
    </span>
    <NuxtButton
      v-if="gesture"
      :color="gesture.color"
      :icon="gesture.icon"
      :label="gesture.label"
      @click.prevent.stop
    />
    <NuxtIcon v-else name="i-lucide-chevron-right" class="size-5 shrink-0 text-dimmed transition group-hover:text-toned" />
  </NuxtLink>
</template>
