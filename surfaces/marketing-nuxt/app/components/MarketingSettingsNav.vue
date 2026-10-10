<script setup lang="ts">
// A faixa das sub-seções de Ajustes: Campanhas, Modelos, Ofertas e cupons e Plataformas.
//
// Fase 2 (WP-FASE2-UX-OPERADOR, A4 e seção 5): sub-seção divide a faixa esquerda da
// toolbar com os recortes rápidos, mas muda a URL (cada uma tem rota própria embaixo
// de `/settings`). A tela a põe no `#filters-primary` do `OperatorPageHeader`.
//
// Com quatro opções, a regra do celular (seção 11: "sub-seção com mais de 3 opções vira
// `NuxtSelect`") pede a lista no celular e as abas do `sm` para cima. As duas vão no
// HTML do servidor e o CSS escolhe (régua única, sem `v-if` de largura): o celular
// nasce no desenho do celular.
//
// ⚠️ Peça a promover: o `OperatorQuickFilters` do kit (K4, com `to`) ainda não existe;
// quando existir, esta faixa vira ele.
const { activeSettings, settingsSections } = useMarketingSections();

const items = computed(() =>
  settingsSections.map((section) => ({
    label: section.label,
    value: section.key,
    icon: section.icon.replace("lucide:", "i-lucide-"),
  })),
);

const current = computed({
  get: () => activeSettings.value ?? undefined,
  set: (next: string | undefined) => {
    const target = settingsSections.find((section) => section.key === next);
    if (target && target.key !== activeSettings.value) void navigateTo(target.to);
  },
});
</script>

<template>
  <nav class="flex min-w-0" aria-label="Seções de Ajustes" data-marketing-settings-nav>
    <NuxtTabs
      v-model="current"
      :items="items"
      :content="false"
      variant="pill"
      class="max-sm:hidden"
      aria-label="Seções de Ajustes"
    />
    <NuxtSelect
      v-model="current"
      :items="items"
      class="w-48 sm:hidden"
      aria-label="Seção de Ajustes"
      data-marketing-settings-select
    />
  </nav>
</template>
