<script setup lang="ts">
// Cabeçalho do B.I. — navegação por domínio + a janela de análise compartilhada.
// A janela mora aqui (e não em cada página) porque a pergunta "em que período?"
// é uma só para o app inteiro — trocar de aba não pode trocar de período.
//
// O período é UM botão que sempre DIZ a janela ativa ("28D · 18/07 – 14/08");
// os chips de bolsa (1D…Máx, No ano) e o personalizado moram no popover dele.
// Um controle só: a barra não disputa espaço nem rola em tela estreita.
//
// O desenho da barra (alvo de toque, `aria-current`, revelação da aba ativa) vem do
// `OperatorAppBar` do kit. As abas daqui estavam em `h-8` — metade do alvo de toque da
// casa — e a seção ativa podia nascer fora da área visível numa barra de oito abas.
import {
  WINDOW_PRESETS_CALENDAR,
  WINDOW_PRESETS_ROLLING,
  windowButtonLabel,
} from "~/presentation/bi";
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

const sections: OperatorSection[] = [
  { key: "production", label: "Produção", icon: "lucide:flame", to: "/" },
  { key: "sales", label: "Vendas", icon: "lucide:shopping-basket", to: "/sales" },
  { key: "cash", label: "Caixa", icon: "lucide:banknote", to: "/cash" },
  { key: "customers", label: "Clientes", icon: "lucide:users", to: "/customers" },
  { key: "profiles", label: "Perfis", icon: "lucide:armchair", to: "/profiles" },
  { key: "explore", label: "Explorar", icon: "lucide:compass", to: "/explore" },
  // As outras abas olham o que aconteceu; esta projeta.
  { key: "forecast", label: "Projeção", icon: "lucide:telescope", to: "/forecast" },
  // Última: a IA propõe cenários sobre os agregados; o gestor decide.
  { key: "scenarios", label: "Cenários", icon: "lucide:sparkles", to: "/scenarios" },
];

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
  <OperatorAppBar :sections="sections" label="Seções do B.I.">
    <template #end>
      <div class="relative">
        <button
          type="button"
          class="inline-flex min-h-control items-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground"
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
          class="absolute top-full right-0 z-20 mt-2 w-80 max-w-[calc(100vw-4rem)] rounded-md border border-border bg-card p-3 shadow-md"
        >
          <p class="mb-2 text-xs font-medium text-muted-foreground">Período atual</p>
          <div class="grid grid-cols-4 gap-1.5 rounded-md bg-muted p-1" role="group" aria-label="Período atual do calendário">
            <button
              v-for="preset in WINDOW_PRESETS_CALENDAR"
              :key="preset.key"
              type="button"
              class="inline-flex min-h-control items-center justify-center rounded-md px-1 text-sm whitespace-nowrap transition-all"
              :class="chipClass(selection.preset === preset.key)"
              @click="pick(preset.key)"
            >
              {{ preset.label }}
            </button>
          </div>
          <p class="mt-3 mb-2 text-xs font-medium text-muted-foreground">Últimos</p>
          <div class="grid grid-cols-4 gap-1.5 rounded-md bg-muted p-1" role="group" aria-label="Janelas móveis">
            <button
              v-for="preset in WINDOW_PRESETS_ROLLING"
              :key="preset.key"
              type="button"
              class="inline-flex min-h-control items-center justify-center rounded-md px-1 text-sm whitespace-nowrap transition-all"
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
                class="min-h-control w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
              />
            </label>
            <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              Até
              <input
                v-model="customTo"
                type="date"
                class="min-h-control w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
              />
            </label>
          </div>
          <button
            type="button"
            class="mt-2 inline-flex min-h-control w-full items-center justify-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
            :disabled="!customFrom || !customTo"
            @click="submitCustom"
          >
            Aplicar período
          </button>
        </div>
      </div>
    </template>
  </OperatorAppBar>
</template>
