<script setup lang="ts">
// Frescor da leitura: quando o servidor gerou o que está na tela, e há quanto tempo.
// É a frase das leituras SEM tempo real (Histórico, Clientes, B.I.), onde um selo
// "ao vivo" seria rótulo que mente; e é a prova, nas que têm tempo real, de que a
// fila não parou. Nasceu no Gestor (`orders-nuxt`) e subiu ao kit no PR-K2 do
// WP-BI-CANON-LAUDO, sem mudar de comportamento.
//
// A idade conta pelo relógio do SERVIDOR (`useNowTick` ancora em `generated_at`):
// dispositivo com o relógio errado não envelhece nem rejuvenesce a leitura.
//
// `inline` (UX-KIT-V1): a mesma frase, sem a faixa própria, para morar no fim da linha
// de recortes do cabeçalho de uma linha. O texto não encolhe: "Última leitura útil"
// segue escrito, porque é o que prova ao operador que a leitura não parou.
//
// `realtimeLabel`: o nome do estado do transporte, dito pelo app ("Ao vivo",
// "Conectando…"). O kit não decide o vocabulário do tempo real de cada superfície;
// só diz que a conexão e a leitura são estados distintos.
//
// `source` (opt-in): leitura que vem de FORA (o iFood), dita pela fonte e numa linha
// só: "Lido do iFood às 13h55 (há 9 s)". Hora de relógio e idade não se misturam
// na mesma grandeza. Sem a prop, a frase de sempre.
import { computed } from "vue";

import { useNowTick } from "../composables/useNowTick";
import { STORE_TIME_ZONE } from "../presentation/dates";
import { formatClock, formatClockSeconds } from "../presentation/clock";

const props = defineProps<{
  /** O carimbo da leitura: `generated_at` em ISO, como as projeções o mandam. */
  metadata?: { generated_at?: string | null } | null;
  /** A última tentativa de atualizar falhou (a leitura na tela é a anterior). */
  failed?: boolean;
  realtimeLabel?: string;
  inline?: boolean;
  /** Fonte externa da leitura, com o artigo: "do iFood". */
  source?: string;
}>();
const now = useNowTick(() => props.metadata?.generated_at ?? "");
const age = computed(() =>
  Math.max(
    0,
    Math.floor(
      (now.value - Date.parse(props.metadata?.generated_at ?? "")) / 1000,
    ),
  ),
);
const clock = computed(() =>
  props.metadata?.generated_at
    ? // A hora da casa, não a do processo: o SSR (UTC no servidor) e o navegador
      // escreveriam horas diferentes e a hidratação descasaria.
      formatClockSeconds(props.metadata.generated_at, STORE_TIME_ZONE)
    : "",
);
const sourceClock = computed(() =>
  props.metadata?.generated_at
    ? formatClock(props.metadata.generated_at, STORE_TIME_ZONE)
    : "",
);
</script>

<template>
  <component
    :is="inline ? 'span' : 'p'"
    class="flex flex-wrap gap-x-3 gap-y-1 text-xs font-normal text-muted-foreground"
    :class="
      source
        ? 'leading-4'
        : inline
          ? 'max-w-52 whitespace-normal leading-4'
          : 'px-4 py-1'
    "
    data-read-freshness
  >
    <span v-if="source && metadata?.generated_at" data-read-freshness-source
      >Lido {{ source }} às
      <time :datetime="metadata.generated_at">{{ sourceClock }}</time> (há
      {{ age }} s)<span v-if="failed"> · a última consulta falhou</span></span
    >
    <!-- Cada bloco é inteiro (#3143): no teto do `inline`, a frase quebra ENTRE a
         hora, a idade e a falha, nunca dentro de um deles ("há 3 / s"). -->
    <span v-else-if="metadata?.generated_at" data-read-freshness-useful
      ><span class="whitespace-nowrap" data-read-freshness-block
        >Última leitura útil:
        <time :datetime="metadata.generated_at">{{ clock }}</time></span
      >
      <span class="whitespace-nowrap" data-read-freshness-block
        >· há {{ age }} s</span
      >
      <span v-if="failed" class="whitespace-nowrap" data-read-freshness-block
        >· atualização falhou</span
      ></span
    >
    <span v-else>Horário da leitura indisponível</span>
    <span v-if="realtimeLabel" class="whitespace-nowrap"
      >Conexão: {{ realtimeLabel }}</span
    >
  </component>
</template>
