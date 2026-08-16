import type { BIForecastReport } from "~/types/bi";

export type ForecastHorizon = "day" | "week" | "month";

/**
 * "O que esperar" — e esta é a única página do B.I. que NÃO usa a janela
 * compartilhada da barra.
 *
 * A janela da barra responde "que período do passado eu quero olhar". Aqui a
 * pergunta é outra: "que dia do futuro eu quero planejar". Amarrar as duas faria
 * o gestor mudar o período de análise sem querer ao escolher a data da fornada —
 * e, pior, sugeriria que a projeção lê só aquele pedaço do passado, quando ela
 * sempre varre o histórico inteiro atrás de dias parecidos.
 */
export function useBiForecast() {
  const target = ref(tomorrow());
  const horizon = ref<ForecastHorizon>("day");

  const query = computed(() => ({ target: target.value, horizon: horizon.value }));

  const { data, pending, error, refresh } = useFetch<{ bi: BIForecastReport }>(
    "/api/v1/backstage/bi/forecast/",
    {
      key: "bi-forecast",
      server: true,
      query,
      onResponseError: operatorSessionOnError,
    },
  );

  const report = computed(() => data.value?.bi ?? null);

  return { report, pending, error, refresh, target, horizon };
}

function tomorrow(): string {
  const day = new Date();
  day.setDate(day.getDate() + 1);
  return day.toISOString().slice(0, 10);
}
