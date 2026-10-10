// Janela de análise compartilhada entre as páginas. O controle é o "Período" do
// kit (`OperatorPeriodPicker`, Tipo 2): Período (Dia…Ano), Últimos (7D…Máx),
// Personalizado, e ‹ › que andam um período igual. A seleção vira
// date_from/date_to na query da API; o backend normaliza e clampa: o contrato é
// do servidor, aqui é UX.
//
// A janela MORA NA URL (`?period=week&from=…`, plano SUITE-UX): o link colado
// numa conversa abre a mesma janela, o voltar do navegador volta a janela junto,
// e recarregar não a perde. As abas da barra levam a mesma query (`windowQuery`),
// para trocar de aba não trocar de período. Sem nada na URL, vale o padrão (28D).
//
// `max` é hoje: no B.I. o calendário corre do início do período até hoje, e o
// futuro é assunto da Projeção, que não usa esta janela.
import { DATA_EPOCH } from "~/presentation/bi";
import {
  PAST_PERIOD_PRESETS,
  PERIOD_QUERY_KEYS,
  customPeriod,
  isCurrentPeriod,
  periodFromQuery,
  periodToQuery,
  resolvePeriod,
  todayIso,
  type PeriodBounds,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";

/** O B.I. olha o passado inteiro: todas as granularidades, mais o personalizado. */
const BI_PERIOD_PRESETS = PAST_PERIOD_PRESETS;

/** A janela quando a URL não diz nada. */
export const BI_DEFAULT_WINDOW: PeriodSelection = { preset: "28d", from: "", to: "" };

const QUERY_OPTIONS = { presets: BI_PERIOD_PRESETS, custom: true, fallback: BI_DEFAULT_WINDOW };

export function useBiWindow() {
  const route = useRoute();
  const router = useRouter();

  const selection = computed<PeriodSelection>({
    get: () => periodFromQuery(route.query, QUERY_OPTIONS),
    set: (next) => {
      const rest = Object.fromEntries(
        Object.entries(route.query).filter(([key]) => !(PERIOD_QUERY_KEYS as readonly string[]).includes(key)),
      );
      void router.replace({ query: { ...rest, ...periodToQuery(next, BI_DEFAULT_WINDOW) } });
    },
  });

  /** As chaves da janela na URL, para as abas da barra levarem junto. */
  const windowQuery = computed(() => periodToQuery(selection.value, BI_DEFAULT_WINDOW));

  const bounds = computed<PeriodBounds>(() => {
    const today = todayIso();
    return { today, max: today, epoch: DATA_EPOCH };
  });
  const range = computed(() => resolvePeriod(selection.value, bounds.value));

  function setPreset(key: string) {
    selection.value = { preset: key, from: "", to: "" };
  }

  function applyCustom(from: string, to: string) {
    if (!from || !to) return;
    selection.value = customPeriod(from, to);
  }

  /**
   * Como o cenário salvo guarda a janela: a chave quando ela acompanha hoje
   * ("28D" continua sendo os últimos 28 dias amanhã), o intervalo quando o gestor
   * andou com ‹ › ou escolheu à mão (a semana passada não vira a desta semana).
   */
  const savedWindow = computed((): Record<string, string> => {
    if (isCurrentPeriod(selection.value)) return { preset: selection.value.preset };
    return { from: range.value.date_from, to: range.value.date_to };
  });

  return {
    selection,
    bounds,
    range,
    presets: BI_PERIOD_PRESETS,
    windowQuery,
    setPreset,
    applyCustom,
    savedWindow,
  };
}
