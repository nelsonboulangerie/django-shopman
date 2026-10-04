// Densidade da grade (tamanho do ticket, boa prática de KDS). É da ESTAÇÃO provisionada,
// não do dispositivo nem do toque de quem passa (prévia v4 `cozinha-estacao4.html`,
// nota 1: "densidade e som saem do botão: vêm da estação provisionada"). O cadastro
// guarda (`KDSInstance.config["density"]`), o quadro conta ao shell, e os Ajustes gravam.
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

export function useKdsDensity() {
  const board = useKdsBoardState();
  const density = computed<KDSDensity>(() => board.value.density);
  const option = computed(() => KDS_DENSITIES.find((d) => d.key === density.value) ?? KDS_DENSITIES[1]!);
  return { density, option };
}
