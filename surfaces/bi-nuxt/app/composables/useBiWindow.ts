// Janela de análise compartilhada entre as páginas: chips de bolsa (1D…Máx,
// "No ano") + período personalizado. A seleção vira date_from/date_to na
// query; o backend normaliza e clampa — o contrato é do servidor, aqui é UX.
import { resolveWindowRange, type WindowSelection } from "~/presentation/bi";

export function useBiWindow() {
  const selection = useState<WindowSelection>("bi-window", () => ({
    preset: "28d",
    from: "",
    to: "",
  }));

  const range = computed(() => resolveWindowRange(selection.value));

  function setPreset(key: string) {
    selection.value = { preset: key, from: "", to: "" };
  }

  function applyCustom(from: string, to: string) {
    if (!from || !to) return;
    selection.value = { preset: "custom", from, to };
  }

  return { selection, range, setPreset, applyCustom };
}
