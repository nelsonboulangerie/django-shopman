import type { POSTabProjection } from "~/types/pos";
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

/**
 * As seções que o rail do PDV publica para a barra do polegar do celular. O rail
 * escreve, a barra lê: uma leitura das Encomendas por tela, não duas.
 */
export function usePosSectionsState() {
  return useState<{ sections: OperatorSection[]; current: string }>("pos-sections", () => ({
    sections: [],
    current: "board",
  }));
}

/** As comandas da última leitura da Projection, para o selo das Comandas no rail. */
export function usePosTabsState() {
  return useState<POSTabProjection[]>("pos-tabs", () => []);
}
