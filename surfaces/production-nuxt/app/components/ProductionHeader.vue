<script setup lang="ts">
// Cabeçalho das telas da Produção: o `OperatorPageHeader` do kit, com os papéis das
// barras da fase 2 (WP-FASE2-UX-OPERADOR §5):
//   · barra primária: título, selo ao vivo com a hora da última leitura, a busca
//     (nível "Esta tela" declarado: filtra a lista da tela) e o ⋯ "Mais ações" (as
//     ações como DADOS: as da tela e Atualizar, tecla R). Avisos e o ciclo da barra
//     lateral são do kit;
//   · toolbar: o dia ou a vista (`#primary`, no começo da linha, também no celular), os recortes
//     (`#filters`, que no celular vão para o painel "Filtros") e, no fim, o progresso
//     do dia ("4 de 28 planejados" com a barra);
//   · aviso da tela: `alerts`, logo abaixo da toolbar.
// As etapas do lote (Alt+1 a Alt+5), "/" (busca) e "?" (ajuda) são do shell e da busca
// da suíte. Este cabeçalho só segura o R, e entrega à ajuda do kit os grupos de teclas
// da Produção.
import type { OperatorHeaderAction } from "../../../operator-kit/app/presentation/pageHeader";
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";
import {
  isEditableKeyboardTarget,
  PRODUCTION_SHORTCUT_GROUPS,
  PRODUCTION_SHORTCUTS_DESCRIPTION,
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
    /** Selo ao lado do título (ex.: o dia que a tela mostra). */
    eyebrow?: string;
    /** O que a tela diz em uma frase, ao lado do selo ao vivo ("lotes fechados hoje"). */
    subtitle?: string;
    searchPlaceholder?: string;
    /** O que a busca filtra nesta tela ("filtrando os lotes"). */
    searchLabel?: string;
    /** Telas sem lista própria (Ajustes, Relatórios) usam a busca da suíte, sem nível de tela. */
    searchable?: boolean;
    /** Ações da tela, antes de Atualizar, no ⋯ "Mais ações". */
    actions?: OperatorHeaderAction[];
    /** Recortes ativos (viram número no "Filtros" e chips no celular). */
    activeFilters?: { key: string; label: string; remove: () => void }[];
    alerts?: OperatorScreenAlert[];
  }>(),
  {
    count: undefined,
    countLabel: "",
    total: null,
    progress: null,
    pending: false,
    stale: false,
    eyebrow: "",
    subtitle: "",
    searchPlaceholder: "Buscar produto ou SKU",
    searchLabel: "filtrando a lista",
    searchable: true,
    actions: () => [],
    activeFilters: () => [],
    alerts: () => [],
  },
);
const emit = defineEmits<{ refresh: [] }>();
const query = defineModel<string>("query", { default: "" });

provideOperatorShortcuts(PRODUCTION_SHORTCUT_GROUPS, PRODUCTION_SHORTCUTS_DESCRIPTION);

// A hora da última leitura útil: o selo ao vivo mostra quando a tela leu pela última
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

const headerActions = computed<OperatorHeaderAction[]>(() => [
  ...props.actions,
  {
    label: "Atualizar",
    icon: "i-lucide-refresh-cw",
    kbds: ["R"],
    onSelect: () => emit("refresh"),
  },
]);

function onGlobalKeydown(event: KeyboardEvent) {
  if (event.repeat || event.isComposing || productionGlobalKeysBlocked()) return;
  if (resolveProductionGlobalShortcut(event) !== "refresh") return;
  if (isEditableKeyboardTarget(event.target)) return;
  event.preventDefault();
  emit("refresh");
}

onMounted(() => {
  stamp();
  window.addEventListener("keydown", onGlobalKeydown);
});
onBeforeUnmount(() => window.removeEventListener("keydown", onGlobalKeydown));

const counterText = computed(() => {
  if (props.count == null) return "";
  if (props.total != null) return `de ${props.total} ${props.countLabel}`.trim();
  return props.countLabel || "ativos";
});
</script>

<template>
  <OperatorPageHeader
    :title="title"
    :eyebrow="eyebrow"
    :actions="headerActions"
    actions-label="Mais ações da tela"
    :active-filters="activeFilters"
    :alerts="alerts"
  >
    <template v-if="$slots.lead" #lead><slot name="lead" /></template>
    <template #status>
      <OperatorLiveStatus
        :tone="stale ? 'late' : 'live'"
        :time="readClock"
        :label="stale ? 'Sem atualizar' : 'Ao vivo'"
        :detail="stale ? 'A última leitura falhou: a tela mostra o que tinha.' : ''"
      />
      <span
        v-if="subtitle"
        class="min-w-0 text-xs text-muted-foreground"
        data-header-subtitle
      >{{ subtitle }}</span>
    </template>
    <template v-if="searchable" #search>
      <OperatorSuiteSearch
        v-model="query"
        :screen-label="searchLabel"
        :placeholder="searchPlaceholder"
        aria-label="Buscar por código, SKU ou receita"
      />
    </template>
    <template v-if="$slots.primary" #filters-primary><slot name="primary" /></template>
    <template v-if="$slots.filters" #filters><slot name="filters" /></template>
    <template v-if="count != null" #filters-end>
      <!-- O percentual mora COM o número que ele resume, nunca longe dele. -->
      <div class="flex items-center gap-3" data-header-progress>
        <p class="whitespace-nowrap text-sm">
          <span class="font-semibold tabular-nums">{{ count }}</span>
          <span class="text-muted-foreground">{{ ` ${counterText}` }}</span>
        </p>
        <NuxtProgress
          v-if="progress != null"
          :model-value="progress"
          class="w-24 max-sm:hidden"
          size="sm"
          :aria-label="`Progresso do dia: ${progress}%`"
        />
      </div>
    </template>
    <template v-if="$slots.below" #below><slot name="below" /></template>
  </OperatorPageHeader>
</template>
