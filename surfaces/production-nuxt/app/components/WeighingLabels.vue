<script setup lang="ts">
// Etiquetas de pesagem — SÓ IMPRESSÃO (papel físico, medium ≠ tela). Dois papéis:
//   · CEGAS: código do dia + ingrediente + peso + data, SEM o nome da receita (o
//     colaborador pesa sem correlacionar; o mapa código↔preparo é visão de gestor);
//   · INTERNAS: identificação planejada do preparo, inequivocamente separada
//     de qualquer rótulo de venda.
// Os tamanhos aqui são fixos para a etiquetadora, não os papéis tipográficos de tela —
// por isso este componente é allowlistado no guardrail de tipografia (como o PosReceipt).
import type {
  ProductionBlindLabel,
  ProductionPreparationLabelTicket,
} from "~/types/productionPrinting";
import {
  operationalTargetDisplay,
  projectedQuantityDisplay,
} from "~/presentation/weighing";

withDefaults(
  defineProps<{
    printMode: "pesagem" | "preparo";
    labels: ProductionBlindLabel[];
    tickets: ProductionPreparationLabelTicket[];
    copyNumber?: number;
  }>(),
  { copyNumber: 1 },
);
</script>

<template>
  <!-- Etiquetas CEGAS de pesagem: uma por (preparo × ingrediente). -->
  <section
    v-if="printMode === 'pesagem'"
    class="weighing-label-sheet hidden print:block"
    aria-hidden="true"
  >
    <div class="grid grid-cols-1 gap-2">
      <div
        v-for="label in labels"
        :key="label.key"
        class="flex break-inside-avoid flex-col gap-0.5 rounded border border-black p-2"
      >
        <span class="text-center text-[0.6rem] font-bold uppercase"
          >Pesagem interna · não é rótulo de venda</span
        >
        <span
          v-if="copyNumber > 1"
          class="text-center text-[0.65rem] font-bold uppercase"
          >{{ copyNumber }}ª via</span
        >
        <div class="flex items-baseline justify-between gap-2">
          <span class="font-mono text-2xl font-bold tracking-widest">{{
            label.code
          }}</span>
          <span class="text-[0.65rem]">{{ label.date }}</span>
        </div>
        <span class="text-sm font-semibold">{{ label.ingredient }}</span>
        <span class="font-mono text-[0.65rem]">{{ label.sku }}</span>
        <span class="text-lg font-bold tabular-nums">{{ label.weight }}</span>
        <span v-if="label.annotation" class="text-xs">{{ label.annotation }}</span>
      </div>
    </div>
  </section>

  <!-- Identificação interna do preparo: uma por preparo. -->
  <section
    v-else
    class="weighing-label-sheet hidden print:block"
    aria-hidden="true"
  >
    <div class="grid grid-cols-1 gap-2">
      <div
        v-for="ticket in tickets"
        :key="ticket.ticket_ref || ticket.output_sku"
        class="flex break-inside-avoid flex-col gap-0.5 rounded border border-black p-2"
      >
        <span class="text-center text-[0.6rem] font-bold uppercase"
          >Uso interno · não é rótulo de venda</span
        >
        <span
          v-if="copyNumber > 1"
          class="text-center text-[0.65rem] font-bold uppercase"
          >{{ copyNumber }}ª via</span
        >
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-lg font-bold uppercase leading-tight">{{
            ticket.name
          }}</span>
          <span class="text-xs font-semibold tabular-nums"
            >Preparo {{ ticket.made_display }} · Validade
            {{ ticket.expiry_display }}</span
          >
        </div>
        <span class="font-mono text-[0.7rem]">{{ ticket.output_sku }}</span>
        <span
          v-if="ticket.total_weight_display || ticket.dough_weight_display"
          class="text-base font-bold tabular-nums"
        >
          Alvo total:
          {{
            operationalTargetDisplay(
              ticket.total_weight_display,
              ticket.dough_weight_display,
            )
          }}
        </span>
        <span v-if="ticket.output_quantity_display" class="text-xs"
          >Rendimento previsto:
          {{ projectedQuantityDisplay(ticket.output_quantity_display) }}</span
        >
        <span v-if="ticket.sources_display" class="text-xs"
          >Objetivo: {{ ticket.sources_display }}</span
        >
        <span class="font-mono text-[0.65rem]">{{ ticket.blind_code }}</span>
      </div>
    </div>
  </section>
</template>

<style>
@media print {
  /* 80 mm com 4 mm de respiro em cada lateral. O driver pode usar papel
     contínuo ou etiquetas destacáveis sem reescalar a composição. */
  .weighing-label-sheet {
    box-sizing: border-box;
    width: 72mm;
    margin: 0 auto;
  }
}
</style>
