<script setup lang="ts">
// Cabeçalho de seção do Marketing — mora no topo do CONTEÚDO (não é o rail).
// Segura o controle do rail (kit) + a navegação própria (Painel/Regras/Histórico).
// As funções comuns (Central, operador, tema) vivem no OperatorRail à esquerda.
const route = useRoute();
const section = computed(() =>
  route.path.startsWith("/rules") ? "rules"
  : route.path.startsWith("/modelos") ? "templates"
  : route.path.startsWith("/plataformas") ? "platforms"
  : route.path.startsWith("/history") ? "history"
  : "board",
);

const tabs = [
  { to: "/", key: "board", label: "Painel", icon: "lucide:megaphone" },
  { to: "/rules", key: "rules", label: "Regras", icon: "lucide:sliders-horizontal" },
  // Modelos entram na nav porque escrever o texto que vai ao cliente é operação, não
  // configuração de bastidor. Antes só existiam no Admin, e sem nenhum modelo era
  // impossível criar campanha por aqui.
  { to: "/modelos", key: "templates", label: "Modelos", icon: "lucide:file-text" },
  // Plataformas: por onde o anúncio SAI. Não confundir com canal, que é por onde se vende
  // (ADR-020 §10). Era a casa que faltava — sem ela, a config vazava para o painel.
  { to: "/plataformas", key: "platforms", label: "Plataformas", icon: "lucide:share-2" },
  { to: "/history", key: "history", label: "Histórico", icon: "lucide:history" },
] as const;
</script>

<template>
  <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2.5 print:hidden">
    <RailToggle />
    <div class="h-6 w-px shrink-0 bg-border"></div>
    <!-- min-w-0 + overflow-x-auto: no celular a nav rola DENTRO de si mesma. Sem
         isso ela empurra o header e a página inteira ganha scroll horizontal. -->
    <nav
      class="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto rounded-md bg-muted p-1"
      aria-label="Seções do Marketing"
    >
      <NuxtLink
        v-for="t in tabs"
        :key="t.key"
        :to="t.to"
        class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-3 text-sm transition-all"
        :class="section === t.key
          ? 'bg-card font-semibold text-foreground shadow-sm'
          : 'text-muted-foreground hover:bg-card/60 hover:text-foreground'"
      >
        <Icon :name="t.icon" class="size-4" :class="section === t.key ? 'text-foreground' : 'text-muted-foreground'" />
        <span>{{ t.label }}</span>
      </NuxtLink>
    </nav>
  </header>
</template>
