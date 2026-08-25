import type { POSAddressAutocompleteProjection } from "~/types/pos";
import type { GoogleNamespace, GooglePlacesLibrary } from "~/types/googleMaps";

declare global {
  interface Window {
    google?: GoogleNamespace;
    __shopman_pos_maps_loading?: Promise<GooglePlacesLibrary>;
    __shopman_pos_maps_ready?: () => void;
  }
}

/**
 * Loader da Google Maps JS API para o PDV — bootstrap `loading=async` + callback,
 * depois `importLibrary("places")` (Places API New). Mesmo desenho do
 * `useGoogleMaps` do storefront; a chave e o viés de localização vêm da
 * capability `address_autocomplete` do contrato de checkout.
 */
export function usePosGoogleMaps(capability: Ref<POSAddressAutocompleteProjection | null | undefined>) {
  const isAvailable = computed(() => {
    const config = capability.value;
    return Boolean(config?.enabled && config.public_api_key && config.provider === "google_places");
  });

  function injectBootstrap(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (typeof window.google?.maps?.importLibrary === "function") {
        resolve();
        return;
      }
      const config = capability.value;
      const params = new URLSearchParams({
        key: config?.public_api_key || "",
        v: "weekly",
        loading: "async",
        language: config?.language || "pt-BR",
        region: config?.region || "BR",
        callback: "__shopman_pos_maps_ready",
      });
      window.__shopman_pos_maps_ready = () => {
        delete window.__shopman_pos_maps_ready;
        if (window.google?.maps?.importLibrary) resolve();
        else reject(new Error("Google Maps bootstrap incompleto"));
      };
      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
      script.async = true;
      script.onerror = () => reject(new Error("Falha ao carregar o Google Maps"));
      document.head.appendChild(script);
    });
  }

  /** Carrega (uma vez por página) e devolve a biblioteca Places (New). */
  function ensureLoaded(): Promise<GooglePlacesLibrary> {
    if (typeof window === "undefined") return Promise.reject(new Error("SSR"));
    if (!capability.value?.public_api_key) {
      return Promise.reject(new Error("Chave do Google Maps não configurada"));
    }
    if (window.__shopman_pos_maps_loading) return window.__shopman_pos_maps_loading;
    window.__shopman_pos_maps_loading = injectBootstrap()
      .then(() => window.google?.maps?.importLibrary?.("places"))
      .then((places) => {
        if (!places?.AutocompleteSuggestion) {
          throw new Error("Biblioteca Places indisponível");
        }
        return places;
      })
      .catch((error) => {
        window.__shopman_pos_maps_loading = undefined;
        throw error;
      });
    return window.__shopman_pos_maps_loading;
  }

  return { isAvailable, ensureLoaded };
}
