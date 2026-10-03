// A Saída mudou para o Gestor (SUITE-UX-FUNCTION-PLAN §9, §15 e §16; frente UX-G3).
//
// Havia duas telas para o mesmo fato: a Saída da Cozinha e a coluna Saída do Gestor,
// com a mesma `advance_order`. Fica uma só, no Gestor: o posto de saída é o Gestor
// com Entrada e Preparo recolhidas. A Cozinha fica com as estações e o Painel de
// retirada. O quiosque que guardou o endereço da Saída (`/saida`, `/expedicao`,
// `/estacao/expedicao`) não pode cair em página vazia: a estação de Saída manda
// para o Gestor já na visão Saída, e o índice das estações leva direto para lá.
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
