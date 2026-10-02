import type { BIForecastReport } from "~/types/bi";
import { addDays, todayIso, type PeriodSelection } from "../../../operator-kit/app/presentation/dates";

export type ForecastHorizon = "day" | "week" | "month";

/** Granularidades da projeção: o dia, a semana (segunda a domingo) e o mês. */
const FORECAST_PRESETS = ["day", "week", "month"] as const;

/**
 * "O que esperar" — e esta é a única página do B.I. que NÃO usa a janela
 * compartilhada da barra.
 *
 * A janela da barra responde "que período do passado eu quero olhar". Aqui a
 * pergunta é outra: "que dia do futuro eu quero planejar". Amarrar as duas faria
 * o gestor mudar o período de análise sem querer ao escolher a data da fornada —
 * e, pior, sugeriria que a projeção lê só aquele pedaço do passado, quando ela
 * sempre varre o histórico inteiro atrás de dias parecidos.
 *
 * O controle é o mesmo "Período" do kit, com o seu próprio estado: o horizonte é
 * a granularidade, o dia planejado é a âncora (a semana e o mês são os que o
 * contêm, como o servidor calcula).
 */
export function useBiForecast() {
  const target = ref(addDays(todayIso(), 1));
  const horizon = ref<ForecastHorizon>("day");

  const period = computed<PeriodSelection>({
    get: () => ({ preset: horizon.value, from: target.value === todayIso() ? "" : target.value, to: "" }),
    set: (next) => {
      horizon.value = next.preset as ForecastHorizon;
      target.value = next.from || todayIso();
    },
  });

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

  return { report, pending, error, refresh, target, horizon, period, presets: FORECAST_PRESETS };
}
