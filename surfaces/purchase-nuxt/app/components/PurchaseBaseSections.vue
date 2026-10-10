<script setup lang="ts">
// As sub-seções da Base (Insumos, Fornecedores, Custos, Contagem) na faixa esquerda da
// toolbar: navegação, não filtro (cada uma muda a URL). É o `OperatorQuickFilters` do
// kit no modo de rota (todo item com `to`): a ativa é a da rota de agora. No celular,
// sub-seção com mais de 3 opções vira lista (WP-FASE2-UX-OPERADOR §11): `phone-max` 3,
// e as quatro da Base viram o `NuxtSelect` do kit em vez de uma faixa que some na borda.
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
  <OperatorQuickFilters :items="items" label="Cadastro da Base" :phone-max="3" data-base-sections />
</template>
