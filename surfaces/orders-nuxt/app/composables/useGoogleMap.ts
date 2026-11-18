// O Google Maps de verdade no Gestor (a página Entregas). Mesmo bootstrap do PDV e
// da loja (`loading=async` + callback, depois `importLibrary("maps")`), com a chave
// PÚBLICA do navegador que a projeção entrega. Chave vazia, script que não baixa ou
// chave recusada pelo Google (`gm_authFailure`): a promessa falha e a tela fica com o
// desenho próprio, nunca com um retângulo cinza.
//
// Só os pedaços da API que o mapa das Entregas toca, sem pacote de tipos.

export interface GLatLng {
  lat(): number;
  lng(): number;
}
export interface GPoint {
  x: number;
  y: number;
}
export interface GProjection {
  fromLatLngToDivPixel(latLng: GLatLng | { lat: number; lng: number }): GPoint | null;
}
export interface GPanes {
  overlayMouseTarget: HTMLElement;
}
export interface GOverlayView {
  setMap(map: GMap | null): void;
  getPanes(): GPanes | null;
  getProjection(): GProjection | null;
  onAdd?(): void;
  draw?(): void;
  onRemove?(): void;
}
export interface GLatLngBounds {
  extend(point: { lat: number; lng: number }): GLatLngBounds;
}
export interface GMap {
  fitBounds(bounds: GLatLngBounds, padding?: number | Record<string, number>): void;
  setZoom(zoom: number): void;
  getZoom(): number | undefined;
  /** O gesto do operador (arrastar, dar zoom) chega como evento do mapa. */
  addListener(event: string, handler: () => void): unknown;
  /** Repinta o mapa (o estilo escuro ao trocar o tema). */
  setOptions(options: Record<string, unknown>): void;
}
export interface GMapsLibrary {
  Map: new (element: HTMLElement, options: Record<string, unknown>) => GMap;
  OverlayView: (new () => GOverlayView) & {
    preventMapHitsAndGesturesFrom(element: HTMLElement): void;
  };
}
export interface GCoreLibrary {
  LatLngBounds: new () => GLatLngBounds;
}

declare global {
  interface Window {
    google?: { maps?: { importLibrary?: (name: string) => Promise<unknown> } };
    gm_authFailure?: () => void;
    __shopman_gestor_maps?: Promise<{ maps: GMapsLibrary; core: GCoreLibrary }>;
    __shopman_gestor_maps_ready?: () => void;
  }
}

/** O Google recusou a chave depois de carregar (domínio fora da lista, cota). */
const refused = ref(false);

function bootstrap(key: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window.google?.maps?.importLibrary === "function") return resolve();
    const params = new URLSearchParams({
      key,
      v: "weekly",
      loading: "async",
      language: "pt-BR",
      region: "BR",
      callback: "__shopman_gestor_maps_ready",
    });
    window.__shopman_gestor_maps_ready = () => {
      delete window.__shopman_gestor_maps_ready;
      if (window.google?.maps?.importLibrary) resolve();
      else reject(new Error("Google Maps incompleto"));
    };
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
    script.async = true;
    script.onerror = () => reject(new Error("O Google Maps não baixou"));
    document.head.appendChild(script);
  });
}

export function useGoogleMap() {
  function load(key: string): Promise<{ maps: GMapsLibrary; core: GCoreLibrary }> {
    if (import.meta.server) return Promise.reject(new Error("SSR"));
    if (!key) return Promise.reject(new Error("Sem chave do Google Maps"));
    if (refused.value) return Promise.reject(new Error("O Google recusou a chave"));
    window.gm_authFailure = () => {
      refused.value = true;
    };
    if (!window.__shopman_gestor_maps) {
      window.__shopman_gestor_maps = bootstrap(key)
        .then(async () => {
          const importLibrary = window.google!.maps!.importLibrary!;
          const [maps, core] = await Promise.all([importLibrary("maps"), importLibrary("core")]);
          return { maps: maps as GMapsLibrary, core: core as GCoreLibrary };
        })
        .catch((error) => {
          window.__shopman_gestor_maps = undefined;
          throw error;
        });
    }
    return window.__shopman_gestor_maps;
  }
  return { load, refused: readonly(refused) };
}
