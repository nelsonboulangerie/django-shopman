// A contagem leve das Entregas (`deliveries/count/`), UMA leitura para o selo do menu e
// para o Painel (#2876): `waiting` (entregas do dia sem corrida chamada; `null` quando
// o servidor não conseguiu contar) e `call_refs` (os prontos que dá para chamar agora,
// que ganham o "Chamar entregador" no cartão). A mesma chave nos dois lugares: um
// pedido só, relido a cada push do canal de pedidos (quem relê é `useGestorSections`).
export interface DeliveriesWaiting {
  waiting?: number | null;
  call_refs?: string[];
}

export function useDeliveriesWaiting() {
  return useFetch<DeliveriesWaiting>("/api/v1/backstage/deliveries/count/", {
    key: "orders:rail:deliveries",
    server: false,
  });
}
