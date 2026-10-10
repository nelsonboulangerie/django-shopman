import type { Ref } from "vue";
import {
  distanceMeters,
  OUTSIDE_CONSENT_KEY,
  outsideConsent,
  type OutsideConsent,
} from "~/presentation/outsideStore";

/**
 * "Você está fora da loja: mostrando o que pede decisão" (G18, prévia v3
 * `depois-gestor-celular` (c), pino 7: "Localização com consentimento: fora da loja o
 * Gestor abre em resumo e decisões. A faixa diz por que a tela está assim").
 *
 * Só no celular e só com o sim de quem segura o dispositivo (guardado no próprio
 * dispositivo: é preferência dele, não do pedido). A posição é comparada AQUI com o
 * ponto da loja (`store_location`, do servidor) e nunca sai do dispositivo. Sem
 * coordenadas da loja, sem permissão do navegador ou sem posição, a tela é a de sempre.
 */
export function useOutsideStore(
  store: () => { lat?: number; lng?: number; radius_m?: number } | null,
  enabled: Ref<boolean>,
) {
  const consent = ref<OutsideConsent>("unknown");
  const distance = ref<number | null>(null);
  const forcedAll = ref(false);

  function read() {
    try {
      consent.value = outsideConsent(localStorage.getItem(OUTSIDE_CONSENT_KEY));
    } catch {
      consent.value = "unknown";
    }
  }
  function save(value: OutsideConsent) {
    consent.value = value;
    try {
      localStorage.setItem(OUTSIDE_CONSENT_KEY, value);
    } catch {
      /* a escolha vale até recarregar */
    }
  }
  function locate() {
    const point = store();
    if (
      consent.value !== "granted" ||
      !point?.lat ||
      !point?.lng ||
      !("geolocation" in navigator)
    )
      return;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        distance.value = distanceMeters(
          position.coords.latitude,
          position.coords.longitude,
          point.lat!,
          point.lng!,
        );
      },
      () => {
        distance.value = null;
      },
      { maximumAge: 60_000, timeout: 10_000 },
    );
  }

  onMounted(() => {
    read();
    locate();
  });
  watch([store, enabled], () => locate());

  const hasStore = computed(() => Boolean(store()?.lat && store()?.lng));
  const askConsent = computed(
    () => enabled.value && hasStore.value && consent.value === "unknown",
  );
  const away = computed(() => {
    const radius = store()?.radius_m ?? 300;
    return (
      enabled.value &&
      !forcedAll.value &&
      consent.value === "granted" &&
      distance.value !== null &&
      distance.value > radius
    );
  });

  return {
    askConsent,
    away,
    allow() {
      save("granted");
      locate();
    },
    decline() {
      save("declined");
    },
    showAll() {
      forcedAll.value = true;
    },
  };
}
