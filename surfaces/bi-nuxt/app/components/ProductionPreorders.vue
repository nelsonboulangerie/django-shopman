<script setup lang="ts">
// Produção, terceira leitura: os dois tempos de cada encomenda na Cozinha (decisão do
// dono, 09/11/2026). A encomenda chega à Cozinha em hora combinada − preparo −
// antecedência, e chegar não é começar: a espera vai da chegada ao "Iniciar", o preparo
// do "Iniciar" ao "Pronto". Por pedido, não por estação. Venda do dia não entra: vai à
// Cozinha no aceite e não tem espera de encomenda. A página monta o cabeçalho (o
// período); este componente é o corpo.
import type { TableColumn } from "#ui/types";
import type { BIPreorderKitchenReport } from "~/types/bi";
import { formatInt } from "~/presentation/bi";
import {
  minutesLabel,
  preorderKitchenAnswer,
  preorderKitchenCsv,
  preorderKitchenLines,
  startedHint,
  type PreorderKitchenLine,
} from "~/presentation/preorderKitchen";

const { report, pending, error, refresh } = useBiReport<BIPreorderKitchenReport>("preorder-kitchen");

const lines = computed(() => preorderKitchenLines(report.value?.rows ?? []));

const columns: TableColumn<PreorderKitchenLine>[] = [
  { accessorKey: "ref", header: "Encomenda" },
  { accessorKey: "released", header: "Chegou à Cozinha", meta: { class: { td: "tnum" } } },
  { accessorKey: "started", header: "Iniciada", meta: { class: { td: "tnum" } } },
  { accessorKey: "ready", header: "Pronta", meta: { class: { th: "max-sm:hidden", td: "tnum max-sm:hidden" } } },
  { accessorKey: "wait", header: "Espera", meta: { class: { th: "text-end", td: "text-end tnum" } } },
  { accessorKey: "prep", header: "Preparo", meta: { class: { th: "text-end", td: "text-end tnum" } } },
];
</script>

<template>
  <div class="flex flex-col gap-3 [&>*]:shrink-0" data-bi-preorders>
    <OperatorScreenState v-if="error" state="error" what="as encomendas do período" @retry="refresh()" />
    <OperatorScreenState v-if="pending && !report" state="loading" what="as encomendas do período" data-bi-loading />

    <template v-if="report">
      <div class="grid grid-cols-2 gap-3 xl:grid-cols-[1.4fr_1fr_1fr_1fr]" data-bi-preorder-tiles>
        <OperatorMetric
          title="A resposta"
          :value="preorderKitchenAnswer(report)"
          size="statement"
          class="col-span-2 xl:col-span-1"
        />
        <OperatorMetric
          title="Espera na Cozinha"
          :value="minutesLabel(report.wait_median_minutes)"
          hint="Mediana, da chegada à Cozinha até o Iniciar"
        />
        <OperatorMetric
          title="Preparo"
          :value="minutesLabel(report.prep_median_minutes)"
          hint="Mediana, do Iniciar ao Pronto"
        />
        <OperatorMetric
          title="Encomendas na Cozinha"
          :value="formatInt(report.orders)"
          :hint="startedHint(report)"
        />
      </div>

      <OperatorReadingCard
        title="Encomenda por encomenda"
        description="A chegada mais recente primeiro. Quem ainda não foi iniciada fica sem os tempos, e não conta nas medianas."
        :csv="preorderKitchenCsv(report.rows)"
      >
        <OperatorTable
          in-card
          :data="lines"
          :columns="columns"
          :row-key="(row) => row.ref"
          sticky="header"
          class="max-h-[32rem]"
          caption="Encomendas na Cozinha, uma por linha"
          empty-icon="i-lucide-calendar-clock"
          empty-title="Nenhuma encomenda chegou à Cozinha no período"
          empty-description="A encomenda entra aqui quando chega à Cozinha, na hora combinada menos o preparo e a antecedência."
        />
      </OperatorReadingCard>
    </template>
  </div>
</template>
