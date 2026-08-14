<script setup lang="ts">
// Cabeçalho do B.I. — navegação por domínio + a janela de análise compartilhada.
// A janela mora aqui (e não em cada página) porque a pergunta "em que período?"
// é uma só para o app inteiro — trocar de aba não pode trocar de período.
// Chips no padrão de bolsa (1 toque) + "Personalizado" com datas nativas.
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

const { selection, range, setPreset, applyCustom } = useBiWindow();

const customOpen = ref(false);
const customFrom = ref("");
const customTo = ref("");

function openCustom() {
  customFrom.value = range.value.date_from;
  customTo.value = range.value.date_to;
  customOpen.value = true;
}

function submitCustom() {
  applyCustom(customFrom.value, customTo.value);
  customOpen.value = false;
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
    <div class="relative ml-auto flex min-w-0 shrink items-center">
      <div
        class="flex items-center gap-0.5 overflow-x-auto rounded-md bg-muted p-1"
        role="group"
        aria-label="Período de análise"
      >
        <button
          v-for="preset in WINDOW_PRESETS"
          :key="preset.key"
          type="button"
          class="inline-flex h-8 shrink-0 items-center rounded-md px-2.5 text-sm transition-all"
          :class="chipClass(selection.preset === preset.key)"
          @click="setPreset(preset.key)"
        >
          {{ preset.label }}
        </button>
        <button
          type="button"
          class="inline-flex h-8 shrink-0 items-center gap-1 rounded-md px-2.5 text-sm transition-all"
          :class="chipClass(selection.preset === 'custom')"
          @click="customOpen ? (customOpen = false) : openCustom()"
        >
          <Icon name="lucide:calendar-range" class="size-4" />
          <span class="sr-only">Período personalizado</span>
        </button>
      </div>
      <!-- Popover do personalizado: datas nativas, zero lib externa. -->
      <div
        v-if="customOpen"
        class="absolute right-0 top-full z-20 mt-2 flex items-end gap-2 rounded-md border border-border bg-card p-3 shadow-md"
      >
        <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
          De
          <input
            v-model="customFrom"
            type="date"
            class="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          />
        </label>
        <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
          Até
          <input
            v-model="customTo"
            type="date"
            class="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          />
        </label>
        <button
          type="button"
          class="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground"
          :disabled="!customFrom || !customTo"
          @click="submitCustom"
        >
          Aplicar
        </button>
      </div>
    </div>
  </header>
</template>
