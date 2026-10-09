<script setup lang="ts">
// Ajustes do Marketing (fase 2, A4): o andar do cadastro e da configuração, fora da
// operação do dia. A mesma forma dos Ajustes do Gestor: cada sub-seção a um toque, com
// o que mora nela escrito. Dentro de uma sub-seção, a faixa da toolbar leva às outras.
const { settingsSections } = useMarketingSections();
const items = computed(() =>
  settingsSections.map((section) => ({
    key: section.key,
    label: section.label,
    description: section.description,
    icon: section.icon.replace("lucide:", "i-lucide-"),
    to: section.to,
  })),
);
useHead({ title: "Ajustes" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Ajustes" search-placeholder="Buscar campanha, modelo ou tela" />

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <NuxtPageGrid
        class="gap-[var(--op-region-gap)]"
        aria-label="Ajustes do Marketing"
      >
        <NuxtPageCard
          v-for="item in items"
          :key="item.key"
          :to="item.to"
          :icon="item.icon"
          :title="item.label"
          :description="item.description"
          :data-settings-section="item.key"
        />
      </NuxtPageGrid>
    </section>
  </main>
</template>
