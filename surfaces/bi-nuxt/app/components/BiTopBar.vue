<script setup lang="ts">
// Cabeçalho do B.I. — navegação por domínio + a janela de análise compartilhada.
// A janela mora aqui (e não em cada página) porque a pergunta "em que período?"
// é uma só para o app inteiro — trocar de aba não pode trocar de período.
import { WINDOW_PRESETS } from "~/presentation/bi";

const route = useRoute();
const section = computed(() =>
  route.path.startsWith("/sales") ? "sales"
  : route.path.startsWith("/cash") ? "cash"
  : route.path.startsWith("/customers") ? "customers"
  : "production",
);

const tabs = [
  { to: "/", key: "production", label: "Produção", icon: "lucide:flame" },
  { to: "/sales", key: "sales", label: "Vendas", icon: "lucide:shopping-basket" },
  { to: "/cash", key: "cash", label: "Caixa", icon: "lucide:banknote" },
  { to: "/customers", key: "customers", label: "Clientes", icon: "lucide:users" },
] as const;

const { days } = useBiWindow();
</script>

<template>
  <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2.5 print:hidden">
    <RailToggle />
    <div class="h-6 w-px shrink-0 bg-border"></div>
    <nav
      class="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto rounded-md bg-muted p-1"
      aria-label="Seções do B.I."
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
    <div class="flex shrink-0 items-center gap-0.5 rounded-md bg-muted p-1" role="group" aria-label="Período de análise">
      <button
        v-for="preset in WINDOW_PRESETS"
        :key="preset.days"
        type="button"
        class="inline-flex h-8 items-center rounded-md px-3 text-sm transition-all"
        :class="days === preset.days
          ? 'bg-card font-semibold text-foreground shadow-sm'
          : 'text-muted-foreground hover:bg-card/60 hover:text-foreground'"
        @click="days = preset.days"
      >
        {{ preset.label }}
      </button>
    </div>
  </header>
</template>
