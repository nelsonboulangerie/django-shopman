// O PAINEL — read-side da previsão da produção (estilo aeroporto).
// GET /api/v1/backstage/production/forecast/ e poll de 30s: o painel fica
// aberto o dia inteiro numa tela da loja, então ele se atualiza sozinho.
import type { ProductionForecastProjection, ProductionForecastResponse } from "~/types/production";
import { isoForOffset } from "~/presentation/production";

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

  useAdaptivePoll(refresh, () => 30_000);

  return { forecast, rows, selectedDate, pending, error, refresh };
}
