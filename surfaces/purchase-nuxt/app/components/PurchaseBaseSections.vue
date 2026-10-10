<script setup lang="ts">
// As sub-seções da Base (Insumos, Fornecedores, Custos, Contagem) na faixa esquerda da
// toolbar: navegação, não filtro (cada uma muda a URL). Regra da toolbar no celular
// (WP-FASE2-UX-OPERADOR §11): sub-seção com mais de 3 opções vira `NuxtSelect`; na mesa,
// abas. As duas vão no HTML e o CSS escolhe (`sm:hidden` / `max-sm:hidden`): o celular
// nasce com a lista, sem piscar.
import { PURCHASE_BASE_SECTIONS } from "~/presentation/purchaseSections";
import type { PurchaseBaseView } from "~/types/purchase";

const props = defineProps<{
  current: PurchaseBaseView;
  /** Contagem ao lado do nome ("Insumos 18"). */
  counts?: Partial<Record<PurchaseBaseView, number>>;
}>();

const tabs = computed(() =>
  PURCHASE_BASE_SECTIONS.map((section) => ({
    label: section.label,
    value: section.key,
    icon: section.icon,
    count: props.counts?.[section.key] ?? 0,
  })),
);
const options = computed(() =>
  PURCHASE_BASE_SECTIONS.map((section) => ({
    label: props.counts?.[section.key] ? `${section.label} (${props.counts[section.key]})` : section.label,
    value: section.key,
    icon: section.icon,
  })),
);

function go(value: unknown) {
  const section = PURCHASE_BASE_SECTIONS.find((item) => item.key === value);
  if (section && section.key !== props.current) void navigateTo(section.to);
}
</script>

<template>
  <div class="min-w-0" data-base-sections>
    <NuxtSelect
      :model-value="current"
      :items="options"
      value-key="value"
      aria-label="Cadastro da Base"
      class="w-44 sm:hidden"
      data-base-sections-phone
      @update:model-value="go"
    />
    <NuxtTabs
      :model-value="current"
      :items="tabs"
      :content="false"
      variant="pill"
      aria-label="Cadastro da Base"
      class="w-max max-sm:hidden"
      data-base-sections-desk
      @update:model-value="go"
    >
      <template #trailing="{ item }">
        <OperatorCountChip :count="item.count" />
      </template>
    </NuxtTabs>
  </div>
</template>
