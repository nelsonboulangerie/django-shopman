<script setup lang="ts">
// Ajustes do Gestor (D, 13/11/2026): o andar do cadastro que se mexe fora do turno,
// Clientes e Postos. Histórico, Catálogo e Canais são operação e moram no rail; Rotinas
// mora no PDV.
import { SETTINGS_SKELETON_CARDS } from "~/presentation/gestorSections";

const { settings, ready } = useGestorSections();
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
      <!-- A grade só desenha com as permissões resolvidas (GES-22): antes, metade
           dos cartões entrava depois e o toque caía no cartão errado. -->
      <NuxtPageGrid
        v-else-if="!ready"
        class="gap-[var(--op-region-gap)]"
        aria-label="Carregando os Ajustes do Gestor"
        aria-busy="true"
        data-settings-loading
      >
        <NuxtSkeleton
          v-for="i in SETTINGS_SKELETON_CARDS"
          :key="i"
          class="h-28 w-full"
        />
      </NuxtPageGrid>
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
            <NuxtBadge color="warning" :label="item.badge" />
          </template>
        </NuxtPageCard>
      </NuxtPageGrid>
    </section>
  </main>
</template>
