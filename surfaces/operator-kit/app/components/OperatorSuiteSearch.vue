<script setup lang="ts">
// Busca transversal da suíte. A interação e a aparência são dos componentes
// canônicos DashboardSearchButton, Modal, Tabs e CommandPalette do Nuxt UI.
import { useMediaQuery } from "@vueuse/core";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";

import { OPERATOR_APPS, type OperatorAppRef } from "../../appIdentity";
import {
  SUITE_SEARCH_COPY as COPY,
  appCount,
  groupsForScope,
  groupsForType,
  suiteEmptyCopy,
  suiteQueryReady,
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
const text = ref(props.modelValue ?? "");
watch(
  () => props.modelValue,
  (value) => {
    if (value !== undefined && value !== text.value) text.value = value;
  },
);

const isPhone = useMediaQuery("(max-width: 767.98px)");
const dialogOpen = ref(false);
const scopes = computed(() =>
  suiteScopes({ hasScreen: hasScreen.value, appRef }),
);
const scope = ref<SuiteSearchScope>(scopes.value[0]!);
watch(scopes, (next) => {
  if (!next.includes(scope.value)) scope.value = next[0]!;
});
const typeFilter = ref("");

const { groups, apps, status, retry } = useSuiteSearchResults(
  text,
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
const ready = computed(() => suiteQueryReady(text.value));
const scopedGroups = computed(() =>
  groupsForScope(groups.value, scope.value, appRef),
);
const visibleGroups = computed(() =>
  groupsForType(scopedGroups.value, typeFilter.value),
);
const counts = computed<Record<SuiteSearchScope, number | null>>(() => ({
  screen: props.screenCount,
  app:
    ready.value && status.value === "ready"
      ? appCount(apps.value, appRef)
      : null,
  suite:
    ready.value && status.value === "ready" ? suiteTotal(groups.value) : null,
}));

function scopeLabel(value: SuiteSearchScope): string {
  if (value === "screen") return COPY.screenScope;
  if (value === "app") return appLabel.value;
  return COPY.suiteScope;
}
function setText(value: string) {
  text.value = value;
  if (hasScreen.value) emit("update:modelValue", value);
}
function openSearch() {
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
    ? SUITE_SEARCH_SHORTCUTS.filter(
        (command) => command.id !== "suite.search.slash",
      )
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
  cameraSupported.value =
    "BarcodeDetector" in window &&
    Boolean(navigator.mediaDevices?.getUserMedia);
});
async function startCamera() {
  cameraError.value = "";
  cameraOpen.value = true;
  cameraStarting.value = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
    });
    await nextTick();
    if (!video.value) return;
    video.value.srcObject = stream;
    await video.value.play();
    const DetectorClass = (
      window as unknown as { BarcodeDetector: new () => Detector }
    ).BarcodeDetector;
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

const emptyCopy = computed(() =>
  suiteEmptyCopy(text.value, scope.value, appLabel.value),
);
const typeChips = computed(() =>
  scopedGroups.value.map((group) => ({
    type: group.type,
    label: group.label,
    count: group.results.length,
  })),
);
const scopeItems = computed(() =>
  scopes.value.map((value) => ({
    value,
    label:
      counts.value[value] === null
        ? scopeLabel(value)
        : `${scopeLabel(value)} · ${counts.value[value]}`,
    "data-suite-search-scope": value,
  })),
);
const typeItems = computed(() => [
  { value: "", label: "Todos" },
  ...typeChips.value.map((chip) => ({
    value: chip.type,
    label: `${chip.label} · ${chip.count}`,
    "data-suite-search-type": chip.type,
  })),
]);
const commandGroups = computed(() =>
  visibleGroups.value.map((group) => ({
    id: group.type,
    label: group.label,
    ignoreFilter: true,
    items: group.results.map((result) => ({
      id: result.key,
      label: result.title,
      description: [result.place, result.detail].filter(Boolean).join(" · "),
      icon: `i-lucide-${result.icon}`,
      to: result.url,
      target: linkFor(result).target,
      rel: linkFor(result).rel,
      "aria-label": suiteResultLabel(result),
      "data-suite-search-result": "",
      "data-type": result.type,
      onSelect: () => closeDialog(),
    })),
  })),
);

defineExpose({ focus: openSearch, open: openSearch });
</script>

<template>
  <div
    :class="
      variant === 'hero'
        ? 'w-full md:w-[34rem]'
        : variant === 'hotkey'
          ? 'contents'
          : 'w-full md:w-fit'
    "
    data-suite-search
    :data-suite-search-variant="variant"
  >
    <NuxtDashboardSearchButton
      v-if="variant !== 'hotkey'"
      class="w-full suite-page:min-h-control"
      :size="variant === 'hero' ? 'xl' : 'md'"
      :label="text || placeholder"
      :aria-label="label"
      :kbds="variant === 'hero' ? ['/', 'meta', 'k'] : ['/']"
      data-suite-search-input
      :data-suite-search-phone-trigger="variant === 'hero' ? '' : undefined"
      @click="openSearch"
    />

    <NuxtModal
      :open="dialogOpen"
      :fullscreen="isPhone"
      :title="label"
      description="Busque nesta tela, neste app ou em toda a suíte."
      @update:open="(value) => (value ? openSearch() : closeDialog())"
    >
      <template #body>
        <div class="grid gap-3" data-suite-search-dialog>
          <NuxtTabs
            v-model="scope"
            :items="scopeItems"
            :content="false"
            variant="pill"
            aria-label="Alcance da busca"
            data-suite-search-scopes
          />
          <NuxtTabs
            v-if="typeItems.length > 1"
            v-model="typeFilter"
            :items="typeItems"
            :content="false"
            variant="link"
            aria-label="Tipo de resultado"
            data-suite-search-chips
          />

          <NuxtButton
            v-if="cameraSupported && !cameraOpen"
            color="neutral"
            variant="outline"
            icon="i-lucide-scan-line"
            :label="COPY.camera"
            :loading="cameraStarting"
            data-suite-search-camera
            data-suite-search-camera-row
            @click="startCamera"
          />
          <NuxtCard
            v-if="cameraOpen"
            variant="soft"
            data-suite-search-camera-view
          >
            <video
              ref="video"
              class="aspect-[4/3] w-full bg-black object-cover"
              muted
              playsinline
            />
            <template #footer>
              <div class="grid gap-2">
                <p class="text-sm text-muted-foreground">
                  {{ COPY.cameraAim }}
                </p>
                <NuxtButton
                  block
                  color="neutral"
                  variant="outline"
                  :label="COPY.cameraClose"
                  @click="stopCamera()"
                />
              </div>
            </template>
          </NuxtCard>
          <NuxtAlert
            v-if="cameraError"
            color="warning"
            variant="subtle"
            :title="cameraError"
          />

          <NuxtAlert
            v-if="scope === 'screen' && text"
            color="neutral"
            variant="subtle"
            :title="
              screenCount === null
                ? `A tela está filtrada por “${text.trim()}”.`
                : `${screenCount === 1 ? '1 na tela' : `${screenCount} na tela`} com “${text.trim()}”.`
            "
            :description="screenLabel || undefined"
            data-suite-search-screen-line
          >
            <template #actions
              ><NuxtButton
                color="neutral"
                variant="outline"
                label="Ver na tela"
                @click="closeDialog"
            /></template>
          </NuxtAlert>

          <NuxtCommandPalette
            :search-term="text"
            :groups="commandGroups"
            :loading="status === 'loading'"
            :input="{
              placeholder: isPhone ? 'Buscar em toda a suíte' : placeholder,
            }"
            :aria-label="label"
            preserve-group-order
            data-suite-search-panel
            @update:search-term="setText"
          >
            <template #empty>
              <!-- O #empty do CommandPalette centraliza o texto; o Alert volta ao início. -->
              <NuxtAlert
                v-if="!ready"
                class="text-start"
                color="neutral"
                variant="subtle"
                icon="i-lucide-info"
                :title="COPY.typeMore"
                data-suite-search-hint
              />
              <NuxtAlert
                v-else-if="status === 'error'"
                class="text-start"
                color="error"
                variant="subtle"
                icon="i-lucide-circle-alert"
                :title="hasScreen ? COPY.failed : COPY.failedNoScreen"
                :actions="[
                  {
                    label: COPY.retry,
                    color: 'error',
                    variant: 'outline',
                    onClick: retry,
                  },
                ]"
                data-suite-search-error
              />
              <NuxtEmpty
                v-else-if="status === 'loading'"
                icon="i-line-md-loading-loop"
                :title="COPY.searching"
              />
              <NuxtEmpty
                v-else
                icon="i-lucide-search-x"
                :title="emptyCopy"
                data-suite-search-empty
              />
            </template>
          </NuxtCommandPalette>
        </div>
      </template>
    </NuxtModal>
  </div>
</template>
