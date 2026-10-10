<script setup lang="ts">
// As sub-seções da Base (Insumos, Fornecedores, Custos, Contagem) na faixa esquerda da
// toolbar: navegação, não filtro (cada uma muda a URL). É o `OperatorQuickFilters` do
// kit no modo de rota (todo item com `to`): a ativa é a da rota de agora, e a régua do
// celular (rolar a faixa ou virar lista) é a do kit, igual em toda a suíte.
import type { QuickFilterItem } from "../../../operator-kit/app/presentation/quickFilters";
import { PURCHASE_BASE_SECTIONS } from "~/presentation/purchaseSections";
import type { PurchaseBaseView } from "~/types/purchase";

const props = defineProps<{
  /** Contagem ao lado do nome ("Insumos 18"). */
  counts?: Partial<Record<PurchaseBaseView, number>>;
}>();

const items = computed<QuickFilterItem[]>(() =>
  PURCHASE_BASE_SECTIONS.map((section) => ({
    key: section.key,
    label: section.label,
    icon: section.icon,
    to: section.to,
    count: props.counts?.[section.key] ?? 0,
  })),
);
</script>

<template>
  <OperatorQuickFilters :items="items" label="Cadastro da Base" data-base-sections />
</template>
