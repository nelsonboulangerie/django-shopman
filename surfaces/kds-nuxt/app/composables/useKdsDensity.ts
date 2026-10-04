// Densidade da grade (tamanho do ticket, boa prática de KDS), lembrada por
// dispositivo. Mora em Ajustes desde a v4 (`cozinha-estacao4.html`, nota 1: "densidade
// e som saem do botão"): o tamanho do ticket é da bancada, não do toque de quem passa.
//
// `min` é a largura MÍNIMA que faz o código + o relógio caberem com folga numa linha
// (nunca truncam). A grade enche em quantas colunas couber a partir daí.
import type { KDSDensity } from "~/presentation/board";

export interface KdsDensityOption {
  key: KDSDensity;
  label: string;
  icon: string;
  min: number;
}

export const KDS_DENSITIES: readonly KdsDensityOption[] = [
  { key: "compact", label: "Compacta", icon: "lucide:grid-3x3", min: 260 },
  { key: "cozy", label: "Padrão", icon: "lucide:layout-grid", min: 320 },
  { key: "roomy", label: "Ampla", icon: "lucide:square", min: 390 },
];

const STORAGE_KEY = "kds.density";

export function useKdsDensity() {
  const density = useState<KDSDensity>("kds-density", () => "cozy");
  const option = computed(() => KDS_DENSITIES.find((d) => d.key === density.value) ?? KDS_DENSITIES[1]!);

  function setDensity(value: KDSDensity) {
    density.value = value;
    if (!import.meta.client) return;
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch {
      // Sem storage, vale só nesta montagem.
    }
  }

  onMounted(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "compact" || stored === "cozy" || stored === "roomy") density.value = stored;
    } catch {
      // Sem storage, fica a padrão.
    }
  });

  return { density, option, setDensity };
}
