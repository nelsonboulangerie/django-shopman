/**
 * Em que rede este dispositivo está vendendo (v4 `pos-tablet-fluxo` 4): a da loja
 * (wi-fi/cabo) ou o 4G dele mesmo, quando o roteador apagou.
 *
 * A pergunta é DESTE dispositivo: o tablet não alcança o agente do PC do Balcão
 * (loopback de outra máquina), então "rede da loja" se lê pelo tipo de conexão que
 * o navegador informa (Network Information API). Onde o navegador não informa
 * (iPad/Safari), a resposta é "unknown" e a tela não afirma nada: aviso que chuta
 * é pior que aviso nenhum. Sem internet nenhuma é o `useConnectivity` do kit.
 */
export type StoreNetwork = "store" | "cellular" | "unknown";

interface NetworkInformationLike extends EventTarget {
  type?: string;
}

export function storeNetworkOf(type: string | undefined): StoreNetwork {
  if (!type) return "unknown";
  if (type === "cellular") return "cellular";
  if (type === "wifi" || type === "ethernet") return "store";
  return "unknown";
}

export function useStoreNetwork() {
  const network = ref<StoreNetwork>("unknown");
  let connection: NetworkInformationLike | undefined;
  const read = () => {
    network.value = storeNetworkOf(connection?.type);
  };
  onMounted(() => {
    connection = (navigator as Navigator & { connection?: NetworkInformationLike }).connection;
    read();
    connection?.addEventListener?.("change", read);
  });
  onBeforeUnmount(() => connection?.removeEventListener?.("change", read));
  return { network };
}
