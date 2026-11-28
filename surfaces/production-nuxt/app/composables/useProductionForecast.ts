// O PAINEL — read-side da previsão da produção (estilo aeroporto).
// GET /api/v1/backstage/production/forecast/: o painel fica aberto o dia inteiro
// numa tela da loja. O lote que muda chega pelo canal da Produção (ADR-016, WP-F15);
// o poll de 30 s fica de reserva, só enquanto o canal não está aberto.
import type { ProductionForecastProjection, ProductionForecastResponse } from "~/types/production";
import { isoForOffset } from "~/presentation/production";
import { useProductionLive } from "~/composables/useProductionLive";

export function useProductionForecast() {
  const path = "/api/v1/backstage/production/forecast/";
  const selectedDate = ref(isoForOffset(0));

  const { data, pending, error, refresh } = useFetch<ProductionForecastResponse>(path, {
    key: "production-forecast",
    server: true,
    query: computed(() => ({ date: selectedDate.value })),
    onResponseError: operatorSessionOnError,
  });

  const forecast = computed<ProductionForecastProjection | null>(() => data.value?.forecast ?? null);
  const rows = computed(() => forecast.value?.rows ?? []);

  const { realtime, fallbackPollMs } = useProductionLive(refresh, () => 30_000);

  return { forecast, rows, selectedDate, pending, error, refresh, realtime, fallbackPollMs };
}
