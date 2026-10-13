<script setup lang="ts">
// O PONTO DA ENTREGA NO MAPA, o mesmo passo da loja online (AddressPicker): o pin
// fica parado no centro e o MAPA é que se move até o pin cair no portão certo.
// Dois usos, como lá:
//   - "É aqui que vamos entregar?": logo depois de escolher uma sugestão do Google,
//     quando a loja liga a confirmação (`map_confirmation_enabled`, a mesma chave
//     do site);
//   - "Ajustar no mapa": a qualquer momento, com o endereço já preenchido.
// No balcão o teclado manda: as setas movem o mapa, Enter confirma e Esc volta.
// A tela não resolve endereço: devolve o ponto, e quem o descreve é o servidor.
import type { POSAddressAutocompleteProjection } from "~/types/pos";
import type { GoogleMap } from "~/types/googleMaps";
import { pointMoved, type AddressPoint } from "~/presentation/address";

const props = defineProps<{
  open: boolean;
  capability: POSAddressAutocompleteProjection | null;
  /** Onde o pin nasce (o ponto do Google ou o já confirmado). */
  point: AddressPoint | null;
  /** `confirm`: logo depois da sugestão. `adjust`: o operador pediu para ajustar. */
  purpose: "confirm" | "adjust";
  /** A linha do endereço, para o operador ler em voz alta antes de confirmar. */
  summary: string;
  busy?: boolean;
  issue?: string;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  confirm: [{ point: AddressPoint; moved: boolean }];
  cancel: [];
}>();

const isOpen = computed({
  get: () => props.open,
  set: (value: boolean) => {
    if (!value) emit("cancel");
    emit("update:open", value);
  },
});

const title = computed(() => (props.purpose === "confirm" ? "É aqui que vamos entregar?" : "Ajustar no mapa"));
const confirmLabel = computed(() => (props.purpose === "confirm" ? "É aqui" : "Confirmar"));

const capabilityRef = computed(() => props.capability);
const { loadMaps } = usePosGoogleMaps(capabilityRef);

const mapEl = ref<HTMLElement | null>(null);
const loading = ref(false);
const loadIssue = ref("");
const moved = ref(false);
let map: GoogleMap | null = null;
let session = 0;

function center(): AddressPoint | null {
  const value = map?.getCenter?.();
  return value ? { lat: value.lat(), lng: value.lng() } : null;
}

function teardown() {
  session += 1;
  if (map) window.google?.maps?.event?.clearInstanceListeners?.(map);
  map = null;
}

async function mount() {
  const start = props.point;
  if (!start) return;
  const mine = ++session;
  moved.value = false;
  loadIssue.value = "";
  loading.value = true;
  await nextTick();
  try {
    const maps = await loadMaps();
    if (mine !== session || !mapEl.value || !maps.Map) return;
    map = new maps.Map(mapEl.value, {
      center: start,
      zoom: 17,
      minZoom: 8,
      disableDefaultUI: true,
      zoomControl: true,
      gestureHandling: "greedy",
      clickableIcons: false,
      keyboardShortcuts: false,
      styles: [
        { elementType: "geometry", stylers: [{ saturation: -70 }, { lightness: 8 }] },
        { elementType: "labels.icon", stylers: [{ saturation: -100 }] },
        { featureType: "poi", stylers: [{ visibility: "off" }] },
        { featureType: "transit", stylers: [{ visibility: "off" }] },
      ],
    });
    map.addListener("center_changed", () => {
      const current = center();
      if (mine === session && current) moved.value = pointMoved(start, current);
    });
    mapEl.value.focus({ preventScroll: true });
  } catch {
    if (mine === session) loadIssue.value = "O mapa não está disponível agora. Volte e confira os campos do endereço.";
  } finally {
    if (mine === session) loading.value = false;
  }
}

watch(() => props.open, (open) => {
  if (open) void mount();
  else teardown();
}, { immediate: true });
onBeforeUnmount(teardown);

function confirm() {
  if (props.busy || loading.value) return;
  const start = props.point;
  const point = center() || start;
  if (!point || !start) return;
  emit("confirm", { point, moved: pointMoved(start, point) });
}

function onMapKeydown(event: KeyboardEvent) {
  if (event.key === "Enter") {
    event.preventDefault();
    confirm();
    return;
  }
  const step = 32;
  const offsets: Record<string, [number, number]> = {
    ArrowLeft: [-step, 0],
    ArrowRight: [step, 0],
    ArrowUp: [0, -step],
    ArrowDown: [0, step],
  };
  const offset = offsets[event.key];
  if (!offset || !map) return;
  event.preventDefault();
  map.panBy(offset[0], offset[1]);
}

function onOpenAutoFocus(event: Event) {
  // O foco vai ao MAPA (setas e Enter), não ao primeiro botão.
  event.preventDefault();
}
function onCloseAutoFocus(event: Event) {
  // Quem decide para onde o foco vai depois do mapa é o Recebimento (o próximo
  // campo vazio, ou a busca de volta); devolver à busca atropelaria o passo.
  event.preventDefault();
}
</script>

<template>
  <NuxtModal
    v-model:open="isOpen"
    :title="title"
    description="Mova o mapa até o pin ficar no ponto certo."
    :content="{ onOpenAutoFocus, onCloseAutoFocus }"
    :ui="{ content: 'sm:max-w-2xl', body: 'p-0 sm:p-0' }"
    data-pos-address-map
  >
    <template #body>
      <div class="relative h-[min(60dvh,28rem)]">
        <div
          ref="mapEl"
          class="absolute inset-0 bg-muted outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
          tabindex="0"
          role="application"
          aria-label="Mapa do ponto de entrega. As setas movem o mapa sob o pin; Enter confirma."
          data-pos-address-map-canvas
          @keydown="onMapKeydown"
        />
        <div class="pointer-events-none absolute inset-0 grid place-items-center" aria-hidden="true">
          <div class="-translate-y-4 rounded-full bg-primary p-2 text-inverted shadow-lg ring-4 ring-default/80">
            <Icon name="lucide:map-pin" class="size-6" />
          </div>
        </div>
        <div v-if="loading" class="absolute inset-0 grid place-items-center bg-default/60">
          <Icon name="lucide:loader-circle" class="size-6 animate-spin text-muted" />
        </div>
        <p
          v-if="loadIssue || issue"
          class="absolute inset-x-4 top-3 rounded-md bg-default px-3 py-2 text-sm text-error shadow-sm"
          role="alert"
        >
          {{ loadIssue || issue }}
        </p>
      </div>
    </template>
    <template #footer>
      <div class="grid w-full gap-3">
        <div aria-live="polite" class="grid gap-0.5">
          <p v-if="summary" class="text-sm font-semibold">{{ summary }}</p>
          <p class="text-xs text-muted">{{ moved ? "Ponto ajustado." : "Confira o ponto no mapa antes de continuar." }}</p>
        </div>
        <div class="flex justify-end gap-2">
          <NuxtButton color="neutral" variant="outline" label="Voltar" data-pos-address-map-back @click="isOpen = false" />
          <NuxtButton
            color="primary"
            :label="confirmLabel"
            :loading="busy"
            :disabled="loading || Boolean(loadIssue)"
            data-pos-address-map-confirm
            @click="confirm"
          />
        </div>
      </div>
    </template>
  </NuxtModal>
</template>
