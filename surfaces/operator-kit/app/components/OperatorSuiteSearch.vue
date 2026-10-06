<script setup lang="ts">
// A busca da suíte (SUITE-UX-V2 §2.2 e FUNCTION §7; prévias v3 `depois-gestor-busca`,
// `depois-hub-celular`, `fontes/search-overlay.part` e o campo do cabeçalho das v4).
//
// Um campo só, uma tecla só (`/` fora de campo, Ctrl K em qualquer lugar). Ao digitar,
// FILTRA A TELA (o `v-model`, quando a tela tem filtro próprio: o quadro do Gestor, a
// matriz da Produção) e abre o painel com o alcance em controle segmentado: Esta tela ·
// <App> · Toda a suíte (Tab troca). Os resultados vêm agrupados por tipo, cada um com o
// selo do app de destino e o caminho ("Gestor › Clientes"); Enter abre, ↑↓ anda, Esc fecha
// e MANTÉM o filtro. No celular, a mesma busca em tela cheia, pedida pela lupa da barra de
// 56px (`OperatorPageHeader`) ou pelo campo da Central, com a câmera para ler um código.
//
// Variantes:
//   - `header` (padrão): o campo de 22rem do cabeçalho de toda tela (tablet e desktop);
//   - `hero`: a barra grande da Central (34rem, "/" e Ctrl K impressos); no celular vira o
//     campo "Buscar em toda a suíte" que abre a tela cheia;
//   - `hotkey`: sem campo na tela (a Venda e as Encomendas do PDV, cujo campo e cuja
//     tecla `/` são do produto e do "cliente veio buscar"): Ctrl K (e a lupa do celular)
//     abre a busca da suíte num diálogo.
//
// Teclas impressas só com ponteiro fino (SPEC4 §7: tablet sem teclas impressas).
import { onClickOutside, useMediaQuery } from "@vueuse/core";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from "vue";

import { OPERATOR_APPS, type OperatorAppRef } from "../../appIdentity";

import {
  SUITE_SEARCH_COPY as COPY,
  appCount,
  flattenGroups,
  groupsForScope,
  groupsForType,
  highlightParts,
  nextSuiteScope,
  suiteEmptyCopy,
  suiteQueryReady,
  suiteResultColor,
  suiteResultLabel,
  suiteScopes,
  suiteTotal,
  surfaceRefForKitApp,
  type SuiteSearchResult,
  type SuiteSearchScope,
} from "../presentation/suiteSearch";
import { SUITE_SEARCH_SHORTCUTS } from "../shortcuts/suiteShortcuts";

const props = withDefaults(
  defineProps<{
    /** O filtro desta tela. Sem `v-model`, a tela não filtra e não há o alcance "Esta tela". */
    modelValue?: string;
    placeholder?: string;
    /** O que o filtro desta tela faz ("filtrando o quadro"), escrito no painel. */
    screenLabel?: string;
    /** Quantos itens a tela mostra com o filtro (o número ao lado de "Esta tela"). */
    screenCount?: number | null;
    variant?: "header" | "hero" | "hotkey";
    ariaLabel?: string;
  }>(),
  {
    modelValue: undefined,
    placeholder: "Buscar",
    screenLabel: "",
    screenCount: null,
    variant: "header",
    ariaLabel: "",
  },
);
const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const config = useRuntimeConfig().public as {
  operatorPwa?: { app?: string; identity?: { label?: string } };
};
const appRef = surfaceRefForKitApp(config.operatorPwa?.app);
const hasScreen = computed(() => props.modelValue !== undefined);
const label = computed(() => props.ariaLabel || props.placeholder);

const text = ref(props.modelValue ?? "");
watch(
  () => props.modelValue,
  (value) => {
    if (value !== undefined && value !== text.value) text.value = value;
  },
);

const isPhone = useMediaQuery("(max-width: 767.98px)");
const panelOpen = ref(false);
const dialogOpen = ref(false);
const useDialog = computed(() => props.variant === "hotkey" || isPhone.value);
const searching = computed(() => panelOpen.value || dialogOpen.value);

const scopes = computed(() => suiteScopes({ hasScreen: hasScreen.value, appRef }));
const scope = ref<SuiteSearchScope>(scopes.value[0]!);
watch(scopes, (next) => {
  if (!next.includes(scope.value)) scope.value = next[0]!;
});
const typeFilter = ref("");

const { groups, apps, status, retry } = useSuiteSearchResults(text, searching);
const kitIdentity = OPERATOR_APPS[config.operatorPwa?.app as OperatorAppRef];
const appLabel = computed(
  () => apps.value.find((app) => app.ref === appRef)?.label || kitIdentity?.shortLabel || kitIdentity?.label || "App",
);
const ready = computed(() => suiteQueryReady(text.value));
const scopedGroups = computed(() => groupsForScope(groups.value, scope.value, appRef));
const visibleGroups = computed(() => groupsForType(scopedGroups.value, typeFilter.value));
const flat = computed(() => flattenGroups(visibleGroups.value));
const counts = computed<Record<SuiteSearchScope, number | null>>(() => ({
  screen: props.screenCount,
  // O número só aparece quando a leitura respondeu: "0" enquanto busca seria mentira.
  app: ready.value && status.value === "ready" ? appCount(apps.value, appRef) : null,
  suite: ready.value && status.value === "ready" ? suiteTotal(groups.value) : null,
}));
function scopeLabel(value: SuiteSearchScope): string {
  if (value === "screen") return COPY.screenScope;
  if (value === "app") return appLabel.value;
  return COPY.suiteScope;
}

const active = ref(-1);
watch([flat, scope, typeFilter], () => {
  active.value = -1;
});

// `useId`: o mesmo id no servidor e no navegador (um aleatório descasava a hidratação).
const uid = `suite-search-${useId()}`;
const listId = `${uid}-list`;
const optionId = (index: number) => `${uid}-opt-${index}`;
const activeId = computed(() => (active.value >= 0 ? optionId(active.value) : undefined));

const root = ref<HTMLElement | null>(null);
const input = ref<HTMLInputElement | null>(null);
const dialogInput = ref<HTMLInputElement | null>(null);

function setText(value: string) {
  text.value = value;
  if (hasScreen.value) emit("update:modelValue", value);
}
function onInput(event: Event) {
  setText((event.target as HTMLInputElement).value);
  if (!useDialog.value) panelOpen.value = true;
}
function clear() {
  setText("");
  (dialogOpen.value ? dialogInput : input).value?.focus();
}

function openSearch() {
  if (useDialog.value) {
    dialogOpen.value = true;
    void nextTick(() => dialogInput.value?.focus());
    return;
  }
  panelOpen.value = true;
  input.value?.focus();
  input.value?.select();
}
function closePanel() {
  panelOpen.value = false;
}
function closeDialog() {
  dialogOpen.value = false;
  stopCamera();
}

onClickOutside(root, () => {
  if (panelOpen.value) closePanel();
});

function linkFor(result: SuiteSearchResult) {
  return appLink.attrsFor(result.url);
}
const appLink = useOperatorAppLink();

function openActive(): boolean {
  if (active.value < 0) return false;
  const link = document.getElementById(optionId(active.value)) as HTMLAnchorElement | null;
  link?.click();
  return Boolean(link);
}

function onKeydown(event: KeyboardEvent) {
  const total = flat.value.length;
  if (event.key === "ArrowDown") {
    event.preventDefault();
    if (!searching.value) openSearch();
    if (total) active.value = (active.value + 1) % total;
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    if (total) active.value = active.value <= 0 ? total - 1 : active.value - 1;
  } else if (event.key === "Enter") {
    event.preventDefault();
    if (!openActive() && hasScreen.value) {
      // Enter sem resultado escolhido: fica o filtro da tela (o que se queria 9 em 10 vezes).
      closePanel();
      closeDialog();
    }
  } else if (event.key === "Tab" && searching.value && scopes.value.length > 1) {
    event.preventDefault();
    scope.value = nextSuiteScope(scopes.value, scope.value, event.shiftKey);
  } else if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    if (dialogOpen.value) closeDialog();
    else if (panelOpen.value) closePanel();
    else input.value?.blur();
  }
}

// Resultado do próprio app abre pelo roteador (sem recarregar a página); de outro app,
// pelo link, que já sabe abrir na janela do app de destino quando instalado.
function afterOpen(event: MouseEvent, result: SuiteSearchResult) {
  closePanel();
  closeDialog();
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button > 0) return;
  const target = new URL(result.url, window.location.href);
  if (target.origin !== window.location.origin) return;
  event.preventDefault();
  void navigateTo(`${target.pathname}${target.search}${target.hash}`);
}

// Teclas da tela inteira e o pedido da lupa: só a busca dona atende.
const { isOwner } = useSuiteSearchOwnership();
const searchCommands = props.variant === "hotkey"
  ? SUITE_SEARCH_SHORTCUTS.filter((command) => command.id !== "suite.search.slash")
  : SUITE_SEARCH_SHORTCUTS;
const shortcutContexts = computed<ReadonlySet<string>>(() => new Set(["ready"]));
useOperatorShortcutMap(
  searchCommands,
  Object.fromEntries(searchCommands.map((command) => [command.id, () => {
    if (isOwner()) openSearch();
  }])),
  shortcutContexts,
);
const { requests } = useSuiteSearchRequest();
watch(requests, () => {
  if (isOwner()) openSearch();
});
onBeforeUnmount(() => {
  stopCamera();
  unlockScroll();
});

// Tela cheia: a página de baixo não rola junto.
let previousOverflow: string | null = null;
function lockScroll() {
  previousOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
}
function unlockScroll() {
  if (previousOverflow === null) return;
  document.body.style.overflow = previousOverflow;
  previousOverflow = null;
}
watch(dialogOpen, (open) => {
  if (open) lockScroll();
  else unlockScroll();
});

// Câmera (celular): lê QR, EAN ou a chave da NF e põe o que leu no campo.
type Detector = { detect: (source: HTMLVideoElement) => Promise<Array<{ rawValue: string }>> };
const cameraSupported = ref(false);
const cameraOpen = ref(false);
const cameraError = ref("");
const cameraStarting = ref(false);
const video = ref<HTMLVideoElement | null>(null);
let stream: MediaStream | null = null;
let scanTimer: ReturnType<typeof setTimeout> | null = null;
onMounted(() => {
  cameraSupported.value = "BarcodeDetector" in window && Boolean(navigator.mediaDevices?.getUserMedia);
});
async function startCamera() {
  cameraError.value = "";
  cameraOpen.value = true;
  cameraStarting.value = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    await nextTick();
    if (!video.value) return;
    video.value.srcObject = stream;
    await video.value.play();
    const DetectorClass = (window as unknown as { BarcodeDetector: new () => Detector }).BarcodeDetector;
    const detector = new DetectorClass();
    const scan = async () => {
      if (!cameraOpen.value || !video.value) return;
      try {
        const [code] = await detector.detect(video.value);
        if (code?.rawValue) {
          navigator.vibrate?.(40);
          setText(code.rawValue.trim());
          stopCamera();
          return;
        }
      } catch {
        // quadro sem código: segue lendo
      }
      scanTimer = setTimeout(() => void scan(), 250);
    };
    void scan();
  } catch {
    cameraError.value = COPY.cameraUnavailable;
    stopCamera();
  } finally {
    cameraStarting.value = false;
  }
}
function stopCamera(close = true) {
  if (scanTimer) clearTimeout(scanTimer);
  scanTimer = null;
  for (const track of stream?.getTracks() ?? []) track.stop();
  stream = null;
  if (close) cameraOpen.value = false;
}

const emptyCopy = computed(() => suiteEmptyCopy(text.value, scope.value, appLabel.value));
const typeChips = computed(() =>
  scopedGroups.value.map((group) => ({ type: group.type, label: group.label, count: group.results.length })),
);

defineExpose({ focus: () => openSearch(), open: openSearch });
</script>

<template>
  <div
    ref="root"
    class="relative"
    :class="variant === 'hero' ? 'w-full md:w-[34rem]' : variant === 'hotkey' ? 'contents' : 'w-full md:w-[22rem]'"
    data-suite-search
    :data-suite-search-variant="variant"
  >
    <!-- O campo (tablet e desktop). No celular a busca é a tela cheia. -->
    <div v-if="variant !== 'hotkey'" class="relative" :class="variant === 'hero' ? 'hidden md:block' : ''">
      <Icon
        name="lucide:search"
        class="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
        :class="variant === 'hero' ? 'left-4 size-5 text-muted-foreground' : 'text-muted-foreground'"
        aria-hidden="true"
      />
      <input
        ref="input"
        :value="text"
        type="search"
        inputmode="search"
        role="combobox"
        autocomplete="off"
        spellcheck="false"
        :placeholder="placeholder"
        :aria-label="label"
        aria-autocomplete="list"
        :aria-expanded="panelOpen"
        :aria-controls="listId"
        :aria-activedescendant="panelOpen ? activeId : undefined"
        aria-keyshortcuts="/ Control+K"
        class="w-full rounded-md border border-input bg-card text-[15px] outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring [&::-webkit-search-cancel-button]:appearance-none"
        :class="variant === 'hero' ? 'h-12 rounded-lg pr-36 pl-12 text-base' : 'h-control pr-12 pl-9'"
        data-suite-search-input
        @input="onInput"
        @focus="ready && !useDialog && (panelOpen = true)"
        @keydown="onKeydown"
      >
      <span
        v-if="!text"
        class="pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 items-center gap-1.5 pointer-fine:flex"
        aria-hidden="true"
        data-search-shortcut
      >
        <kbd class="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">/</kbd>
        <kbd v-if="variant === 'hero'" class="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">Ctrl K</kbd>
      </span>
      <button
        v-if="text"
        type="button"
        class="absolute top-1/2 right-0 grid size-control -translate-y-1/2 place-items-center rounded text-muted-foreground transition hover:text-foreground"
        :aria-label="COPY.clear"
        data-suite-search-clear
        @click="clear"
      >
        <Icon name="lucide:x" class="size-4" />
      </button>
    </div>

    <!-- Central no celular: o campo que abre a tela cheia (com a câmera ao lado). -->
    <button
      v-if="variant === 'hero'"
      type="button"
      class="flex h-12 w-full items-center gap-3 rounded-lg border border-input bg-card pr-1 pl-4 text-left text-[15px] text-muted-foreground md:hidden"
      :aria-label="label"
      data-suite-search-phone-trigger
      @click="openSearch"
    >
      <Icon name="lucide:search" class="size-5" aria-hidden="true" />
      <span class="min-w-0 flex-1 truncate">{{ text || "Buscar em toda a suíte" }}</span>
      <span class="h-6 w-px bg-border" aria-hidden="true" />
      <span class="grid size-10 place-items-center text-foreground" aria-hidden="true">
        <Icon name="lucide:scan-line" class="size-5" />
      </span>
    </button>

    <!-- Painel (tablet e desktop): alcance, resultados por tipo, teclas. -->
    <div
      v-if="panelOpen && !useDialog"
      class="absolute top-full left-0 z-50 mt-2 overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl"
      :class="variant === 'hero' ? 'w-full' : 'w-[min(37.5rem,calc(100vw-2rem))]'"
      data-suite-search-panel
    >
      <div class="flex items-center gap-2 border-b border-border px-3 pt-3 pb-2">
        <div class="inline-flex h-9 items-center gap-1 rounded-md bg-secondary p-1" role="radiogroup" aria-label="Alcance da busca">
          <button
            v-for="value in scopes"
            :key="value"
            type="button"
            role="radio"
            :aria-checked="scope === value"
            tabindex="-1"
            class="inline-flex h-full items-center gap-1.5 rounded px-2.5 op-label"
            :class="scope === value ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground'"
            :data-suite-search-scope="value"
            @mousedown.prevent
            @click="scope = value"
          >
            {{ scopeLabel(value) }}
            <span v-if="counts[value] !== null" class="tnum" :class="scope === value ? 'text-muted-foreground' : ''">{{ counts[value] }}</span>
          </button>
        </div>
        <span v-if="scopes.length > 1" class="ml-auto hidden op-micro text-muted-foreground pointer-fine:inline">{{ COPY.tabHint }}</span>
      </div>

      <div class="max-h-[min(28rem,60vh)] overflow-y-auto pb-2">
        <template v-if="scope === 'screen'">
          <p class="px-4 pt-3 pb-1 op-eyebrow text-muted-foreground">
            {{ COPY.screenSection }}<template v-if="screenLabel"> · {{ screenLabel }}</template>
          </p>
          <p class="px-4 pb-1 op-body text-muted-foreground" data-suite-search-screen-line>
            <template v-if="!text">A tela filtra enquanto você digita.</template>
            <template v-else-if="screenCount === null">A tela está filtrada por “{{ text.trim() }}”. Esc fecha e mantém o filtro.</template>
            <template v-else-if="screenCount === 0">Nada nesta tela com “{{ text.trim() }}”.</template>
            <template v-else>{{ screenCount === 1 ? "1 na tela" : `${screenCount} na tela` }} com “{{ text.trim() }}”. Enter fica no filtro.</template>
          </p>
          <p v-if="ready" class="px-4 pt-3 pb-1 op-eyebrow text-muted-foreground">{{ COPY.suiteSection }}</p>
        </template>

        <p v-if="!ready" class="px-4 py-3 op-body text-muted-foreground" data-suite-search-hint>{{ COPY.typeMore }}</p>
        <p v-else-if="status === 'error'" class="flex flex-wrap items-center gap-2 px-4 py-3 op-body text-muted-foreground" role="alert" data-suite-search-error>
          {{ hasScreen ? COPY.failed : COPY.failedNoScreen }}
          <button type="button" class="font-semibold text-foreground underline" @click="retry">{{ COPY.retry }}</button>
        </p>
        <p v-else-if="status === 'loading' && !flat.length" class="px-4 py-3 op-body text-muted-foreground" role="status">{{ COPY.searching }}</p>
        <p v-else-if="status === 'ready' && !flat.length" class="px-4 py-3 op-body text-muted-foreground" role="status" data-suite-search-empty>{{ emptyCopy }}</p>

        <div :id="listId" role="listbox" :aria-label="label">
          <template v-for="group in visibleGroups" :key="group.type">
            <p v-if="scope !== 'screen' || visibleGroups.length > 1" class="px-4 pt-3 pb-1 op-eyebrow text-muted-foreground" role="presentation" data-suite-search-group>{{ group.label }}</p>
            <div class="px-2" role="group" :aria-label="group.label">
              <a
                v-for="result in group.results"
                :id="optionId(flat.indexOf(result))"
                :key="result.key"
                :href="result.url"
                :target="linkFor(result).target"
                :rel="linkFor(result).rel"
                role="option"
                :aria-selected="active === flat.indexOf(result)"
                :aria-label="suiteResultLabel(result)"
                class="flex min-h-12 items-center gap-3 rounded-md px-2 py-1.5"
                :class="active === flat.indexOf(result) ? 'bg-accent' : 'hover:bg-accent/60'"
                data-suite-search-result
                :data-type="result.type"
                @mousemove="active = flat.indexOf(result)"
                @click="afterOpen($event, result)"
              >
                <span
                  class="grid size-8 shrink-0 place-items-center rounded-md text-white"
                  :style="{ background: suiteResultColor(result.app) || 'var(--muted-foreground)' }"
                  aria-hidden="true"
                >
                  <Icon :name="`lucide:${result.icon}`" class="size-4" />
                </span>
                <span class="min-w-0 flex-1">
                  <span class="block op-label font-semibold"><!-- numa linha só: espaço entre os trechos partiria a palavra marcada --><template v-for="(part, i) in highlightParts(result.title, text)" :key="i"><mark v-if="part.match" class="rounded-sm bg-primary/20 text-foreground">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span>
                  <span class="block op-micro text-muted-foreground">{{ [result.place, result.detail].filter(Boolean).join(" · ") }}</span>
                </span>
                <kbd v-if="active === flat.indexOf(result)" class="hidden font-mono op-micro text-muted-foreground pointer-fine:inline" aria-hidden="true">Enter</kbd>
              </a>
            </div>
          </template>
        </div>
      </div>

      <div class="hidden h-10 items-center gap-4 border-t border-border bg-muted/50 px-4 op-micro text-muted-foreground pointer-fine:flex" aria-hidden="true">
        <span><kbd class="font-mono">↑↓</kbd> navegar</span>
        <span><kbd class="font-mono">Enter</kbd> abrir</span>
        <span v-if="scopes.length > 1"><kbd class="font-mono">Tab</kbd> alcance</span>
        <span><kbd class="font-mono">Esc</kbd> {{ hasScreen ? "fechar e manter o filtro" : "fechar" }}</span>
      </div>
    </div>

    <!-- Tela cheia (celular) ou diálogo (Ctrl K na Venda do PDV). -->
    <Teleport to="body">
      <div
        v-if="dialogOpen"
        class="fixed inset-0 z-[70] flex flex-col bg-background text-foreground"
        :class="isPhone ? '' : 'items-center bg-foreground/20 px-4 pt-[10vh]'"
        role="dialog"
        aria-modal="true"
        :aria-label="label"
        data-suite-search-dialog
        @click.self="closeDialog"
      >
        <div class="flex min-h-0 w-full flex-1 flex-col bg-background" :class="isPhone ? '' : 'max-h-[75vh] max-w-[40rem] flex-none overflow-hidden rounded-xl border border-border shadow-2xl'">
          <div class="flex items-center gap-2 px-2 pt-[max(env(safe-area-inset-top),0.5rem)] pb-2">
            <button type="button" class="grid size-12 shrink-0 place-items-center rounded-md" :aria-label="COPY.close" data-suite-search-dialog-close @click="closeDialog">
              <Icon name="lucide:arrow-left" class="size-6" />
            </button>
            <div class="relative flex min-w-0 flex-1 items-center rounded-lg border-2 border-ring bg-card">
              <input
                ref="dialogInput"
                :value="text"
                type="search"
                inputmode="search"
                role="combobox"
                autocomplete="off"
                spellcheck="false"
                :placeholder="isPhone ? 'Buscar em toda a suíte' : placeholder"
                :aria-label="label"
                aria-autocomplete="list"
                aria-expanded="true"
                :aria-controls="`${listId}-dialog`"
                class="h-12 min-w-0 flex-1 bg-transparent pl-3 text-base outline-none [&::-webkit-search-cancel-button]:appearance-none"
                data-suite-search-dialog-input
                @input="onInput"
                @keydown="onKeydown"
              >
              <button v-if="text" type="button" class="grid size-11 shrink-0 place-items-center text-muted-foreground" :aria-label="COPY.clear" @click="clear">
                <Icon name="lucide:x" class="size-5" />
              </button>
              <button
                v-if="cameraSupported"
                type="button"
                class="m-1 grid size-10 shrink-0 place-items-center rounded-md bg-primary text-primary-foreground"
                :aria-label="COPY.camera"
                data-suite-search-camera
                :aria-busy="cameraStarting"
                @click="cameraOpen ? stopCamera() : startCamera()"
              >
                <Icon name="lucide:scan-line" class="size-5" />
              </button>
            </div>
          </div>

          <!-- Alcance e tipo, em chips que rolam na horizontal. -->
          <div class="flex items-center gap-2 overflow-x-auto px-4 pb-3 no-scrollbar *:shrink-0" data-suite-search-chips>
            <button
              v-for="value in scopes"
              :key="value"
              type="button"
              class="inline-flex h-10 items-center gap-1.5 rounded-full border px-3.5 op-label"
              :class="scope === value && !typeFilter ? 'border-foreground/60 bg-accent font-semibold' : 'border-border bg-card'"
              :aria-pressed="scope === value && !typeFilter"
              :data-suite-search-scope="value"
              @click="scope = value; typeFilter = ''"
            >
              <Icon v-if="scope === value && !typeFilter" name="lucide:check" class="size-4" aria-hidden="true" />
              {{ scopeLabel(value) }}
              <span v-if="counts[value] !== null" class="tnum text-muted-foreground">{{ counts[value] }}</span>
            </button>
            <button
              v-for="chip in typeChips"
              :key="chip.type"
              type="button"
              class="inline-flex h-10 items-center gap-1.5 rounded-full border px-3.5 op-label"
              :class="typeFilter === chip.type ? 'border-foreground/60 bg-accent font-semibold' : 'border-border bg-card'"
              :aria-pressed="typeFilter === chip.type"
              :data-suite-search-type="chip.type"
              @click="typeFilter = typeFilter === chip.type ? '' : chip.type"
            >
              {{ chip.label }} <span class="tnum text-muted-foreground">{{ chip.count }}</span>
            </button>
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto border-t border-border pb-[max(env(safe-area-inset-bottom),1rem)]">
            <div v-if="cameraOpen" class="grid gap-2 p-4" data-suite-search-camera-view>
              <video ref="video" class="aspect-[4/3] w-full rounded-xl bg-black object-cover" muted playsinline />
              <p class="op-micro text-muted-foreground">{{ COPY.cameraAim }}</p>
              <button type="button" class="h-12 rounded-lg border border-border bg-card op-label font-semibold" @click="stopCamera()">{{ COPY.cameraClose }}</button>
            </div>
            <p v-if="cameraError" class="px-4 pt-3 op-body text-warning" role="alert">{{ cameraError }}</p>

            <button
              v-if="cameraSupported && !cameraOpen && !text"
              type="button"
              class="mx-4 mt-3 flex w-[calc(100%-2rem)] items-center gap-3 rounded-xl bg-accent px-4 py-3 text-left"
              data-suite-search-camera-row
              :aria-busy="cameraStarting"
              @click="startCamera"
            >
              <span class="grid size-10 place-items-center rounded-lg bg-card" aria-hidden="true"><Icon name="lucide:scan-barcode" class="size-5" /></span>
              <span class="min-w-0 flex-1">
                <span class="block op-label font-semibold">{{ COPY.camera }}</span>
                <span class="block op-micro text-muted-foreground">{{ COPY.cameraHint }}</span>
              </span>
              <Icon name="lucide:chevron-right" class="size-5 text-muted-foreground" aria-hidden="true" />
            </button>

            <p v-if="scope === 'screen' && text" class="px-4 pt-3 op-body text-muted-foreground" data-suite-search-screen-line>
              <template v-if="screenCount === null">A tela está filtrada por “{{ text.trim() }}”.</template>
              <template v-else>{{ screenCount === 1 ? "1 na tela" : `${screenCount} na tela` }} com “{{ text.trim() }}”.</template>
              <button type="button" class="ml-1 font-semibold text-foreground underline" @click="closeDialog">Ver na tela</button>
            </p>

            <p v-if="!ready && !cameraOpen" class="px-4 py-3 op-body text-muted-foreground" data-suite-search-hint>{{ COPY.typeMore }}</p>
            <p v-else-if="ready && status === 'error'" class="flex flex-wrap items-center gap-2 px-4 py-3 op-body text-muted-foreground" role="alert">
              {{ hasScreen ? COPY.failed : COPY.failedNoScreen }}
              <button type="button" class="font-semibold text-foreground underline" @click="retry">{{ COPY.retry }}</button>
            </p>
            <p v-else-if="ready && status === 'loading' && !flat.length" class="px-4 py-3 op-body text-muted-foreground" role="status">{{ COPY.searching }}</p>
            <p v-else-if="ready && status === 'ready' && !flat.length" class="px-4 py-3 op-body text-muted-foreground" role="status" data-suite-search-empty>{{ emptyCopy }}</p>

            <div :id="`${listId}-dialog`" role="listbox" :aria-label="label">
              <template v-for="group in visibleGroups" :key="group.type">
                <p class="px-4 pt-4 pb-1 op-eyebrow text-muted-foreground" role="presentation" data-suite-search-group>{{ group.label }}</p>
                <a
                  v-for="result in group.results"
                  :id="optionId(flat.indexOf(result))"
                  :key="result.key"
                  :href="result.url"
                  :target="linkFor(result).target"
                  :rel="linkFor(result).rel"
                  role="option"
                  :aria-selected="active === flat.indexOf(result)"
                  :aria-label="suiteResultLabel(result)"
                  class="flex min-h-14 items-center gap-3 px-4 py-2"
                  :class="active === flat.indexOf(result) ? 'bg-accent' : ''"
                  data-suite-search-result
                  :data-type="result.type"
                  @click="afterOpen($event, result)"
                >
                  <span
                    class="grid size-10 shrink-0 place-items-center rounded-lg text-white"
                    :style="{ background: suiteResultColor(result.app) || 'var(--muted-foreground)' }"
                    aria-hidden="true"
                  >
                    <Icon :name="`lucide:${result.icon}`" class="size-5" />
                  </span>
                  <span class="min-w-0 flex-1">
                    <span class="block op-label font-semibold"><!-- numa linha só: espaço entre os trechos partiria a palavra marcada --><template v-for="(part, i) in highlightParts(result.title, text)" :key="i"><mark v-if="part.match" class="rounded-sm bg-primary/20 text-foreground">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span>
                    <span class="block op-micro text-muted-foreground">{{ [result.place, result.detail].filter(Boolean).join(" · ") }}</span>
                  </span>
                  <Icon name="lucide:chevron-right" class="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                </a>
              </template>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
