<script setup lang="ts">
// Uma linha do "Sobrou ou faltou?" (prévia `bi-sobra4.html`): produto e SKU, a
// etiqueta do veredito, a barra fez × vendeu com o desfecho, a hora em que acabou, o
// histórico nos mesmos dias da semana, a comparação com o típico e o "Ver lotes e
// vendas". Do desktop largo para cima é uma linha da grade de sete colunas; abaixo,
// um bloco de três linhas com as mesmas informações (nada fica só no desktop). A
// linha mora no corpo do NuxtCard (o respiro lateral é o do cartão); a linha aberta
// se diz pelo botão aceso e pelo detalhe tingido logo abaixo.
import type { BIOverShortRow } from "~/types/bi";
import { formatQty } from "~/presentation/bi";
import {
  historyText,
  outcomeText,
  soldoutText,
  verdictMeta,
  versusTypicalText,
} from "~/presentation/overShort";

const props = defineProps<{ row: BIOverShortRow; scale: number; open: boolean; columns: string }>();
const emit = defineEmits<{ toggle: [] }>();

const meta = computed(() => verdictMeta(props.row.verdict));
// O veredito é um NuxtBadge na cor do tema (o tom carrega o sentido; o rótulo também).
const BADGE = { destructive: "error", warning: "warning", success: "success" } as const;
const OUTCOME = { destructive: "text-destructive", warning: "text-warning", success: "text-success" } as const;
const detailId = computed(() => `over-short-detail-${props.row.sku}`);
</script>

<template>
  <!-- `lg:min-h-[50px]`: a linha da grade de sete colunas tem a altura da barra fez ×
       vendeu com a legenda embaixo; sem o piso, as linhas sem legenda encolhem e a
       grade perde o ritmo. -->
  <div
    class="grid items-center gap-x-3 gap-y-1.5 border-b border-border py-2.5 lg:min-h-[50px] lg:py-1.5"
    :class="columns"
    data-over-short-row
    :data-verdict="row.verdict"
  >
    <!-- produto -->
    <div class="min-w-0 lg:col-auto">
      <p class="op-body font-medium">
        {{ row.name }} <span class="font-mono op-micro text-muted-foreground">{{ row.sku }}</span>
      </p>
    </div>
    <!-- veredito -->
    <div class="justify-self-end lg:justify-self-start">
      <NuxtBadge :color="BADGE[meta.tone]" variant="soft" :label="meta.label" data-over-short-verdict />
    </div>
    <!-- fez × vendeu -->
    <div class="col-span-2 flex flex-col gap-1 lg:col-span-1">
      <OverShortBar :row="row" :scale="scale" />
      <p class="op-micro tnum text-muted-foreground">
        fez <b class="text-foreground">{{ formatQty(row.made) }}</b> · vendeu <b class="text-foreground">{{ formatQty(row.sold) }}</b> ·
        <span class="font-semibold" :class="OUTCOME[meta.tone]">{{ outcomeText(row) }}</span>
      </p>
    </div>
    <!-- acabou às -->
    <div class="op-label tnum max-lg:op-micro">
      <span class="text-muted-foreground lg:hidden">acabou às </span>
      <b v-if="row.verdict === 'short'" class="text-destructive">{{ soldoutText(row) }}</b>
      <template v-else>{{ soldoutText(row) }}</template>
    </div>
    <!-- nos N dias -->
    <div class="op-label tnum text-muted-foreground max-lg:justify-self-end max-lg:op-micro">{{ historyText(row) }}</div>
    <!-- contra o típico -->
    <div class="col-span-2 self-center op-micro text-muted-foreground md:col-span-1">{{ versusTypicalText(row) }}</div>
    <!-- aprofundar -->
    <div class="col-span-2 flex md:col-span-1 md:justify-end">
      <NuxtButton
        :color="open ? 'primary' : 'neutral'"
        :variant="open ? 'soft' : 'ghost'"
        :trailing-icon="open ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
        label="Ver lotes e vendas"
        class="w-full justify-center md:w-auto"
        :aria-expanded="open"
        :aria-controls="detailId"
        data-over-short-toggle
        @click="emit('toggle')"
      />
    </div>
  </div>
  <div v-if="open" :id="detailId">
    <slot />
  </div>
</template>
