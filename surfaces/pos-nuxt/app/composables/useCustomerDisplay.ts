// Sincronização da tela do cliente: MESMA máquina, MESMO navegador, duas
// janelas (a estação e o segundo monitor). A estação PUBLICA snapshots prontos
// (presentation pura) num BroadcastChannel; a janela `/display` só CONSOME —
// nunca busca dado nem emite comando. Sem servidor no meio: o display mostra
// exatamente o que a estação vê, no instante em que ela vê.
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from "vue";

import type { CustomerDisplaySnapshot } from "~/types/customerDisplay";

export const CUSTOMER_DISPLAY_CHANNEL = "pos-customer-display";

type CustomerDisplayMessage =
  | { kind: "snapshot"; snapshot: CustomerDisplaySnapshot }
  // O display recém-aberto pede o estado atual — sem isso ele ficaria nas
  // boas-vindas até a próxima mudança na estação.
  | { kind: "hello" };

function openChannel(): BroadcastChannel | null {
  if (typeof BroadcastChannel === "undefined") return null;
  return new BroadcastChannel(CUSTOMER_DISPLAY_CHANNEL);
}

/** Nome da janela: clicar de novo reaproveita a existente em vez de empilhar outra. */
export const CUSTOMER_DISPLAY_WINDOW = "pos-customer-display";

/**
 * Abrir a TELA DO CLIENTE — e, no mesmo gesto, perguntar se há versão nova.
 *
 * Por que a sonda mora aqui: abrir a segunda janela é um dos poucos gestos do balcão
 * que comprovadamente NÃO acontece no meio de uma venda (é preparação de estação, uma
 * vez por turno). O que ela resolve não é a janela nova — essa já nasce na versão
 * nova, porque a navegação é `NetworkOnly` e o HTML fresco aponta para os arquivos
 * novos, que o worker velho não tem no precache e deixa passar para a rede. Quem está
 * preso é a JANELA DO OPERADOR, aberta há dias: a sonda faz o worker em espera ser
 * descoberto AGORA, e é isso que acende o aviso "Nova versão disponível" e dá o que
 * aplicar quando o balcão esvaziar.
 *
 * ⚠️ E é por isso também que a tela do cliente NUNCA aplica a troca por conta própria:
 * `skipWaiting` vale para a ORIGEM inteira, e toda janela que viu o worker em espera
 * recarrega junto. A tela do cliente, que ninguém toca, seria considerada ociosa
 * sempre — e recarregaria o PDV no meio da venda.
 */
export function useCustomerDisplayWindow() {
  const pwa = usePwaUpdate();

  function open(): boolean {
    if (!import.meta.client) return false;
    void pwa.checkForUpdate();
    return Boolean(window.open("/display", CUSTOMER_DISPLAY_WINDOW));
  }

  return { open };
}

/** Lado da ESTAÇÃO: publica cada snapshot novo e responde ao "hello" do display. */
export function useCustomerDisplayPublisher(snapshot: Ref<CustomerDisplaySnapshot>) {
  let channel: BroadcastChannel | null = null;

  function publish() {
    if (!channel) return;
    const message: CustomerDisplayMessage = { kind: "snapshot", snapshot: snapshot.value };
    channel.postMessage(message);
  }

  onMounted(() => {
    channel = openChannel();
    if (!channel) return;
    channel.onmessage = (event: MessageEvent) => {
      if ((event.data as CustomerDisplayMessage | null)?.kind === "hello") publish();
    };
    publish();
  });

  watch(snapshot, () => publish());

  onBeforeUnmount(() => {
    channel?.close();
    channel = null;
  });

  return { publish };
}

/** Lado do DISPLAY: consome snapshots; `null` enquanto a estação não falou. */
export function useCustomerDisplayConsumer() {
  const snapshot = ref<CustomerDisplaySnapshot | null>(null);
  let channel: BroadcastChannel | null = null;

  onMounted(() => {
    channel = openChannel();
    if (!channel) return;
    channel.onmessage = (event: MessageEvent) => {
      const message = event.data as CustomerDisplayMessage | null;
      if (message?.kind === "snapshot" && message.snapshot) snapshot.value = message.snapshot;
    };
    const hello: CustomerDisplayMessage = { kind: "hello" };
    channel.postMessage(hello);
  });

  onBeforeUnmount(() => {
    channel?.close();
    channel = null;
  });

  return { snapshot };
}
