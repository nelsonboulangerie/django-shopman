<script setup lang="ts">
// A perda de um lote, inteira e aberta nas partes (dono, 24/11: nenhuma tela
// esconde perda). O total é a soma da perda declarada com o que rendeu menos; cada
// parte diz quanto, a causa, quem fechou e a hora. "Rendeu mais" aparece à parte,
// com a causa, e não abate nada. Sem dinheiro: a Gerente vê quantidades.
import type { WorkOrderReportRow } from "~/types/production";
import { lossPartDetail, lossPartTitle, sortedLossParts } from "~/presentation/reports";

const props = defineProps<{ row: WorkOrderReportRow }>();
const parts = computed(() => sortedLossParts(props.row.loss_parts));
</script>

<template>
  <div class="grid min-w-40 max-w-72 gap-1 text-left whitespace-normal" data-loss-parts>
    <span class="font-semibold tabular-nums">{{ row.qty_loss_display }}</span>
    <ul v-if="parts.length" class="grid gap-1">
      <li
        v-for="(part, index) in parts"
        :key="`${part.kind}:${index}`"
        class="text-xs leading-snug"
        :class="part.counts_as_loss ? 'text-default' : 'text-muted-foreground'"
        :data-loss-part="part.kind"
      >
        <span class="font-medium">{{ lossPartTitle(part) }}</span>
        <span class="block text-muted-foreground">{{ lossPartDetail(part) }}</span>
      </li>
    </ul>
  </div>
</template>
