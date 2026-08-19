<script setup lang="ts">
// Cabeçalho do B.I. — navegação por domínio + a janela de análise compartilhada.
// A janela mora aqui (e não em cada página) porque a pergunta "em que período?"
// é uma só para o app inteiro — trocar de aba não pode trocar de período.
//
// O período é UM botão que sempre DIZ a janela ativa ("28D · 18/07 – 14/08");
// os chips de bolsa (1D…Máx, No ano) e o personalizado moram no popover dele.
// Um controle só: a barra não disputa espaço nem rola em tela estreita.
import {
  WINDOW_PRESETS_CALENDAR,
  WINDOW_PRESETS_ROLLING,
  windowButtonLabel,
} from "~/presentation/bi";

const route = useRoute();
const section = computed(() =>
  route.path.startsWith("/forecast") ? "forecast"
  : route.path.startsWith("/sales") ? "sales"
  : route.path.startsWith("/cash") ? "cash"
  : route.path.startsWith("/customers") ? "customers"
  : route.path.startsWith("/explore") ? "explore"
  : route.path.startsWith("/profiles") ? "profiles"
  : route.path.startsWith("/scenarios") ? "scenarios"
  : "production",
);

const tabs = [
  { to: "/", key: "production", label: "Produção", icon: "lucide:flame" },
  { to: "/sales", key: "sales", label: "Vendas", icon: "lucide:shopping-basket" },
  { to: "/cash", key: "cash", label: "Caixa", icon: "lucide:banknote" },
  { to: "/customers", key: "customers", label: "Clientes", icon: "lucide:users" },
  { to: "/profiles", key: "profiles", label: "Perfis", icon: "lucide:armchair" },
  { to: "/explore", key: "explore", label: "Explorar", icon: "lucide:compass" },
  // As outras abas olham o que aconteceu; esta projeta.
  { to: "/forecast", key: "forecast", label: "Projeção", icon: "lucide:telescope" },
  // Última: a IA propõe cenários sobre os agregados; o gestor decide.
  { to: "/scenarios", key: "scenarios", label: "Cenários", icon: "lucide:sparkles" },
] as const;

const { selection, range, setPreset, applyCustom } = useBiWindow();

const open = ref(false);
const customFrom = ref("");
const customTo = ref("");

function toggle() {
  if (!open.value) {
    customFrom.value = range.value.date_from;
    customTo.value = range.value.date_to;
  }
  open.value = !open.value;
}

function pick(key: string) {
  setPreset(key);
  open.value = false;
}

function submitCustom() {
  applyCustom(customFrom.value, customTo.value);
  open.value = false;
}

const chipClass = (active: boolean) =>
  active
    ? "bg-card font-semibold text-foreground shadow-sm"
    : "text-muted-foreground hover:bg-card/60 hover:text-foreground";
</script>

<template>
  <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2.5 print:hidden">
    <RailToggle />
    <div class="h-6 w-px shrink-0 bg-border"></div>
    <nav
      class="flex min-w-0 items-center gap-0.5 overflow-x-auto rounded-md bg-muted p-1"
      aria-label="Seções do B.I."
    >
      <NuxtLink
        v-for="t in tabs"
        :key="t.key"
        :to="t.to"
        class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-3 text-sm transition-all"
        :class="chipClass(section === t.key)"
      >
        <Icon :name="t.icon" class="size-4" :class="section === t.key ? 'text-foreground' : 'text-muted-foreground'" />
        <span>{{ t.label }}</span>
      </NuxtLink>
    </nav>

    <div class="relative ml-auto shrink-0">
      <button
        type="button"
        class="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground"
        :aria-expanded="open"
        aria-label="Período de análise"
        @click="toggle"
      >
        <Icon name="lucide:calendar-range" class="size-4 text-muted-foreground" />
        <span class="tabular-nums">{{ windowButtonLabel(selection, range) }}</span>
        <Icon name="lucide:chevron-down" class="size-4 text-muted-foreground" />
      </button>

      <div
        v-if="open"
        class="absolute right-0 top-full z-20 mt-2 w-80 max-w-[calc(100vw-4rem)] rounded-md border border-border bg-card p-3 shadow-md"
      >
        <p class="mb-2 text-xs font-medium text-muted-foreground">Período atual</p>
        <div class="grid grid-cols-4 gap-1.5 rounded-md bg-muted p-1" role="group" aria-label="Período atual do calendário">
          <button
            v-for="preset in WINDOW_PRESETS_CALENDAR"
            :key="preset.key"
            type="button"
            class="inline-flex h-8 items-center justify-center whitespace-nowrap rounded-md px-1 text-sm transition-all"
            :class="chipClass(selection.preset === preset.key)"
            @click="pick(preset.key)"
          >
            {{ preset.label }}
          </button>
        </div>
        <p class="mb-2 mt-3 text-xs font-medium text-muted-foreground">Últimos</p>
        <div class="grid grid-cols-4 gap-1.5 rounded-md bg-muted p-1" role="group" aria-label="Janelas móveis">
          <button
            v-for="preset in WINDOW_PRESETS_ROLLING"
            :key="preset.key"
            type="button"
            class="inline-flex h-8 items-center justify-center whitespace-nowrap rounded-md px-1 text-sm transition-all"
            :class="chipClass(selection.preset === preset.key)"
            @click="pick(preset.key)"
          >
            {{ preset.label }}
          </button>
        </div>
        <div class="my-3 border-t border-border"></div>
        <p class="mb-2 text-xs font-medium text-muted-foreground">Personalizado</p>
        <div class="grid grid-cols-2 gap-2">
          <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
            De
            <input
              v-model="customFrom"
              type="date"
              class="h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
            />
          </label>
          <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
            Até
            <input
              v-model="customTo"
              type="date"
              class="h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
            />
          </label>
        </div>
        <button
          type="button"
          class="mt-2 inline-flex h-9 w-full items-center justify-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
          :disabled="!customFrom || !customTo"
          @click="submitCustom"
        >
          Aplicar período
        </button>
      </div>
    </div>
  </header>
</template>
