<script setup lang="ts">
// A faixa das sub-seções de Ajustes: Campanhas, Modelos, Ofertas e cupons e Plataformas.
//
// Fase 2 (WP-FASE2-UX-OPERADOR, A4 e seção 5): sub-seção divide a faixa esquerda da
// toolbar com os recortes rápidos, mas muda a URL (cada uma tem rota própria embaixo
// de `/settings`). A tela a põe no `#filters-primary` do `OperatorPageHeader`.
//
// É o `OperatorQuickFilters` do kit no modo de rota (todo item com `to`): a ativa é a
// da rota de agora, e a régua do celular é a do kit, igual em toda a suíte.
const { settingsSections } = useMarketingSections();

const items = computed(() =>
  settingsSections.map((section) => ({
    key: section.key,
    label: section.label,
    icon: section.icon.replace("lucide:", "i-lucide-"),
    to: section.to,
  })),
);
</script>

<template>
  <nav class="flex min-w-0" aria-label="Seções de Ajustes" data-marketing-settings-nav>
    <OperatorQuickFilters :items="items" label="Seções de Ajustes" />
  </nav>
</template>
