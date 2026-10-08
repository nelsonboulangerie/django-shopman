<script setup lang="ts">
// Ajustes do Gestor (UX-15, prévia v4 `gestor-fila4.html`): o andar do cadastro e do
// que se consulta fora do turno. Histórico, Catálogo, Clientes, Canais e Postos saíram
// do rail da operação e moram aqui, cada um a um toque. O ponto de atenção de Canais
// ("1 desligado") aparece no item Ajustes do rail e na linha de Canais.
const { settings } = useGestorSections();
const { expeditesOnly } = useGestorAccess();
const settingsItems = computed(() =>
  settings.value.map((entry) => ({
    label: entry.label,
    description: entry.description,
    icon: entry.icon.replace("lucide:", "i-lucide-"),
    to: entry.to,
    badge: entry.attention || undefined,
    "data-settings-section": entry.key,
  })),
);
useHead({ title: "Ajustes" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Ajustes" />

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <NuxtEmpty
        v-if="expeditesOnly"
        icon="i-lucide-lock"
        title="Ajustes restritos"
        description="Os ajustes do Gestor são de quem gerencia pedidos. Daqui você opera a Saída."
      />
      <!-- Navegação entre áreas: PageGrid de PageCard (contrato de Card do kit), com
           a descrição de cada área à vista e o aviso de atenção como Badge. -->
      <NuxtPageGrid
        v-else
        class="gap-[var(--op-region-gap)]"
        aria-label="Ajustes do Gestor"
      >
        <NuxtPageCard
          v-for="item in settingsItems"
          :key="item.to"
          :to="item.to"
          :icon="item.icon"
          :title="item.label"
          :description="item.description"
          :data-settings-section="item['data-settings-section']"
        >
          <template v-if="item.badge" #footer>
            <NuxtBadge color="warning" variant="subtle" :label="item.badge" />
          </template>
        </NuxtPageCard>
      </NuxtPageGrid>
    </section>
  </main>
</template>
