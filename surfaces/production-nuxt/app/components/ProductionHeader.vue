<script setup lang="ts">
// Cabeçalho de seção do Produção — mora no topo do CONTEÚDO (não é o rail). Segura o
// controle do rail (kit) + a nav das visões de produção (Planejamento/Preparação/
// Produção/Expedição/Painel) + busca, alertas e atualizar. As funções COMUNS (Central,
// operador/travar, tema) vivem no OperatorRail à esquerda — o rail as concentra e economiza
// a horizontal. Touch-first e light-first, como o Gestor.
import {
  isEditableKeyboardTarget,
  productionGlobalKeysBlocked,
  resolveProductionGlobalShortcut,
} from "~/presentation/keyboard";

defineProps<{
  title: string;
  count?: number;
  countLabel?: string;
  /** 0–100: a linha visual do quanto o dia andou, JUNTO do contador. */
  progress?: number | null;
  pending?: boolean;
}>();
const emit = defineEmits<{ refresh: [] }>();
const query = defineModel<string>("query", { default: "" });

const route = useRoute();
const searchInput = ref<{ inputRef: HTMLInputElement | null } | null>(null);
const shortcutsHelpOpen = ref(false);

// Timers da bancada: ferramenta de primeira classe, em toda tela. O contador
// vem do localStorage — o servidor não o conhece —, então o primeiro render
// do cliente precisa BATER com o SSR (0) e só depois de montar mostrar o real.
const floorTimers = useFloorTimers();
const timersOpen = ref(false);
const hydrated = ref(false);
const timersCount = computed(() =>
  hydrated.value ? floorTimers.activeCount.value : 0,
);
const timersRinging = computed(() =>
  hydrated.value ? floorTimers.ringingCount.value : 0,
);

const SHORTCUT_ROUTES = {
  plan: "/plan",
  "mise-en-place": "/mise-en-place",
  produce: "/",
  expedite: "/expedite",
} as const;

function onGlobalKeydown(event: KeyboardEvent) {
  if (event.repeat || event.isComposing || productionGlobalKeysBlocked())
    return;
  const shortcut = resolveProductionGlobalShortcut(event);
  if (!shortcut) return;
  const editing = isEditableKeyboardTarget(event.target);
  if (editing && ["focus-search", "refresh", "help"].includes(shortcut)) return;

  event.preventDefault();
  if (shortcut === "focus-search") {
    searchInput.value?.inputRef?.focus();
    return;
  }
  if (shortcut === "refresh") {
    emit("refresh");
    return;
  }
  if (shortcut === "help") {
    shortcutsHelpOpen.value = true;
    return;
  }
  navigateTo(SHORTCUT_ROUTES[shortcut]);
}

onMounted(() => {
  hydrated.value = true;
  window.addEventListener("keydown", onGlobalKeydown);
});
onBeforeUnmount(() => window.removeEventListener("keydown", onGlobalKeydown));

// As abas são SÓ o fluxo do dia do operador: decide → separa/pesa → produz →
// expede. A Expedição É o fechamento de fornada (QC, ADR-017 §9): a fornada
// sai do forno já classificada. O que não é etapa do fluxo — o Letreiro
// (kiosk de TV) e os Relatórios (persona gestor) — mora no RAIL, não aqui:
// primeiro nível enxuto, e a fileira nunca mais estoura a janela escondendo
// aba sem aviso.
const tabs = computed(() => [
  {
    to: "/plan",
    label: "Planejamento",
    icon: "lucide:layout-grid",
    shortcut: "Alt+1",
  },
  {
    to: "/mise-en-place",
    label: "Preparação",
    icon: "lucide:scale",
    shortcut: "Alt+2",
  },
  {
    to: "/",
    label: "Produção",
    icon: "lucide:flame",
    shortcut: "Alt+3",
  },
  {
    to: "/expedite",
    label: "Expedição",
    icon: "lucide:package-check",
    shortcut: "Alt+4",
  },
]);
function isActive(to: string): boolean {
  return to === "/" ? route.path === "/" : route.path.startsWith(to);
}
</script>

<template>
  <header
    class="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b bg-card px-4 py-2.5"
  >
    <RailToggle />
    <div class="mr-2 min-w-0">
      <p
        class="text-xs font-medium uppercase tracking-wider text-muted-foreground"
      >
        Produção
      </p>
      <h1 class="truncate text-lg font-bold leading-tight">{{ title }}</h1>
    </div>

    <nav
      class="flex items-center gap-1 rounded-md border bg-background p-0.5"
      aria-label="Telas de produção"
    >
      <NuxtLink
        v-for="tab in tabs"
        :key="tab.to"
        :to="tab.to"
        :aria-keyshortcuts="tab.shortcut"
        :title="`${tab.label} · ${tab.shortcut}`"
        class="inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium transition"
        :class="
          isActive(tab.to)
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-foreground'
        "
      >
        <Icon :name="tab.icon" class="size-4" />
        <span class="hidden sm:inline">{{ tab.label }}</span>
        <OperatorKbd
          variant="inverse"
          class="hidden opacity-100 xl:inline-flex"
          aria-hidden="true"
          >{{ tab.shortcut }}</OperatorKbd>
      </NuxtLink>
    </nav>

    <div
      v-if="count != null"
      class="ml-auto hidden flex-col items-end gap-1 leading-none sm:flex"
    >
      <span class="text-lg font-bold tabular-nums"
        >{{ count }}
        <span
          class="text-xs font-medium uppercase tracking-wider text-muted-foreground"
          >{{ countLabel || "ativos" }}</span
        ></span
      >
      <!-- O percentual mora COM o número que ele resume — nunca longe dele. -->
      <div
        v-if="progress != null"
        class="flex items-center gap-1.5"
        role="progressbar"
        :aria-valuenow="progress"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-label="Progresso do dia"
      >
        <div class="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
          <div
            class="h-full rounded-full bg-primary transition-all"
            :style="{ width: `${progress}%` }"
          />
        </div>
        <span class="text-xs font-medium tabular-nums text-muted-foreground"
          >{{ progress }}%</span
        >
      </div>
    </div>

    <div
      class="flex items-center gap-1.5"
      :class="count != null ? '' : 'ml-auto'"
    >
      <div class="relative">
        <Icon
          name="lucide:search"
          class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <UiInput
          ref="searchInput"
          v-model="query"
          type="search"
          inputmode="search"
          placeholder="Buscar…"
          class="w-32 pl-8 pr-8 focus:w-44 sm:w-40"
          aria-label="Buscar por código, SKU ou receita"
          aria-keyshortcuts="/"
        />
        <!-- Limpar ocupa o espaço reservado dentro do campo; é affordance do input, não botão de toolbar. -->
        <button
          v-if="query"
          type="button"
          class="absolute right-1 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded text-muted-foreground transition hover:text-foreground"
          aria-label="Limpar busca"
          @click="query = ''"
        >
          <Icon name="lucide:x" class="size-3.5" />
        </button>
        <OperatorKbd
          v-else
          class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2"
          aria-hidden="true"
          >/</OperatorKbd>
      </div>
      <!-- Timers: contador de ativos; pulsa quando algum toca. Nunca bloqueia nada. -->
      <UiButton
        type="button"
        variant="outline"
        size="sm"
        class="relative min-h-11"
        :class="timersRinging ? 'border-destructive text-destructive' : ''"
        :aria-label="`Timers (${timersCount} ativos)`"
        title="Timers da bancada"
        @click="timersOpen = true"
      >
        <Icon
          name="lucide:alarm-clock"
          class="size-4"
          :class="timersRinging ? 'animate-pulse motion-reduce:animate-none' : ''"
        />
        <span class="hidden xl:inline">Timers</span>
        <span
          v-if="timersCount"
          class="absolute -right-1 -top-1 grid min-w-4 place-items-center rounded-full px-1 text-xs font-bold tabular-nums"
          :class="
            timersRinging
              ? 'bg-destructive text-destructive-foreground'
              : 'bg-primary text-primary-foreground'
          "
          >{{ timersCount }}</span
        >
      </UiButton>
      <AlertsBell />
      <UiButton
        type="button"
        variant="outline"
        size="icon-sm"
        class="min-h-11 min-w-11"
        aria-label="Atualizar"
        aria-keyshortcuts="R"
        title="Atualizar · R"
        @click="emit('refresh')"
      >
        <Icon
          name="lucide:refresh-cw"
          class="size-4"
          :class="pending ? 'animate-spin' : ''"
        />
      </UiButton>
      <UiButton
        type="button"
        variant="outline"
        size="sm"
        class="min-h-11"
        aria-label="Ver atalhos do teclado"
        aria-keyshortcuts="?"
        title="Atalhos do teclado · ?"
        @click="shortcutsHelpOpen = true"
      >
        <Icon name="lucide:keyboard" class="size-4" />
        <span class="hidden xl:inline">Atalhos</span>
        <OperatorKbd
          aria-hidden="true"
          >?</OperatorKbd>
      </UiButton>
    </div>
  </header>

  <ProductionShortcutsHelp v-model:open="shortcutsHelpOpen" />
  <FloorTimersPanel v-model:open="timersOpen" />
</template>
