<script setup lang="ts">
// Uma linha do "Sobrou ou faltou?" (prévia `bi-sobra4.html`): produto e SKU, a
// etiqueta do veredito, a barra fez × vendeu com o desfecho, a hora em que acabou, o
// histórico nos mesmos dias da semana, a comparação com o típico e o "Ver lotes e
// vendas". Do desktop largo para cima é uma linha da grade de sete colunas; abaixo,
// um bloco de três linhas com as mesmas informações (nada fica só no desktop).
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
const PILL = {
  destructive: "pill-destructive",
  warning: "pill-warning",
  success: "pill-success",
} as const;
const DOT = { destructive: "bg-destructive", warning: "bg-warning", success: "bg-success" } as const;
const OUTCOME = { destructive: "text-destructive", warning: "text-warning", success: "text-success" } as const;
const detailId = computed(() => `over-short-detail-${props.row.sku}`);
</script>

<template>
  <div
    class="grid items-center gap-x-3 gap-y-1.5 border-b border-border px-4 py-2.5 lg:min-h-[50px] lg:py-1.5"
    :class="[columns, open ? 'bg-primary/5' : '']"
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
      <span class="inline-flex h-6 items-center gap-1.5 rounded-full px-2 op-micro font-semibold" :class="PILL[meta.tone]">
        <span class="size-1.5 rounded-full" :class="DOT[meta.tone]" aria-hidden="true" />{{ meta.label }}
      </span>
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
      <button
        type="button"
        class="inline-flex min-h-control w-full items-center justify-center gap-1.5 rounded-md border border-border px-2.5 op-label transition hover:bg-accent md:w-auto lg:border-transparent"
        :class="open ? 'bg-secondary font-semibold' : ''"
        :aria-expanded="open"
        :aria-controls="detailId"
        data-over-short-toggle
        @click="emit('toggle')"
      >
        Ver lotes e vendas
        <Icon :name="open ? 'lucide:chevron-up' : 'lucide:chevron-down'" class="size-4" aria-hidden="true" />
      </button>
    </div>
  </div>
  <div v-if="open" :id="detailId">
    <slot />
  </div>
</template>
