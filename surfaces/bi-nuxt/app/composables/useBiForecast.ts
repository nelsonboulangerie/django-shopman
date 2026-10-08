import type { BIForecastReport, BIReading } from "~/types/bi";
import { forecastFromQuery, forecastToQuery, type ForecastHorizon } from "~/presentation/forecast";
import { addDays, todayIso, type PeriodSelection } from "../../../operator-kit/app/presentation/dates";

export type { ForecastHorizon };

/** Granularidades da projeção: o dia, a semana (segunda a domingo) e o mês. */
const FORECAST_PRESETS = ["day", "week", "month"] as const;

/**
 * "O que esperar", e esta é a única página do B.I. que NÃO usa a janela
 * compartilhada da barra.
 *
 * A janela da barra responde "que período do passado eu quero olhar". Aqui a
 * pergunta é outra: "que dia do futuro eu quero planejar". Amarrar as duas faria
 * o gestor mudar o período de análise sem querer ao escolher a data da fornada,
 * e, pior, sugeriria que a projeção lê só aquele pedaço do passado, quando ela
 * sempre varre o histórico inteiro atrás de dias parecidos.
 *
 * O controle é o mesmo "Período" do kit, com o seu próprio estado: o horizonte é
 * a granularidade, o dia planejado é a âncora (a semana e o mês são os que o
 * contêm, como o servidor calcula). O estado mora na URL com chaves próprias
 * (`horizon`, `target`): o "Copiar link desta leitura" abre o mesmo dia planejado.
 */
export function useBiForecast() {
  const route = useRoute();
  const router = useRouter();
  const tomorrow = () => addDays(todayIso(), 1);

  const plan = computed(() => forecastFromQuery(route.query, tomorrow()));
  const target = computed(() => plan.value.target);
  const horizon = computed<ForecastHorizon>(() => plan.value.horizon);

  const period = computed<PeriodSelection>({
    get: () => ({ preset: horizon.value, from: target.value === todayIso() ? "" : target.value, to: "" }),
    set: (next) => {
      const rest = Object.fromEntries(
        Object.entries(route.query).filter(([key]) => key !== "horizon" && key !== "target"),
      );
      const value = { horizon: next.preset as ForecastHorizon, target: next.from || todayIso() };
      void router.replace({ query: { ...rest, ...forecastToQuery(value, tomorrow()) } });
    },
  });

  const query = computed(() => ({ target: target.value, horizon: horizon.value }));

  const { data, pending, error, refresh } = useFetch<BIReading<BIForecastReport>>(
    "/api/v1/backstage/bi/forecast/",
    {
      key: "bi-forecast",
      server: true,
      query,
      onResponseError: operatorSessionOnError,
    },
  );

  const report = computed(() => data.value?.bi ?? null);
  const freshness = computed(() => ({ generated_at: data.value?.generated_at ?? null }));

  return { report, freshness, pending, error, refresh, target, horizon, period, presets: FORECAST_PRESETS };
}
