// A COBRANÇA da corrida ficou para trás (P2-28): o pedido mudou depois de chamar o
// entregador (itens, troco, forma de pagar) e a observação que ele lê no celular,
// na porta, ainda diz o antigo. A TaOn não altera a observação de uma corrida
// aberta (a API só abre, consulta e cancela); o caminho é cancelar e chamar de
// novo, ou, depois da coleta, ligar para o entregador.
//
// O fato é do servidor (`courier.charge_outdated`, no bloco `courier` do Gestor e
// do PDV); aqui só a frase.

export interface CourierChargeOutdated {
  /** O que a corrida leva ("Cobrar R$ 50,00 em dinheiro · troco para R$ 100,00"). */
  sent: string;
  /** O que o pedido diz agora. */
  current: string;
  /** O entregador já coletou: cancelar não serve mais. */
  collected: boolean;
}

export interface CourierChargeNotice {
  title: string;
  description: string;
}

export const COURIER_CHARGE_TITLE = "O pedido mudou depois da chamada";

/**
 * O aviso, ou `null` quando a corrida leva a cobrança certa. `cancelHere`: a tela
 * tem o "Solicitar cancelamento" (o Gestor); no PDV, ele mora no Gestor.
 */
export function courierChargeNotice(
  outdated: CourierChargeOutdated | null | undefined,
  { cancelHere }: { cancelHere: boolean },
): CourierChargeNotice | null {
  if (!outdated) return null;
  const facts = `Na corrida: ${outdated.sent}. No pedido: ${outdated.current}.`;
  const advice = outdated.collected
    ? "O entregador já coletou: ligue para ele e passe a cobrança nova."
    : cancelHere
      ? "A TaOn não muda a corrida aberta: solicite o cancelamento e chame o entregador de novo."
      : "A TaOn não muda a corrida aberta: no Gestor de pedidos, solicite o cancelamento e chame o entregador de novo.";
  return { title: COURIER_CHARGE_TITLE, description: `${facts} ${advice}` };
}
