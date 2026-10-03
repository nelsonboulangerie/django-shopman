// A Saída é a coluna Saída do Gestor (SUITE-UX-FUNCTION-PLAN §9, §15 e §16; frente UX-G3).
//
// A Cozinha fica com as estações de preparo e o Painel de retirada; a estação de Saída
// do cadastro não tem tela aqui. O índice das estações leva quem escolhe a Saída direto
// para o Gestor, já na visão Saída.
//
// `columns=expedition` é lido pelo Gestor (`orders-nuxt/app/composables/useBoardLayout.ts`,
// `BOARD_COLUMNS_QUERY`): abre o quadro só com a Saída e guarda a arrumação no posto.

/** O tipo da estação de Saída no cadastro (`KDSInstance.type`). */
export const EXIT_STATION_TYPE = "expedition";

/** A coluna Saída do Gestor, já como posto de saída. Vazio sem a URL do Gestor. */
export function gestorExitUrl(ordersUrl: string): string {
  const base = (ordersUrl || "").trim().replace(/\/+$/, "");
  return base ? `${base}/?columns=expedition` : "";
}
