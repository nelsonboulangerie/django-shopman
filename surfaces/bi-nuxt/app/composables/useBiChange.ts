import type { Ref } from "vue";
import type { BIChangeReport } from "~/types/bi";
import type { ForecastHorizon } from "./useBiForecast";

/**
 * Quanto de troco separar. Anda junto com a projeção porque é a mesma decisão
 * de véspera, e recebe o dia e o horizonte de fora em vez de manter os seus: se
 * cada bloco guardasse a própria data, a tela mostraria o faturamento de sábado
 * ao lado do troco de sexta sem nada denunciando o desencontro.
 */
export function useBiChange(target: Ref<string>, horizon: Ref<ForecastHorizon>) {
  const query = computed(() => ({ target: target.value, horizon: horizon.value }));

  const { data, pending, error, refresh } = useFetch<{ bi: BIChangeReport }>(
    "/api/v1/backstage/bi/change/",
    {
      key: "bi-change",
      server: true,
      query,
      onResponseError: operatorSessionOnError,
    },
  );

  return { change: computed(() => data.value?.bi ?? null), pending, error, refresh };
}
