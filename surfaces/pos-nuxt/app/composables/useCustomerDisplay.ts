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
