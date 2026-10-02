// Janela de análise compartilhada entre as páginas. O controle é o "Período" do
// kit (`OperatorPeriodPicker`, Tipo 2): chips de bolsa (Dia…Máx), personalizado e
// ‹ › que andam um período igual. A seleção vira date_from/date_to na query; o
// backend normaliza e clampa: o contrato é do servidor, aqui é UX.
//
// `max` é hoje: no B.I. o calendário corre do início do período até hoje, e o
// futuro é assunto da Projeção, que não usa esta janela.
import { DATA_EPOCH } from "~/presentation/bi";
import {
  customPeriod,
  isCurrentPeriod,
  resolvePeriod,
  todayIso,
  type PeriodBounds,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";

/** Granularidades que o B.I. aceita: todas, mais o personalizado. */
const BI_PERIOD_PRESETS = ["day", "week", "month", "year", "7d", "28d", "3m", "6m", "1y", "5y", "max"] as const;

export function useBiWindow() {
  const selection = useState<PeriodSelection>("bi-window", () => ({
    preset: "28d",
    from: "",
    to: "",
  }));

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

  return { selection, bounds, range, presets: BI_PERIOD_PRESETS, setPreset, applyCustom, savedWindow };
}
