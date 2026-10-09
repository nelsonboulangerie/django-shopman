<script setup lang="ts">
// Busca da suíte em níveis (WP-FASE2-UX-OPERADOR, K6; dono, 09/10/2026: "busca em
// níveis no canônico"). O botão é o `NuxtDashboardSearchButton` e o painel é o
// `NuxtDashboardSearch` oficial (o `Modal` + `CommandPalette` do Nuxt UI): teclado,
// grupos e tela cheia no celular vêm dele. Esta peça só diz O QUE aparece:
//
//   1. Nesta tela: "Filtrar o histórico por “maria”" vira o recorte da tela (o
//      `v-model`); com a tela já filtrada, "Tirar o filtro “maria”".
//   2. No app: o que a suíte achou no app atual.
//   3. Na suíte: o que achou nos outros apps.
//
// Os grupos ficam nesta ordem sempre (`preserve-group-order`). Digitar não mexe na tela:
// o recorte entra quando a pessoa escolhe "Filtrar … por …", e Esc fecha sem mudar nada.
// Teclas: `/` fora de campo e Ctrl K (⌘K) em qualquer lugar abrem, pela infraestrutura de
// atalhos do kit (`SUITE_SEARCH_SHORTCUTS`); o atalho próprio do `DashboardSearch` fica
// desligado para não abrir duas vezes.
import { useScreen } from "../composables/useScreen";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { OPERATOR_APPS, type OperatorAppRef } from "../../appIdentity";
import {
  SUITE_SEARCH_COPY as COPY,
  normalizeSuiteQuery,
  suiteEmptyCopy,
  suiteLevels,
  suiteQueryReady,
  suiteResultLabel,
  suiteScreenTarget,
  surfaceRefForKitApp,
  type SuiteSearchResult,
} from "../presentation/suiteSearch";
import { SUITE_SEARCH_SHORTCUTS } from "../shortcuts/suiteShortcuts";

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    placeholder?: string;
    screenLabel?: string;
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

const { belowMd: isPhone } = useScreen();
const dialogOpen = ref(false);
// O termo do painel é do painel: a tela só muda quando a pessoa escolhe o recorte.
const term = ref(props.modelValue ?? "");

const { groups, apps, status, retry } = useSuiteSearchResults(
  term,
  computed(() => dialogOpen.value),
);
const kitIdentity = OPERATOR_APPS[config.operatorPwa?.app as OperatorAppRef];
const appLabel = computed(
  () =>
    apps.value.find((app) => app.ref === appRef)?.label ||
    kitIdentity?.shortLabel ||
    kitIdentity?.label ||
    "App",
);
const ready = computed(() => suiteQueryReady(term.value));

function applyScreen(value: string) {
  if (hasScreen.value) emit("update:modelValue", value);
}
function openSearch() {
  term.value = props.modelValue ?? "";
  dialogOpen.value = true;
}
function closeDialog() {
  dialogOpen.value = false;
  stopCamera();
}

const appLink = useOperatorAppLink();
function linkFor(result: SuiteSearchResult) {
  return appLink.attrsFor(result.url);
}

const { isOwner } = useSuiteSearchOwnership();
const searchCommands =
  props.variant === "hotkey"
    ? SUITE_SEARCH_SHORTCUTS.filter((command) => command.id !== "suite.search.slash")
    : SUITE_SEARCH_SHORTCUTS;
useOperatorShortcutMap(
  searchCommands,
  Object.fromEntries(
    searchCommands.map((command) => [
      command.id,
      () => {
        if (isOwner()) openSearch();
      },
    ]),
  ),
  computed<ReadonlySet<string>>(() => new Set(["ready"])),
);
const { requests } = useSuiteSearchRequest();
watch(requests, () => {
  if (isOwner()) openSearch();
});

// A captura de código é a única exceção de baixo nível: o navegador expõe o vídeo,
// mas todos os controles ao redor dele continuam sendo Nuxt UI.
type Detector = {
  detect: (source: HTMLVideoElement) => Promise<Array<{ rawValue: string }>>;
};
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
          term.value = code.rawValue.trim();
          stopCamera();
          return;
        }
      } catch {
        // Um quadro sem código é normal; a leitura continua.
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
onBeforeUnmount(stopCamera);

const keepOpen = (fn: () => void) => (event: Event) => {
  event.preventDefault();
  fn();
};

// Os três níveis, em ordem fixa. O estado da suíte (falta letra, buscando, falhou,
// nada) mora como item desligado no fim, para não sumir atrás do recorte da tela.
const levelGroups = computed(() => {
  const typed = normalizeSuiteQuery(term.value);
  const out: Record<string, unknown>[] = [];

  if (hasScreen.value) {
    const target = suiteScreenTarget(props.screenLabel);
    const items: Record<string, unknown>[] = [];
    if (typed)
      items.push({
        label: `Filtrar ${target} por “${typed}”`,
        icon: "i-lucide-list-filter",
        "data-suite-search-screen": "apply",
        onSelect: () => {
          applyScreen(typed);
          closeDialog();
        },
      });
    if (props.modelValue)
      items.push({
        label: `Tirar o filtro “${props.modelValue}” de ${target}`,
        icon: "i-lucide-filter-x",
        "data-suite-search-screen": "clear",
        onSelect: () => {
          applyScreen("");
          closeDialog();
        },
      });
    if (items.length) out.push({ id: "screen", label: COPY.screenSection, ignoreFilter: true, items });
  }

  const levels = suiteLevels(groups.value, appRef);
  const resultItem = (result: SuiteSearchResult, typeLabel: string) => ({
    id: result.key,
    label: result.title,
    description: [result.place, result.detail].filter(Boolean).join(" · "),
    suffix: typeLabel,
    icon: `i-lucide-${result.icon}`,
    to: result.url,
    target: linkFor(result).target,
    rel: linkFor(result).rel,
    "aria-label": suiteResultLabel(result),
    "data-suite-search-result": "",
    "data-type": result.type,
    onSelect: () => closeDialog(),
  });
  if (appRef && levels.app.length)
    out.push({
      id: "app",
      label: `${COPY.appSection} (${appLabel.value})`,
      ignoreFilter: true,
      items: levels.app.map(({ result, typeLabel }) => resultItem(result, typeLabel)),
    });

  const state: Record<string, unknown>[] = [];
  if (!ready.value) state.push({ label: COPY.typeMore, icon: "i-lucide-info", disabled: true, "data-suite-search-hint": "" });
  else if (status.value === "error")
    state.push({
      label: hasScreen.value ? COPY.failed : COPY.failedNoScreen,
      description: COPY.retry,
      icon: "i-lucide-circle-alert",
      color: "error",
      "data-suite-search-error": "",
      onSelect: keepOpen(retry),
    });
  else if (status.value === "loading") state.push({ label: COPY.searching, icon: "i-lucide-loader", disabled: true });
  else if (status.value === "ready" && !levels.app.length && !levels.suite.length)
    state.push({ label: suiteEmptyCopy(term.value, "suite", appLabel.value), icon: "i-lucide-search-x", disabled: true, "data-suite-search-empty": "" });
  if (levels.suite.length || state.length)
    out.push({
      id: "suite",
      label: COPY.suiteSection,
      ignoreFilter: true,
      items: [...levels.suite.map(({ result, typeLabel }) => resultItem(result, typeLabel)), ...state],
    });
  return out;
});

// Texto da casa não se corta: o rótulo e a descrição do item quebram linha em vez do
// corte com reticências do oficial ("O filtro desta tela c…"). Uma vez aqui.
const SEARCH_UI = {
  itemLabel: "whitespace-normal text-clip",
  itemDescription: "whitespace-normal text-clip",
};

defineExpose({ focus: openSearch, open: openSearch });
</script>

<template>
  <div
    :class="variant === 'hero' ? 'w-full md:w-[34rem]' : variant === 'hotkey' ? 'contents' : 'w-full md:w-fit'"
    data-suite-search
    :data-suite-search-variant="variant"
  >
    <!-- O clique é desta busca: o `toggleSearch` do grupo do Dashboard abriria TODAS as
         `NuxtDashboardSearch` montadas (e fecharia a que acabou de abrir). -->
    <div v-if="variant !== 'hotkey'" class="contents" @click.capture.stop="openSearch">
      <NuxtDashboardSearchButton
        class="w-full suite-page:min-h-control"
        :size="variant === 'hero' ? 'xl' : 'md'"
        :label="modelValue || placeholder"
        :aria-label="label"
        :kbds="variant === 'hero' ? ['/', 'meta', 'k'] : ['/']"
        data-suite-search-input
        :data-suite-search-phone-trigger="variant === 'hero' ? '' : undefined"
      />
    </div>

    <NuxtDashboardSearch
      v-model:search-term="term"
      :open="dialogOpen"
      :groups="levelGroups as never"
      :fullscreen="isPhone"
      :color-mode="false"
      shortcut=""
      :loading="status === 'loading'"
      :placeholder="placeholder"
      :title="label"
      description="Busque nesta tela, neste app ou em toda a suíte."
      preserve-group-order
      :ui="SEARCH_UI"
      data-suite-search-panel
      @update:open="(value: boolean) => (value ? openSearch() : closeDialog())"
    >
      <!-- O pé só existe onde há câmera: o leitor de código (QR do pedido, EAN do insumo). -->
      <template v-if="cameraSupported" #footer>
        <div class="grid gap-2" data-suite-search-camera-row>
          <NuxtButton
            v-if="!cameraOpen"
            color="neutral"
            variant="outline"
            icon="i-lucide-scan-line"
            :label="COPY.camera"
            :loading="cameraStarting"
            data-suite-search-camera
            @click="startCamera"
          />
          <template v-if="cameraOpen">
            <video ref="video" class="aspect-[4/3] w-full rounded-md bg-black object-cover" muted playsinline />
            <p class="text-sm text-muted">{{ COPY.cameraAim }}</p>
            <NuxtButton block color="neutral" variant="outline" :label="COPY.cameraClose" @click="stopCamera()" />
          </template>
          <NuxtAlert v-if="cameraError" color="warning" variant="subtle" :title="cameraError" />
        </div>
      </template>
    </NuxtDashboardSearch>
  </div>
</template>
