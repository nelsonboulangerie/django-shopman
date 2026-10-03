<script setup lang="ts">
// Cabeçalho de seção do Marketing: mora no topo do CONTEÚDO (não é o rail).
//
// Decisão do dono (03/10/2026, SUITE-UX §6): o andar de OPERAÇÃO tem quatro
// seções, Decisões, Agendados, Enviados e Ajustes, e o andar de AJUSTES entra por
// um item só, com as próprias seções numa segunda linha (Campanhas, Modelos,
// Ofertas e cupons, Plataformas). No celular as quatro vão para uma barra no pé
// da tela, ao alcance do polegar (`MarketingSectionBar`, montado no fim da coluna de
// conteúdo pelo `app.vue`); a barra do topo fica com o sino.
//
// Nenhuma rota foi removida: `/v2?area=…`, `/campaigns`, `/templates`, `/platforms` e
// `/history` continuam onde estavam. Só mudou por onde se chega a elas.
// As funções comuns (Central, operador, tema) vivem no OperatorRail à esquerda.

import type { MarketingSettingsKey } from "~/composables/useMarketingSections";

const { activeSection, activeSettings, sections } = useMarketingSections();

const settingsSections: ReadonlyArray<{
  key: MarketingSettingsKey;
  label: string;
  to: string;
}> = [
  { key: "campaigns", label: "Campanhas", to: "/v2?area=campaigns" },
  { key: "templates", label: "Modelos", to: "/templates" },
  { key: "offers", label: "Ofertas e cupons", to: "/v2?area=offers" },
  { key: "platforms", label: "Plataformas", to: "/v2?area=platforms" },
];
</script>

<template>
  <!-- No celular a navegação mora na barra do pé; a do topo fica só com o sino. -->
  <div
    class="max-sm:[&_[data-operator-app-bar]_nav]:hidden"
    data-marketing-top-bar
  >
    <OperatorAppBar
      :sections="sections"
      :current="activeSection"
      label="Seções do Marketing"
    >
      <template #end>
        <MarketingNotificationsBell />
      </template>
    </OperatorAppBar>

    <nav
      v-if="activeSection === 'settings'"
      class="flex gap-1 overflow-x-auto border-b border-border bg-card px-4 py-2"
      aria-label="Seções de Ajustes"
      data-marketing-settings-nav
    >
      <NuxtLink
        v-for="section in settingsSections"
        :key="section.key"
        :to="section.to"
        :aria-current="activeSettings === section.key ? 'page' : undefined"
        class="inline-flex min-h-11 shrink-0 items-center rounded-md px-3 text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        :class="
          activeSettings === section.key
            ? 'bg-muted font-semibold text-foreground'
            : 'text-muted-foreground hover:bg-muted hover:text-foreground'
        "
      >
        {{ section.label }}
      </NuxtLink>
    </nav>

  </div>
</template>

