<script setup lang="ts">
// A barra superior primária das telas compostas (rodada 2). Protótipo do que o
// `OperatorPageHeader` passa a ser; aqui com `div`, porque a estrutura canônica do Nuxt
// UI só mora no kit (ledger). Regra do celular mantida: ☰ + título + 2 ícones + ⋯.
//   - o "Ao vivo · 10:42" é um SELO ao lado do título (dono, 09/10); sem espaço, ele
//     desce para a linha de baixo antes de espremer o título, que nunca corta;
//   - na mesa: o ciclo da barra lateral, o título com o selo, a busca, a ação primária
//     da tela e o ⋯; no celular a ação primária entra no ⋯ e Avisos ganha a vaga dela.
type MenuItem = { label: string; icon?: string; kbds?: string[]; class?: string; onSelect?: () => void };

withDefaults(
  defineProps<{
    title: string;
    live?: { label: string; color: "success" | "warning" | "error" | "neutral" } | null;
    primary?: { label: string; icon: string } | null;
    actions?: MenuItem[][];
    inbox?: number;
  }>(),
  { live: null, primary: null, actions: () => [], inbox: 0 },
);
const rail = useSuiteRail();
</script>

<template>
  <div class="flex min-h-14 items-center gap-1 px-2 py-1 sm:gap-2 sm:px-3" data-fase2-header>
    <NuxtDashboardSidebarToggle class="lg:hidden" aria-label="Abrir o menu do app" />
    <NuxtButton
      v-if="rail"
      class="hidden lg:inline-flex"
      :icon="rail.next.value.icon"
      color="neutral"
      variant="ghost"
      square
      :aria-label="rail.next.value.label"
      @click="rail.cycle()"
    />
    <div class="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5">
      <h1 class="min-w-0 text-lg font-semibold text-pretty text-highlighted">{{ title }}</h1>
      <NuxtBadge
        v-if="live"
        :color="live.color"
        :label="live.label"
        icon="i-lucide-radio"
        class="shrink-0 tabular-nums"
        data-fase2-live
      />
    </div>
    <slot name="search" />
    <NuxtChip :text="inbox || undefined" :show="inbox > 0" size="4xl" :inset="false" class="lg:hidden">
      <NuxtButton icon="i-lucide-bell" color="neutral" variant="ghost" square :aria-label="`Avisos, ${inbox} novos`" />
    </NuxtChip>
    <NuxtButton v-if="primary" :label="primary.label" :icon="primary.icon" class="max-sm:hidden" />
    <NuxtDropdownMenu v-if="actions.length" :items="actions" :content="{ align: 'end' }">
      <NuxtButton icon="i-lucide-ellipsis" color="neutral" variant="ghost" square aria-label="Mais ações" />
    </NuxtDropdownMenu>
  </div>
</template>
