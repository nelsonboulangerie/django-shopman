<script setup lang="ts">
// O mapa da corrida na tela "Dirigindo" (#2509, plano §4.5.1 e prévia 5): a linha da rota
// na cor da corrida, as paradas com o código, a próxima em destaque e a moto. Com a chave
// do Google, o mapa de verdade por baixo, que segue a moto até o entregador mexer nele
// ("Centralizar em mim" volta a seguir). Sem chave ou sem rede, o desenho próprio: as
// mesmas linhas e pontos, enquadrados na tela.
import {
  type MapPoint,
  type MapStop,
  frameProjection,
  routeLine
} from '~/presentation/courierRide'

const props = defineProps<{
  stops: MapStop[]
  here: MapPoint | null
  origin: MapPoint | null
  mapsKey: string
  tone: { bg: string, fg: string } | null
  dark: boolean
}>()

const box = ref<HTMLElement | null>(null)
const canvas = ref<HTMLElement | null>(null)
const size = ref({ w: 0, h: 0 })
const real = ref(false)
const following = ref(true)
const tick = ref(0)

let map: google.maps.Map | null = null
let overlay: google.maps.OverlayView | null = null
let observer: ResizeObserver | null = null
let programmatic = false

const framed = computed<MapPoint[]>(() => [
  ...(props.here ? [props.here] : props.origin ? [props.origin] : []),
  ...props.stops.filter(stop => !stop.done)
])
/** A faixa de baixo onde moram "Abrir no Waze", "Abrir no mapa" e "Centralizar em mim". */
const CHIPS_BAND = 96
const flat = computed(() => frameProjection(framed.value.length ? framed.value : props.stops, size.value.w, size.value.h, 48, CHIPS_BAND))

function px (p: MapPoint): { x: number, y: number } {
  if (real.value && overlay) {
    void tick.value
    const q = overlay.getProjection()?.fromLatLngToContainerPixel({ lat: p.lat, lng: p.lng })
    if (q) return { x: q.x, y: q.y }
  }
  return flat.value(p)
}

const line = computed(() => routeLine(props.stops, props.here ?? props.origin).map(px))
const path = computed(() => line.value.map((q, i) => `${i ? 'L' : 'M'}${q.x.toFixed(1)} ${q.y.toFixed(1)}`).join(' '))
const pins = computed(() => props.stops.map(stop => ({ ...stop, ...px(stop) })))
const me = computed(() => (props.here ? px(props.here) : null))
const ink = computed(() => (props.dark ? '#ffffff' : '#000000'))

// Sem POI e sem ônibus; no escuro, o papel escuro. Paleta neutra da página.
function styles (dark: boolean): google.maps.MapTypeStyle[] {
  const base: google.maps.MapTypeStyle[] = [
    { featureType: 'poi', stylers: [{ visibility: 'off' }] },
    { featureType: 'transit', stylers: [{ visibility: 'off' }] }
  ]
  if (!dark) return base
  return [
    ...base,
    { elementType: 'geometry', stylers: [{ color: '#262626' }] },
    { elementType: 'labels.text.fill', stylers: [{ color: '#d4d4d4' }] },
    { elementType: 'labels.text.stroke', stylers: [{ color: '#000000' }] },
    { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#404040' }] },
    { featureType: 'water', stylers: [{ color: '#000000' }] }
  ]
}

function fit () {
  if (!map) return
  const area = new google.maps.LatLngBounds()
  for (const p of framed.value) area.extend({ lat: p.lat, lng: p.lng })
  programmatic = true
  map.fitBounds(area, { top: 56, right: 56, bottom: CHIPS_BAND, left: 56 })
}

function follow () {
  following.value = true
  if (!map) return
  programmatic = true
  if (props.here) map.panTo({ lat: props.here.lat, lng: props.here.lng })
  else fit()
}

async function mountReal () {
  if (!props.mapsKey || !canvas.value) return
  if (!(await loadGoogleMapsWithKey(props.mapsKey)) || !window.google || !canvas.value) return
  const { Map, OverlayView } = (await google.maps.importLibrary('maps')) as google.maps.MapsLibrary
  if (!canvas.value) return
  map = new Map(canvas.value, {
    center: framed.value[0] ?? props.stops[0] ?? { lat: 0, lng: 0 },
    zoom: 15,
    disableDefaultUI: true,
    clickableIcons: false,
    keyboardShortcuts: false,
    gestureHandling: 'greedy',
    styles: styles(props.dark),
    backgroundColor: props.dark ? '#262626' : '#f5f5f5'
  })
  const view = new OverlayView()
  view.onAdd = () => {}
  view.draw = () => { tick.value++ }
  view.onRemove = () => {}
  view.setMap(map)
  overlay = view
  map.addListener('dragstart', () => { following.value = false })
  map.addListener('zoom_changed', () => { if (!programmatic) following.value = false })
  map.addListener('idle', () => { programmatic = false })
  real.value = true
  fit()
}

// A moto andou: o mapa vai junto, a menos que o entregador esteja olhando outra parte.
watch(() => props.here, (where) => {
  if (!map || !where || !following.value) return
  programmatic = true
  map.panTo({ lat: where.lat, lng: where.lng })
})
watch(() => props.dark, value => map?.setOptions({ styles: styles(value) }))

onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    if (entry) size.value = { w: entry.contentRect.width, h: entry.contentRect.height }
  })
  if (box.value) observer.observe(box.value)
  void mountReal()
})
onBeforeUnmount(() => {
  observer?.disconnect()
  overlay?.setMap(null)
  overlay = null
  map = null
})
</script>

<template>
  <div ref="box" class="crm" :data-map="real ? 'google' : 'own'">
    <div ref="canvas" class="crm-canvas" aria-hidden="true" />
    <svg v-if="size.w" class="crm-layer" :viewBox="`0 0 ${size.w} ${size.h}`" aria-hidden="true">
      <template v-if="line.length > 1">
        <path :d="path" fill="none" :stroke="ink" stroke-width="11" stroke-linejoin="round" stroke-linecap="round" />
        <path :d="path" fill="none" :stroke="tone?.bg || ink" stroke-width="6" stroke-linejoin="round" stroke-linecap="round" />
      </template>
    </svg>
    <div
      v-for="pin in pins"
      :key="pin.ref"
      class="crm-pin"
      :class="{ 'is-next': pin.next, 'is-done': pin.done }"
      :style="{ left: `${pin.x}px`, top: `${pin.y}px` }"
      :data-map-stop="pin.code"
    >
      {{ pin.code }}
    </div>
    <div v-if="me" class="crm-me" :style="{ left: `${me.x}px`, top: `${me.y}px` }" data-map-me />
    <div class="crm-actions">
      <slot />
      <button v-if="real && here && !following" type="button" class="crm-chip" @click="follow">Centralizar em mim</button>
    </div>
  </div>
</template>

<style scoped>
.crm {
  position: relative;
  min-height: 0;
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  background: var(--cr-block);
}
.crm-canvas { position: absolute; inset: 0; }
.crm-layer { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.crm-pin {
  position: absolute;
  display: grid;
  min-width: 3rem;
  height: 3rem;
  place-items: center;
  transform: translate(-50%, -50%);
  border: 3px solid var(--cr-fg);
  border-radius: 999px;
  background: var(--cr-bg);
  color: var(--cr-fg);
  padding: 0 0.375rem;
  font-size: 0.9375rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  pointer-events: none;
}
.crm-pin.is-next { min-width: 3.5rem; height: 3.5rem; border-width: 4px; z-index: 1; }
.crm-pin.is-done { opacity: 0.45; }
.crm-me {
  position: absolute;
  width: 1.5rem;
  height: 1.5rem;
  transform: translate(-50%, -50%);
  border: 4px solid var(--cr-bg);
  border-radius: 999px;
  background: var(--cr-fg);
  box-shadow: 0 0 0 2px var(--cr-fg);
  pointer-events: none;
  z-index: 2;
}
.crm-actions {
  position: absolute;
  right: max(0.75rem, env(safe-area-inset-right));
  bottom: 0.75rem;
  left: max(0.75rem, env(safe-area-inset-left));
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.5rem;
  pointer-events: none;
}
.crm-actions > :deep(*) { pointer-events: auto; }
.crm-chip, .crm-actions :deep(.crm-chip) {
  display: flex;
  min-height: 3rem;
  align-items: center;
  border: 0;
  border-radius: 999px;
  background: var(--cr-bg);
  color: var(--cr-fg);
  padding: 0 1rem;
  font-family: inherit;
  font-size: 0.9375rem;
  font-weight: 800;
  text-decoration: none;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25);
  cursor: pointer;
}
</style>
