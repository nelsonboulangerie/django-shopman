<script setup lang="ts">
// Cabeçalho das telas da Produção na camada visual da suíte (V4-PROD, prévias v4
// `plano-porque4.html` e `producao-qualidade4.html`): UMA linha com o título, o ponto
// ao vivo com a hora da última leitura, a busca, o progresso do dia ("4 de 28
// planejados" com a barra), os controles da tela (`#actions`, ex.: o dia) e o ⋯
// (Atualizar, Timers, Atalhos). Os recortes descem para a segunda linha (`#filters`).
// As etapas do lote (Planejamento a Qualidade) moram no rail da suíte e, no celular, na
// barra do polegar (`ProductionNav`); este cabeçalho segura as TECLAS delas (Alt+1 a
// Alt+5), que valem em toda tela da Produção, mais "/", R e "?".
//
// No celular (`OperatorPageHeader`): barra de 56px com o selo do app, o título, o ponto,
// a lupa, Timers (contagem e anel quando toca) e o sino; os controles descem para uma
// linha que rola. Receitas, Relatórios e o Letreiro, que no tablet moram no pé do rail,
// entram no ⋯ do celular.
import {
  isEditableKeyboardTarget,
  productionGlobalKeysBlocked,
  resolveProductionGlobalShortcut,
} from "~/presentation/keyboard";

const props = withDefaults(
  defineProps<{
    title: string;
    count?: number;
    countLabel?: string;
    /** Total do dia: com ele o contador fala "4 de 28 planejados". */
    total?: number | null;
    /** 0–100: a linha visual do quanto o dia andou, JUNTO do contador. */
    progress?: number | null;
    pending?: boolean;
    /** A última leitura falhou e a tela mostra dado velho: o ao vivo fala por extenso. */
    stale?: boolean;
    /** Linha fina sob o título (ex.: "sáb 03/10 · lotes fechados hoje"). */
    eyebrow?: string;
    searchPlaceholder?: string;
    /** Telas sem busca própria (ex.: Timers) escondem o campo. */
    searchable?: boolean;
  }>(),
  {
    count: undefined,
    countLabel: "",
    total: null,
    progress: null,
    pending: false,
    stale: false,
    eyebrow: "",
    searchPlaceholder: "Buscar produto ou SKU",
    searchable: true,
  },
);
const emit = defineEmits<{ refresh: [] }>();
const query = defineModel<string>("query", { default: "" });

const searchInput = ref<{ focus: () => void } | null>(null);
const shortcutsHelpOpen = ref(false);
const menuOpen = ref(false);

// Timers da bancada: o contador vem do localStorage — o servidor não o conhece —,
// então o primeiro render do cliente precisa BATER com o SSR (0) e só depois de
// montar mostrar o real.
const floorTimers = useFloorTimers();
const hydrated = ref(false);
const timersCount = computed(() =>
  hydrated.value ? floorTimers.activeCount.value : 0,
);
const timersRinging = computed(() =>
  hydrated.value ? floorTimers.ringingCount.value : 0,
);

// Receitas e Relatórios (só com o acesso) e o Letreiro: no celular, que não tem rail.
const { tools } = useProductionSections();

// A hora da última leitura útil: o ponto ao vivo mostra quando a tela leu pela última
// vez. Nasce no cliente (o SSR não sabe a hora local de quem lê).
const readClock = ref("");
function stamp() {
  readClock.value = new Date().toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}
watch(
  () => props.pending,
  (now, before) => {
    if (before && !now && !props.stale) stamp();
  },
);
const liveTone = computed(() => (props.stale ? "late" : "live"));
const liveLabel = computed(() =>
  props.stale ? "Sem atualizar" : "Ao vivo",
);

const SHORTCUT_ROUTES = {
  plan: "/plan",
  "mise-en-place": "/mise-en-place",
  open: "/",
  close: "/close",
  quality: "/quality",
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
    searchInput.value?.focus();
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
  stamp();
  window.addEventListener("keydown", onGlobalKeydown);
});
onBeforeUnmount(() => window.removeEventListener("keydown", onGlobalKeydown));

function refreshFromMenu() {
  // O ⋯ fica aberto: a hora ao lado do título mostra na hora se a leitura entrou.
  emit("refresh");
}

function openHelp() {
  menuOpen.value = false;
  shortcutsHelpOpen.value = true;
}

const counterText = computed(() => {
  if (props.count == null) return "";
  if (props.total != null) return `de ${props.total} ${props.countLabel}`.trim();
  return props.countLabel || "ativos";
});

const ITEM =
  "flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent";
</script>

<template>
  <OperatorPageHeader :title="title" :eyebrow="eyebrow">
    <template v-if="$slots.lead" #lead><slot name="lead" /></template>
    <template #status>
      <OperatorLiveStatus
        :tone="liveTone"
        :time="readClock"
        :label="liveLabel"
        :detail="stale ? 'A última leitura falhou: a tela mostra o que tinha.' : ''"
      />
    </template>
    <template v-if="searchable" #search>
      <OperatorSuiteSearch
        ref="searchInput"
        v-model="query"
        class="suite:md:w-[18rem]!"
        screen-label="filtrando a lista"
        :placeholder="searchPlaceholder"
        aria-label="Buscar por código, SKU ou receita"
      />
    </template>
    <template #phone-actions>
      <!-- Timers: contagem de ativos; o anel pulsa quando algum toca. LEVA à página. -->
      <NuxtLink
        to="/timers"
        class="relative grid size-12 place-items-center rounded-md"
        :class="timersRinging ? 'text-destructive' : 'text-foreground'"
        :aria-label="`Timers (${timersCount} ativos)`"
        title="Timers da bancada"
        data-header-timers
      >
        <Icon
          name="lucide:alarm-clock"
          class="size-6"
          :class="timersRinging ? 'animate-pulse motion-reduce:animate-none' : ''"
        />
        <span
          v-if="timersCount"
          class="absolute right-1 top-1 h-[18px] min-w-[18px] rounded-full px-[5px] text-xs font-bold leading-[18px] tabular-nums"
          :class="
            timersRinging
              ? 'bg-destructive text-destructive-foreground'
              : 'bg-suite-badge text-suite-badge-foreground'
          "
          >{{ timersCount }}</span
        >
      </NuxtLink>
      <AlertsBell placement="phone" />
    </template>
    <template #actions>
      <!-- O percentual mora COM o número que ele resume — nunca longe dele. -->
      <div
        v-if="count != null"
        class="flex items-center gap-3 pr-1 max-lg:hidden"
        data-header-progress
      >
        <p class="op-label whitespace-nowrap">
          <span class="op-title tnum">{{ count }}</span>
          <span class="text-muted-foreground">{{ ` ${counterText}` }}</span>
        </p>
        <div
          v-if="progress != null"
          class="h-2 w-24 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          :aria-valuenow="progress"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-label="`Progresso do dia: ${progress}%`"
        >
          <div
            class="h-full rounded-full bg-primary transition-all"
            :style="{ width: `${progress}%` }"
          />
        </div>
      </div>
      <slot name="actions" />
      <UiPopover v-model:open="menuOpen">
        <UiPopoverTrigger as-child>
          <button
            type="button"
            class="grid size-control shrink-0 place-items-center rounded-md border border-border bg-card text-foreground transition hover:bg-accent"
            aria-label="Mais: atualizar, timers e atalhos"
            title="Mais"
            data-header-menu
          >
            <Icon name="lucide:ellipsis" class="size-5" />
          </button>
        </UiPopoverTrigger>
        <UiPopoverContent
          align="end"
          :side-offset="6"
          :collision-padding="8"
          class="w-64 p-1.5"
        >
          <div role="menu" data-header-menu-panel>
            <!-- Tablet em pé e celular: o progresso do dia sai da linha e mora aqui. -->
            <p
              v-if="count != null"
              class="px-2.5 pt-1 pb-2 op-label lg:hidden"
              data-header-menu-progress
            >
              <span class="op-title tnum">{{ count }}</span>
              <span class="text-muted-foreground">{{ ` ${counterText}` }}</span>
            </p>
            <button
              type="button"
              role="menuitem"
              :class="ITEM"
              aria-label="Atualizar"
              aria-keyshortcuts="R"
              data-header-refresh
              @click="refreshFromMenu"
            >
              <Icon
                name="lucide:refresh-cw"
                class="size-4 text-muted-foreground"
                :class="pending ? 'motion-safe:animate-spin' : ''"
              />
              <span class="flex-1">Atualizar</span>
              <kbd
                class="hidden font-mono op-micro text-muted-foreground pointer-fine:inline"
                aria-hidden="true"
                >R</kbd
              >
            </button>
            <NuxtLink
              to="/timers"
              role="menuitem"
              :class="ITEM"
              @click="menuOpen = false"
            >
              <Icon name="lucide:alarm-clock" class="size-4 text-muted-foreground" />
              <span class="flex-1">Abrir timers</span>
              <span v-if="timersCount" class="op-micro tnum text-muted-foreground">{{
                timersCount
              }}</span>
            </NuxtLink>
            <slot name="menu" :close="() => (menuOpen = false)" />
            <div class="md:hidden">
              <NuxtLink
                v-for="tool in tools"
                :key="tool.key"
                :to="tool.to!"
                role="menuitem"
                :class="ITEM"
                @click="menuOpen = false"
              >
                <Icon :name="tool.icon" class="size-4 text-muted-foreground" />
                {{ tool.label }}
              </NuxtLink>
            </div>
            <div class="mt-1.5 border-t border-border pt-1.5">
              <button
                type="button"
                role="menuitem"
                :class="ITEM"
                aria-label="Ver atalhos do teclado"
                aria-keyshortcuts="?"
                @click="openHelp"
              >
                <Icon name="lucide:keyboard" class="size-4 text-muted-foreground" />
                <span class="flex-1">Atalhos desta tela</span>
                <kbd
                  class="hidden font-mono op-micro text-muted-foreground pointer-fine:inline"
                  aria-hidden="true"
                  >?</kbd
                >
              </button>
            </div>
          </div>
        </UiPopoverContent>
      </UiPopover>
    </template>
    <template v-if="$slots.filters" #filters><slot name="filters" /></template>
    <template v-if="$slots.below" #below><slot name="below" /></template>
  </OperatorPageHeader>

  <ProductionShortcutsHelp v-model:open="shortcutsHelpOpen" />
</template>
